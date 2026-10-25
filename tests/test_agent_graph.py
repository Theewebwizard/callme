"""
Unit tests for the shared LangGraph conversation workflow.
Tests graph construction, node transitions, multi-tenant parameterization, and error handling.
"""

from unittest.mock import MagicMock
import pytest
from backend.agent.state import AgentState
from backend.agent.nodes import (
    prepare_context_node,
    generate_response_node,
    finalize_response_node,
)
from backend.agent.graph import (
    create_receptionist_graph,
    invoke_receptionist_workflow,
)
from backend.services.groq_service import GroqService
from backend.mock_data import INITIAL_BUSINESSES, INITIAL_TOOLS


# ---------------------------------------------------------------------------
# 1. Graph Construction & Node Unit Tests
# ---------------------------------------------------------------------------

def test_create_receptionist_graph_compiles():
    """Verify that the StateGraph compiles without errors."""
    graph = create_receptionist_graph()
    assert graph is not None


def test_prepare_context_node_valid():
    """Verify prepare_context_node constructs system instruction for valid state."""
    state: AgentState = {
        "business_id": "biz_spice_garden",
        "business_config": INITIAL_BUSINESSES["biz_spice_garden"],
        "enabled_tools": INITIAL_TOOLS,
        "messages": [{"role": "user", "content": "What are your hours?"}],
    }
    result = prepare_context_node(state)
    assert result["success"] is True
    assert result["error"] is None
    assert "Spice Garden Bistro" in result["system_instruction"]


def test_prepare_context_node_missing_business_config():
    """Verify prepare_context_node fails safely if business config is missing."""
    state: AgentState = {
        "business_id": "biz_unknown",
        "business_config": {},
        "enabled_tools": {},
        "messages": [{"role": "user", "content": "Hello"}],
    }
    result = prepare_context_node(state)
    assert result["success"] is False
    assert "Missing or invalid business configuration" in result["error"]


def test_prepare_context_node_empty_messages():
    """Verify prepare_context_node fails safely if messages are empty or blank."""
    state: AgentState = {
        "business_id": "biz_spice_garden",
        "business_config": INITIAL_BUSINESSES["biz_spice_garden"],
        "enabled_tools": {},
        "messages": [],
    }
    result = prepare_context_node(state)
    assert result["success"] is False
    assert "Conversation input is empty" in result["error"]


def test_generate_response_node_success():
    """Verify generate_response_node parses output from mock Groq service."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "We are open until 11:00 PM."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    mock_service = GroqService(client=mock_client)
    state: AgentState = {
        "business_id": "biz_spice_garden",
        "business_config": INITIAL_BUSINESSES["biz_spice_garden"],
        "enabled_tools": {},
        "messages": [{"role": "user", "content": "What time do you close?"}],
        "system_instruction": "You are a receptionist.",
        "success": True,
        "error": None,
    }

    result = generate_response_node(state, groq_service=mock_service)
    assert result["success"] is True
    assert result["response_content"] == "We are open until 11:00 PM."


def test_generate_response_node_unconfigured_groq():
    """Verify generate_response_node returns controlled error when key is unconfigured."""
    unconfigured_service = GroqService(api_key="your_groq_api_key_here")
    state: AgentState = {
        "business_id": "biz_spice_garden",
        "business_config": INITIAL_BUSINESSES["biz_spice_garden"],
        "enabled_tools": {},
        "messages": [{"role": "user", "content": "Hello"}],
        "system_instruction": "System instruction",
        "success": True,
        "error": None,
    }

    result = generate_response_node(state, groq_service=unconfigured_service)
    assert result["success"] is False
    assert "Groq API key is not configured" in result["error"]
    assert result["response_content"] is None


def test_finalize_response_node():
    """Verify finalize_response_node handles both success and failure states explicitly."""
    # Success state
    success_state: AgentState = {
        "success": True,
        "response_content": "Thank you for calling.",
        "error": None,
    }
    fin_success = finalize_response_node(success_state)
    assert fin_success["success"] is True
    assert fin_success["response_content"] == "Thank you for calling."

    # Failure state
    failure_state: AgentState = {
        "success": False,
        "response_content": None,
        "error": "API rate limit reached.",
    }
    fin_failure = finalize_response_node(failure_state)
    assert fin_failure["success"] is False
    assert fin_failure["response_content"] is None
    assert fin_failure["error"] == "API rate limit reached."


# ---------------------------------------------------------------------------
# 2. End-to-End Workflow Invocation & Multi-Tenant Tests
# ---------------------------------------------------------------------------

def test_e2e_workflow_restaurant_flow():
    """Verify full graph execution with restaurant tenant profile."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Namaste! Spice Garden Bistro is open until 11:00 PM."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    mock_service = GroqService(client=mock_client)
    restaurant = INITIAL_BUSINESSES["biz_spice_garden"]

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=restaurant,
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "What are your dining hours?"}],
        groq_service=mock_service,
    )

    assert result["success"] is True
    assert result["response_content"] == "Namaste! Spice Garden Bistro is open until 11:00 PM."
    assert "Spice Garden Bistro" in result["system_instruction"]
    assert "Restaurant" in result["system_instruction"]


def test_e2e_workflow_clinic_flow():
    """Verify full graph execution with clinic tenant profile."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello! Apex Dental offers root canals and smile makeovers."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    mock_service = GroqService(client=mock_client)
    clinic = INITIAL_BUSINESSES["biz_apex_dental"]

    result = invoke_receptionist_workflow(
        business_id="biz_apex_dental",
        business_config=clinic,
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "What services do you provide?"}],
        groq_service=mock_service,
    )

    assert result["success"] is True
    assert result["response_content"] == "Hello! Apex Dental offers root canals and smile makeovers."
    assert "Apex Dental & Orthodontics" in result["system_instruction"]
    assert "Clinic" in result["system_instruction"]


def test_single_graph_instance_serves_both_businesses():
    """Verify the same compiled graph instance serves different tenants independently."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Receptionist response."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    mock_service = GroqService(client=mock_client)
    # Single compiled graph instance
    shared_graph = create_receptionist_graph(groq_service=mock_service)

    # 1. Invoke for restaurant
    res_restaurant = shared_graph.invoke({
        "business_id": "biz_spice_garden",
        "business_config": INITIAL_BUSINESSES["biz_spice_garden"],
        "enabled_tools": INITIAL_TOOLS,
        "messages": [{"role": "user", "content": "Table for 2?"}],
        "system_instruction": None,
        "response_content": None,
        "error": None,
        "success": False,
    })

    # 2. Invoke for clinic
    res_clinic = shared_graph.invoke({
        "business_id": "biz_apex_dental",
        "business_config": INITIAL_BUSINESSES["biz_apex_dental"],
        "enabled_tools": INITIAL_TOOLS,
        "messages": [{"role": "user", "content": "Tooth cleaning slot?"}],
        "system_instruction": None,
        "response_content": None,
        "error": None,
        "success": False,
    })

    assert "Spice Garden Bistro" in res_restaurant["system_instruction"]
    assert "Apex Dental & Orthodontics" in res_clinic["system_instruction"]
    assert res_restaurant["business_id"] == "biz_spice_garden"
    assert res_clinic["business_id"] == "biz_apex_dental"


def test_workflow_error_does_not_fabricate_response():
    """Verify that an LLM failure returns success=False and response_content=None."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Internal upstream failure")

    mock_service = GroqService(client=mock_client)
    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Hello"}],
        groq_service=mock_service,
    )

    assert result["success"] is False
    assert result["response_content"] is None
    assert "error" in result
    assert result["error"] is not None
