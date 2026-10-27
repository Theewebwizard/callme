"""
Domain models and outcome schemas for the multilingual FAQ retrieval subsystem.
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Set
from pydantic import BaseModel, Field, ConfigDict


class MatchOutcome(str, Enum):
    """
    Evidence-based outcomes for FAQ candidate retrieval.
    Separates strong matches from ambiguous matches, insufficient evidence,
    and unconfigured/empty FAQ state.
    """
    STRONG_MATCH = "strong_match"
    AMBIGUOUS_MATCH = "ambiguous_match"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    EMPTY_OR_UNAVAILABLE = "empty_or_unavailable"


class FAQDocument(BaseModel):
    """
    Validated, normalized in-memory representation of a tenant FAQ item.
    Pre-tokenized for deterministic, high-performance lexical and BM25 ranking.
    """
    id: str
    question: str
    answer: str
    category: str = "General"
    alternate_questions: List[str] = Field(default_factory=list)
    synonyms: Dict[str, str] = Field(default_factory=dict)
    
    # Pre-computed tokens and normalized fields
    clean_question: str = ""
    question_tokens: List[str] = Field(default_factory=list)
    content_tokens: List[str] = Field(default_factory=list)
    alternate_tokens: List[List[str]] = Field(default_factory=list)
    answer_tokens: List[str] = Field(default_factory=list)
    all_tokens: Set[str] = Field(default_factory=set)

    model_config = ConfigDict(extra="ignore")


class ScoredCandidate(BaseModel):
    """
    Candidate FAQ with multi-signal score metrics and token coverage.
    Scores are kept separate from probability assumptions.
    """
    faq: FAQDocument
    raw_score: float = 0.0
    confidence_score: float = 0.0  # Calibrated normalized confidence [0.0, 1.0]
    token_coverage: float = 0.0    # Ratio of substantive query terms matched [0.0, 1.0]
    match_type: str = "bm25_lexical"
    evidence_terms: List[str] = Field(default_factory=list)
    matched_field: str = "question"

    model_config = ConfigDict(extra="ignore")


class DecisionResult(BaseModel):
    """
    Decision produced by the evidence engine comparing top candidates and runner-up margin.
    """
    outcome: MatchOutcome
    best_candidate: Optional[ScoredCandidate] = None
    runner_up: Optional[ScoredCandidate] = None
    confidence_score: float = 0.0
    reason: str = ""
    top_candidates: List[ScoredCandidate] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")
