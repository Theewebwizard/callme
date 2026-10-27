"""
Pending Action human-in-the-loop confirmation endpoints.
"""

from fastapi import APIRouter, HTTPException, status, Depends

from backend.auth import verify_business_access
from backend.api.schemas import ActionConfirmResponse
from backend.database.service import get_database_service
from backend.agent import execute_pending_action

router = APIRouter(
    prefix="/businesses/{business_id}/pending-actions",
    tags=["Pending Actions"],
    dependencies=[Depends(verify_business_access)],
)


@router.post("/{action_id}/confirm", response_model=ActionConfirmResponse)
def confirm_pending_action(
    business_id: str,
    action_id: str,
) -> ActionConfirmResponse:
    """
    Phase B: Explicitly confirm and commit a state-modifying action.
    Strictly verifies business scoping and prevents double execution replay.
    """
    db_service = get_database_service()

    # 1. Verify business tenant exists
    biz_profile = db_service.get_business_profile(business_id)
    if not biz_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    # 2. Retrieve pending action by ID for tenant
    pending = db_service.get_pending_action_by_id(business_id, action_id)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending action '{action_id}' not found for business '{business_id}'.",
        )

    if pending.get("status") != "pending_confirmation":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This action has already been executed, cancelled, or expired.",
        )

    # 3. Atomically transition database status to executed to prevent concurrent double-execution
    claimed = db_service.transition_pending_action(
        business_id=business_id,
        action_id=action_id,
        new_status="executed",
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This action has already been executed, cancelled, or expired.",
        )

    # 4. Commit execution through confirmation boundary
    execution_result = execute_pending_action(
        business_id=business_id,
        business_config=biz_profile,
        pending_action=pending,
        confirmed=True,
    )

    if not execution_result.success:
        db_service.transition_pending_action(
            business_id=business_id,
            action_id=action_id,
            new_status="failed",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=execution_result.message or "Action execution failed.",
        )

    # 5. Record reference ID if produced
    if execution_result.reference_id:
        db_service.set_pending_action_reference(
            business_id=business_id,
            action_id=action_id,
            execution_reference=execution_result.reference_id,
        )

    # 6. Append confirmed message to persistent chat history
    ref_note = f" (Reference: {execution_result.reference_id})" if execution_result.reference_id else ""
    db_service.add_conversation_message(
        business_id=business_id,
        role="assistant",
        content=f"✅ **Confirmed**: {execution_result.message}{ref_note}",
        is_simulated=True,
    )

    return ActionConfirmResponse(
        success=True,
        action_id=action_id,
        status="executed",
        reference_id=execution_result.reference_id,
        message=execution_result.message or "Action confirmed and executed successfully.",
    )


@router.post("/{action_id}/cancel", response_model=ActionConfirmResponse)
def cancel_pending_action(
    business_id: str,
    action_id: str,
) -> ActionConfirmResponse:
    """Explicitly reject or cancel a pending action."""
    db_service = get_database_service()

    biz_profile = db_service.get_business_profile(business_id)
    if not biz_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    pending = db_service.get_pending_action_by_id(business_id, action_id)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending action '{action_id}' not found for business '{business_id}'.",
        )

    cancelled = db_service.transition_pending_action(
        business_id=business_id,
        action_id=action_id,
        new_status="cancelled",
    )
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This action is not pending confirmation (already executed, cancelled, or expired).",
        )

    db_service.add_conversation_message(
        business_id=business_id,
        role="assistant",
        content="🚫 **Action Cancelled**: The requested action was cancelled. How else may I assist you?",
        is_simulated=True,
    )

    return ActionConfirmResponse(
        success=True,
        action_id=action_id,
        status="cancelled",
        message="Action was cancelled by user.",
    )
