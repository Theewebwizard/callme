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

# Shared module-level in-memory caches to persist context across per-request instances
_GLOBAL_SESSIONS_CACHE: Dict[str, CallSession] = {}
_GLOBAL_SESSION_HISTORY_CACHE: Dict[str, List[Dict[str, Any]]] = {}


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

    def terminate_session(
        self,
        session_id: str,
        reason: str = "completed",
        summary: Optional[str] = None,
    ) -> Optional[CallSession]:
        """
        Terminate voice session idempotently.
        Creates an audit CallRecord on first termination and transitions status.
        Repeated calls return the already-terminated session without error.
        """
        # Evict from active cache on termination
        _GLOBAL_SESSIONS_CACHE.pop(session_id, None)
        _GLOBAL_SESSION_HISTORY_CACHE.pop(session_id, None)

        session_dict = self.db.get_voice_session(session_id)
        if not session_dict:
            logger.warning("Attempted to terminate non-existent session %s", session_id)
            return None

        # Idempotency check: already ended
        if session_dict.get("status") in [SessionStatus.TERMINATED.value, SessionStatus.COMPLETED.value]:
            logger.info("Session %s already finalized with status %s", session_id, session_dict.get("status"))
            return self._dict_to_call_session(session_dict)

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

        # Log permanent call record
        call_record = self.db.log_call(
            business_id=session_dict["business_id"],
            caller_number=caller_masked,
            duration_seconds=duration_seconds,
            duration_formatted=duration_formatted,
            outcome=f"Voice Call: {reason}",
            summary=summary or f"Voice call ended with reason: {reason}",
            tools_used=[],
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
