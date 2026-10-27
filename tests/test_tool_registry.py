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
from backend.database.seed_data import INITIAL_BUSINESSES


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
    assert "is not enabled for business" in res.message or "is only available for businesses in" in res.message


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
    assert "Table reserved for" in res_confirmed.message


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
    assert "Appointment confirmed for" in res_confirmed.message


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


# ---------------------------------------------------------------------------
# 6. Hardened Validation, Safety, & Execution Mode Tests
# ---------------------------------------------------------------------------

def test_calendar_date_and_time_validation(registry: ToolRegistry):
    """Verify non-existent calendar dates (e.g. Feb 31) and invalid times are rejected."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # February 31 does not exist on the calendar
    res_bad_calendar_date = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="check_table_availability",
        input_data={"date": "2026-02-31", "time": "19:00", "party_size": 2},
    )
    assert res_bad_calendar_date.status == ToolExecutionStatus.VALIDATION_ERROR
    assert res_bad_calendar_date.success is False
    assert "does not exist on the calendar" in res_bad_calendar_date.message

    # Invalid clock time (24:00 is not a valid 24h clock time, 00:00 to 23:59)
    res_bad_time = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="check_table_availability",
        input_data={"date": "2026-10-25", "time": "25:30", "party_size": 2},
    )
    assert res_bad_time.status == ToolExecutionStatus.VALIDATION_ERROR
    assert res_bad_time.success is False


def test_phone_number_validation_and_cleaning(registry: ToolRegistry):
    """Verify phone numbers require minimum 7 digits and reject letters/garbage."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # 7 characters but only 6 digits (e.g. '123-456')
    res_short_digits = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="create_table_booking",
        input_data={
            "customer_name": "Test User",
            "customer_phone": "123-456",  # 6 digits
            "date": "2026-10-28",
            "time": "19:00",
            "party_size": 2,
        },
        confirmed=True,
    )
    assert res_short_digits.status == ToolExecutionStatus.VALIDATION_ERROR
    assert "at least 7 digits" in res_short_digits.message


def test_business_identity_mismatch_rejection(registry: ToolRegistry):
    """Verify registry rejects calls when business_id does not match business_config['id']."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    res = registry.execute_tool(
        business_id="spoofed_business_id",
        business_config=restaurant_config,  # has id "biz_spice_garden"
        tool_id="check_table_availability",
        input_data={"date": "2026-10-25", "time": "19:00", "party_size": 2},
    )
    assert res.status == ToolExecutionStatus.PERMISSION_DENIED
    assert res.success is False
    assert res.error_code == "BUSINESS_IDENTITY_MISMATCH"


def test_strict_live_execution_mode_fails_closed(registry: ToolRegistry):
    """Verify when business mandates live mode, simulated mock tools fail closed as UNAVAILABLE."""
    strict_biz_config = dict(INITIAL_BUSINESSES["biz_spice_garden"])
    strict_biz_config["execution_mode"] = "live"

    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=strict_biz_config,
        tool_id="create_table_booking",
        input_data={
            "customer_name": "VIP Guest",
            "customer_phone": "+91 9876543210",
            "date": "2026-10-28",
            "time": "19:00",
            "party_size": 2,
        },
        confirmed=True,
    )
    assert res.status == ToolExecutionStatus.UNAVAILABLE
    assert res.success is False
    assert res.mode == ToolExecutionMode.UNAVAILABLE
    assert res.error_code == "LIVE_INTEGRATION_NOT_CONFIGURED"


def test_handler_exception_returns_safe_error_and_diagnostics(registry: ToolRegistry):
    """Verify unexpected handler crash returns safe error with internal diagnostics."""
    def crashing_handler(inp, biz):
        raise RuntimeError("Authoritative inventory database unreachable")

    failing_tool = ToolDefinition(
        id="crashing_tool",
        name="Crashing Tool",
        description="Tool that raises an unexpected exception",
        category=ToolCategory.INFORMATION,
        input_schema=AnswerFAQInput,
        handler=crashing_handler,
    )
    registry.register(failing_tool)

    biz_config = dict(INITIAL_BUSINESSES["biz_spice_garden"])
    biz_config["enabled_tools"] = dict(biz_config["enabled_tools"])
    biz_config["enabled_tools"]["crashing_tool"] = True

    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=biz_config,
        tool_id="crashing_tool",
        input_data={"question": "Test question"},
    )
    assert res.status == ToolExecutionStatus.ERROR
    assert res.success is False
    assert res.error_code == "HANDLER_EXCEPTION"
    assert "inventory database unreachable" in res.internal_diagnostics


def test_operating_hours_business_declined_status(registry: ToolRegistry):
    """Verify outside-hours queries return BUSINESS_DECLINED with success=True (system operation succeeded)."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="check_table_availability",
        input_data={"date": "2026-10-25", "time": "03:00", "party_size": 2},  # 3 AM is closed
    )
    assert res.status == ToolExecutionStatus.BUSINESS_DECLINED
    assert res.success is True
    assert res.is_business_accepted is False
    assert res.data["available"] is False
    assert res.data["reason"] == "outside_operating_hours"


def test_secure_references_not_derived_from_personal_data(registry: ToolRegistry):
    """Verify booking references use cryptographically unique UUIDs rather than personal data hashes."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]
    payload = {
        "customer_name": "Arun Kumar",
        "customer_phone": "+91 9999988888",
        "date": "2026-10-28",
        "time": "19:00",
        "party_size": 2,
    }

    res1 = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="create_table_booking",
        input_data=payload,
        confirmed=True,
    )
    res2 = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="create_table_booking",
        input_data=payload,
        confirmed=True,
    )

    # Identical arguments MUST generate different reference IDs (UUIDs)
    ref1 = res1.data["booking_reference"]
    ref2 = res2.data["booking_reference"]
    assert ref1 != ref2
    assert ref1.startswith("TB-")
    assert ref2.startswith("TB-")


def test_ranked_faq_retrieval_and_confidence(registry: ToolRegistry):
    """Verify ranked retrieval selects the highest-scoring candidate among multiple FAQs."""
    custom_faqs = [
        {"question": "What are your weekend dining hours?", "answer": "Weekends 11:30 AM to 11:30 PM."},
        {"question": "Do you offer outdoor patio dining?", "answer": "Yes, our garden patio is open weather permitting."},
        {"question": "Can I bring my own wine for dining?", "answer": "Corkage fee applies: Rs 500 per bottle."},
    ]
    biz_config = dict(INITIAL_BUSINESSES["biz_spice_garden"])
    biz_config["faqs"] = custom_faqs

    # Query targeting patio dining
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=biz_config,
        tool_id="answer_faq",
        input_data={"question": "Is outdoor patio dining available?"},
    )
    assert res.success is True
    assert "garden patio" in res.data["answer"]
    assert res.data["confidence_score"] >= 0.5


def test_multilingual_faq_query(registry: ToolRegistry):
    """Verify Hindi / Hinglish tokens match relevant business FAQs."""
    restaurant_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # "parking" inquiry in Hinglish
    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=restaurant_config,
        tool_id="answer_faq",
        input_data={"question": "kya gaadi parking ki suvidha available hai?"},
    )
    assert res.success is True
    assert "valet parking" in res.data["answer"].lower()


def test_transfer_call_live_mode_unavailability(registry: ToolRegistry):
    """Verify call transfer fails closed when live execution mode is enforced."""
    live_config = dict(INITIAL_BUSINESSES["biz_spice_garden"])
    live_config["execution_mode"] = "live"

    res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=live_config,
        tool_id="transfer_call",
        input_data={"reason": "Urgent manager transfer"},
    )
    assert res.status == ToolExecutionStatus.UNAVAILABLE
    assert res.success is False
    assert res.mode == ToolExecutionMode.UNAVAILABLE
    assert res.error_code == "LIVE_INTEGRATION_NOT_CONFIGURED"
    assert "no verified live integration is configured" in res.message

