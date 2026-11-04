"""
Healthcare and appointment scheduling tool handlers.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional
from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import (
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    QueryTreatmentPricingInput,
)

logger = logging.getLogger(__name__)


def handle_check_appointment_availability(
    input_data: CheckAppointmentAvailabilityInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Check appointment consultation slot availability for a clinical service.
    Executes authoritative adapter when in live mode; provides truthful simulation in mock mode.
    """
    opening = business_config.get("opening_time", "09:00")
    closing = business_config.get("closing_time", "19:00")
    biz_name = business_config.get("name", "Clinic")
    biz_id = business_config.get("id", "")

    if input_data.preferred_time:
        if input_data.preferred_time < opening or input_data.preferred_time > closing:
            return ToolExecutionResult(
                tool_id="check_appointment_availability",
                status=ToolExecutionStatus.BUSINESS_DECLINED,
                success=True,
                is_business_accepted=False,
                is_simulated=(business_config.get("execution_mode") != "live"),
                mode=ToolExecutionMode.LIVE if business_config.get("execution_mode") == "live" else ToolExecutionMode.MOCK,
                data={
                    "available": False,
                    "reason": "outside_clinic_hours",
                    "opening_time": opening,
                    "closing_time": closing,
                    "is_simulated": (business_config.get("execution_mode") != "live"),
                },
                message=(
                    f"Requested consultation time ({input_data.preferred_time}) is outside of {biz_name}'s "
                    f"clinic hours ({opening} \u2013 {closing})."
                ),
            )

    # Live Mode Execution via Authoritative Integration Adapter
    if business_config.get("execution_mode") == "live":
        try:
            from datetime import datetime, timedelta
            from backend.integrations.resolver import resolve_tool_adapter

            adapter = resolve_tool_adapter(biz_id, "check_appointment_availability")
            req_time = input_data.preferred_time or "10:00"
            start_dt = datetime.fromisoformat(f"{input_data.preferred_date}T{req_time}:00")
            duration_mins = int(business_config.get("consultation_duration_minutes", 30))
            end_dt = start_dt + timedelta(minutes=duration_mins)

            avail_res = adapter.check_availability(
                start_time=start_dt,
                end_time=end_dt,
                party_size=1,
                resource_type="room",
            )

            if avail_res.get("available"):
                return ToolExecutionResult(
                    tool_id="check_appointment_availability",
                    status=ToolExecutionStatus.SUCCESS,
                    success=True,
                    is_business_accepted=True,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=avail_res,
                    message=(
                        f"Consultation slots are available for {input_data.service_or_department} on "
                        f"{input_data.preferred_date} at {req_time} with {biz_name}."
                    ),
                )
            else:
                return ToolExecutionResult(
                    tool_id="check_appointment_availability",
                    status=ToolExecutionStatus.BUSINESS_DECLINED,
                    success=True,
                    is_business_accepted=False,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=avail_res,
                    message=(
                        f"No clinical consultation slots are currently available for {input_data.service_or_department} on "
                        f"{input_data.preferred_date} at {req_time} at {biz_name}."
                    ),
                )
        except Exception:
            return ToolExecutionResult(
                tool_id="check_appointment_availability",
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="ADAPTER_EXECUTION_ERROR",
                message="Unable to verify live appointment availability at this moment.",
            )

    # Deterministic mock availability
    return ToolExecutionResult(
        tool_id="check_appointment_availability",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "available": True,
            "department": input_data.service_or_department,
            "date": input_data.preferred_date,
            "availability_type": "simulated_schedule",
            "available_slots": ["10:00", "11:30", "14:15", "16:45"],
            "is_simulated": True,
        },
        message=(
            f"[Development Simulation] Consultation slots are available in simulated schedule for {input_data.service_or_department} on "
            f"{input_data.preferred_date} at {biz_name}. Note: Live practitioner scheduling is not connected."
        ),
    )


def handle_create_appointment(
    input_data: CreateAppointmentInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Schedule an appointment.
    Executes authoritative integration adapter in live mode; simulates in mock mode.
    """
    biz_name = business_config.get("name", "Clinic")
    biz_id = business_config.get("id", "")

    # Live Mode Execution via Authoritative Integration Adapter
    if business_config.get("execution_mode") == "live":
        try:
            from datetime import datetime, timedelta
            from backend.integrations.resolver import resolve_tool_adapter
            from backend.database.repositories.reservation_repo import ReservationConflictError

            adapter = resolve_tool_adapter(biz_id, "create_appointment")
            start_dt = datetime.fromisoformat(f"{input_data.appointment_date}T{input_data.appointment_time}:00")
            duration_mins = int(business_config.get("consultation_duration_minutes", 30))
            end_dt = start_dt + timedelta(minutes=duration_mins)

            spec_req = f"Department: {input_data.service_or_department}. Notes: {input_data.notes or 'None'}"
            booking_res = adapter.create_reservation(
                customer_name=input_data.patient_name,
                customer_phone=input_data.patient_phone,
                party_size=1,
                start_time=start_dt,
                end_time=end_dt,
                special_requests=spec_req,
                idempotency_key=input_data.idempotency_key,
            )

            if not booking_res.get("success", True) or booking_res.get("status") == "failed":
                return ToolExecutionResult(
                    tool_id="create_appointment",
                    status=ToolExecutionStatus.ERROR,
                    success=False,
                    is_business_accepted=False,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    error_code="APPOINTMENT_FAILED",
                    data=booking_res,
                    message=booking_res.get("message") or f"Unable to confirm appointment with authoritative provider ({booking_res.get('authoritative_source', 'external')}).",
                )

            ref_code = booking_res.get("appointment_reference", booking_res.get("booking_reference"))
            room_name = booking_res.get("room_name", "Clinical Consultation Suite")

            return ToolExecutionResult(
                tool_id="create_appointment",
                status=ToolExecutionStatus.SUCCESS,
                success=True,
                is_business_accepted=True,
                is_simulated=False,
                mode=ToolExecutionMode.LIVE,
                data=booking_res,
                message=(
                    f"Appointment confirmed for '{input_data.patient_name}' for {input_data.service_or_department} "
                    f"on {input_data.appointment_date} at {input_data.appointment_time} with {biz_name} "
                    f"({room_name}). Reference: {ref_code}."
                ),
            )
        except ReservationConflictError:
            return ToolExecutionResult(
                tool_id="create_appointment",
                status=ToolExecutionStatus.BUSINESS_DECLINED,
                success=True,
                is_business_accepted=False,
                is_simulated=False,
                mode=ToolExecutionMode.LIVE,
                data={"available": False, "reason": "conflict"},
                message="The requested clinical appointment time is no longer available due to a scheduling conflict. Please select another slot.",
            )
        except Exception:
            return ToolExecutionResult(
                tool_id="create_appointment",
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="APPOINTMENT_FAILED",
                message="Unable to schedule clinical consultation. Please try again or contact staff directly.",
            )

    # Simulated Mock Execution
    ref_code = f"APT-{uuid.uuid4().hex[:8].upper()}"
    return ToolExecutionResult(
        tool_id="create_appointment",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "appointment_reference": ref_code,
            "business_id": biz_id,
            "patient_name": input_data.patient_name,
            "patient_phone": input_data.patient_phone,
            "service_or_department": input_data.service_or_department,
            "appointment_date": input_data.appointment_date,
            "appointment_time": input_data.appointment_time,
            "notes": input_data.notes,
            "status": "simulated_appointment",
            "is_simulated": True,
        },
        message=(
            f"[Development Simulation] Appointment confirmed for '{input_data.patient_name}' for {input_data.service_or_department} "
            f"on {input_data.appointment_date} at {input_data.appointment_time} with {biz_name}. "
            f"Appointment reference: {ref_code}. This appointment is simulated in development mode and is not scheduled in a live medical system."
        ),
    )


def format_appointment_summary(args: Dict[str, Any]) -> str:
    """Format human-readable summary of a clinical appointment for confirmation."""
    notes = f"\n• Notes: {args['notes']}" if args.get("notes") else ""
    return (
        f"• Action: Clinical Consultation Appointment\n"
        f"• Patient: {args.get('patient_name')} ({args.get('patient_phone')})\n"
        f"• Service / Department: {args.get('service_or_department')}\n"
        f"• Date & Time: {args.get('appointment_date')} at {args.get('appointment_time')}"
        f"{notes}"
    )

def handle_query_treatment_pricing(
    input_data: QueryTreatmentPricingInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Search clinic treatment fee catalog, consultation charges, doctor specializations,
    procedure durations, and patient preparation notes.
    """
    biz_id = business_config.get("id", "")
    biz_name = business_config.get("name", "our clinic")
    raw_mode = business_config.get("execution_mode", "mock")
    is_live = (str(raw_mode).lower() == "live")
    exec_mode = ToolExecutionMode.LIVE if is_live else ToolExecutionMode.MOCK

    query = input_data.query.strip()
    category = input_data.category.strip() if input_data.category else None
    practitioner_type = input_data.practitioner_type.strip() if input_data.practitioner_type else None
    max_budget = input_data.max_budget

    matching_treatments: List[Dict[str, Any]] = []

    # 1. Authoritative query via DatabaseService
    try:
        from backend.database.service import get_database_service
        db_service = get_database_service()
        if db_service and biz_id:
            matching_treatments = db_service.search_treatments_semantic(
                business_id=biz_id,
                query=query,
                category=category,
                practitioner_type=practitioner_type,
                max_budget=max_budget,
                limit=6,
            )
    except Exception as exc:
        logger.warning("Database search failed in handle_query_treatment_pricing: %s", exc)

    # 2. In-memory fallback if DB returned empty and treatments were supplied in business_config
    if not matching_treatments and "treatments" in business_config and business_config["treatments"]:
        from backend.database.repositories.treatment_repo import rank_treatments_semantic
        matching_treatments = rank_treatments_semantic(
            treatments=business_config["treatments"],
            query=query,
            category=category,
            practitioner_type=practitioner_type,
            max_budget=max_budget,
            limit=6,
        )

    # 3. Assemble response
    if not matching_treatments:
        budget_str = f" under ₹{int(max_budget)}" if max_budget else ""
        spec_str = f" with {practitioner_type}" if practitioner_type else ""
        return ToolExecutionResult(
            tool_id="query_treatment_pricing",
            status=ToolExecutionStatus.SUCCESS,
            success=True,
            is_business_accepted=True,
            mode=exec_mode,
            is_simulated=(not is_live),
            data={
                "found": False,
                "count": 0,
                "query": query,
                "treatments": [],
            },
            message=(
                f"We currently do not have any treatments or procedures matching '{query}'{spec_str}{budget_str} "
                f"at {biz_name}. Would you like me to check our other clinical services or book a general consultation with our doctor?"
            ),
        )

    lines = [f"Here are the matching treatments and consultation fees at {biz_name}:"]
    currency_symbol = matching_treatments[0].get("currency", "INR")
    curr_prefix = "₹" if currency_symbol in ("INR", "₹") else f"{currency_symbol} "

    for t in matching_treatments:
        p_base = t.get("base_fee", 0.0)
        p_max = t.get("fee_range_max", p_base)
        if p_max and p_max > p_base:
            fee_str = f"{curr_prefix}{int(p_base)} - {curr_prefix}{int(p_max)}"
        else:
            fee_str = f"{curr_prefix}{int(p_base)}" if p_base == int(p_base) else f"{curr_prefix}{p_base:.2f}"

        name = t.get("name", "Treatment")
        duration = t.get("duration_minutes", 30)
        doctor = t.get("practitioner_type") or "Doctor / Specialist"
        prep = t.get("preparation_instructions")
        prep_str = f" [Prep: {prep}]" if prep else ""

        lines.append(f"• {name} - {fee_str} (~{duration} mins, {doctor}){prep_str}")

    summary_text = "\n".join(lines)
    return ToolExecutionResult(
        tool_id="query_treatment_pricing",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        mode=exec_mode,
        is_simulated=(not is_live),
        data={
            "found": True,
            "count": len(matching_treatments),
            "query": query,
            "treatments": matching_treatments,
        },
        message=summary_text,
    )

