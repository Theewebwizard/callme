"""
Mock voice providers for simulation, local development, and testing.
Provides deterministic mock implementations of Telephony, STT, and TTS without external network dependencies.
"""

from typing import Optional, Dict, Any, List
import hmac
import hashlib
import uuid
import logging

import asyncio
from backend.database.models import utcnow
from backend.voice.audio import pad_pcm16_to_multiple
from backend.voice.events import (
    InboundCallEvent,
    CallControlResult,
    ProviderCapabilities,
    TranscriptEvent,
    CallStatus,
)
from backend.voice.providers.base import BaseTelephonyProvider

logger = logging.getLogger(__name__)


class MockTelephonyProvider(BaseTelephonyProvider):
    """
    Mock telephony provider for testing and sandbox simulations.
    Supports configurable signature verification and webhook parsing.
    """

    def __init__(self, webhook_secret: Optional[str] = None) -> None:
        self.webhook_secret = webhook_secret

    @property
    def provider_name(self) -> str:
        return "mock"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="mock",
            supports_streaming_stt=False,
            supports_streaming_tts=False,
            supports_barge_in=False,
            supports_dtmf=True,
            supports_call_recording=False,
            supported_audio_codecs=["mulaw", "pcm", "mp3"],
        )

    def parse_inbound_webhook(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> InboundCallEvent:
        """
        Parses inbound payload. Supports both standard format and telephony provider aliases.
        """
        provider_call_id = (
            payload.get("provider_call_id")
            or payload.get("CallSid")
            or payload.get("call_id")
            or f"mock_call_{uuid.uuid4().hex[:12]}"
        )
        called_number = (
            payload.get("called_number")
            or payload.get("To")
            or payload.get("to")
            or ""
        )
        caller_number = (
            payload.get("caller_number")
            or payload.get("From")
            or payload.get("from")
        )
        call_status = payload.get("call_status", CallStatus.INITIATED.value)

        return InboundCallEvent(
            provider_call_id=str(provider_call_id),
            provider_name=self.provider_name,
            called_number=str(called_number),
            caller_number=str(caller_number) if caller_number else None,
            call_status=call_status,
            timestamp=utcnow(),
            metadata=payload.get("metadata", {}),
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verify HMAC-SHA256 signature if secret is provided or configured.
        Headers checked: 'X-Mock-Signature', 'X-Webhook-Signature', 'X-Signature'.
        """
        check_secret = secret or self.webhook_secret
        if not check_secret:
            # If no secret is configured, accept the payload in mock mode
            return True

        provided_sig = (
            headers.get("x-mock-signature")
            or headers.get("X-Mock-Signature")
            or headers.get("x-webhook-signature")
            or headers.get("X-Webhook-Signature")
            or headers.get("x-signature")
            or headers.get("X-Signature")
        )
        if not provided_sig:
            logger.warning("Mock webhook verification failed: No signature header present")
            return False

        computed = hmac.new(check_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed.lower(), provided_sig.lower())

    def accept_call(
        self,
        event: InboundCallEvent,
        greeting_text: Optional[str] = None,
    ) -> CallControlResult:
        return CallControlResult(
            session_id=None,
            action="accept",
            message=greeting_text,
            status="accepted",
            metadata={"provider_call_id": event.provider_call_id},
        )

    def reject_call(
        self,
        event: InboundCallEvent,
        reason: str = "busy",
    ) -> CallControlResult:
        return CallControlResult(
            session_id=None,
            action="reject",
            message=reason,
            status="rejected",
            metadata={"provider_call_id": event.provider_call_id},
        )

    def hangup_call(
        self,
        session_id: str,
        reason: str = "completed",
    ) -> CallControlResult:
        return CallControlResult(
            session_id=session_id,
            action="hangup",
            message=reason,
            status="completed",
        )


class MockSTTStream:
    """Mock streaming session for STT simulations in testing and sandbox mode."""

    def __init__(self, session_id: str = "mock_stream", allow_simulation: bool = True) -> None:
        self.session_id = session_id
        self.allow_simulation = allow_simulation
        self._queue: asyncio.Queue = asyncio.Queue()
        self._is_closed = False

    async def connect(self) -> None:
        pass

    async def send_audio(self, audio_chunk: bytes) -> None:
        if self._is_closed:
            return

        try:
            decoded = audio_chunk.decode("utf-8").strip()
            if decoded and all(c.isprintable() or c.isspace() for c in decoded):
                await self._queue.put(TranscriptEvent(
                    session_id=self.session_id,
                    text=decoded,
                    is_final=True,
                    confidence=0.98,
                    speaker="customer",
                    timestamp=utcnow(),
                ))
                return
        except Exception:
            pass

        if self.allow_simulation:
            await self._queue.put(TranscriptEvent(
                session_id=self.session_id,
                text="Hello, I have a question about your business.",
                is_final=True,
                confidence=0.95,
                speaker="customer",
                timestamp=utcnow(),
            ))

    async def receive_event(self, timeout: Optional[float] = None) -> Optional[TranscriptEvent]:
        if self._is_closed and self._queue.empty():
            return None
        try:
            if timeout is not None:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return await self._queue.get()
        except asyncio.TimeoutError:
            return None

    async def close(self) -> None:
        self._is_closed = True


class MockSTTProvider:
    """Mock Speech-to-Text provider converting buffers or strings to transcripts."""

    def __init__(self, allow_simulation: bool = True) -> None:
        self.allow_simulation = allow_simulation

    @property
    def provider_name(self) -> str:
        return "mock_stt"

    def create_stream(
        self,
        session_id: str,
        sample_rate: Optional[int] = None,
        language: Optional[str] = None,
        ws_client: Any = None,
    ) -> MockSTTStream:
        return MockSTTStream(session_id=session_id, allow_simulation=self.allow_simulation)

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en",
    ) -> TranscriptEvent:
        """Converts raw audio bytes or text simulation to TranscriptEvent."""
        try:
            # Check if printable simulation text payload was passed
            decoded = audio_bytes.decode("utf-8").strip()
            if decoded and all(c.isprintable() or c.isspace() for c in decoded):
                return TranscriptEvent(
                    session_id="simulated",
                    text=decoded,
                    is_final=True,
                    confidence=0.98,
                    language=language,
                    speaker="customer",
                )
        except Exception:
            pass

        if self.allow_simulation:
            return TranscriptEvent(
                session_id="simulated",
                text="Hello, I have a question about your business.",
                is_final=True,
                confidence=0.95,
                language=language,
                speaker="customer",
            )

        raise RuntimeError("Production Speech-To-Text provider is not configured.")


class MockTTSProvider:
    """Mock Text-to-Speech provider producing deterministic audio byte frames."""

    @property
    def provider_name(self) -> str:
        return "mock_tts"

    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        language: str = "en",
    ) -> bytes:
        """Produces a deterministic mock audio payload."""
        raw = f"[MOCK_WAV:{text[:50]}]".encode("utf-8")
        return pad_pcm16_to_multiple(raw, 320)

    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        sample_rate: Optional[int] = None,
        cancellation_token: Optional[asyncio.Event] = None,
        ws_client: Any = None,
    ):
        """Yields mock audio chunk stream."""
        if not text or not text.strip():
            return
        if cancellation_token and cancellation_token.is_set():
            return
        chunk = self.synthesize(text, voice_id=voice_id)
        yield chunk
