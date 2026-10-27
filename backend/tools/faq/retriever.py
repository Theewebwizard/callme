"""
Candidate retrieval interface and BM25F multi-field ranking engine.
Balances question text, alternate phrasings, and answer text without allowing
generic words from long answers to dominate retrieval.
"""

from abc import ABC, abstractmethod
from collections import Counter
import math
from typing import List, Dict, Any, Optional, Set

from backend.tools.faq.models import FAQDocument, ScoredCandidate
from backend.tools.faq.normalization import (
    normalize_text,
    strip_punctuation_unicode,
    tokenize,
    extract_content_tokens,
    expand_tokens_with_synonyms,
    DEFAULT_HINGLISH_SYNONYMS,
)


class BaseFAQRetriever(ABC):
    """Abstract interface for FAQ candidate retrieval."""

    @abstractmethod
    def index(self, documents: List[FAQDocument]) -> None:
        """Index tenant documents into the retriever."""
        pass

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[ScoredCandidate]:
        """Retrieve and rank candidates for a given customer query."""
        pass


class BM25FAQRetriever(BaseFAQRetriever):
    """
    Multi-field BM25F retriever specifically tuned for FAQ retrieval.
    
    Signals & Weights:
    - Question text (weight 2.5): Primary retrieval signal.
    - Alternate questions (weight 2.0): Tenant-configured phrasings.
    - Answer text (weight 0.4): Weighted low to prevent generic filler in long answers from dominating.
    - Exact match & whole-phrase containment bonus.
    - Substantive query content token recall check.
    """

    def __init__(
        self,
        documents: Optional[List[FAQDocument]] = None,
        tenant_synonyms: Optional[Dict[str, str]] = None,
        k1: float = 1.2,
        w_question: float = 2.5,
        w_alternate: float = 2.0,
        w_answer: float = 0.4,
        b_question: float = 0.5,
        b_alternate: float = 0.5,
        b_answer: float = 0.8,
    ) -> None:
        self.k1 = k1
        self.w_question = w_question
        self.w_alternate = w_alternate
        self.w_answer = w_answer
        self.b_question = b_question
        self.b_alternate = b_alternate
        self.b_answer = b_answer
        self.tenant_synonyms = tenant_synonyms or {}

        self.documents: List[FAQDocument] = []
        self.N: int = 0
        self.avg_q_len: float = 1.0
        self.avg_alt_len: float = 1.0
        self.avg_a_len: float = 1.0
        self.df: Counter = Counter()

        if documents:
            self.index(documents)

    def index(self, documents: List[FAQDocument]) -> None:
        """Build term document frequencies and field statistics across tenant corpus."""
        self.documents = list(documents)
        self.N = len(self.documents)

        if self.N == 0:
            return

        total_q = sum(len(d.question_tokens) for d in self.documents)
        total_alt = sum(
            sum(len(toks) for toks in d.alternate_tokens) / max(1, len(d.alternate_tokens))
            if d.alternate_tokens else 0
            for d in self.documents
        )
        total_a = sum(len(d.answer_tokens) for d in self.documents)

        self.avg_q_len = max(1.0, total_q / self.N)
        self.avg_alt_len = max(1.0, total_alt / self.N) if total_alt > 0 else 1.0
        self.avg_a_len = max(1.0, total_a / self.N)

        self.df = Counter()
        for doc in self.documents:
            unique_terms: Set[str] = set(doc.question_tokens) | set(doc.answer_tokens)
            for alt_toks in doc.alternate_tokens:
                unique_terms.update(alt_toks)
            for term in unique_terms:
                self.df[term] += 1

    def idf(self, term: str) -> float:
        """Compute standard Robertson-Spärck Jones IDF with floor."""
        n = self.df.get(term, 0)
        return math.log(((self.N - n + 0.5) / (n + 0.5)) + 1.0)

    def retrieve(self, query: str, top_k: int = 5) -> List[ScoredCandidate]:
        """Rank indexed FAQs against customer query."""
        if not self.documents:
            return []

        clean_query = strip_punctuation_unicode(normalize_text(query)).lower()
        raw_tokens = tokenize(query)
        if not raw_tokens:
            return []

        # Content tokens: substantive terms excluding minimal grammatical filler
        content_tokens = extract_content_tokens(raw_tokens)
        query_content_set = set(content_tokens)

        # Expanded tokens incorporating tenant synonyms and transliterated equivalents
        expanded_tokens = expand_tokens_with_synonyms(
            raw_tokens,
            tenant_synonyms=self.tenant_synonyms,
            use_default_hinglish=True,
        )
        expanded_set = set(expanded_tokens)

        max_possible_idf = sum(self.idf(t) for t in expanded_set) or 1.0
        candidates: List[ScoredCandidate] = []

        for doc in self.documents:
            clean_doc_q = strip_punctuation_unicode(doc.question).lower()

            # 1. Exact phrase / question match
            if clean_query and clean_query == clean_doc_q:
                candidates.append(
                    ScoredCandidate(
                        faq=doc,
                        raw_score=100.0,
                        confidence_score=1.0,
                        token_coverage=1.0,
                        match_type="exact_question",
                        evidence_terms=list(doc.question_tokens),
                        matched_field="question",
                    )
                )
                continue

            # 2. Exact match against an alternate question phrasing
            matched_alt = None
            for alt_str in doc.alternate_questions:
                clean_alt = strip_punctuation_unicode(alt_str).lower()
                if clean_query and clean_query == clean_alt:
                    matched_alt = alt_str
                    break

            if matched_alt:
                candidates.append(
                    ScoredCandidate(
                        faq=doc,
                        raw_score=95.0,
                        confidence_score=0.96,
                        token_coverage=1.0,
                        match_type="exact_alternate",
                        evidence_terms=list(raw_tokens),
                        matched_field="alternate_questions",
                    )
                )
                continue

            # 3. Whole-string containment check
            containment_boost = 0.0
            if len(clean_query) >= 4 and len(clean_doc_q) >= 4:
                if clean_query in clean_doc_q or clean_doc_q in clean_query:
                    containment_boost = 0.88

            # Substantive content token check
            # At least ONE content token must overlap with question, alternates, or answer.
            # This prevents queries like "Can you repair laptop motherboard?" from matching on "you".
            content_overlap = query_content_set & doc.all_tokens
            if query_content_set and not content_overlap and not (expanded_set & doc.all_tokens):
                # Zero content evidence
                continue

            # 4. Multi-field BM25F calculation
            q_tf = Counter(doc.question_tokens)
            a_tf = Counter(doc.answer_tokens)

            # Combined alternate TF
            alt_tf = Counter()
            for alt_toks in doc.alternate_tokens:
                alt_tf.update(alt_toks)

            len_norm_q = 1.0 - self.b_question + self.b_question * (len(doc.question_tokens) / self.avg_q_len)
            len_norm_alt = (
                1.0 - self.b_alternate + self.b_alternate * (sum(len(t) for t in doc.alternate_tokens) / (self.avg_alt_len or 1.0))
                if doc.alternate_tokens else 1.0
            )
            len_norm_a = 1.0 - self.b_answer + self.b_answer * (len(doc.answer_tokens) / self.avg_a_len)

            bm25_sum = 0.0
            matched_terms: Set[str] = set()

            for term in expanded_set:
                tf_q_term = q_tf.get(term, 0)
                tf_alt_term = alt_tf.get(term, 0)
                tf_a_term = a_tf.get(term, 0)

                if tf_q_term == 0 and tf_alt_term == 0 and tf_a_term == 0:
                    continue

                matched_terms.add(term)

                # Weight-normalized effective term frequency
                tf_tilde = (
                    (self.w_question * tf_q_term / len_norm_q)
                    + (self.w_alternate * tf_alt_term / len_norm_alt)
                    + (self.w_answer * tf_a_term / len_norm_a)
                )

                bm25_sum += self.idf(term) * (tf_tilde / (self.k1 + tf_tilde))

            # Query recall metrics
            q_overlap = query_content_set & set(doc.question_tokens)
            # Count terms whose expanded synonyms matched question terms (e.g. gaadi -> parking)
            for t in query_content_set:
                syn = self.tenant_synonyms.get(t) or DEFAULT_HINGLISH_SYNONYMS.get(t)
                if syn and syn in set(doc.question_tokens):
                    q_overlap.add(t)

            covered_content = {
                t for t in query_content_set
                if t in doc.all_tokens
                or ((self.tenant_synonyms.get(t) or DEFAULT_HINGLISH_SYNONYMS.get(t)) in doc.all_tokens)
            }
            recall_q = min(1.0, len(q_overlap) / max(1, len(query_content_set)))
            recall_total = min(1.0, len(covered_content) / max(1, len(query_content_set)))

            # Normalization of bm25_sum against theoretical maximum single-term question match
            max_term_scaling = self.w_question / (self.k1 + self.w_question)
            rel_score = min(1.0, bm25_sum / max(0.1, max_possible_idf * max_term_scaling))

            # Composite calibrated confidence (approximate BM25 capped at 0.84 to preserve ambiguity boundary)
            raw_conf = (
                (0.35 * rel_score)
                + (0.45 * recall_q)
                + (0.20 * recall_total)
            )
            conf = min(0.84, raw_conf)

            if containment_boost > 0.0:
                conf = max(conf, containment_boost)

            if conf > 0.0 and len(matched_terms) > 0:
                candidates.append(
                    ScoredCandidate(
                        faq=doc,
                        raw_score=round(bm25_sum, 4),
                        confidence_score=round(conf, 4),
                        token_coverage=round(recall_total, 4),
                        match_type="bm25_lexical",
                        evidence_terms=list(matched_terms),
                        matched_field="question" if q_overlap else "answer",
                    )
                )

        # Sort descending by confidence score, then raw score
        candidates.sort(key=lambda c: (c.confidence_score, c.raw_score), reverse=True)
        return candidates[:top_k]
