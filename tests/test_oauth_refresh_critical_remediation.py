"""
Regression and Adversarial Security Test Suite for Critical Findings:
CRITICAL-1: Safe OAuth Credential Preservation & Refresh-Token Rotation
CRITICAL-2: Tenant-Scoped Refresh Lifecycle & Lease Isolation (IDOR Prevention)
"""

import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema
from backend.database.models import IntegrationCredential, utcnow
from backend.database.service import DatabaseService
from backend.capabilities.vault import encrypt_vault_payload, decrypt_vault_payload
from backend.capabilities.oauth_refresh import (
    execute_oauth_refresh_with_lease,
    RefreshCoordinationError,
    TenantIsolationError,
    StaleCommitRejectedError,
    validate_and_sanitize_refresh_response,
)


@pytest.fixture
def test_db_service():
    """Create isolated SQLite in-memory database with two distinct business tenants."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(engine)
    service = DatabaseService(engine=engine)
    service.create_business({
        "id": "biz_tenant_alpha",
        "name": "Alpha Corp",
        "industry": "Clinic",
        "phone_number": "+15551112222",
        "opening_time": "09:00",
        "closing_time": "17:00",
        "timezone": "UTC",
    })
    service.create_business({
        "id": "biz_tenant_beta",
        "name": "Beta Hospitality",
        "industry": "Restaurant",
        "phone_number": "+15553334444",
        "opening_time": "11:00",
        "closing_time": "23:00",
        "timezone": "UTC",
    })
    return service


# ==============================================================================
# CRITICAL-1: Safe OAuth Credential Preservation & Rotation Tests
# ==============================================================================

def test_provider_returns_only_access_token_and_expiration_preserves_refresh_token(test_db_service):
    """
    CRITICAL-1 Verification:
    Provider's refresh response omits refresh_token and client credentials.
    Ensure that existing refresh_token, client_id, and client_secret are preserved in DB.
    """
    initial_secrets = {
        "client_id": "google_client_id_9988.apps.googleusercontent.com",
        "client_secret": "GOCSPX-super_secret_client_key",
        "access_token": "ya29.initial_expired_token",
        "refresh_token": "1//04_permanent_refresh_token_to_preserve",
        "scope": "https://www.googleapis.com/auth/calendar.events",
    }
    enc, fp = encrypt_vault_payload(initial_secrets)
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Upstream mock returns standard OAuth RFC 6749 response: only access_token and expires_in
    async def mock_provider_refresh():
        return {
            "access_token": "ya29.brand_new_access_token_2026",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    refreshed = asyncio.run(
        execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_tenant_alpha",
            cred_id=cred["id"],
            refresh_coro_fn=mock_provider_refresh,
            worker_id="worker_preserve",
        )
    )

    # 1. Returned dictionary has new access token and preserved secrets
    assert refreshed["access_token"] == "ya29.brand_new_access_token_2026"
    assert refreshed["refresh_token"] == "1//04_permanent_refresh_token_to_preserve"
    assert refreshed["client_id"] == "google_client_id_9988.apps.googleusercontent.com"
    assert refreshed["client_secret"] == "GOCSPX-super_secret_client_key"

    # 2. Database committed vault record has preserved secrets
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored_secrets = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored_secrets["access_token"] == "ya29.brand_new_access_token_2026"
    assert stored_secrets["refresh_token"] == "1//04_permanent_refresh_token_to_preserve"
    assert stored_secrets["client_id"] == "google_client_id_9988.apps.googleusercontent.com"
    assert stored_secrets["client_secret"] == "GOCSPX-super_secret_client_key"
    assert stored_secrets["scope"] == "https://www.googleapis.com/auth/calendar.events"


def test_provider_returns_rotated_refresh_token(test_db_service):
    """
    CRITICAL-1 Verification:
    Provider issues a new rotated refresh_token.
    Ensure old refresh_token is replaced by the new one, while preserving client credentials.
    """
    initial_secrets = {
        "client_id": "ms_client_id_123",
        "client_secret": "ms_secret_456",
        "access_token": "old_token",
        "refresh_token": "old_refresh_token_v1",
    }
    enc, fp = encrypt_vault_payload(initial_secrets)
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Upstream mock returns rotated refresh token
    async def mock_rotating_refresh():
        return {
            "access_token": "new_rotated_access_token",
            "refresh_token": "new_rotated_refresh_token_v2",
            "expires_in": 7200,
        }

    refreshed = asyncio.run(
        execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_tenant_alpha",
            cred_id=cred["id"],
            refresh_coro_fn=mock_rotating_refresh,
            worker_id="worker_rot",
        )
    )

    assert refreshed["access_token"] == "new_rotated_access_token"
    assert refreshed["refresh_token"] == "new_rotated_refresh_token_v2"
    assert refreshed["client_id"] == "ms_client_id_123"

    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["refresh_token"] == "new_rotated_refresh_token_v2"
    assert stored["client_id"] == "ms_client_id_123"
    assert stored["client_secret"] == "ms_secret_456"


def test_provider_response_omits_client_credentials(test_db_service):
    """
    CRITICAL-1 Verification:
    Verify that standard provider responses omitting client credentials never purge client_id/client_secret.
    """
    initial_secrets = {
        "client_id": "authoritative_client_id",
        "client_secret": "authoritative_client_secret",
        "access_token": "token_v0",
        "refresh_token": "refr_v0",
    }
    enc, fp = encrypt_vault_payload(initial_secrets)
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    async def mock_refresh():
        return {"access_token": "token_v1", "expires_in": 1800}

    asyncio.run(
        execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_tenant_alpha",
            cred_id=cred["id"],
            refresh_coro_fn=mock_refresh,
        )
    )

    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["client_id"] == "authoritative_client_id"
    assert stored["client_secret"] == "authoritative_client_secret"
    assert stored["refresh_token"] == "refr_v0"


def test_provider_response_malformed_or_incomplete(test_db_service):
    """
    CRITICAL-1 Verification:
    Malformed responses (missing access_token, invalid types, negative expiration) fail closed.
    Stored credentials remain unaltered and the lease is released.
    """
    initial_secrets = {"access_token": "intact_token", "refresh_token": "intact_refresh"}
    enc, fp = encrypt_vault_payload(initial_secrets)
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # 1. Missing access_token
    async def mock_missing_token():
        return {"expires_in": 3600}

    with pytest.raises(RefreshCoordinationError, match="missing valid non-empty 'access_token'"):
        asyncio.run(
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_tenant_alpha",
                cred_id=cred["id"],
                refresh_coro_fn=mock_missing_token,
            )
        )

    # 2. Negative expires_in
    async def mock_negative_exp():
        return {"access_token": "new_tok", "expires_in": -50}

    with pytest.raises(RefreshCoordinationError, match="must be positive"):
        asyncio.run(
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_tenant_alpha",
                cred_id=cred["id"],
                refresh_coro_fn=mock_negative_exp,
            )
        )

    # 3. Not a dictionary
    async def mock_string_response():
        return "Not a JSON dictionary"

    with pytest.raises(RefreshCoordinationError, match="must be a dict"):
        asyncio.run(
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_tenant_alpha",
                cred_id=cred["id"],
                refresh_coro_fn=mock_string_response,
            )
        )

    # Verify database was never modified
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["access_token"] == "intact_token"
    assert stored["refresh_token"] == "intact_refresh"

    # Verify lease was cleanly released
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        assert c.lease_owner_id is None


def test_refresh_fails_before_persistence(test_db_service):
    """
    CRITICAL-1 Verification:
    If upstream refresh call throws an exception, stored credentials are untouched
    and the lease is released.
    """
    initial_secrets = {"access_token": "valid_old_token", "refresh_token": "valid_refresh"}
    enc, fp = encrypt_vault_payload(initial_secrets)
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    async def mock_network_error():
        raise ConnectionResetError("Provider TCP connection dropped")

    with pytest.raises(ConnectionResetError):
        asyncio.run(
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_tenant_alpha",
                cred_id=cred["id"],
                refresh_coro_fn=mock_network_error,
            )
        )

    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["access_token"] == "valid_old_token"

    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        assert c.lease_owner_id is None


def test_stale_worker_cannot_commit_merged_payload(test_db_service):
    """
    CRITICAL-1 Verification:
    A stale worker whose lease expired cannot overwrite newer credentials with an obsolete payload.
    """
    enc, fp = encrypt_vault_payload({"access_token": "v0_tok", "refresh_token": "v0_refr"})
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Worker Alpha acquires lease (fencing_token = 1)
    fence_a = test_db_service.acquire_refresh_lease(
        cred_id=cred["id"],
        worker_id="worker_alpha",
        ttl_seconds=1,
        business_id="biz_tenant_alpha",
    )
    assert fence_a == 1

    # Worker Alpha stalls; lease expires
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        c.lease_expires_at = utcnow() - timedelta(seconds=10)
        session.commit()

    # Worker Beta acquires lease and commits new credentials
    fence_b = test_db_service.acquire_refresh_lease(
        cred_id=cred["id"],
        worker_id="worker_beta",
        ttl_seconds=30,
        business_id="biz_tenant_alpha",
    )
    assert fence_b == 2

    enc_b, fp_b = encrypt_vault_payload({"access_token": "v1_from_beta", "refresh_token": "v0_refr"})
    committed_b = test_db_service.commit_refreshed_credentials(
        cred_id=cred["id"],
        worker_id="worker_beta",
        acquired_fencing_token=fence_b,
        new_encrypted_secrets=enc_b,
        new_key_fingerprint=fp_b,
        business_id="biz_tenant_alpha",
    )
    assert committed_b is True

    # Stale Worker Alpha attempts to commit with stale fencing_token 1 -> Rejected!
    enc_a, fp_a = encrypt_vault_payload({"access_token": "v1_stale_from_alpha", "refresh_token": "v0_refr"})
    committed_a = test_db_service.commit_refreshed_credentials(
        cred_id=cred["id"],
        worker_id="worker_alpha",
        acquired_fencing_token=fence_a,
        new_encrypted_secrets=enc_a,
        new_key_fingerprint=fp_a,
        business_id="biz_tenant_alpha",
    )
    assert committed_a is False

    # Authoritative record reflects Worker Beta's commit
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["access_token"] == "v1_from_beta"


def test_existing_secrets_remain_intact_after_successful_refresh(test_db_service):
    """
    CRITICAL-1 Verification:
    Verify that arbitrary custom provider configuration (scopes, redirect URI, endpoints)
    remains completely unaltered when refreshing an access token.
    """
    initial_secrets = {
        "client_id": "app_client_id_001",
        "client_secret": "app_secret_xyz",
        "access_token": "old_token",
        "refresh_token": "permanent_refresh_key",
        "redirect_uri": "https://callme.example.com/oauth/callback",
        "token_uri": "https://oauth2.googleapis.com/token",
        "custom_settings": {"calendar_id": "primary", "sync_events": True},
    }
    enc, fp = encrypt_vault_payload(initial_secrets)
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    async def mock_refresh():
        return {"access_token": "refreshed_access_token_ok", "expires_in": 3600}

    refreshed = asyncio.run(
        execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_tenant_alpha",
            cred_id=cred["id"],
            refresh_coro_fn=mock_refresh,
        )
    )

    assert refreshed["access_token"] == "refreshed_access_token_ok"
    assert refreshed["redirect_uri"] == "https://callme.example.com/oauth/callback"
    assert refreshed["custom_settings"]["calendar_id"] == "primary"

    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["redirect_uri"] == "https://callme.example.com/oauth/callback"
    assert stored["custom_settings"]["sync_events"] is True


# ==============================================================================
# CRITICAL-2: Tenant-Scoped Refresh Lifecycle & Lease Isolation (IDOR Tests)
# ==============================================================================

def test_cross_tenant_cannot_refresh_by_supplying_id(test_db_service):
    """
    CRITICAL-2 Verification:
    Tenant Beta supplies Tenant Alpha's cred_id to execute_oauth_refresh_with_lease.
    Must fail closed immediately with TenantIsolationError.
    No lease acquired, no fencing token incremented, no upstream call made.
    """
    enc_alpha, fp_a = encrypt_vault_payload({
        "client_id": "alpha_cid",
        "access_token": "alpha_tok",
        "refresh_token": "alpha_refr",
    })
    cred_alpha = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc_alpha,
        key_fingerprint=fp_a,
    )

    call_count = 0

    async def mock_upstream():
        nonlocal call_count
        call_count += 1
        return {"access_token": "attacker_token"}

    # Tenant Beta attempts to refresh Tenant Alpha's credential
    with pytest.raises(TenantIsolationError, match="Access denied"):
        asyncio.run(
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_tenant_beta",  # Malicious caller
                cred_id=cred_alpha["id"],
                refresh_coro_fn=mock_upstream,
            )
        )

    # 1. Zero upstream calls were made
    assert call_count == 0

    # 2. Fencing token remained 0 (lease was NOT acquired)
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    assert raw["fencing_token"] == 0

    # 3. Tenant Alpha's secrets remained unaltered
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["access_token"] == "alpha_tok"


def test_cross_tenant_cannot_read_fresh_token_during_polling(test_db_service):
    """
    CRITICAL-2 Verification:
    Tenant Alpha has a fresh token committed in the DB.
    Tenant Beta cannot read Tenant Alpha's fresh token through polling deduplication.
    """
    # Tenant Alpha's token expires in 1 hour (already fresh in DB)
    fresh_time = datetime.now(timezone.utc) + timedelta(hours=1)
    enc_alpha, fp_a = encrypt_vault_payload({
        "access_token": "alpha_fresh_secret_token",
        "refresh_token": "alpha_refresh",
    })
    cred_alpha = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc_alpha,
        key_fingerprint=fp_a,
        expires_at=fresh_time,
    )

    async def mock_refresh():
        return {"access_token": "never"}

    # Tenant Beta attempts to obtain Tenant Alpha's fresh token
    with pytest.raises(TenantIsolationError):
        asyncio.run(
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_tenant_beta",
                cred_id=cred_alpha["id"],
                refresh_coro_fn=mock_refresh,
            )
        )


def test_cross_tenant_cannot_acquire_or_release_lease(test_db_service):
    """
    CRITICAL-2 Verification:
    Tenant Beta cannot acquire or release Tenant Alpha's lease.
    """
    enc, fp = encrypt_vault_payload({"token": "alpha_data"})
    cred_alpha = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # 1. Tenant Beta attempts to acquire lease on Tenant Alpha's credential
    token_beta = test_db_service.acquire_refresh_lease(
        cred_id=cred_alpha["id"],
        worker_id="worker_beta",
        business_id="biz_tenant_beta",
    )
    assert token_beta is None

    # Verify fencing token was not incremented
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    assert raw["fencing_token"] == 0

    # 2. Tenant Alpha acquires legitimate lease
    token_alpha = test_db_service.acquire_refresh_lease(
        cred_id=cred_alpha["id"],
        worker_id="worker_alpha",
        business_id="biz_tenant_alpha",
    )
    assert token_alpha == 1

    # 3. Tenant Beta attempts to release Tenant Alpha's held lease
    released_by_beta = test_db_service.release_refresh_lease(
        cred_id=cred_alpha["id"],
        worker_id="worker_alpha",
        business_id="biz_tenant_beta",
    )
    assert released_by_beta is False

    # Verify lease is still held by worker_alpha
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred_alpha["id"])
        assert c.lease_owner_id == "worker_alpha"


def test_cross_tenant_cannot_commit_to_another_tenant_record(test_db_service):
    """
    CRITICAL-2 Verification:
    Tenant Beta cannot commit new credentials to Tenant Alpha's record.
    """
    enc, fp = encrypt_vault_payload({"token": "alpha_initial"})
    cred_alpha = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Alpha acquires lease
    fence_a = test_db_service.acquire_refresh_lease(
        cred_id=cred_alpha["id"],
        worker_id="worker_alpha",
        business_id="biz_tenant_alpha",
    )
    assert fence_a == 1

    # Tenant Beta attempts commit using acquired fencing token 1
    malicious_enc, m_fp = encrypt_vault_payload({"token": "malicious_overwrite"})
    committed_by_beta = test_db_service.commit_refreshed_credentials(
        cred_id=cred_alpha["id"],
        worker_id="worker_alpha",
        acquired_fencing_token=1,
        new_encrypted_secrets=malicious_enc,
        new_key_fingerprint=m_fp,
        business_id="biz_tenant_beta",
    )
    assert committed_by_beta is False

    # Verify Alpha's stored credential remains unmodified
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["token"] == "alpha_initial"


def test_valid_same_tenant_refresh_coordination_works(test_db_service):
    """
    Verify standard authorized same-tenant refresh coordination succeeds completely.
    """
    enc, fp = encrypt_vault_payload({
        "client_id": "cid_valid",
        "access_token": "old_token",
        "refresh_token": "refr_valid",
    })
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    async def mock_refresh():
        return {"access_token": "new_authorized_token", "expires_in": 3600}

    refreshed = asyncio.run(
        execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_tenant_alpha",
            cred_id=cred["id"],
            refresh_coro_fn=mock_refresh,
            worker_id="worker_legit",
        )
    )

    assert refreshed["access_token"] == "new_authorized_token"
    assert refreshed["refresh_token"] == "refr_valid"
    assert refreshed["client_id"] == "cid_valid"

    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    assert raw["fencing_token"] == 2


# ==============================================================================
# Strict Required business_id Validation Tests (Omitted Tenant Fails Closed)
# ==============================================================================

def test_omitted_tenant_id_fails_closed_on_acquire_lease(test_db_service):
    """
    Verify that omitting business_id or passing None/empty to acquire_refresh_lease
    fails closed immediately with ValueError before any database operation.
    """
    enc, fp = encrypt_vault_payload({"token": "init"})
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # 1. Omitted business_id
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.acquire_refresh_lease(cred["id"], worker_id="worker_anon")

    # 2. Explicit None
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.acquire_refresh_lease(cred["id"], worker_id="worker_anon", business_id=None)

    # 3. Empty string
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.acquire_refresh_lease(cred["id"], worker_id="worker_anon", business_id="   ")

    # Verify no lease was acquired and fencing token was not incremented
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    assert raw["fencing_token"] == 0
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        assert c.lease_owner_id is None


def test_omitted_tenant_id_fails_closed_on_commit_credentials(test_db_service):
    """
    Verify that omitting business_id or passing None/empty to commit_refreshed_credentials
    fails closed immediately with ValueError without modifying the stored record.
    """
    enc, fp = encrypt_vault_payload({"token": "original_payload"})
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Alpha legitimately acquires lease
    fence = test_db_service.acquire_refresh_lease(
        cred["id"],
        worker_id="worker_alpha",
        business_id="biz_tenant_alpha",
    )
    assert fence == 1

    # Attempt commit with omitted business_id
    new_enc, new_fp = encrypt_vault_payload({"token": "tampered"})
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.commit_refreshed_credentials(
            cred_id=cred["id"],
            worker_id="worker_alpha",
            acquired_fencing_token=fence,
            new_encrypted_secrets=new_enc,
        )

    # Attempt commit with explicit None
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.commit_refreshed_credentials(
            cred_id=cred["id"],
            worker_id="worker_alpha",
            acquired_fencing_token=fence,
            new_encrypted_secrets=new_enc,
            business_id=None,
        )

    # Verify database was NOT updated
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    stored = decrypt_vault_payload(raw["encrypted_secrets"])
    assert stored["token"] == "original_payload"


def test_omitted_tenant_id_fails_closed_on_release_lease(test_db_service):
    """
    Verify that omitting business_id or passing None/empty to release_refresh_lease
    fails closed immediately with ValueError without releasing the held lease.
    """
    enc, fp = encrypt_vault_payload({"token": "init"})
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Alpha acquires lease
    test_db_service.acquire_refresh_lease(
        cred["id"],
        worker_id="worker_alpha",
        business_id="biz_tenant_alpha",
    )

    # Attempt release without business_id
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.release_refresh_lease(cred["id"], worker_id="worker_alpha")

    # Attempt release with explicit None
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.release_refresh_lease(cred["id"], worker_id="worker_alpha", business_id=None)

    # Verify lease is still held
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        assert c.lease_owner_id == "worker_alpha"


def test_repository_level_omitted_tenant_id_fails_closed(test_db_service):
    """
    Verify ConnectionRepository methods directly reject omitted or None business_id
    before executing any SQL query.
    """
    from backend.database.repositories.connection_repo import ConnectionRepository

    enc, fp = encrypt_vault_payload({"token": "init"})
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    with test_db_service.session_factory() as session:
        repo = ConnectionRepository(session)

        with pytest.raises(ValueError, match="business_id is required"):
            repo.acquire_refresh_lease(cred["id"], worker_id="w1", business_id=None)

        with pytest.raises(ValueError, match="business_id is required"):
            repo.commit_refreshed_credentials(
                cred_id=cred["id"],
                worker_id="w1",
                acquired_fencing_token=1,
                new_encrypted_secrets=enc,
                business_id=None,
            )

        with pytest.raises(ValueError, match="business_id is required"):
            repo.release_refresh_lease(cred["id"], worker_id="w1", business_id=None)

