"""
Communication and intake tool handlers (messaging and call transfer).
"""

from typing import Dict, Any
from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import (
    TakeMessageInput,
    TransferCallInput,
)


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
