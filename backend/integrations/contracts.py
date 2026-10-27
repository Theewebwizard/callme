"""
Provider-independent capability contracts: typed input schemas, typed result schemas,
side-effect classifications, permission requirements, timeouts, and retry policies.
"""

from typing import Dict, Any, Optional, List, Type
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from backend.integrations.models import (
    CapabilityType,
    SideEffectClassification,
    ErrorCategory,
)


# ============================================================================
# 1. Availability Contracts
# ============================================================================

class AvailabilitySlot(BaseModel):
    """An individual open slot for a resource, service, or table."""
    start_time: str
    end_time: str
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    capacity: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class CheckAvailabilityInput(BaseModel):
    """Input contract for checking schedule, table, or appointment availability."""
    start_time: str = Field(description="ISO 8601 start date-time or YYYY-MM-DDTHH:MM")
    end_time: Optional[str] = Field(default=None, description="ISO 8601 end date-time")
    party_size: int = Field(default=1, ge=1, le=50, description="Party or group size")
    resource_type: str = Field(default="table", description="Resource type: table, room, practitioner, calendar")
    service_id: Optional[str] = Field(default=None, description="Optional service catalog identifier")

    model_config = ConfigDict(extra="ignore")


class AvailabilityResult(BaseModel):
    """Provider-independent availability response."""
    available: bool
    slots: List[AvailabilitySlot] = Field(default_factory=list)
    total_slots_found: int = 0
    reason: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 2. Booking Contracts (Reservations & Appointments)
# ============================================================================

class CreateBookingInput(BaseModel):
    """Input contract for creating a confirmed reservation or clinical appointment."""
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=4, max_length=50)
    customer_email: Optional[str] = None
    start_time: str = Field(description="ISO 8601 start date-time")
    end_time: Optional[str] = Field(default=None, description="ISO 8601 end date-time")
    party_size: int = Field(default=1, ge=1, le=50)
    resource_id: Optional[str] = Field(default=None, description="Specific table/room identifier")
    special_requests: Optional[str] = None
    service_name: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class GetBookingInput(BaseModel):
    """Input contract for looking up an existing reservation."""
    booking_id: str
    customer_phone: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class RescheduleBookingInput(BaseModel):
    """Input contract for rescheduling an existing booking."""
    booking_id: str
    new_start_time: str
    new_end_time: Optional[str] = None
    customer_phone: Optional[str] = None
    reason: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CancelBookingInput(BaseModel):
    """Input contract for cancelling an existing booking."""
    booking_id: str
    customer_phone: Optional[str] = None
    reason: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class BookingResult(BaseModel):
    """Provider-independent reservation/appointment outcome."""
    booking_id: str
    status: str = "confirmed"  # "confirmed", "pending", "cancelled", "completed"
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    start_time: str
    end_time: str
    party_size: int = 1
    customer_name: str
    customer_phone: str
    confirmation_code: str
    special_requests: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class BookingCancellationResult(BaseModel):
    """Outcome of a cancellation request."""
    booking_id: str
    cancelled: bool
    status: str = "cancelled"
    message: str = "Booking successfully cancelled."

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 3. Calendar Event Contracts
# ============================================================================

class CreateCalendarEventInput(BaseModel):
    """Input contract for creating an event on an external calendar."""
    title: str = Field(min_length=1, max_length=200)
    start_time: str
    end_time: str
    attendee_email: Optional[str] = None
    description: Optional[str] = None
    calendar_id: Optional[str] = Field(default="primary")

    model_config = ConfigDict(extra="ignore")


class CalendarEventResult(BaseModel):
    """Provider-independent calendar event outcome."""
    event_id: str
    html_link: Optional[str] = None
    start_time: str
    end_time: str
    title: str
    status: str = "confirmed"

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 4. Customer & CRM Contracts
# ============================================================================

class GetCustomerInput(BaseModel):
    """Input contract for customer profile lookup."""
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_id: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CreateOrUpdateCustomerInput(BaseModel):
    """Input contract for creating or updating customer records in CRM."""
    name: str = Field(min_length=1, max_length=150)
    phone: Optional[str] = None
    email: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class CustomerResult(BaseModel):
    """Provider-independent customer record."""
    customer_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    created: bool = False
    properties: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 5. Messaging & Communication Contracts
# ============================================================================

class SendMessageInput(BaseModel):
    """Input contract for outbound SMS or WhatsApp message."""
    recipient_phone: str = Field(min_length=4, max_length=50)
    message_body: str = Field(min_length=1, max_length=1600)
    channel: str = Field(default="sms", description="'sms' or 'whatsapp'")
    media_url: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class SendEmailInput(BaseModel):
    """Input contract for outbound email dispatch."""
    recipient_email: str = Field(min_length=3, max_length=255)
    subject: str = Field(min_length=1, max_length=255)
    body_text: str = Field(min_length=1)
    body_html: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class MessageResult(BaseModel):
    """Provider-independent message dispatch outcome."""
    message_id: str
    status: str = "queued"  # "queued", "sent", "delivered", "failed"
    channel: str = "sms"
    recipient: str
    delivered_at: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class EmailResult(BaseModel):
    """Provider-independent email dispatch outcome."""
    email_id: str
    status: str = "queued"
    recipient: str

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 6. Telephony Contracts
# ============================================================================

class InitiateCallInput(BaseModel):
    """Input contract for placing an outbound voice call."""
    from_number: str
    to_number: str
    caller_id: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class TransferCallInput(BaseModel):
    """Input contract for transferring an active voice call."""
    session_id: str
    target_number: str
    reason: str
    timeout_seconds: int = Field(default=30, ge=5, le=120)

    model_config = ConfigDict(extra="ignore")


class GetCallStatusInput(BaseModel):
    """Input contract for inspecting a telephony call's live status."""
    call_id: str

    model_config = ConfigDict(extra="ignore")


class CallResult(BaseModel):
    """Provider-independent telephony call outcome."""
    call_id: str
    status: str = "in-progress"  # "ringing", "in-progress", "completed", "failed", "transferred"
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    transfer_target: Optional[str] = None
    duration_seconds: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 7. Customer Support Desk Contracts
# ============================================================================

class CreateSupportTicketInput(BaseModel):
    """Input contract for filing an escalation ticket with customer support."""
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requester_name: str
    requester_email: Optional[str] = None
    requester_phone: Optional[str] = None
    priority: str = Field(default="normal", description="'low', 'normal', 'high', 'urgent'")

    model_config = ConfigDict(extra="ignore")


class SupportTicketResult(BaseModel):
    """Provider-independent support ticket outcome."""
    ticket_id: str
    status: str = "open"  # "open", "pending", "resolved", "closed"
    subject: str
    url: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# 8. Payments Contracts
# ============================================================================

class CreatePaymentRequestInput(BaseModel):
    """Input contract for generating a payment link or charge invoice."""
    amount_cents: int = Field(gt=0, description="Amount in minor units (e.g. cents, paise)")
    currency: str = Field(default="usd", min_length=3, max_length=3)
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    description: str = Field(default="Service Payment")
    due_in_minutes: int = Field(default=60, ge=5, le=1440)

    model_config = ConfigDict(extra="ignore")


class GetPaymentStatusInput(BaseModel):
    """Input contract for authoritative payment status verification."""
    payment_id: str

    model_config = ConfigDict(extra="ignore")


class PaymentResult(BaseModel):
    """Provider-independent payment outcome."""
    payment_id: str
    status: str = "pending"  # "pending", "succeeded", "failed", "expired"
    amount_cents: int
    currency: str
    payment_url: Optional[str] = None
    paid_at: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# Operation Contract Metadata Structure
# ============================================================================

class OperationContract(BaseModel):
    """Metadata specification governing operation constraints, retries, and permissions."""
    operation: CapabilityType
    input_schema: Type[BaseModel]
    result_schema: Type[BaseModel]
    side_effect: SideEffectClassification
    required_permission: str
    default_timeout_seconds: float = 8.0
    max_retries: int = 2
    retryable_error_codes: List[str] = Field(default_factory=lambda: [
        ErrorCategory.RATE_LIMITED.value,
        ErrorCategory.TIMEOUT.value,
        ErrorCategory.PROVIDER_UNAVAILABLE.value,
    ])
    requires_idempotency: bool = False

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)


CAPABILITY_CONTRACTS: Dict[CapabilityType, OperationContract] = {
    CapabilityType.CHECK_AVAILABILITY: OperationContract(
        operation=CapabilityType.CHECK_AVAILABILITY,
        input_schema=CheckAvailabilityInput,
        result_schema=AvailabilityResult,
        side_effect=SideEffectClassification.READ_ONLY,
        required_permission="bookings:read",
        default_timeout_seconds=5.0,
        max_retries=2,
        requires_idempotency=False,
    ),
    CapabilityType.CREATE_BOOKING: OperationContract(
        operation=CapabilityType.CREATE_BOOKING,
        input_schema=CreateBookingInput,
        result_schema=BookingResult,
        side_effect=SideEffectClassification.NON_IDEMPOTENT_WRITE,
        required_permission="bookings:write",
        default_timeout_seconds=10.0,
        max_retries=0,  # Blind retry forbidden without idempotency check
        requires_idempotency=True,
    ),
    CapabilityType.GET_BOOKING: OperationContract(
        operation=CapabilityType.GET_BOOKING,
        input_schema=GetBookingInput,
        result_schema=BookingResult,
        side_effect=SideEffectClassification.READ_ONLY,
        required_permission="bookings:read",
        default_timeout_seconds=5.0,
        max_retries=2,
        requires_idempotency=False,
    ),
    CapabilityType.RESCHEDULE_BOOKING: OperationContract(
        operation=CapabilityType.RESCHEDULE_BOOKING,
        input_schema=RescheduleBookingInput,
        result_schema=BookingResult,
        side_effect=SideEffectClassification.NON_IDEMPOTENT_WRITE,
        required_permission="bookings:write",
        default_timeout_seconds=8.0,
        max_retries=0,
        requires_idempotency=True,
    ),
    CapabilityType.CANCEL_BOOKING: OperationContract(
        operation=CapabilityType.CANCEL_BOOKING,
        input_schema=CancelBookingInput,
        result_schema=BookingCancellationResult,
        side_effect=SideEffectClassification.IDEMPOTENT_WRITE,
        required_permission="bookings:write",
        default_timeout_seconds=8.0,
        max_retries=2,
        requires_idempotency=True,
    ),
    CapabilityType.CREATE_CALENDAR_EVENT: OperationContract(
        operation=CapabilityType.CREATE_CALENDAR_EVENT,
        input_schema=CreateCalendarEventInput,
        result_schema=CalendarEventResult,
        side_effect=SideEffectClassification.NON_IDEMPOTENT_WRITE,
        required_permission="calendar:write",
        default_timeout_seconds=8.0,
        max_retries=0,
        requires_idempotency=True,
    ),
    CapabilityType.GET_CUSTOMER: OperationContract(
        operation=CapabilityType.GET_CUSTOMER,
        input_schema=GetCustomerInput,
        result_schema=CustomerResult,
        side_effect=SideEffectClassification.READ_ONLY,
        required_permission="customers:read",
        default_timeout_seconds=5.0,
        max_retries=2,
        requires_idempotency=False,
    ),
    CapabilityType.CREATE_OR_UPDATE_CUSTOMER: OperationContract(
        operation=CapabilityType.CREATE_OR_UPDATE_CUSTOMER,
        input_schema=CreateOrUpdateCustomerInput,
        result_schema=CustomerResult,
        side_effect=SideEffectClassification.IDEMPOTENT_WRITE,
        required_permission="customers:write",
        default_timeout_seconds=8.0,
        max_retries=2,
        requires_idempotency=True,
    ),
    CapabilityType.SEND_MESSAGE: OperationContract(
        operation=CapabilityType.SEND_MESSAGE,
        input_schema=SendMessageInput,
        result_schema=MessageResult,
        side_effect=SideEffectClassification.NON_IDEMPOTENT_WRITE,
        required_permission="messaging:send",
        default_timeout_seconds=6.0,
        max_retries=1,
        requires_idempotency=True,
    ),
    CapabilityType.SEND_EMAIL: OperationContract(
        operation=CapabilityType.SEND_EMAIL,
        input_schema=SendEmailInput,
        result_schema=EmailResult,
        side_effect=SideEffectClassification.NON_IDEMPOTENT_WRITE,
        required_permission="messaging:send",
        default_timeout_seconds=8.0,
        max_retries=1,
        requires_idempotency=True,
    ),
    CapabilityType.INITIATE_CALL: OperationContract(
        operation=CapabilityType.INITIATE_CALL,
        input_schema=InitiateCallInput,
        result_schema=CallResult,
        side_effect=SideEffectClassification.ESCALATION,
        required_permission="telephony:call",
        default_timeout_seconds=10.0,
        max_retries=0,
        requires_idempotency=True,
    ),
    CapabilityType.TRANSFER_CALL: OperationContract(
        operation=CapabilityType.TRANSFER_CALL,
        input_schema=TransferCallInput,
        result_schema=CallResult,
        side_effect=SideEffectClassification.ESCALATION,
        required_permission="telephony:call",
        default_timeout_seconds=15.0,
        max_retries=0,
        requires_idempotency=True,
    ),
    CapabilityType.GET_CALL_STATUS: OperationContract(
        operation=CapabilityType.GET_CALL_STATUS,
        input_schema=GetCallStatusInput,
        result_schema=CallResult,
        side_effect=SideEffectClassification.READ_ONLY,
        required_permission="telephony:call",
        default_timeout_seconds=5.0,
        max_retries=2,
        requires_idempotency=False,
    ),
    CapabilityType.CREATE_SUPPORT_TICKET: OperationContract(
        operation=CapabilityType.CREATE_SUPPORT_TICKET,
        input_schema=CreateSupportTicketInput,
        result_schema=SupportTicketResult,
        side_effect=SideEffectClassification.NON_IDEMPOTENT_WRITE,
        required_permission="support:write",
        default_timeout_seconds=8.0,
        max_retries=1,
        requires_idempotency=True,
    ),
    CapabilityType.GET_PAYMENT_STATUS: OperationContract(
        operation=CapabilityType.GET_PAYMENT_STATUS,
        input_schema=GetPaymentStatusInput,
        result_schema=PaymentResult,
        side_effect=SideEffectClassification.READ_ONLY,
        required_permission="payments:read",
        default_timeout_seconds=5.0,
        max_retries=2,
        requires_idempotency=False,
    ),
    CapabilityType.CREATE_PAYMENT_REQUEST: OperationContract(
        operation=CapabilityType.CREATE_PAYMENT_REQUEST,
        input_schema=CreatePaymentRequestInput,
        result_schema=PaymentResult,
        side_effect=SideEffectClassification.FINANCIAL,
        required_permission="payments:write",
        default_timeout_seconds=10.0,
        max_retries=0,
        requires_idempotency=True,
    ),
}
