"""
Tests for Conversational Date Auto-Anchoring, Internal Tool Suppression,
and Professional English/Hindi Progress Filler Phrases.
"""

from datetime import datetime, date, timedelta
import zoneinfo
import pytest

from backend.tools.base import normalize_booking_date
from backend.tools.definitions import (
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
)
from backend.agent.nodes import (
    get_contextual_filler_phrase,
    has_tool_leakage,
    sanitize_customer_facing_text,
    call_llm_node,
    finalize_response_node,
)
from backend.services.groq_service import (
    build_business_system_instruction,
    LLMResponse,
)
from backend.agent.state import AgentState, WorkflowStatus


def test_date_normalizer_anchors_explicit_and_conversational_dates():
    """Verify that dates without year or with hallucinated past years anchor to the current calendar year."""
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()
    current_year = today.year

    # 1. Date with missing year: "29 November"
    res1 = normalize_booking_date("29 November")
    assert res1 == f"{current_year}-11-29"

    # 2. Date with hallucinated past year: "2024-11-29" or "2023-11-29"
    res2 = normalize_booking_date("2024-11-29")
    assert res2 == f"{current_year}-11-29"

    res3 = normalize_booking_date("2023-11-29")
    assert res3 == f"{current_year}-11-29"

    # 3. Textual abbreviated formats
    assert normalize_booking_date("29 Nov") == f"{current_year}-11-29"
    assert normalize_booking_date("November 29") == f"{current_year}-11-29"
    assert normalize_booking_date("Nov 29") == f"{current_year}-11-29"
    assert normalize_booking_date("29-11") == f"{current_year}-11-29"

    # 4. Relative keywords in English & Hindi
    assert normalize_booking_date("today") == today.isoformat()
    assert normalize_booking_date("aaj") == today.isoformat()
    assert normalize_booking_date("आज") == today.isoformat()

    tomorrow = (today + timedelta(days=1)).isoformat()
    assert normalize_booking_date("tomorrow") == tomorrow
    assert normalize_booking_date("kal") == tomorrow
    assert normalize_booking_date("कल") == tomorrow

    day_after = (today + timedelta(days=2)).isoformat()
    assert normalize_booking_date("day after tomorrow") == day_after
    assert normalize_booking_date("parson") == day_after
    assert normalize_booking_date("परसों") == day_after


def test_date_normalizer_advances_passed_dates_to_next_year():
    """Verify that a date that has already elapsed in the current calendar year advances to the upcoming year."""
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()

    # If today is in November, January 10 has already passed in the current year
    past_date_str = "10 January"
    res = normalize_booking_date(past_date_str)
    parsed = datetime.strptime(res, "%Y-%m-%d").date()
    assert parsed >= today
    assert parsed.year >= today.year


def test_pydantic_schema_auto_normalizes_dates():
    """Verify that tool input Pydantic schemas normalize dates before validation."""
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()
    current_year = today.year

    # Dining Availability
    din_avail = CheckTableAvailabilityInput(
        date="29 November",
        time="19:30",
        party_size=4,
    )
    assert din_avail.date == f"{current_year}-11-29"

    # Dining Booking with past year
    din_book = CreateTableBookingInput(
        customer_name="Pooja Sharma",
        customer_phone="+919876543210",
        date="2024-11-29",
        time="20:00",
        party_size=2,
    )
    assert din_book.date == f"{current_year}-11-29"

    # Healthcare Availability
    med_avail = CheckAppointmentAvailabilityInput(
        service_or_department="Cardiology",
        preferred_date="29 November",
        preferred_time="10:00",
    )
    assert med_avail.preferred_date == f"{current_year}-11-29"

    # Healthcare Booking with past year
    med_book = CreateAppointmentInput(
        patient_name="Rahul Verma",
        patient_phone="+919876543210",
        service_or_department="Dentistry",
        appointment_date="2023-11-29",
        appointment_time="11:30",
    )
    assert med_book.appointment_date == f"{current_year}-11-29"


def test_tool_leakage_detection():
    """Verify that internal tool names and robotic step narration are accurately detected."""
    assert has_tool_leakage("I will now call check_table_availability with party_size=2.")
    assert has_tool_leakage("Step 1: Calling create_table_booking.")
    assert has_tool_leakage("Executing check_appointment_availability now.")
    assert has_tool_leakage("Using the create_appointment tool...")

    # Clean customer conversational sentences must NOT trigger leakage
    assert not has_tool_leakage("We have a table available at 8:00 PM for 2 guests.")
    assert not has_tool_leakage("Dr. Singh has an open consultation slot at 11:00 AM.")
    assert not has_tool_leakage("Would you like me to reserve that for you?")


def test_sanitize_customer_facing_text():
    """Verify that internal technical tool names and step narration are eliminated."""
    # Pure technical chatter gets replaced with respectful filler
    chatter = "I will now call check_table_availability with party_size=2."
    sanitized = sanitize_customer_facing_text(chatter, fallback_tool_id="check_table_availability", language="en")
    assert "check_table_availability" not in sanitized
    assert "checking our available tables" in sanitized

    # In Hindi
    sanitized_hi = sanitize_customer_facing_text(chatter, fallback_tool_id="check_table_availability", language="hi")
    assert "check_table_availability" not in sanitized_hi
    assert "टेबल चेक कर रहा हूँ" in sanitized_hi

    # Step narration in otherwise helpful sentence gets cleaned
    step_msg = "Step 1: We have checked and your table for 4 guests is available at 8:00 PM."
    sanitized_step = sanitize_customer_facing_text(step_msg)
    assert "Step 1" not in sanitized_step
    assert "available at 8:00 PM" in sanitized_step


def test_contextual_filler_phrases_english_and_hindi():
    """Verify that proper, respectful filler phrases exist for all tools in both English and Hindi."""
    tools = [
        "check_table_availability",
        "create_table_booking",
        "check_appointment_availability",
        "create_appointment",
        "check_room_availability",
        "create_room_booking",
        "take_message",
        "transfer_call",
        "answer_faq",
    ]

    for tool_id in tools:
        en_phrase = get_contextual_filler_phrase(tool_id, language="en")
        hi_phrase = get_contextual_filler_phrase(tool_id, language="hi")

        assert en_phrase and isinstance(en_phrase, str)
        assert hi_phrase and isinstance(hi_phrase, str)

        # No raw tool names in filler phrases
        assert tool_id not in en_phrase
        assert tool_id not in hi_phrase

        # Polite verbal etiquette
        assert "seconds" in en_phrase or "Please" in en_phrase or "moment" in en_phrase or "hold" in en_phrase
        assert "सेकंड" in hi_phrase or "कृपया" in hi_phrase or "क्षण" in hi_phrase or "पल" in hi_phrase


def test_system_prompt_calendar_anchor_and_speech_rules():
    """Verify that build_business_system_instruction injects calendar context and strict speech rules."""
    biz = {
        "name": "The Royal Dawat",
        "industry": "Restaurant",
        "timezone": "Asia/Kolkata",
    }
    prompt = build_business_system_instruction(biz, {})

    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    current_year = datetime.now(tz).year

    # Temporal Anchor
    assert "[CURRENT CALENDAR & REAL-TIME CLOCK CONTEXT]" in prompt
    assert f"Current Calendar Year: {current_year}" in prompt
    assert "STRICT DATE ANCHORING RULES" in prompt

    # Spoken Speech & Telephony Guardrails
    assert "[CUSTOMER-FACING SPOKEN VOICE & TELEPHONY RULES]" in prompt
    assert "ZERO INTERNAL TECHNICAL JARGON" in prompt
    assert "ZERO INTERNAL TASK STEP NARRATION" in prompt
    assert "RESPECTFUL FILLER & PROGRESS ACKNOWLEDGMENT" in prompt


def test_call_llm_node_sanitizes_tool_calls_and_provides_filler():
    """Verify that when an LLM produces tool calls, call_llm_node yields a polite filler phrase instead of robotic chatter."""
    class FakeGroqService:
        def generate_response(self, messages, system_instruction, tools):
            return LLMResponse(
                content="I will now execute check_table_availability to find open slots.",
                tool_calls=[{
                    "id": "tc_123",
                    "type": "function",
                    "function": {
                        "name": "check_table_availability",
                        "arguments": '{"date": "29 November", "time": "20:00", "party_size": 2}',
                    },
                }],
            )

    state: AgentState = {
        "business_id": "biz_spice",
        "business_config": {"name": "Spice Garden", "industry": "Restaurant"},
        "messages": [{"role": "user", "content": "Can I get a table for 2 on 29 November around 8 PM?"}],
        "system_instruction": "Test instruction",
        "tool_definitions": [],
        "success": True,
        "iteration_count": 0,
    }

    result = call_llm_node(state, groq_service=FakeGroqService())

    assert result["success"] is True
    # Robotic chatter must be replaced with polite filler
    assert "check_table_availability" not in result["response_content"]
    assert "checking our available tables" in result["response_content"]
    assert result["filler_phrase"] is not None


def test_call_llm_node_hindi_caller_receives_hindi_filler():
    """Verify that a Hindi/Hinglish caller message receives a polite Hindi filler phrase during tool calls."""
    class FakeGroqService:
        def generate_response(self, messages, system_instruction, tools):
            return LLMResponse(
                content="Calling check_table_availability.",
                tool_calls=[{
                    "id": "tc_456",
                    "type": "function",
                    "function": {
                        "name": "check_table_availability",
                        "arguments": '{"date": "29 November", "time": "20:00", "party_size": 2}',
                    },
                }],
            )

    state: AgentState = {
        "business_id": "biz_spice",
        "business_config": {"name": "Spice Garden", "industry": "Restaurant"},
        "messages": [{"role": "user", "content": "नमस्ते, क्या 29 नवंबर को 2 लोगों के लिए टेबल मिलेगी?"}],
        "system_instruction": "Test instruction",
        "tool_definitions": [],
        "success": True,
        "iteration_count": 0,
    }

    result = call_llm_node(state, groq_service=FakeGroqService())

    assert result["success"] is True
    # Hindi caller receives polite Hindi filler
    assert "check_table_availability" not in result["response_content"]
    assert "टेबल चेक कर रहा हूँ" in result["response_content"]
    assert "टेबल" in result["response_content"]
