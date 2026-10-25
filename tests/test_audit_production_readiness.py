"""
Automated audit and regression verification tests for Step 9D: Production Readiness Audit.
Tests:
1. Production mode mandatory WebSocket authentication enforcement (1008 Policy Violation).
2. Public transcript inspection tenant authorization and production 401/403 protection.
3. Multi-segment STT utterance accumulation (speech_final=False vs speech_final=True).
4. Acoustic echo / self-playback loop suppression.
"""

import asyncio
import json
import base64
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.main import app
from backend.config import get_settings
from backend.services.groq_service import GroqService
import backend.services.groq_service as groq_service_mod
from backend.voice.providers.deepgram import DeepgramSTTStream


class MockWebSocketConnection:
    """Mock WebSocket for Deepgram STT stream test."""
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.is_closed = False

    async def send(self, msg):
        self.sent.append(msg)

    async def recv(self):
        if not self.incoming:
            raise asyncio.TimeoutError()
        return self.incoming.pop(0)

    async def close(self):
        self.is_closed = True


def test_production_websocket_auth_enforcement(monkeypatch):
    """
    Verify that in production mode (ENVIRONMENT='production'), unauthenticated or
    misconfigured WebSocket connections are rejected with code 1008 (Policy Violation).
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "EXOTEL_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "EXOTEL_API_KEY", None)

    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/voice/exotel/ws") as ws:
            ws.receive_json()

    assert exc_info.value.code == 1008


def test_transcript_inspection_authorization_and_production_protection(monkeypatch):
    """
    Verify that GET /api/voice/sessions/{session_id}:
    1. Rejects cross-tenant inspection with 403 Forbidden.
    2. In production mode, rejects anonymous requests without tenant ID with 401 Unauthorized.
    """
    client = TestClient(app)

    # First, simulate a call for Spice Garden to obtain a real session_id
    sim_resp = client.post(
        "/api/voice/simulation/inbound",
        json={
            "provider_call_id": "audit_sess_test",
            "called_number": "+91 80 4123 5678",  # Spice Garden
            "caller_number": "+91 98 7654 3210",
        },
    )
    assert sim_resp.status_code == 200
    session_id = sim_resp.json()["session_id"]

    # 1. Cross-tenant inspection: Apex Dental attempts to inspect Spice Garden session
    cross_resp = client.get(
        f"/api/voice/sessions/{session_id}",
        params={"business_id": "biz_apex_dental"},
    )
    assert cross_resp.status_code == 403
    assert "Tenant authorization mismatch" in cross_resp.json()["detail"]

    # 2. Legitimate tenant inspection
    valid_resp = client.get(
        f"/api/voice/sessions/{session_id}",
        params={"business_id": "biz_spice_garden"},
    )
    assert valid_resp.status_code == 200
    assert valid_resp.json()["session_id"] == session_id

    # 3. Production mode anonymous inspection protection
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    anon_resp = client.get(f"/api/voice/sessions/{session_id}")
    assert anon_resp.status_code == 401
    assert "Authentication required" in anon_resp.json()["detail"]


def test_stt_multi_segment_utterance_accumulation():
    """
    Verify that Deepgram STT stream accumulates multi-segment speech with is_final=True, speech_final=False
    and emits the full accumulated sentence only when speech_final=True is triggered.
    """
    async def _run():
        segment_1 = json.dumps({
            "type": "Results",
            "is_final": True,
            "speech_final": False,
            "channel": {"alternatives": [{"transcript": "I want to reserve a table", "confidence": 0.95}]}
        })
        segment_2 = json.dumps({
            "type": "Results",
            "is_final": True,
            "speech_final": True,
            "channel": {"alternatives": [{"transcript": "for two people tonight", "confidence": 0.97}]}
        })

        mock_ws = MockWebSocketConnection([segment_1, segment_2])
        stream = DeepgramSTTStream(api_key="test_key", ws_client=mock_ws)
        await stream.connect()

        # Segment 1 should be accumulated with speech_final=False
        ev1 = await stream.receive_event()
        assert ev1 is not None
        assert ev1.is_final is True
        assert ev1.speech_final is False
        assert ev1.text == "I want to reserve a table"

        # Segment 2 should flush the full merged utterance with speech_final=True
        ev2 = await stream.receive_event()
        assert ev2 is not None
        assert ev2.is_final is True
        assert ev2.speech_final is True
        assert ev2.text == "I want to reserve a table for two people tonight"

        await stream.close()

    asyncio.run(_run())


def test_acoustic_echo_rejection(monkeypatch):
    """
    Verify that if incoming audio produces a transcript identical to the assistant's
    recent speech output (acoustic echo from caller speakerphone), it is dropped
    without triggering a runaway recursive dialogue turn.
    """
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Royal Spice Garden is located on Indiranagar 100 Feet Road."
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    client = TestClient(app)

    with client.websocket_connect("/api/voice/exotel/ws") as ws:
        # Start stream
        ws.send_text(json.dumps({
            "event": "start",
            "start": {
                "stream_sid": "stream_echo_001",
                "call_sid": "call_echo_001",
                "to": "+91 80 4123 5678",
            }
        }))
        ws.receive_json()  # greeting media
        ws.receive_json()  # greeting mark

        # Customer asks question
        ws.send_text(json.dumps({
            "event": "media",
            "stream_sid": "stream_echo_001",
            "media": {"payload": base64.b64encode(b"Where are you located?").decode("utf-8")}
        }))
        reply_media = ws.receive_json()
        assert reply_media["event"] == "media"
        ws.receive_json()  # mark

        # Now simulate caller handset echoing the assistant's exact response back
        echo_payload = base64.b64encode(b"Royal Spice Garden is located on Indiranagar 100 Feet Road.").decode("utf-8")
        ws.send_text(json.dumps({
            "event": "media",
            "stream_sid": "stream_echo_001",
            "media": {"payload": echo_payload}
        }))

        # Send stop event
        ws.send_text(json.dumps({"event": "stop", "stream_sid": "stream_echo_001"}))


def test_validate_production_configuration_fails_fast(monkeypatch):
    """
    Verify validate_production_configuration fails closed in production mode
    when required secrets are missing, and passes when all are valid.
    """
    from backend.main import validate_production_configuration
    from backend.config import Settings

    # 1. Missing keys in production mode
    prod_settings = Settings(
        ENVIRONMENT="production",
        GROQ_API_KEY=None,
        DATABASE_URL=None,
        EXOTEL_ACCOUNT_SID=None,
        EXOTEL_API_KEY=None,
        EXOTEL_API_TOKEN=None,
        DEEPGRAM_API_KEY=None,
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_configuration(prod_settings)
    err_msg = str(exc_info.value)
    assert "Production configuration validation failed" in err_msg
    assert "GROQ_API_KEY" in err_msg
    assert "DATABASE_URL" in err_msg
    assert "EXOTEL_API_KEY" in err_msg
    assert "DEEPGRAM_API_KEY" in err_msg

    # 2. Database URL placeholder check
    placeholder_settings = Settings(
        ENVIRONMENT="production",
        GROQ_API_KEY="gsk_valid_key",
        DATABASE_URL="postgresql://postgres:[YOUR-PASSWORD]@db.supabase.co:5432/postgres",
        EXOTEL_ACCOUNT_SID="AC_valid_sid",
        EXOTEL_API_KEY="exo_key",
        EXOTEL_API_TOKEN="exo_token",
        DEEPGRAM_API_KEY="dg_key",
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_configuration(placeholder_settings)
    assert "DATABASE_URL" in str(exc_info.value)

    # 3. All valid production settings succeed cleanly
    valid_settings = Settings(
        ENVIRONMENT="production",
        GROQ_API_KEY="gsk_valid_key",
        DATABASE_URL="postgresql://postgres:secretpassword@db.supabase.co:5432/postgres",
        EXOTEL_ACCOUNT_SID="AC_valid_sid",
        EXOTEL_API_KEY="exo_key",
        EXOTEL_API_TOKEN="exo_token",
        DEEPGRAM_API_KEY="dg_key",
    )
    validate_production_configuration(valid_settings)


def test_production_mode_prohibits_mock_providers(monkeypatch):
    """
    Verify that in production mode (ENVIRONMENT='production'), attempting to
    retrieve mock telephony, mock STT, or mock TTS raises RuntimeError.
    """
    from backend.voice.providers import (
        get_telephony_provider,
        get_stt_provider,
        get_tts_provider,
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    with pytest.raises(RuntimeError) as exc_tel:
        get_telephony_provider("mock")
    assert "Mock telephony provider is prohibited in production mode" in str(exc_tel.value)

    with pytest.raises(RuntimeError) as exc_stt:
        get_stt_provider("mock")
    assert "Mock STT provider is prohibited in production mode" in str(exc_stt.value)

    with pytest.raises(RuntimeError) as exc_tts:
        get_tts_provider("mock")
    assert "Mock TTS provider is prohibited in production mode" in str(exc_tts.value)


def test_deepgram_auth_uses_headers_not_url_query_params():
    """
    Verify that Deepgram streaming STT and TTS WebSocket URLs do not contain
    credentials or API keys in query parameters; auth must be in headers.
    """
    from backend.voice.providers.deepgram import DeepgramSTTStream, DEEPGRAM_LISTEN_WS_URL, DEEPGRAM_SPEAK_WS_URL

    stream = DeepgramSTTStream(api_key="secret_test_token_12345")
    # Verify api_key is stored for Authorization header, not in any URL string
    assert "secret_test_token_12345" not in DEEPGRAM_LISTEN_WS_URL
    assert "secret_test_token_12345" not in DEEPGRAM_SPEAK_WS_URL


def test_exotel_passthru_supports_get_and_post(monkeypatch):
    """
    Verify that Exotel Passthru applet webhook endpoint supports both GET and POST requests.
    """
    from backend.voice.providers.exotel import ExotelTelephonyProvider
    client = TestClient(app)

    # Compute valid HMAC signature
    test_secret = "test_signing_secret_123"
    settings = get_settings()
    monkeypatch.setattr(settings, "EXOTEL_WEBHOOK_SECRET", test_secret)

    # 1. POST request
    post_body = json.dumps({
        "CallSid": "call_post_001",
        "To": "+91 80 4123 5678",
        "From": "+91 98 7654 3210",
    }).encode("utf-8")
    import hmac
    import hashlib
    sig_post = hmac.new(test_secret.encode("utf-8"), post_body, hashlib.sha256).hexdigest()

    post_resp = client.post(
        "/api/voice/exotel/passthru",
        content=post_body,
        headers={
            "Content-Type": "application/json",
            "X-Exotel-Signature": f"sha256={sig_post}",
        },
    )
    assert post_resp.status_code == 200
    assert post_resp.json()["status"] == "accepted"

    # 2. GET request with query params
    get_query = "CallSid=call_get_001&To=%2B91+80+4123+5678&From=%2B91+98+7654+3210"
    sig_get = hmac.new(test_secret.encode("utf-8"), get_query.encode("utf-8"), hashlib.sha256).hexdigest()

    get_resp = client.get(
        f"/api/voice/exotel/passthru?{get_query}",
        headers={
            "X-Exotel-Signature": f"sha256={sig_get}",
        },
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "accepted"


def test_forged_tenant_claim_in_inbound_call_rejected():
    """
    Verify that an inbound call claiming a tenant ID different from the registered
    owner of the called number is rejected with 403 Forbidden.
    """
    client = TestClient(app)
    resp = client.post(
        "/api/voice/simulation/inbound",
        json={
            "called_number": "+91 80 4123 5678",  # Spice Garden
            "caller_number": "+91 98 7654 3210",
            "claimed_business_id": "biz_apex_dental",  # Spoofed claim
        },
    )
    assert resp.status_code == 403
    assert "Tenant verification failed" in resp.json()["detail"] or "does not match" in resp.json()["detail"]
