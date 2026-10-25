"""
Base provider abstractions for telephony, STT, and TTS integrations.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from backend.voice.events import (
    InboundCallEvent,
    CallControlResult,
    ProviderCapabilities,
)
from backend.voice.interfaces import TelephonyProvider, SpeechToTextProvider, TextToSpeechProvider


class BaseTelephonyProvider(ABC):
    """Abstract base class for telephony platform adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name identifier."""
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return provider capabilities."""
        raise NotImplementedError

    @abstractmethod
    def parse_inbound_webhook(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> InboundCallEvent:
        """Normalize raw incoming webhook payload into InboundCallEvent."""
        raise NotImplementedError

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        """Verify webhook signature."""
        raise NotImplementedError

    @abstractmethod
    def accept_call(
        self,
        event: InboundCallEvent,
        greeting_text: Optional[str] = None,
    ) -> CallControlResult:
        """Accept inbound call."""
        raise NotImplementedError

    @abstractmethod
    def reject_call(
        self,
        event: InboundCallEvent,
        reason: str = "busy",
    ) -> CallControlResult:
        """Reject inbound call."""
        raise NotImplementedError

    @abstractmethod
    def hangup_call(
        self,
        session_id: str,
        reason: str = "completed",
    ) -> CallControlResult:
        """Terminate call session."""
        raise NotImplementedError
