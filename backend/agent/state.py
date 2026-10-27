"""
Domain models and LangGraph state schema for the shared AI Receptionist conversation workflow.
Provides strongly-typed schemas for conversation turns, tool calls, execution budgets,
two-phase pending actions, and workflow lifecycle tracking.
"""

from enum import Enum
import time
from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class WorkflowStatus(str, Enum):
    """Execution status lifecycle of the receptionist conversation graph."""
    INITIALIZED = "initialized"
    PREPARING = "preparing"
    PROCESSING_LLM = "processing_llm"
    EXECUTING_TOOLS = "executing_tools"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    FAILED = "failed"


class ToolCallFunction(BaseModel):
    """Specification of the function invoked by the LLM tool call."""
    name: str
    arguments: str

    model_config = ConfigDict(extra="ignore")


class ToolCallRequest(BaseModel):
    """Validated model for tool calls emitted by the LLM."""
    id: str
    type: str = "function"
    function: ToolCallFunction

    model_config = ConfigDict(extra="ignore")


class ConversationMessage(BaseModel):
    """Standardized conversation turn representation."""
    role: str  # "system", "user", "assistant", "tool"
    content: Optional[str] = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class PendingActionPayload(BaseModel):
    """Validated payload for an action awaiting user or staff confirmation."""
    action_id: str
    business_id: str
    session_id: Optional[str] = None
    tool_id: str
    tool_name: str
    arguments: Dict[str, Any]
    summary: str
    status: str = "pending_confirmation"  # "pending_confirmation", "executed", "cancelled", "expired"
    created_at: Optional[str] = None
    expires_at: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class AgentExecutionBudget(BaseModel):
    """
    Execution budget tracking and boundaries to strictly prevent unbounded recursion,
    infinite tool loops, and excessive LLM billing.
    """
    max_llm_turns: int = 5
    max_tool_rounds: int = 5
    max_execution_seconds: float = 60.0
    start_timestamp: float = Field(default_factory=time.time)
    llm_turns_completed: int = 0
    tool_rounds_completed: int = 0

    def is_exceeded(self) -> bool:
        """Evaluate if any boundary of the execution budget has been exhausted."""
        if self.llm_turns_completed >= self.max_llm_turns:
            return True
        if self.tool_rounds_completed >= self.max_tool_rounds:
            return True
        if (time.time() - self.start_timestamp) > self.max_execution_seconds:
            return True
        return False

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_timestamp

    model_config = ConfigDict(extra="ignore")


class AgentState(TypedDict, total=False):
    """
    Canonical State schema for the receptionist conversation workflow.
    Tracks tenant context, conversation turns, tool calls, confirmation states,
    and bounded execution budgets.
    """
    business_id: str
    session_id: Optional[str]
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
    workflow_status: Optional[str]
    budget: Optional[Dict[str, Any]]
