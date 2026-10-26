"""
Provider-independent interfaces and protocols for voice and telephony architecture.
Defines contracts for TelephonyProvider, SpeechToTextProvider, TextToSpeechProvider, and VoiceSessionManager.
"""

from typing import Optional, Dict, Any, List, Protocol, runtime_checkable
from abc import ABC, abstractmethod

from backend.voice.events import (
    InboundCallEvent,
    CallSession,
    TranscriptEvent,
    VoiceTurnResult,
    CallControlResult,
    ProviderCapabilities,
)


@runtime_checkable
class TelephonyProvider(Protocol):
    """
    Protocol for telephony platform integrations (Mock, Twilio, LiveKit, etc.).
    """

    @property
    def provider_name(self) -> str:
        """Identifier for the telephony provider."""
        ...

    def get_capabilities(self) -> ProviderCapabilities:
        """Return provider-specific feature flags and codec support."""
        ...

    def parse_inbound_webhook(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> InboundCallEvent:
        """Parse raw provider webhook payload into normalized InboundCallEvent."""
        ...

    def verify_webhook_signature(
        self,
        payload: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        """Verify cryptographic signature on incoming provider webhooks."""
        ...

    def accept_call(
        self,
        event: InboundCallEvent,
        greeting_text: Optional[str] = None,
    ) -> CallControlResult:
        """Answer inbound call and optionally queue an initial greeting."""
        ...

    def reject_call(
        self,
        event: InboundCallEvent,
        reason: str = "busy",
    ) -> CallControlResult:
        """Reject inbound call without answering."""
        ...

    def hangup_call(
        self,
        session_id: str,
        reason: str = "completed",
    ) -> CallControlResult:
        """Terminate an active call."""
        ...


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """
    Protocol for speech-to-text audio transcription.
    """

    @property
    def provider_name(self) -> str:
        """Identifier for the STT provider."""
        ...

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en",
    ) -> TranscriptEvent:
        """Convert audio buffer to a transcription event."""
        ...


@runtime_checkable
class TextToSpeechProvider(Protocol):
    """
    Protocol for text-to-speech audio synthesis.
    """

    @property
    def provider_name(self) -> str:
        """Identifier for the TTS provider."""
        ...

    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        language: str = "en",
    ) -> bytes:
        """Synthesize text into raw or encoded audio bytes."""
        ...


@runtime_checkable
class VoiceSessionManager(Protocol):
    """
    Protocol managing durable voice sessions, status transitions, and history.
    """

    def create_session(
        self,
        inbound_event: InboundCallEvent,
        business_id: str,
    ) -> CallSession:
        """Instantiate and persist a new voice session."""
        ...

    def get_session(self, session_id: str) -> Optional[CallSession]:
        """Fetch session by its ID."""
        ...

    def get_session_by_provider_call_id(
        self,
        provider_call_id: str,
        provider_name: str = "mock",
    ) -> Optional[CallSession]:
        """Fetch session by external provider call ID."""
        ...

    def get_session_by_correlation_id(self, correlation_id: str) -> Optional[CallSession]:
        """Fetch session by correlation ID (e.g. stream_sid)."""
        ...

    def update_session_metadata(
        self,
        session_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Optional[CallSession]:
        """Update session_metadata dictionary."""
        ...

    def update_last_turn(self, session_id: str) -> Optional[CallSession]:
        """Update last active turn timestamp on session."""
        ...

    def record_tool_used(self, session_id: str, tool_id: str) -> None:
        """Record an autonomous tool invoked during a voice session."""
        ...

    def get_session_tools(self, session_id: str) -> List[str]:
        """Retrieve all tools invoked during a session."""
        ...

    def terminate_session(
        self,
        session_id: str,
        reason: str = "completed",
        summary: Optional[str] = None,
    ) -> Optional[CallSession]:
        """End voice session and persist final call record idempotently."""
        ...

    def record_message(
        self,
        business_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        """Persist conversation turn scoped to the voice session."""
        ...

    def get_session_history(
        self,
        business_id: str,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation history scoped to the voice session."""
        ...
