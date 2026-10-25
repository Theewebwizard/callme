"""
Backward-compatibility proxy re-exporting from standalone tools packages.
"""

from tools.answer_faq import (
    AnswerFAQInput,
    handle_answer_faq,
)

__all__ = [
    "AnswerFAQInput",
    "handle_answer_faq",
]
