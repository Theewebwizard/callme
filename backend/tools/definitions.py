"""
Pydantic input models and schema definitions for the receptionist tool catalogue.
Enforces strict type safety, boundary validation, and rejection of dangerous inputs.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class AnswerFAQInput(BaseModel):
    """Input payload for looking up business FAQs."""
    question: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Customer question or inquiry keyword to match against configured FAQs.",
    )

    model_config = ConfigDict(extra="forbid")


class CheckTableAvailabilityInput(BaseModel):
    """Input payload for inspecting dining table availability."""
    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Target dining date in YYYY-MM-DD format.",
    )
    time: str = Field(
        ...,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Requested dining time in 24-hour HH:MM format.",
    )
    party_size: int = Field(
        ...,
        ge=1,
        le=20,
        description="Number of dining guests (1 to 20).",
    )

    model_config = ConfigDict(extra="forbid")


class CreateTableBookingInput(BaseModel):
    """Input payload for reserving a table."""
    customer_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full name of primary dining contact.",
    )
    customer_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Contact telephone number for SMS/call confirmation.",
    )
    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Reservation date in YYYY-MM-DD format.",
    )
    time: str = Field(
        ...,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Reservation time in 24-hour HH:MM format.",
    )
    party_size: int = Field(
        ...,
        ge=1,
        le=20,
        description="Number of dining guests (1 to 20).",
    )
    special_requests: Optional[str] = Field(
        None,
        max_length=300,
        description="Dietary requirements or seating preferences (e.g. outdoor, high chair).",
    )

    model_config = ConfigDict(extra="forbid")


class CheckAppointmentAvailabilityInput(BaseModel):
    """Input payload for checking medical, dental, or clinical consultation slots."""
    service_or_department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Medical/dental specialty or practitioner requested.",
    )
    preferred_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Requested appointment date in YYYY-MM-DD format.",
    )
    preferred_time: Optional[str] = Field(
        None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Preferred consultation time in 24-hour HH:MM format.",
    )

    model_config = ConfigDict(extra="forbid")


class CreateAppointmentInput(BaseModel):
    """Input payload for creating a patient or client appointment."""
    patient_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full legal name of the patient.",
    )
    patient_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Patient contact telephone number.",
    )
    service_or_department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Clinical department, treatment, or practitioner.",
    )
    appointment_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Confirmed appointment date in YYYY-MM-DD format.",
    )
    appointment_time: str = Field(
        ...,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Confirmed appointment time in 24-hour HH:MM format.",
    )
    notes: Optional[str] = Field(
        None,
        max_length=300,
        description="Clinical symptoms or visit background.",
    )

    model_config = ConfigDict(extra="forbid")


class TakeMessageInput(BaseModel):
    """Input payload for capturing caller callback details and messages."""
    caller_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full name of caller.",
    )
    caller_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Callback contact telephone number.",
    )
    message: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Detailed message content to deliver to business staff.",
    )
    urgency: str = Field(
        "normal",
        pattern=r"^(low|normal|urgent)$",
        description="Callback priority: 'low', 'normal', or 'urgent'.",
    )

    model_config = ConfigDict(extra="forbid")


class TransferCallInput(BaseModel):
    """Input payload for requesting a human operator or line transfer."""
    reason: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Reason caller is requesting human escalation.",
    )
    department_or_target: Optional[str] = Field(
        None,
        max_length=100,
        description="Specific staff member, department, or desk requested.",
    )

    model_config = ConfigDict(extra="forbid")
