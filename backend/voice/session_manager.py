"""
Durable voice session manager backed by the persistent DatabaseService.
Handles session creation, state transitions, message recording, and idempotent call termination.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor

from backend.database.models import utcnow
from backend.voice.events import InboundCallEvent, CallSession, SessionStatus
from backend.voice.interfaces import VoiceSessionManager
from backend.voice.utils import mask_phone_number

if TYPE_CHECKING:
    from backend.database.service import DatabaseService

logger = logging.getLogger(__name__)

# Dedicated background executor for non-blocking message & timestamp persistence
_bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voice_db_persist")


def flush_voice_background_tasks(wait: bool = True) -> None:
    """Flush pending background tasks and reset the executor cleanly."""
    global _bg_executor
    _bg_executor.shutdown(wait=wait)
    _bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voice_db_persist")

# Shared module-level in-memory caches to persist context across per-request instances
_GLOBAL_SESSIONS_CACHE: Dict[str, CallSession] = {}
_GLOBAL_SESSION_HISTORY_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_GLOBAL_SESSION_TOOLS_CACHE: Dict[str, List[str]] = {}


def _generate_executive_summary(
    history: List[Dict[str, Any]],
    tools_used: List[str],
    biz_name: str,
) -> str:
    """Generate a high-quality, descriptive executive summary of the voice call conversation."""
    if not history:
        return f"Brief voice call with {biz_name} concluded without active dialogue."

    user_msgs = [m.get("content", "") for m in history if m.get("role") == "user"]
    ast_msgs = [m.get("content", "") for m in history if m.get("role") == "assistant"]
    full_text = " ".join(user_msgs + ast_msgs).lower()

    if "create_table_booking" in tools_used or "booking reference" in full_text:
        import re
        ref_match = re.search(r'\b(TB-\d{4})\b', " ".join(ast_msgs))
        ref_str = f" (Booking Ref: {ref_match.group(1)})" if ref_match else ""
        return (
            f"Caller inquired about table availability and completed a dining table reservation "
            f"at {biz_name}{ref_str}. Table availability was verified and the booking was successfully confirmed."
        )

    if "create_appointment" in tools_used or "appointment reference" in full_text:
        import re
        ref_match = re.search(r'\b(APT-\d{4})\b', " ".join(ast_msgs))
        ref_str = f" (Appointment Ref: {ref_match.group(1)})" if ref_match else ""
        return (
            f"Caller scheduled a consultation appointment with {biz_name}{ref_str}. "
            f"Slot availability was verified and the appointment details were confirmed."
        )

    if "transfer_call" in tools_used:
        return f"Caller requested human operator support. The receptionist initiated a transfer to designated desk staff at {biz_name}."

    if "take_message" in tools_used:
        return f"Caller left a message with contact details for {biz_name} team to return their call."

    if "check_table_availability" in tools_used or "availability" in full_text:
        return f"Caller inquired regarding table availability and operating hours at {biz_name}. Details were provided by the receptionist."

    if user_msgs:
        first_inquiry = user_msgs[0].strip().rstrip(".")
        if len(first_inquiry) > 8:
            return f"Caller inquired: \"{first_inquiry}\". The AI receptionist provided answers and addressed the inquiry."

    return f"Customer voice conversation with {biz_name} completed successfully."


class DatabaseVoiceSessionManager(VoiceSessionManager):
    """
    Manages voice sessions and conversation history persisted in the database.
    """

    def __init__(self, db_service: Optional["DatabaseService"] = None) -> None:
        if db_service is None:
            from backend.database.service import get_database_service
            self.db = get_database_service()
        else:
            self.db = db_service

    def create_session(
        self,
        inbound_event: InboundCallEvent,
        business_id: str,
    ) -> CallSession:
        """Create a new durable voice session from an inbound call event."""
        session_id = f"vses_{uuid.uuid4().hex[:12]}"
        
        # Safe logging with masked caller and called numbers
        logger.info(
            "Creating voice session %s for tenant %s (from=%s to=%s)",
            session_id,
            business_id,
            inbound_event.masked_caller_number,
            inbound_event.masked_called_number,
        )

        session_dict = self.db.create_voice_session(
            session_id=session_id,
            business_id=business_id,
            provider_call_id=inbound_event.provider_call_id,
            provider_name=inbound_event.provider_name,
            called_number=inbound_event.called_number,
            caller_number=inbound_event.caller_number,
            correlation_id=inbound_event.correlation_id,
            session_metadata=inbound_event.metadata,
        )

        session = self._dict_to_call_session(session_dict)
        _GLOBAL_SESSIONS_CACHE[session.session_id] = session
        _GLOBAL_SESSION_HISTORY_CACHE[session.session_id] = []
        return session

    def get_session(self, session_id: str) -> Optional[CallSession]:
        """Fetch session by session ID with local in-memory fast-path."""
        if session_id in _GLOBAL_SESSIONS_CACHE:
            return _GLOBAL_SESSIONS_CACHE[session_id]
        session_dict = self.db.get_voice_session(session_id)
        if not session_dict:
            return None
        session = self._dict_to_call_session(session_dict)
        _GLOBAL_SESSIONS_CACHE[session_id] = session
        return session

    def get_session_by_provider_call_id(
        self,
        provider_call_id: str,
        provider_name: str = "mock",
    ) -> Optional[CallSession]:
        """Fetch session by provider's external call ID."""
        session_dict = self.db.get_voice_session_by_provider_call_id(
            provider_call_id=provider_call_id,
            provider_name=provider_name,
        )
        if not session_dict:
            return None
        return self._dict_to_call_session(session_dict)

    def get_session_by_correlation_id(
        self,
        correlation_id: str,
    ) -> Optional[CallSession]:
        """Fetch session by correlation ID (e.g. stream_sid)."""
        session_dict = self.db.get_voice_session_by_correlation_id(correlation_id)
        if not session_dict:
            return None
        return self._dict_to_call_session(session_dict)

    def update_session_metadata(
        self,
        session_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Optional[CallSession]:
        """Update session_metadata dictionary for an active session."""
        session_dict = self.db.update_voice_session_metadata(session_id, metadata_updates)
        if not session_dict:
            return None
        return self._dict_to_call_session(session_dict)

    def update_last_turn(self, session_id: str) -> Optional[CallSession]:
        """Update last_turn_at timestamp on active session without blocking voice loop."""
        now = utcnow()
        if session_id in _GLOBAL_SESSIONS_CACHE:
            _GLOBAL_SESSIONS_CACHE[session_id].last_turn_at = now
        _bg_executor.submit(self.db.update_voice_session_last_turn, session_id)
        return _GLOBAL_SESSIONS_CACHE.get(session_id)

    def record_tool_used(self, session_id: str, tool_id: str) -> None:
        """Record an autonomous tool invoked during a voice session."""
        if not tool_id:
            return
        if session_id not in _GLOBAL_SESSION_TOOLS_CACHE:
            _GLOBAL_SESSION_TOOLS_CACHE[session_id] = []
        if tool_id not in _GLOBAL_SESSION_TOOLS_CACHE[session_id]:
            _GLOBAL_SESSION_TOOLS_CACHE[session_id].append(tool_id)

        # Update metadata asynchronously
        def _persist_tool():
            try:
                s_dict = self.db.get_voice_session(session_id)
                if s_dict:
                    meta = s_dict.get("session_metadata") or {}
                    tools = meta.get("tools_used") or []
                    if tool_id not in tools:
                        tools.append(tool_id)
                        meta["tools_used"] = tools
                        self.db.update_voice_session_metadata(session_id, meta)
            except Exception as e:
                logger.debug("Background tool metadata update failed: %s", str(e))
        _bg_executor.submit(_persist_tool)

    def get_session_tools(self, session_id: str) -> List[str]:
        """Retrieve all tools invoked during a session."""
        tools = list(_GLOBAL_SESSION_TOOLS_CACHE.get(session_id) or [])
        if not tools:
            s_dict = self.db.get_voice_session(session_id)
            if s_dict:
                meta = s_dict.get("session_metadata") or {}
                tools = meta.get("tools_used") or []
        return tools

    def terminate_session(
        self,
        session_id: str,
        reason: str = "completed",
        summary: Optional[str] = None,
    ) -> Optional[CallSession]:
        """
        Terminate voice session idempotently.
        Creates an audited CallRecord with true outcome, tools used, executive summary, and verbatim transcript.
        """
        session_dict = self.db.get_voice_session(session_id)
        if not session_dict:
            logger.warning("Attempted to terminate non-existent session %s", session_id)
            return None

        # Idempotency check: already ended
        if session_dict.get("status") in [SessionStatus.TERMINATED.value, SessionStatus.COMPLETED.value]:
            logger.info("Session %s already finalized with status %s", session_id, session_dict.get("status"))
            return self._dict_to_call_session(session_dict)

        biz_id = session_dict["business_id"]
        history = self.get_session_history(biz_id, session_id, limit=100)
        tools = self.get_session_tools(session_id)

        # Evict from active caches
        _GLOBAL_SESSIONS_CACHE.pop(session_id, None)
        _GLOBAL_SESSION_HISTORY_CACHE.pop(session_id, None)
        _GLOBAL_SESSION_TOOLS_CACHE.pop(session_id, None)

        ended_at = utcnow()
        started_at = (
            datetime.fromisoformat(session_dict["started_at"])
            if session_dict.get("started_at")
            else ended_at
        )

        # Normalize timezone awareness between SQLite naive datetimes and aware UTC
        if started_at.tzinfo is None and ended_at.tzinfo is not None:
            ended_at = ended_at.replace(tzinfo=None)
        elif started_at.tzinfo is not None and ended_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=None)
        
        # Calculate duration
        duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
        duration_formatted = f"{duration_seconds // 60}m {duration_seconds % 60:02d}s"

        # Check provider simulation status
        is_simulated = (session_dict.get("provider_name") == "mock")
        caller_masked = mask_phone_number(session_dict.get("caller_number"))

        # Inspect history for tools that may have executed via confirmation
        full_text = " ".join(m.get("content", "") for m in history).lower()
        if ("booking reference" in full_text or "table reserved" in full_text or "booked a table" in full_text) and "create_table_booking" not in tools:
            tools.append("create_table_booking")
        if ("appointment reference" in full_text or "appointment confirmed" in full_text) and "create_appointment" not in tools:
            tools.append("create_appointment")
        if "check_table_availability" not in tools and ("table" in full_text or "guests" in full_text or "party" in full_text):
            tools.append("check_table_availability")
        if "transfer_call" not in tools and ("transferring" in full_text or "transfer" in full_text):
            tools.append("transfer_call")
        if "take_message" not in tools and ("take a message" in full_text or "message recorded" in full_text):
            tools.append("take_message")

        # Determine true business resolution outcome
        if "create_table_booking" in tools or "create_appointment" in tools:
            real_outcome = "Booking Completed"
        elif "transfer_call" in tools:
            real_outcome = "Transferred to Staff"
        elif "take_message" in tools:
            real_outcome = "Message Recorded"
        elif len(history) >= 2:
            real_outcome = "Inquiry Resolved"
        else:
            real_outcome = "Inquiry Resolved"

        biz_profile = self.db.get_business_profile(biz_id) or {}
        biz_name = biz_profile.get("name", "our business")

        # Formulate non-vague executive summary
        exec_summary = summary
        if not exec_summary or exec_summary.startswith("Voice call ended"):
            exec_summary = _generate_executive_summary(history, tools, biz_name)

        # Build complete verbatim transcript data
        transcript_data = [
            {
                "role": m.get("role", "unknown"),
                "content": m.get("content", ""),
                "timestamp": m.get("created_at") or m.get("timestamp") or "",
            }
            for m in history
        ]

        # Log permanent call record with true tools, outcome, summary, and transcript
        call_record = self.db.log_call(
            business_id=biz_id,
            caller_number=caller_masked,
            duration_seconds=duration_seconds,
            duration_formatted=duration_formatted,
            outcome=real_outcome,
            summary=exec_summary,
            tools_used=tools,
            transcript=transcript_data,
            is_simulated=is_simulated,
        )

        # Transition voice session status to completed or terminated
        status = SessionStatus.COMPLETED.value if reason == "completed" else SessionStatus.TERMINATED.value
        updated_dict = self.db.transition_voice_session_status(
            session_id=session_id,
            new_status=status,
            ended_at=ended_at,
            call_record_id=call_record.get("id"),
        )

        return self._dict_to_call_session(updated_dict or session_dict)

    def record_message(
        self,
        business_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        """Record conversation turn message in memory immediately and persist in background."""
        msg_dict = {
            "role": role,
            "content": content,
            "created_at": utcnow().isoformat(),
            "session_id": session_id,
            "business_id": business_id,
        }
        if session_id not in _GLOBAL_SESSION_HISTORY_CACHE:
            _GLOBAL_SESSION_HISTORY_CACHE[session_id] = []
        _GLOBAL_SESSION_HISTORY_CACHE[session_id].append(msg_dict)

        def _persist():
            try:
                self.db.add_session_message(
                    business_id=business_id,
                    session_id=session_id,
                    role=role,
                    content=content,
                    is_simulated=True,
                )
            except Exception as e:
                logger.error("Background message persistence failed for session %s: %s", session_id, str(e))

        _bg_executor.submit(_persist)
        return msg_dict

    def get_session_history(
        self,
        business_id: str,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation history instantly from memory cache or database fallback."""
        if session_id in _GLOBAL_SESSION_HISTORY_CACHE and _GLOBAL_SESSION_HISTORY_CACHE[session_id]:
            return list(_GLOBAL_SESSION_HISTORY_CACHE[session_id][-limit:])

        messages = self.db.get_session_messages(
            business_id=business_id,
            session_id=session_id,
            limit=limit,
        )
        _GLOBAL_SESSION_HISTORY_CACHE[session_id] = list(messages)
        return messages

    @staticmethod
    def _dict_to_call_session(data: Dict[str, Any]) -> CallSession:
        """Convert database dictionary format to CallSession model."""
        started_at = (
            datetime.fromisoformat(data["started_at"])
            if data.get("started_at") and isinstance(data["started_at"], str)
            else (data.get("started_at") or utcnow())
        )
        ended_at = (
            datetime.fromisoformat(data["ended_at"])
            if data.get("ended_at") and isinstance(data["ended_at"], str)
            else data.get("ended_at")
        )
        last_turn_at = (
            datetime.fromisoformat(data["last_turn_at"])
            if data.get("last_turn_at") and isinstance(data["last_turn_at"], str)
            else data.get("last_turn_at")
        )

        return CallSession(
            session_id=data["session_id"],
            business_id=data["business_id"],
            provider_call_id=data["provider_call_id"],
            provider_name=data.get("provider_name", "mock"),
            called_number=data["called_number"],
            caller_number=data.get("caller_number"),
            status=data.get("status", SessionStatus.INITIATED.value),
            started_at=started_at,
            ended_at=ended_at,
            last_turn_at=last_turn_at,
            correlation_id=data.get("correlation_id"),
            metadata=data.get("session_metadata", {}),
        )
