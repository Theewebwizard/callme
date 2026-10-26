"""
Dining and table management tool handlers.
"""

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
    Uses business operating hours for deterministic mock checks.
    """
    opening = business_config.get("opening_time", "11:00")
    closing = business_config.get("closing_time", "23:00")
    biz_name = business_config.get("name", "Restaurant")

    # Time window check (HH:MM string comparison works for standard 24h format)
    if input_data.time < opening or input_data.time > closing:
        return ToolExecutionResult(
            tool_id="check_table_availability",
            status=ToolExecutionStatus.SUCCESS,
            success=False,
            mode=ToolExecutionMode.MOCK,
            data={
                "available": False,
                "reason": "outside_operating_hours",
                "opening_time": opening,
                "closing_time": closing,
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
            status=ToolExecutionStatus.SUCCESS,
            success=False,
            mode=ToolExecutionMode.MOCK,
            data={
                "available": False,
                "reason": "party_size_exceeds_automated_booking",
                "party_size": input_data.party_size,
            },
            message=(
                f"Parties larger than 10 guests ({input_data.party_size} requested) require "
                f"direct arrangement with the events manager at {business_config.get('phone_number', 'our front desk')}."
            ),
        )

    # Deterministic mock availability
    return ToolExecutionResult(
        tool_id="check_table_availability",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "available": True,
            "date": input_data.date,
            "requested_time": input_data.time,
            "party_size": input_data.party_size,
            "seating_options": ["Indoor Dining Room", "Window Table", "Outdoor Terrace"],
            "mock_slots": [input_data.time, "15 mins before", "15 mins after"],
        },
        message=(
            f"Tables are available for a party of {input_data.party_size} on {input_data.date} "
            f"around {input_data.time} at {biz_name}. Would you like to proceed with a reservation?"
        ),
    )


def handle_create_table_booking(
    input_data: CreateTableBookingInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Simulate creating a table booking after confirmation has been validated.
    """
    ref_seed = f"{input_data.customer_name}{input_data.date}{input_data.time}"
    ref_code = f"TB-{abs(hash(ref_seed)) % 10000:04d}"
    biz_name = business_config.get("name", "Restaurant")

    return ToolExecutionResult(
        tool_id="create_table_booking",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "booking_reference": ref_code,
            "business_id": business_config.get("id"),
            "customer_name": input_data.customer_name,
            "customer_phone": input_data.customer_phone,
            "date": input_data.date,
            "time": input_data.time,
            "party_size": input_data.party_size,
            "special_requests": input_data.special_requests,
            "status": "confirmed",
        },
        message=(
            f"Table reserved for {input_data.party_size} guests under "
            f"'{input_data.customer_name}' at {biz_name} on {input_data.date} at {input_data.time}. "
            f"Booking reference: {ref_code}. A confirmation will be shared with the guest."
        ),
    )
