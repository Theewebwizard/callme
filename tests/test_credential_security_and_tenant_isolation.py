"""
Security, Penetration, and Tenant Isolation Test Suite for Credential Vault (Phase 5).
Validates cross-tenant boundaries, cryptographic integrity, anti-zombie fencing,
zero secret leakage across logs/audits, and fail-closed security invariants.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema
from backend.database.models import (
    IntegrationConnection,
    IntegrationCredential,
    utcnow,
)
from backend.database.service import DatabaseService
from backend.capabilities.vault import (
    encrypt_vault_payload,
    decrypt_vault_payload,
    CredentialDecryptionError,
    redact_credential_dict,
)
from backend.capabilities.oauth_refresh import execute_oauth_refresh_with_lease
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.integrations.resolver import resolve_tool_adapter, UnconfiguredAdapter


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
# 1. Cross-Tenant Isolation & Privilege Escalation Prevention
# ==============================================================================

def test_cross_tenant_credential_access_prevention(test_db_service):
    """
    Verify Tenant Beta cannot read, resolve, or borrow credentials owned by Tenant Alpha,
    even when Tenant Beta knows Tenant Alpha's connection_id or tool_id.
    """
    # Tenant Alpha creates a private Google Calendar connection
    conn_alpha = test_db_service.create_connection(
        business_id="biz_tenant_alpha",
        provider_id="google_calendar",
        connection_slug="executive-calendar",
        external_account_id="alpha_ceo@alphacorp.com",
        is_default=True,
    )
    enc_alpha, fp_a = encrypt_vault_payload({
        "access_token": "ya29.alpha_top_secret_token",
        "client_secret": "alpha_private_secret_9988",
    })
    test_db_service.save_connection_credential(
        connection_id=conn_alpha["id"],
        business_id="biz_tenant_alpha",
        encrypted_secrets=enc_alpha,
        key_fingerprint=fp_a,
    )

    # 1. Tenant Beta attempts to resolve Tenant Alpha's connection directly
    adapter_beta = resolve_tool_adapter(
        business_id="biz_tenant_beta",
        tool_id="check_appointment_availability",
        db_service=test_db_service,
        connection_id=conn_alpha["id"],
    )
    # Must fail closed: return UnconfiguredAdapter without credentials
    assert isinstance(adapter_beta, UnconfiguredAdapter)
    assert adapter_beta.credentials == {}

    # 2. DatabaseService get_connection query with Tenant Beta's business_id fails
    conn_query = test_db_service.get_connection(conn_alpha["id"], business_id="biz_tenant_beta")
    assert conn_query is None

    # 3. DatabaseService raw credential fetch with Tenant Beta's business_id fails
    cred_raw = test_db_service.get_connection_credential_raw(
        business_id="biz_tenant_beta",
        connection_id=conn_alpha["id"],
    )
    assert cred_raw is None


def test_cross_tenant_connection_slug_uniqueness_isolation(test_db_service):
    """
    Verify that tenant slugs are scoped strictly to (business_id, provider_id);
    Tenant Alpha and Tenant Beta can both have a connection named 'default' without collisions.
    """
    conn_alpha = test_db_service.create_connection(
        business_id="biz_tenant_alpha",
        provider_id="stripe",
        connection_slug="default",
        is_default=True,
    )
    conn_beta = test_db_service.create_connection(
        business_id="biz_tenant_beta",
        provider_id="stripe",
        connection_slug="default",
        is_default=True,
    )

    assert conn_alpha["id"] != conn_beta["id"]
    assert conn_alpha["business_id"] == "biz_tenant_alpha"
    assert conn_beta["business_id"] == "biz_tenant_beta"


# ==============================================================================
# 2. Cryptographic Integrity, Nonce Freshness, and Tampering Tests
# ==============================================================================

def test_nonce_freshness_defense_against_replay():
    """Verify encrypting identical plaintext produces distinct nonces and ciphertexts."""
    plaintext = {"key": "same_payload_repeated"}
    enc1_json, fp1 = encrypt_vault_payload(plaintext)
    enc2_json, fp2 = encrypt_vault_payload(plaintext)

    env1 = json.loads(enc1_json)
    env2 = json.loads(enc2_json)

    # Nonces must be strictly distinct (96-bit CSPRNG)
    assert env1["iv"] != env2["iv"]
    assert env1["c"] != env2["c"]
    assert env1["t"] != env2["t"]
    # Fingerprints remain identical (same key used)
    assert fp1 == fp2


def test_bit_flipping_tampering_fails_closed():
    """Verify bit-flipping on ciphertext triggers GCM tag authentication failure."""
    plaintext = {"amount": 1000, "currency": "USD", "destination": "acct_legit"}
    enc_json, _ = encrypt_vault_payload(plaintext)
    env = json.loads(enc_json)

    # Flip one character in the base64 ciphertext
    c_list = list(env["c"])
    c_list[0] = "A" if c_list[0] != "A" else "B"
    env["c"] = "".join(c_list)
    tampered_json = json.dumps(env)

    with pytest.raises(CredentialDecryptionError, match="authentication check"):
        decrypt_vault_payload(tampered_json)


def test_auth_tag_truncation_fails_closed():
    """Verify modifying authentication tag length or bytes fails closed."""
    plaintext = {"token": "valid_token"}
    enc_json, _ = encrypt_vault_payload(plaintext)
    env = json.loads(enc_json)

    # Truncate tag from 16 bytes (24 base64 chars) to 8 bytes
    env["t"] = env["t"][:12]
    tampered_json = json.dumps(env)

    with pytest.raises(CredentialDecryptionError):
        decrypt_vault_payload(tampered_json)


# ==============================================================================
# 3. Anti-Zombie Fencing Token & Lease Safety Tests
# ==============================================================================

def test_expired_lease_worker_cannot_overwrite_newer_commit(test_db_service):
    """
    Verify anti-zombie fencing token guard:
    Worker Alpha acquires lease with fencing_token = 1.
    Worker Alpha stalls (e.g. GC pause). Lease expires.
    Worker Beta acquires lease with fencing_token = 2, commits fresh token (fencing_token becomes 3).
    Worker Alpha wakes up and attempts to commit using stale fencing_token 1 -> REJECTED.
    """
    enc, fp = encrypt_vault_payload({"token": "v0_initial"})
    cred = test_db_service.save_credential(
        business_id="biz_tenant_alpha",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Worker Alpha acquires lease (fencing_token becomes 1)
    fence_alpha = test_db_service.acquire_refresh_lease(
        cred_id=cred["id"],
        worker_id="worker_alpha",
        ttl_seconds=1,  # Short TTL
        business_id="biz_tenant_alpha",
    )
    assert fence_alpha == 1

    # Simulate lease expiry for Worker Alpha
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        c.lease_expires_at = utcnow() - timedelta(seconds=10)
        session.commit()

    # Worker Beta acquires lease after Alpha expires
    fence_beta = test_db_service.acquire_refresh_lease(
        cred_id=cred["id"],
        worker_id="worker_beta",
        ttl_seconds=15,
        business_id="biz_tenant_alpha",
    )
    assert fence_beta == 2

    # Worker Beta commits new credentials (fencing_token increments to 3)
    enc_beta, fp_beta = encrypt_vault_payload({"token": "v1_from_beta"})
    committed_beta = test_db_service.commit_refreshed_credentials(
        cred_id=cred["id"],
        worker_id="worker_beta",
        acquired_fencing_token=fence_beta,
        new_encrypted_secrets=enc_beta,
        new_key_fingerprint=fp_beta,
        business_id="biz_tenant_alpha",
    )
    assert committed_beta is True

    # Now Worker Alpha wakes up and attempts to commit with stale fencing_token = 1
    enc_alpha, fp_alpha = encrypt_vault_payload({"token": "v1_stale_from_alpha"})
    committed_alpha = test_db_service.commit_refreshed_credentials(
        cred_id=cred["id"],
        worker_id="worker_alpha",
        acquired_fencing_token=fence_alpha,
        new_encrypted_secrets=enc_alpha,
        new_key_fingerprint=fp_alpha,
        business_id="biz_tenant_alpha",
    )
    # Stale write MUST be rejected
    assert committed_alpha is False

    # Verify authoritative database state reflects Worker Beta's commit
    raw = test_db_service.get_credential_raw("biz_tenant_alpha", "check_appointment_availability")
    decrypted = decrypt_vault_payload(raw["encrypted_secrets"])
    assert decrypted["token"] == "v1_from_beta"
    assert raw["fencing_token"] == 3


# ==============================================================================
# 4. Crypto-Shredding vs Logical Disconnect Lifecycle Tests
# ==============================================================================

def test_disconnect_integration_crypto_shredding_and_state(test_db_service):
    """
    Verify full lifecycle upon disconnect:
    1. Provider connection status set to 'disconnected'.
    2. Ciphertext and DEK row permanently purged from integration_credentials table.
    3. Live database cannot decrypt or recover the purged credentials.
    """
    conn = test_db_service.create_connection(
        business_id="biz_tenant_alpha",
        provider_id="stripe",
        connection_slug="main",
        status="active",
    )
    enc, fp = encrypt_vault_payload({"secret_key": "sk_live_permanent_secret_123"})
    cred = test_db_service.save_connection_credential(
        connection_id=conn["id"],
        business_id="biz_tenant_alpha",
        encrypted_secrets=enc,
        key_fingerprint=fp,
        tool_id="charge_deposit",
    )

    # Disconnect integration via wizard
    wizard = CapabilitySetupWizard(test_db_service)
    result = wizard.disconnect_integration("biz_tenant_alpha", "charge_deposit")
    assert result["success"] is True

    # 1. Connection marked disconnected
    conn_after = test_db_service.get_connection(conn["id"])
    assert conn_after["status"] == "disconnected"

    # 2. Vault credential purged
    with test_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred["id"])
        assert c is None

    # 3. Resolver returns UnconfiguredAdapter with zero credentials
    adapter = resolve_tool_adapter(
        business_id="biz_tenant_alpha",
        tool_id="charge_deposit",
        db_service=test_db_service,
        connection_id=conn["id"],
    )
    assert isinstance(adapter, UnconfiguredAdapter)
    assert adapter.credentials == {}


# ==============================================================================
# 5. Zero-Leakage Standard Across Logs and Dictionaries
# ==============================================================================

def test_redact_credential_dict_masks_all_sensitive_keys():
    """Verify deep redaction utility masks all sensitive fields recursively."""
    payload = {
        "api_key": "sk_live_51AbcDefGhIjKlMnOpQrStUv",
        "client_secret": "cs_live_998877665544",
        "access_token": "ya29.a0AfH6SMD_very_long_live_access_token",
        "refresh_token": "1//04_refresh_token_secret",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...",
        "short_pin": "1234",
        "ordinary_setting": "clinic_calendar",
        "nested_oauth": {
            "password": "super_secret_db_password",
            "provider_name": "google",
        },
    }

    redacted = redact_credential_dict(payload)

    # Sensitive values must be masked
    assert redacted["api_key"] == "sk_l...StUv"
    assert redacted["client_secret"] == "cs_l...5544"
    assert redacted["access_token"] == "ya29...oken"
    assert redacted["refresh_token"] == "1//0...cret"
    assert redacted["private_key"] == "[REDACTED_SECRET]"
    assert redacted["short_pin"] == "********"
    assert redacted["nested_oauth"]["password"] == "supe...word"

    # Non-sensitive fields preserved
    assert redacted["ordinary_setting"] == "clinic_calendar"
    assert redacted["nested_oauth"]["provider_name"] == "google"

    # Verify original dictionary was not mutated
    assert payload["api_key"] == "sk_live_51AbcDefGhIjKlMnOpQrStUv"
