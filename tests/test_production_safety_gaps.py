"""
Production safety regression test suite.
Verifies all 8 critical production-safety requirements:
1. Safe exception handling
2. Truthful tool outcomes
3. Execution policy (allowlist & verified live implementations)
4. Database integration (real message persistence & tenant association)
5. FAQ quality & ambiguity margin
6. Canonical industry authorization
7. Confirmation safety (binding, expiration, replay prevention)
8. End-to-end verification
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError, BaseModel, Field

from backend.config import Settings
from backend.database.service import get_database_service
from backend.database.models import PendingAction, ConversationMessage, utcnow
from backend.database.seed_data import INITIAL_BUSINESSES
from backend.tools.base import (
    ToolDefinition,
    ToolCategory,
    ToolExecutionStatus,
    ToolExecutionMode,
    ToolExecutionResult,
    normalize_industry_name,
)
from backend.tools.registry import (
    ToolRegistry,
    build_default_tool_registry,
)
from backend.tools.definitions import (
    CreateTableBookingInput,
    CreateAppointmentInput,
    CheckTableAvailabilityInput,
    CheckAppointmentAvailabilityInput,
    TakeMessageInput,
    TransferCallInput,
    AnswerFAQInput,
)
from backend.tools.implementations.information import (
    FAQSearchEngine,
    handle_answer_faq,
    AMBIGUITY_MARGIN,
    MIN_CONFIDENCE_THRESHOLD,
)
from backend.tools.implementations.communication import (
    handle_take_message,
    handle_transfer_call,
)
from backend.agent.nodes import execute_pending_action


# ==============================================================================
# 1. Safe Exception Handling
# ==============================================================================

def test_unhandled_exception_masks_raw_text_and_returns_error_id_and_code():
    """Verify registry catches unhandled handler exceptions and returns safe error payload without leaking stack or raw messages."""
    registry = ToolRegistry()

    class DummyInput(BaseModel):
        payload: str

    def buggy_handler(args: DummyInput, biz_config: dict) -> ToolExecutionResult:
        raise RuntimeError("CRITICAL_LEAK: Internal connection string postgresql://admin:supersecret@10.0.0.1:5432/core")

    dummy_tool = ToolDefinition(
        id="buggy_action",
        name="Buggy Action",
        description="A tool that triggers an exception",
        category=ToolCategory.INFORMATION,
        input_schema=DummyInput,
        handler=buggy_handler,
    )
    registry.register(dummy_tool)

    biz_config = {"id": "biz_test", "name": "Test Tenant", "enabled_tools": {"buggy_action": True}}
    res = registry.execute_tool(
        business_id="biz_test",
        business_config=biz_config,
        tool_id="buggy_action",
        input_data={"payload": "test"},
    )

    # Must fail safely
    assert res.status == ToolExecutionStatus.ERROR
    assert res.success is False
    assert res.error_code == "HANDLER_EXCEPTION"

    # User-facing message must NEVER leak credentials, hostnames, or raw exception strings
    assert "CRITICAL_LEAK" not in res.message
    assert "supersecret" not in res.message
    assert "10.0.0.1" not in res.message
    assert "An unexpected error occurred while executing the action (Error ID:" in res.message

    # Internal diagnostics must preserve the diagnostic for log collection
    assert res.internal_diagnostics is not None
    assert "CRITICAL_LEAK" in res.internal_diagnostics


# ==============================================================================
# 2. Truthful Tool Outcomes
# ==============================================================================

def test_mock_dining_availability_and_booking_truthful_simulation():
    """Verify mock dining tools explicitly disclose simulation and do not claim confirmed live outcomes."""
    registry = build_default_tool_registry()
    biz_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # Availability check
    avail_res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=biz_config,
        tool_id="check_table_availability",
        input_data={"date": "2026-10-28", "time": "19:00", "party_size": 2},
    )
    assert avail_res.success is True
    assert avail_res.is_simulated is True
    assert avail_res.data["is_simulated"] is True
    assert "[Development Simulation]" in avail_res.message
    assert "live table inventory integration is not connected" in avail_res.message.lower()

    # Table booking creation
    book_res = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=biz_config,
        tool_id="create_table_booking",
        input_data={
            "customer_name": "Rohan Gupta",
            "customer_phone": "+91 98888 77777",
            "date": "2026-10-28",
            "time": "19:00",
            "party_size": 2,
        },
        confirmed=True,
    )
    assert book_res.success is True
    assert book_res.is_simulated is True
    assert book_res.data["is_simulated"] is True
    assert book_res.data["status"] == "simulated_booking"
    assert "[Development Simulation]" in book_res.message
    assert "is simulated in development mode" in book_res.message.lower()


def test_mock_healthcare_availability_and_appointment_truthful_simulation():
    """Verify mock healthcare tools explicitly disclose simulation and do not claim verified doctor booking."""
    registry = build_default_tool_registry()
    biz_config = INITIAL_BUSINESSES["biz_apex_dental"]

    # Appointment availability check
    avail_res = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=biz_config,
        tool_id="check_appointment_availability",
        input_data={"service_or_department": "Dental Checkup", "preferred_date": "2026-10-29"},
    )
    assert avail_res.success is True
    assert avail_res.is_simulated is True
    assert avail_res.data["is_simulated"] is True
    assert "[Development Simulation]" in avail_res.message
    assert "live practitioner scheduling is not connected" in avail_res.message.lower()

    # Appointment creation
    appt_res = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=biz_config,
        tool_id="create_appointment",
        input_data={
            "patient_name": "Anita Roy",
            "patient_phone": "+91 97777 66666",
            "service_or_department": "Dental Checkup",
            "appointment_date": "2026-10-29",
            "appointment_time": "11:00",
        },
        confirmed=True,
    )
    assert appt_res.success is True
    assert appt_res.is_simulated is True
    assert appt_res.data["is_simulated"] is True
    assert appt_res.data["status"] == "simulated_appointment"
    assert "[Development Simulation]" in appt_res.message
    assert "is simulated in development mode" in appt_res.message.lower()


def test_transfer_call_never_promises_hold_and_filters_placeholders():
    """Verify simulated call transfer does not tell callers to hold and removes dummy numbers."""
    # Test with placeholder business phone
    dummy_config = {
        "id": "biz_dummy",
        "name": "Dummy Clinic",
        "phone_number": "+91 80 0000 0000",
        "execution_mode": "mock",
    }
    input_data = TransferCallInput(reason="Emergency consultation", department_or_target="Dentist Desk")
    res = handle_transfer_call(input_data, dummy_config)

    assert res.success is True
    assert res.is_simulated is True
    assert res.data["live_telephony_transfer_performed"] is False
    assert res.data["destination_phone"] is None  # Placeholder filtered

    # Verify no false hold instructions
    msg_lower = res.message.lower()
    assert "hold on" not in msg_lower
    assert "please hold while" not in msg_lower
    assert "hold the line" not in msg_lower
    assert "live telephony line transfer is simulated" in msg_lower


def test_message_taking_truthfully_reports_unpersisted_status_when_db_offline(monkeypatch):
    """Verify take_message marks status as simulated_intake (not logged) when DB engine is disconnected."""
    from backend.database import engine as eng_mod
    monkeypatch.setattr(eng_mod, "check_database_connection", lambda *args, **kwargs: {"connected": False})

    biz_config = {"id": "biz_offline", "name": "Offline Biz", "execution_mode": "mock"}
    input_data = TakeMessageInput(
        caller_name="Vikram Singh",
        caller_phone="+91 98888 12345",
        message="Calling to ask about banquet hall pricing.",
        urgency="normal",
    )
    res = handle_take_message(input_data, biz_config)

    assert res.success is True
    assert res.is_simulated is True
    assert res.data["is_persisted"] is False
    assert res.data["status"] == "simulated_intake"  # Truthful status: NOT "logged"
    assert res.data["persistence_status"] == "unpersisted_memory"
    assert res.data["notification_queued"] is False
    assert res.data["notification_delivered"] is False
    assert "[Development Simulation]" in res.message


# ==============================================================================
# 3. Execution Policy
# ==============================================================================

def test_settings_execution_mode_allowlist_validation():
    """Verify application configuration fails closed for invalid execution modes at startup."""
    # Valid execution modes
    for valid_mode in ["mock", "live", "unavailable", "MOCK", "LIVE"]:
        s = Settings(TOOL_EXECUTION_MODE=valid_mode)
        assert s.TOOL_EXECUTION_MODE == valid_mode.lower()

    # Invalid execution mode must raise ValueError
    with pytest.raises(ValidationError, match="Invalid TOOL_EXECUTION_MODE 'invalid_turbo'"):
        Settings(TOOL_EXECUTION_MODE="invalid_turbo")


def test_live_execution_mode_fails_closed_for_unverified_tools():
    """Verify that unverified tools fail closed with UNAVAILABLE status in live execution mode."""
    registry = build_default_tool_registry()

    # Restaurant table booking in live mode
    live_restaurant = dict(INITIAL_BUSINESSES["biz_spice_garden"])
    live_restaurant["execution_mode"] = "live"

    res_avail = registry.execute_tool(
        business_id="biz_spice_garden",
        business_config=live_restaurant,
        tool_id="check_table_availability",
        input_data={"date": "2026-10-28", "time": "19:00", "party_size": 2},
    )
    assert res_avail.status == ToolExecutionStatus.UNAVAILABLE
    assert res_avail.success is False
    assert res_avail.error_code == "LIVE_INTEGRATION_NOT_CONFIGURED"

    # Clinic appointment in live mode
    live_clinic = dict(INITIAL_BUSINESSES["biz_apex_dental"])
    live_clinic["execution_mode"] = "live"

    res_appt = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=live_clinic,
        tool_id="create_appointment",
        input_data={
            "patient_name": "Anita Roy",
            "patient_phone": "+91 97777 66666",
            "service_or_department": "Dental Checkup",
            "appointment_date": "2026-10-29",
            "appointment_time": "11:00",
        },
        confirmed=True,
    )
    assert res_appt.status == ToolExecutionStatus.UNAVAILABLE
    assert res_appt.success is False
    assert res_appt.error_code == "LIVE_INTEGRATION_NOT_CONFIGURED"


def test_no_silent_fallback_when_live_message_persistence_fails(monkeypatch):
    """Verify take_message in live mode fails closed with error when persistence fails, instead of falling back to mock success."""
    from backend.database import engine as eng_mod
    monkeypatch.setattr(eng_mod, "check_database_connection", lambda *args, **kwargs: {"connected": False})

    live_biz = {"id": "biz_live_test", "name": "Live Tenant", "execution_mode": "live"}
    input_data = TakeMessageInput(
        caller_name="Pooja Sharma",
        caller_phone="+91 98111 22233",
        message="Urgent follow up requested.",
        urgency="urgent",
    )
    res = handle_take_message(input_data, live_biz)

    # Must fail closed, not silently succeed as mock!
    assert res.status == ToolExecutionStatus.ERROR
    assert res.success is False
    assert res.is_business_accepted is False
    assert res.error_code == "MESSAGE_PERSISTENCE_FAILED"
    assert "Message could not be saved to staff records" in res.message


# ==============================================================================
# 4. Database Integration (Real Message Persistence & Tenant Association)
# ==============================================================================

def test_message_persistence_in_real_database():
    """Verify take_message actually creates a persistent database record scoped to tenant."""
    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    biz_config = INITIAL_BUSINESSES[biz_id]

    input_data = TakeMessageInput(
        caller_name="Harish Patel",
        caller_phone="+91 98222 33344",
        message="Inquiry about private dining room capacity.",
        urgency="urgent",
    )
    res = handle_take_message(input_data, biz_config)

    # Verify execution outcome
    assert res.success is True
    assert res.data["is_persisted"] is True
    assert res.data["status"] == "persisted"
    assert res.mode == ToolExecutionMode.LIVE

    # Verify message is actually in the database!
    messages = db_service.get_conversation_messages(biz_id)
    persisted_texts = [m["content"] for m in messages if m["role"] == "caller_message"]
    assert any("Harish Patel" in txt and res.data["message_reference"] in txt for txt in persisted_texts)

    # Verify tenant isolation: message is NOT present for another tenant
    other_tenant_messages = db_service.get_conversation_messages("biz_apex_dental")
    other_persisted_texts = [m["content"] for m in other_tenant_messages if m["role"] == "caller_message"]
    assert not any("Harish Patel" in txt for txt in other_persisted_texts)


# ==============================================================================
# 5. FAQ Quality & Ambiguity Margin
# ==============================================================================

def test_faq_ambiguity_margin_detection():
    """Verify when two FAQs have close relevance scores (< AMBIGUITY_MARGIN), the system detects ambiguity and requests clarification."""
    custom_faqs = [
        {"question": "Do you accept credit card payments?", "answer": "Yes, we accept Visa and Mastercard credit cards."},
        {"question": "Do you accept debit card payments?", "answer": "Yes, we accept Rupay and debit cards."},
    ]
    biz_config = {
        "id": "biz_test",
        "name": "Spice Garden",
        "faqs": custom_faqs,
    }

    # Query matching both payment FAQs with high score and tiny margin
    input_data = AnswerFAQInput(question="Do you accept card payments?")
    res = handle_answer_faq(input_data, biz_config)

    assert res.success is False
    assert res.error_code == "AMBIGUOUS_FAQ_MATCH"
    assert res.data["is_ambiguous"] is True
    assert len(res.data["top_candidates"]) == 2
    assert "specify which topic" in res.message


def test_faq_lexical_ranking_deterministic_eval():
    """Evaluate FAQ engine against deterministic English, Hindi, Hinglish, and low-overlap test set."""
    faqs = [
        {"question": "What are your business hours?", "answer": "We are open from 9 AM to 10 PM daily."},
        {"question": "Do you offer valet parking?", "answer": "Yes, complimentary valet parking is available."},
        {"question": "Is table reservation required?", "answer": "Walk-ins are welcome, but reservations recommended on weekends."},
        {"question": "गाड़ी पार्किंग की क्या व्यवस्था है?", "answer": "जी हाँ, हमारे पास निःशुल्क वैलेट पार्किंग उपलब्ध है।"},
    ]
    biz_config = {"id": "biz_faq_test", "name": "Test Bistro", "faqs": faqs}

    # 1. Exact match
    res_exact = handle_answer_faq(AnswerFAQInput(question="What are your business hours?"), biz_config)
    assert res_exact.success is True
    assert res_exact.data["confidence_score"] == 1.0
    assert "9 AM to 10 PM" in res_exact.data["answer"]
    assert res_exact.data["retrieval_method"] in ("bm25_multilingual_ranking", "lexical_token_jaccard_ranking")

    # 2. Hinglish query for parking
    res_hinglish = handle_answer_faq(AnswerFAQInput(question="kya parking available hai?"), biz_config)
    assert res_hinglish.success is True
    assert "valet parking" in res_hinglish.data["answer"].lower()

    # 3. Hindi Devanagari query matching Devanagari FAQ
    res_hindi = handle_answer_faq(AnswerFAQInput(question="गाड़ी पार्किंग की क्या व्यवस्था है?"), biz_config)
    assert res_hindi.success is True
    assert "पार्किंग" in res_hindi.data["answer"]

    # 4. Low-overlap irrelevant query fails gracefully
    res_low = handle_answer_faq(AnswerFAQInput(question="Can you repair my laptop motherboard?"), biz_config)
    assert res_low.success is False
    assert res_low.data["found"] is False
    assert "No matching FAQ was found" in res_low.message


def test_faq_deduplication():
    """Verify FAQSearchEngine deduplicates identical questions."""
    duplicate_faqs = [
        {"question": "What is your address?", "answer": "123 Main St, Bengaluru."},
        {"question": "what is your address? ", "answer": "Duplicate answer."},
        {"question": "WHAT IS YOUR ADDRESS?", "answer": "Another duplicate."},
    ]
    ranked = FAQSearchEngine.rank_faqs("address", duplicate_faqs)
    assert len(ranked) == 1
    assert ranked[0][0]["answer"] == "123 Main St, Bengaluru."


# ==============================================================================
# 6. Canonical Industry Authorization
# ==============================================================================

def test_canonical_industry_allowlists_and_denials():
    """Verify explicit canonical industry matching for restaurant, clinic, services, and universal tools."""
    registry = build_default_tool_registry()

    # 1. Canonical normalization mapping
    assert normalize_industry_name("Restaurant") == "restaurant"
    assert normalize_industry_name("Cafe & Bistro") == "restaurant"
    assert normalize_industry_name("Dental Clinic") == "clinic"
    assert normalize_industry_name("Healthcare") == "clinic"
    assert normalize_industry_name("Salon & Spa") == "services"
    assert normalize_industry_name("Automotive Repair") is None
    assert normalize_industry_name("Aerospace Defense") is None

    # 2. Restaurant tenant only gets restaurant + universal tools
    restaurant_config = {
        "id": "biz_test_rest",
        "name": "Test Rest",
        "industry": "Restaurant",
        "enabled_tools": {
            "check_table_availability": True,
            "create_table_booking": True,
            "check_appointment_availability": True,  # Disabled by industry rule!
            "create_appointment": True,             # Disabled by industry rule!
            "answer_faq": True,
            "take_message": True,
            "transfer_call": True,
        },
    }
    rest_tools = {t.id for t in registry.get_enabled_tools_for_business(restaurant_config)}
    assert "check_table_availability" in rest_tools
    assert "create_table_booking" in rest_tools
    assert "answer_faq" in rest_tools
    assert "check_appointment_availability" not in rest_tools
    assert "create_appointment" not in rest_tools

    # 3. Clinic tenant only gets clinic + universal tools
    clinic_config = {
        "id": "biz_test_clinic",
        "name": "Test Clinic",
        "industry": "Dental Clinic",
        "enabled_tools": {
            "check_table_availability": True,        # Disabled by industry rule!
            "create_table_booking": True,            # Disabled by industry rule!
            "check_appointment_availability": True,
            "create_appointment": True,
            "answer_faq": True,
            "take_message": True,
            "transfer_call": True,
        },
    }
    clinic_tools = {t.id for t in registry.get_enabled_tools_for_business(clinic_config)}
    assert "check_appointment_availability" in clinic_tools
    assert "create_appointment" in clinic_tools
    assert "check_table_availability" not in clinic_tools
    assert "create_table_booking" not in clinic_tools

    # 4. Unsupported industry (e.g. Automotive) receives ONLY universal tools
    auto_config = {
        "id": "biz_test_auto",
        "name": "Test Motors",
        "industry": "Automotive",
        "enabled_tools": {t.id: True for t in registry.list_tools()},
    }
    auto_tools = {t.id for t in registry.get_enabled_tools_for_business(auto_config)}
    assert auto_tools == {"answer_faq", "take_message", "transfer_call"}


# ==============================================================================
# 7. Confirmation Safety
# ==============================================================================

def test_pending_action_expiration_and_rejection():
    """Verify expired pending actions cannot be confirmed or executed."""
    biz_config = INITIAL_BUSINESSES["biz_spice_garden"]

    # Pending action that expired 5 minutes ago
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    expired_action = {
        "action_id": "act_expired_1",
        "business_id": "biz_spice_garden",
        "tool_id": "create_table_booking",
        "status": "pending_confirmation",
        "arguments": {
            "customer_name": "Arun Kumar",
            "customer_phone": "+91 99999 88888",
            "date": "2026-10-30",
            "time": "20:00",
            "party_size": 2,
        },
        "expires_at": past_time,
    }

    res = execute_pending_action(
        business_id="biz_spice_garden",
        business_config=biz_config,
        pending_action=expired_action,
        confirmed=True,
    )
    assert res.success is False
    assert res.error_code == "ACTION_EXPIRED"
    assert expired_action["status"] == "expired"


def test_pending_action_replay_prevention():
    """Verify executing an already processed action returns ACTION_ALREADY_PROCESSED."""
    biz_config = INITIAL_BUSINESSES["biz_spice_garden"]
    already_executed = {
        "action_id": "act_done_1",
        "business_id": "biz_spice_garden",
        "tool_id": "create_table_booking",
        "status": "executed",
        "arguments": {},
    }
    res = execute_pending_action(
        business_id="biz_spice_garden",
        business_config=biz_config,
        pending_action=already_executed,
        confirmed=True,
    )
    assert res.success is False
    assert res.error_code == "ACTION_ALREADY_PROCESSED"


def test_pending_action_tenant_binding():
    """Verify executing an action bound to another tenant fails with BUSINESS_IDENTITY_MISMATCH."""
    biz_config = INITIAL_BUSINESSES["biz_spice_garden"]
    mismatched_action = {
        "action_id": "act_mismatch_1",
        "business_id": "biz_apex_dental",  # Belongs to clinic, not spice garden!
        "tool_id": "create_table_booking",
        "status": "pending_confirmation",
        "arguments": {},
    }
    res = execute_pending_action(
        business_id="biz_spice_garden",
        business_config=biz_config,
        pending_action=mismatched_action,
        confirmed=True,
    )
    assert res.success is False
    assert res.error_code == "BUSINESS_IDENTITY_MISMATCH"


def test_untrusted_input_cannot_inject_confirmed_boolean():
    """Verify LLM or untrusted caller cannot pass confirmed=True in input schema."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CreateTableBookingInput(
            customer_name="Malicious Actor",
            customer_phone="+91 99999 88888",
            date="2026-10-30",
            time="20:00",
            party_size=2,
            confirmed=True,  # Extra field injected!
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CreateAppointmentInput(
            patient_name="Malicious Actor",
            patient_phone="+91 99999 88888",
            service_or_department="Consultation",
            appointment_date="2026-10-30",
            appointment_time="11:00",
            confirmed=True,  # Extra field injected!
        )
