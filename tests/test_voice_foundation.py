"""
Comprehensive test suite for Step 9A: Voice and Telephony Architecture Foundation.
Verifies:
1. Voice capabilities endpoint
2. Inbound routing and tenant resolution
3. E.164 phone normalization across formats
4. Unknown tenant rejection
5. Inactive tenant rejection
6. Ambiguous tenant rejection
7. Tenant verification / spoofing prevention
8. Durable session conversation isolation
9. Voice turn orchestration through LangGraph
10. Two-phase action confirmation preservation
11. Safe error boundaries without hallucinations
12. Concurrency serialization per session
13. Idempotent call termination and CallRecord auditing
14. Telephony provider webhook signature verification
15. Privacy masking of phone numbers
"""

import hmac
import hashlib
import json
import threading
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.groq_service import GroqService, LLMResponse
import backend.services.groq_service as groq_service_mod
from backend.database.service import get_database_service
from backend.voice.utils import normalize_phone_number, mask_phone_number
from backend.voice.events import InboundCallEvent, TranscriptEvent
from backend.voice.router import (
    InboundCallRouter,
    UnknownTenantError,
    InactiveTenantError,
    AmbiguousTenantError,
    TenantMismatchError,
)
from backend.voice.orchestrator import VoiceTurnOrchestrator
from backend.voice.session_manager import DatabaseVoiceSessionManager
from backend.voice.providers import get_telephony_provider, MockTelephonyProvider, register_telephony_provider


@pytest.fixture
def api_client():
    """TestClient instance for FastAPI application with platform admin auth."""
    client = TestClient(app)
    client.headers.update({"X-Admin-API-Key": "test-admin-secret-key-12345"})
    return client


# ==============================================================================
# 1. Voice Capabilities Endpoint
# ==============================================================================

def test_voice_capabilities(api_client):
    """GET /api/voice/capabilities returns provider capabilities and supported codecs."""
    response = api_client.get("/api/voice/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "telephony_providers" in data
    assert "stt_providers" in data
    assert "tts_providers" in data
    assert "supported_audio_codecs" in data

    mock_prov = next((p for p in data["telephony_providers"] if p["name"] == "mock"), None)
    assert mock_prov is not None
    assert "mulaw" in data["supported_audio_codecs"]

    # Also test /api/v1/voice/capabilities route alias
    v1_response = api_client.get("/api/v1/voice/capabilities")
    assert v1_response.status_code == 200
    assert v1_response.json() == data


# ==============================================================================
# 2. Inbound Routing & E.164 Phone Normalization
# ==============================================================================

def test_inbound_routing_success(api_client):
    """POST /api/voice/simulation/inbound resolves tenant, creates session, and returns greeting."""
    payload = {
        "called_number": "+91 80 4123 5678",
        "caller_number": "+91 98765 43210",
        "provider_name": "mock",
    }
    response = api_client.post("/api/voice/simulation/inbound", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["business_id"] == "biz_spice_garden"
    assert "Spice Garden" in data["business_name"]
    assert "session_id" in data
    assert data["session_id"].startswith("vses_")
    assert "Namaste" in data["greeting_message"]
    assert data["status"] == "initiated"

    # Verify session is persisted in DB
    db = get_database_service()
    session = db.get_voice_session(data["session_id"])
    assert session is not None
    assert session["business_id"] == "biz_spice_garden"

    # Verify greeting is recorded in session conversation messages
    history = db.get_session_messages("biz_spice_garden", data["session_id"])
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert "Namaste" in history[0]["content"]


@pytest.mark.parametrize("dialled_number", [
    "+91 80 4123 5678",
    "+918041235678",
    "08041235678",
    "+91-80-4123-5678",
    "80 4123 5678",
])
def test_phone_number_normalization_routing(dialled_number):
    """InboundCallRouter matches across various local and international number formats."""
    router = InboundCallRouter()
    event = InboundCallEvent(
        provider_call_id=f"test_norm_{dialled_number}",
        provider_name="mock",
        called_number=dialled_number,
    )
    result = router.route_inbound_call(event)
    assert result.business["id"] == "biz_spice_garden"
    assert result.session.session_id.startswith("vses_")


# ==============================================================================
# 3. Rejections: Unknown, Inactive, Ambiguous, and Mismatched Tenants
# ==============================================================================

def test_unknown_tenant_rejection(api_client):
    """Calling an unassigned number returns 404."""
    payload = {
        "called_number": "+91 99 9999 9999",
        "caller_number": "+91 98765 43210",
    }
    response = api_client.post("/api/voice/simulation/inbound", json=payload)
    assert response.status_code == 404
    assert "not assigned" in response.json()["detail"].lower()


def test_inactive_tenant_rejection(api_client):
    """Calling a business whose phone number is not Active & Connected returns 400."""
    db = get_database_service()
    db.update_business("biz_spice_garden", {"assigned_number_status": "Disconnected"})

    payload = {
        "called_number": "+91 80 4123 5678",
        "caller_number": "+91 98765 43210",
    }
    response = api_client.post("/api/voice/simulation/inbound", json=payload)
    assert response.status_code == 400
    assert "not active" in response.json()["detail"].lower()


def test_ambiguous_tenant_rejection(api_client):
    """When multiple businesses share the same phone number, call is rejected with 409."""
    db = get_database_service()
    # Create conflicting business sharing Spice Garden's number
    db.create_business({
        "id": "biz_conflict_restaurant",
        "name": "Conflict Diner",
        "industry": "Restaurant",
        "phone_number": "+91 80 4123 5678",
        "assigned_number_status": "Active & Connected",
        "greeting_message": "Welcome to Conflict Diner!",
    })

    payload = {
        "called_number": "+91 80 4123 5678",
        "caller_number": "+91 98765 43210",
    }
    response = api_client.post("/api/voice/simulation/inbound", json=payload)
    assert response.status_code == 409
    assert "ambiguously" in response.json()["detail"].lower()


def test_tenant_verification_spoofing_prevention(api_client):
    """Webhook providing claimed_business_id conflicting with dialled number owner returns 403."""
    payload = {
        "called_number": "+91 80 4123 5678",  # Belongs to Spice Garden
        "claimed_business_id": "biz_apex_dental",  # Claiming Apex Dental
    }
    response = api_client.post("/api/voice/simulation/inbound", json=payload)
    assert response.status_code == 403
    assert "verification failed" in response.json()["detail"].lower() or "does not match" in response.json()["detail"].lower()


# ==============================================================================
# 4. Session Conversation History Isolation
# ==============================================================================

def test_session_isolation(api_client, monkeypatch):
    """Turns in one voice session must never contaminate another session or playground history."""
    # Mock LLM
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "I understand. How else can I help?"
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    # 1. Create Call 1
    resp1 = api_client.post("/api/voice/simulation/inbound", json={"called_number": "+91 80 4123 5678"})
    session_id_1 = resp1.json()["session_id"]

    # 2. Create Call 2
    resp2 = api_client.post("/api/voice/simulation/inbound", json={"called_number": "+91 80 4123 5678"})
    session_id_2 = resp2.json()["session_id"]
    assert session_id_1 != session_id_2

    # 3. User turn in Call 1
    api_client.post(
        f"/api/voice/simulation/sessions/{session_id_1}/turns",
        json={"text": "Message specifically for Call 1"},
    )

    # 4. User turn in Call 2
    api_client.post(
        f"/api/voice/simulation/sessions/{session_id_2}/turns",
        json={"text": "Message specifically for Call 2"},
    )

    # 5. User turn in Playground
    api_client.post(
        "/api/businesses/biz_spice_garden/playground/messages",
        json={"message": "Message specifically for Playground"},
    )

    # 6. Verify Session 1 messages
    detail1 = api_client.get(f"/api/voice/sessions/{session_id_1}").json()
    texts1 = [m["content"] for m in detail1["messages"]]
    assert any("Call 1" in t for t in texts1)
    assert not any("Call 2" in t for t in texts1)
    assert not any("Playground" in t for t in texts1)

    # 7. Verify Session 2 messages
    detail2 = api_client.get(f"/api/voice/sessions/{session_id_2}").json()
    texts2 = [m["content"] for m in detail2["messages"]]
    assert any("Call 2" in t for t in texts2)
    assert not any("Call 1" in t for t in texts2)
    assert not any("Playground" in t for t in texts2)

    # 8. Verify Playground messages
    db = get_database_service()
    play_msgs = db.get_conversation_messages("biz_spice_garden")
    play_texts = [m["content"] for m in play_msgs]
    assert any("Playground" in t for t in play_texts)
    assert not any("Call 1" in t for t in play_texts)
    assert not any("Call 2" in t for t in play_texts)


# ==============================================================================
# 5. Voice Turn Orchestration & Error Boundary
# ==============================================================================

def test_voice_turn_orchestration(api_client, monkeypatch):
    """Voice turn executes shared LangGraph receptionist and returns assistant speech."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "We are open from 11:30 AM to 11:00 PM today."
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    # Start call
    inbound_resp = api_client.post("/api/voice/simulation/inbound", json={"called_number": "+91 80 4123 5678"})
    session_id = inbound_resp.json()["session_id"]

    # Send turn
    turn_resp = api_client.post(
        f"/api/voice/simulation/sessions/{session_id}/turns",
        json={"text": "What are your opening hours today?"},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert turn_data["session_id"] == session_id
    assert "11:30 AM to 11:00 PM" in turn_data["assistant_text"]
    assert turn_data["session_status"] == "active"


def test_safe_error_boundary(api_client, monkeypatch):
    """Orchestrator catches unexpected workflow exceptions and returns polite fallback without hallucinating."""
    # Force Groq LLM to raise an unexpected error
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("Groq upstream connection failed")
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    inbound_resp = api_client.post("/api/voice/simulation/inbound", json={"called_number": "+91 80 4123 5678"})
    session_id = inbound_resp.json()["session_id"]

    turn_resp = api_client.post(
        f"/api/voice/simulation/sessions/{session_id}/turns",
        json={"text": "Can I get a table?"},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert "technical difficulties" in turn_data["assistant_text"].lower()
    assert turn_data["pending_action"] is None


# ==============================================================================
# 6. Two-Phase Action Confirmation Preservation in Voice
# ==============================================================================

def test_two_phase_action_preservation_in_voice(api_client, monkeypatch):
    """When an action requires confirmation, it is proposed and persisted but not executed."""
    mock_client = MagicMock()

    # Step A: LLM proposes create_table_booking
    tool_call_obj = MagicMock()
    tool_call_obj.id = "call_mock_123"
    tool_call_obj.function.name = "create_table_booking"
    tool_call_obj.function.arguments = json.dumps({
        "customer_name": "Dr. Sarah",
        "customer_phone": "+91 98765 11111",
        "party_size": 4,
        "date": "2026-10-30",
        "time": "19:00",
    })

    choice1 = MagicMock()
    choice1.message.content = ""
    choice1.message.tool_calls = [tool_call_obj]

    # Step B: LLM summarizes proposal
    choice2 = MagicMock()
    choice2.message.content = "I have prepared your reservation for 4 guests on Oct 30 at 7:00 PM. Would you like me to confirm it?"
    choice2.message.tool_calls = None

    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[choice1]),
        MagicMock(choices=[choice2]),
    ]
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    # Start call
    inbound_resp = api_client.post("/api/voice/simulation/inbound", json={"called_number": "+91 80 4123 5678"})
    session_id = inbound_resp.json()["session_id"]

    # Send turn
    turn_resp = api_client.post(
        f"/api/voice/simulation/sessions/{session_id}/turns",
        json={"text": "Book a table for 4 under Dr. Sarah on Oct 30 at 7pm"},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert turn_data["pending_action"] is not None
    assert turn_data["pending_action"]["tool_id"] == "create_table_booking"
    assert turn_data["pending_action"]["status"] == "pending_confirmation"

    # Verify action is in database pending confirmation
    db = get_database_service()
    action = db.get_pending_action("biz_spice_garden")
    assert action is not None
    assert action["tool_id"] == "create_table_booking"
    assert action["status"] == "pending_confirmation"


# ==============================================================================
# 7. Concurrency Serialization
# ==============================================================================

def test_concurrency_serialization():
    """Concurrent turns for the same session are serialized via session lock."""
    db = get_database_service()
    session_manager = DatabaseVoiceSessionManager(db)

    # Create session
    event = InboundCallEvent(
        provider_call_id="test_conc_call",
        provider_name="mock",
        called_number="+91 80 4123 5678",
    )
    router = InboundCallRouter(db_service=db, session_manager=session_manager)
    res = router.route_inbound_call(event)
    session_id = res.session.session_id

    # Mock Groq
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Response from assistant."
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)

    orchestrator = VoiceTurnOrchestrator(
        db_service=db,
        session_manager=session_manager,
        groq_service=mock_service,
    )

    results = []
    errors = []

    def worker(idx: int):
        try:
            transcript = TranscriptEvent(
                session_id=session_id,
                turn_id=f"turn_{idx}",
                text=f"Turn message {idx}",
            )
            r = orchestrator.process_turn(session_id, transcript)
            results.append(r)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 3

    # Check that all messages exist in history
    history = session_manager.get_session_history("biz_spice_garden", session_id)
    user_turns = [m for m in history if m["role"] == "user"]
    assert len(user_turns) == 3


# ==============================================================================
# 8. Idempotent Call Termination & Audit CallRecord
# ==============================================================================

def test_idempotent_call_termination(api_client):
    """Terminating a voice session creates a CallRecord; subsequent termination calls are idempotent."""
    inbound_resp = api_client.post("/api/voice/simulation/inbound", json={"called_number": "+91 80 4123 5678"})
    session_id = inbound_resp.json()["session_id"]

    db = get_database_service()
    initial_call_count = len(db.get_call_history("biz_spice_garden"))

    # First termination
    term_resp1 = api_client.post(
        f"/api/voice/simulation/sessions/{session_id}/terminate",
        json={"reason": "completed", "summary": "Customer asked for directions."},
    )
    assert term_resp1.status_code == 200
    data1 = term_resp1.json()
    assert data1["status"] == "completed"

    # Call record created
    call_count_after1 = len(db.get_call_history("biz_spice_garden"))
    assert call_count_after1 == initial_call_count + 1

    # Second termination (idempotent repeat)
    term_resp2 = api_client.post(
        f"/api/voice/simulation/sessions/{session_id}/terminate",
        json={"reason": "completed"},
    )
    assert term_resp2.status_code == 200
    assert term_resp2.json()["status"] == "completed"

    # Verify no duplicate CallRecord was created
    call_count_after2 = len(db.get_call_history("biz_spice_garden"))
    assert call_count_after2 == call_count_after1


# ==============================================================================
# 9. Provider Webhook Signature Verification
# ==============================================================================

def test_webhook_signature_verification(api_client):
    """Webhook verifies HMAC signature: rejects invalid, accepts valid."""
    secret = "test_webhook_secret_key"
    register_telephony_provider("mock_sec", MockTelephonyProvider(webhook_secret=secret))

    payload = {
        "called_number": "+91 80 4123 5678",
        "caller_number": "+91 98765 43210",
        "provider_call_id": "call_sec_100",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")

    # 1. Invalid signature -> 401
    bad_headers = {"X-Mock-Signature": "invalid_sig_hex"}
    bad_resp = api_client.post(
        "/api/voice/webhook/mock_sec",
        content=raw_bytes,
        headers={"Content-Type": "application/json", **bad_headers},
    )
    assert bad_resp.status_code == 401
    assert "Invalid webhook signature" in bad_resp.json()["detail"]

    # 2. Valid signature -> 200
    valid_sig = hmac.new(secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    good_headers = {"X-Mock-Signature": valid_sig}
    good_resp = api_client.post(
        "/api/voice/webhook/mock_sec",
        content=raw_bytes,
        headers={"Content-Type": "application/json", **good_headers},
    )
    assert good_resp.status_code == 200
    assert good_resp.json()["action"] == "accept"


# ==============================================================================
# 10. Privacy Masking of Phone Numbers
# ==============================================================================

def test_phone_masking_and_privacy():
    """Verify telephone numbers are masked in events, representations, and CallRecord logs."""
    assert mask_phone_number("+91 80 4123 5678") == "+9180***5678"
    assert mask_phone_number("+14155552671") == "+1415***2671"
    assert mask_phone_number(None) == "[ANONYMOUS]"

    event = InboundCallEvent(
        provider_call_id="call_mask_test",
        called_number="+91 80 4123 5678",
        caller_number="+91 98765 43210",
    )
    assert "***" in event.masked_caller_number
    assert "***" in event.masked_called_number
    assert "***" in repr(event)
    assert "+91 98765 43210" not in repr(event)
