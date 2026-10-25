"""
Sanitized Call Diagnostics and Telemetry Engine.
Tracks real-time telephony timestamps, latencies, and statuses without
exposing secrets, authorization headers, raw audio, or full transcripts.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
from pydantic import BaseModel, Field

from backend.database.models import utcnow

logger = logging.getLogger("backend.voice.diagnostics")


def mask_identifier(val: Optional[str], prefix_len: int = 4, suffix_len: int = 4) -> str:
    """
    Safely mask provider call or stream identifier (e.g. 'CA1234567890abcdef' -> 'CA12...cdef').
    """
    if not val:
        return "[UNKNOWN]"
    val_str = str(val).strip()
    if len(val_str) <= prefix_len + suffix_len:
        return "****"
    return f"{val_str[:prefix_len]}...{val_str[-suffix_len:]}"


class CallDiagnostics(BaseModel):
    """
    Structured in-memory telemetry model for an active telephony session.
    Records critical conversational lifecycle checkpoints with microsecond precision.
    """
    ws_connected_at: Optional[datetime] = None
    ws_authenticated: bool = False
    call_sid_masked: str = "[UNKNOWN]"
    stream_sid_masked: str = "[UNKNOWN]"
    tenant_routing_status: str = "pending"
    business_id: Optional[str] = None
    first_audio_received_at: Optional[datetime] = None
    total_audio_frames: int = 0
    total_audio_bytes: int = 0
    first_final_transcript_at: Optional[datetime] = None
    turn_count: int = 0
    last_speech_confidence: Optional[float] = None
    last_speech_char_count: int = 0
    llm_started_at: Optional[datetime] = None
    llm_completed_at: Optional[datetime] = None
    llm_duration_ms: Optional[float] = None
    tts_first_chunk_sent_at: Optional[datetime] = None
    tts_duration_ms: Optional[float] = None
    barge_in_count: int = 0
    session_terminated_at: Optional[datetime] = None
    session_persisted: bool = False
    termination_reason: Optional[str] = None

    def record_ws_connected(self) -> None:
        self.ws_connected_at = utcnow()
        logger.info("[CALL_DIAGNOSTICS] WebSocket client connected at %s", self.ws_connected_at.isoformat())

    def record_ws_authenticated(self, success: bool) -> None:
        self.ws_authenticated = success
        level = logging.INFO if success else logging.WARNING
        logger.log(level, "[CALL_DIAGNOSTICS] Handshake authentication status: %s", "ACCEPTED" if success else "REJECTED")

    def record_start(self, call_sid: str, stream_sid: str) -> None:
        self.call_sid_masked = mask_identifier(call_sid, prefix_len=4, suffix_len=4)
        self.stream_sid_masked = mask_identifier(stream_sid, prefix_len=4, suffix_len=4)
        logger.info(
            "[CALL_DIAGNOSTICS] Stream started: call_sid=%s stream_sid=%s",
            self.call_sid_masked,
            self.stream_sid_masked,
        )

    def record_routing(self, success: bool, business_id: Optional[str] = None, error_code: Optional[str] = None) -> None:
        self.tenant_routing_status = "success" if success else f"failed({error_code or 'error'})"
        self.business_id = business_id
        if success:
            logger.info(
                "[CALL_DIAGNOSTICS] Call %s: Tenant routing SUCCEEDED for business '%s'",
                self.call_sid_masked,
                business_id,
            )
        else:
            logger.warning(
                "[CALL_DIAGNOSTICS] Call %s: Tenant routing FAILED (code: %s)",
                self.call_sid_masked,
                error_code or "unknown",
            )

    def record_audio_frame(self, frame_bytes_len: int) -> None:
        if self.first_audio_received_at is None:
            self.first_audio_received_at = utcnow()
            logger.info(
                "[CALL_DIAGNOSTICS] Call %s: First inbound audio received (%d bytes) at %s",
                self.call_sid_masked,
                frame_bytes_len,
                self.first_audio_received_at.isoformat(),
            )
        self.total_audio_frames += 1
        self.total_audio_bytes += frame_bytes_len

    def record_final_transcript(self, confidence: float, char_count: int) -> None:
        now = utcnow()
        if self.first_final_transcript_at is None:
            self.first_final_transcript_at = now
        self.turn_count += 1
        self.last_speech_confidence = confidence
        self.last_speech_char_count = char_count
        logger.info(
            "[CALL_DIAGNOSTICS] Call %s turn %d: Final speech recognized (chars: %d, confidence: %.2f)",
            self.call_sid_masked,
            self.turn_count,
            char_count,
            confidence,
        )

    def record_llm_turn(self, duration_ms: float, tools_called: List[str]) -> None:
        self.llm_duration_ms = duration_ms
        self.llm_completed_at = utcnow()
        logger.info(
            "[CALL_DIAGNOSTICS] Call %s turn %d: LLM request completed in %.1fms (tools executed: %s)",
            self.call_sid_masked,
            self.turn_count,
            duration_ms,
            tools_called if tools_called else "none",
        )

    def record_tts_first_chunk(self, duration_ms: float, total_bytes: int) -> None:
        self.tts_first_chunk_sent_at = utcnow()
        self.tts_duration_ms = duration_ms
        logger.info(
            "[CALL_DIAGNOSTICS] Call %s turn %d: TTS first chunk generated in %.1fms (%d total bytes)",
            self.call_sid_masked,
            self.turn_count,
            duration_ms,
            total_bytes,
        )

    def record_barge_in(self) -> None:
        self.barge_in_count += 1
        logger.info(
            "[CALL_DIAGNOSTICS] Call %s: Barge-in #%d detected! Outbound telecom buffer cleared.",
            self.call_sid_masked,
            self.barge_in_count,
        )

    def record_termination(self, persisted: bool, reason: str = "completed") -> None:
        self.session_terminated_at = utcnow()
        self.session_persisted = persisted
        self.termination_reason = reason
        level = logging.INFO if persisted else logging.ERROR
        logger.log(
            level,
            "[CALL_DIAGNOSTICS] Call %s: Terminated with reason '%s' (persisted: %s)",
            self.call_sid_masked,
            reason,
            "YES" if persisted else "NO",
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return sanitized dictionary suitable for monitoring or API responses."""
        return {
            "ws_connected_at": self.ws_connected_at.isoformat() if self.ws_connected_at else None,
            "ws_authenticated": self.ws_authenticated,
            "call_sid_masked": self.call_sid_masked,
            "stream_sid_masked": self.stream_sid_masked,
            "tenant_routing_status": self.tenant_routing_status,
            "business_id": self.business_id,
            "first_audio_received_at": self.first_audio_received_at.isoformat() if self.first_audio_received_at else None,
            "total_audio_frames": self.total_audio_frames,
            "total_audio_bytes": self.total_audio_bytes,
            "first_final_transcript_at": self.first_final_transcript_at.isoformat() if self.first_final_transcript_at else None,
            "turn_count": self.turn_count,
            "last_speech_confidence": self.last_speech_confidence,
            "last_speech_char_count": self.last_speech_char_count,
            "llm_duration_ms": self.llm_duration_ms,
            "tts_first_chunk_sent_at": self.tts_first_chunk_sent_at.isoformat() if self.tts_first_chunk_sent_at else None,
            "tts_duration_ms": self.tts_duration_ms,
            "barge_in_count": self.barge_in_count,
            "session_terminated_at": self.session_terminated_at.isoformat() if self.session_terminated_at else None,
            "session_persisted": self.session_persisted,
            "termination_reason": self.termination_reason,
        }
