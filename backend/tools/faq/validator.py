"""
Tenant FAQ validation, deduplication, and pre-tokenization.
Guarantees clean, grounded documents without mutating tenant configuration.
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional, Set

from backend.tools.faq.models import FAQDocument
from backend.tools.faq.normalization import (
    normalize_text,
    strip_punctuation_unicode,
    tokenize,
    extract_content_tokens,
)

logger = logging.getLogger(__name__)


def validate_and_deduplicate_faqs(
    raw_faqs: Any,
    tenant_synonyms: Optional[Dict[str, str]] = None,
) -> List[FAQDocument]:
    """
    Validate, sanitize, deduplicate, and pre-tokenize a tenant's configured FAQs.
    
    Guarantees:
    - Skips non-dicts, missing or empty question/answer fields.
    - Trims whitespace and normalizes Unicode.
    - Deduplicates identical questions based on normalized text.
    - Preserves legitimate FAQs that differ meaningfully (e.g. credit vs debit card).
    - Preserves tenant isolation and never mutates caller's input.
    """
    if not raw_faqs or not isinstance(raw_faqs, list):
        return []

    seen_question_keys: Set[str] = set()
    validated_docs: List[FAQDocument] = []

    for idx, item in enumerate(raw_faqs):
        if not isinstance(item, dict):
            logger.debug("Skipping non-dict FAQ entry at index %d", idx)
            continue

        raw_q = item.get("question")
        raw_a = item.get("answer")

        if not isinstance(raw_q, str) or not isinstance(raw_a, str):
            continue

        clean_q = normalize_text(raw_q)
        clean_a = normalize_text(raw_a)

        if not clean_q or not clean_a:
            continue

        # Normalization key for deduplication
        dedup_key = strip_punctuation_unicode(clean_q).lower()
        if not dedup_key:
            continue

        if dedup_key in seen_question_keys:
            logger.debug("Deduplicated identical FAQ question: '%s'", clean_q)
            continue
        seen_question_keys.add(dedup_key)

        # Extract or generate deterministic ID
        item_id = item.get("id")
        if not item_id or not isinstance(item_id, str):
            id_hash = hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()[:12]
            item_id = f"faq_{id_hash}"

        category = item.get("category")
        category_clean = normalize_text(category) if isinstance(category, str) else "General"

        # Optional alternate questions / phrasings
        alternates_raw = item.get("alternate_questions") or item.get("alternate_phrasings") or []
        valid_alternates: List[str] = []
        alternate_tokens_list: List[List[str]] = []

        if isinstance(alternates_raw, list):
            for alt in alternates_raw:
                if isinstance(alt, str):
                    clean_alt = normalize_text(alt)
                    if clean_alt and clean_alt != clean_q:
                        valid_alternates.append(clean_alt)
                        alternate_tokens_list.append(tokenize(clean_alt))

        # Optional FAQ-level synonyms merged with tenant synonyms
        faq_synonyms: Dict[str, str] = {}
        if tenant_synonyms and isinstance(tenant_synonyms, dict):
            faq_synonyms.update(tenant_synonyms)
        item_synonyms = item.get("synonyms")
        if isinstance(item_synonyms, dict):
            for k, v in item_synonyms.items():
                if isinstance(k, str) and isinstance(v, str):
                    faq_synonyms[k.lower().strip()] = v.lower().strip()

        # Pre-compute tokens
        q_tokens = tokenize(clean_q)
        q_content = extract_content_tokens(q_tokens)
        a_tokens = tokenize(clean_a)

        all_tokens_set = set(q_tokens) | set(a_tokens)
        for alt_toks in alternate_tokens_list:
            all_tokens_set.update(alt_toks)

        doc = FAQDocument(
            id=item_id,
            question=clean_q,
            answer=clean_a,
            category=category_clean or "General",
            alternate_questions=valid_alternates,
            synonyms=faq_synonyms,
            clean_question=clean_q.lower(),
            question_tokens=q_tokens,
            content_tokens=q_content,
            alternate_tokens=alternate_tokens_list,
            answer_tokens=a_tokens,
            all_tokens=all_tokens_set,
        )
        validated_docs.append(doc)

    return validated_docs
