"""
Unit tests for Step 6: Connecting LangGraph to the Modular Tool Registry.
Covers tool calling, execution loops, multi-tenant authorization, two-phase confirmation, and boundaries.
Uses mock Groq clients and deterministic handlers with no external network calls.
"""

from unittest.mock import MagicMock
import json
import pytest

from backend.agent.graph import (
    create_receptionist_graph,
    invoke_receptionist_workflow,
)
from backend.agent.nodes import execute_pending_action
from backend.services.groq_service import GroqService
from backend.tools.base import ToolExecutionStatus
from backend.tools.registry import build_default_tool_registry
from backend.mock_data import INITIAL_BUSINESSES, INITIAL_TOOLS


@pytest.fixture
def registry():
    return build_default_tool_registry()


# ---------------------------------------------------------------------------
# 1. LLM Tool Calling and Loop Execution Tests
# ---------------------------------------------------------------------------

def test_graph_executes_single_tool_and_returns_final_answer(registry):
    """Verify tool call request is executed and LLM formulates final answer using the result."""
    mock_client = MagicMock()

    # Turn 1: LLM requests check_table_availability
    choice_1 = MagicMock()
    choice_1.message.content = ""
    mock_tc = MagicMock()
    mock_tc.id = "call_tbl_123"
    mock_tc.function.name = "check_table_availability"
    mock_tc.function.arguments = json.dumps({"date": "2026-10-25", "time": "19:30", "party_size": 4})
    choice_1.message.tool_calls = [mock_tc]
    resp_1 = MagicMock(choices=[choice_1])

    # Turn 2: LLM receives tool output and responds with final text
    choice_2 = MagicMock()
    choice_2.message.content = "Great news! We have tables available for 4 guests tomorrow at 7:30 PM."
    choice_2.message.tool_calls = None
    resp_2 = MagicMock(choices=[choice_2])

    mock_client.chat.completions.create.side_effect = [resp_1, resp_2]
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Do you have a table for 4 tomorrow at 7:30 PM?"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    assert result["success"] is True
    assert "tables available for 4 guests" in result["response_content"]
    assert mock_client.chat.completions.create.call_count == 2

    # Verify tool result was inserted into message history
    tool_messages = [m for m in result["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_tbl_123"
    assert "Tables are available" in tool_messages[0]["content"]


def test_graph_enforces_maximum_iteration_limit(registry):
    """Verify the tool loop terminates when the maximum iteration limit (5) is reached."""
    mock_client = MagicMock()

    # Configure LLM to always request a tool call endlessly
    def make_tool_choice():
        choice = MagicMock()
        choice.message.content = ""
        mock_tc = MagicMock()
        mock_tc.id = "call_loop"
        mock_tc.function.name = "check_table_availability"
        mock_tc.function.arguments = json.dumps({"date": "2026-10-25", "time": "19:00", "party_size": 2})
        choice.message.tool_calls = [mock_tc]
        return MagicMock(choices=[choice])

    mock_client.chat.completions.create.side_effect = [make_tool_choice() for _ in range(10)]
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Check availability endlessly"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    # Should stop after hitting the iteration bound (5)
    assert result["iteration_count"] == 5
    assert mock_client.chat.completions.create.call_count == 5


def test_graph_handles_malformed_json_arguments_gracefully(registry):
    """Verify malformed JSON arguments return an error result to LLM without crashing."""
    mock_client = MagicMock()

    # Turn 1: Malformed JSON
    choice_1 = MagicMock()
    choice_1.message.content = ""
    mock_tc = MagicMock()
    mock_tc.id = "call_malformed"
    mock_tc.function.name = "check_table_availability"
    mock_tc.function.arguments = "{bad_json: missing_quotes"
    choice_1.message.tool_calls = [mock_tc]
    resp_1 = MagicMock(choices=[choice_1])

    # Turn 2: LLM recovery
    choice_2 = MagicMock()
    choice_2.message.content = "Could you please clarify the date and party size?"
    choice_2.message.tool_calls = None
    resp_2 = MagicMock(choices=[choice_2])

    mock_client.chat.completions.create.side_effect = [resp_1, resp_2]
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Book table"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    assert result["success"] is True
    tool_messages = [m for m in result["messages"] if m.get("role") == "tool"]
    assert "Malformed JSON" in tool_messages[0]["content"]


# ---------------------------------------------------------------------------
# 2. Authorization, Permissions, and Multi-Tenant Isolation
# ---------------------------------------------------------------------------

def test_restaurant_cannot_execute_clinic_only_tool(registry):
    """Verify that a restaurant cannot execute create_appointment even if requested by LLM."""
    mock_client = MagicMock()

    choice_1 = MagicMock()
    choice_1.message.content = ""
    mock_tc = MagicMock()
    mock_tc.id = "call_illegal"
    mock_tc.function.name = "create_appointment"
    mock_tc.function.arguments = json.dumps({
        "patient_name": "Rohan",
        "patient_phone": "+91 9876543210",
        "service_or_department": "Dentistry",
        "appointment_date": "2026-10-30",
        "appointment_time": "15:00",
    })
    choice_1.message.tool_calls = [mock_tc]
    resp_1 = MagicMock(choices=[choice_1])

    choice_2 = MagicMock()
    choice_2.message.content = "I apologize, Spice Garden Bistro does not offer clinical appointments."
    choice_2.message.tool_calls = None
    resp_2 = MagicMock(choices=[choice_2])

    mock_client.chat.completions.create.side_effect = [resp_1, resp_2]
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "I want an appointment with the dentist"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    # Tool message must show permission denied
    tool_msgs = [m for m in result["messages"] if m.get("role") == "tool"]
    assert "Permission denied" in tool_msgs[0]["content"]
    assert "not enabled for business 'biz_spice_garden'" in tool_msgs[0]["content"]


def test_disabled_tool_is_rejected_at_runtime(registry):
    """Verify tool toggled off in business config is rejected when called."""
    mock_client = MagicMock()

    # Copy restaurant config and disable take_message
    custom_biz = dict(INITIAL_BUSINESSES["biz_spice_garden"])
    custom_biz["enabled_tools"] = dict(custom_biz["enabled_tools"])
    custom_biz["enabled_tools"]["take_message"] = False

    choice_1 = MagicMock()
    choice_1.message.content = ""
    mock_tc = MagicMock()
    mock_tc.id = "call_disabled"
    mock_tc.function.name = "take_message"
    mock_tc.function.arguments = json.dumps({
        "caller_name": "Bob",
        "caller_phone": "+91 9888877777",
        "message": "Please call me back",
        "urgency": "normal",
    })
    choice_1.message.tool_calls = [mock_tc]
    resp_1 = MagicMock(choices=[choice_1])

    choice_2 = MagicMock()
    choice_2.message.content = "Message taking is currently disabled."
    choice_2.message.tool_calls = None
    resp_2 = MagicMock(choices=[choice_2])

    mock_client.chat.completions.create.side_effect = [resp_1, resp_2]
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=custom_biz,
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Take a message for the manager"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    tool_msgs = [m for m in result["messages"] if m.get("role") == "tool"]
    assert "Permission denied: Tool 'take_message' is not enabled" in tool_msgs[0]["content"]


# ---------------------------------------------------------------------------
# 3. Two-Phase Confirmation Boundary Tests
# ---------------------------------------------------------------------------

def test_booking_request_creates_pending_action_without_execution(registry):
    """Verify create_table_booking halts with a pending_action record and does not execute."""
    mock_client = MagicMock()

    choice_1 = MagicMock()
    choice_1.message.content = ""
    mock_tc = MagicMock()
    mock_tc.id = "call_booking_req"
    mock_tc.function.name = "create_table_booking"
    mock_tc.function.arguments = json.dumps({
        "customer_name": "Anita Desai",
        "customer_phone": "+91 9876543210",
        "date": "2026-10-28",
        "time": "20:00",
        "party_size": 4,
        "special_requests": "Window table",
    })
    choice_1.message.tool_calls = [mock_tc]
    mock_client.chat.completions.create.return_value = MagicMock(choices=[choice_1])
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Please reserve a table for 4 under Anita Desai on Oct 28 at 8pm"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    assert result["success"] is True
    # Must have pending_action populated
    pending = result["pending_action"]
    assert pending is not None
    assert pending["tool_id"] == "create_table_booking"
    assert pending["status"] == "pending_confirmation"
    assert pending["business_id"] == "biz_spice_garden"
    assert pending["arguments"]["customer_name"] == "Anita Desai"
    assert pending["arguments"]["party_size"] == 4

    # The action was NOT yet executed through the registry
    assert "Please click **Confirm** or **Cancel**" in result["response_content"]


def test_appointment_request_creates_pending_action_without_execution(registry):
    """Verify create_appointment halts with a pending_action record and does not execute."""
    mock_client = MagicMock()

    choice_1 = MagicMock()
    choice_1.message.content = ""
    mock_tc = MagicMock()
    mock_tc.id = "call_apt_req"
    mock_tc.function.name = "create_appointment"
    mock_tc.function.arguments = json.dumps({
        "patient_name": "Vikram Singh",
        "patient_phone": "+91 9988776655",
        "service_or_department": "Orthodontics",
        "appointment_date": "2026-10-31",
        "appointment_time": "11:00",
        "notes": "Aligner consultation",
    })
    choice_1.message.tool_calls = [mock_tc]
    mock_client.chat.completions.create.return_value = MagicMock(choices=[choice_1])
    mock_service = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_apex_dental",
        business_config=INITIAL_BUSINESSES["biz_apex_dental"],
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "Book an orthodontic appointment for Vikram on Oct 31 at 11am"}],
        groq_service=mock_service,
        tool_registry=registry,
    )

    assert result["success"] is True
    pending = result["pending_action"]
    assert pending is not None
    assert pending["tool_id"] == "create_appointment"
    assert pending["status"] == "pending_confirmation"
    assert pending["business_id"] == "biz_apex_dental"


def test_phase_b_execute_pending_action_lifecycle(registry):
    """Verify confirming pending action commits simulation; duplicate execution is blocked."""
    pending = {
        "action_id": "test_act_123",
        "business_id": "biz_spice_garden",
        "tool_id": "create_table_booking",
        "tool_name": "Create Table Booking",
        "arguments": {
            "customer_name": "Kavita Roy",
            "customer_phone": "+91 9777711111",
            "date": "2026-11-01",
            "time": "19:00",
            "party_size": 2,
        },
        "status": "pending_confirmation",
    }

    # 1. Successful execution with confirmed=True
    exec_res = execute_pending_action(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        pending_action=pending,
        confirmed=True,
        tool_registry=registry,
    )

    assert exec_res.success is True
    assert exec_res.status == ToolExecutionStatus.SUCCESS
    assert "TB-" in exec_res.data["booking_reference"]
    assert pending["status"] == "executed"

    # 2. Duplicate submission attempt is rejected
    dup_res = execute_pending_action(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        pending_action=pending,
        confirmed=True,
        tool_registry=registry,
    )
    assert dup_res.success is False
    assert "already been processed" in dup_res.message


def test_pending_action_rejected_if_switched_business(registry):
    """Verify an action created for restaurant cannot execute under clinic context."""
    pending = {
        "action_id": "cross_biz_act",
        "business_id": "biz_spice_garden",
        "tool_id": "create_table_booking",
        "arguments": {
            "customer_name": "Sneha",
            "customer_phone": "+91 9888800000",
            "date": "2026-11-02",
            "time": "18:00",
            "party_size": 2,
        },
        "status": "pending_confirmation",
    }

    # Attempt to execute under Apex Dental
    res = execute_pending_action(
        business_id="biz_apex_dental",
        business_config=INITIAL_BUSINESSES["biz_apex_dental"],
        pending_action=pending,
        confirmed=True,
        tool_registry=registry,
    )

    assert res.success is False
    assert "does not belong to the currently active business" in res.message


def test_pending_action_cancellation(registry):
    """Verify user cancellation returns a failed/cancelled outcome without executing."""
    pending = {
        "action_id": "cancel_act",
        "business_id": "biz_spice_garden",
        "tool_id": "create_table_booking",
        "arguments": {},
        "status": "pending_confirmation",
    }

    res = execute_pending_action(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        pending_action=pending,
        confirmed=False,  # User clicked Cancel
        tool_registry=registry,
    )

    assert res.success is False
    assert "cancelled by the user" in res.message
