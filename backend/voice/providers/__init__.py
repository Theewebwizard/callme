"""
Voice and telephony providers registry and factory functions.
"""

from typing import Dict, Optional

from backend.voice.interfaces import TelephonyProvider, SpeechToTextProvider, TextToSpeechProvider
from backend.voice.providers.base import BaseTelephonyProvider
from backend.voice.providers.mock import MockTelephonyProvider, MockSTTProvider, MockTTSProvider
from backend.voice.providers.deepgram import (
    DeepgramSTTProvider,
    DeepgramTTSProvider,
    DeepgramSTTStream,
)
from backend.voice.providers.groq_speech import (
    GroqSTTProvider,
    GroqTTSProvider,
    GroqSTTStream,
)
from backend.voice.providers.exotel import (
    ExotelTelephonyProvider,
    ExotelWebSocketMessage,
    ExotelStartData,
    ExotelMediaData,
    ExotelStopData,
    ExotelMarkData,
    ExotelDtmfData,
    ExotelMediaFormat,
    build_exotel_media_message,
    build_exotel_mark_message,
    build_exotel_clear_message,
    validate_exotel_audio_format,
)

_TELEPHONY_PROVIDERS: Dict[str, TelephonyProvider] = {
    "mock": MockTelephonyProvider(),
    "exotel": ExotelTelephonyProvider(),
}

_STT_PROVIDERS: Dict[str, SpeechToTextProvider] = {
    "mock": MockSTTProvider(),
    "deepgram": DeepgramSTTProvider(),
    "deepgram_stt": DeepgramSTTProvider(),
    "groq": GroqSTTProvider(),
    "groq_stt": GroqSTTProvider(),
}

_TTS_PROVIDERS: Dict[str, TextToSpeechProvider] = {
    "mock": MockTTSProvider(),
    "deepgram": DeepgramTTSProvider(),
    "deepgram_tts": DeepgramTTSProvider(),
    "groq": GroqTTSProvider(),
    "groq_tts": GroqTTSProvider(),
}


def register_telephony_provider(name: str, provider: TelephonyProvider) -> None:
    """Register or replace a telephony provider implementation."""
    _TELEPHONY_PROVIDERS[name.lower()] = provider


def register_stt_provider(name: str, provider: SpeechToTextProvider) -> None:
    """Register or replace an STT provider implementation."""
    _STT_PROVIDERS[name.lower()] = provider


def register_tts_provider(name: str, provider: TextToSpeechProvider) -> None:
    """Register or replace a TTS provider implementation."""
    _TTS_PROVIDERS[name.lower()] = provider


def get_telephony_provider(name: str = "mock") -> TelephonyProvider:
    """Retrieve telephony provider by name, defaulting to mock in non-production."""
    from backend.config import get_settings
    settings = get_settings()

    target = name.lower()
    if settings.ENVIRONMENT == "production" and target == "mock":
        raise RuntimeError("Mock telephony provider is prohibited in production mode. Use 'exotel'.")

    prov = _TELEPHONY_PROVIDERS.get(target)
    if not prov:
        raise ValueError(f"Unknown telephony provider: '{name}'. Available: {list(_TELEPHONY_PROVIDERS.keys())}")
    return prov


def get_stt_provider(name: Optional[str] = None) -> SpeechToTextProvider:
    """
    Retrieve STT provider by name.
    If name is None or 'default', returns deepgram if configured, else groq if configured, else mock.
    """
    from backend.config import get_settings
    settings = get_settings()

    if name is None or name.lower() == "default":
        if settings.is_deepgram_configured:
            target = "deepgram"
        elif settings.GROQ_API_KEY:
            target = "groq"
        else:
            target = "mock"
    else:
        target = name.lower()

    if settings.ENVIRONMENT == "production" and target == "mock":
        raise RuntimeError("Mock STT provider is prohibited in production mode. Configure DEEPGRAM_API_KEY or GROQ_API_KEY.")

    prov = _STT_PROVIDERS.get(target)
    if not prov:
        raise ValueError(f"Unknown STT provider: '{name}'. Available: {list(_STT_PROVIDERS.keys())}")
    return prov


def get_tts_provider(name: Optional[str] = None) -> TextToSpeechProvider:
    """
    Retrieve TTS provider by name.
    If name is None or 'default', returns deepgram if configured, else groq if configured, else mock.
    """
    from backend.config import get_settings
    settings = get_settings()

    if name is None or name.lower() == "default":
        if settings.is_deepgram_configured:
            target = "deepgram"
        elif settings.GROQ_API_KEY:
            target = "groq"
        else:
            target = "mock"
    else:
        target = name.lower()

    if settings.ENVIRONMENT == "production" and target == "mock":
        raise RuntimeError("Mock TTS provider is prohibited in production mode. Configure DEEPGRAM_API_KEY or GROQ_API_KEY.")

    prov = _TTS_PROVIDERS.get(target)
    if not prov:
        raise ValueError(f"Unknown TTS provider: '{name}'. Available: {list(_TTS_PROVIDERS.keys())}")
    return prov


__all__ = [
    "BaseTelephonyProvider",
    "MockTelephonyProvider",
    "MockSTTProvider",
    "MockTTSProvider",
    "ExotelTelephonyProvider",
    "ExotelWebSocketMessage",
    "ExotelStartData",
    "ExotelMediaData",
    "ExotelStopData",
    "ExotelMarkData",
    "ExotelDtmfData",
    "ExotelMediaFormat",
    "build_exotel_media_message",
    "build_exotel_mark_message",
    "build_exotel_clear_message",
    "validate_exotel_audio_format",
    "DeepgramSTTProvider",
    "DeepgramTTSProvider",
    "DeepgramSTTStream",
    "register_telephony_provider",
    "register_stt_provider",
    "register_tts_provider",
    "get_telephony_provider",
    "get_stt_provider",
    "get_tts_provider",
]
