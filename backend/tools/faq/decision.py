"""
Evidence-based decision engine for FAQ match categorization.
Distinguishes strong matches, ambiguous candidate ties, insufficient evidence,
and empty knowledge bases without assuming raw scores are probabilities.
"""

import logging
from typing import List, Optional

from backend.tools.faq.models import (
    MatchOutcome,
    ScoredCandidate,
    DecisionResult,
)

logger = logging.getLogger(__name__)

# Configurable evidence thresholds
DEFAULT_MIN_CONFIDENCE_THRESHOLD: float = 0.28
DEFAULT_AMBIGUITY_MARGIN: float = 0.08
DEFAULT_EXACT_MATCH_THRESHOLD: float = 0.85


class FAQDecisionEngine:
    """
    Evaluates ranked candidate evidence to decide match outcome.
    
    Threshold Semantics:
    - min_confidence: Minimum calibrated evidence score required to treat a candidate as viable.
    - ambiguity_margin: Maximum score gap between top two candidates that triggers a clarification request.
    - exact_threshold: Confidence score above which a match is considered unambiguous (exact phrase).
    """

    def __init__(
        self,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE_THRESHOLD,
        ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
        exact_threshold: float = DEFAULT_EXACT_MATCH_THRESHOLD,
    ) -> None:
        self.min_confidence = min_confidence
        self.ambiguity_margin = ambiguity_margin
        self.exact_threshold = exact_threshold

    def evaluate(
        self,
        ranked_candidates: List[ScoredCandidate],
        total_faqs_in_corpus: int,
    ) -> DecisionResult:
        """
        Evaluate candidate list against calibrated decision rules.
        Handles single-candidate and multi-candidate scenarios separately.
        """
        # 1. Empty knowledge base
        if total_faqs_in_corpus == 0:
            return DecisionResult(
                outcome=MatchOutcome.EMPTY_OR_UNAVAILABLE,
                best_candidate=None,
                runner_up=None,
                confidence_score=0.0,
                reason="Tenant has no configured FAQs.",
                top_candidates=[],
            )

        # 2. No candidates scored
        if not ranked_candidates:
            return DecisionResult(
                outcome=MatchOutcome.INSUFFICIENT_EVIDENCE,
                best_candidate=None,
                runner_up=None,
                confidence_score=0.0,
                reason="No candidate FAQs had term overlap with query.",
                top_candidates=[],
            )

        best = ranked_candidates[0]

        # 3. Check minimum evidence threshold
        if best.confidence_score < self.min_confidence:
            return DecisionResult(
                outcome=MatchOutcome.INSUFFICIENT_EVIDENCE,
                best_candidate=best,
                runner_up=ranked_candidates[1] if len(ranked_candidates) > 1 else None,
                confidence_score=best.confidence_score,
                reason=f"Top candidate score {best.confidence_score:.3f} below evidence threshold {self.min_confidence:.3f}.",
                top_candidates=ranked_candidates[:2],
            )

        # 4. Multi-candidate ambiguity check (Runner-up comparison)
        if len(ranked_candidates) >= 2:
            second = ranked_candidates[1]
            score_diff = best.confidence_score - second.confidence_score

            # Ambiguity triggers only if:
            # - Best candidate is not an exact/near-exact match (score < exact_threshold)
            # - Score difference is narrower than ambiguity_margin
            # - Runner-up itself meets the minimum confidence threshold
            if (
                best.confidence_score < self.exact_threshold
                and score_diff < self.ambiguity_margin
                and second.confidence_score >= self.min_confidence
            ):
                logger.info(
                    "Detected ambiguous FAQ match between '%s' (%.3f) and '%s' (%.3f) [Diff: %.3f]",
                    best.faq.question,
                    best.confidence_score,
                    second.faq.question,
                    second.confidence_score,
                    score_diff,
                )
                return DecisionResult(
                    outcome=MatchOutcome.AMBIGUOUS_MATCH,
                    best_candidate=best,
                    runner_up=second,
                    confidence_score=best.confidence_score,
                    reason=f"Close scores between candidates (diff {score_diff:.3f} < margin {self.ambiguity_margin:.3f}).",
                    top_candidates=[best, second],
                )

        # 5. Strong unambiguous match (single candidate or clear margin winner)
        return DecisionResult(
            outcome=MatchOutcome.STRONG_MATCH,
            best_candidate=best,
            runner_up=ranked_candidates[1] if len(ranked_candidates) > 1 else None,
            confidence_score=best.confidence_score,
            reason=f"Strong match on '{best.faq.question}' ({best.match_type}).",
            top_candidates=ranked_candidates[:2],
        )
