"""
LangGraph conversation workflow graph construction, validation, and execution.
Implements bounded tool-calling loop, explicit conditional routing, execution budget enforcement,
and two-phase confirmation guards for the AI Receptionist system.

Graph Topology:
  START
    │
    ▼
 [prepare_context]
    │
    ├── (terminal farewell / pure continuation prompt / error) ──► [finalize_response] ──► END
    │
    ▼
  [call_llm] ◄─────────────────────────────────────────────┐
    │                                                      │
    ├── (no tool calls / should_terminate / budget limit)  │
    │         │                                            │
    │         ▼                                            │
    │    [finalize_response] ──► END                       │
    │                                                      │
    ▼ (tool calls requested)                               │
 [execute_tools]                                           │
    │                                                      │
    ├── (action requires confirmation / budget limit)      │
    │         │                                            │
    │         ▼                                            │
    │    [finalize_response] ──► END                       │
    │                                                      │
    └── (tools executed, return results to LLM) ───────────┘
"""

from enum import Enum
import logging
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from backend.agent.state import AgentState, AgentExecutionBudget, WorkflowStatus
from backend.agent.nodes import (
    prepare_context_node,
    call_llm_node,
    execute_tools_node,
    finalize_response_node,
    execute_pending_action,
)
from backend.services.groq_service import GroqService
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class RoutingDestination(str, Enum):
    """Explicit conditional edge routing targets for testability and safety."""
    CALL_LLM = "call_llm"
    EXECUTE_TOOLS = "execute_tools"
    FINALIZE_RESPONSE = "finalize_response"


def route_after_prepare_context(state: AgentState) -> str:
    """
    Conditional edge router following context preparation.
    
    Routing Logic:
    1. If preparation failed or an error is present -> finalize_response.
    2. If a terminal response was formed (e.g. caller farewell) -> finalize_response.
    3. If a direct follow-up prompt was produced for a pure continuation (e.g. caller answered 'yes'
       without posing a question yet) -> finalize_response.
    4. Otherwise (new inquiry, first turn, caller question) -> call_llm.
    """
    if not state.get("success", False) or state.get("error"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    # Terminal state (farewell or explicit exit)
    if state.get("should_terminate"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    # Direct short-circuit response generated for pure affirmative continuation prompt
    if state.get("response_content") and state.get("followup_intent") == "has_further_query":
        return RoutingDestination.FINALIZE_RESPONSE.value

    return RoutingDestination.CALL_LLM.value


def route_after_llm(state: AgentState) -> str:
    """
    Conditional edge router evaluating LLM generation outcome.
    
    Routing Logic:
    1. If LLM call failed or returned error -> finalize_response.
    2. If state requires termination or pending action is set -> finalize_response.
    3. If tool calls requested:
       - Check execution budget (turns and wall-clock timeout). If exceeded -> finalize_response.
       - Otherwise -> execute_tools.
    4. Otherwise (plain conversational answer) -> finalize_response.
    """
    if not state.get("success", False) or state.get("error"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    if state.get("pending_action"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    if state.get("should_terminate"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    tool_calls = state.get("latest_tool_calls")
    if tool_calls:
        # Check execution budget limits
        budget_dict = state.get("budget")
        if budget_dict and isinstance(budget_dict, dict):
            try:
                budget = AgentExecutionBudget.model_validate(budget_dict)
                if budget.is_exceeded():
                    logger.info("Routing to finalize_response due to budget exhaustion.")
                    return RoutingDestination.FINALIZE_RESPONSE.value
            except Exception:
                pass

        # Fallback counter check to strictly prevent infinite looping
        if state.get("iteration_count", 0) >= 5:
            return RoutingDestination.FINALIZE_RESPONSE.value

        return RoutingDestination.EXECUTE_TOOLS.value

    return RoutingDestination.FINALIZE_RESPONSE.value


def route_after_tools(state: AgentState) -> str:
    """
    Conditional edge router evaluating tool execution outcome.
    
    Routing Logic:
    1. If tool execution errored -> finalize_response.
    2. If action requires human confirmation (pending_action set) -> finalize_response.
    3. If execution budget exceeded or should_terminate -> finalize_response.
    4. Otherwise -> loop back to call_llm with tool observations.
    """
    if not state.get("success", False) or state.get("error"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    if state.get("pending_action"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    if state.get("should_terminate"):
        return RoutingDestination.FINALIZE_RESPONSE.value

    budget_dict = state.get("budget")
    if budget_dict and isinstance(budget_dict, dict):
        try:
            budget = AgentExecutionBudget.model_validate(budget_dict)
            if budget.is_exceeded():
                return RoutingDestination.FINALIZE_RESPONSE.value
        except Exception:
            pass

    return RoutingDestination.CALL_LLM.value


def create_receptionist_graph(
    groq_service: Optional[GroqService] = None,
    tool_registry: Optional[ToolRegistry] = None,
) -> CompiledStateGraph:
    """
    Construct and compile the stateful LangGraph conversation workflow.
    Dependencies (GroqService, ToolRegistry) can be injected for deterministic testing
    or left as None for dynamic runtime resolution.
    """
    workflow = StateGraph(AgentState)

    # 1. Register Nodes
    workflow.add_node(
        "prepare_context",
        lambda state: prepare_context_node(state, tool_registry=tool_registry, groq_service=groq_service),
    )
    workflow.add_node(
        "call_llm",
        lambda state: call_llm_node(state, groq_service=groq_service),
    )
    workflow.add_node(
        "execute_tools",
        lambda state: execute_tools_node(state, tool_registry=tool_registry, groq_service=groq_service),
    )
    workflow.add_node("finalize_response", finalize_response_node)

    # 2. Connect Edges
    workflow.add_edge(START, "prepare_context")
    workflow.add_conditional_edges(
        "prepare_context",
        route_after_prepare_context,
        {
            RoutingDestination.CALL_LLM.value: "call_llm",
            RoutingDestination.FINALIZE_RESPONSE.value: "finalize_response",
        },
    )

    workflow.add_conditional_edges(
        "call_llm",
        route_after_llm,
        {
            RoutingDestination.EXECUTE_TOOLS.value: "execute_tools",
            RoutingDestination.FINALIZE_RESPONSE.value: "finalize_response",
        },
    )

    workflow.add_conditional_edges(
        "execute_tools",
        route_after_tools,
        {
            RoutingDestination.CALL_LLM.value: "call_llm",
            RoutingDestination.FINALIZE_RESPONSE.value: "finalize_response",
        },
    )

    workflow.add_edge("finalize_response", END)

    return workflow.compile()


# Thread-safe compiled graph cache for standard runtime reuse
_cached_compiled_graph: Optional[CompiledStateGraph] = None


def get_compiled_receptionist_graph(refresh: bool = False) -> CompiledStateGraph:
    """
    Return a pre-compiled singleton instance of the conversation graph.
    Safely shared across requests because workflow state is passed per invocation
    without cross-tenant mutable state leakage.
    """
    global _cached_compiled_graph
    if _cached_compiled_graph is None or refresh:
        _cached_compiled_graph = create_receptionist_graph()
    return _cached_compiled_graph


def invoke_receptionist_workflow(
    business_id: str,
    business_config: Dict[str, Any],
    enabled_tools: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    groq_service: Optional[GroqService] = None,
    tool_registry: Optional[ToolRegistry] = None,
) -> Dict[str, Any]:
    """
    Convenience function to execute the receptionist conversation workflow for a tenant.
    Reuses pre-compiled graph for production throughput when standard dependencies are used.
    """
    # If custom dependencies were injected (e.g. in test suites), compile a custom graph instance
    if groq_service is not None or tool_registry is not None:
        graph = create_receptionist_graph(groq_service=groq_service, tool_registry=tool_registry)
    else:
        graph = get_compiled_receptionist_graph()

    initial_state: AgentState = {
        "business_id": business_id,
        "business_config": business_config,
        "enabled_tools": enabled_tools if enabled_tools is not None else business_config.get("enabled_tools", {}),
        "messages": messages or [],
        "iteration_count": 0,
        "success": True,
        "tools_called": [],
        "workflow_status": WorkflowStatus.INITIALIZED.value,
    }

    return graph.invoke(initial_state)
