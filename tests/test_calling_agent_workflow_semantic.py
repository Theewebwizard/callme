"""
Unit tests for calling agent workflow updates:
- Work completion confirmation & proactive follow-up question.
- Semantic intent evaluation for caller replies (yes/no/new inquiry).
- Pydantic schema validation preventing errors.
- Automatic graceful call termination upon caller completion.
"""

import pytest
from unittest.mock import MagicMock
import json

from backend.agent.state import AgentState
from backend.agent.semantic_intent import (
    FollowupIntentType,
    SemanticIntentExtraction,
    extract_semantic_followup_intent,
    is_followup_prompt,
    detect_language,
)
from backend.agent.graph import invoke_receptionist_workflow
from backend.agent.nodes import prepare_context_node, finalize_response_node
from backend.services.groq_service import GroqService, LLMResponse
from backend.database.seed_data import INITIAL_BUSINESSES, INITIAL_TOOLS


def test_semantic_intent_pydantic_schema_validation():
    """Verify SemanticIntentExtraction enforces valid Pydantic fields."""
    # Valid model construction
    valid = SemanticIntentExtraction(
        intent=FollowupIntentType.NO_FURTHER_QUERY,
        has_more_queries=False,
        is_farewell=True,
        language="en",
        confidence=0.98,
        reasoning="Caller said that's all",
    )
    assert valid.intent == FollowupIntentType.NO_FURTHER_QUERY
    assert valid.has_more_queries is False
    assert valid.is_farewell is True

    # Pydantic JSON export and re-import
    json_data = valid.model_dump_json()
    reconstructed = SemanticIntentExtraction.model_validate_json(json_data)
    assert reconstructed.intent == valid.intent


def test_semantic_intent_negative_variations():
    """Verify semantic meaning of 'no' / completion across English and Hindi."""
    test_phrases = [
        ("No, that's all thank you!", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("Nope, I am good.", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("Nothing else, thanks!", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("That will be all for now.", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("We are all set, bye!", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("Nahi bas, itna hi tha", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("Kuch nahi chahiye, shukriya", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("Bas ho gaya, thank you", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("Sab theek hai abhi ke liye", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("yes work is done", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("work is done, thank you", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("haan kaam ho gaya", FollowupIntentType.NO_FURTHER_QUERY, False),
        ("yes that is all", FollowupIntentType.NO_FURTHER_QUERY, False),
    ]
    for phrase, expected_intent, expected_has_more in test_phrases:
        res = extract_semantic_followup_intent(phrase)
        assert res.intent == expected_intent, f"Failed on: {phrase}"
        assert res.has_more_queries is expected_has_more, f"Failed has_more_queries on: {phrase}"


def test_semantic_intent_affirmative_variations():
    """Verify semantic meaning of 'yes' / has more queries across English and Hindi."""
    test_phrases = [
        ("Yes, one more question please", FollowupIntentType.HAS_FURTHER_QUERY, True),
        ("Actually yeah, I had a doubt", FollowupIntentType.HAS_FURTHER_QUERY, True),
        ("One more thing", FollowupIntentType.HAS_FURTHER_QUERY, True),
        ("Haanji, ek aur sawal hai", FollowupIntentType.HAS_FURTHER_QUERY, True),
        ("Ek baat aur puchni thi", FollowupIntentType.HAS_FURTHER_QUERY, True),
    ]
    for phrase, expected_intent, expected_has_more in test_phrases:
        res = extract_semantic_followup_intent(phrase)
        assert res.intent == expected_intent, f"Failed on: {phrase}"
        assert res.has_more_queries is expected_has_more, f"Failed has_more_queries on: {phrase}"


def test_semantic_intent_distinguishes_no_problem():
    """Verify that phrases containing 'no' like 'no problem' are not falsely marked as no_further_query."""
    res = extract_semantic_followup_intent("No problem, please go ahead with the booking")
    assert res.intent != FollowupIntentType.NO_FURTHER_QUERY


def test_work_completion_appends_proactive_followup_query():
    """When tools execute, finalize_response_node ensures follow-up query is asked."""
    state: AgentState = {
        "success": True,
        "response_content": "I have reserved a table for 4 guests tonight at 8:00 PM.",
        "tools_called": ["create_table_booking"],
        "work_completed": True,
        "should_terminate": False,
    }
    finalized = finalize_response_node(state)
    assert finalized["success"] is True
    assert "reserved a table" in finalized["response_content"]
    assert "Is there anything else I can help you with today?" in finalized["response_content"]


def test_work_completion_hindi_appends_hindi_followup_query():
    """When tools execute and response is Hindi, follow-up query is in Hindi."""
    state: AgentState = {
        "success": True,
        "response_content": "आपकी टेबल आज रात 8 बजे के लिए बुक कर दी गई है।",
        "tools_called": ["create_table_booking"],
        "work_completed": True,
        "should_terminate": False,
    }
    finalized = finalize_response_node(state)
    assert finalized["success"] is True
    assert "क्या मैं आपकी किसी और चीज़ में सहायता कर सकता हूँ?" in finalized["response_content"]


def test_workflow_e2e_caller_answers_no_terminates_gracefully():
    """
    E2E test:
    Turn 1: Assistant asks 'Is there anything else I can help you with today?'
    Turn 2: Caller says 'No, that's all, thank you!'
    Result: Agent replies with polite farewell and marks should_terminate=True.
    """
    messages = [
        {"role": "user", "content": "Can you check table availability for tonight?"},
        {
            "role": "assistant",
            "content": "Tables are available for tonight. Is there anything else I can help you with today?",
        },
        {"role": "user", "content": "No, that's all, thank you!"},
    ]

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=messages,
    )

    assert result["success"] is True
    assert result["should_terminate"] is True
    assert result["followup_intent"] == "no_further_query"
    assert "thank you for calling" in result["response_content"].lower()
    assert "goodbye" in result["response_content"].lower()


def test_workflow_e2e_caller_answers_yes_prompts_further_help():
    """
    E2E test:
    Turn 1: Assistant asks 'Is there anything else I can help you with today?'
    Turn 2: Caller says 'Yes please, one more question'
    Result: Agent encourages caller and leaves should_terminate=False.
    """
    messages = [
        {"role": "user", "content": "What are your hours?"},
        {
            "role": "assistant",
            "content": "We are open from 11:30 AM to 11:00 PM today. Is there anything else I can help you with today?",
        },
        {"role": "user", "content": "Yes, actually one more thing"},
    ]

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=messages,
    )

    assert result["success"] is True
    assert result["should_terminate"] is False
    assert result["followup_intent"] == "has_further_query"
    assert "what else can i help you with" in result["response_content"].lower()


def test_workflow_e2e_caller_says_yes_work_is_done_cuts_call():
    """
    E2E test:
    Turn 1: Assistant asks 'Is there anything else I can help you with today?'
    Turn 2: Caller says 'Yes work is done, thank you!'
    Result: Agent confirms completion, says farewell, and sets should_terminate=True (call cuts).
    """
    messages = [
        {"role": "user", "content": "Can you book a table for tonight?"},
        {
            "role": "assistant",
            "content": "Your table is confirmed. Is there anything else I can help you with today?",
        },
        {"role": "user", "content": "Yes work is done, thank you!"},
    ]

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=messages,
    )

    assert result["success"] is True
    assert result["should_terminate"] is True
    assert result["followup_intent"] == "no_further_query"
    assert "thank you for calling" in result["response_content"].lower()
    assert "goodbye" in result["response_content"].lower()


def test_verbal_confirmation_executes_booking_tool_without_button_click():
    """
    Verify that when the assistant has proposed a booking, and the caller verbally
    says 'Confirm the booking' or 'Okay', the booking tool executes directly
    without requiring a visual UI button click.
    """
    from backend.tools.registry import get_tool_registry
    registry = get_tool_registry()

    messages = [
        {"role": "user", "content": "Book for Simmer Singh, 5 guests on 27th Oct at 5pm"},
        {
            "role": "assistant",
            "content": (
                "I've prepared your create table booking details:\n\n"
                "• Action: Dining Table Reservation\n"
                "• Guest Contact: Simmer Singh (+91 8090721413)\n"
                "• Party Size: 5 guests\n"
                "• Reservation Date & Time: 2024-10-27 at 17:00\n\n"
                "Would you like me to go ahead and confirm this for you?"
            ),
        },
        {"role": "user", "content": "Confirm the booking"},
    ]

    mock_client = MagicMock()
    tc = MagicMock()
    tc.id = "call_tc_confirm"
    tc.function.name = "create_table_booking"
    tc.function.arguments = json.dumps({
        "customer_name": "Simmer Singh",
        "customer_phone": "+91 8090721413",
        "date": "2024-10-27",
        "time": "17:00",
        "party_size": 5,
    })
    choice_tc = MagicMock()
    choice_tc.message.content = ""
    choice_tc.message.tool_calls = [tc]

    choice_final = MagicMock()
    choice_final.message.content = "Your table for 5 guests has been confirmed for 27th October at 5 PM under Simmer Singh."
    choice_final.message.tool_calls = None

    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[choice_tc]),
        MagicMock(choices=[choice_final]),
    ]
    mock_groq = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id="biz_spice_garden",
        business_config=INITIAL_BUSINESSES["biz_spice_garden"],
        enabled_tools=INITIAL_TOOLS,
        messages=messages,
        groq_service=mock_groq,
        tool_registry=registry,
    )

    assert result["success"] is True
    # The tool MUST have executed
    assert "create_table_booking" in result["tools_called"]
    # There should NOT be an unexecuted pending_action left
    assert result["pending_action"] is None
    # Response must confirm reservation and include follow-up inquiry
    assert "confirmed" in result["response_content"].lower()
    assert "anything else" in result["response_content"].lower()

def test_schema_driven_tool_bound_prompt_instructions():
    """Verify system instruction contains autonomous tool-bound information gathering rules."""
    from backend.services.groq_service import build_business_system_instruction
    restaurant = INITIAL_BUSINESSES["biz_spice_garden"]
    prompt = build_business_system_instruction(restaurant, INITIAL_TOOLS)

    assert "TOOL-BOUND REASONING (COLLECT ONLY FOR ENABLED TOOLS)" in prompt
    assert "WHEN A CALLER ASKS FOR AN ACTION WITH NO ENABLED TOOL" in prompt
    assert "DO NOT collect booking/appointment parameters" in prompt
    assert "Immediately inform the caller upfront on the very first turn" in prompt


def test_system_prompt_excludes_disabled_tools_from_catalog():
    """Verify disabled tools are not listed in TENANT TOOLS IN SYSTEM."""
    import copy
    from backend.services.groq_service import build_business_system_instruction
    biz = copy.deepcopy(INITIAL_BUSINESSES["biz_spice_garden"])
    biz["enabled_tools"]["create_table_booking"] = False

    enabled_tools = {k: v for k, v in INITIAL_TOOLS.items() if biz["enabled_tools"].get(k, False)}
    prompt = build_business_system_instruction(biz, enabled_tools)

    assert "Create Table Booking" not in prompt
    assert "Check Table Availability" in prompt
