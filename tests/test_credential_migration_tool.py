"""
Tests for Phase 4: Resumable Credential Migration Tooling,
Dry-Run Mode, Redacted Reports, and Rollback Safeguards.
"""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema
from backend.database.models import (
    IntegrationConnection,
    IntegrationCredential,
)
from backend.database.service import DatabaseService
from backend.capabilities.vault import (
    generate_vault_key,
    decrypt_vault_payload,
    get_active_vault_key,
)
from backend.capabilities.migration_tool import (
    migrate_credentials,
    is_v2_envelope,
    CredentialMigrationResult,
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
    """Create isolated SQLite in-memory database with initial tenant records."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(engine)
    service = DatabaseService(engine=engine)
    service.create_business({
        "id": "biz_mig_alpha",
        "name": "Alpha Medical Clinic",
        "industry": "Clinic",
        "phone_number": "+15550001111",
        "opening_time": "08:00",
        "closing_time": "17:00",
        "timezone": "UTC",
    })
    service.create_business({
        "id": "biz_mig_beta",
        "name": "Beta Bistro",
        "industry": "Restaurant",
        "phone_number": "+15550002222",
        "opening_time": "10:00",
        "closing_time": "22:00",
        "timezone": "UTC",
    })
    return service


# ==============================================================================
# 1. Core Migration & Connection Synthesis Tests
# ==============================================================================

def test_migration_upgrades_legacy_v1_and_synthesizes_connection(test_db_service):
    """Verify legacy v1 credentials are re-encrypted to v2 and synthesized into a default connection."""
    vault_key = get_active_vault_key()
    legacy_secrets = {"api_key": "sec_alpha_key_9988", "calendar_id": "cal_alpha@apex.com"}
    legacy_cipher = _create_legacy_v1_envelope(legacy_secrets, vault_key)

    with test_db_service.session_factory() as session:
        cred = IntegrationCredential(
            id="cred_legacy_001",
            business_id="biz_mig_alpha",
            connection_id=None,  # Orphan credential without connection
            tool_id="check_appointment_availability",
            option_id="google_calendar",
            encrypted_secrets=legacy_cipher,
            key_fingerprint="fp_legacy_v1",
            schema_version=1,
        )
        session.add(cred)
        session.commit()

    # Execute live migration
    result = migrate_credentials(db_service=test_db_service, dry_run=False)

    assert result.dry_run is False
    assert result.success is True
    assert result.total_inspected == 1
    assert result.migrated_count == 1
    assert result.already_migrated_count == 0
    assert result.failed_count == 0

    # Verify DB state after migration
    with test_db_service.session_factory() as session:
        migrated_cred = session.get(IntegrationCredential, "cred_legacy_001")
        assert migrated_cred is not None
        assert migrated_cred.schema_version == 2
        assert is_v2_envelope(migrated_cred.encrypted_secrets) is True
        assert migrated_cred.connection_id is not None
        assert migrated_cred.key_fingerprint.startswith("fp_")

        # Verify synthesized connection
        conn = session.get(IntegrationConnection, migrated_cred.connection_id)
        assert conn is not None
        assert conn.business_id == "biz_mig_alpha"
        assert conn.provider_id == "google_calendar"
        assert conn.connection_slug == "default"
        assert conn.is_default is True
        assert conn.status == "active"
        assert conn.metadata_json.get("migrated_from_legacy") is True

        # Verify secret decryption from migrated record
        decrypted = decrypt_vault_payload(migrated_cred.encrypted_secrets)
        assert decrypted == legacy_secrets


# ==============================================================================
# 2. Dry-Run Mode & Rollback Safeguards
# ==============================================================================

def test_dry_run_mode_does_not_mutate_database(test_db_service):
    """Verify dry_run mode performs trial migration and generates report without persisting any changes."""
    vault_key = get_active_vault_key()
    legacy_secrets = {"stripe_account": "acct_test_dryrun", "token": "tok_12345"}
    legacy_cipher = _create_legacy_v1_envelope(legacy_secrets, vault_key)

    with test_db_service.session_factory() as session:
        cred = IntegrationCredential(
            id="cred_dryrun_002",
            business_id="biz_mig_beta",
            connection_id=None,
            tool_id="charge_deposit",
            option_id="stripe",
            encrypted_secrets=legacy_cipher,
            key_fingerprint="fp_legacy_v1",
            schema_version=1,
        )
        session.add(cred)
        session.commit()

    # Execute dry-run migration
    result = migrate_credentials(db_service=test_db_service, dry_run=True)

    assert result.dry_run is True
    assert result.success is True
    assert result.total_inspected == 1
    assert result.migrated_count == 1  # Simulated 1 migration

    # Verify database was NOT modified (transaction rollback safeguard)
    with test_db_service.session_factory() as session:
        raw_cred = session.get(IntegrationCredential, "cred_dryrun_002")
        assert raw_cred.schema_version == 1
        assert raw_cred.connection_id is None
        assert raw_cred.encrypted_secrets == legacy_cipher

        # Verify NO connection was inserted
        conns = session.scalars(select(IntegrationConnection)).all()
        assert len(conns) == 0


# ==============================================================================
# 3. Idempotent Resumability Tests
# ==============================================================================

def test_idempotent_resumability(test_db_service):
    """Verify running migration repeatedly skips already migrated records safely."""
    vault_key = get_active_vault_key()
    legacy_secrets = {"token": "refr_resume_test"}
    legacy_cipher = _create_legacy_v1_envelope(legacy_secrets, vault_key)

    with test_db_service.session_factory() as session:
        cred = IntegrationCredential(
            id="cred_resume_003",
            business_id="biz_mig_alpha",
            connection_id=None,
            tool_id="check_appointment_availability",
            option_id="google_calendar",
            encrypted_secrets=legacy_cipher,
            key_fingerprint="fp_legacy_v1",
            schema_version=1,
        )
        session.add(cred)
        session.commit()

    # Pass 1: Live migration
    pass1 = migrate_credentials(db_service=test_db_service, dry_run=False)
    assert pass1.migrated_count == 1
    assert pass1.already_migrated_count == 0

    # Pass 2: Re-run immediately
    pass2 = migrate_credentials(db_service=test_db_service, dry_run=False)
    assert pass2.migrated_count == 0
    assert pass2.already_migrated_count == 1
    assert pass2.failed_count == 0
    assert pass2.records[0].status == "SKIPPED_ALREADY_MIGRATED"


# ==============================================================================
# 4. Association with Existing Connections
# ==============================================================================

def test_links_to_existing_default_connection_if_present(test_db_service):
    """Verify orphan credential links to an existing default connection rather than creating duplicate."""
    # Pre-create default connection for Google Calendar
    existing_conn = test_db_service.create_connection(
        business_id="biz_mig_alpha",
        provider_id="google_calendar",
        connection_slug="pre-existing-calendar",
        is_default=True,
    )

    vault_key = get_active_vault_key()
    legacy_cipher = _create_legacy_v1_envelope({"api_key": "sec_pre_existing"}, vault_key)

    with test_db_service.session_factory() as session:
        cred = IntegrationCredential(
            id="cred_pre_existing_004",
            business_id="biz_mig_alpha",
            connection_id=None,
            tool_id="check_appointment_availability",
            option_id="google_calendar",
            encrypted_secrets=legacy_cipher,
            key_fingerprint="fp_v1",
            schema_version=1,
        )
        session.add(cred)
        session.commit()

    result = migrate_credentials(db_service=test_db_service, dry_run=False)
    assert result.migrated_count == 1

    with test_db_service.session_factory() as session:
        migrated_cred = session.get(IntegrationCredential, "cred_pre_existing_004")
        assert migrated_cred.connection_id == existing_conn["id"]

        # Ensure no second connection was created
        all_conns = session.scalars(select(IntegrationConnection)).all()
        assert len(all_conns) == 1


# ==============================================================================
# 5. Zero-Leakage Redacted Audit Reporting Tests
# ==============================================================================

def test_redacted_audit_report_never_leaks_secrets(test_db_service):
    """Verify migration report dictionary and markdown do not expose any secret values."""
    vault_key = get_active_vault_key()
    plaintext_secrets = {
        "api_key": "sk_super_secret_api_key_sensitive_99999",
        "refresh_token": "ya29.super_secret_refresh_token_xyz123",
        "password": "unmaskable_database_password_987",
    }
    legacy_cipher = _create_legacy_v1_envelope(plaintext_secrets, vault_key)

    with test_db_service.session_factory() as session:
        cred = IntegrationCredential(
            id="cred_secret_leak_check",
            business_id="biz_mig_alpha",
            connection_id=None,
            tool_id="check_appointment_availability",
            option_id="google_calendar",
            encrypted_secrets=legacy_cipher,
            key_fingerprint="fp_v1",
            schema_version=1,
        )
        session.add(cred)
        session.commit()

    result = migrate_credentials(db_service=test_db_service, dry_run=False)

    report_dict = result.to_dict()
    report_md = result.to_markdown()

    # Serialize entire report to string to perform leakage check
    dict_str = json.dumps(report_dict)

    for secret_val in plaintext_secrets.values():
        assert secret_val not in dict_str, f"Plaintext secret '{secret_val}' leaked into JSON report!"
        assert secret_val not in report_md, f"Plaintext secret '{secret_val}' leaked into Markdown report!"


# ==============================================================================
# 6. Corrupt Data Handling and Isolation
# ==============================================================================

def test_corrupt_ciphertext_marks_record_failed_and_preserves_others(test_db_service):
    """Verify corrupt ciphertext is marked as FAILED in audit without halting valid migrations."""
    vault_key = get_active_vault_key()
    valid_cipher = _create_legacy_v1_envelope({"valid": True}, vault_key)
    corrupt_cipher = "not_valid_json_at_all_garbage_gibberish"

    with test_db_service.session_factory() as session:
        session.add(IntegrationCredential(
            id="cred_valid_record",
            business_id="biz_mig_alpha",
            connection_id=None,
            tool_id="check_appointment_availability",
            option_id="google_calendar",
            encrypted_secrets=valid_cipher,
            key_fingerprint="fp_v1",
            schema_version=1,
        ))
        session.add(IntegrationCredential(
            id="cred_corrupt_record",
            business_id="biz_mig_beta",
            connection_id=None,
            tool_id="charge_deposit",
            option_id="stripe",
            encrypted_secrets=corrupt_cipher,
            key_fingerprint="fp_v1",
            schema_version=1,
        ))
        session.commit()

    result = migrate_credentials(db_service=test_db_service, dry_run=False)

    assert result.total_inspected == 2
    assert result.migrated_count == 1
    assert result.failed_count == 1
    assert result.success is False

    statuses = {r.credential_id: r.status for r in result.records}
    assert statuses["cred_valid_record"] == "MIGRATED"
    assert statuses["cred_corrupt_record"] == "FAILED"


# ==============================================================================
# 7. CLI Command-Line Interface Invocation
# ==============================================================================

def test_cli_invocation_dry_run_and_json():
    """Verify CLI tool can be executed with --dry-run and --json flags."""
    cmd = [
        sys.executable,
        "-m",
        "backend.capabilities.migration_tool",
        "--dry-run",
        "--json",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    assert proc.returncode == 0
    parsed = json.loads(proc.stdout)
    assert parsed["summary"]["dry_run"] is True
    assert "migrated_count" in parsed["summary"]
    assert isinstance(parsed["records"], list)
