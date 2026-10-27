"""
Multilingual FAQ retrieval, normalization, validation, and decision engine package.
"""

from backend.tools.faq.models import (
    MatchOutcome,
    FAQDocument,
    ScoredCandidate,
    DecisionResult,
)
from backend.tools.faq.normalization import (
    normalize_text,
    strip_punctuation_unicode,
    tokenize,
    detect_script,
    extract_content_tokens,
    expand_tokens_with_synonyms,
    ENGLISH_MINIMAL_STOPWORDS,
    HINDI_DEVANAGARI_STOPWORDS,
    ROMANIZED_HINDI_STOPWORDS,
    ALL_MINIMAL_STOPWORDS,
    DEFAULT_HINGLISH_SYNONYMS,
)
from backend.tools.faq.validator import validate_and_deduplicate_faqs
from backend.tools.faq.retriever import (
    BaseFAQRetriever,
    BM25FAQRetriever,
)
from backend.tools.faq.decision import (
    FAQDecisionEngine,
    DEFAULT_MIN_CONFIDENCE_THRESHOLD,
    DEFAULT_AMBIGUITY_MARGIN,
    DEFAULT_EXACT_MATCH_THRESHOLD,
)

__all__ = [
    "MatchOutcome",
    "FAQDocument",
    "ScoredCandidate",
    "DecisionResult",
    "normalize_text",
    "strip_punctuation_unicode",
    "tokenize",
    "detect_script",
    "extract_content_tokens",
    "expand_tokens_with_synonyms",
    "ENGLISH_MINIMAL_STOPWORDS",
    "HINDI_DEVANAGARI_STOPWORDS",
    "ROMANIZED_HINDI_STOPWORDS",
    "ALL_MINIMAL_STOPWORDS",
    "DEFAULT_HINGLISH_SYNONYMS",
    "validate_and_deduplicate_faqs",
    "BaseFAQRetriever",
    "BM25FAQRetriever",
    "FAQDecisionEngine",
    "DEFAULT_MIN_CONFIDENCE_THRESHOLD",
    "DEFAULT_AMBIGUITY_MARGIN",
    "DEFAULT_EXACT_MATCH_THRESHOLD",
]
