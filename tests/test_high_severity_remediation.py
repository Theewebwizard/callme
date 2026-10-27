"""
Regression and Adversarial Security Tests for Level 2 (High-Severity) Remediation:
1. HIGH-1: Capability Wizard Disconnect Purges Connection-Bound Credentials.
2. HIGH-2: AES-256-GCM Authenticated Additional Data (AAD) Prevents Cross-Tenant Transplantation.
3. HIGH-3: Dynamic Schema Migration Skips Non-SQLite Engines (Alembic Authoritative Guard).
4. HIGH-4: Credential Migration Tool Batch-Size Pagination & Discrete Transactions.
"""

import base64
import json
import os
import hashlib
import hmac
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema, migrate_schema_columns
from backend.database.models import (
    IntegrationConnection,
    IntegrationCredential,
)
from backend.database.service import DatabaseService
from backend.capabilities.vault import (
    encrypt_vault_payload,
    decrypt_vault_payload,
    get_active_vault_key,
    CredentialDecryptionError,
)
from backend.capabilities.credentials import (
    encrypt_credentials,
    decrypt_credentials,
)
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.capabilities.migration_tool import (
    migrate_credentials,
    is_v2_envelope,
)


def _create_legacy_v1_envelope(secrets: dict, key: bytes) -> str:
    """Helper to construct an authentic legacy v1 HMAC keystream envelope."""
    iv = os.urandom(16)
    raw_bytes = json.dumps(secrets, sort_keys=True).encode("utf-8")

    keystream = hashlib.sha256(key + iv).digest()
    while len(keystream) < len(raw_bytes):
        keystream += hashlib.sha256(keystream + key).digest()

    cipher_bytes = bytes(b ^ k for b, k in zip(raw_bytes, keystream[:len(raw_bytes)]))
    mac = hmac.new(key, iv + cipher_bytes, hashlib.sha256).digest()

    envelope = {
        "v": 1,
        "iv": base64.b64encode(iv).decode("ascii"),
        "c": base64.b64encode(cipher_bytes).decode("ascii"),
        "t": base64.b64encode(mac).decode("ascii"),
    }
    return json.dumps(envelope)


@pytest.fixture
def test_db_service():
    """Create isolated SQLite in-memory database with test business profile."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(engine)
    service = DatabaseService(engine=engine)
    service.create_business({
        "id": "biz_high_alpha",
        "name": "Alpha Clinic",
        "industry": "Clinic",
        "phone_number": "+15551112222",
        "opening_time": "08:00",
        "closing_time": "18:00",
        "timezone": "UTC",
    })
    service.create_business({
        "id": "biz_high_beta",
        "name": "Beta Bistro",
        "industry": "Restaurant",
        "phone_number": "+15553334444",
        "opening_time": "10:00",
        "closing_time": "22:00",
        "timezone": "UTC",
    })
    return service


# ==============================================================================
# HIGH-1: Capability Wizard Disconnect Purges Connection-Bound Credentials
# ==============================================================================

def test_disconnect_integration_purges_connection_bound_credentials(test_db_service):
    """
    Verify wizard.disconnect_integration:
    1. Identifies connection-bound credentials where tool_id defaults to conn_{id}.
    2. Calls provider revocation hook with decrypted credentials.
    3. Updates connection status to 'disconnected'.
    4. Purges the credential row from integration_credentials table.
    """
    # Create active connection
    conn = test_db_service.create_connection(
        business_id="biz_high_alpha",
        provider_id="google_calendar",
        connection_slug="main",
        status="active",
        is_default=True,
    )

    # Save connection-bound credential with default tool_id (conn_{conn_id})
    enc, fp = encrypt_vault_payload({"refresh_token": "refr_conn_secret_9988"})
    cred = test_db_service.save_connection_credential(
        connection_id=conn["id"],
        business_id="biz_high_alpha",
        encrypted_secrets=enc,
        key_fingerprint=fp,
        option_id="google_calendar",
        tool_id=None,  # Defaults to conn_{conn["id"]}
    )

    # Configure tool capability
    test_db_service.set_tool_capability(
        business_id="biz_high_alpha",
        tool_id="check_appointment_availability",
        is_enabled=True,
        selected_option_id="google_calendar",
        configuration={"connection_id": conn["id"]},
    )

    wizard = CapabilitySetupWizard(test_db_service)

    with patch("backend.capabilities.wizard.revoke_oauth_provider_credentials") as mock_revoke:
        mock_revoke.return_value = True

        result = wizard.disconnect_integration("biz_high_alpha", "check_appointment_availability")
        assert result["success"] is True

        # 1. Outbound provider revocation was invoked with decrypted credentials
        assert mock_revoke.called
        called_creds = mock_revoke.call_args[1]["credentials"]
        assert called_creds["refresh_token"] == "refr_conn_secret_9988"

        # 2. Connection record updated to disconnected
        conn_after = test_db_service.get_connection(conn["id"], business_id="biz_high_alpha")
        assert conn_after["status"] == "disconnected"

        # 3. Connection credential purged from vault
        raw_cred = test_db_service.get_connection_credential_raw("biz_high_alpha", conn["id"])
        assert raw_cred is None

        # 4. Direct DB check confirms row was deleted
        with test_db_service.session_factory() as session:
            db_row = session.get(IntegrationCredential, cred["id"])
            assert db_row is None


def test_delete_connection_credential_requires_tenant_id(test_db_service):
    """Verify delete_connection_credential strictly enforces non-empty business_id."""
    conn = test_db_service.create_connection(
        business_id="biz_high_alpha",
        provider_id="google_calendar",
    )
    enc, fp = encrypt_vault_payload({"token": "test"})
    test_db_service.save_connection_credential(
        connection_id=conn["id"],
        business_id="biz_high_alpha",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Reject None
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.delete_connection_credential(conn["id"], None)

    # Reject blank string
    with pytest.raises(ValueError, match="business_id is required"):
        test_db_service.delete_connection_credential(conn["id"], "   ")


def test_delete_connection_credential_cross_tenant_isolation(test_db_service):
    """Verify tenant Beta cannot delete tenant Alpha's connection credentials."""
    conn_alpha = test_db_service.create_connection(
        business_id="biz_high_alpha",
        provider_id="google_calendar",
    )
    enc, fp = encrypt_vault_payload({"token": "alpha_secret"})
    cred_alpha = test_db_service.save_connection_credential(
        connection_id=conn_alpha["id"],
        business_id="biz_high_alpha",
        encrypted_secrets=enc,
        key_fingerprint=fp,
    )

    # Beta attempts to delete Alpha's connection credential
    deleted = test_db_service.delete_connection_credential(conn_alpha["id"], business_id="biz_high_beta")
    assert deleted is False

    # Alpha's credential remains intact
    raw_alpha = test_db_service.get_connection_credential_raw("biz_high_alpha", conn_alpha["id"])
    assert raw_alpha is not None
    assert raw_alpha["id"] == cred_alpha["id"]


# ==============================================================================
# HIGH-2: AES-256-GCM Authenticated Additional Data (AAD)
# ==============================================================================

def test_aes_gcm_aad_cryptographic_binding():
    """
    Verify AES-256-GCM Authenticated Additional Data (AAD):
    1. Binds ciphertext to tenant/context identifier.
    2. Envelope flags 'aad: True'.
    3. Correct AAD decrypts successfully.
    4. Mismatched AAD fails closed with CredentialDecryptionError.
    5. Missing AAD when envelope requires AAD fails closed.
    6. Stripping 'aad: True' flag fails closed via GMAC tag check.
    """
    secrets = {"api_key": "live_secret_key_7777", "webhook_secret": "whsec_abc123"}
    tenant_alpha = "biz_tenant_alpha"
    tenant_beta = "biz_tenant_beta"

    # 1. Encrypt with tenant Alpha's ID as AAD
    encrypted_str, fp = encrypt_vault_payload(secrets, associated_data=tenant_alpha)
    envelope = json.loads(encrypted_str)

    assert envelope["v"] == 2
    assert envelope["alg"] == "AES-256-GCM"
    assert envelope.get("aad") is True

    # 2. Decrypt with correct AAD -> Succeeds
    decrypted = decrypt_vault_payload(encrypted_str, associated_data=tenant_alpha)
    assert decrypted == secrets

    # 3. Decrypt with mismatched AAD (Tenant Beta transplant attack) -> Fails closed
    with pytest.raises(CredentialDecryptionError, match="failed GCM authentication check"):
        decrypt_vault_payload(encrypted_str, associated_data=tenant_beta)

    # 4. Decrypt with missing AAD when envelope expects AAD -> Fails closed
    with pytest.raises(CredentialDecryptionError, match="AAD.*is required"):
        decrypt_vault_payload(encrypted_str, associated_data=None)

    # 5. Adversarial tamper: attacker removes 'aad: True' from envelope and attempts decrypt
    tampered_envelope = dict(envelope)
    del tampered_envelope["aad"]
    tampered_str = json.dumps(tampered_envelope)

    with pytest.raises(CredentialDecryptionError, match="failed GCM authentication check"):
        decrypt_vault_payload(tampered_str, associated_data=None)


def test_aes_gcm_backward_compatibility_without_aad():
    """Verify v2 payloads encrypted without AAD continue to decrypt cleanly."""
    secrets = {"token": "unbound_legacy_v2_secret"}
    encrypted_str, _ = encrypt_vault_payload(secrets, associated_data=None)

    envelope = json.loads(encrypted_str)
    assert "aad" not in envelope or envelope["aad"] is not True

    # Decrypts without AAD
    decrypted = decrypt_vault_payload(encrypted_str, associated_data=None)
    assert decrypted == secrets


def test_credentials_facade_passes_associated_data():
    """Verify encrypt_credentials and decrypt_credentials facade honors associated_data."""
    secrets = {"client_secret": "top_secret_facade_test"}
    aad = "biz_crm_tenant:hubspot"

    enc, _ = encrypt_credentials(secrets, associated_data=aad)
    dec = decrypt_credentials(enc, associated_data=aad)
    assert dec == secrets

    with pytest.raises(CredentialDecryptionError):
        decrypt_credentials(enc, associated_data="different_aad")


# ==============================================================================
# HIGH-3: Dynamic Schema Migration Skips PostgreSQL (Alembic Authoritative)
# ==============================================================================

def test_migrate_schema_columns_skips_postgresql_dialect():
    """Verify migrate_schema_columns completely skips raw DDL on PostgreSQL engines."""
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"

    # Should log and return immediately without calling engine.begin()
    migrate_schema_columns(mock_engine)
    assert not mock_engine.begin.called


def test_migrate_schema_columns_runs_on_sqlite():
    """Verify migrate_schema_columns executes non-destructive PRAGMA checks on SQLite."""
    mem_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(mem_engine)

    # Calling migrate_schema_columns on SQLite completes without error
    migrate_schema_columns(mem_engine)


# ==============================================================================
# HIGH-4: Credential Migration Tool Batch-Size Pagination & Transactions
# ==============================================================================

def test_migration_tool_batch_size_pagination_and_commit_boundaries(test_db_service):
    """
    Verify migrate_credentials respects batch_size:
    1. Populates 7 unmigrated legacy records.
    2. Runs migration with batch_size=3 (3 batches: 3, 3, 1).
    3. Confirms all 7 records are successfully inspected, migrated, and upgraded.
    """
    vault_key = get_active_vault_key()

    # Create 7 legacy credentials
    with test_db_service.session_factory() as session:
        for i in range(1, 8):
            legacy_secrets = {"api_key": f"sec_key_{i:03d}", "tenant_idx": i}
            legacy_cipher = _create_legacy_v1_envelope(legacy_secrets, vault_key)
            cred = IntegrationCredential(
                id=f"cred_batch_{i:03d}",
                business_id="biz_high_alpha" if i % 2 == 1 else "biz_high_beta",
                connection_id=None,
                tool_id=f"tool_batch_{i:03d}",
                option_id="google_calendar" if i % 2 == 1 else "stripe",
                encrypted_secrets=legacy_cipher,
                key_fingerprint="fp_legacy_v1",
                schema_version=1,
            )
            session.add(cred)
        session.commit()

    # Execute migration with batch_size=3
    result = migrate_credentials(
        db_service=test_db_service,
        dry_run=False,
        batch_size=3,
    )

    assert result.dry_run is False
    assert result.success is True
    assert result.total_inspected == 7
    assert result.migrated_count == 7
    assert result.already_migrated_count == 0
    assert result.failed_count == 0

    # Verify all 7 records in the DB have been migrated to schema_version 2
    with test_db_service.session_factory() as session:
        for i in range(1, 8):
            migrated_cred = session.get(IntegrationCredential, f"cred_batch_{i:03d}")
            assert migrated_cred is not None
            assert migrated_cred.schema_version == 2
            assert is_v2_envelope(migrated_cred.encrypted_secrets) is True
            assert migrated_cred.connection_id is not None
            decrypted = decrypt_vault_payload(migrated_cred.encrypted_secrets)
            assert decrypted["api_key"] == f"sec_key_{i:03d}"
            assert decrypted["tenant_idx"] == i


def test_migration_tool_dry_run_batching_rolls_back(test_db_service):
    """Verify dry_run with batch_size processes all batches and safely rolls back."""
    vault_key = get_active_vault_key()

    with test_db_service.session_factory() as session:
        for i in range(1, 5):
            legacy_secrets = {"token": f"dryrun_tok_{i}"}
            legacy_cipher = _create_legacy_v1_envelope(legacy_secrets, vault_key)
            cred = IntegrationCredential(
                id=f"cred_dry_{i:03d}",
                business_id="biz_high_alpha",
                connection_id=None,
                tool_id=f"tool_dry_{i:03d}",
                option_id="google_calendar",
                encrypted_secrets=legacy_cipher,
                key_fingerprint="fp_legacy_v1",
                schema_version=1,
            )
            session.add(cred)
        session.commit()

    # Run dry-run with batch_size=2
    result = migrate_credentials(
        db_service=test_db_service,
        dry_run=True,
        batch_size=2,
    )

    assert result.dry_run is True
    assert result.success is True
    assert result.total_inspected == 4
    assert result.migrated_count == 4

    # Confirm database was NOT mutated
    with test_db_service.session_factory() as session:
        for i in range(1, 5):
            c = session.get(IntegrationCredential, f"cred_dry_{i:03d}")
            assert c.schema_version == 1
            assert c.connection_id is None
