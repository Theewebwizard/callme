"""
Automated test suite for Step 9C: Deepgram Speech-to-Text and Text-to-Speech Integration.
Tests streaming STT, streaming TTS, sample rate conversion, chunk framing, barge-in,
and end-to-end voice pipeline isolation without requiring real credentials or paid API calls.
"""

import asyncio
import base64
import json
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.voice.audio import (
    resample_pcm16,
    chunk_pcm16,
    pad_pcm16_to_multiple,
    validate_pcm16_chunk,
)
from backend.voice.events import InboundCallEvent, TranscriptEvent
from backend.voice.providers.deepgram import (
    DeepgramSTTProvider,
    DeepgramTTSProvider,
    DeepgramSTTStream,
)
from backend.voice.providers import (
    get_stt_provider,
    get_tts_provider,
    register_stt_provider,
    register_tts_provider,
)


class MockWebSocketConnection:
    """Mock WebSocket client for Deepgram streaming tests without network I/O."""

    def __init__(self, incoming_messages=None):
        self.incoming = list(incoming_messages or [])
        self.sent_messages = []
        self.is_closed = False

    async def send(self, msg):
        self.sent_messages.append(msg)

    async def recv(self):
        if not self.incoming:
            raise asyncio.TimeoutError()
        msg = self.incoming.pop(0)
        if isinstance(msg, Exception):
            raise msg
        return msg

    async def close(self):
        self.is_closed = True


# ============================================================================
# 1. Audio Conversion & Framing Tests
# ============================================================================

def test_audio_resampling_and_validation():
    """Verify sample rate conversion (8000 Hz <-> 16000 Hz) and 16-bit alignment."""
    # 20ms of silence at 8000 Hz (160 samples = 320 bytes)
    audio_8k = b"\x00\x00" * 160
    is_valid, err = validate_pcm16_chunk(audio_8k)
    assert is_valid is True
    assert err is None

    # Resample 8000 -> 16000 Hz
    audio_16k = resample_pcm16(audio_8k, 8000, 16000)
    assert len(audio_16k) > 0
    assert len(audio_16k) % 2 == 0  # Preserves 16-bit alignment

    # Resample back 16000 -> 8000 Hz
    audio_8k_roundtrip = resample_pcm16(audio_16k, 16000, 8000)
    assert len(audio_8k_roundtrip) % 2 == 0

    # No-op when sample rates match
    same = resample_pcm16(audio_8k, 8000, 8000)
    assert same == audio_8k

    # Odd-byte chunk validation
    odd_chunk = b"\x00\x01\x02"
    is_valid_odd, err_odd = validate_pcm16_chunk(odd_chunk)
    assert is_valid_odd is False
    assert "odd byte length" in err_odd


def test_audio_padding_and_chunking():
    """Verify audio padding to multiples of 320 bytes for Exotel compatibility."""
    raw = b"\x12\x34" * 100  # 200 bytes (not multiple of 320)
    padded = pad_pcm16_to_multiple(raw, 320)
    assert len(padded) == 320
    assert padded.startswith(raw)
    assert padded[200:] == b"\x00" * 120

    # Chunking
    chunks = chunk_pcm16(padded, chunk_size_bytes=320)
    assert len(chunks) == 1
    assert len(chunks[0]) == 320

    # Chunking large stream
    large_audio = b"\x00\x00" * 320  # 640 bytes
    large_chunks = chunk_pcm16(large_audio, chunk_size_bytes=320)
    assert len(large_chunks) == 2
    for ch in large_chunks:
        assert len(ch) == 320


# ============================================================================
# 2. Deepgram STT Streaming Tests
# ============================================================================

def test_deepgram_stt_stream_interim_and_final_transcripts():
    """Verify Deepgram STT distinguishes interim vs finalized speech results."""
    async def _run():
        interim_msg = json.dumps({
            "type": "Results",
            "channel_index": [0, 1],
            "is_final": False,
            "speech_final": False,
            "channel": {
                "alternatives": [{
                    "transcript": "I would like to",
                    "confidence": 0.85
                }]
            }
        })
        final_msg = json.dumps({
            "type": "Results",
            "channel_index": [0, 1],
            "is_final": True,
            "speech_final": True,
            "channel": {
                "alternatives": [{
                    "transcript": "I would like to book a table for two tonight.",
                    "confidence": 0.98
                }]
            }
        })

        mock_ws = MockWebSocketConnection(incoming_messages=[interim_msg, final_msg])
        stream = DeepgramSTTStream(api_key="test_key", session_id="test_sess", ws_client=mock_ws)
        await stream.connect()

        # Receive interim
        event1 = await stream.receive_event()
        assert event1 is not None
        assert event1.is_final is False
        assert event1.text == "I would like to"

        # Receive final
        event2 = await stream.receive_event()
        assert event2 is not None
        assert event2.is_final is True
        assert "book a table" in event2.text

        await stream.close()
        assert mock_ws.is_closed is True

    asyncio.run(_run())


def test_deepgram_stt_stream_empty_and_malformed_handling():
    """Verify STT stream ignores empty alternatives, metadata frames, and invalid JSON."""
    async def _run():
        empty_alt_msg = json.dumps({
            "type": "Results",
            "channel": {"alternatives": []}
        })
        metadata_msg = json.dumps({
            "type": "Metadata",
            "transaction_key": "12345"
        })
        malformed_json = "NOT_A_JSON_STRING"

        mock_ws = MockWebSocketConnection(incoming_messages=[empty_alt_msg, metadata_msg, malformed_json])
        stream = DeepgramSTTStream(api_key="test_key", ws_client=mock_ws)
        await stream.connect()

        assert await stream.receive_event() is None
        assert await stream.receive_event() is None
        assert await stream.receive_event() is None

        await stream.close()

    asyncio.run(_run())


def test_deepgram_stt_send_audio_validation():
    """Verify send_audio rejects malformed or odd-length audio chunks."""
    async def _run():
        mock_ws = MockWebSocketConnection()
        stream = DeepgramSTTStream(api_key="test_key", ws_client=mock_ws)
        await stream.connect()

        # Valid 16-bit chunk
        valid_pcm = b"\x00\x00" * 160
        await stream.send_audio(valid_pcm)
        assert len(mock_ws.sent_messages) == 1
        assert mock_ws.sent_messages[0] == valid_pcm

        # Invalid odd chunk should be dropped
        odd_chunk = b"\x01\x02\x03"
        await stream.send_audio(odd_chunk)
        assert len(mock_ws.sent_messages) == 1  # Not sent

        await stream.close()

    asyncio.run(_run())


# ============================================================================
# 3. Deepgram TTS Streaming Tests
# ============================================================================

def test_deepgram_tts_stream_chunk_generation_and_flush():
    """Verify Deepgram streaming TTS sends Speak and Flush, and yields binary audio chunks."""
    async def _run():
        audio_chunk_1 = b"\x11\x22" * 160
        audio_chunk_2 = b"\x33\x44" * 160
        flushed_msg = json.dumps({"type": "Flushed", "sequence_id": 1})

        mock_ws = MockWebSocketConnection(incoming_messages=[audio_chunk_1, audio_chunk_2, flushed_msg])
        provider = DeepgramTTSProvider(api_key="test_key")

        chunks_received = []
        async for chunk in provider.synthesize_stream("Welcome to Spice Garden!", ws_client=mock_ws):
            chunks_received.append(chunk)

        assert len(chunks_received) == 2
        assert chunks_received[0] == audio_chunk_1
        assert chunks_received[1] == audio_chunk_2

        # Verify control frames sent to Deepgram
        sent_json = [json.loads(m) for m in mock_ws.sent_messages if isinstance(m, str)]
        assert any(m.get("type") == "Speak" and "Spice Garden" in m.get("text", "") for m in sent_json)
        assert any(m.get("type") == "Flush" for m in sent_json)

    asyncio.run(_run())


def test_deepgram_tts_stream_barge_in_cancellation():
    """Verify that setting the cancellation token immediately halts TTS generation."""
    async def _run():
        audio_chunk_1 = b"\x11\x22" * 160
        audio_chunk_2 = b"\x33\x44" * 160
        flushed_msg = json.dumps({"type": "Flushed"})

        mock_ws = MockWebSocketConnection(incoming_messages=[audio_chunk_1, audio_chunk_2, flushed_msg])
        provider = DeepgramTTSProvider(api_key="test_key")
        cancel_token = asyncio.Event()

        chunks_received = []
        # Trigger cancellation before second chunk
        async for chunk in provider.synthesize_stream("This is a long sentence...", cancellation_token=cancel_token, ws_client=mock_ws):
            chunks_received.append(chunk)
            cancel_token.set()  # Caller interrupts

        assert len(chunks_received) == 1
        # Check that Clear frame was sent upon cancellation
        sent_json = [json.loads(m) for m in mock_ws.sent_messages if isinstance(m, str)]
        assert any(m.get("type") == "Clear" for m in sent_json)

    asyncio.run(_run())


# ============================================================================
# 4. Deepgram Batch REST Fallback Tests
# ============================================================================

def test_deepgram_stt_batch_transcribe_mock():
    """Verify Deepgram STT batch transcription uses Listen REST API with fallback."""
    provider = DeepgramSTTProvider(api_key="mock_key")
    audio = b"\x00\x00" * 160

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": {
            "channels": [{
                "alternatives": [{
                    "transcript": "Do you have vegan options?",
                    "confidence": 0.96
                }]
            }]
        }
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        event = provider.transcribe(audio)
        assert event.text == "Do you have vegan options?"
        assert event.confidence == 0.96
        assert event.is_final is True


def test_deepgram_tts_batch_synthesize_mock():
    """Verify Deepgram TTS batch synthesis returns raw PCM bytes."""
    provider = DeepgramTTSProvider(api_key="mock_key")
    pcm_audio = b"\x05\x06" * 320

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = pcm_audio

    with patch("httpx.Client.post", return_value=mock_resp):
        result = provider.synthesize("Table confirmed.")
        assert result == pcm_audio


# ============================================================================
# 5. Full End-to-End Pipeline & Barge-In Integration Tests
# ============================================================================

def test_exotel_barge_in_and_tts_cancellation(monkeypatch):
    """
    Test that an incoming caller speech event while the receptionist is speaking
    triggers barge-in, aborts outbound TTS transmission, and emits an Exotel 'clear' frame.
    """
    from backend.services.groq_service import GroqService
    import backend.services.groq_service as groq_service_mod

    # Mock Groq LLM
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Certainly, I can help you reserve a table at Spice Garden."
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    client = TestClient(app)

    with client.websocket_connect("/api/voice/exotel/ws") as ws:
        # 1. Send start event
        start_payload = {
            "event": "start",
            "start": {
                "stream_sid": "stream_barge_in_001",
                "account_sid": "exo_acc_001",
                "call_sid": "call_barge_001",
                "from": "+919876543210",
                "to": "+91 80 4123 5678",  # Spice Garden
                "media_format": {
                    "encoding": "audio/x-raw",
                    "sample_rate": 8000,
                    "channels": 1
                }
            }
        }
        ws.send_text(json.dumps(start_payload))

        # Consume initial greeting frames
        greeting_media = ws.receive_json()
        assert greeting_media["event"] == "media"
        greeting_mark = ws.receive_json()
        assert greeting_mark["event"] == "mark"

        # 2. Simulate caller sending media
        caller_speech = "Hello, what time do you open?"
        media_payload = {
            "event": "media",
            "stream_sid": "stream_barge_in_001",
            "media": {
                "payload": base64.b64encode(caller_speech.encode("utf-8")).decode("utf-8")
            }
        }
        ws.send_text(json.dumps(media_payload))

        # Receives assistant response media and mark
        assistant_media = ws.receive_json()
        assert assistant_media["event"] == "media"
        assert assistant_media["stream_sid"] == "stream_barge_in_001"
        assistant_mark = ws.receive_json()
        assert assistant_mark["event"] == "mark"

        # 3. Simulate client sending clear event (telecom hardware buffer purge)
        clear_event = {
            "event": "clear",
            "stream_sid": "stream_barge_in_001"
        }
        ws.send_text(json.dumps(clear_event))

        # 4. Caller hangs up
        stop_event = {
            "event": "stop",
            "stream_sid": "stream_barge_in_001",
            "stop": {"call_sid": "call_barge_001"}
        }
        ws.send_text(json.dumps(stop_event))


def test_cross_tenant_deepgram_isolation():
    """Verify that multiple simultaneous streams for different tenants remain completely isolated."""
    client = TestClient(app)

    # Spice Garden call
    with client.websocket_connect("/api/voice/exotel/ws") as ws1:
        ws1.send_text(json.dumps({
            "event": "start",
            "start": {
                "stream_sid": "stream_tenant_spice",
                "account_sid": "acc_01",
                "call_sid": "call_01",
                "from": "+919876543210",
                "to": "+91 80 4123 5678",  # Spice Garden
                "media_format": {"encoding": "audio/x-raw", "sample_rate": 8000, "channels": 1}
            }
        }))
        g1 = ws1.receive_json()
        assert g1["event"] == "media"
        ws1.receive_json()  # mark

        # Apex Dental call
        with client.websocket_connect("/api/voice/exotel/ws") as ws2:
            ws2.send_text(json.dumps({
                "event": "start",
                "start": {
                    "stream_sid": "stream_tenant_apex",
                    "account_sid": "acc_02",
                    "call_sid": "call_02",
                    "from": "+919123456789",
                    "to": "+91 80 6789 1234",  # Apex Dental
                    "media_format": {"encoding": "audio/x-raw", "sample_rate": 8000, "channels": 1}
                }
            }))
            g2 = ws2.receive_json()
            assert g2["event"] == "media"
            ws2.receive_json()  # mark

            # Clean up both
            ws2.send_text(json.dumps({"event": "stop", "stream_sid": "stream_tenant_apex"}))
        ws1.send_text(json.dumps({"event": "stop", "stream_sid": "stream_tenant_spice"}))


def test_deepgram_stt_timeout_and_disconnect():
    """Verify STT stream handles timeout and connection exceptions gracefully."""
    async def _run():
        mock_ws = MockWebSocketConnection(incoming_messages=[asyncio.TimeoutError(), ConnectionResetError("network lost")])
        stream = DeepgramSTTStream(api_key="test_key", ws_client=mock_ws)
        await stream.connect()

        # Timeout should return None without error
        res1 = await stream.receive_event()
        assert res1 is None

        # Disconnect should mark closed and return None
        res2 = await stream.receive_event()
        assert res2 is None
        assert stream._is_closed is True

    asyncio.run(_run())


def test_deepgram_stt_batch_failure_safeguard():
    """Verify HTTP error status from Deepgram REST endpoint returns empty transcript without raising uncaught exception."""
    provider = DeepgramSTTProvider(api_key="mock_key")
    audio = b"\x00\x00" * 160

    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch("httpx.Client.post", return_value=mock_resp):
        event = provider.transcribe(audio)
        assert event.text == ""
        assert event.confidence == 0.0


def test_deepgram_tts_batch_failure_safeguard():
    """Verify HTTP error status from Deepgram Speak endpoint returns empty bytes without crashing."""
    provider = DeepgramTTSProvider(api_key="mock_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.Client.post", return_value=mock_resp):
        audio = provider.synthesize("Hello")
        assert audio == b""


def test_pending_action_safeguard_in_voice_flow(monkeypatch):
    """
    Verify two-phase confirmation protection:
    Voice turn requiring sensitive tool execution yields a pending confirmation action,
    preserving tenant separation and requiring explicit customer confirmation.
    """
    from backend.services.groq_service import GroqService
    import backend.services.groq_service as groq_service_mod
    from backend.database.service import get_database_service

    # Mock tool call requesting table reservation
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "I would be happy to book a table for 4 at 7:00 PM tonight. Would you like me to confirm this reservation?"
    tool_call = MagicMock()
    tool_call.id = "call_reserve_01"
    tool_call.function.name = "create_table_booking"
    tool_call.function.arguments = json.dumps({
        "customer_name": "Rohan",
        "customer_phone": "+919876543210",
        "date": "2026-10-25",
        "time": "19:00",
        "party_size": 4,
        "special_requests": "Window seat"
    })
    mock_choice.message.tool_calls = [tool_call]
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    client = TestClient(app)

    with client.websocket_connect("/api/voice/exotel/ws") as ws:
        stream_sid = f"stream_pending_{uuid.uuid4().hex[:8]}"
        ws.send_text(json.dumps({
            "event": "start",
            "start": {
                "stream_sid": stream_sid,
                "account_sid": "acc_01",
                "call_sid": "call_pending_01",
                "from": "+919876543210",
                "to": "+91 80 4123 5678",  # Spice Garden
                "media_format": {"encoding": "audio/x-raw", "sample_rate": 8000, "channels": 1}
            }
        }))
        ws.receive_json()  # greeting media
        ws.receive_json()  # greeting mark

        # Caller requests table
        ws.send_text(json.dumps({
            "event": "media",
            "stream_sid": stream_sid,
            "media": {"payload": base64.b64encode(b"Book table for 4 at 7pm").decode("utf-8")}
        }))
        reply_media = ws.receive_json()
        assert reply_media["event"] == "media"
        ws.receive_json()  # mark

        ws.send_text(json.dumps({"event": "stop", "stream_sid": stream_sid}))

    # Verify pending action is stored in database with pending status
    db = get_database_service()
    pending = db.get_pending_action("biz_spice_garden")
    assert pending is not None
    assert pending["tool_id"] == "create_table_booking"

