"""
Automated test suite for Gnani.ai Vachana Voice Providers (Prisma STT & Timbre TTS).
"""

import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.voice.providers.gnani import (
    GnaniSTTProvider,
    GnaniTTSProvider,
    GNANI_SUPPORTED_LANGUAGES,
    GNANI_LANGUAGE_CODES,
    GNANI_VOICES,
)
from backend.voice.providers import get_stt_provider, get_tts_provider


client = TestClient(app)


def test_gnani_supported_languages_catalog():
    """Verify catalog includes all 12 core Indic locales and auto-detection."""
    assert len(GNANI_SUPPORTED_LANGUAGES) >= 12
    codes = set(GNANI_LANGUAGE_CODES)
    expected = {
        "indic-auto", "hi-IN", "en-IN", "bn-IN", "gu-IN",
        "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN", "as-IN"
    }
    assert expected.issubset(codes)


def test_gnani_voices_catalog():
    """Verify supported Timbre neural voices."""
    assert "Nalini" in GNANI_VOICES
    assert "Deepak" in GNANI_VOICES
    assert "Bhavna" in GNANI_VOICES


def test_gnani_stt_provider_transcribe_mock():
    """Verify GnaniSTTProvider transcribes audio with mock response."""
    provider = GnaniSTTProvider(api_key="vach_test_key_123")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "success": True,
        "transcript": "नमस्ते, मुझे टेबल बुक करनी है।",
        "detected_language_code": "hi-IN"
    }).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        event = provider.transcribe(b"dummy_wav_bytes", language="hi-IN")
        assert event.text == "नमस्ते, मुझे टेबल बुक करनी है।"
        assert event.is_final is True
        assert event.confidence > 0.9


def test_gnani_stt_provider_empty_audio():
    """Verify GnaniSTTProvider handles empty audio safely."""
    provider = GnaniSTTProvider(api_key="vach_test_key_123")
    event = provider.transcribe(b"")
    assert event.text == ""


def test_gnani_tts_provider_synthesize_mock():
    """Verify GnaniTTSProvider returns synthesized audio bytes."""
    provider = GnaniTTSProvider(api_key="vach_test_key_123", voice="Nalini")
    mock_audio_bytes = b"RIFF....WAVEfmt ...."
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = mock_audio_bytes
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        audio = provider.synthesize(text="Hello from CallMe", language="en-IN")
        assert audio == mock_audio_bytes


def test_gnani_tts_provider_empty_text():
    """Verify GnaniTTSProvider handles empty text gracefully."""
    provider = GnaniTTSProvider(api_key="vach_test_key_123")
    audio = provider.synthesize(text="")
    assert audio == b""


def test_gnani_provider_resolution():
    """Verify get_stt_provider and get_tts_provider resolve 'gnani' correctly."""
    stt = get_stt_provider("gnani")
    tts = get_tts_provider("gnani")
    assert isinstance(stt, GnaniSTTProvider)
    assert isinstance(tts, GnaniTTSProvider)
    assert stt.provider_name == "gnani"
    assert tts.provider_name == "gnani"


def test_web_voice_languages_endpoint():
    """Verify /api/voice/web/languages returns Gnani catalog."""
    resp = client.get("/api/voice/web/languages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "gnani"
    assert data["stt_model"] == "prisma-v3.0"
    assert data["tts_model"] == "timbre-v2.5"
    assert len(data["languages"]) >= 12
    lang_codes = [l["code"] for l in data["languages"]]
    assert "hi-IN" in lang_codes
    assert "en-IN" in lang_codes
    assert "indic-auto" in lang_codes
