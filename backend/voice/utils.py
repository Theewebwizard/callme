"""
Voice and telephony utility functions.
Handles privacy-conscious phone number masking and canonical E.164 normalization.
"""

from typing import Optional
import re


def normalize_phone_number(raw_phone: Optional[str]) -> str:
    """
    Normalize phone number to international E.164 format or canonical digits.
    Strips whitespace, hyphens, dots, and parentheses.
    Handles Indian phone numbers (10 digits, 0 trunk prefix, or +91 country code).

    Examples:
        '+91 80 4567 8901' -> '+918045678901'
        '+918045678901'    -> '+918045678901'
        '08045678901'      -> '+918045678901'
        '80 4567 8901'     -> '+918045678901'
        '+1 (415) 555-2671' -> '+14155552671'
    """
    if not raw_phone or not isinstance(raw_phone, str):
        return ""

    cleaned = raw_phone.strip()
    digits_only = re.sub(r"\D", "", cleaned)
    if not digits_only:
        return ""

    # Canonicalize standard 10-digit Indian numbers, with or without +91 / 0
    if digits_only.startswith("91") and len(digits_only) == 12:
        return f"+{digits_only}"
    elif digits_only.startswith("0") and len(digits_only) == 11:
        return f"+91{digits_only[1:]}"
    elif len(digits_only) == 10:
        return f"+91{digits_only}"
    elif cleaned.startswith("+"):
        return f"+{digits_only}"

    return digits_only


def mask_phone_number(phone: Optional[str]) -> str:
    """
    Mask a telephone number for secure, privacy-compliant logging and UI representation.
    Never prints full customer caller IDs or inbound numbers.

    Examples:
        '+918045678901'     -> '+9180***8901'
        '+91 80 4123 5678'  -> '+9180***5678'
        '+14155552671'      -> '+1415***2671'
        None                -> '[ANONYMOUS]'
    """
    if not phone or not isinstance(phone, str):
        return "[ANONYMOUS]"

    p = normalize_phone_number(phone) or phone.strip()
    if len(p) <= 4:
        return "****"
    if len(p) <= 7:
        return f"{p[:2]}***{p[-2:]}"
    return f"{p[:5]}***{p[-4:]}"
