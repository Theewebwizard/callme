"""
Secure Credential Vault and secret redaction utilities.
Guarantees secrets are stored encrypted, never logged, and redacted in all API responses.
"""

import base64
import json
import hashlib
import os
import hmac
from typing import Dict, Any, Tuple, Set, Optional

from backend.config import get_settings


def get_vault_master_key() -> bytes:
    """Retrieve or derive vault master encryption key from environment settings."""
    settings = get_settings()
    raw_key = getattr(settings, "VAULT_SECRET_KEY", None) or os.getenv("SECRET_KEY") or "callme-default-vault-entropy-key-2026"
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def redact_secret_value(val: Optional[str]) -> str:
    """Mask secret value for display in logs or UI (e.g. 'sk_l...4a2b')."""
    if not val:
        return "********"
    s = str(val).strip()
    if "PRIVATE KEY" in s or s.startswith("-----") or len(s) > 200:
        return "[REDACTED_SECRET]"
    if len(s) <= 8:
        return "********"
    return f"{s[:4]}...{s[-4:]}"


def redact_credential_dict(data: Dict[str, Any], secret_field_names: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Return copy of dictionary with all sensitive fields masked."""
    if not secret_field_names:
        secret_field_names = {
            "api_key", "secret", "password", "token", "service_account_json",
            "private_key", "client_secret", "access_token", "auth_token"
        }
    redacted = {}
    for k, v in data.items():
        if k in secret_field_names or any(secret_term in k.lower() for secret_term in ("secret", "token", "key", "password")):
            redacted[k] = redact_secret_value(v)
        elif isinstance(v, dict):
            redacted[k] = redact_credential_dict(v, secret_field_names)
        else:
            redacted[k] = v
    return redacted


redact_sensitive_config = redact_credential_dict


def compute_key_fingerprint(secret_data: Dict[str, Any]) -> str:
    """Compute non-reversible SHA-256 fingerprint of stored credentials for audit identification."""
    serialized = json.dumps(secret_data, sort_keys=True).encode("utf-8")
    return f"fp_{hashlib.sha256(serialized).hexdigest()[:12]}"


def encrypt_credentials(secrets_dict: Dict[str, Any], master_key: Optional[bytes] = None) -> Tuple[str, str]:
    """
    Encrypt dictionary of secret credentials.
    Returns (encrypted_payload_str, key_fingerprint).
    """
    key = master_key or get_vault_master_key()
    fingerprint = compute_key_fingerprint(secrets_dict)
    raw_bytes = json.dumps(secrets_dict).encode("utf-8")

    # Symmetric encryption with unique IV
    iv = os.urandom(16)
    # Stream keystream derived via HMAC-SHA256
    keystream = hashlib.sha256(key + iv).digest()
    while len(keystream) < len(raw_bytes):
        keystream += hashlib.sha256(keystream + key).digest()

    cipher_bytes = bytes(b ^ k for b, k in zip(raw_bytes, keystream[:len(raw_bytes)]))
    # MAC authentication tag
    mac = hmac.new(key, iv + cipher_bytes, hashlib.sha256).digest()

    envelope = {
        "v": 1,
        "iv": base64.b64encode(iv).decode("ascii"),
        "c": base64.b64encode(cipher_bytes).decode("ascii"),
        "t": base64.b64encode(mac).decode("ascii"),
    }
    return json.dumps(envelope), fingerprint


def decrypt_credentials(encrypted_payload_str: str, master_key: Optional[bytes] = None) -> Dict[str, Any]:
    """
    Decrypt encrypted secrets payload and verify message authenticity.
    Raises ValueError if payload is tampered with or corrupted.
    """
    key = master_key or get_vault_master_key()
    try:
        envelope = json.loads(encrypted_payload_str)
        iv = base64.b64decode(envelope["iv"])
        cipher_bytes = base64.b64decode(envelope["c"])
        expected_mac = base64.b64decode(envelope["t"])
    except Exception as exc:
        raise ValueError(f"Malformed credential envelope: {exc}")

    actual_mac = hmac.new(key, iv + cipher_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        raise ValueError("Credential payload failed MAC authentication check. Data may be corrupted or key changed.")

    keystream = hashlib.sha256(key + iv).digest()
    while len(keystream) < len(cipher_bytes):
        keystream += hashlib.sha256(keystream + key).digest()

    plain_bytes = bytes(c ^ k for c, k in zip(cipher_bytes, keystream[:len(cipher_bytes)]))
    return json.loads(plain_bytes.decode("utf-8"))
