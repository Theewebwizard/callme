"""
Information and FAQ tool implementations.
"""

from typing import Dict, Any
from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import AnswerFAQInput

STOP_WORDS = {
    "the", "and", "you", "are", "for", "can", "how", "what", "where",
    "when", "why", "who", "which", "with", "from", "that", "this",
    "our", "have", "your", "does", "about", "allow", "will", "there",
    "accept", "please",
}


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

        # 2. Meaningful keyword overlap (requires at least 2 common keywords or all keywords if short query)
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
