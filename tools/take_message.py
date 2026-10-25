"""
Take Caller Message Tool Functionality.
Standalone tool module for capturing caller contact details, callback requests, and urgent voicemails.
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


class TakeMessageInput(BaseModel):
    """Input payload for capturing caller callback details and messages."""
    caller_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full name of caller.",
    )
    caller_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Callback contact telephone number.",
    )
    message: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Detailed message content to deliver to business staff.",
    )
    urgency: str = Field(
        "normal",
        pattern=r"^(low|normal|urgent)$",
        description="Callback priority: 'low', 'normal', or 'urgent'.",
    )

    model_config = ConfigDict(extra="forbid")


def handle_take_message(
    input_data: TakeMessageInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Simulate recording a caller's message and callback telephone number.
    """
    ref_seed = f"{input_data.caller_name}{input_data.message}"
    ref_code = f"MSG-{abs(hash(ref_seed)) % 10000:04d}"
    biz_name = business_config.get("name", "our team")

    return ToolExecutionResult(
        tool_id="take_message",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "message_reference": ref_code,
            "business_id": business_config.get("id"),
            "caller_name": input_data.caller_name,
            "caller_phone": input_data.caller_phone,
            "message": input_data.message,
            "urgency": input_data.urgency,
            "status": "simulated_logged",
        },
        message=(
            f"Message recorded for {biz_name} staff from '{input_data.caller_name}' "
            f"({input_data.caller_phone}). Priority: {input_data.urgency}. "
            f"(Ref: {ref_code}) [SIMULATED MESSAGE RECORD]"
        ),
    )


def create_take_message_tool_def() -> ToolDefinition:
    """Factory creating the canonical Take Message ToolDefinition."""
    return ToolDefinition(
        id="take_message",
        name="Take Message",
        description="Record a detailed caller message and contact information for staff callback.",
        category=ToolCategory.COMMUNICATION,
        allowed_industries=["*"],
        input_schema=TakeMessageInput,
        requires_confirmation=False,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_take_message(data, biz),
    )
