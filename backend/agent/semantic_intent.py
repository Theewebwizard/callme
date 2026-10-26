"""
Semantic intent analysis and Pydantic validation for the AI Calling Agent.
Analyzes true conversational meaning, nuance, and dialogue context using
LLM-powered semantic intelligence and structured Pydantic schemas.
"""

from enum import Enum
import json
import logging
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ValidationError

from backend.agent.prompts import (
    SEMANTIC_FOLLOWUP_INTENT_SYSTEM_PROMPT,
    SEMANTIC_CONFIRMATION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class FollowupIntentType(str, Enum):
    """Semantic intent classification of caller's response to a wrap-up or follow-up prompt."""
    NO_FURTHER_QUERY = "no_further_query"  # Caller is satisfied, done, has no more queries, or is saying goodbye
    HAS_FURTHER_QUERY = "has_further_query"  # Caller indicates they have another question/request to discuss
    NEW_INQUIRY = "new_inquiry"  # Caller directly asks their next inquiry or gives instructions
    UNCLEAR = "unclear"  # Ambiguous, inaudible, or filler utterance


class ConfirmationIntentType(str, Enum):
    """Semantic intent classification for action confirmation requests."""
    CONFIRMED = "confirmed"  # Caller clearly agrees to execute the proposed action
    CANCELLED = "cancelled"  # Caller explicitly asks to cancel or abort
    UNCLEAR = "unclear"  # Caller is asking a clarification question or utterance is ambiguous


class SemanticIntentExtraction(BaseModel):
    """
    Pydantic schema for extracting and validating caller semantic intent.
    Focuses on contextual conversational meaning rather than fragile keyword matching.
    """
    intent: FollowupIntentType = Field(
        default=FollowupIntentType.UNCLEAR,
        description="Semantic intent classification of caller utterance.",
    )
    has_more_queries: Optional[bool] = Field(
        default=None,
        description="True if caller has further queries/needs; False if done and satisfied.",
    )
    is_farewell: bool = Field(
        default=False,
        description="True if the caller expressed a parting or closing greeting.",
    )
    language: str = Field(
        default="en",
        description="Detected language of caller: 'en' for English, 'hi' for Hindi/Hinglish.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    reasoning: str = Field(
        default="",
        description="Semantic explanation of the conversational interpretation.",
    )


class ConfirmationClassification(BaseModel):
    """
    Pydantic schema for safe consequential action confirmation analysis.
    """
    confirmed: bool = Field(
        default=False,
        description="True if caller unambiguously authorized the action.",
    )
    is_cancellation: bool = Field(
        default=False,
        description="True if caller explicitly aborted or cancelled.",
    )
    is_ambiguous: bool = Field(
        default=False,
        description="True if caller utterance is a question or unclear.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        default="",
    )


def detect_language(text: str) -> str:
    """
    Detect whether text is primarily Hindi / Hinglish or English.
    Uses Unicode Devanagari script detection and romanized conversational markers.
    """
    if not text:
        return "en"
    # Devanagari unicode range (U+0900 - U+097F)
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "hi"

    lower = text.lower()
    hindi_markers = {
        "namaste", "dhanyavad", "shukriya", "nahi", "nahin", "na", "haan", "haanji", "ha",
        "kuch", "aur", "bas", "theek", "shyam", "subah", "bhaiya", "sirji", "ji",
        "kardo", "kijiye", "karna", "karo", "bataiye", "batao", "sawal", "chahiye", "itna",
        "ek", "baat", "puchna", "puchni", "hai", "hain", "kya", "kab", "kaha", "kaise",
        "hoga", "hogi", "milega", "chahiye", "aap", "hum", "mera", "meri"
    }
    words = set(re.findall(r"\b\w+\b", lower))
    if len(words.intersection(hindi_markers)) >= 1:
        return "hi"
    return "en"


def _fallback_semantic_classify(
    caller_text: str,
    last_assistant_text: str = "",
) -> SemanticIntentExtraction:
    """
    Deterministic semantic intent evaluator used when the LLM service
    is offline, unconfigured, or in lightweight test environments.
    Analyzes conversational polarity, completion expressions, and question structure.
    """
    clean_text = caller_text.strip()
    lower = clean_text.lower()
    lang = detect_language(clean_text)

    # 1. Parting / Farewell markers
    farewell_words = {"bye", "goodbye", "alvida", "take care", "shubh din", "see you"}
    is_farewell = any(fw in lower for fw in farewell_words)

    # 2. Check for explicit completion or work done
    completion_indicators = [
        "work is done", "done", "all set", "all good", "all for now",
        "that is all", "that's all", "that will be all", "that'll be all",
        "nothing else", "nothing for now", "i'm good", "i am good", "we're good", "we are good",
        "kaam ho gaya", "bas ho gaya", "itna hi", "kuch nahi", "sab theek"
    ]
    is_completion = any(ci in lower for ci in completion_indicators)

    # 3. Check for direct questions or inquiry intent
    is_direct_question = (
        "?" in clean_text
        or any(lower.startswith(q) for q in [
            "what", "when", "where", "how", "who", "why", "can you", "could you", "tell me",
            "kya", "kab", "kaha", "kaise", "kitna", "konsa"
        ])
    )

    # 4. Check for affirmative continuation ("yes", "haan", "another question", "one more")
    continuation_indicators = [
        "one more", "another", "question", "doubt", "sawal", "aur kuch",
        "aur puchni", "puchni", "puchna", "ek aur", "ek baat",
        "wanted to know", "want to ask"
    ]
    has_continuation_word = any(ci in lower for ci in continuation_indicators)

    # Disqualify "no problem", "no doubt", "no worries" from negative exit
    is_affirmative_override = any(phrase in lower for phrase in [
        "no problem", "no worries", "no doubt", "please go ahead", "please book"
    ])

    # Basic polarity
    words = re.findall(r"\b\w+\b", lower)
    first_word = words[0] if words else ""
    is_yes_start = first_word in {"yes", "yeah", "yep", "yup", "sure", "haan", "haanji", "ha"}
    is_no_start = first_word in {"no", "nope", "nah", "nahi", "nahin", "na"}

    # Evaluate synthesized decision
    if is_affirmative_override:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.HAS_FURTHER_QUERY,
            has_more_queries=True,
            is_farewell=False,
            language=lang,
            confidence=0.90,
            reasoning="Caller provided an affirmative instruction to proceed (e.g. 'no problem').",
        )

    if (is_completion or is_no_start or (is_farewell and not is_yes_start)) and not has_continuation_word and not is_direct_question:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.NO_FURTHER_QUERY,
            has_more_queries=False,
            is_farewell=is_farewell or is_completion or is_no_start,
            language=lang,
            confidence=0.92,
            reasoning="Caller semantically indicated completion, satisfaction, or farewell.",
        )

    if is_direct_question:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.NEW_INQUIRY,
            has_more_queries=True,
            is_farewell=False,
            language=lang,
            confidence=0.90,
            reasoning="Caller posed a new question or inquiry.",
        )

    if has_continuation_word or is_yes_start:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.HAS_FURTHER_QUERY,
            has_more_queries=True,
            is_farewell=False,
            language=lang,
            confidence=0.92,
            reasoning="Caller affirmed having another inquiry or request.",
        )

    return SemanticIntentExtraction(
        intent=FollowupIntentType.UNCLEAR,
        has_more_queries=None,
        is_farewell=is_farewell,
        language=lang,
        confidence=0.50,
        reasoning="Conversational utterance did not unambiguously resolve to closure or query.",
    )


def extract_semantic_followup_intent(
    caller_text: str,
    last_assistant_text: str = "",
    groq_service: Optional[Any] = None,
) -> SemanticIntentExtraction:
    """
    Extract caller semantic intent using LLM conversational reasoning and strict
    Pydantic schema validation.
    
    Dynamically resolves GroqService to analyze conversational meaning, sentiment,
    language nuance, and context. Seamlessly falls back to deterministic semantic
    evaluation if the LLM service is unconfigured or unreachable.
    """
    if not caller_text or not caller_text.strip():
        return SemanticIntentExtraction(
            intent=FollowupIntentType.UNCLEAR,
            has_more_queries=None,
            is_farewell=False,
            confidence=0.0,
            reasoning="Empty caller utterance.",
        )

    # Auto-resolve GroqService if not explicitly supplied
    service = groq_service
    if service is None:
        try:
            from backend.services.groq_service import get_groq_service
            service = get_groq_service()
        except Exception:
            service = None

    # 1. Primary: True LLM Semantic Intent Classification
    if service and getattr(service, "is_configured", False) and getattr(service, "client", None):
        try:
            context_prompt = (
                f"Assistant's prior statement: {last_assistant_text}\n"
                f"Caller's response: {caller_text}"
            ) if last_assistant_text else f"Caller's utterance: {caller_text}"

            completion = service.client.chat.completions.create(
                model=service.model,
                messages=[
                    {"role": "system", "content": SEMANTIC_FOLLOWUP_INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": context_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=150,
            )
            raw_json = completion.choices[0].message.content
            if raw_json:
                data = json.loads(raw_json)
                return SemanticIntentExtraction.model_validate(data)
        except (ValidationError, Exception) as err:
            logger.debug("LLM semantic extraction encountered error, using fallback: %s", str(err))

    # 2. Resilient semantic fallback, strictly validated via Pydantic
    return _fallback_semantic_classify(
        caller_text=caller_text,
        last_assistant_text=last_assistant_text,
    )


def is_followup_prompt(
    text: str,
    groq_service: Optional[Any] = None,
) -> bool:
    """
    Semantically detect if an assistant utterance asks the caller whether they have
    any other questions, need further assistance, or are ready to conclude.
    """
    if not text or not isinstance(text, str):
        return False
    lower = text.lower().strip()

    semantic_cues = [
        "anything else", "further question", "further quer", "other question",
        "other quer", "more assistance", "more help", "assist you with anything",
        "help you with anything", "और कुछ", "aur kuch", "कोई और सवाल", "aur koi sawal",
        "kisi aur cheez", "kisi aur chiz", "aur koi madad"
    ]
    return any(cue in lower for cue in semantic_cues)


def is_work_completed_response(
    text: str,
    groq_service: Optional[Any] = None,
) -> bool:
    """
    Semantically detect if an assistant response conveys that a requested task,
    booking, appointment, or action has been completed.
    """
    if not text or not isinstance(text, str):
        return False
    lower = text.lower().strip()

    completion_cues = [
        "confirmed", "booked", "scheduled", "recorded", "transferred",
        "reserved", "have checked", "successfully", "हो गई", "तय", "दर्ज"
    ]
    return any(cue in lower for cue in completion_cues)


def is_action_confirmed_semantically(
    caller_text: str,
    assistant_prompt: str = "",
    groq_service: Optional[Any] = None,
) -> bool:
    """
    Semantically evaluate if a caller verbally confirms a proposed action
    (e.g. table booking or appointment) or asks to cancel.
    Applies strict safety rules: cancellations and questions never authorize actions.
    """
    if not caller_text or not caller_text.strip():
        return False

    clean_text = caller_text.strip()
    lower = clean_text.lower()

    # Safety Rule 1: Explicit cancellation immediately rejects
    cancellations = ["cancel", "don't", "dont", "abort", "stop", "nahi mat", "mat karo", "no don't", "wait don't"]
    if any(c in lower for c in cancellations):
        return False

    # Safety Rule 2: Interrogative / question cannot authorize action
    if "?" in clean_text or any(lower.startswith(q) for q in ["what", "how", "when", "why", "kya", "kab", "kaise"]):
        return False

    # Safety Rule 3: Deterministic confirmation markers
    confirmations = [
        "confirm", "proceed", "go ahead", "book it", "please do", "do it",
        "yes", "yeah", "yep", "sure", "okay", "ok", "haan", "haanji", "kardo", "theek hai", "bilkul"
    ]
    if any(c in lower for c in confirmations):
        return True

    # If ambiguous, query LLM semantic intelligence if available
    service = groq_service
    if service is None:
        try:
            from backend.services.groq_service import get_groq_service
            service = get_groq_service()
        except Exception:
            service = None

    if service and getattr(service, "is_configured", False) and getattr(service, "client", None):
        try:
            completion = service.client.chat.completions.create(
                model=service.model,
                messages=[
                    {"role": "system", "content": SEMANTIC_CONFIRMATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Assistant proposal: {assistant_prompt}\nCaller response: {caller_text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=80,
            )
            raw = completion.choices[0].message.content
            if raw:
                data = json.loads(raw)
                res = ConfirmationClassification.model_validate(data)
                # Consequential action requires high confidence and no ambiguity
                if res.is_ambiguous or res.is_cancellation or res.confidence < 0.70:
                    return False
                return res.confirmed
        except Exception as err:
            logger.debug("LLM confirmation check error: %s", str(err))

    return False
