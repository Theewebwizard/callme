"""
LangGraph state definitions for the shared AI Receptionist conversation workflow.
Supports tool-calling execution loops and two-phase confirmation states.
"""

from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict, total=False):
    """
    State schema for the receptionist conversation workflow.
    Tracks tenant context, conversation turns, tool calls, and confirmation states.
    """
    business_id: str
    business_config: Dict[str, Any]
    enabled_tools: Dict[str, Any]
    messages: List[Dict[str, Any]]
    system_instruction: Optional[str]
    response_content: Optional[str]
    error: Optional[str]
    success: bool
    tool_definitions: Optional[List[Dict[str, Any]]]
    pending_action: Optional[Dict[str, Any]]
    iteration_count: int
    latest_tool_calls: Optional[List[Dict[str, Any]]]
    work_completed: Optional[bool]
    should_terminate: Optional[bool]
    followup_intent: Optional[str]
    tools_called: Optional[List[str]]
