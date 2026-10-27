"""
Tests for Phase 3: Credential Resolution, Provider Integration,
OAuth Refresh Coordination, and Multi-Account Support.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema
from backend.database.service import DatabaseService
from backend.capabilities.vault import encrypt_vault_payload
from backend.capabilities.oauth_refresh import (
    execute_oauth_refresh_with_lease,
    revoke_oauth_provider_credentials,
)
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.integrations.resolver import resolve_tool_adapter, UnconfiguredAdapter


@pytest.fixture
def test_db_service():
    """Create isolated SQLite database for Phase 3 tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(engine)
    service = DatabaseService(engine=engine)
    service.create_business({
        "id": "biz_clinic_apex",
        "name": "Apex Dental Clinic",
        "industry": "Clinic",
        "phone_number": "+15551234567",
        "opening_time": "09:00",
        "closing_time": "18:00",
        "timezone": "UTC",
    })
    service.create_business({
        "id": "biz_dining_spice",
        "name": "Spice Garden",
        "industry": "Restaurant",
        "phone_number": "+15559876543",
        "opening_time": "11:00",
        "closing_time": "23:00",
        "timezone": "UTC",
    })
    return service


# ==============================================================================
# 1. Multi-Account Credential Resolution Tests
# ==============================================================================

def test_resolve_tool_adapter_by_specific_connection_id(test_db_service):
    """Verify adapter resolves credentials for an explicitly requested connection."""
    # Create two separate Google Calendar connections for Apex Clinic
    conn_smith = test_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="builtin_clinic",
        connection_slug="dr-smith",
        external_account_id="smith@apex.com",
        is_default=False,
    )
    conn_jones = test_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="builtin_clinic",
        connection_slug="dr-jones",
        external_account_id="jones@apex.com",
        is_default=True,
    )

    # Store distinct credentials linked to each connection
    enc_smith, fp_s = encrypt_vault_payload({"calendar_owner": "Dr. Smith", "api_key": "sec_smith"})
    test_db_service.save_connection_credential(
        connection_id=conn_smith["id"],
        business_id="biz_clinic_apex",
        encrypted_secrets=enc_smith,
        key_fingerprint=fp_s,
    )

    enc_jones, fp_j = encrypt_vault_payload({"calendar_owner": "Dr. Jones", "api_key": "sec_jones"})
    test_db_service.save_connection_credential(
        connection_id=conn_jones["id"],
        business_id="biz_clinic_apex",
        encrypted_secrets=enc_jones,
        key_fingerprint=fp_j,
    )

    # 1. Explicitly resolve Dr. Smith's connection
    adapter_smith = resolve_tool_adapter(
        business_id="biz_clinic_apex",
        tool_id="create_appointment",
        db_service=test_db_service,
        connection_id=conn_smith["id"],
    )
    assert adapter_smith.credentials["calendar_owner"] == "Dr. Smith"
    assert adapter_smith.credentials["api_key"] == "sec_smith"

    # 2. Explicitly resolve Dr. Jones's connection
    adapter_jones = resolve_tool_adapter(
        business_id="biz_clinic_apex",
        tool_id="create_appointment",
        db_service=test_db_service,
        connection_id=conn_jones["id"],
    )
    assert adapter_jones.credentials["calendar_owner"] == "Dr. Jones"
    assert adapter_jones.credentials["api_key"] == "sec_jones"


def test_cross_tenant_connection_isolation_rejected(test_db_service):
    """Verify attempting to resolve a connection owned by another tenant fails closed."""
    # Connection belongs to Spice Garden
    conn_spice = test_db_service.create_connection(
        business_id="biz_dining_spice",
        provider_id="builtin_dining",
        connection_slug="main-patio",
    )

    # Apex Clinic attempts to resolve Spice Garden's connection
    adapter = resolve_tool_adapter(
        business_id="biz_clinic_apex",
        tool_id="check_table_availability",
        db_service=test_db_service,
        connection_id=conn_spice["id"],
    )
    assert isinstance(adapter, UnconfiguredAdapter)


def test_resolve_default_connection_fallback(test_db_service):
    """Verify resolver automatically selects the default connection when connection_id is omitted."""
    conn_default = test_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="builtin_clinic",
        connection_slug="default-clinic",
        is_default=True,
    )
    enc, fp = encrypt_vault_payload({"default_account": True, "token": "tok_default_123"})
    cred = test_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="builtin_clinic",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )
    test_db_service.link_credential_to_connection(cred["id"], conn_default["id"])

    # Configure tool to use builtin_clinic
    test_db_service.set_tool_capability(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        is_enabled=True,
        selected_option_id="builtin_clinic",
    )

    # Call resolver without connection_id -> picks up default connection
    adapter = resolve_tool_adapter(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        db_service=test_db_service,
    )
    assert adapter.credentials.get("default_account") is True


# ==============================================================================
# 2. Distributed OAuth Refresh Coordination Tests
# ==============================================================================

def test_single_worker_oauth_refresh(test_db_service):
    """Verify standard single worker token refresh with lease and commit."""
    enc, fp = encrypt_vault_payload({"access_token": "old_token", "refresh_token": "refr_123"})
    cred = test_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    async def _run():
        async def mock_refresh_http():
            return {
                "access_token": "new_fresh_token",
                "refresh_token": "refr_123",
                "expires_in": 3600,
            }

        refreshed = await execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_clinic_apex",
            cred_id=cred["id"],
            refresh_coro_fn=mock_refresh_http,
            worker_id="worker_alpha",
        )
        return refreshed

    refreshed = asyncio.run(_run())
    assert refreshed["access_token"] == "new_fresh_token"

    # Verify committed in DB
    raw = test_db_service.get_credential_raw("biz_clinic_apex", "check_appointment_availability")
    assert raw["fencing_token"] == 2  # 1 for acquire, 1 for commit


def test_concurrent_oauth_refresh_deduplication(test_db_service):
    """
    Verify concurrent refresh deduplication:
    5 concurrent coroutines attempt refresh; exactly 1 makes upstream call;
    the other 4 wait and receive the refreshed token from DB.
    """
    enc, fp = encrypt_vault_payload({"access_token": "old_token", "refresh_token": "refr_concurrent"})
    cred = test_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    call_count = 0

    async def _run_concurrent():
        nonlocal call_count

        async def mock_upstream_refresh():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate network latency
            return {
                "access_token": "shared_fresh_token",
                "refresh_token": "refr_concurrent",
                "expires_in": 3600,
            }

        tasks = [
            execute_oauth_refresh_with_lease(
                db_service=test_db_service,
                business_id="biz_clinic_apex",
                cred_id=cred["id"],
                refresh_coro_fn=mock_upstream_refresh,
                worker_id=f"worker_{i}",
                max_wait_seconds=5.0,
            )
            for i in range(5)
        ]

        return await asyncio.gather(*tasks)

    results = asyncio.run(_run_concurrent())

    # Exactly 1 upstream HTTP call made!
    assert call_count == 1
    # All 5 workers received the fresh token!
    for res in results:
        assert res["access_token"] == "shared_fresh_token"


def test_oauth_refresh_bounded_http_timeout(test_db_service):
    """Verify upstream call exceeding bounded HTTP timeout aborts and releases lease."""
    enc, fp = encrypt_vault_payload({"access_token": "token", "refresh_token": "refr"})
    cred = test_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    async def _run_timeout():
        async def hanging_refresh():
            await asyncio.sleep(5.0)  # Exceeds 0.2s timeout
            return {"access_token": "never"}

        await execute_oauth_refresh_with_lease(
            db_service=test_db_service,
            business_id="biz_clinic_apex",
            cred_id=cred["id"],
            refresh_coro_fn=hanging_refresh,
            worker_id="worker_slow",
            http_timeout_seconds=0.2,
        )

    with pytest.raises(TimeoutError, match="timed out"):
        asyncio.run(_run_timeout())

    # Verify lease was cleanly released (lease_owner_id is None)
    with test_db_service.session_factory() as session:
        from backend.database.models import IntegrationCredential
        c = session.get(IntegrationCredential, cred["id"])
        assert c.lease_owner_id is None


# ==============================================================================
# 3. Provider Revocation on Disconnection Tests
# ==============================================================================

def test_revoke_oauth_provider_credentials_google():
    """Verify Google token revocation dispatches POST to revocation endpoint."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        success = revoke_oauth_provider_credentials(
            provider_id="google_calendar",
            credentials={"refresh_token": "ya29.sample_refresh_token_to_revoke"},
        )
        assert success is True
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert "oauth2.googleapis.com/revoke" in req.full_url
        assert "ya29.sample_refresh_token_to_revoke" in req.full_url


def test_disconnect_integration_triggers_revocation_and_purges(test_db_service):
    """Verify disconnect_integration executes outbound revocation, disconnects connection, and purges vault."""
    conn = test_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="main",
        status="active",
    )
    enc, fp = encrypt_vault_payload({"refresh_token": "refr_token_to_revoke_123"})
    cred = test_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )
    test_db_service.link_credential_to_connection(cred["id"], conn["id"])

    wizard = CapabilitySetupWizard(test_db_service)

    with patch("backend.capabilities.wizard.revoke_oauth_provider_credentials") as mock_revoke:
        mock_revoke.return_value = True

        result = wizard.disconnect_integration("biz_clinic_apex", "check_appointment_availability")
        assert result["success"] is True

        # 1. Outbound provider revocation was invoked with decrypted credentials
        assert mock_revoke.called
        called_creds = mock_revoke.call_args[1]["credentials"]
        assert called_creds["refresh_token"] == "refr_token_to_revoke_123"

        # 2. Connection record updated to disconnected
        conn_after = test_db_service.get_connection(conn["id"])
        assert conn_after["status"] == "disconnected"

        # 3. Vault credentials purged
        raw = test_db_service.get_credential_raw("biz_clinic_apex", "check_appointment_availability")
        assert raw is None
