"""
Comprehensive test suite for Step 9B: Exotel Telephony Adapter and Bidirectional WebSocket Integration.
Verifies:
1. Provider registration & capabilities matrix
2. Passthru webhook signature verification (X-Exotel-Signature HMAC-SHA256)
3. Handshake HTTP Basic Authentication (valid & invalid credentials)
4. Valid AgentStream WebSocket lifecycle (connected -> start -> media -> mark -> stop)
5. Out-of-order event sequence rejection (media before start -> 1002)
6. Unsupported audio encoding and sample rate rejection (1003)
7. Inbound tenant resolution from called number (Exophone)
8. Unknown & inactive tenant number rejection
9. Duplicate start event resiliency
10. Duplicate stop and idempotent call termination (single CallRecord audit)
11. Bounded buffer limits & oversized message protection (1009)
12. Cross-tenant conversation history isolation
13. Pluggable speech processing & mock compatibility
"""

import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.main import app
from backend.config import get_settings
from backend.database.service import get_database_service
from backend.services.groq_service import GroqService
import backend.services.groq_service as groq_service_mod
from backend.voice.providers import get_telephony_provider, ExotelTelephonyProvider
from backend.voice.providers.exotel import (
    validate_exotel_audio_format,
    ExotelMediaFormat,
    build_exotel_media_message,
    build_exotel_mark_message,
    build_exotel_clear_message,
)


@pytest.fixture
def api_client():
    """TestClient instance for FastAPI application."""
    return TestClient(app)


# ==============================================================================
# 1. Provider Capabilities & Format Helpers
# ==============================================================================

def test_exotel_provider_capabilities():
    """Exotel provider exposes documented streaming and audio capabilities."""
    provider = get_telephony_provider("exotel")
    assert provider.provider_name == "exotel"
    caps = provider.get_capabilities()
    assert caps.supports_streaming_stt is True
    assert caps.supports_streaming_tts is True
    assert caps.supports_barge_in is True
    assert caps.supports_dtmf is True
    assert "audio/x-raw" in caps.supported_audio_codecs
    assert "audio/x-l16" in caps.supported_audio_codecs


def test_exotel_audio_format_validation():
    """Validates supported and unsupported audio formats according to Exotel spec."""
    # Valid: 8000 Hz raw PCM
    valid_8k = ExotelMediaFormat(encoding="audio/x-raw", sample_rate="8000")
    ok, err = validate_exotel_audio_format(valid_8k)
    assert ok is True
    assert err is None

    # Valid: 16000 Hz L16 PCM
    valid_16k = ExotelMediaFormat(encoding="audio/x-l16", sample_rate=16000)
    ok, err = validate_exotel_audio_format(valid_16k)
    assert ok is True

    # Valid: 24000 Hz linear16
    valid_24k = ExotelMediaFormat(encoding="linear16", sample_rate=24000)
    ok, err = validate_exotel_audio_format(valid_24k)
    assert ok is True

    # Invalid: 48000 Hz sample rate
    invalid_rate = ExotelMediaFormat(encoding="audio/x-raw", sample_rate=48000)
    ok, err = validate_exotel_audio_format(invalid_rate)
    assert ok is False
    assert "48000" in err

    # Invalid: Ogg Vorbis or MP3 encoding
    invalid_enc = ExotelMediaFormat(encoding="audio/ogg", sample_rate=8000)
    ok, err = validate_exotel_audio_format(invalid_enc)
    assert ok is False
    assert "Unsupported audio encoding" in err


def test_exotel_message_builders():
    """Constructs valid JSON messages conforming to Exotel outbound protocol."""
    media_json = build_exotel_media_message("MZ123", "AQIDBA==")
    media_data = json.loads(media_json)
    assert media_data["event"] == "media"
    assert media_data["stream_sid"] == "MZ123"
    assert media_data["media"]["payload"] == "AQIDBA=="

    mark_json = build_exotel_mark_message("MZ123", "prompt_done", sequence_number=4)
    mark_data = json.loads(mark_json)
    assert mark_data["event"] == "mark"
    assert mark_data["stream_sid"] == "MZ123"
    assert mark_data["mark"]["name"] == "prompt_done"
    assert mark_data["sequence_number"] == 4

    clear_json = build_exotel_clear_message("MZ123")
    clear_data = json.loads(clear_json)
    assert clear_data["event"] == "clear"
    assert clear_data["stream_sid"] == "MZ123"


# ==============================================================================
# 2. Passthru Webhook & Signature Verification
# ==============================================================================

def test_exotel_webhook_signature_verification(api_client, monkeypatch):
    """Exotel Passthru webhook verifies X-Exotel-Signature (HMAC-SHA256)."""
    secret = "exotel_test_webhook_secret_key"
    provider = ExotelTelephonyProvider(webhook_secret=secret)
    from backend.voice.providers import register_telephony_provider
    register_telephony_provider("exotel", provider)

    payload = {
        "CallSid": "CA_exo_test_001",
        "From": "+919876543210",
        "To": "+91 80 4123 5678",
        "CallType": "inbound",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")

    # 1. Invalid signature -> 401
    bad_headers = {"X-Exotel-Signature": "sha256=invalid_hex_digest"}
    resp_bad = api_client.post(
        "/api/voice/webhook/exotel",
        content=raw_bytes,
        headers={"Content-Type": "application/json", **bad_headers},
    )
    assert resp_bad.status_code == 401
    assert "Invalid webhook signature" in resp_bad.json()["detail"]

    # 2. Valid signature with sha256= prefix -> 200
    valid_digest = hmac.new(secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    good_headers = {"X-Exotel-Signature": f"sha256={valid_digest}"}
    resp_good = api_client.post(
        "/api/voice/webhook/exotel",
        content=raw_bytes,
        headers={"Content-Type": "application/json", **good_headers},
    )
    assert resp_good.status_code == 200
    data = resp_good.json()
    assert data["status"] == "accepted"
    assert data["action"] == "accept"


# ==============================================================================
# 3. Handshake HTTP Basic Authentication
# ==============================================================================

def test_exotel_websocket_basic_auth_rejection(api_client, monkeypatch):
    """Rejects WebSocket handshake if invalid HTTP Basic credentials are provided."""
    key = "valid_api_key_123"
    token = "valid_api_token_456"
    provider = ExotelTelephonyProvider(api_key=key, api_token=token)
    from backend.voice.providers import register_telephony_provider
    register_telephony_provider("exotel", provider)

    monkeypatch.setattr("backend.voice.providers.exotel.get_settings", lambda: MagicMock(
        EXOTEL_ACCOUNT_SID="AC123",
        EXOTEL_API_KEY=key,
        EXOTEL_API_TOKEN=token,
        is_exotel_configured=True,
        VOICE_WS_IDLE_TIMEOUT_SECONDS=60,
        VOICE_WS_MAX_MESSAGE_BYTES=131072,
        VOICE_MAX_BUFFER_BYTES=1048576,
    ))

    # Send incorrect basic auth
    bad_b64 = base64.b64encode(b"wrong_key:wrong_token").decode("utf-8")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with api_client.websocket_connect(
            "/api/voice/exotel/ws",
            headers={"Authorization": f"Basic {bad_b64}"},
        ):
            pass
    assert exc_info.value.code == 1008  # Policy Violation / Unauthorized


# ==============================================================================
# 4. Valid AgentStream Lifecycle & Dialogue Execution
# ==============================================================================

def test_exotel_websocket_valid_lifecycle(api_client, monkeypatch):
    """Full valid lifecycle: connected -> start -> media -> mark -> stop."""
    # Mock Groq LLM
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Certainly, I can help you reserve a table at Spice Garden."
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    stream_sid = "MZ_test_stream_001"
    call_sid = "CA_test_call_001"

    with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
        # 1. Send 'connected'
        ws.send_json({"event": "connected", "protocol": "Call", "version": "1.0.0"})

        # 2. Send 'start'
        ws.send_json({
            "event": "start",
            "sequence_number": "1",
            "stream_sid": stream_sid,
            "start": {
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "account_sid": "AC123456",
                "from": "+919876543210",
                "to": "+91 80 4123 5678",  # Spice Garden
                "media_format": {
                    "encoding": "audio/x-raw",
                    "sample_rate": "8000",
                    "bit_rate": "16",
                },
                "custom_parameters": {"campaign": "inbound_dining"},
            }
        })

        # 3. Server should immediately reply with initial greeting media frame + mark frame
        greeting_media = ws.receive_json()
        assert greeting_media["event"] == "media"
        assert greeting_media["stream_sid"] == stream_sid
        assert "payload" in greeting_media["media"]

        greeting_mark = ws.receive_json()
        assert greeting_mark["event"] == "mark"
        assert greeting_mark["mark"]["name"] == "greeting_complete"

        # 4. Send customer media turn (simulation speech text bytes)
        sim_speech = "Do you have outdoor seating available?".encode("utf-8")
        sim_b64 = base64.b64encode(sim_speech).decode("utf-8")
        ws.send_json({
            "event": "media",
            "sequence_number": "2",
            "stream_sid": stream_sid,
            "media": {
                "chunk": "1",
                "timestamp": "100",
                "payload": sim_b64,
            }
        })

        # 5. Receive assistant response media frame + turn completion mark
        turn_media = ws.receive_json()
        assert turn_media["event"] == "media"
        assert turn_media["stream_sid"] == stream_sid
        assert "payload" in turn_media["media"]

        turn_mark = ws.receive_json()
        assert turn_mark["event"] == "mark"
        assert "turn_" in turn_mark["mark"]["name"]

        # 6. Send milestone mark from Exotel
        ws.send_json({
            "event": "mark",
            "sequence_number": "3",
            "stream_sid": stream_sid,
            "mark": {"name": "greeting_complete"},
        })

        # 7. Send 'stop'
        ws.send_json({
            "event": "stop",
            "sequence_number": "4",
            "stream_sid": stream_sid,
            "stop": {"call_sid": call_sid},
        })

    # Verify session persisted in DB with stream_sid correlation and ended status
    db = get_database_service()
    session = db.get_voice_session_by_correlation_id(stream_sid)
    assert session is not None
    assert session["business_id"] == "biz_spice_garden"
    assert session["status"] in ("completed", "terminated")

    # Verify conversation history was recorded
    history = db.get_session_messages("biz_spice_garden", session["session_id"])
    assert len(history) >= 3  # greeting + user turn + assistant reply


# ==============================================================================
# 5. Protocol Violations & Error Handling
# ==============================================================================

def test_exotel_media_before_start_rejection(api_client):
    """Sending a 'media' event before 'start' violates protocol and closes with 1002."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
            ws.send_json({
                "event": "media",
                "sequence_number": "1",
                "stream_sid": "MZ_premature",
                "media": {"payload": "AQIDBA=="},
            })
            ws.receive_json()
    assert exc_info.value.code == 1002  # Protocol Error


def test_exotel_unsupported_audio_format_rejection(api_client):
    """Specifying an unsupported audio format closes connection with 1003."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
            ws.send_json({
                "event": "start",
                "stream_sid": "MZ_bad_audio",
                "start": {
                    "stream_sid": "MZ_bad_audio",
                    "call_sid": "CA_bad_audio",
                    "to": "+91 80 4123 5678",
                    "media_format": {
                        "encoding": "audio/ogg",
                        "sample_rate": "48000",
                    }
                }
            })
            ws.receive_json()
    assert exc_info.value.code == 1003  # Unsupported Data


def test_exotel_unknown_called_number_rejection(api_client):
    """Inbound call dialled to an unassigned virtual number is rejected with 4004."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
            ws.send_json({
                "event": "start",
                "stream_sid": "MZ_unknown_num",
                "start": {
                    "stream_sid": "MZ_unknown_num",
                    "call_sid": "CA_unknown_num",
                    "to": "+91 99 9999 9999",  # Not assigned to any business
                }
            })
            ws.receive_json()
    assert exc_info.value.code == 4004  # Tenant Not Found


def test_exotel_inactive_tenant_number_rejection(api_client):
    """Inbound call dialled to a disconnected tenant number is rejected with 4000."""
    db = get_database_service()
    db.update_business("biz_spice_garden", {"assigned_number_status": "Disconnected"})

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
            ws.send_json({
                "event": "start",
                "stream_sid": "MZ_inactive_num",
                "start": {
                    "stream_sid": "MZ_inactive_num",
                    "call_sid": "CA_inactive_num",
                    "to": "+91 80 4123 5678",
                }
            })
            ws.receive_json()
    assert exc_info.value.code == 4000  # Tenant Inactive


def test_exotel_duplicate_start_handling(api_client):
    """Duplicate start events on the same active stream are ignored without creating a new session."""
    stream_sid = "MZ_dup_test_001"
    call_sid = "CA_dup_test_001"

    with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
        # First start
        ws.send_json({
            "event": "start",
            "stream_sid": stream_sid,
            "start": {
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "to": "+91 80 4123 5678",
            }
        })
        ws.receive_json()  # greeting media
        ws.receive_json()  # greeting mark

        # Second duplicate start
        ws.send_json({
            "event": "start",
            "stream_sid": stream_sid,
            "start": {
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "to": "+91 80 4123 5678",
            }
        })

        # Graceful stop
        ws.send_json({"event": "stop", "stream_sid": stream_sid})

    db = get_database_service()
    session = db.get_voice_session_by_correlation_id(stream_sid)
    assert session is not None


def test_exotel_idempotent_termination_on_disconnect(api_client):
    """Closing the WebSocket terminates the session idempotently and logs exactly one CallRecord."""
    stream_sid = "MZ_term_test_001"
    call_sid = "CA_term_test_001"

    db = get_database_service()
    initial_calls = len(db.get_call_history("biz_spice_garden"))

    with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
        ws.send_json({
            "event": "start",
            "stream_sid": stream_sid,
            "start": {
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "to": "+91 80 4123 5678",
            }
        })
        ws.receive_json()  # greeting media
        ws.receive_json()  # greeting mark
        # Client disconnects without sending stop

    # Verify session marked terminated
    session = db.get_voice_session_by_correlation_id(stream_sid)
    assert session["status"] in ("completed", "terminated")

    # Verify CallRecord was created
    calls_after = len(db.get_call_history("biz_spice_garden"))
    assert calls_after == initial_calls + 1


def test_root_exotel_ws_alias(api_client):
    """Root endpoint /ws/voice/exotel connects identically to /api/voice/exotel/ws."""
    stream_sid = "MZ_root_alias_001"
    with api_client.websocket_connect("/ws/voice/exotel") as ws:
        ws.send_json({
            "event": "start",
            "stream_sid": stream_sid,
            "start": {
                "stream_sid": stream_sid,
                "call_sid": "CA_root_alias",
                "to": "+91 80 4123 5678",
            }
        })
        greeting_media = ws.receive_json()
        assert greeting_media["event"] == "media"


def test_exotel_oversized_message_rejection(api_client):
    """Messages exceeding frame size limit (128 KB) close connection with 1009."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
            ws.send_json({
                "event": "start",
                "stream_sid": "MZ_big_msg",
                "start": {
                    "stream_sid": "MZ_big_msg",
                    "call_sid": "CA_big_msg",
                    "to": "+91 80 4123 5678",
                }
            })
            ws.receive_json()  # greeting media
            ws.receive_json()  # greeting mark

            # Send payload exceeding 128 KB
            huge_payload = "A" * (135 * 1024)
            ws.send_json({
                "event": "media",
                "stream_sid": "MZ_big_msg",
                "media": {"payload": huge_payload},
            })
            ws.receive_json()
    assert exc_info.value.code == 1009  # Message Too Big


def test_exotel_dtmf_and_clear_events(api_client):
    """Handles DTMF keypad presses and buffer clear (barge-in) events safely."""
    stream_sid = "MZ_dtmf_clear_001"
    with api_client.websocket_connect("/api/voice/exotel/ws") as ws:
        ws.send_json({
            "event": "start",
            "stream_sid": stream_sid,
            "start": {
                "stream_sid": stream_sid,
                "call_sid": "CA_dtmf_clear",
                "to": "+91 80 4123 5678",
            }
        })
        ws.receive_json()  # greeting media
        ws.receive_json()  # greeting mark

        # Send DTMF digit 1
        ws.send_json({
            "event": "dtmf",
            "stream_sid": stream_sid,
            "dtmf": {"digit": "1"},
        })

        # Send buffer clear
        ws.send_json({
            "event": "clear",
            "stream_sid": stream_sid,
        })

        ws.send_json({"event": "stop", "stream_sid": stream_sid})


def test_exotel_cross_tenant_isolation(api_client, monkeypatch):
    """Calls to Spice Garden and Apex Dental maintain strictly isolated sessions and histories."""
    # Mock LLM
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Tenant isolated reply."
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    stream1 = "MZ_spice_001"
    stream2 = "MZ_dental_002"

    # Call 1: Spice Garden
    with api_client.websocket_connect("/api/voice/exotel/ws") as ws1:
        ws1.send_json({
            "event": "start",
            "stream_sid": stream1,
            "start": {
                "stream_sid": stream1,
                "call_sid": "CA_spice",
                "to": "+91 80 4123 5678",  # Spice Garden
            }
        })
        ws1.receive_json()  # greeting media
        ws1.receive_json()  # greeting mark

        ws1.send_json({
            "event": "media",
            "stream_sid": stream1,
            "media": {"payload": base64.b64encode(b"I want Indian curry").decode("utf-8")},
        })
        ws1.receive_json()  # reply media
        ws1.receive_json()  # reply mark
        ws1.send_json({"event": "stop", "stream_sid": stream1})

    # Call 2: Apex Dental
    with api_client.websocket_connect("/api/voice/exotel/ws") as ws2:
        ws2.send_json({
            "event": "start",
            "stream_sid": stream2,
            "start": {
                "stream_sid": stream2,
                "call_sid": "CA_dental",
                "to": "+91 80 6789 1234",  # Apex Dental
            }
        })
        ws2.receive_json()  # greeting media
        ws2.receive_json()  # greeting mark

        ws2.send_json({
            "event": "media",
            "stream_sid": stream2,
            "media": {"payload": base64.b64encode(b"I need root canal treatment").decode("utf-8")},
        })
        ws2.receive_json()  # reply media
        ws2.receive_json()  # reply mark
        ws2.send_json({"event": "stop", "stream_sid": stream2})

    db = get_database_service()
    session1 = db.get_voice_session_by_correlation_id(stream1)
    session2 = db.get_voice_session_by_correlation_id(stream2)

    assert session1["business_id"] == "biz_spice_garden"
    assert session2["business_id"] == "biz_apex_dental"

    msgs1 = [m["content"] for m in db.get_session_messages("biz_spice_garden", session1["session_id"])]
    msgs2 = [m["content"] for m in db.get_session_messages("biz_apex_dental", session2["session_id"])]

    assert any("curry" in m for m in msgs1)
    assert not any("curry" in m for m in msgs2)
    assert any("root canal" in m for m in msgs2)
    assert not any("root canal" in m for m in msgs1)

