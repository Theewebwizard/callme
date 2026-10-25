"""
Unit tests for Streamlit UI state management and multi-tenant business isolation.
"""

import pytest
import streamlit as st
from ui.state import (
    init_session_state,
    get_all_businesses,
    get_active_business_id,
    set_active_business_id,
    get_active_business,
    update_business_config,
    set_business_tool_status,
    get_call_history_for_business,
    get_playground_messages,
    add_playground_message,
    reset_playground_messages,
    get_pending_action,
    set_pending_action,
    clear_pending_action,
)


@pytest.fixture(autouse=True)
def reset_streamlit_session():
    """Clear session state before each test run."""
    st.session_state.clear()
    init_session_state()


def test_session_state_initialization():
    """Verify that session state contains both sample businesses and catalogues."""
    businesses = get_all_businesses()
    assert "biz_spice_garden" in businesses
    assert "biz_apex_dental" in businesses

    assert businesses["biz_spice_garden"]["industry"] == "Restaurant"
    assert businesses["biz_apex_dental"]["industry"] == "Clinic"


def test_business_switching():
    """Verify that switching active business returns appropriate tenant profile."""
    assert get_active_business_id() == "biz_spice_garden"
    assert get_active_business()["name"] == "Spice Garden Bistro"

    set_active_business_id("biz_apex_dental")
    assert get_active_business_id() == "biz_apex_dental"
    assert get_active_business()["name"] == "Apex Dental & Orthodontics"


def test_independent_tool_configurations():
    """Verify that tool toggling for one business does not alter the other business."""
    # Spice Garden: table booking enabled, clinic appointment disabled
    sg_tools = get_all_businesses()["biz_spice_garden"]["enabled_tools"]
    ad_tools = get_all_businesses()["biz_apex_dental"]["enabled_tools"]

    assert sg_tools["check_table_availability"] is True
    assert sg_tools["check_appointment_availability"] is False

    assert ad_tools["check_table_availability"] is False
    assert ad_tools["check_appointment_availability"] is True

    # Toggle table availability for Apex Dental
    set_business_tool_status("biz_apex_dental", "check_table_availability", True)
    assert get_all_businesses()["biz_apex_dental"]["enabled_tools"]["check_table_availability"] is True
    # Verify Spice Garden remained unchanged
    assert get_all_businesses()["biz_spice_garden"]["enabled_tools"]["check_table_availability"] is True

    # Disable for Spice Garden
    set_business_tool_status("biz_spice_garden", "check_table_availability", False)
    assert get_all_businesses()["biz_spice_garden"]["enabled_tools"]["check_table_availability"] is False
    assert get_all_businesses()["biz_apex_dental"]["enabled_tools"]["check_table_availability"] is True


def test_business_profile_updates_isolation():
    """Verify editing business profile does not contaminate other tenants."""
    update_business_config("biz_spice_garden", {"name": "Royal Spice Garden"})
    assert get_all_businesses()["biz_spice_garden"]["name"] == "Royal Spice Garden"
    # Apex Dental name must remain unchanged
    assert get_all_businesses()["biz_apex_dental"]["name"] == "Apex Dental & Orthodontics"


def test_call_history_isolation():
    """Verify call history records are separated per business."""
    sg_calls = get_call_history_for_business("biz_spice_garden")
    ad_calls = get_call_history_for_business("biz_apex_dental")

    assert len(sg_calls) > 0
    assert len(ad_calls) > 0
    assert sg_calls[0]["id"].startswith("call_sg_")
    assert ad_calls[0]["id"].startswith("call_ad_")


def test_playground_chat_flow():
    """Verify playground chat messaging and reset functions."""
    biz_id = "biz_spice_garden"
    initial_msgs = get_playground_messages(biz_id)
    assert len(initial_msgs) == 1
    assert initial_msgs[0]["role"] == "assistant"

    add_playground_message(biz_id, "user", "I would like to book a table.")
    msgs = get_playground_messages(biz_id)
    assert len(msgs) == 2
    assert msgs[1]["content"] == "I would like to book a table."

    reset_playground_messages(biz_id)
    reset_msgs = get_playground_messages(biz_id)
    assert len(reset_msgs) == 1


def test_pending_action_state_lifecycle():
    """Verify storing, retrieving, and clearing pending actions in session state."""
    biz_id = "biz_spice_garden"
    assert get_pending_action(biz_id) is None

    action_payload = {
        "action_id": "test-act-123",
        "business_id": biz_id,
        "tool_id": "create_table_booking",
        "arguments": {"customer_name": "Test Customer", "party_size": 2},
    }
    set_pending_action(biz_id, action_payload)
    assert get_pending_action(biz_id) == action_payload
    # Other business should not see this action
    assert get_pending_action("biz_apex_dental") is None

    clear_pending_action(biz_id)
    assert get_pending_action(biz_id) is None

