"""
Create Appointment Booking Tool Functionality.
Standalone tool module for scheduling patient, client, and consultation appointments.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from tools.base import (
    ToolDefinition,
    ToolCategory,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)


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


def handle_create_appointment(
    input_data: CreateAppointmentInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Simulate scheduling a patient appointment after confirmation validation.
    """
    ref_seed = f"{input_data.patient_name}{input_data.appointment_date}{input_data.appointment_time}"
    ref_code = f"APT-{abs(hash(ref_seed)) % 10000:04d}"
    biz_name = business_config.get("name", "Clinic")

    return ToolExecutionResult(
        tool_id="create_appointment",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "appointment_reference": ref_code,
            "business_id": business_config.get("id"),
            "patient_name": input_data.patient_name,
            "patient_phone": input_data.patient_phone,
            "service_or_department": input_data.service_or_department,
            "appointment_date": input_data.appointment_date,
            "appointment_time": input_data.appointment_time,
            "notes": input_data.notes,
            "status": "simulated_scheduled",
        },
        message=(
            f"Appointment simulated for '{input_data.patient_name}' ({input_data.service_or_department}) "
            f"on {input_data.appointment_date} at {input_data.appointment_time} at {biz_name} "
            f"(Reference: {ref_code}). [SIMULATED MOCK APPOINTMENT - NOT A REAL APPOINTMENT]"
        ),
    )


def create_create_appointment_tool_def() -> ToolDefinition:
    """Factory creating the canonical Create Appointment ToolDefinition."""
    return ToolDefinition(
        id="create_appointment",
        name="Create Appointment",
        description="Simulate booking an appointment. Requires explicit user confirmation before execution.",
        category=ToolCategory.HEALTHCARE,
        allowed_industries=[
            "Clinic", "Doctor", "Healthcare & Services", "Hospital",
            "Dental", "Salon", "Spa", "Consulting / Services",
            "Astrology / Spiritual", "Legal",
        ],
        input_schema=CreateAppointmentInput,
        requires_confirmation=True,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_create_appointment(data, biz),
    )
