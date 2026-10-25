"""
Authentication utilities for password hashing and verification using bcrypt.
"""

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plain text password using bcrypt with salt."""
    if not plain_password:
        return ""
    # bcrypt max length is 72 bytes
    pwd_bytes = plain_password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a stored bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False
