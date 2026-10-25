"""
Create Dining Table Booking Tool Functionality.
Standalone tool module for creating and reserving restaurant dining reservations.
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
            "status": "simulated_confirmed",
        },
        message=(
            f"Table reservation confirmed for {input_data.customer_name} (Party of {input_data.party_size}) "
            f"on {input_data.date} at {input_data.time} at {biz_name} (Reference: {ref_code}). "
            f"[SIMULATED MOCK BOOKING - NOT A REAL RESERVATION]"
        ),
    )


def create_create_table_booking_tool_def() -> ToolDefinition:
    """Factory creating the canonical Create Table Booking ToolDefinition."""
    return ToolDefinition(
        id="create_table_booking",
        name="Create Table Booking",
        description="Simulate dining table reservation. Requires explicit user confirmation before execution.",
        category=ToolCategory.DINING,
        allowed_industries=["Restaurant", "Dining", "Hospitality", "Cafe", "Food & Beverage"],
        input_schema=CreateTableBookingInput,
        requires_confirmation=True,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_create_table_booking(data, biz),
    )
