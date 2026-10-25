"""
Answer Business FAQ Tool Functionality.
Standalone tool module for searching and retrieving tenant-configured FAQs.
"""

from typing import Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from tools.base import (
    ToolDefinition,
    ToolCategory,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)

STOP_WORDS = {
    "the", "and", "you", "are", "for", "can", "how", "what", "where",
    "when", "why", "who", "which", "with", "from", "that", "this",
    "our", "have", "your", "does", "about", "allow", "will", "there",
    "accept", "please",
}


class AnswerFAQInput(BaseModel):
    """Input payload for looking up business FAQs."""
    question: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Customer question or inquiry keyword to match against configured FAQs.",
    )

    model_config = ConfigDict(extra="forbid")


def handle_answer_faq(
    input_data: AnswerFAQInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Search the business's configured FAQs for a matching answer.
    Never invents or hallucinates answers not present in the business config.
    """
    query = input_data.question.strip().lower()
    faqs = business_config.get("faqs", [])
    biz_name = business_config.get("name", "our business")
    phone = business_config.get("phone_number", "our primary number")

    if not faqs:
        return ToolExecutionResult(
            tool_id="answer_faq",
            status=ToolExecutionStatus.SUCCESS,
            success=False,
            mode=ToolExecutionMode.MOCK,
            data={"found": False, "faqs_available": 0},
            message=f"{biz_name} has no configured FAQs. Please reach out directly to staff at {phone}.",
        )

    # Extract meaningful keywords excluding common English stop words
    query_words = set(
        w.strip("?,.!")
        for w in query.split()
        if len(w) > 2 and w.lower() not in STOP_WORDS
    )

    best_match = None
    for faq in faqs:
        q_text = faq.get("question", "").lower()
        a_text = faq.get("answer", "")

        # 1. Exact or substring match
        clean_q = q_text.strip("?,.!")
        clean_query = query.strip("?,.!")
        if clean_query in clean_q or clean_q in clean_query:
            best_match = (faq.get("question", ""), a_text)
            break

        # 2. Meaningful keyword overlap
        q_words = set(
            w.strip("?,.!")
            for w in q_text.split()
            if len(w) > 2 and w.lower() not in STOP_WORDS
        )
        overlap = query_words & q_words
        if len(overlap) >= 2 or (len(query_words) == 1 and len(overlap) == 1):
            best_match = (faq.get("question", ""), a_text)
            break

    if best_match:
        matched_q, matched_a = best_match
        return ToolExecutionResult(
            tool_id="answer_faq",
            status=ToolExecutionStatus.SUCCESS,
            success=True,
            mode=ToolExecutionMode.MOCK,
            data={
                "found": True,
                "matched_question": matched_q,
                "answer": matched_a,
                "source": "tenant_configured_faqs",
            },
            message=matched_a,
        )

    return ToolExecutionResult(
        tool_id="answer_faq",
        status=ToolExecutionStatus.SUCCESS,
        success=False,
        mode=ToolExecutionMode.MOCK,
        data={"found": False, "query": input_data.question},
        message=(
            f"No matching FAQ was found for '{input_data.question}' in {biz_name}'s "
            f"knowledge base. Please contact our reception desk at {phone} for assistance."
        ),
    )


def create_answer_faq_tool_def() -> ToolDefinition:
    """Factory creating the canonical Answer FAQ ToolDefinition."""
    return ToolDefinition(
        id="answer_faq",
        name="Answer Business FAQs",
        description="Search business knowledge base and FAQs to answer customer inquiries accurately.",
        category=ToolCategory.INFORMATION,
        allowed_industries=["*"],
        input_schema=AnswerFAQInput,
        requires_confirmation=False,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_answer_faq(data, biz),
    )
