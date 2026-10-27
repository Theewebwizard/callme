"""
Dining and table management tool handlers.
"""

import uuid
from typing import Dict, Any
from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import (
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
)


def handle_check_table_availability(
    input_data: CheckTableAvailabilityInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Check dining table availability for a given date, time, and party size.
    Executes authoritative adapter when in live mode; provides truthful simulation in mock mode.
    """
    opening = business_config.get("opening_time", "11:00")
    closing = business_config.get("closing_time", "23:00")
    biz_name = business_config.get("name", "Restaurant")
    biz_id = business_config.get("id", "")

    # Time window check (HH:MM string comparison works for standard 24h format)
    if input_data.time < opening or input_data.time > closing:
        return ToolExecutionResult(
            tool_id="check_table_availability",
            status=ToolExecutionStatus.BUSINESS_DECLINED,
            success=True,
            is_business_accepted=False,
            is_simulated=(business_config.get("execution_mode") != "live"),
            mode=ToolExecutionMode.LIVE if business_config.get("execution_mode") == "live" else ToolExecutionMode.MOCK,
            data={
                "available": False,
                "reason": "outside_operating_hours",
                "opening_time": opening,
                "closing_time": closing,
                "is_simulated": (business_config.get("execution_mode") != "live"),
            },
            message=(
                f"Requested dining time ({input_data.time}) is outside of {biz_name}'s "
                f"operating hours ({opening} \u2013 {closing})."
            ),
        )

    # Party size rule
    if input_data.party_size > 10:
        return ToolExecutionResult(
            tool_id="check_table_availability",
            status=ToolExecutionStatus.BUSINESS_DECLINED,
            success=True,
            is_business_accepted=False,
            is_simulated=(business_config.get("execution_mode") != "live"),
            mode=ToolExecutionMode.LIVE if business_config.get("execution_mode") == "live" else ToolExecutionMode.MOCK,
            data={
                "available": False,
                "reason": "party_size_exceeds_automated_booking",
                "party_size": input_data.party_size,
                "is_simulated": (business_config.get("execution_mode") != "live"),
            },
            message=(
                f"Parties larger than 10 guests ({input_data.party_size} requested) require "
                f"direct arrangement with the events manager at {business_config.get('phone_number', 'our front desk')}."
            ),
        )

    # Live Mode Execution via Authoritative Integration Adapter
    if business_config.get("execution_mode") == "live":
        try:
            from datetime import datetime, timedelta
            from backend.integrations.resolver import resolve_tool_adapter

            adapter = resolve_tool_adapter(biz_id, "check_table_availability")
            start_dt = datetime.fromisoformat(f"{input_data.date}T{input_data.time}:00")
            duration_mins = int(business_config.get("reservation_duration_minutes", 90))
            end_dt = start_dt + timedelta(minutes=duration_mins)

            avail_res = adapter.check_availability(
                start_time=start_dt,
                end_time=end_dt,
                party_size=input_data.party_size,
                resource_type="table",
            )

            if avail_res.get("available"):
                return ToolExecutionResult(
                    tool_id="check_table_availability",
                    status=ToolExecutionStatus.SUCCESS,
                    success=True,
                    is_business_accepted=True,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=avail_res,
                    message=(
                        f"Tables are available for a party of {input_data.party_size} on {input_data.date} "
                        f"at {input_data.time} at {biz_name}."
                    ),
                )
            else:
                return ToolExecutionResult(
                    tool_id="check_table_availability",
                    status=ToolExecutionStatus.BUSINESS_DECLINED,
                    success=True,
                    is_business_accepted=False,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=avail_res,
                    message=(
                        f"No tables are currently available for a party of {input_data.party_size} on {input_data.date} "
                        f"at {input_data.time} at {biz_name}."
                    ),
                )
        except Exception as exc:
            return ToolExecutionResult(
                tool_id="check_table_availability",
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="ADAPTER_EXECUTION_ERROR",
                message="Unable to verify live table availability at this moment.",
            )

    # Deterministic mock availability
    return ToolExecutionResult(
        tool_id="check_table_availability",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "available": True,
            "date": input_data.date,
            "requested_time": input_data.time,
            "party_size": input_data.party_size,
            "availability_type": "simulated_schedule",
            "seating_options": ["Indoor Dining Room", "Window Table", "Outdoor Terrace"],
            "mock_slots": [input_data.time, "15 mins before", "15 mins after"],
            "is_simulated": True,
        },
        message=(
            f"[Development Simulation] Tables are available in simulated schedule for a party of {input_data.party_size} on {input_data.date} "
            f"around {input_data.time} at {biz_name}. Note: live table inventory integration is not connected."
        ),
    )


def handle_create_table_booking(
    input_data: CreateTableBookingInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Create a table booking.
    Executes authoritative integration adapter in live mode; simulates in mock mode.
    """
    biz_name = business_config.get("name", "Restaurant")
    biz_id = business_config.get("id", "")

    # Live Mode Execution via Authoritative Integration Adapter
    if business_config.get("execution_mode") == "live":
        try:
            from datetime import datetime, timedelta
            from backend.integrations.resolver import resolve_tool_adapter
            from backend.database.repositories.reservation_repo import ReservationConflictError

            adapter = resolve_tool_adapter(biz_id, "create_table_booking")
            start_dt = datetime.fromisoformat(f"{input_data.date}T{input_data.time}:00")
            duration_mins = int(business_config.get("reservation_duration_minutes", 90))
            end_dt = start_dt + timedelta(minutes=duration_mins)

            booking_res = adapter.create_reservation(
                customer_name=input_data.customer_name,
                customer_phone=input_data.customer_phone,
                party_size=input_data.party_size,
                start_time=start_dt,
                end_time=end_dt,
                special_requests=input_data.special_requests,
                idempotency_key=input_data.idempotency_key,
            )

            if not booking_res.get("success", True) or booking_res.get("status") == "failed":
                return ToolExecutionResult(
                    tool_id="create_table_booking",
                    status=ToolExecutionStatus.ERROR,
                    success=False,
                    is_business_accepted=False,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    error_code="RESERVATION_FAILED",
                    data=booking_res,
                    message=booking_res.get("message") or f"Unable to confirm booking with authoritative provider ({booking_res.get('authoritative_source', 'external')}).",
                )

            ref_code = booking_res.get("booking_reference")
            table_name = booking_res.get("table_name", "Assigned Table")

            return ToolExecutionResult(
                tool_id="create_table_booking",
                status=ToolExecutionStatus.SUCCESS,
                success=True,
                is_business_accepted=True,
                is_simulated=False,
                mode=ToolExecutionMode.LIVE,
                data=booking_res,
                message=(
                    f"Table reserved for {input_data.party_size} guests under "
                    f"'{input_data.customer_name}' at {biz_name} on {input_data.date} at {input_data.time} "
                    f"({table_name}). Booking reference: {ref_code}."
                ),
            )
        except ReservationConflictError:
            return ToolExecutionResult(
                tool_id="create_table_booking",
                status=ToolExecutionStatus.BUSINESS_DECLINED,
                success=True,
                is_business_accepted=False,
                is_simulated=False,
                mode=ToolExecutionMode.LIVE,
                data={"available": False, "reason": "conflict"},
                message="The requested table is no longer available at this time due to a reservation conflict. Please choose another time.",
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_id="create_table_booking",
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="BOOKING_FAILED",
                message="Unable to complete table reservation. Please try again or contact staff directly.",
            )

    # Simulated Mock Execution
    ref_code = f"TB-{uuid.uuid4().hex[:8].upper()}"
    return ToolExecutionResult(
        tool_id="create_table_booking",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "booking_reference": ref_code,
            "business_id": biz_id,
            "customer_name": input_data.customer_name,
            "customer_phone": input_data.customer_phone,
            "date": input_data.date,
            "time": input_data.time,
            "party_size": input_data.party_size,
            "special_requests": input_data.special_requests,
            "status": "simulated_booking",
            "is_simulated": True,
        },
        message=(
            f"[Development Simulation] Table reserved for {input_data.party_size} guests under "
            f"'{input_data.customer_name}' at {biz_name} on {input_data.date} at {input_data.time}. "
            f"Booking reference: {ref_code}. This reservation is simulated in development mode and is not confirmed on a live reservation engine."
        ),
    )


def format_dining_reservation_summary(args: Dict[str, Any]) -> str:
    """Format human-readable summary of a dining reservation for confirmation."""
    notes = f"\n• Special Requests: {args['special_requests']}" if args.get("special_requests") else ""
    return (
        f"• Action: Dining Table Reservation\n"
        f"• Guest Contact: {args.get('customer_name')} ({args.get('customer_phone')})\n"
        f"• Party Size: {args.get('party_size')} guests\n"
        f"• Reservation Date & Time: {args.get('date')} at {args.get('time')}"
        f"{notes}"
    )
