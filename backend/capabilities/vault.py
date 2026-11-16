"""
Cryptographic Vault Engine for Integration Credentials (NIST SP 800-38D AES-256-GCM).
Enforces fail-closed key validation, CSPRNG nonce generation, authenticated decryption,
and backward-compatible lossless reading of legacy v1 envelopes.
"""

from typing import Dict, Any, Tuple, Optional, Set, Union, List
import base64
import json
import hashlib
import hmac
import os
import logging
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

# Development fallback key derived deterministically (stable across local dev restarts)
DEV_FALLBACK_KEY_BYTES = hashlib.sha256(b"callme-development-stable-vault-key-2026-seed").digest()


class CredentialVaultError(Exception):
    """Base exception for vault encryption/decryption operations."""
    pass


class CredentialDecryptionError(CredentialVaultError, ValueError):
    """Raised when credential authentication or decryption fails."""
    pass


class KeyValidationError(CredentialVaultError, ValueError):
    """Raised when an encryption key fails structural or entropy requirements."""
    pass


# ---------------------------------------------------------------------------
# 1. Key Generation and Validation
# ---------------------------------------------------------------------------

def generate_vault_key() -> str:
    """Generate cryptographically secure 256-bit (32-byte) key encoded in URL-safe Base64."""
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).decode("ascii")


def validate_and_decode_key(
    raw_key: Optional[str] = None,
    environment: str = "development",
) -> bytes:
    """
    Validate and decode a 32-byte (256-bit) AES-256 master key.
    Supports standard Base64, URL-safe Base64, Hex encoding, or raw 32-byte ASCII.
    Fails closed in production if missing, weak, or of incorrect length.
    """
    is_production = environment.lower() in ("production", "prod")

    if not raw_key or not str(raw_key).strip():
        if is_production:
            raise KeyValidationError("FATAL: CAPABILITY_ENCRYPTION_KEY must be configured in production.")
        logger.warning(
            "CAPABILITY_ENCRYPTION_KEY not set. Using stable development vault key. "
            "Configure CAPABILITY_ENCRYPTION_KEY in .env for persistent custom credentials."
        )
        return DEV_FALLBACK_KEY_BYTES

    key_str = str(raw_key).strip()

    # Reject known placeholders and legacy default keys in production
    if is_production and (
        "callme-default-vault" in key_str
        or "callme-default-vault" in key_str
        or "dev_secret" in key_str
        or "change_in_production" in key_str
    ):
        raise KeyValidationError(
            "FATAL: Production environment detected with insecure placeholder CAPABILITY_ENCRYPTION_KEY."
        )

    decoded: Optional[bytes] = None

    # 1. Try standard / URL-safe Base64
    try:
        # Pad with '=' if missing
        padded = key_str + "=" * (-len(key_str) % 4)
        cand = base64.b64decode(padded, validate=True)
        if len(cand) == 32:
            decoded = cand
    except Exception:
        pass

    # 2. Try URL-safe Base64 if standard failed
    if decoded is None:
        try:
            padded = key_str + "=" * (-len(key_str) % 4)
            cand = base64.urlsafe_b64decode(padded)
            if len(cand) == 32:
                decoded = cand
        except Exception:
            pass

    # 3. Try Hex decoding (64 hex characters = 32 bytes)
    if decoded is None and len(key_str) == 64:
        try:
            cand = bytes.fromhex(key_str)
            if len(cand) == 32:
                decoded = cand
        except Exception:
            pass

    # 4. Fallback: exact 32 ASCII bytes
    if decoded is None and len(key_str.encode("utf-8")) == 32:
        decoded = key_str.encode("utf-8")

    # Strict length check: must be exactly 32 bytes (256 bits)
    if decoded is None or len(decoded) != 32:
        actual_len = len(decoded) if decoded else len(key_str)
        raise KeyValidationError(
            f"Invalid key length: CAPABILITY_ENCRYPTION_KEY must decode to exactly 32 raw bytes (256 bits). "
            f"Got {actual_len} bytes. Generate a valid key using: python -m backend.capabilities.vault"
        )

    # Reject degenerate keys (e.g. all 0s, all 'A's)
    if len(set(decoded)) <= 1:
        raise KeyValidationError("Invalid key: Key bytes lack variance (degenerate uniform sequence detected).")

    return decoded


def get_active_vault_key(override_key: Optional[Union[bytes, str]] = None) -> bytes:
    """Retrieve validated active master key from environment or settings."""
    from backend.config import get_settings
    settings = get_settings()
    env = getattr(settings, "ENVIRONMENT", "development")

    if override_key:
        if isinstance(override_key, str):
            return validate_and_decode_key(override_key, environment=env)
        if len(override_key) != 32:
            raise KeyValidationError(f"Override key must be exactly 32 bytes, got {len(override_key)}.")
        return override_key

    raw = (
        os.getenv("CAPABILITY_ENCRYPTION_KEY")
        or getattr(settings, "CAPABILITY_ENCRYPTION_KEY", None)
        or os.getenv("VAULT_SECRET_KEY")
    )
    return validate_and_decode_key(raw, environment=env)


def compute_key_fingerprint(key: Union[bytes, str]) -> str:
    """Compute non-reversible SHA-256 fingerprint for audit and key version tracking."""
    if isinstance(key, str):
        try:
            key_bytes = validate_and_decode_key(key)
        except Exception:
            key_bytes = key.encode("utf-8")
    else:
        key_bytes = key
    return f"fp_{hashlib.sha256(key_bytes).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# 2. AES-256-GCM Encryption (Envelope Version 2)
# ---------------------------------------------------------------------------

def encrypt_vault_payload(
    secrets_dict: Dict[str, Any],
    master_key: Optional[bytes] = None,
    associated_data: Optional[Union[bytes, str]] = None,
) -> Tuple[str, str]:
    """
    Encrypt dictionary of secret credentials using NIST SP 800-38D AES-256-GCM.
    Uses 96-bit (12-byte) random nonce and 128-bit authentication tag.
    Optionally binds Authenticated Additional Data (AAD) such as tenant/credential ID
    to cryptographically prevent cross-tenant ciphertext transplantation.
    Returns (envelope_json_str, key_fingerprint).
    """
    key = get_active_vault_key(master_key)
    fingerprint = compute_key_fingerprint(key)
    raw_bytes = json.dumps(secrets_dict, sort_keys=True).encode("utf-8")

    # 96-bit (12-byte) CSPRNG nonce
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)

    aad_bytes: Optional[bytes] = None
    if associated_data is not None:
        aad_bytes = (
            associated_data.encode("utf-8")
            if isinstance(associated_data, str)
            else bytes(associated_data)
        )

    # AESGCM.encrypt returns ciphertext + 16-byte authentication tag appended
    encrypted_blob = aesgcm.encrypt(nonce, raw_bytes, aad_bytes)
    cipher_bytes = encrypted_blob[:-16]
    tag_bytes = encrypted_blob[-16:]

    envelope: Dict[str, Any] = {
        "v": 2,
        "alg": "AES-256-GCM",
        "iv": base64.b64encode(nonce).decode("ascii"),
        "c": base64.b64encode(cipher_bytes).decode("ascii"),
        "t": base64.b64encode(tag_bytes).decode("ascii"),
        "fp": fingerprint,
    }
    if aad_bytes is not None:
        envelope["aad"] = True

    return json.dumps(envelope), fingerprint


def get_vault_keyring(
    override_keyring: Optional[Dict[str, bytes]] = None,
    environment: Optional[str] = None,
) -> Dict[str, bytes]:
    """
    Retrieve map of { key_fingerprint: key_bytes } supporting zero-downtime key rotation.
    Combines active vault key and any historical keys configured in CAPABILITY_KEYRING.
    """
    from backend.config import get_settings
    settings = get_settings()
    env = environment or getattr(settings, "ENVIRONMENT", "development")

    keyring: Dict[str, bytes] = {}
    try:
        active_key = get_active_vault_key()
        active_fp = compute_key_fingerprint(active_key)
        keyring[active_fp] = active_key
    except Exception:
        pass

    if override_keyring:
        for k_fp, k_val in override_keyring.items():
            try:
                dec = validate_and_decode_key(k_val, environment=env) if isinstance(k_val, str) else k_val
                if isinstance(dec, bytes) and len(dec) == 32:
                    keyring[k_fp] = dec
            except Exception:
                pass

    raw_keyring = os.getenv("CAPABILITY_KEYRING") or getattr(settings, "CAPABILITY_KEYRING", None)

    if raw_keyring and str(raw_keyring).strip():
        raw_val = str(raw_keyring).strip()
        candidates: List[str] = []
        if raw_val.startswith("{"):
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            decoded = validate_and_decode_key(v, environment=env)
                            fp = k if str(k).startswith("fp_") else compute_key_fingerprint(decoded)
                            keyring[fp] = decoded
                        except Exception:
                            pass
            except Exception:
                pass
        else:
            candidates = [k.strip() for k in raw_val.split(",") if k.strip()]

        for cand in candidates:
            try:
                dec = validate_and_decode_key(cand, environment=env)
                fp = compute_key_fingerprint(dec)
                keyring[fp] = dec
            except Exception:
                pass

    return keyring


# ---------------------------------------------------------------------------
# 3. Authenticated Decryption (Dual-Envelope v2 and Legacy v1)
# ---------------------------------------------------------------------------

def decrypt_vault_payload(
    encrypted_payload_str: str,
    master_key: Optional[bytes] = None,
    associated_data: Optional[Union[bytes, str]] = None,
    keyring: Optional[Dict[str, bytes]] = None,
) -> Dict[str, Any]:
    """
    Decrypt encrypted secrets payload and verify message authenticity.
    Automatically handles Envelope v2 (AES-256-GCM) and legacy Envelope v1.
    Supports zero-downtime key rotation using cryptographic fingerprint lookup against keyring.
    Verifies Authenticated Additional Data (AAD) if present to prevent cross-tenant transplantation.
    Raises CredentialDecryptionError if data is corrupted, tampered with, or key changed.
    """
    try:
        envelope = json.loads(encrypted_payload_str)
    except Exception as exc:
        raise CredentialDecryptionError("Malformed credential envelope: not valid JSON.") from exc

    version = envelope.get("v", 1)
    target_fp = envelope.get("fp")

    # Determine prioritized candidate keys to attempt decryption
    candidate_keys: List[bytes] = []
    if master_key:
        candidate_keys.append(master_key)
    else:
        active_keyring = get_vault_keyring(override_keyring=keyring)
        # 1. Match by fingerprint if registered in keyring
        if target_fp and target_fp in active_keyring:
            candidate_keys.append(active_keyring[target_fp])
        # 2. Add active key if not already first candidate
        try:
            active_key = get_active_vault_key()
            if active_key not in candidate_keys:
                candidate_keys.append(active_key)
        except Exception:
            pass
        # 3. Add remaining keyring keys
        for k_bytes in active_keyring.values():
            if k_bytes not in candidate_keys:
                candidate_keys.append(k_bytes)

    if not candidate_keys:
        candidate_keys.append(get_active_vault_key())

    last_error: Optional[Exception] = None
    for key in candidate_keys:
        try:
            if version == 2:
                return _decrypt_v2_gcm(envelope, key, associated_data=associated_data)
            elif version == 1:
                return _decrypt_v1_legacy(envelope, key)
            else:
                raise CredentialDecryptionError(f"Unsupported credential envelope version: {version}.")
        except CredentialDecryptionError as dec_err:
            last_error = dec_err
            continue

    if last_error:
        raise last_error
    raise CredentialDecryptionError("Decryption failed across all available keyring keys.")


def _decrypt_v2_gcm(
    envelope: Dict[str, Any],
    key: Union[bytes, str],
    associated_data: Optional[Union[bytes, str]] = None,
) -> Dict[str, Any]:
    """Decrypt Envelope v2 using AES-256-GCM with optional AAD verification."""
    if isinstance(key, str):
        key = validate_and_decode_key(key)
    try:
        nonce = base64.b64decode(envelope["iv"])
        cipher_bytes = base64.b64decode(envelope["c"])
        tag_bytes = base64.b64decode(envelope["t"])
    except (KeyError, Exception) as exc:
        raise CredentialDecryptionError("Malformed v2 credential envelope fields.") from exc

    if len(nonce) != 12:
        raise CredentialDecryptionError(f"Invalid GCM nonce length: expected 12 bytes, got {len(nonce)}.")
    if len(tag_bytes) != 16:
        raise CredentialDecryptionError(f"Invalid GCM tag length: expected 16 bytes, got {len(tag_bytes)}.")

    has_aad = envelope.get("aad") is True
    aad_bytes: Optional[bytes] = None

    if has_aad:
        if associated_data is None or (isinstance(associated_data, (str, bytes)) and len(associated_data) == 0):
            raise CredentialDecryptionError(
                "Associated authenticated data (AAD) is required to decrypt this credential payload."
            )
        aad_bytes = (
            associated_data.encode("utf-8")
            if isinstance(associated_data, str)
            else bytes(associated_data)
        )
    else:
        aad_bytes = None

    aesgcm = AESGCM(key)
    full_ciphertext = cipher_bytes + tag_bytes

    try:
        plaintext_bytes = aesgcm.decrypt(nonce, full_ciphertext, aad_bytes)
    except InvalidTag as exc:
        raise CredentialDecryptionError(
            "Credential payload failed GCM authentication check. Data may be corrupted, tampered with, or key/tenant mismatched."
        ) from exc
    except Exception as exc:
        raise CredentialDecryptionError(f"Decryption failed: {exc}") from exc

    try:
        return json.loads(plaintext_bytes.decode("utf-8"))
    except Exception as exc:
        raise CredentialDecryptionError("Decrypted credential payload is not valid JSON.") from exc



def _decrypt_v1_legacy(envelope: Dict[str, Any], key: Union[bytes, str]) -> Dict[str, Any]:
    """Decrypt legacy Envelope v1 (HMAC-SHA256 keystream stream cipher)."""
    if isinstance(key, str):
        key = validate_and_decode_key(key)
    try:
        iv = base64.b64decode(envelope["iv"])
        cipher_bytes = base64.b64decode(envelope["c"])
        expected_mac = base64.b64decode(envelope["t"])
    except (KeyError, Exception) as exc:
        raise CredentialDecryptionError("Malformed v1 credential envelope fields.") from exc

    # In legacy v1, key was either derived via sha256 or raw master key
    # Try with raw 32-byte key first, then with sha256(raw_key) if needed
    candidates = [key, hashlib.sha256(key).digest()]

    matched_key: Optional[bytes] = None
    for cand in candidates:
        actual_mac = hmac.new(cand, iv + cipher_bytes, hashlib.sha256).digest()
        if hmac.compare_digest(actual_mac, expected_mac):
            matched_key = cand
            break

    if not matched_key:
        raise CredentialDecryptionError(
            "Legacy credential payload failed MAC authentication check. Data may be corrupted or key changed."
        )

    keystream = hashlib.sha256(matched_key + iv).digest()
    while len(keystream) < len(cipher_bytes):
        keystream += hashlib.sha256(keystream + matched_key).digest()

    plain_bytes = bytes(c ^ k for c, k in zip(cipher_bytes, keystream[:len(cipher_bytes)]))

    try:
        return json.loads(plain_bytes.decode("utf-8"))
    except Exception as exc:
        raise CredentialDecryptionError("Decrypted legacy payload is not valid JSON.") from exc


# ---------------------------------------------------------------------------
# 4. Secret Redaction Utilities (Zero-Leakage Standard)
# ---------------------------------------------------------------------------

def redact_secret_value(val: Optional[str]) -> str:
    """Mask secret value for safe display in logs or UI (e.g. 'sk_l...4a2b')."""
    if not val:
        return "********"
    s = str(val).strip()
    if "PRIVATE KEY" in s or s.startswith("-----") or len(s) > 200:
        return "[REDACTED_SECRET]"
    if len(s) <= 8:
        return "********"
    return f"{s[:4]}...{s[-4:]}"


def redact_credential_dict(
    data: Dict[str, Any],
    secret_field_names: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Return deep copy of dictionary with all sensitive fields masked."""
    if not secret_field_names:
        secret_field_names = {
            "api_key", "secret", "password", "token", "service_account_json",
            "private_key", "client_secret", "access_token", "auth_token", "refresh_token", "pin"
        }
    redacted = {}
    for k, v in data.items():
        if k in secret_field_names or any(secret_term in k.lower() for secret_term in ("secret", "token", "key", "password", "pin")):
            redacted[k] = redact_secret_value(v)
        elif isinstance(v, dict):
            redacted[k] = redact_credential_dict(v, secret_field_names)
        else:
            redacted[k] = v
    return redacted


if __name__ == "__main__":
    print(generate_vault_key())
