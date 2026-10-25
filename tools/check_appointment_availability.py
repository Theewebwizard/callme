"""
Check Appointment Availability Tool Functionality.
Standalone tool module for checking doctor, clinic, and professional consultation slots.
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


def handle_check_appointment_availability(
    input_data: CheckAppointmentAvailabilityInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Check appointment consultation slot availability for a clinical or service department.
    """
    opening = business_config.get("opening_time", "09:00")
    closing = business_config.get("closing_time", "19:00")
    biz_name = business_config.get("name", "Clinic")

    if input_data.preferred_time:
        if input_data.preferred_time < opening or input_data.preferred_time > closing:
            return ToolExecutionResult(
                tool_id="check_appointment_availability",
                status=ToolExecutionStatus.SUCCESS,
                success=False,
                mode=ToolExecutionMode.MOCK,
                data={
                    "available": False,
                    "reason": "outside_clinic_hours",
                    "opening_time": opening,
                    "closing_time": closing,
                },
                message=(
                    f"Requested consultation time ({input_data.preferred_time}) is outside of {biz_name}'s "
                    f"clinic hours ({opening} – {closing}). [SIMULATED MOCK AVAILABILITY]"
                ),
            )

    return ToolExecutionResult(
        tool_id="check_appointment_availability",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "available": True,
            "department": input_data.service_or_department,
            "date": input_data.preferred_date,
            "available_slots": ["10:00", "11:30", "14:15", "16:45"],
        },
        message=(
            f"Consultation slots are available for {input_data.service_or_department} on "
            f"{input_data.preferred_date} at {biz_name}. [SIMULATED MOCK AVAILABILITY - NOT LIVE CALENDAR]"
        ),
    )


def create_check_appointment_availability_tool_def() -> ToolDefinition:
    """Factory creating the canonical Check Appointment Availability ToolDefinition."""
    return ToolDefinition(
        id="check_appointment_availability",
        name="Check Appointment Availability",
        description="Check available slots for consultations, healthcare departments, or service visits.",
        category=ToolCategory.HEALTHCARE,
        allowed_industries=[
            "Clinic", "Doctor", "Healthcare & Services", "Hospital",
            "Dental", "Salon", "Spa", "Consulting / Services",
            "Astrology / Spiritual", "Legal",
        ],
        input_schema=CheckAppointmentAvailabilityInput,
        requires_confirmation=False,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_check_appointment_availability(data, biz),
    )
