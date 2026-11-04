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
import logging
from typing import Dict, Any, Optional, List

from backend.tools.definitions import (
    CheckRoomAvailabilityInput,
    CreateRoomBookingInput,
    QueryRoomPricingInput,
)

logger = logging.getLogger(__name__)


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


def handle_query_room_pricing(
    input_data: QueryRoomPricingInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Search hotel room catalog for room types, current rates, amenities, bed types, and inclusions.
    Uses semantic concept matching and dynamic tenant database access mirroring handle_query_menu_pricing.
    """
    biz_id = business_config.get("id", "")
    biz_name = business_config.get("name", "our hotel")
    raw_mode = business_config.get("execution_mode", "mock")
    is_live = (str(raw_mode).lower() == "live")
    exec_mode = ToolExecutionMode.LIVE if is_live else ToolExecutionMode.MOCK

    query = input_data.query.strip()
    category = input_data.category.strip() if input_data.category else None
    amenity_pref = input_data.amenity_preference.strip() if input_data.amenity_preference else None
    guests_count = input_data.guests_count
    max_budget = input_data.max_budget_per_night

    nights = None
    if input_data.check_in_date and input_data.check_out_date:
        try:
            d_in = datetime.strptime(input_data.check_in_date, "%Y-%m-%d")
            d_out = datetime.strptime(input_data.check_out_date, "%Y-%m-%d")
            if d_out > d_in:
                nights = (d_out - d_in).days
        except Exception:
            nights = None

    matching_rooms: List[Dict[str, Any]] = []

    # 1. Authoritative query via DatabaseService
    try:
        from backend.database.service import get_database_service
        db_service = get_database_service()
        if db_service and biz_id:
            matching_rooms = db_service.search_room_types_semantic(
                business_id=biz_id,
                query=query,
                category=category,
                amenity_preference=amenity_pref,
                guests_count=guests_count,
                max_budget_per_night=max_budget,
                limit=6,
            )
    except Exception as exc:
        logger.warning("Database search failed in handle_query_room_pricing: %s", exc)

    # 2. In-memory fallback if DB returned empty and room_types were supplied in business_config
    if not matching_rooms and "room_types" in business_config and business_config["room_types"]:
        from backend.database.repositories.room_repo import rank_room_types_semantic
        matching_rooms = rank_room_types_semantic(
            rooms=business_config["room_types"],
            query=query,
            category=category,
            amenity_preference=amenity_pref,
            guests_count=guests_count,
            max_budget_per_night=max_budget,
            limit=6,
        )

    # 3. Assemble response
    if not matching_rooms:
        budget_str = f" under ₹{int(max_budget)}/night" if max_budget else ""
        amenity_str = f" with {amenity_pref}" if amenity_pref else ""
        return ToolExecutionResult(
            tool_id="query_room_pricing",
            status=ToolExecutionStatus.SUCCESS,
            success=True,
            is_business_accepted=True,
            mode=exec_mode,
            is_simulated=(not is_live),
            data={
                "found": False,
                "count": 0,
                "query": query,
                "rooms": [],
            },
            message=(
                f"We currently do not have any room options matching '{query}'{amenity_str}{budget_str} "
                f"at {biz_name}. Would you like me to check our other luxury suites or look up availability for specific dates?"
            ),
        )

    # Format clear spoken voice summary
    lines = [f"Here are the matching room options at {biz_name}:"]
    currency_symbol = matching_rooms[0].get("currency", "INR")
    curr_prefix = "₹" if currency_symbol in ("INR", "₹") else f"{currency_symbol} "

    for r in matching_rooms:
        p = r.get("base_price", 0.0)
        formatted_price = f"{curr_prefix}{int(p)}" if p == int(p) else f"{curr_prefix}{p:.2f}"
        name = r.get("name", "Standard Room")
        bed = r.get("bed_type") or "King Bed"
        cap = r.get("max_occupancy", 2)
        amenities = r.get("amenities") or []
        inclusions = r.get("inclusions") or []

        amenity_str = f" ({', '.join(amenities[:3])})" if amenities else ""
        inclusion_str = f" - includes {', '.join(inclusions[:2])}" if inclusions else ""

        if nights and nights > 0:
            total_est = p * nights
            total_fmt = f"{curr_prefix}{int(total_est)}" if total_est == int(total_est) else f"{curr_prefix}{total_est:.2f}"
            lines.append(f"• {name} - {formatted_price}/night ({total_fmt} for {nights} nights) [{bed}, up to {cap} guests]{amenity_str}{inclusion_str}")
        else:
            lines.append(f"• {name} - {formatted_price}/night [{bed}, up to {cap} guests]{amenity_str}{inclusion_str}")

    summary_text = "\n".join(lines)

    return ToolExecutionResult(
        tool_id="query_room_pricing",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        mode=exec_mode,
        is_simulated=(not is_live),
        data={
            "found": True,
            "count": len(matching_rooms),
            "query": query,
            "nights": nights,
            "rooms": matching_rooms,
        },
        message=summary_text,
    )
