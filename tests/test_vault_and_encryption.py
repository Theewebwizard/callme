"""
Tests for Phase 2: AES-256-GCM Cryptographic Vault Engine, Key Validation,
Production Fail-Closed Enforcement, and Lossless Legacy v1 Envelope Reading.
"""

import base64
import json
import hashlib
import hmac
import os
import pytest

from backend.capabilities.vault import (
    generate_vault_key,
    validate_and_decode_key,
    get_active_vault_key,
    compute_key_fingerprint,
    encrypt_vault_payload,
    decrypt_vault_payload,
    redact_secret_value,
    redact_credential_dict,
    CredentialDecryptionError,
    KeyValidationError,
)
from backend.capabilities.credentials import (
    encrypt_credentials,
    decrypt_credentials,
    get_vault_master_key,
)
from backend.config import Settings


# ==============================================================================
# 1. AES-256-GCM Envelope v2 Round-Trip & Nonce Uniqueness
# ==============================================================================

def test_aes_gcm_encryption_roundtrip():
    """Verify AES-256-GCM encrypts and decrypts secret dictionaries losslessly."""
    key = validate_and_decode_key(generate_vault_key())
    secret_payload = {
        "access_token": "ya29.a0AfH6SMD_mock_token_12345",
        "refresh_token": "1//04mock_refresh_token_67890",
        "client_id": "client_apex_clinic",
        "expires_in": 3600,
        "nested": {"key": "value", "count": 42},
    }

    envelope_json, fingerprint = encrypt_vault_payload(secret_payload, master_key=key)
    assert fingerprint.startswith("fp_")

    envelope = json.loads(envelope_json)
    assert envelope["v"] == 2
    assert envelope["alg"] == "AES-256-GCM"
    assert len(base64.b64decode(envelope["iv"])) == 12  # 96-bit nonce
    assert len(base64.b64decode(envelope["t"])) == 16   # 128-bit GCM tag
    assert envelope["fp"] == fingerprint

    # Decrypt
    decrypted = decrypt_vault_payload(envelope_json, master_key=key)
    assert decrypted == secret_payload


def test_nonce_uniqueness_for_identical_payloads():
    """Verify encrypting identical plaintext yields unique nonces and ciphertexts."""
    key = validate_and_decode_key(generate_vault_key())
    payload = {"api_key": "fixed_api_key_123"}

    env_str_1, _ = encrypt_vault_payload(payload, master_key=key)
    env_str_2, _ = encrypt_vault_payload(payload, master_key=key)

    env1 = json.loads(env_str_1)
    env2 = json.loads(env_str_2)

    assert env1["iv"] != env2["iv"]
    assert env1["c"] != env2["c"]


# ==============================================================================
# 2. Tamper Resistance and Authentication Tag Verification
# ==============================================================================

def test_tampered_ciphertext_rejected():
    """Verify altering even 1 bit of ciphertext raises CredentialDecryptionError."""
    key = validate_and_decode_key(generate_vault_key())
    env_str, _ = encrypt_vault_payload({"secret": "sensitive_data"}, master_key=key)
    envelope = json.loads(env_str)

    raw_c = bytearray(base64.b64decode(envelope["c"]))
    raw_c[0] ^= 0x01  # Flip one bit
    envelope["c"] = base64.b64encode(raw_c).decode("ascii")

    with pytest.raises(CredentialDecryptionError, match="authentication check"):
        decrypt_vault_payload(json.dumps(envelope), master_key=key)


def test_tampered_auth_tag_rejected():
    """Verify modifying authentication tag raises CredentialDecryptionError."""
    key = validate_and_decode_key(generate_vault_key())
    env_str, _ = encrypt_vault_payload({"secret": "sensitive_data"}, master_key=key)
    envelope = json.loads(env_str)

    raw_t = bytearray(base64.b64decode(envelope["t"]))
    raw_t[0] ^= 0xFF  # Corrupt tag
    envelope["t"] = base64.b64encode(raw_t).decode("ascii")

    with pytest.raises(CredentialDecryptionError, match="authentication check"):
        decrypt_vault_payload(json.dumps(envelope), master_key=key)


def test_tampered_iv_rejected():
    """Verify modifying IV/nonce raises CredentialDecryptionError."""
    key = validate_and_decode_key(generate_vault_key())
    env_str, _ = encrypt_vault_payload({"secret": "sensitive_data"}, master_key=key)
    envelope = json.loads(env_str)

    raw_iv = bytearray(base64.b64decode(envelope["iv"]))
    raw_iv[0] ^= 0x01
    envelope["iv"] = base64.b64encode(raw_iv).decode("ascii")

    with pytest.raises(CredentialDecryptionError, match="authentication check"):
        decrypt_vault_payload(json.dumps(envelope), master_key=key)


def test_wrong_key_decryption_rejected():
    """Verify decrypting with a different valid master key fails authentication check."""
    key1 = validate_and_decode_key(generate_vault_key())
    key2 = validate_and_decode_key(generate_vault_key())

    env_str, _ = encrypt_vault_payload({"token": "secret_abc"}, master_key=key1)

    with pytest.raises(CredentialDecryptionError, match="authentication check"):
        decrypt_vault_payload(env_str, master_key=key2)


# ==============================================================================
# 3. Key Generation, Validation, and Fail-Closed Production Behavior
# ==============================================================================

def test_generate_and_validate_key():
    """Verify generate_vault_key outputs valid 32-byte Base64 key."""
    key_str = generate_vault_key()
    key_bytes = validate_and_decode_key(key_str)
    assert len(key_bytes) == 32


def test_hex_key_validation():
    """Verify 64-hex character key decodes cleanly to 32 bytes."""
    raw = os.urandom(32)
    hex_key = raw.hex()
    assert len(hex_key) == 64
    decoded = validate_and_decode_key(hex_key)
    assert decoded == raw


def test_short_key_rejected():
    """Verify keys shorter than 32 raw bytes are rejected."""
    short_key = base64.b64encode(os.urandom(16)).decode("ascii")
    with pytest.raises(KeyValidationError, match="Invalid key length"):
        validate_and_decode_key(short_key)


def test_long_key_rejected():
    """Verify keys longer than 32 raw bytes are rejected."""
    long_key = base64.b64encode(os.urandom(40)).decode("ascii")
    with pytest.raises(KeyValidationError, match="Invalid key length"):
        validate_and_decode_key(long_key)


def test_degenerate_uniform_key_rejected():
    """Verify uniform sequence keys (all zeros or identical characters) are rejected."""
    all_zeros_b64 = base64.b64encode(b"\x00" * 32).decode("ascii")
    with pytest.raises(KeyValidationError, match="lack variance"):
        validate_and_decode_key(all_zeros_b64)


def test_production_fail_closed_without_key():
    """Verify missing key in production raises fatal KeyValidationError."""
    with pytest.raises(KeyValidationError, match="FATAL: CAPABILITY_ENCRYPTION_KEY must be configured in production"):
        validate_and_decode_key(raw_key=None, environment="production")

    with pytest.raises(KeyValidationError, match="FATAL: CAPABILITY_ENCRYPTION_KEY must be configured in production"):
        validate_and_decode_key(raw_key="", environment="production")


def test_production_rejects_placeholder_keys():
    """Verify production environment rejects known development/placeholder keys."""
    with pytest.raises(KeyValidationError, match="insecure placeholder"):
        validate_and_decode_key(
            raw_key="callme-default-vault-entropy-key-2026",
            environment="production",
        )


def test_development_fallback_key():
    """Verify development environment uses stable fallback when key is not provided."""
    key = validate_and_decode_key(raw_key=None, environment="development")
    assert len(key) == 32
    # Verify deterministic/stable across invocations
    key2 = validate_and_decode_key(raw_key=None, environment="development")
    assert key == key2


def test_settings_model_validator_production():
    """Verify Settings pydantic model raises error if production has no key."""
    # Production without key fails validation
    with pytest.raises(ValueError, match="CAPABILITY_ENCRYPTION_KEY must be configured"):
        Settings(ENVIRONMENT="production", CAPABILITY_ENCRYPTION_KEY=None)

    # Production with valid 32-byte key succeeds
    valid_key = generate_vault_key()
    cfg = Settings(ENVIRONMENT="production", CAPABILITY_ENCRYPTION_KEY=valid_key)
    assert cfg.CAPABILITY_ENCRYPTION_KEY == valid_key


# ==============================================================================
# 4. Lossless Legacy Envelope v1 Compatibility
# ==============================================================================

def test_legacy_v1_envelope_lossless_decryption():
    """Verify vault decrypts legacy v1 HMAC-keystream envelopes without data loss."""
    # Construct an authentic legacy v1 envelope
    key = os.urandom(32)
    iv = os.urandom(16)
    secrets = {"api_key": "sec_live_legacy_key_998877", "account_sid": "AC_mock_sid_123"}
    raw_bytes = json.dumps(secrets).encode("utf-8")

    keystream = hashlib.sha256(key + iv).digest()
    while len(keystream) < len(raw_bytes):
        keystream += hashlib.sha256(keystream + key).digest()

    cipher_bytes = bytes(b ^ k for b, k in zip(raw_bytes, keystream[:len(raw_bytes)]))
    mac = hmac.new(key, iv + cipher_bytes, hashlib.sha256).digest()

    legacy_envelope = {
        "v": 1,
        "iv": base64.b64encode(iv).decode("ascii"),
        "c": base64.b64encode(cipher_bytes).decode("ascii"),
        "t": base64.b64encode(mac).decode("ascii"),
    }
    legacy_payload_str = json.dumps(legacy_envelope)

    # Decrypt via new decrypt_vault_payload
    decrypted = decrypt_vault_payload(legacy_payload_str, master_key=key)
    assert decrypted == secrets


# ==============================================================================
# 5. Backward-Compatible Credentials Facade
# ==============================================================================

def test_credentials_facade_roundtrip():
    """Verify backend.capabilities.credentials exports continue to work seamlessly."""
    payload = {"service_account_json": '{"type": "service_account"}', "status": "active"}
    encrypted_str, fp = encrypt_credentials(payload)
    assert isinstance(encrypted_str, str)
    assert fp.startswith("fp_")

    decrypted = decrypt_credentials(encrypted_str)
    assert decrypted == payload


def test_secret_redaction_utilities():
    """Verify secret redaction masks sensitive keys and handles edge cases."""
    data = {
        "api_key": "sk_live_1234567890abcdef",
        "access_token": "ya29.mock_oauth_token",
        "customer_email": "user@example.com",
        "nested": {
            "client_secret": "sec_super_secret_xyz",
            "open_count": 5,
        },
    }

    redacted = redact_credential_dict(data)
    assert redacted["api_key"] == "sk_l...cdef"
    assert "..." in redacted["access_token"]
    assert redacted["customer_email"] == "user@example.com"
    assert "..." in redacted["nested"]["client_secret"]
    assert redacted["nested"]["open_count"] == 5

    # Short and private key handling
    assert redact_secret_value(None) == "********"
    assert redact_secret_value("1234") == "********"
    assert redact_secret_value("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...") == "[REDACTED_SECRET]"
