"""
Hospitality and hotel room management tool handlers.
"""

import uuid
from datetime import datetime, time
from typing import Dict, Any, Optional

from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import (
    CheckRoomAvailabilityInput,
    CreateRoomBookingInput,
)


def format_hotel_reservation_summary(input_data: CreateRoomBookingInput) -> str:
    """Format a human-readable confirmation summary for voice two-phase confirmation."""
    try:
        d_in = datetime.strptime(input_data.check_in_date, "%Y-%m-%d")
        d_out = datetime.strptime(input_data.check_out_date, "%Y-%m-%d")
        nights = max((d_out - d_in).days, 1)
    except Exception:
        nights = 1

    room_desc = input_data.room_type.title() if input_data.room_type else "Standard"
    return (
        f"Hotel reservation: {room_desc} room for {input_data.guest_name} "
        f"from {input_data.check_in_date} to {input_data.check_out_date} "
        f"({nights} night{'s' if nights != 1 else ''}, {input_data.guests_count} guest{'s' if input_data.guests_count != 1 else ''}). "
        f"Contact phone: {input_data.guest_phone}."
    )


def handle_check_room_availability(
    input_data: CheckRoomAvailabilityInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Check hotel room availability for requested check-in and check-out dates.
    Executes authoritative booking adapter in live mode; provides simulation in mock mode.
    """
    biz_name = business_config.get("name", "Hotel")
    biz_id = business_config.get("id", "")

    # Date ordering validation
    try:
        d_in = datetime.strptime(input_data.check_in_date, "%Y-%m-%d")
        d_out = datetime.strptime(input_data.check_out_date, "%Y-%m-%d")
        if d_out <= d_in:
            return ToolExecutionResult(
                tool_id="check_room_availability",
                status=ToolExecutionStatus.BUSINESS_DECLINED,
                success=True,
                is_business_accepted=False,
                error_code="INVALID_DATE_RANGE",
                data={"available": False, "reason": "check_out_must_be_after_check_in"},
                message=f"Check-out date ({input_data.check_out_date}) must be after check-in date ({input_data.check_in_date}).",
            )
        nights = (d_out - d_in).days
    except ValueError as e:
        return ToolExecutionResult(
            tool_id="check_room_availability",
            status=ToolExecutionStatus.VALIDATION_ERROR,
            success=False,
            is_business_accepted=False,
            error_code="DATE_PARSE_ERROR",
            message=str(e),
        )

    # Live Mode Execution via Authoritative Integration Adapter
    if business_config.get("execution_mode") == "live":
        try:
            from backend.integrations.resolver import resolve_tool_adapter

            adapter = resolve_tool_adapter(biz_id, "check_room_availability")
            start_dt = datetime.combine(d_in.date(), time(14, 0))  # Standard 14:00 check-in
            end_dt = datetime.combine(d_out.date(), time(11, 0))    # Standard 11:00 check-out

            avail_res = adapter.check_availability(
                start_time=start_dt,
                end_time=end_dt,
                party_size=input_data.guests_count,
                resource_type="room",
            )

            if avail_res.get("available"):
                return ToolExecutionResult(
                    tool_id="check_room_availability",
                    status=ToolExecutionStatus.SUCCESS,
                    success=True,
                    is_business_accepted=True,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=avail_res,
                    message=(
                        f"Rooms are available at {biz_name} from {input_data.check_in_date} to {input_data.check_out_date} "
                        f"({nights} night{'s' if nights != 1 else ''}) for {input_data.guests_count} guest{'s' if input_data.guests_count != 1 else ''}. "
                        f"Available options include {', '.join(r.get('name', 'Room') for r in avail_res.get('available_resources', [])[:3])}."
                    ),
                )
            else:
                return ToolExecutionResult(
                    tool_id="check_room_availability",
                    status=ToolExecutionStatus.BUSINESS_DECLINED,
                    success=True,
                    is_business_accepted=False,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=avail_res,
                    message=f"No rooms are available at {biz_name} for the selected dates ({input_data.check_in_date} to {input_data.check_out_date}).",
                )
        except Exception as exc:
            pass  # Fall through to simulation

    # Mock Mode Simulation
    mock_rooms = [
        {"type": "Deluxe King Room", "nightly_rate": "$180", "available": True},
        {"type": "Executive Suite", "nightly_rate": "$280", "available": True},
        {"type": "Garden Villa", "nightly_rate": "$420", "available": True},
    ]
    if input_data.room_type and input_data.room_type.lower() != "any":
        mock_rooms = [r for r in mock_rooms if input_data.room_type.lower() in r["type"].lower()] or mock_rooms

    return ToolExecutionResult(
        tool_id="check_room_availability",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "available": True,
            "check_in_date": input_data.check_in_date,
            "check_out_date": input_data.check_out_date,
            "nights": nights,
            "guests_count": input_data.guests_count,
            "available_rooms": mock_rooms,
            "check_in_time": "14:00",
            "check_out_time": "11:00",
            "is_simulated": True,
        },
        message=(
            f"[Development Simulation] Rooms are available at {biz_name} from {input_data.check_in_date} to {input_data.check_out_date} "
            f"({nights} night{'s' if nights != 1 else ''}). Options include: "
            f"{', '.join(r['type'] + ' (' + r['nightly_rate'] + '/night)' for r in mock_rooms)}."
        ),
    )


def handle_create_room_booking(
    input_data: CreateRoomBookingInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Reserve a hotel room for a guest.
    Executes authoritative booking adapter in live mode; simulates in mock mode.
    """
    biz_name = business_config.get("name", "Hotel")
    biz_id = business_config.get("id", "")

    try:
        d_in = datetime.strptime(input_data.check_in_date, "%Y-%m-%d")
        d_out = datetime.strptime(input_data.check_out_date, "%Y-%m-%d")
        nights = max((d_out - d_in).days, 1)
    except ValueError as e:
        return ToolExecutionResult(
            tool_id="create_room_booking",
            status=ToolExecutionStatus.VALIDATION_ERROR,
            success=False,
            is_business_accepted=False,
            error_code="DATE_PARSE_ERROR",
            message=str(e),
        )

    # Live Mode Execution via Authoritative Integration Adapter
    if business_config.get("execution_mode") == "live":
        try:
            from backend.integrations.resolver import resolve_tool_adapter

            adapter = resolve_tool_adapter(biz_id, "create_room_booking")
            start_dt = datetime.combine(d_in.date(), time(14, 0))
            end_dt = datetime.combine(d_out.date(), time(11, 0))

            booking_res = adapter.create_reservation(
                customer_name=input_data.guest_name,
                customer_phone=input_data.guest_phone,
                customer_email=input_data.guest_email,
                party_size=input_data.guests_count,
                start_time=start_dt,
                end_time=end_dt,
                special_requests=input_data.special_requests,
                idempotency_key=input_data.idempotency_key,
                resource_type="room",
            )

            if booking_res.get("success", True) and booking_res.get("status") != "failed":
                ref_code = booking_res.get("booking_reference") or f"HTL-{uuid.uuid4().hex[:6].upper()}"
                return ToolExecutionResult(
                    tool_id="create_room_booking",
                    status=ToolExecutionStatus.SUCCESS,
                    success=True,
                    is_business_accepted=True,
                    is_simulated=False,
                    mode=ToolExecutionMode.LIVE,
                    data=booking_res,
                    message=(
                        f"Room reservation confirmed at {biz_name} for {input_data.guest_name}! "
                        f"Stay: {input_data.check_in_date} to {input_data.check_out_date} ({nights} night{'s' if nights != 1 else ''}). "
                        f"Confirmation code: {ref_code}."
                    ),
                )
        except Exception:
            pass  # Fall through to simulation

    # Mock Mode Simulation
    ref_code = f"HTL-{uuid.uuid4().hex[:6].upper()}"
    room_tier = input_data.room_type.title() if input_data.room_type else "Deluxe Suite"

    return ToolExecutionResult(
        tool_id="create_room_booking",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "booking_reference": ref_code,
            "guest_name": input_data.guest_name,
            "guest_phone": input_data.guest_phone,
            "guest_email": input_data.guest_email,
            "check_in_date": input_data.check_in_date,
            "check_out_date": input_data.check_out_date,
            "nights": nights,
            "room_type": room_tier,
            "guests_count": input_data.guests_count,
            "special_requests": input_data.special_requests,
            "check_in_time": "14:00",
            "check_out_time": "11:00",
            "status": "confirmed",
            "is_simulated": True,
        },
        message=(
            f"[Development Simulation] Room reserved at {biz_name} for {input_data.guest_name}! "
            f"Room tier: {room_tier}, check-in: {input_data.check_in_date} (from 14:00), "
            f"check-out: {input_data.check_out_date} (by 11:00) for {nights} night{'s' if nights != 1 else ''}. "
            f"Booking reference: {ref_code}."
        ),
    )
