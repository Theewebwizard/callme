"""
LangGraph conversation workflow graph construction and execution.
Implements bounded tool-calling loop, conditional routing, and two-phase confirmation.
"""

from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from backend.agent.state import AgentState
from backend.agent.nodes import (
    prepare_context_node,
    call_llm_node,
    execute_tools_node,
    finalize_response_node,
    execute_pending_action,
)
from backend.services.groq_service import GroqService
from backend.tools.registry import ToolRegistry


def route_after_prepare_context(state: AgentState) -> str:
    """
    Conditional router after prepare_context.
    If a semantic farewell or direct follow-up prompt was resolved,
    routes directly to finalize_response without redundant LLM roundtrips.
    """
    if not state.get("success", False) or state.get("error"):
        return "finalize_response"

    if state.get("response_content") and (state.get("should_terminate") or state.get("followup_intent") == "has_further_query"):
        return "finalize_response"

    return "call_llm"


def route_after_llm(state: AgentState) -> str:
    """
    Conditional edge router evaluating LLM generation outcome.
    Routes to execute_tools if tool calls requested, otherwise finalizes.
    """
    if not state.get("success", False) or state.get("error"):
        return "finalize_response"

    if state.get("pending_action"):
        return "finalize_response"

    if state.get("should_terminate"):
        return "finalize_response"

    tool_calls = state.get("latest_tool_calls")
    if tool_calls:
        # Bounded execution: at most 5 loop iterations
        if state.get("iteration_count", 0) >= 5:
            return "finalize_response"
        return "execute_tools"

    return "finalize_response"


def route_after_tools(state: AgentState) -> str:
    """
    Conditional edge router evaluating tool execution outcome.
    If a confirmation action was prepared, stops to await user confirmation.
    Otherwise loops back to call_llm with the tool results.
    """
    if not state.get("success", False) or state.get("error"):
        return "finalize_response"

    # Stop and present confirmation controls if an action is pending
    if state.get("pending_action"):
        return "finalize_response"

    return "call_llm"


def create_receptionist_graph(
    groq_service: Optional[GroqService] = None,
    tool_registry: Optional[ToolRegistry] = None,
) -> CompiledStateGraph:
    """
    Construct and compile the stateful LangGraph conversation workflow.
    Topology:
      START -> prepare_context -> call_llm -> (decision)
         ↳ execute_tools -> (decision) -> call_llm (loop)
         ↳ finalize_response -> END
    """
    workflow = StateGraph(AgentState)

    # 1. Register Nodes
    workflow.add_node(
        "prepare_context",
        lambda state: prepare_context_node(state, tool_registry=tool_registry),
    )
    workflow.add_node(
        "call_llm",
        lambda state: call_llm_node(state, groq_service=groq_service),
    )
    workflow.add_node(
        "execute_tools",
        lambda state: execute_tools_node(state, tool_registry=tool_registry),
    )
    workflow.add_node("finalize_response", finalize_response_node)

    # 2. Connect Edges
    workflow.add_edge(START, "prepare_context")
    workflow.add_conditional_edges(
        "prepare_context",
        route_after_prepare_context,
        {
            "call_llm": "call_llm",
            "finalize_response": "finalize_response",
        },
    )

    # Conditional routing after LLM response
    workflow.add_conditional_edges(
        "call_llm",
        route_after_llm,
        {
            "execute_tools": "execute_tools",
            "finalize_response": "finalize_response",
        },
    )

    # Conditional routing after Tool execution
    workflow.add_conditional_edges(
        "execute_tools",
        route_after_tools,
        {
            "call_llm": "call_llm",
            "finalize_response": "finalize_response",
        },
    )

    workflow.add_edge("finalize_response", END)

    return workflow.compile()


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
    Initializes state and executes the compiled LangGraph workflow.
    """
    graph = create_receptionist_graph(
        groq_service=groq_service,
        tool_registry=tool_registry,
    )

    initial_state: AgentState = {
        "business_id": business_id,
        "business_config": business_config or {},
        "enabled_tools": enabled_tools or {},
        "messages": messages or [],
        "system_instruction": None,
        "response_content": None,
        "error": None,
        "success": False,
        "iteration_count": 0,
        "pending_action": None,
        "latest_tool_calls": None,
        "work_completed": False,
        "should_terminate": False,
        "followup_intent": None,
        "tools_called": [],
    }

    return graph.invoke(initial_state)
