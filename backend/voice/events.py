"""
Voice and telephony typed events and data models.
Provides Pydantic schemas for inbound calls, sessions, transcripts, turn results, and termination.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, Field

from backend.database.models import utcnow
from backend.voice.utils import normalize_phone_number, mask_phone_number


class CallStatus(str, Enum):
    """Standardized telephony call status."""
    INITIATED = "initiated"
    RINGING = "ringing"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BUSY = "busy"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    CANCELED = "canceled"


class SessionStatus(str, Enum):
    """Voice session lifecycle states."""
    INITIATED = "initiated"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    FAILED = "failed"


class ProviderCapabilities(BaseModel):
    """Capabilities and features supported by a telephony or voice provider."""
    name: str
    supports_streaming_stt: bool = False
    supports_streaming_tts: bool = False
    supports_barge_in: bool = False
    supports_dtmf: bool = False
    supports_call_recording: bool = False
    supported_audio_codecs: List[str] = Field(default_factory=lambda: ["mulaw", "pcm", "mp3"])


class InboundCallEvent(BaseModel):
    """
    Typed event representing an incoming telephony call webhook or event.
    """
    provider_call_id: str = Field(..., description="Unique call ID assigned by telephony provider")
    provider_name: str = Field("mock", description="Name of provider (e.g., mock, twilio)")
    called_number: str = Field(..., description="Phone number dialled by the caller (E.164 or formatted)")
    caller_number: Optional[str] = Field(None, description="Caller's phone number if available")
    call_status: str = Field(CallStatus.INITIATED.value, description="Initial call state")
    timestamp: datetime = Field(default_factory=utcnow, description="Call initiation timestamp")
    correlation_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), description="Trace correlation ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific headers/payload")

    @property
    def normalized_called_number(self) -> str:
        """Normalized E.164 format of the called number."""
        return normalize_phone_number(self.called_number)

    @property
    def normalized_caller_number(self) -> Optional[str]:
        """Normalized E.164 format of caller number if available."""
        return normalize_phone_number(self.caller_number) if self.caller_number else None

    @property
    def masked_caller_number(self) -> str:
        """Privacy-masked caller number for logs and reports."""
        return mask_phone_number(self.caller_number)

    @property
    def masked_called_number(self) -> str:
        """Privacy-masked called number."""
        return mask_phone_number(self.called_number)

    def __repr__(self) -> str:
        return (
            f"<InboundCallEvent call_id={self.provider_call_id} "
            f"provider={self.provider_name} "
            f"called={self.masked_called_number} "
            f"caller={self.masked_caller_number}>"
        )


class CallSession(BaseModel):
    """
    Active voice session representing an ongoing phone conversation with a business tenant.
    """
    session_id: str = Field(..., description="Internal unique voice session ID")
    business_id: str = Field(..., description="Resolved tenant business ID")
    provider_call_id: str = Field(..., description="Provider's external call ID")
    provider_name: str = Field("mock", description="Telephony provider name")
    called_number: str = Field(..., description="Dialled business number")
    caller_number: Optional[str] = Field(None, description="Caller phone number")
    status: str = Field(SessionStatus.INITIATED.value, description="Lifecycle status")
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: Optional[datetime] = None
    last_turn_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def masked_caller_number(self) -> str:
        """Privacy-masked caller number."""
        return mask_phone_number(self.caller_number)

    @property
    def masked_called_number(self) -> str:
        """Privacy-masked called number."""
        return mask_phone_number(self.called_number)


class TranscriptEvent(BaseModel):
    """
    Speech-to-text transcript turn event from caller or speech recognizer.
    """
    session_id: str = Field(..., description="Voice session ID")
    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Turn correlation ID")
    text: str = Field(..., description="Recognized utterance text")
    is_final: bool = Field(True, description="Whether transcription is finalized")
    speech_final: bool = Field(True, description="Whether speaker turn is completed by endpointing")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    language: str = Field("en", description="Detected language code")
    speaker: str = Field("customer", description="Speaker role: customer or assistant")
    timestamp: datetime = Field(default_factory=utcnow)


class VoiceTurnResult(BaseModel):
    """
    Result of processing a voice turn through the LangGraph receptionist workflow.
    """
    session_id: str = Field(..., description="Voice session ID")
    turn_id: str = Field(..., description="Turn ID matching the transcript turn")
    user_text: str = Field(..., description="Customer utterance")
    assistant_text: str = Field(..., description="Receptionist reply text")
    audio_payload: Optional[bytes] = Field(None, description="Synthesized voice audio bytes if available")
    audio_url: Optional[str] = Field(None, description="URL or reference to synthesized voice audio")
    tool_calls_executed: List[str] = Field(default_factory=list, description="IDs of tools executed")
    pending_action: Optional[Dict[str, Any]] = Field(None, description="Pending confirmation action if any")
    llm_duration_ms: Optional[float] = Field(None, description="Execution latency of LangGraph LLM generation in milliseconds")
    session_status: str = Field(SessionStatus.ACTIVE.value, description="Current session state")
    should_terminate: bool = Field(False, description="Flag indicating if call should terminate")
    timestamp: datetime = Field(default_factory=utcnow)


class CallTerminationEvent(BaseModel):
    """
    Event generated upon call hangup or termination.
    """
    session_id: str = Field(..., description="Voice session ID")
    reason: str = Field("completed", description="Reason: completed, caller_hangup, system_hangup, error, transferred")
    duration_seconds: int = Field(0, ge=0, description="Total call duration in seconds")
    ended_at: datetime = Field(default_factory=utcnow)
    summary: Optional[str] = Field(None, description="Call summary or outcome")
    tools_used: List[str] = Field(default_factory=list, description="List of tools used during call")


class CallControlResult(BaseModel):
    """
    Telephony action response returned to provider or caller.
    """
    session_id: Optional[str] = Field(None, description="Voice session ID if active")
    action: str = Field(..., description="Action: accept, reject, hangup, speak, transfer")
    message: Optional[str] = Field(None, description="Greeting or speech text to play")
    status: str = Field("success", description="Status of control operation")
    metadata: Dict[str, Any] = Field(default_factory=dict)
