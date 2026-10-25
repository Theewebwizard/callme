"""
Check Dining Table Availability Tool Functionality.
Standalone tool module for checking restaurant table capacity and timeslots.
"""

from typing import Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from tools.base import (
    ToolDefinition,
    ToolCategory,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)


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
                f"operating hours ({opening} – {closing}). [SIMULATED MOCK AVAILABILITY]"
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
            f"around {input_data.time} at {biz_name}. [SIMULATED MOCK AVAILABILITY - NOT LIVE INVENTORY]"
        ),
    )


def create_check_table_availability_tool_def() -> ToolDefinition:
    """Factory creating the canonical Check Table Availability ToolDefinition."""
    return ToolDefinition(
        id="check_table_availability",
        name="Check Table Availability",
        description="Verify dining table availability for party size, date, and timeslot.",
        category=ToolCategory.DINING,
        allowed_industries=["Restaurant", "Dining", "Hospitality", "Cafe", "Food & Beverage"],
        input_schema=CheckTableAvailabilityInput,
        requires_confirmation=False,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_check_table_availability(data, biz),
    )
