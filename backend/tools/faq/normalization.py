"""
Multilingual text normalization and Unicode-safe tokenization.
Supports English, Devanagari Hindi, and Romanized Hindi (Hinglish) without
corrupting combining marks, vowel matras, or removing critical domain keywords.
"""

import unicodedata
import re
from typing import List, Set, Optional, Dict


# Minimal, language-aware grammatical particles (strictly function words only).
# Crucial domain terms (accept, booking, cancellation, refunds, payments,
# parking, appointments, hours, timings, price) are NEVER included here.

ENGLISH_MINIMAL_STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "this", "that",
    "it", "its", "as", "from", "do", "does", "did", "can", "could", "would",
    "should", "will", "what", "where", "when", "why", "how", "who", "which",
    "please", "tell", "any", "all", "your", "our", "my", "i", "me", "we", "us", "you",
}

HINDI_DEVANAGARI_STOPWORDS: Set[str] = {
    "का", "की", "के", "को", "से", "में", "पर", "है", "हैं", "था", "थी", "थे",
    "और", "भी", "तो", "या", "ने", "हो", "हुए", "क्या", "क्यों", "कैसे", "कब",
    "कहाँ", "किधर", "कितना", "कितने", "कौन", "किसे", "सकते", "सकती", "सकता",
    "दीजिए", "बताइए", "कृपया",
}

ROMANIZED_HINDI_STOPWORDS: Set[str] = {
    "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "hai", "hain",
    "tha", "thi", "the", "aur", "bhi", "toh", "ya", "ho", "huye",
    "kya", "kyun", "kaise", "kab", "kahan", "kitna", "kitne", "kaun",
    "kisko", "sakte", "sakti", "sakta", "hoga", "hogi", "honge",
    "batao", "bataiye", "kripya", "karo", "kijiye",
}

# Combined minimal particle set for fast candidate filtering
ALL_MINIMAL_STOPWORDS: Set[str] = (
    ENGLISH_MINIMAL_STOPWORDS
    | HINDI_DEVANAGARI_STOPWORDS
    | ROMANIZED_HINDI_STOPWORDS
)

# Standard baseline transliterated equivalences for common Indian hospitality and services queries
DEFAULT_HINGLISH_SYNONYMS: Dict[str, str] = {
    "gaadi": "parking",
    "gadi": "parking",
    "samay": "hours",
    "waqt": "hours",
    "timing": "hours",
    "timings": "hours",
    "time": "hours",
    "open": "hours",
    "opening": "hours",
    "close": "hours",
    "closing": "hours",
    "suvidha": "amenity",
    "paisa": "payment",
    "paise": "payment",
    "rupaye": "payment",
    "kharcha": "price",
    "shuru": "opening",
    "khulna": "opening",
    "band": "closing",
    "ilaj": "treatment",
    "dava": "medicine",
    "cards": "card",
    "payments": "payment",
    "pay": "payment",
}


def normalize_text(text: Optional[str]) -> str:
    """
    Apply Unicode NFKC normalization, strip surrounding whitespace,
    and collapse internal whitespace.
    """
    if not text or not isinstance(text, str):
        return ""
    nfkc = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", nfkc).strip()


def detect_script(text: str) -> str:
    """
    Detect character script present in text.
    Returns 'devanagari', 'latin', 'mixed', or 'other'.
    Note: Latin script does not imply English (could be Romanized Hindi / Hinglish).
    """
    has_devanagari = any("\u0900" <= c <= "\u097f" for c in text)
    has_latin = any("a" <= c.lower() <= "z" for c in text)
    if has_devanagari and has_latin:
        return "mixed"
    if has_devanagari:
        return "devanagari"
    if has_latin:
        return "latin"
    return "other"


def strip_punctuation_unicode(text: str) -> str:
    """
    Replace Unicode punctuation and symbols with spaces while strictly
    preserving Letters (L*), Combining Marks/Matras (M*), and Numbers (N*).
    Prevents corruption of Devanagari vowel signs (matras, viramas, nuktas).
    """
    chars = []
    for c in unicodedata.normalize("NFKC", text):
        cat = unicodedata.category(c)
        # Keep letters, combining marks (vowel signs), numbers, and space
        if cat[0] in ("L", "M", "N") or c in (" ", "_"):
            chars.append(c)
        else:
            chars.append(" ")
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def tokenize(
    text: Optional[str],
    remove_stopwords: bool = False,
    language: Optional[str] = None,
) -> List[str]:
    """
    Unicode-safe tokenization.
    Case-folds Latin characters while preserving Devanagari scripts and vowel marks intact.
    Filters out empty tokens.
    """
    if not text or not isinstance(text, str):
        return []

    tokens: List[str] = []
    current: List[str] = []

    for c in unicodedata.normalize("NFKC", text):
        cat = unicodedata.category(c)
        if cat[0] in ("L", "M", "N"):
            # Lowercase Latin characters; Devanagari characters are unaffected by lower()
            current.append(c.lower())
        else:
            if current:
                token = "".join(current)
                tokens.append(token)
                current = []

    if current:
        tokens.append("".join(current))

    if remove_stopwords:
        return extract_content_tokens(tokens, language=language)

    return tokens


def extract_content_tokens(
    tokens: List[str],
    language: Optional[str] = None,
) -> List[str]:
    """
    Extract substantive content tokens by stripping minimal grammatical particles.
    Guarantees domain words (accept, booking, cancellation, parking, etc.) are kept.
    If all tokens are particles, falls back to the original tokens to avoid empty token sets.
    """
    stop_set = ALL_MINIMAL_STOPWORDS
    if language == "en":
        stop_set = ENGLISH_MINIMAL_STOPWORDS
    elif language == "hi_devanagari":
        stop_set = HINDI_DEVANAGARI_STOPWORDS
    elif language == "hi_romanized":
        stop_set = ROMANIZED_HINDI_STOPWORDS

    content = [t for t in tokens if t not in stop_set and len(t) > 0]
    # If the user query consisted entirely of particles, keep original tokens as fallback
    return content if content else list(tokens)


def expand_tokens_with_synonyms(
    tokens: List[str],
    tenant_synonyms: Optional[Dict[str, str]] = None,
    use_default_hinglish: bool = True,
) -> List[str]:
    """
    Enrich token list with configured tenant synonyms and optional Hinglish equivalences.
    Preserves original tokens and appends canonical synonyms.
    """
    expanded = list(tokens)
    added = set(tokens)

    # 1. Apply tenant-configured synonyms (highest priority)
    if tenant_synonyms and isinstance(tenant_synonyms, dict):
        for t in tokens:
            syn = tenant_synonyms.get(t)
            if syn and syn not in added:
                expanded.append(syn)
                added.add(syn)

    # 2. Apply baseline Hinglish / transliterated equivalents if enabled
    if use_default_hinglish:
        for t in tokens:
            syn = DEFAULT_HINGLISH_SYNONYMS.get(t)
            if syn and syn not in added:
                expanded.append(syn)
                added.add(syn)

    return expanded
