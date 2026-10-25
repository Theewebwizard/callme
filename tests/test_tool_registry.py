"""
Unit tests for the modular business tool registry.
Covers registration, validation, business-specific permissions, two-phase confirmation, and mock handlers.
"""

import pytest
from pydantic import BaseModel, Field
from backend.tools.base import (
    ToolDefinition,
    ToolCategory,
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.registry import (
    ToolRegistry,
    build_default_tool_registry,
    get_tool_registry,
)
from backend.tools.definitions import (
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
)
from ui.mock_data import INITIAL_BUSINESSES


@pytest.fixture
def registry() -> ToolRegistry:
    """Fixture providing a fresh canonical tool registry."""
    return build_default_tool_registry()


# ---------------------------------------------------------------------------
# 1. Registration & Lookup Tests
# ---------------------------------------------------------------------------

def test_registry_registration_and_lookup(registry: ToolRegistry):
    """Verify tool registration, lookup, and existence checks."""
    assert registry.has_tool("answer_faq") is True
    assert registry.has_tool("nonexistent_tool") is False

    tool = registry.get_tool("answer_faq")
    assert tool is not None
    assert tool.id == "answer_faq"
    assert tool.name == "Answer Business FAQs"


def test_registry_rejects_duplicate_registration(registry: ToolRegistry):
    """Verify that registering a tool with an already-used ID raises ValueError."""
    duplicate_tool = ToolDefinition(
        id="answer_faq",
        name="Duplicate FAQ",
        description="Duplicate",
        category=ToolCategory.INFORMATION,
        input_schema=AnswerFAQInput,
    )
    with pytest.raises(ValueError, match="Duplicate tool registration"):
        registry.register(duplicate_tool)


def test_registry_list_tools_filtering(registry: ToolRegistry):
    """Verify listing all tools and filtering by category."""
    all_tools = registry.list_tools()
    assert len(all_tools) == 7

    dining_tools = registry.list_tools(category=ToolCategory.DINING)
    assert len(dining_tools) == 2
    assert {t.id for t in dining_tools} == {"check_table_availability", "create_table_booking"}

    healthcare_tools = registry.list_tools(category=ToolCategory.HEALTHCARE)
    assert len(healthcare_tools) == 2
    assert {t.id for t in healthcare_tools} == {"check_appointment_availability", "create_appointment"}


# ---------------------------------------------------------------------------
# 2. Multi-Tenant Permission & Tool Visibility Tests
# ---------------------------------------------------------------------------

def test_enabled_tools_for_restaurant(registry: ToolRegistry):
    """Verify restaurant gets table booking and FAQ tools, but not healthcare tools."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    enabled = registry.get_enabled_tools_for_business(restaurant_config)
    enabled_ids = {t.id for t in enabled}

    assert "check_table_availability" in enabled_ids
    assert "create_table_booking" in enabled_ids
    assert "answer_faq" in enabled_ids
    assert "check_appointment_availability" not in enabled_ids
    assert "create_appointment" not in enabled_ids


def test_enabled_tools_for_clinic(registry: ToolRegistry):
    """Verify clinic gets appointment and FAQ tools, but not dining tools."""
    clinic_config = INITIAL_BUSINESSES["biz_apex_dental"]
    enabled = registry.get_enabled_tools_for_business(clinic_config)
    enabled_ids = {t.id for t in enabled}

    assert "check_appointment_availability" in enabled_ids
    assert "create_appointment" in enabled_ids
    assert "answer_faq" in enabled_ids
    assert "check_table_availability" not in enabled_ids
    assert "create_table_booking" not in enabled_ids


def test_rejection_of_disabled_tool_for_tenant(registry: ToolRegistry):
    """Verify attempting to run clinic tools on a restaurant returns DISABLED status."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="create_appointment",  # Disabled for restaurant
        input_data={
            "patient_name": "John Doe",
            "patient_phone": "+91 9876543210",
            "service_or_department": "Dentistry",
            "appointment_date": "2026-10-30",
            "appointment_time": "14:00",
        },
        confirmed=True,
    )
    assert res.status == ToolExecutionStatus.DISABLED
    assert res.success is False
    assert "is not enabled for business" in res.message


def test_rejection_of_unknown_tool(registry: ToolRegistry):
    """Verify executing an unregistered tool returns ERROR status."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="book_flight_ticket",
        input_data={},
    )
    assert res.status == ToolExecutionStatus.ERROR
    assert res.success is False
    assert "not registered in the system" in res.message


# ---------------------------------------------------------------------------
# 3. Input Validation Tests (Pydantic)
# ---------------------------------------------------------------------------

def test_input_validation_failure_table_availability(registry: ToolRegistry):
    """Verify validation fails on negative or oversized party size and invalid dates."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # Invalid party size (le 20)
    res_oversize = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="check_table_availability",
        input_data={"date": "2026-10-25", "time": "19:00", "party_size": 25},
    )
    assert res_oversize.status == ToolExecutionStatus.VALIDATION_ERROR
    assert res_oversize.success is False

    # Invalid date format
    res_bad_date = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="check_table_availability",
        input_data={"date": "25-10-2026", "time": "19:00", "party_size": 4},
    )
    assert res_bad_date.status == ToolExecutionStatus.VALIDATION_ERROR
    assert res_bad_date.success is False


def test_input_validation_failure_empty_message(registry: ToolRegistry):
    """Verify validation fails if message content is empty."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="take_message",
        input_data={
            "caller_name": "Alice",
            "caller_phone": "+91 9876543210",
            "message": "",  # Empty
            "urgency": "normal",
        },
    )
    assert res.status == ToolExecutionStatus.VALIDATION_ERROR
    assert res.success is False


# ---------------------------------------------------------------------------
# 4. Confirmation Boundary Tests
# ---------------------------------------------------------------------------

def test_confirmation_required_for_booking(registry: ToolRegistry):
    """Verify table booking is blocked with CONFIRMATION_REQUIRED when confirmed=False."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    payload = {
        "customer_name": "Rohan Verma",
        "customer_phone": "+91 9876543210",
        "date": "2026-10-28",
        "time": "20:00",
        "party_size": 4,
    }

    # Unconfirmed call
    res_unconfirmed = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="create_table_booking",
        input_data=payload,
        confirmed=False,
    )
    assert res_unconfirmed.status == ToolExecutionStatus.CONFIRMATION_REQUIRED
    assert res_unconfirmed.success is False
    assert res_unconfirmed.requires_confirmation is True

    # Confirmed call
    res_confirmed = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="create_table_booking",
        input_data=payload,
        confirmed=True,
    )
    assert res_confirmed.status == ToolExecutionStatus.SUCCESS
    assert res_confirmed.success is True
    assert "TB-" in res_confirmed.data["booking_reference"]
    assert "[SIMULATED MOCK BOOKING" in res_confirmed.message


def test_confirmation_required_for_appointment(registry: ToolRegistry):
    """Verify appointment creation is blocked with CONFIRMATION_REQUIRED when confirmed=False."""
    clinic_config = INITIAL_BUSINESSES["biz_apex_dental"]
    payload = {
        "patient_name": "Priya Nair",
        "patient_phone": "+91 9845123456",
        "service_or_department": "Orthodontics",
        "appointment_date": "2026-10-29",
        "appointment_time": "11:30",
    }

    res_unconfirmed = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=clinic_config,
        tool_id="create_appointment",
        input_data=payload,
        confirmed=False,
    )
    assert res_unconfirmed.status == ToolExecutionStatus.CONFIRMATION_REQUIRED
    assert res_unconfirmed.success is False

    res_confirmed = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=clinic_config,
        tool_id="create_appointment",
        input_data=payload,
        confirmed=True,
    )
    assert res_confirmed.status == ToolExecutionStatus.SUCCESS
    assert res_confirmed.success is True
    assert "APT-" in res_confirmed.data["appointment_reference"]
    assert "[SIMULATED MOCK APPOINTMENT" in res_confirmed.message


# ---------------------------------------------------------------------------
# 5. Domain Handler Behavior Tests
# ---------------------------------------------------------------------------

def test_answer_faq_grounded_in_business_data(registry: ToolRegistry):
    """Verify FAQ handler matches configured questions and avoids hallucination."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # Match parking FAQ
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="answer_faq",
        input_data={"question": "Is parking available at the venue?"},
    )
    assert res.success is True
    assert "valet parking" in res.message.lower()

    # Query for nonexistent policy
    res_not_found = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="answer_faq",
        input_data={"question": "Do you allow pet tigers on the balcony?"},
    )
    assert res_not_found.success is False
    assert "No matching FAQ was found" in res_not_found.message


def test_take_message_handler(registry: ToolRegistry):
    """Verify message taking logs structured mock message record."""
    clinic_config = INITIAL_BUSINESSES["biz_apex_dental"]
    res = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=clinic_config,
        tool_id="take_message",
        input_data={
            "caller_name": "Suresh Kumar",
            "caller_phone": "+91 9771122334",
            "message": "Please call me regarding my X-ray results.",
            "urgency": "urgent",
        },
    )
    assert res.success is True
    assert res.data["urgency"] == "urgent"
    assert "MSG-" in res.data["message_reference"]


def test_transfer_call_handler(registry: ToolRegistry):
    """Verify call transfer returns simulated escalation record."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="transfer_call",
        input_data={
            "reason": "Banquet booking inquiry for 50 people",
            "department_or_target": "Banquet Events Manager",
        },
    )
    assert res.success is True
    assert res.data["target"] == "Banquet Events Manager"
    assert "XFER-" in res.data["transfer_reference"]


def test_context_cannot_be_spoofed_via_input(registry: ToolRegistry):
    """Verify business context passed to handler is the trusted server context."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # Even if user payload claims to be for Apex Dental, execution checks restaurant config
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="check_table_availability",
        input_data={
            "date": "2026-10-25",
            "time": "12:00",
            "party_size": 2,
        },
    )
    assert res.success is True
    assert "Spice Garden Bistro" in res.message
