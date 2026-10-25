"""
Backward-compatibility proxy re-exporting from the standalone 'tools.definitions' package.
"""

from tools.definitions import (
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
    ANSWER_FAQ_TOOL,
    CHECK_TABLE_AVAILABILITY_TOOL,
    CREATE_TABLE_BOOKING_TOOL,
    CHECK_APPOINTMENT_AVAILABILITY_TOOL,
    CREATE_APPOINTMENT_TOOL,
    TAKE_MESSAGE_TOOL,
    TRANSFER_CALL_TOOL,
    CANONICAL_TOOLS,
)

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
