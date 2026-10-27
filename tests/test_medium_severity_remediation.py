"""
Regression and Adversarial Security Tests for Level 3 (Medium-Severity) Remediation:
1. MEDIUM-1: Explicit Connection Resolution Silently Falls Back to Legacy Account on Error.
2. MEDIUM-2: Non-Deterministic Credential Collapse for Multi-Credential Connections.
3. MEDIUM-3: Inability to Perform Zero-Downtime Key Rotation (Missing Keyring Map).
4. MEDIUM-4: Stripe Connect Authorization Model Divergence.
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema
from backend.database.models import (
    IntegrationConnection,
    IntegrationCredential,
    Business,
)
from backend.database.service import DatabaseService, session_scope
from backend.database.repositories.connection_repo import ConnectionRepository
from backend.capabilities.vault import (
    encrypt_vault_payload,
    decrypt_vault_payload,
    get_active_vault_key,
    get_vault_keyring,
    compute_key_fingerprint,
    generate_vault_key,
    validate_and_decode_key,
    CredentialDecryptionError,
)
from backend.capabilities.credentials import (
    encrypt_credentials,
    decrypt_credentials,
)
from backend.integrations.resolver import (
    resolve_tool_adapter,
    UnconfiguredAdapter,
)
from backend.integrations.adapters.stripe_payments_adapter import StripePaymentsAdapter
from backend.integrations.models import (
    CapabilityType,
    ExecutionContext,
    ExecutionOutcome,
)
from backend.config import get_settings


@pytest.fixture
def test_db_service():
    """Create isolated SQLite in-memory database with test business profiles."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(engine)
    service = DatabaseService(engine=engine)
    service.create_business({
        "id": "biz_med_alpha",
        "name": "Alpha Health Clinic",
        "industry": "Clinic",
        "phone_number": "+15551113333",
        "opening_time": "08:00",
        "closing_time": "18:00",
        "timezone": "UTC",
    })
    service.create_business({
        "id": "biz_med_beta",
        "name": "Beta Medical Group",
        "industry": "Clinic",
        "phone_number": "+15552224444",
        "opening_time": "08:00",
        "closing_time": "18:00",
        "timezone": "UTC",
    })
    return service


# ==============================================================================
# MEDIUM-1: Explicit Connection Resolution Silently Falls Back to Legacy Account
# ==============================================================================

def test_explicit_connection_resolution_does_not_fall_back_to_legacy_on_missing_credentials(test_db_service):
    """
    MEDIUM-1 Scenario:
    Tenant has a legacy tool credential configured for 'booking' (e.g. Dr. Jones's calendar).
    A call explicitly requests connection_id='conn_dr_smith', but conn_dr_smith has NO credentials stored.
    Invariant: Must return UnconfiguredAdapter immediately.
    Must NEVER fall back to Dr. Jones's legacy tool credential.
    """
    biz_id = "biz_med_alpha"

    # 1. Setup legacy tool credential for Dr. Jones
    legacy_secrets = {"doctor": "dr_jones", "calendar_id": "cal_jones_123"}
    enc_legacy, fp_legacy = encrypt_credentials(legacy_secrets)
    test_db_service.save_credential_raw(
        business_id=biz_id,
        tool_id="booking",
        encrypted_secrets=enc_legacy,
        key_fingerprint=fp_legacy,
    )
    test_db_service.save_tool_config(
        business_id=biz_id,
        tool_id="booking",
        selected_option_id="google_calendar",
        configuration={"default_calendar": "primary"},
    )

    # 2. Setup explicit connection for Dr. Smith, but WITHOUT credentials
    conn_smith = test_db_service.create_connection(
        business_id=biz_id,
        provider_id="google_calendar",
        connection_slug="dr-smith-calendar",
        display_label="Dr. Smith Calendar",
        metadata={"doctor": "dr_smith"},
    )
    conn_id = conn_smith["id"]

    # 3. Resolve with explicit connection_id="conn_smith"
    adapter = resolve_tool_adapter(
        business_id=biz_id,
        tool_id="booking",
        db_service=test_db_service,
        connection_id=conn_id,
    )

    # Invariant: Must be UnconfiguredAdapter; must NOT contain Dr. Jones's credentials!
    assert isinstance(adapter, UnconfiguredAdapter), (
        f"Expected UnconfiguredAdapter when explicit connection has no credentials, got {type(adapter)}"
    )
    assert adapter.credentials == {} or adapter.credentials is None


def test_explicit_connection_resolution_does_not_fall_back_to_legacy_on_decryption_failure(test_db_service):
    """
    MEDIUM-1 Scenario:
    Tenant has legacy tool credentials. Explicit connection_id is requested, but its
    credentials cannot be decrypted (e.g. corrupted ciphertext or invalid key).
    Invariant: Must fail closed to UnconfiguredAdapter and NOT fall back to legacy credentials.
    """
    biz_id = "biz_med_alpha"

    # 1. Setup legacy tool credential
    legacy_secrets = {"doctor": "dr_jones", "api_key": "legacy_key_123"}
    enc_legacy, fp_legacy = encrypt_credentials(legacy_secrets)
    test_db_service.save_credential_raw(
        business_id=biz_id,
        tool_id="booking",
        encrypted_secrets=enc_legacy,
        key_fingerprint=fp_legacy,
    )

    # 2. Setup connection with corrupted credentials
    conn = test_db_service.create_connection(
        business_id=biz_id,
        provider_id="google_calendar",
        connection_slug="corrupted-conn",
        display_label="Corrupted Connection",
    )
    corrupted_envelope = json.dumps({
        "v": 2,
        "alg": "AES-256-GCM",
        "iv": base64.b64encode(os.urandom(12)).decode("ascii"),
        "c": base64.b64encode(b"corrupted_ciphertext_data").decode("ascii"),
        "t": base64.b64encode(os.urandom(16)).decode("ascii"),
        "fp": "fp_corrupted",
    })
    test_db_service.save_connection_credential(
        business_id=biz_id,
        connection_id=conn["id"],
        encrypted_secrets=corrupted_envelope,
        key_fingerprint="fp_corrupted",
    )

    # 3. Resolve explicit connection
    adapter = resolve_tool_adapter(
        business_id=biz_id,
        tool_id="booking",
        db_service=test_db_service,
        connection_id=conn["id"],
    )

    # Must fail closed to UnconfiguredAdapter
    assert isinstance(adapter, UnconfiguredAdapter)
    assert adapter.credentials == {} or adapter.credentials is None


def test_explicit_connection_resolution_succeeds_when_credentials_valid(test_db_service):
    """
    Explicit connection resolution succeeds and binds connection credentials when valid.
    """
    biz_id = "biz_med_alpha"

    conn = test_db_service.create_connection(
        business_id=biz_id,
        provider_id="google_calendar",
        connection_slug="dr-smith-valid",
        display_label="Dr. Smith Valid",
    )
    secrets = {"doctor": "dr_smith", "token": "oauth_token_smith_123"}
    enc_sec, fp_sec = encrypt_credentials(secrets)
    test_db_service.save_connection_credential(
        business_id=biz_id,
        connection_id=conn["id"],
        encrypted_secrets=enc_sec,
        key_fingerprint=fp_sec,
    )

    adapter = resolve_tool_adapter(
        business_id=biz_id,
        tool_id="booking",
        db_service=test_db_service,
        connection_id=conn["id"],
    )

    assert not isinstance(adapter, UnconfiguredAdapter)
    assert adapter.credentials.get("doctor") == "dr_smith"
    assert adapter.credentials.get("token") == "oauth_token_smith_123"


def test_omitted_connection_id_falls_back_to_legacy_for_backward_compatibility(test_db_service):
    """
    When connection_id is omitted (None) and no default connection is configured,
    the resolver preserves backward compatibility by loading legacy tool credentials.
    """
    biz_id = "biz_med_alpha"

    legacy_secrets = {"doctor": "dr_legacy", "token": "legacy_token_123"}
    enc_legacy, fp_legacy = encrypt_credentials(legacy_secrets)
    test_db_service.save_credential_raw(
        business_id=biz_id,
        tool_id="booking",
        encrypted_secrets=enc_legacy,
        key_fingerprint=fp_legacy,
    )
    test_db_service.save_tool_config(
        business_id=biz_id,
        tool_id="booking",
        selected_option_id="google_calendar",
    )

    adapter = resolve_tool_adapter(
        business_id=biz_id,
        tool_id="booking",
        db_service=test_db_service,
        connection_id=None,
    )

    assert not isinstance(adapter, UnconfiguredAdapter)
    assert adapter.credentials.get("doctor") == "dr_legacy"


def test_disconnected_connection_returns_unconfigured_adapter(test_db_service):
    """
    If connection status is 'disconnected', resolver immediately returns UnconfiguredAdapter.
    """
    biz_id = "biz_med_alpha"

    conn = test_db_service.create_connection(
        business_id=biz_id,
        provider_id="google_calendar",
        connection_slug="disconnected-conn",
        display_label="Disconnected Connection",
    )
    test_db_service.update_connection_status(conn["id"], "disconnected", business_id=biz_id)

    adapter = resolve_tool_adapter(
        business_id=biz_id,
        tool_id="booking",
        db_service=test_db_service,
        connection_id=conn["id"],
    )

    assert isinstance(adapter, UnconfiguredAdapter)


# ==============================================================================
# MEDIUM-2: Non-Deterministic Credential Collapse for Multi-Credential Connections
# ==============================================================================

def test_get_credential_by_connection_deterministically_returns_newest_updated_at(test_db_service):
    """
    MEDIUM-2 Scenario:
    Multiple IntegrationCredential records point to the same connection_id.
    Invariant: get_credential_by_connection must deterministically return the record
    ordered by updated_at.desc(), created_at.desc(), id.desc().
    """
    biz_id = "biz_med_alpha"
    conn = test_db_service.create_connection(
        business_id=biz_id,
        provider_id="google_calendar",
        connection_slug="multi-cred-conn",
        display_label="Multi Cred Connection",
    )
    conn_id = conn["id"]

    now = datetime.now(timezone.utc)
    t_old = now - timedelta(hours=2)
    t_mid = now - timedelta(hours=1)
    t_new = now

    enc_old, fp_old = encrypt_credentials({"version": "v1_old"})
    enc_mid, fp_mid = encrypt_credentials({"version": "v2_mid"})
    enc_new, fp_new = encrypt_credentials({"version": "v3_new"})

    with session_scope(test_db_service.session_factory) as session:
        # Insert 3 records with explicit timestamps
        c_old = IntegrationCredential(
            id=f"cred_old_{uuid.uuid4().hex[:8]}",
            business_id=biz_id,
            tool_id="tool_old",
            option_id="default",
            connection_id=conn_id,
            encrypted_secrets=enc_old,
            key_fingerprint=fp_old,
            created_at=t_old,
            updated_at=t_old,
        )
        c_mid = IntegrationCredential(
            id=f"cred_mid_{uuid.uuid4().hex[:8]}",
            business_id=biz_id,
            tool_id="tool_mid",
            option_id="default",
            connection_id=conn_id,
            encrypted_secrets=enc_mid,
            key_fingerprint=fp_mid,
            created_at=t_mid,
            updated_at=t_mid,
        )
        c_new = IntegrationCredential(
            id=f"cred_new_{uuid.uuid4().hex[:8]}",
            business_id=biz_id,
            tool_id="tool_new",
            option_id="default",
            connection_id=conn_id,
            encrypted_secrets=enc_new,
            key_fingerprint=fp_new,
            created_at=t_new,
            updated_at=t_new,
        )
        session.add_all([c_old, c_mid, c_new])
        session.flush()

    with session_scope(test_db_service.session_factory) as session:
        repo = ConnectionRepository(session)
        cred = repo.get_credential_by_connection(conn_id, business_id=biz_id)
        assert cred is not None
        assert "cred_new_" in cred.id
        decrypted = decrypt_credentials(cred.encrypted_secrets)
        assert decrypted.get("version") == "v3_new"

    # Now simulate an update to c_old so its updated_at becomes newer than c_new
    t_latest = now + timedelta(minutes=10)
    with session_scope(test_db_service.session_factory) as session:
        stmt = (
            select(IntegrationCredential)
            .where(IntegrationCredential.connection_id == conn_id)
            .where(IntegrationCredential.id.like("cred_old_%"))
        )
        old_record = session.scalars(stmt).first()
        old_record.updated_at = t_latest
        session.flush()

    with session_scope(test_db_service.session_factory) as session:
        repo = ConnectionRepository(session)
        cred_after = repo.get_credential_by_connection(conn_id, business_id=biz_id)
        assert cred_after is not None
        assert "cred_old_" in cred_after.id
        decrypted_after = decrypt_credentials(cred_after.encrypted_secrets)
        assert decrypted_after.get("version") == "v1_old"


def test_get_credential_by_connection_subsecond_tiebreaker_uses_id_desc(test_db_service):
    """
    When updated_at and created_at are identical, the id.desc() tiebreaker guarantees determinism.
    """
    biz_id = "biz_med_alpha"
    conn = test_db_service.create_connection(
        business_id=biz_id,
        provider_id="google_calendar",
        connection_slug="tiebreaker-conn",
        display_label="Tiebreaker Connection",
    )
    conn_id = conn["id"]

    same_time = datetime.now(timezone.utc)
    enc_a, fp_a = encrypt_credentials({"rec": "A"})
    enc_z, fp_z = encrypt_credentials({"rec": "Z"})

    with session_scope(test_db_service.session_factory) as session:
        c_a = IntegrationCredential(
            id="cred_aaaa_100",
            business_id=biz_id,
            tool_id="tool_a",
            option_id="default",
            connection_id=conn_id,
            encrypted_secrets=enc_a,
            key_fingerprint=fp_a,
            created_at=same_time,
            updated_at=same_time,
        )
        c_z = IntegrationCredential(
            id="cred_zzzz_200",
            business_id=biz_id,
            tool_id="tool_z",
            option_id="default",
            connection_id=conn_id,
            encrypted_secrets=enc_z,
            key_fingerprint=fp_z,
            created_at=same_time,
            updated_at=same_time,
        )
        session.add_all([c_a, c_z])
        session.flush()

    with session_scope(test_db_service.session_factory) as session:
        repo = ConnectionRepository(session)
        cred = repo.get_credential_by_connection(conn_id, business_id=biz_id)
        assert cred is not None
        # Must pick cred_zzzz_200 due to id.desc()
        assert cred.id == "cred_zzzz_200"


def test_get_credential_by_connection_tenant_scoping_isolation(test_db_service):
    """
    Verify get_credential_by_connection enforces tenant scoping when business_id is passed.
    """
    biz_a = "biz_med_alpha"
    biz_b = "biz_med_beta"

    conn = test_db_service.create_connection(
        business_id=biz_a,
        provider_id="google_calendar",
        connection_slug="tenant-iso-conn",
        display_label="Tenant Isolation Connection",
    )
    conn_id = conn["id"]

    enc, fp = encrypt_credentials({"secret": "alpha_only"})
    test_db_service.save_connection_credential(
        business_id=biz_a,
        connection_id=conn_id,
        encrypted_secrets=enc,
        key_fingerprint=fp,
        tool_id="booking",
    )

    with session_scope(test_db_service.session_factory) as session:
        repo = ConnectionRepository(session)
        # Querying with biz_a succeeds
        cred_a = repo.get_credential_by_connection(conn_id, business_id=biz_a)
        assert cred_a is not None

        # Querying with biz_b returns None (isolated)
        cred_b = repo.get_credential_by_connection(conn_id, business_id=biz_b)
        assert cred_b is None


# ==============================================================================
# MEDIUM-3: Inability to Perform Zero-Downtime Key Rotation (Missing Keyring Map)
# ==============================================================================

def test_keyring_supports_zero_downtime_key_rotation():
    """
    MEDIUM-3 Scenario:
    1. Key A is used to encrypt credentials.
    2. Master key is rotated to Key B.
    3. Old Key A is added to keyring map.
    4. Decrypting Key A payload succeeds via keyring fingerprint match.
    5. Decrypting new Key B payload succeeds via active master key.
    """
    key_a = validate_and_decode_key(generate_vault_key())
    fp_a = compute_key_fingerprint(key_a)

    key_b = validate_and_decode_key(generate_vault_key())
    fp_b = compute_key_fingerprint(key_b)

    # 1. Encrypt payload with Key A
    secret_a = {"service": "calendar", "token": "token_under_key_a"}
    enc_payload_a, used_fp_a = encrypt_vault_payload(secret_a, master_key=key_a)
    assert used_fp_a == fp_a

    # 2. Key B is now active master key
    with patch("backend.capabilities.vault.get_active_vault_key", return_value=key_b):
        # Without keyring, decrypting Key A payload fails
        with pytest.raises(CredentialDecryptionError):
            decrypt_vault_payload(enc_payload_a)

        # With keyring containing Key A, decrypting Key A payload succeeds
        keyring = {fp_a: key_a}
        decrypted_a = decrypt_vault_payload(enc_payload_a, keyring=keyring)
        assert decrypted_a == secret_a

        # Key B payload encrypts and decrypts with active key
        secret_b = {"service": "stripe", "token": "token_under_key_b"}
        enc_payload_b, used_fp_b = encrypt_vault_payload(secret_b)
        assert used_fp_b == fp_b
        decrypted_b = decrypt_vault_payload(enc_payload_b, keyring=keyring)
        assert decrypted_b == secret_b


def test_keyring_env_var_json_parsing():
    """
    Verify get_vault_keyring parses CAPABILITY_KEYRING JSON environment variable:
    e.g. '{"fp_123": "<base64_key>", "secondary": "<base64_key>"}'
    """
    key_str_1 = generate_vault_key()
    key_bytes_1 = validate_and_decode_key(key_str_1)
    fp_1 = compute_key_fingerprint(key_bytes_1)

    key_str_2 = generate_vault_key()
    key_bytes_2 = validate_and_decode_key(key_str_2)
    fp_2 = compute_key_fingerprint(key_bytes_2)

    json_keyring = json.dumps({
        fp_1: key_str_1,
        "historical_key_2": key_str_2,
    })

    with patch.dict(os.environ, {"CAPABILITY_KEYRING": json_keyring}):
        keyring = get_vault_keyring(environment="development")
        assert fp_1 in keyring
        assert keyring[fp_1] == key_bytes_1
        assert fp_2 in keyring
        assert keyring[fp_2] == key_bytes_2


def test_keyring_env_var_comma_separated_parsing():
    """
    Verify get_vault_keyring parses comma-separated list of base64 keys.
    """
    key_str_1 = generate_vault_key()
    key_bytes_1 = validate_and_decode_key(key_str_1)
    fp_1 = compute_key_fingerprint(key_bytes_1)

    key_str_2 = generate_vault_key()
    key_bytes_2 = validate_and_decode_key(key_str_2)
    fp_2 = compute_key_fingerprint(key_bytes_2)

    csv_keyring = f"{key_str_1}, {key_str_2}"

    with patch.dict(os.environ, {"CAPABILITY_KEYRING": csv_keyring}):
        keyring = get_vault_keyring(environment="development")
        assert fp_1 in keyring
        assert keyring[fp_1] == key_bytes_1
        assert fp_2 in keyring
        assert keyring[fp_2] == key_bytes_2


def test_decryption_fails_closed_when_key_neither_active_nor_in_keyring():
    """
    Decryption fails closed with CredentialDecryptionError if the required key
    is neither active nor present in the keyring.
    """
    orphan_key = validate_and_decode_key(generate_vault_key())
    enc_payload, _ = encrypt_vault_payload({"data": "orphaned"}, master_key=orphan_key)

    active_key = validate_and_decode_key(generate_vault_key())
    other_key = validate_and_decode_key(generate_vault_key())
    other_fp = compute_key_fingerprint(other_key)

    with patch("backend.capabilities.vault.get_active_vault_key", return_value=active_key):
        with pytest.raises(CredentialDecryptionError):
            decrypt_vault_payload(enc_payload, keyring={other_fp: other_key})


def test_credentials_facade_forwards_keyring():
    """
    Verify backend.capabilities.credentials.decrypt_credentials forwards keyring parameter.
    """
    key_rot = validate_and_decode_key(generate_vault_key())
    fp_rot = compute_key_fingerprint(key_rot)
    enc_payload, _ = encrypt_credentials({"auth": "rotated_secret"}, master_key=key_rot)

    active_key = validate_and_decode_key(generate_vault_key())
    with patch("backend.capabilities.vault.get_active_vault_key", return_value=active_key):
        result = decrypt_credentials(enc_payload, keyring={fp_rot: key_rot})
        assert result.get("auth") == "rotated_secret"


# ==============================================================================
# MEDIUM-4: Stripe Connect Authorization Model Divergence
# ==============================================================================

def test_stripe_connect_manifest_exposes_connected_account_field():
    """
    Verify StripePaymentsAdapter manifest defines stripe_account_id in optional_setup_fields.
    """
    adapter = StripePaymentsAdapter(business_id="biz_med_alpha", tool_id="payment")
    manifest = adapter.get_manifest()

    opt_keys = {f.key: f for f in manifest.optional_setup_fields}
    assert "stripe_account_id" in opt_keys
    account_field = opt_keys["stripe_account_id"]
    assert account_field.placeholder == "acct_..."
    assert not account_field.secret  # Public connected account identifier


def test_stripe_direct_merchant_key_configuration_validation():
    """
    Verify direct merchant secret key (sk_live_... / sk_test_...) validates successfully.
    """
    adapter = StripePaymentsAdapter(
        business_id="biz_med_alpha",
        tool_id="payment",
        credentials={"secret_key": "sk_live_merchant_direct_key_12345"},
    )
    result = adapter.validate_configuration({})
    assert result.passed is True
    assert "sk_live_" in result.details


def test_stripe_connect_configuration_validation_and_platform_key():
    """
    Verify Stripe Connect (acct_...) passes validation when platform key is present in settings.
    """
    adapter = StripePaymentsAdapter(
        business_id="biz_med_alpha",
        tool_id="payment",
        configuration={"stripe_account_id": "acct_1Hxyz9876543210"},
        credentials={},
    )

    # 1. Without platform key, validation fails closed
    with patch.dict(os.environ, {"STRIPE_SECRET_KEY": ""}, clear=False):
        with patch("backend.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(STRIPE_SECRET_KEY=None)
            res_no_key = adapter.validate_configuration({})
            assert res_no_key.passed is False
            assert "platform STRIPE_SECRET_KEY" in res_no_key.details

    # 2. With platform key configured, validation passes
    with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_platform_master_key_999"}):
        res_with_key = adapter.validate_configuration({})
        assert res_with_key.passed is True
        assert "acct_1Hxyz98" in res_with_key.details


def test_stripe_connect_invalid_account_id_format_rejected():
    """
    Verify invalid Stripe Connected Account ID format (not starting with acct_) is rejected.
    """
    adapter = StripePaymentsAdapter(
        business_id="biz_med_alpha",
        tool_id="payment",
        configuration={"stripe_account_id": "invalid_format_account"},
        credentials={},
    )
    res = adapter.validate_configuration({})
    assert res.passed is False
    assert "must start with 'acct_'" in res.details


def test_stripe_connect_test_connection_probes_account():
    """
    Verify test_connection distinguishes between direct key probes and Stripe Connect probes.
    """
    # Direct merchant mode
    adapter_direct = StripePaymentsAdapter(
        business_id="biz_med_alpha",
        tool_id="payment",
        credentials={"secret_key": "sk_test_direct_555"},
    )
    res_direct = adapter_direct.test_connection()
    assert res_direct.passed is True
    assert "test mode" in res_direct.details

    # Stripe Connect mode
    adapter_connect = StripePaymentsAdapter(
        business_id="biz_med_alpha",
        tool_id="payment",
        configuration={"stripe_account_id": "acct_999888777"},
        credentials={"secret_key": "sk_live_platform_111"},
    )
    res_connect = adapter_connect.test_connection()
    assert res_connect.passed is True
    assert "Stripe Connect gateway probe succeeded" in res_connect.details
    assert "acct_999888" in res_connect.details


def test_stripe_connect_payment_execution_attributes_account_id():
    """
    Verify CREATE_PAYMENT_REQUEST execution attributes payment to stripe_account_id.
    """
    adapter = StripePaymentsAdapter(
        business_id="biz_med_alpha",
        tool_id="payment",
        configuration={"stripe_account_id": "acct_connected_merchant_123"},
        credentials={"secret_key": "sk_live_platform_root_key"},
    )

    ctx = ExecutionContext(
        tenant_id="biz_med_alpha",
        session_id="session_stripe_001",
        execution_mode="live",
    )

    result = adapter.execute(
        operation=CapabilityType.CREATE_PAYMENT_REQUEST,
        input_data={
            "amount_cents": 7500,
            "currency": "usd",
            "description": "Dental Cleaning",
        },
        context=ctx,
    )

    assert result.outcome == ExecutionOutcome.OPERATION_PENDING
    assert result.success is True
    assert result.data["stripe_account_id"] == "acct_connected_merchant_123"
    assert result.data["amount_cents"] == 7500
    assert "Dental Cleaning" in result.data["description"]
