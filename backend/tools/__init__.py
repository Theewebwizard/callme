"""
Modular Tool Registry and definitions for the AI Receptionist Platform.
"""

from backend.tools.base import (
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
    ToolCategory,
)
from backend.tools.definitions import (
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
)
from backend.tools.registry import (
    ToolRegistry,
    build_default_tool_registry,
    get_tool_registry,
)

__all__ = [
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "ToolExecutionMode",
    "ToolCategory",
    "AnswerFAQInput",
    "CheckTableAvailabilityInput",
    "CreateTableBookingInput",
    "CheckAppointmentAvailabilityInput",
    "CreateAppointmentInput",
    "TakeMessageInput",
    "TransferCallInput",
    "ToolRegistry",
    "build_default_tool_registry",
    "get_tool_registry",
]
