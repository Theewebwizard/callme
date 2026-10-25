"""
Modular tool registry and tool implementations.

This package manages business-specific tools (e.g. appointment scheduling,
FAQ retrieval, caller intake) configured per tenant.
"""

from backend.tools import (
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
    ToolCategory,
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
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
