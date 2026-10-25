"""
Transfer Call to Human Staff Tool Functionality.
Standalone tool module for routing and escalating callers to staff desks or managers.
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


class TransferCallInput(BaseModel):
    """Input payload for requesting a human operator or line transfer."""
    reason: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Reason caller is requesting human escalation.",
    )
    department_or_target: Optional[str] = Field(
        None,
        max_length=100,
        description="Specific staff member, department, or desk requested.",
    )

    model_config = ConfigDict(extra="forbid")


def handle_transfer_call(
    input_data: TransferCallInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Simulate initiating a human operator transfer.
    """
    ref_seed = f"{input_data.reason}{input_data.department_or_target or ''}"
    ref_code = f"XFER-{abs(hash(ref_seed)) % 10000:04d}"
    phone = business_config.get("phone_number", "+91 80 0000 0000")
    target = input_data.department_or_target or "Emergency / Duty Manager Desk"
    biz_name = business_config.get("name", "our office")

    return ToolExecutionResult(
        tool_id="transfer_call",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "transfer_reference": ref_code,
            "business_id": business_config.get("id"),
            "target": target,
            "destination_phone": phone,
            "reason": input_data.reason,
            "status": "simulated_transfer_initiated",
        },
        message=(
            f"Call transfer simulated to {target} ({phone}) for {biz_name} "
            f"regarding '{input_data.reason}' (Ref: {ref_code}). "
            f"[SIMULATED CALL TRANSFER - NOT A REAL TELEPHONE TRANSFER]"
        ),
    )


def create_transfer_call_tool_def() -> ToolDefinition:
    """Factory creating the canonical Transfer Call ToolDefinition."""
    return ToolDefinition(
        id="transfer_call",
        name="Transfer Call",
        description="Initiate transfer to human operator, staff member, or manager.",
        category=ToolCategory.COMMUNICATION,
        allowed_industries=["*"],
        input_schema=TransferCallInput,
        requires_confirmation=False,
        is_implemented=True,
        execution_mode=ToolExecutionMode.MOCK,
        handler=lambda data, biz: handle_transfer_call(data, biz),
    )
