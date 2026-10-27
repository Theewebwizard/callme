"""
Secure Credential Vault facade and secret redaction utilities.
Guarantees secrets are stored encrypted with AES-256-GCM, never logged, and redacted in all API responses.
Provides backward-compatible decryption for legacy v1 envelopes.
"""

from typing import Dict, Any, Tuple, Set, Optional, Union

from backend.capabilities.vault import (
    encrypt_vault_payload,
    decrypt_vault_payload,
    get_active_vault_key,
    get_vault_keyring,
    compute_key_fingerprint as vault_key_fingerprint,
    redact_secret_value,
    redact_credential_dict,
    generate_vault_key,
    validate_and_decode_key,
    CredentialVaultError,
    CredentialDecryptionError,
    KeyValidationError,
)


def get_vault_master_key() -> bytes:
    """Retrieve validated master encryption key from environment settings."""
    return get_active_vault_key()


def compute_key_fingerprint(secret_data: Dict[str, Any]) -> str:
    """Compute audit fingerprint for stored credentials."""
    key = get_active_vault_key()
    return vault_key_fingerprint(key)


def encrypt_credentials(
    secrets_dict: Dict[str, Any],
    master_key: Optional[bytes] = None,
    associated_data: Optional[Union[bytes, str]] = None,
) -> Tuple[str, str]:
    """
    Encrypt dictionary of secret credentials using NIST SP 800-38D AES-256-GCM.
    Returns (encrypted_payload_str, key_fingerprint).
    """
    return encrypt_vault_payload(secrets_dict, master_key=master_key, associated_data=associated_data)


def decrypt_credentials(
    encrypted_payload_str: str,
    master_key: Optional[bytes] = None,
    associated_data: Optional[Union[bytes, str]] = None,
    keyring: Optional[Dict[str, bytes]] = None,
) -> Dict[str, Any]:
    """
    Decrypt encrypted secrets payload and verify message authenticity.
    Supports both Envelope v2 (AES-256-GCM) and legacy Envelope v1.
    Supports zero-downtime key rotation using cryptographic fingerprint lookup against keyring.
    Raises ValueError / CredentialDecryptionError if payload is tampered with or corrupted.
    """
    return decrypt_vault_payload(
        encrypted_payload_str,
        master_key=master_key,
        associated_data=associated_data,
        keyring=keyring,
    )


redact_sensitive_config = redact_credential_dict

__all__ = [
    "get_vault_master_key",
    "compute_key_fingerprint",
    "encrypt_credentials",
    "decrypt_credentials",
    "redact_secret_value",
    "redact_credential_dict",
    "redact_sensitive_config",
    "generate_vault_key",
    "validate_and_decode_key",
    "CredentialVaultError",
    "CredentialDecryptionError",
    "KeyValidationError",
]
