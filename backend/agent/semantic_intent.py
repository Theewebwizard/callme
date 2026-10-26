"""
Semantic intent extraction and Pydantic validation for the AI Calling Agent.
Analyzes conversational meaning (rather than rigid keywords) to determine whether
the caller has further queries, is done, or is initiating a new request.
"""

from enum import Enum
import json
import logging
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class FollowupIntentType(str, Enum):
    """Semantic intent classification of caller's response to an 'anything else' prompt."""
    NO_FURTHER_QUERY = "no_further_query"  # Caller is satisfied, done, has no more queries
    HAS_FURTHER_QUERY = "has_further_query"  # Caller confirms they have another question/request
    NEW_INQUIRY = "new_inquiry"  # Caller directly asks their next question/request
    UNCLEAR = "unclear"  # Ambiguous utterance or filler


class SemanticIntentExtraction(BaseModel):
    """
    Pydantic schema for extracting and validating caller semantic intent.
    Eliminates fragile exact-keyword matching while guaranteeing robust typing.
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
        description="True if the caller expressed a parting/goodbye greeting.",
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
        description="Linguistic explanation of the semantic interpretation.",
    )


class WorkCompletionExtraction(BaseModel):
    """
    Pydantic schema assessing whether an assistant response confirms completed work
    and proactively includes a follow-up inquiry.
    """
    is_completed: bool = Field(
        default=False,
        description="True if the response confirms a completed task or tool execution.",
    )
    task_type: Optional[str] = Field(
        default=None,
        description="Type of task completed (e.g. booking, appointment, faq, message, inquiry).",
    )
    has_followup_question: bool = Field(
        default=False,
        description="True if the response already asks if caller has other queries/needs.",
    )
    summary: str = Field(
        default="",
        description="Brief summary of the work done.",
    )


# Patterns that indicate the assistant asked if caller has any other query
_FOLLOWUP_QUESTION_PATTERNS = [
    r"anything\s+else",
    r"further\s+(?:questions?|queries|assistance|help)",
    r"any\s+other\s+(?:questions?|queries|inquiry|help|assistance)",
    r"help\s+you\s+with\s+(?:anything|something)\s+else",
    r"assist\s+you\s+with\s+(?:anything|something)",
    r"(?:कोई\s+और|और\s+कोई)\s*(?:सवाल|मदद|सहायता|जानकारी|चीज़)",
    r"और\s+कुछ",
    r"aur\s+kuch",
    r"(?:koi\s+aur|aur\s+koi)\s*(?:sawal|madad|cheez|help|chiz)",
    r"kisi\s+aur\s+(?:chiz|cheez|baat)\s+mein\s+madad",
]

# Patterns confirming completion of an action
_WORK_COMPLETION_PATTERNS = [
    r"(?:table|reservation|booking)\s+(?:is\s+)?(?:confirmed|booked|available)",
    r"(?:appointment|consultation)\s+(?:is\s+)?(?:scheduled|booked|confirmed)",
    r"(?:message|note)\s+(?:has\s+been\s+)?(?:taken|recorded|saved|forwarded)",
    r"(?:transferred|transferring\s+your\s+call)",
    r"i\s+have\s+(?:checked|booked|confirmed|taken|scheduled|noted)",
    r"i(?:'ve|'ll)\s+(?:successfully\s+)?(?:booked|scheduled|noted|checked|recorded)",
    r"(?:टेबल|बुकिंग)\s+(?:हो\s+गई|कंफर्म)",
    r"(?:अपॉइंटमेंट)\s+(?:तय|बुक)",
    r"(?:मैसेज|संदेश)\s+(?:ले\s+लिया|दर्ज)",
]


def is_followup_prompt(text: str) -> bool:
    """
    Semantically detect if the assistant's utterance asked whether the caller
    has any other query or needs further assistance.
    """
    if not text or not isinstance(text, str):
        return False
    lower = text.lower().strip()
    return any(re.search(pat, lower) for pat in _FOLLOWUP_QUESTION_PATTERNS)


def is_work_completed_response(text: str) -> bool:
    """
    Semantically detect if an assistant response conveys that a requested task or
    action has been completed.
    """
    if not text or not isinstance(text, str):
        return False
    lower = text.lower().strip()
    return any(re.search(pat, lower) for pat in _WORK_COMPLETION_PATTERNS)


def detect_language(text: str) -> str:
    """Detect if utterance is in Hindi/Hinglish or English."""
    if not text:
        return "en"
    # Devanagari script range
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "hi"
    lower_words = set(re.findall(r"\b\w+\b", text.lower()))
    hindi_cues = {
        "namaste", "dhanyavad", "shukriya", "nahi", "nahin", "haan", "haanji",
        "kuch", "aur", "bas", "theek", "shyam", "subah", "bhaiya", "sirji", "ji"
    }
    if len(lower_words.intersection(hindi_cues)) >= 1:
        return "hi"
    return "en"


def _linguistic_semantic_classify(
    caller_text: str,
    last_assistant_text: str = "",
) -> SemanticIntentExtraction:
    """
    Deep semantic rule-based classifier evaluating caller intent.
    Distinguishes contextual negation ('No, that is all') from affirmative/neutral
    uses of negation ('No problem, please book it').
    """
    clean_text = caller_text.strip()
    lower = clean_text.lower()
    lang = detect_language(clean_text)

    # 1. Check for Farewell / Goodbyes
    farewell_cues = [
        "bye", "goodbye", "good bye", "see you", "take care", "have a good day",
        "have a nice day", "have a great day", "alvida", "shubh din", "bye for now"
    ]
    has_farewell = any(re.search(rf"\b{re.escape(cue)}\b", lower) for cue in farewell_cues)

    # 2. Check for Direct New Questions / Inquiries
    # (Wh-questions, question marks, or explicit requests for info)
    question_starters = [
        r"^(?:what|when|where|which|who|why|how|can|could|do|does|is|are|will|would)\b",
        r"^(?:kya|kab|kaha|kaise|kitna|kitne|kaun)\b",
    ]
    is_direct_question = (
        "?" in clean_text
        or any(re.search(qs, lower) for qs in question_starters)
        or ("what about" in lower)
        or ("tell me about" in lower)
        or ("bataiye" in lower and "?" in clean_text)
    )

    # 3. Check for Affirmative Intent (Caller confirms they have another question)
    # Examples: "yes", "actually yes", "one more thing", "haanji ek sawal aur", etc.
    affirmative_patterns = [
        r"^(?:yes|yeah|yep|yup|sure|of course)\b",
        r"\b(?:actually\s+(?:yes|yeah|yep|yup|sure)|yes\s+please|i\s+do)\b",
        r"\b(?:i\s+(?:have|had)\s+(?:a|another|one more)?\s*(?:question|doubt|query))\b",
        r"\b(?:had|have)\s+a\s+(?:doubt|question|query)\b",
        r"\b(?:one\s+more\s+(?:thing|question|doubt)|also\s+wanted\s+to\s+(?:know|ask))\b",
        r"^(?:haan|haanji|ha ji|ji haan|haan ji)\b",
        r"\b(?:ek\s+(?:aur|sawal|baat|cheez)|aur\s+ek\s+(?:sawal|baat|cheez)|ek\s+doubt)\b",
    ]
    is_affirmative = any(re.search(pat, lower) for pat in affirmative_patterns)

    # 4. Check for Explicit Work Done / Completion Phrases
    # Covers phrases like "yes work is done", "work is done", "yes that's all", "yes I'm done", "haan kaam ho gaya"
    # where the caller confirms their task/request is finished and they are satisfied to end.
    completion_patterns = [
        r"\b(?:work\s+(?:is\s+)?done|my\s+work\s+is\s+done|all\s+done|everything\s+is\s+done|task\s+(?:is\s+)?done)\b",
        r"\b(?:that(?:'s| is| will be)\s+all|that(?:'s| is)\s+it|nothing\s+else|nothing\s+for\s+now)\b",
        r"\b(?:i(?:'m| am)\s+(?:done|good|all good|all set)|we(?:'re| are)\s+(?:done|good|all set))\b",
        r"\b(?:kaam\s+ho\s+gaya|sab\s+ho\s+gaya|bas\s+ho\s+gaya|ho\s+gaya\s+kaam|done\s+hai|ho\s+gaya)\b",
        r"\b(?:aur\s+kuch\s+nahi|kuch\s+nahi\s+chahiye|bas\s+itna\s+hi)\b",
    ]
    is_completion_stated = any(re.search(pat, lower) for pat in completion_patterns)

    # 5. Check for Negative Intent (Caller says no more queries)
    # Context-aware: "no", "nope", "nahi bas"
    # IMPORTANT: Must NOT match "no problem", "no doubt", "no wait", etc.
    non_negative_exceptions = [
        r"\bno\s+problem\b",
        r"\bno\s+worries\b",
        r"\bno\s+doubt\b",
        r"\bno[,\s]+wait\b",
        r"\bno[,\s]+actually\b",
    ]
    has_exception = any(re.search(exc, lower) for exc in non_negative_exceptions)

    negative_patterns = [
        r"^(?:no|nope|nah|nay)(?:[,\.\s]|$)",
        r"\b(?:all good|all set|done for now)\b",
        r"\b(?:no thanks|no thank you|no more questions?)\b",
        r"^(?:nahi|nahin|na)(?:[,\.\s]|$)",
        r"\b(?:nahi bas|kuch nahi|kuch nahi chahiye|bas itna hi|bas ho gaya)\b",
        r"\b(?:aur kuch nahi|shukriya bas|nahi shukriya|sab theek hai|sab theek)\b",
    ]
    is_negative = not has_exception and any(re.search(pat, lower) for pat in negative_patterns)

    # Evaluate synthesized decision
    # Priority A: Caller explicitly says work is done / that is all -> NO_FURTHER_QUERY
    if is_completion_stated and not is_direct_question:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.NO_FURTHER_QUERY,
            has_more_queries=False,
            is_farewell=has_farewell,
            language=lang,
            confidence=0.98,
            reasoning="Caller semantically indicated completion (work is done, that's all, or satisfied).",
        )

    # Priority B: Explicit negative / farewell
    if is_negative or (has_farewell and not is_affirmative and not is_direct_question):
        return SemanticIntentExtraction(
            intent=FollowupIntentType.NO_FURTHER_QUERY,
            has_more_queries=False,
            is_farewell=has_farewell,
            language=lang,
            confidence=0.95,
            reasoning="Caller semantically indicated completion, no more questions, or goodbye.",
        )

    if is_direct_question and not is_negative:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.NEW_INQUIRY,
            has_more_queries=True,
            is_farewell=False,
            language=lang,
            confidence=0.92,
            reasoning="Caller directly posed a new question or inquiry.",
        )

    if is_affirmative:
        return SemanticIntentExtraction(
            intent=FollowupIntentType.HAS_FURTHER_QUERY,
            has_more_queries=True,
            is_farewell=False,
            language=lang,
            confidence=0.95,
            reasoning="Caller semantically indicated having another question or request.",
        )

    return SemanticIntentExtraction(
        intent=FollowupIntentType.UNCLEAR,
        has_more_queries=None,
        is_farewell=has_farewell,
        language=lang,
        confidence=0.50,
        reasoning="Utterance did not clearly resolve to affirmative, negative, or new question.",
    )


def extract_semantic_followup_intent(
    caller_text: str,
    last_assistant_text: str = "",
    groq_service: Optional[Any] = None,
) -> SemanticIntentExtraction:
    """
    Extract semantic intent from caller's response to an 'anything else' prompt
    using Pydantic validation.
    
    If Groq is available and configured, leverages fast structured JSON completion.
    Gracefully falls back to the deep linguistic semantic classifier.
    """
    if not caller_text or not caller_text.strip():
        return SemanticIntentExtraction(
            intent=FollowupIntentType.UNCLEAR,
            has_more_queries=None,
            is_farewell=False,
            confidence=0.0,
            reasoning="Empty caller utterance.",
        )

    # 1. Attempt Groq structured completion if available and client initialized
    if groq_service and getattr(groq_service, "is_configured", False) and getattr(groq_service, "client", None):
        try:
            system_prompt = (
                "You are an expert conversational semantic classifier for an AI telephone receptionist.\n"
                "The assistant just asked the caller if they have any other questions or need further help.\n"
                "Analyze the caller's reply and return strict JSON with:\n"
                "- 'intent': 'no_further_query' | 'has_further_query' | 'new_inquiry' | 'unclear'\n"
                "- 'has_more_queries': true | false | null\n"
                "- 'is_farewell': true | false\n"
                "- 'language': 'en' | 'hi'\n"
                "- 'reasoning': string explanation\n\n"
                "Rules:\n"
                "- Focus on SEMANTIC INTENT, not mere word matching.\n"
                "- 'no_further_query': caller is done, satisfied, says no/that's all/I'm good/nahi bas/kuch nahi.\n"
                "- 'has_further_query': caller wants to ask something else (yes/actually yeah/one more thing/haanji).\n"
                "- 'new_inquiry': caller immediately asks their next question directly.\n"
            )
            completion = groq_service.client.chat.completions.create(
                model=groq_service.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Assistant's prior question: {last_assistant_text}\nCaller's response: {caller_text}",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=150,
            )
            raw_json = completion.choices[0].message.content
            if raw_json:
                data = json.loads(raw_json)
                return SemanticIntentExtraction.model_validate(data)
        except (ValidationError, Exception) as err:
            logger.debug("Groq structured semantic extraction fell back to linguistic rule engine: %s", str(err))

    # 2. Resilient linguistic fallback, strictly validated via Pydantic
    return _linguistic_semantic_classify(
        caller_text=caller_text,
        last_assistant_text=last_assistant_text,
    )
