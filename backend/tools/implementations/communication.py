"""
Communication and intake tool handlers (messaging and call transfer).
"""

import uuid
import logging
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

logger = logging.getLogger(__name__)


def handle_take_message(
    input_data: TakeMessageInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Record a caller's message and callback contact details.
    Persists to database conversation store if database engine is connected;
    fails closed in live mode if persistence fails; explicitly tracks
    persistence, notification queuing, and delivery status.
    """
    ref_code = f"MSG-{uuid.uuid4().hex[:8].upper()}"
    biz_name = business_config.get("name", "our team")
    business_id = business_config.get("id", "unknown")
    exec_mode = business_config.get("execution_mode", "mock")

    # Attempt genuine persistence via DatabaseService if database engine is live
    db_persisted = False
    persistence_error = None
    try:
        from backend.database.service import get_database_service
        from backend.database.engine import check_database_connection
        service = get_database_service()
        engine_to_check = getattr(service, "engine", None)
        conn = check_database_connection(engine=engine_to_check)
        if conn.get("connected"):
            formatted_msg = (
                f"[Caller Message | Ref: {ref_code} | Urgency: {input_data.urgency.upper()}]\n"
                f"From: {input_data.caller_name} ({input_data.caller_phone})\n"
                f"Message: {input_data.message}"
            )
            service.add_conversation_message(
                business_id=business_id,
                role="caller_message",
                content=formatted_msg,
                is_simulated=False,
            )
            db_persisted = True
            logger.info("Successfully persisted caller message %s for business %s", ref_code, business_id)
        else:
            persistence_error = "Database engine is not connected."
    except Exception as exc:
        persistence_error = str(exc)
        logger.warning("Database persistence failed for take_message (%s): %s", ref_code, exc)
        db_persisted = False

    # Fail closed if live mode was mandated but persistence failed
    if exec_mode == "live" and not db_persisted:
        return ToolExecutionResult(
            tool_id="take_message",
            status=ToolExecutionStatus.ERROR,
            success=False,
            is_business_accepted=False,
            is_simulated=False,
            mode=ToolExecutionMode.LIVE,
            error_code="MESSAGE_PERSISTENCE_FAILED",
            internal_diagnostics=f"Failed persisting caller message in live mode: {persistence_error}",
            message=(
                f"Message could not be saved to staff records at this time. "
                f"Please contact our desk directly."
            ),
        )

    status_str = "persisted" if db_persisted else "simulated_intake"
    return ToolExecutionResult(
        tool_id="take_message",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=not db_persisted,
        mode=ToolExecutionMode.LIVE if db_persisted else ToolExecutionMode.MOCK,
        data={
            "message_reference": ref_code,
            "business_id": business_id,
            "caller_name": input_data.caller_name,
            "caller_phone": input_data.caller_phone,
            "message": input_data.message,
            "urgency": input_data.urgency,
            "status": status_str,
            "is_persisted": db_persisted,
            "persistence_status": "persisted" if db_persisted else "unpersisted_memory",
            "notification_queued": False,
            "notification_delivered": False,
            "delivery_status": "stored_for_staff_review" if db_persisted else "simulated_memory_only",
            "is_simulated": not db_persisted,
        },
        message=(
            f"Message recorded for {biz_name} staff from {input_data.caller_name} "
            f"({input_data.caller_phone}). Reference: {ref_code}. Note: Staff SMS/email dispatch queue is not configured."
            if db_persisted
            else f"[Development Simulation] Message captured in development memory for {biz_name} staff from {input_data.caller_name} "
            f"({input_data.caller_phone}). Reference: {ref_code}. Note: Database storage is not active in this development session."
        ),
    )


def handle_transfer_call(
    input_data: TransferCallInput,
    business_config: Dict[str, Any],
) -> ToolExecutionResult:
    """
    Handle call transfer and human escalation request.
    Truthfully reports whether a live telephony bridge exists or if simulated escalation is logged.
    Never promises a nonexistent live transfer or directs callers to hold on dead air.
    Filters placeholder destination numbers.
    """
    ref_code = f"XFER-{uuid.uuid4().hex[:8].upper()}"
    raw_phone = business_config.get("phone_number", "")
    is_placeholder = (
        not raw_phone
        or "0000" in raw_phone.replace(" ", "")
        or raw_phone.strip() in ("+91 80 0000 0000", "+91 80 0000 0001", "000-000-0000")
    )
    phone_to_report = raw_phone if not is_placeholder else None

    target = input_data.department_or_target or "Emergency / Duty Manager Desk"
    biz_name = business_config.get("name", "our office")
    business_id = business_config.get("id", "unknown")

    # Check if strict live execution is mandated without an active telephony bridge
    exec_mode = business_config.get("execution_mode", "mock")
    if exec_mode == "live":
        return ToolExecutionResult(
            tool_id="transfer_call",
            status=ToolExecutionStatus.UNAVAILABLE,
            success=False,
            is_business_accepted=False,
            is_simulated=False,
            mode=ToolExecutionMode.UNAVAILABLE,
            error_code="TELEPHONY_TRANSFER_UNAVAILABLE",
            data={
                "transfer_reference": ref_code,
                "business_id": business_id,
                "target": target,
                "destination_phone": phone_to_report,
                "status": "unavailable",
            },
            message=(
                f"Automated line transfer is currently unavailable. "
                + (f"Please dial our primary line directly at {phone_to_report} to reach {target}." if phone_to_report else f"Please contact {biz_name} staff directly.")
            ),
        )

    # In simulated / development mode, log escalation and return truthful simulation metadata
    dest_str = f"at direct line {phone_to_report}" if phone_to_report else "(no direct phone extension configured)"
    return ToolExecutionResult(
        tool_id="transfer_call",
        status=ToolExecutionStatus.SUCCESS,
        success=True,
        is_business_accepted=True,
        is_simulated=True,
        mode=ToolExecutionMode.MOCK,
        data={
            "transfer_reference": ref_code,
            "business_id": business_id,
            "target": target,
            "destination_phone": phone_to_report,
            "reason": input_data.reason,
            "status": "simulated_escalation_logged",
            "live_telephony_transfer_performed": False,
            "is_simulated": True,
        },
        message=(
            f"[Simulation] Escalation request logged for {target} {dest_str} "
            f"regarding '{input_data.reason}'. Live telephony line transfer is simulated in this environment. Reference: {ref_code}."
        ),
    )
