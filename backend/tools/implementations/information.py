"""
Information and knowledge-base tool implementations.
Includes multilingual, multi-tenant FAQ retrieval with BM25F ranking,
evidence-based match decisions, and strict answer grounding.
"""

import uuid
import logging
from typing import Dict, Any, List, Tuple, Set

from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import AnswerFAQInput
from backend.tools.faq import (
    MatchOutcome,
    FAQDocument,
    ScoredCandidate,
    validate_and_deduplicate_faqs,
    BM25FAQRetriever,
    FAQDecisionEngine,
    ALL_MINIMAL_STOPWORDS,
    DEFAULT_MIN_CONFIDENCE_THRESHOLD,
    DEFAULT_AMBIGUITY_MARGIN,
)

logger = logging.getLogger(__name__)

# Backwards compatibility re-exports
STOP_WORDS: Set[str] = ALL_MINIMAL_STOPWORDS
MIN_CONFIDENCE_THRESHOLD: float = DEFAULT_MIN_CONFIDENCE_THRESHOLD
AMBIGUITY_MARGIN: float = DEFAULT_AMBIGUITY_MARGIN


class FAQSearchEngine:
    """
    Search engine facade for tenant-configured FAQs.
    Separates normalization, validation, and multi-field BM25F ranking
    from tool response assembly.
    """

    @classmethod
    def rank_faqs(
        cls,
        query: str,
        faqs: List[Dict[str, Any]],
        tenant_synonyms: Any = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Validate, normalize, and rank FAQ candidates descending by relevance score.
        Deduplicates identical questions and filters malformed entries.
        Returns list of (faq_dict, confidence_score) tuples for backwards compatibility.
        """
        synonyms = tenant_synonyms if isinstance(tenant_synonyms, dict) else None
        valid_docs = validate_and_deduplicate_faqs(faqs, tenant_synonyms=synonyms)
        if not valid_docs:
            return []

        retriever = BM25FAQRetriever(valid_docs, tenant_synonyms=synonyms)
        candidates = retriever.retrieve(query, top_k=len(valid_docs))

        results: List[Tuple[Dict[str, Any], float]] = []
        for c in candidates:
            faq_dict = {
                "id": c.faq.id,
                "question": c.faq.question,
                "answer": c.faq.answer,
                "category": c.faq.category,
                "alternate_questions": c.faq.alternate_questions,
            }
            results.append((faq_dict, c.confidence_score))

        return results


def handle_answer_faq(
    input_data: AnswerFAQInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Search the business's configured FAQs for a grounded answer.
    
    Guarantees:
    - Never synthesizes or hallucinates unconfigured policies or hours.
    - Decoupled into validation, Unicode normalization, BM25F ranking, and decision engine.
    - Accurately tracks execution mode (live vs mock) based on tenant configuration.
    - Evidence-based classification: strong match, ambiguous tie, or insufficient evidence.
    """
    query = input_data.question.strip()
    faqs = business_config.get("faqs", [])
    biz_name = business_config.get("name", "our business")
    phone = business_config.get("phone_number", "our reception desk")
    raw_mode = business_config.get("execution_mode", "mock")
    is_live = (str(raw_mode).lower() == "live")
    exec_mode = ToolExecutionMode.LIVE if is_live else ToolExecutionMode.MOCK

    tenant_synonyms = business_config.get("faq_synonyms") or business_config.get("synonyms")
    if not isinstance(tenant_synonyms, dict):
        tenant_synonyms = None

    try:
        # 1. Validate, sanitize, and deduplicate tenant FAQs (pure, non-mutating)
        validated_docs = validate_and_deduplicate_faqs(faqs, tenant_synonyms=tenant_synonyms)

        # 2. Empty or unconfigured knowledge base
        if not validated_docs:
            return ToolExecutionResult(
                tool_id="answer_faq",
                status=ToolExecutionStatus.SUCCESS,
                success=False,
                is_business_accepted=False,
                mode=exec_mode,
                is_simulated=False,
                data={
                    "found": False,
                    "faqs_available": 0,
                    "query": query,
                    "match_outcome": MatchOutcome.EMPTY_OR_UNAVAILABLE.value,
                },
                message=f"{biz_name} has no configured FAQs. Please reach out directly to staff at {phone}.",
            )

        # 3. Retrieve ranked candidates via multi-field BM25F
        retriever = BM25FAQRetriever(validated_docs, tenant_synonyms=tenant_synonyms)
        ranked_candidates = retriever.retrieve(query, top_k=5)

        # 4. Evidence-based match decision
        decision_engine = FAQDecisionEngine(
            min_confidence=DEFAULT_MIN_CONFIDENCE_THRESHOLD,
            ambiguity_margin=DEFAULT_AMBIGUITY_MARGIN,
        )
        decision = decision_engine.evaluate(ranked_candidates, total_faqs_in_corpus=len(validated_docs))

        # 5. Result assembly according to decision outcome
        if decision.outcome == MatchOutcome.STRONG_MATCH and decision.best_candidate:
            best = decision.best_candidate
            return ToolExecutionResult(
                tool_id="answer_faq",
                status=ToolExecutionStatus.SUCCESS,
                success=True,
                is_business_accepted=True,
                mode=exec_mode,
                is_simulated=False,
                data={
                    "found": True,
                    "matched_question": best.faq.question,
                    "answer": best.faq.answer,
                    "confidence_score": round(best.confidence_score, 3),
                    "source": "tenant_configured_faqs",
                    "retrieval_method": "bm25_multilingual_ranking",
                    "candidates_evaluated": len(ranked_candidates),
                    "faq_id": best.faq.id,
                    "match_outcome": MatchOutcome.STRONG_MATCH.value,
                },
                message=best.faq.answer,
            )

        if decision.outcome == MatchOutcome.AMBIGUOUS_MATCH and decision.best_candidate and decision.runner_up:
            q1 = decision.best_candidate.faq.question
            q2 = decision.runner_up.faq.question
            return ToolExecutionResult(
                tool_id="answer_faq",
                status=ToolExecutionStatus.SUCCESS,
                success=False,
                is_business_accepted=False,
                mode=exec_mode,
                is_simulated=False,
                error_code="AMBIGUOUS_FAQ_MATCH",
                data={
                    "found": False,
                    "is_ambiguous": True,
                    "match_outcome": MatchOutcome.AMBIGUOUS_MATCH.value,
                    "top_candidates": [
                        {"question": q1, "score": round(decision.best_candidate.confidence_score, 3)},
                        {"question": q2, "score": round(decision.runner_up.confidence_score, 3)},
                    ],
                    "query": query,
                },
                message=(
                    f"Your question could relate to either '{q1}' or '{q2}'. "
                    f"Could you please specify which topic you are inquiring about?"
                ),
            )

        # Insufficient evidence or below confidence threshold
        top_score = ranked_candidates[0].confidence_score if ranked_candidates else 0.0
        return ToolExecutionResult(
            tool_id="answer_faq",
            status=ToolExecutionStatus.SUCCESS,
            success=False,
            is_business_accepted=False,
            mode=exec_mode,
            is_simulated=False,
            data={
                "found": False,
                "query": query,
                "confidence_score": round(top_score, 3),
                "match_outcome": MatchOutcome.INSUFFICIENT_EVIDENCE.value,
            },
            message=(
                f"No matching FAQ was found for '{input_data.question}' in {biz_name}'s "
                f"knowledge base. Please contact our reception desk at {phone} for assistance."
            ),
        )

    except Exception as exc:
        err_id = uuid.uuid4().hex[:8]
        logger.error(
            "FAQ search error [ID: %s] for query '%s' against business '%s': %s",
            err_id, query, business_config.get("id"), exc, exc_info=True,
        )
        return ToolExecutionResult(
            tool_id="answer_faq",
            status=ToolExecutionStatus.ERROR,
            success=False,
            is_business_accepted=False,
            mode=exec_mode,
            is_simulated=False,
            error_code="FAQ_SEARCH_ERROR",
            internal_diagnostics=f"Exception [{err_id}] in answer_faq: {type(exc).__name__}: {str(exc)}",
            message=f"An error occurred while searching FAQs (Error ID: {err_id}). Please contact our reception desk at {phone}.",
        )
