"""
Healthcare and appointment scheduling tool handlers.
"""

from typing import Dict, Any
from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import (
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
)


def handle_check_appointment_availability(
    input_data: CheckAppointmentAvailabilityInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Check appointment consultation slot availability for a clinical service.
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
                    f"clinic hours ({opening} \u2013 {closing})."
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
            f"{input_data.preferred_date} at {biz_name}. Would you like to confirm this appointment?"
        ),
    )


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
            "status": "scheduled",
        },
        message=(
            f"Appointment confirmed for '{input_data.patient_name}' for {input_data.service_or_department} "
            f"on {input_data.appointment_date} at {input_data.appointment_time} with {biz_name}. "
            f"Appointment reference: {ref_code}."
        ),
    )
