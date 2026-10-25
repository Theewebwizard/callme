"""
Voice and Telephony Architecture Foundation package exports.
"""

from backend.voice.utils import normalize_phone_number, mask_phone_number
from backend.voice.events import (
    CallStatus,
    SessionStatus,
    ProviderCapabilities,
    InboundCallEvent,
    CallSession,
    TranscriptEvent,
    VoiceTurnResult,
    CallTerminationEvent,
    CallControlResult,
)
from backend.voice.interfaces import (
    TelephonyProvider,
    SpeechToTextProvider,
    TextToSpeechProvider,
    VoiceSessionManager,
)
from backend.voice.session_manager import DatabaseVoiceSessionManager
from backend.voice.router import (
    InboundCallRouter,
    CallRoutingResult,
    CallRoutingError,
    UnknownTenantError,
    InactiveTenantError,
    AmbiguousTenantError,
    TenantMismatchError,
)
from backend.voice.orchestrator import VoiceTurnOrchestrator
from backend.voice.audio import (
    resample_pcm16,
    pad_pcm16_to_multiple,
    chunk_pcm16,
    validate_pcm16_chunk,
)
from backend.voice.providers import (
    BaseTelephonyProvider,
    MockTelephonyProvider,
    MockSTTProvider,
    MockTTSProvider,
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
    DeepgramSTTProvider,
    DeepgramTTSProvider,
    DeepgramSTTStream,
    register_telephony_provider,
    register_stt_provider,
    register_tts_provider,
    get_telephony_provider,
    get_stt_provider,
    get_tts_provider,
)

__all__ = [
    # Utils
    "normalize_phone_number",
    "mask_phone_number",
    # Events & Models
    "CallStatus",
    "SessionStatus",
    "ProviderCapabilities",
    "InboundCallEvent",
    "CallSession",
    "TranscriptEvent",
    "VoiceTurnResult",
    "CallTerminationEvent",
    "CallControlResult",
    # Interfaces
    "TelephonyProvider",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "VoiceSessionManager",
    # Session Management
    "DatabaseVoiceSessionManager",
    # Routing & Orchestration
    "InboundCallRouter",
    "CallRoutingResult",
    "CallRoutingError",
    "UnknownTenantError",
    "InactiveTenantError",
    "AmbiguousTenantError",
    "TenantMismatchError",
    "VoiceTurnOrchestrator",
    # Providers
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
    # Audio utils
    "resample_pcm16",
    "pad_pcm16_to_multiple",
    "chunk_pcm16",
    "validate_pcm16_chunk",
]
