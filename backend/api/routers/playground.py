"""
Agent Playground conversation endpoint.
Orchestrates dialogue turns through the shared LangGraph conversation workflow.
"""

from fastapi import APIRouter, HTTPException, status, Depends

from backend.auth import verify_business_access
from backend.api.schemas import PlaygroundMessageRequest, PlaygroundMessageResponse
from backend.database.service import get_database_service
from backend.services.groq_service import get_groq_service
from backend.agent import invoke_receptionist_workflow
from backend.tools.registry import get_tool_registry

router = APIRouter(
    prefix="/businesses/{business_id}/playground",
    tags=["Playground"],
    dependencies=[Depends(verify_business_access)],
)


@router.post("/messages", response_model=PlaygroundMessageResponse)
def send_playground_message(
    business_id: str,
    message_req: PlaygroundMessageRequest,
) -> PlaygroundMessageResponse:
    """
    Submit a caller message to the tenant's virtual receptionist.
    Executes dialogue through the LangGraph workflow with tool calling.
    """
    db_service = get_database_service()

    # 1. Verify business tenant exists
    biz_profile = db_service.get_business_profile(business_id)
    if not biz_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    # 2. Check Groq API configuration
    groq_service = get_groq_service()
    if not groq_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Groq LLM service is not configured. Please configure GROQ_API_KEY in .env.",
        )

    # 3. Append user message to persistent conversation history
    db_service.add_conversation_message(
        business_id=business_id,
        role="user",
        content=message_req.message.strip(),
        is_simulated=True,
    )

    # 4. Load full message history for tenant
    history = db_service.get_conversation_messages(business_id=business_id, limit=50)

    # 5. Invoke shared LangGraph workflow
    workflow_result = invoke_receptionist_workflow(
        business_id=business_id,
        business_config=biz_profile,
        enabled_tools=biz_profile.get("enabled_tools", {}),
        messages=history,
        groq_service=groq_service,
        tool_registry=get_tool_registry(),
    )

    # 6. Save assistant response and pending action (if yielded)
    response_content = workflow_result.get("response_content") or ""
    pending_action = workflow_result.get("pending_action")
    workflow_success = workflow_result.get("success", False)
    error_msg = workflow_result.get("error")

    if response_content:
        db_service.add_conversation_message(
            business_id=business_id,
            role="assistant",
            content=response_content,
            is_simulated=True,
        )

    if pending_action:
        db_service.save_pending_action(business_id, pending_action)

    return PlaygroundMessageResponse(
        business_id=business_id,
        role="assistant",
        content=response_content,
        success=workflow_success,
        pending_action=pending_action,
        error=error_msg,
    )
