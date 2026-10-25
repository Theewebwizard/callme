"""
Standalone Modular AI Receptionist Tools Package.

Provides isolated, tenant-aware tools with separate code files for each tool functionality:
  - tools/answer_faq.py
  - tools/check_table_availability.py
  - tools/create_table_booking.py
  - tools/check_appointment_availability.py
  - tools/create_appointment.py
  - tools/take_message.py
  - tools/transfer_call.py
"""

from tools.base import (
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
    ToolCategory,
)
from tools.definitions import (
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
    CANONICAL_TOOLS,
    ANSWER_FAQ_TOOL,
    CHECK_TABLE_AVAILABILITY_TOOL,
    CREATE_TABLE_BOOKING_TOOL,
    CHECK_APPOINTMENT_AVAILABILITY_TOOL,
    CREATE_APPOINTMENT_TOOL,
    TAKE_MESSAGE_TOOL,
    TRANSFER_CALL_TOOL,
)
from tools.registry import (
    ToolRegistry,
    build_default_tool_registry,
    get_tool_registry,
)

# Individual Tool Implementations
from tools.answer_faq import handle_answer_faq
from tools.check_table_availability import handle_check_table_availability
from tools.create_table_booking import handle_create_table_booking
from tools.check_appointment_availability import handle_check_appointment_availability
from tools.create_appointment import handle_create_appointment
from tools.take_message import handle_take_message
from tools.transfer_call import handle_transfer_call

__all__ = [
    # Base Abstractions
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "ToolExecutionMode",
    "ToolCategory",
    # Input Models
    "AnswerFAQInput",
    "CheckTableAvailabilityInput",
    "CreateTableBookingInput",
    "CheckAppointmentAvailabilityInput",
    "CreateAppointmentInput",
    "TakeMessageInput",
    "TransferCallInput",
    # Canonical Tools
    "CANONICAL_TOOLS",
    "ANSWER_FAQ_TOOL",
    "CHECK_TABLE_AVAILABILITY_TOOL",
    "CREATE_TABLE_BOOKING_TOOL",
    "CHECK_APPOINTMENT_AVAILABILITY_TOOL",
    "CREATE_APPOINTMENT_TOOL",
    "TAKE_MESSAGE_TOOL",
    "TRANSFER_CALL_TOOL",
    # Registry & Services
    "ToolRegistry",
    "build_default_tool_registry",
    "get_tool_registry",
    # Handlers
    "handle_answer_faq",
    "handle_check_table_availability",
    "handle_create_table_booking",
    "handle_check_appointment_availability",
    "handle_create_appointment",
    "handle_take_message",
    "handle_transfer_call",
]
