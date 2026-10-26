"""
Workflow nodes for the shared LangGraph conversation graph.
Executes tool-calling decisions, schema validation, and two-phase confirmation guards.
"""

import json
import uuid
from typing import Dict, Any, Optional
from pydantic import ValidationError

from backend.agent.state import AgentState
from backend.agent.semantic_intent import (
    FollowupIntentType,
    SemanticIntentExtraction,
    extract_semantic_followup_intent,
    is_followup_prompt,
    detect_language,
)
from backend.services.groq_service import (
    GroqService,
    get_groq_service,
    build_business_system_instruction,
    convert_tool_definition_to_groq_schema,
)
from backend.tools.base import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.registry import ToolRegistry, get_tool_registry


def _format_pending_action_summary(tool_id: str, args: Dict[str, Any]) -> str:
    """Format human-readable summary of a confirmation-required action."""
    if tool_id == "create_table_booking":
        notes = f"\n• Special Requests: {args['special_requests']}" if args.get("special_requests") else ""
        return (
            f"• Action: Dining Table Reservation\n"
            f"• Guest Contact: {args.get('customer_name')} ({args.get('customer_phone')})\n"
            f"• Party Size: {args.get('party_size')} guests\n"
            f"• Reservation Date & Time: {args.get('date')} at {args.get('time')}"
            f"{notes}"
        )
    elif tool_id == "create_appointment":
        notes = f"\n• Notes: {args['notes']}" if args.get("notes") else ""
        return (
            f"• Action: Clinical Consultation Appointment\n"
            f"• Patient: {args.get('patient_name')} ({args.get('patient_phone')})\n"
            f"• Service / Department: {args.get('service_or_department')}\n"
            f"• Date & Time: {args.get('appointment_date')} at {args.get('appointment_time')}"
            f"{notes}"
        )
    return "\n".join(f"• {k}: {v}" for k, v in args.items())


def prepare_context_node(
    state: AgentState,
    tool_registry: Optional[ToolRegistry] = None,
) -> Dict[str, Any]:
    """
    Node A: Prepare Context
    Validates business configuration and conversation history, retrieves enabled
    tools, and compiles the tenant-specific system prompt and tool definitions.
    """
    biz_config = state.get("business_config")
    if not biz_config or not isinstance(biz_config, dict):
        return {
            "error": "Missing or invalid business configuration in workflow state.",
            "success": False,
        }

    messages = state.get("messages")
    if messages is None or not isinstance(messages, list):
        return {
            "error": "Missing or invalid conversation messages in workflow state.",
            "success": False,
        }

    # Validate that at least one valid turn exists
    valid_turns = [
        m for m in messages
        if isinstance(m, dict) and (m.get("content", "").strip() or m.get("tool_calls"))
    ]
    if not valid_turns:
        return {
            "error": "Conversation input is empty. At least one message is required.",
            "success": False,
        }

    registry = tool_registry or get_tool_registry()
    enabled_tool_defs = registry.get_enabled_tools_for_business(biz_config)
    tool_schemas = [convert_tool_definition_to_groq_schema(t) for t in enabled_tool_defs]

    # Map of enabled tools for prompt generation
    enabled_tools_map = {t.id: t for t in enabled_tool_defs}

    system_instruction = build_business_system_instruction(
        business=biz_config,
        tools_catalogue=enabled_tools_map,
    )

    # Check if the caller is replying to an assistant prompt asking if they have any other queries
    last_assistant_turn = None
    last_user_turn = None
    for m in reversed(valid_turns):
        if m.get("role") == "user" and last_user_turn is None:
            last_user_turn = m
        elif m.get("role") == "assistant" and last_assistant_turn is None:
            last_assistant_turn = m
        if last_assistant_turn and last_user_turn:
            break

    if last_assistant_turn and last_user_turn and valid_turns[-1].get("role") == "user":
        ast_content = last_assistant_turn.get("content", "")
        user_content = last_user_turn.get("content", "")

        if is_followup_prompt(ast_content):
            # Extract semantic intent via Pydantic model
            intent_res = extract_semantic_followup_intent(
                caller_text=user_content,
                last_assistant_text=ast_content,
            )

            if intent_res.intent == FollowupIntentType.NO_FURTHER_QUERY:
                biz_name = biz_config.get("name", "our business")
                is_hindi = intent_res.language == "hi" or detect_language(user_content) == "hi"
                if is_hindi:
                    farewell = "कॉल करने के लिए धन्यवाद! आपका दिन शुभ हो, अलविदा।"
                else:
                    farewell = f"Thank you for calling {biz_name}! Have a wonderful day, goodbye!"

                return {
                    "system_instruction": system_instruction,
                    "tool_definitions": tool_schemas,
                    "iteration_count": 0,
                    "response_content": farewell,
                    "followup_intent": FollowupIntentType.NO_FURTHER_QUERY.value,
                    "should_terminate": True,
                    "success": True,
                    "error": None,
                    "tools_called": [],
                    "work_completed": False,
                }

            elif intent_res.intent == FollowupIntentType.HAS_FURTHER_QUERY:
                is_hindi = intent_res.language == "hi" or detect_language(user_content) == "hi"
                if is_hindi:
                    prompt_reply = "जी बिल्कुल! बताइए, मैं आपकी और क्या सहायता कर सकता हूँ?"
                else:
                    prompt_reply = "Certainly! What else can I help you with?"

                return {
                    "system_instruction": system_instruction,
                    "tool_definitions": tool_schemas,
                    "iteration_count": 0,
                    "response_content": prompt_reply,
                    "followup_intent": FollowupIntentType.HAS_FURTHER_QUERY.value,
                    "should_terminate": False,
                    "success": True,
                    "error": None,
                    "tools_called": [],
                    "work_completed": False,
                }

    return {
        "system_instruction": system_instruction,
        "tool_definitions": tool_schemas,
        "iteration_count": 0,
        "success": True,
        "error": None,
        "tools_called": [],
        "work_completed": False,
        "should_terminate": False,
    }


def call_llm_node(
    state: AgentState,
    groq_service: Optional[GroqService] = None,
) -> Dict[str, Any]:
    """
    Node B: Call LLM
    Invokes Groq with conversation messages, system prompt, and authorized tool schemas.
    """
    if not state.get("success", False) or state.get("error"):
        return {}

    iter_count = state.get("iteration_count", 0) + 1
    service = groq_service or get_groq_service()
    system_instruction = state.get("system_instruction", "")
    messages = state.get("messages", [])
    tools = state.get("tool_definitions")

    llm_resp = service.generate_response(
        messages=messages,
        system_instruction=system_instruction,
        tools=tools,
    )

    if llm_resp.success:
        return {
            "latest_tool_calls": llm_resp.tool_calls,
            "response_content": llm_resp.content,
            "iteration_count": iter_count,
            "success": True,
            "error": None,
        }
    else:
        return {
            "latest_tool_calls": None,
            "response_content": None,
            "iteration_count": iter_count,
            "success": False,
            "error": llm_resp.error or "Failed to generate AI response from Groq.",
        }


# Backward-compatible alias for existing tests
generate_response_node = call_llm_node


def _is_prior_action_confirmed(messages: list, tool_id: str) -> bool:
    """
    Check if the conversation history shows that this tool's action was already
    proposed in the prior assistant turn and the caller just verbally confirmed it.
    Enables voice callers to confirm bookings/appointments verbally without clicking UI buttons.
    """
    import re
    if not messages or len(messages) < 2:
        return False

    last_user_content = ""
    prev_assistant_content = ""

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        role = msg.get("role")
        content = msg.get("content") or ""

        if role == "user" and not last_user_content:
            last_user_content = content.strip().lower()
            for j in range(i - 1, -1, -1):
                if messages[j].get("role") == "assistant":
                    prev_assistant_content = (messages[j].get("content") or "").strip().lower()
                    break
            break

    if not last_user_content or not prev_assistant_content:
        return False

    # 1. Verify previous assistant message proposed an action awaiting confirmation
    proposal_cues = [
        "prepared your",
        "action:",
        "details:",
        "confirm or cancel",
        "confirm this",
        "confirm for you",
        "shall i go ahead",
        "would you like me to confirm",
        "booking details",
        "appointment details",
    ]
    had_proposal = any(cue in prev_assistant_content for cue in proposal_cues)
    if not had_proposal:
        return False

    # 2. Check for explicit cancellation
    cancel_cues = ["cancel", "don't", "dont", "abort", "stop", "nahi mat", "mat karo", "no don't", "no dont"]
    if any(re.search(rf"\b{re.escape(c)}\b", last_user_content) for c in cancel_cues):
        return False

    # 3. Check for verbal confirmation phrases
    confirm_patterns = [
        r"\b(?:confirm|confirmed|confirming)\b",
        r"\b(?:yes|yeah|yep|yup|sure|okay|ok|go ahead|proceed|book it|please do|do it)\b",
        r"\b(?:haan|haanji|ha ji|kardo|kar do|kar dijiye|theek hai|bilkul)\b",
    ]
    return any(re.search(pat, last_user_content) for pat in confirm_patterns)


def execute_tools_node(
    state: AgentState,
    tool_registry: Optional[ToolRegistry] = None,
) -> Dict[str, Any]:
    """
    Node C: Execute Tools
    Validates requested tool calls, enforces tenant permissions, intercepts
    confirmation-required actions, and executes permitted tools through the registry.
    """
    if not state.get("success", False) or state.get("error"):
        return {}

    registry = tool_registry or get_tool_registry()
    tool_calls = state.get("latest_tool_calls") or []
    biz_id = state.get("business_id", "")
    biz_config = state.get("business_config", {})
    messages = list(state.get("messages", []))
    tools_called = list(state.get("tools_called") or [])

    # Record assistant tool call turn in messages history
    assistant_turn = {
        "role": "assistant",
        "content": state.get("response_content") or "",
        "tool_calls": tool_calls,
    }
    messages.append(assistant_turn)

    for tc in tool_calls:
        tc_id = tc.get("id", str(uuid.uuid4()))
        fn = tc.get("function", {})
        tool_id = fn.get("name")
        raw_args = fn.get("arguments", "{}")

        # 1. Parse JSON arguments
        if isinstance(raw_args, str):
            try:
                args_dict = json.loads(raw_args)
            except Exception:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tool_id or "unknown",
                    "content": "Error: Malformed JSON arguments in tool call request.",
                })
                continue
        elif isinstance(raw_args, dict):
            args_dict = raw_args
        else:
            args_dict = {}

        # 2. Check tool exists in registry
        tool_def = registry.get_tool(tool_id) if tool_id else None
        if not tool_def:
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": tool_id or "unknown",
                "content": f"Error: Tool '{tool_id}' is not registered in the system.",
            })
            continue

        # 3. Check tenant permission
        enabled_map = biz_config.get("enabled_tools", {})
        if not enabled_map.get(tool_id, False):
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": tool_id,
                "content": f"Permission denied: Tool '{tool_id}' is not enabled for business '{biz_id}'.",
            })
            continue

        # 4. Validate schema with Pydantic
        try:
            validated_model = tool_def.input_schema.model_validate(args_dict)
            validated_dict = validated_model.model_dump()
        except ValidationError as val_err:
            first_err = val_err.errors()[0]
            field = ".".join(str(loc) for loc in first_err["loc"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": tool_id,
                "content": f"Validation error on field '{field}': {first_err['msg']}",
            })
            continue

        # 5. Two-phase confirmation interception & verbal confirmation handling
        if tool_def.requires_confirmation:
            is_verbally_confirmed = _is_prior_action_confirmed(messages, tool_id)
            if not is_verbally_confirmed:
                action_id = str(uuid.uuid4())
                summary_text = _format_pending_action_summary(tool_id, validated_dict)
                pending_action = {
                    "action_id": action_id,
                    "business_id": biz_id,
                    "tool_id": tool_id,
                    "tool_name": tool_def.name,
                    "arguments": validated_dict,
                    "summary": summary_text,
                    "status": "pending_confirmation",
                }
                friendly_name = "dining reservation" if tool_id == "create_table_booking" else "appointment"
                last_caller_msg = messages[-2].get("content", "") if len(messages) >= 2 else ""
                if detect_language(last_caller_msg) == "hi":
                    confirmation_prompt = (
                        f"मैंने आपकी {friendly_name} की जानकारी तैयार कर ली है:\n\n"
                        f"{summary_text}\n\n"
                        f"क्या मैं इसे आपके लिए कन्फर्म कर दूँ?"
                    )
                else:
                    confirmation_prompt = (
                        f"I've prepared your {friendly_name} details:\n\n"
                        f"{summary_text}\n\n"
                        f"Would you like me to go ahead and confirm this for you?"
                    )
                return {
                    "messages": messages,
                    "pending_action": pending_action,
                    "response_content": confirmation_prompt,
                    "latest_tool_calls": None,
                    "success": True,
                    "error": None,
                }
            else:
                # Verbal confirmation received: caller confirmed in conversation! Execute tool directly.
                result = registry.execute_tool(
                    business_id=biz_id,
                    business_config=biz_config,
                    tool_id=tool_id,
                    input_data=validated_dict,
                    confirmed=True,
                )
                tools_called.append(tool_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tool_id,
                    "content": result.message,
                })
                continue

        # 6. Execute permitted non-confirmation tool
        result = registry.execute_tool(
            business_id=biz_id,
            business_config=biz_config,
            tool_id=tool_id,
            input_data=validated_dict,
            confirmed=False,
        )
        tools_called.append(tool_id)
        messages.append({
            "role": "tool",
            "tool_call_id": tc_id,
            "name": tool_id,
            "content": result.message,
        })

    return {
        "messages": messages,
        "latest_tool_calls": None,
        "tools_called": tools_called,
        "work_completed": True,
        "success": True,
        "error": None,
    }


def finalize_response_node(state: AgentState) -> Dict[str, Any]:
    """
    Node D: Finalize Response
    Packages final workflow output. Never converts errors into successful claims.
    Ensures that when work is done, the caller is informed and asked if they have other queries.
    """
    if not state.get("success", False) or state.get("error"):
        return {
            "success": False,
            "response_content": None,
            "error": state.get("error", "Conversation workflow encountered an error."),
            "pending_action": None,
            "tools_called": state.get("tools_called") or [],
            "work_completed": False,
            "should_terminate": False,
            "followup_intent": None,
        }

    response_content = state.get("response_content", "") or ""
    work_completed = state.get("work_completed", False)
    tools_called = state.get("tools_called") or []
    should_terminate = state.get("should_terminate", False)
    followup_intent = state.get("followup_intent")

    # If work/tools were executed or completed, verify if follow-up question is present
    if (work_completed or len(tools_called) > 0) and response_content and not should_terminate:
        if not is_followup_prompt(response_content):
            lang = detect_language(response_content)
            if lang == "hi":
                followup_q = " क्या मैं आपकी किसी और चीज़ में सहायता कर सकता हूँ?"
            else:
                followup_q = " Is there anything else I can help you with today?"
            response_content = response_content.rstrip() + followup_q

    return {
        "success": True,
        "response_content": response_content,
        "pending_action": state.get("pending_action"),
        "tools_called": tools_called,
        "work_completed": work_completed or len(tools_called) > 0,
        "should_terminate": should_terminate,
        "followup_intent": followup_intent,
        "error": None,
    }


def execute_pending_action(
    business_id: str,
    business_config: Dict[str, Any],
    pending_action: Dict[str, Any],
    confirmed: bool = True,
    tool_registry: Optional[ToolRegistry] = None,
) -> ToolExecutionResult:
    """
    Phase B: Confirm and execute a pending confirmation-required action.
    Enforces active business match and invalidates the pending action upon execution.
    """
    if not confirmed:
        return ToolExecutionResult(
            tool_id=pending_action.get("tool_id", "unknown"),
            status=ToolExecutionStatus.ERROR,
            success=False,
            message="Action was cancelled by the user.",
        )

    if not pending_action or not isinstance(pending_action, dict):
        return ToolExecutionResult(
            tool_id="unknown",
            status=ToolExecutionStatus.ERROR,
            success=False,
            message="No valid pending action found to execute.",
        )

    if pending_action.get("status") != "pending_confirmation":
        return ToolExecutionResult(
            tool_id=pending_action.get("tool_id", "unknown"),
            status=ToolExecutionStatus.ERROR,
            success=False,
            message="This action has already been processed or expired.",
        )

    if pending_action.get("business_id") != business_id:
        return ToolExecutionResult(
            tool_id=pending_action.get("tool_id", "unknown"),
            status=ToolExecutionStatus.ERROR,
            success=False,
            message="Pending action does not belong to the currently active business.",
        )

    registry = tool_registry or get_tool_registry()
    tool_id = pending_action.get("tool_id", "")
    args = pending_action.get("arguments", {})

    # Mark action as executed to prevent double execution
    pending_action["status"] = "executed"

    return registry.execute_tool(
        business_id=business_id,
        business_config=business_config,
        tool_id=tool_id,
        input_data=args,
        confirmed=True,
    )
