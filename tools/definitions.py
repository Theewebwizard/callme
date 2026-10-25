"""
Canonical Schema Definitions and Tool Catalogs.
Aggregates the individual tool schemas from their separate implementation files.
"""

from typing import List
from tools.base import ToolDefinition
from tools.answer_faq import AnswerFAQInput, create_answer_faq_tool_def
from tools.check_table_availability import (
    CheckTableAvailabilityInput,
    create_check_table_availability_tool_def,
)
from tools.create_table_booking import (
    CreateTableBookingInput,
    create_create_table_booking_tool_def,
)
from tools.check_appointment_availability import (
    CheckAppointmentAvailabilityInput,
    create_check_appointment_availability_tool_def,
)
from tools.create_appointment import (
    CreateAppointmentInput,
    create_create_appointment_tool_def,
)
from tools.take_message import TakeMessageInput, create_take_message_tool_def
from tools.transfer_call import TransferCallInput, create_transfer_call_tool_def

# Canonical static tool definition singletons
ANSWER_FAQ_TOOL: ToolDefinition = create_answer_faq_tool_def()
CHECK_TABLE_AVAILABILITY_TOOL: ToolDefinition = create_check_table_availability_tool_def()
CREATE_TABLE_BOOKING_TOOL: ToolDefinition = create_create_table_booking_tool_def()
CHECK_APPOINTMENT_AVAILABILITY_TOOL: ToolDefinition = create_check_appointment_availability_tool_def()
CREATE_APPOINTMENT_TOOL: ToolDefinition = create_create_appointment_tool_def()
TAKE_MESSAGE_TOOL: ToolDefinition = create_take_message_tool_def()
TRANSFER_CALL_TOOL: ToolDefinition = create_transfer_call_tool_def()

CANONICAL_TOOLS: List[ToolDefinition] = [
    ANSWER_FAQ_TOOL,
    CHECK_TABLE_AVAILABILITY_TOOL,
    CREATE_TABLE_BOOKING_TOOL,
    CHECK_APPOINTMENT_AVAILABILITY_TOOL,
    CREATE_APPOINTMENT_TOOL,
    TAKE_MESSAGE_TOOL,
    TRANSFER_CALL_TOOL,
]

__all__ = [
    "AnswerFAQInput",
    "CheckTableAvailabilityInput",
    "CreateTableBookingInput",
    "CheckAppointmentAvailabilityInput",
    "CreateAppointmentInput",
    "TakeMessageInput",
    "TransferCallInput",
    "ANSWER_FAQ_TOOL",
    "CHECK_TABLE_AVAILABILITY_TOOL",
    "CREATE_TABLE_BOOKING_TOOL",
    "CHECK_APPOINTMENT_AVAILABILITY_TOOL",
    "CREATE_APPOINTMENT_TOOL",
    "TAKE_MESSAGE_TOOL",
    "TRANSFER_CALL_TOOL",
    "CANONICAL_TOOLS",
]
