"""
Voice Turn Orchestrator.
Coordinates user transcript turns through the shared LangGraph receptionist workflow and modular tool registry.
Enforces session concurrency serialization, session history isolation, and error boundaries.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
import threading
import logging
import uuid

from backend.agent.graph import invoke_receptionist_workflow
from backend.database.models import utcnow
from backend.services.groq_service import GroqService, get_groq_service
from backend.tools.registry import ToolRegistry, get_tool_registry
from backend.voice.events import TranscriptEvent, VoiceTurnResult, SessionStatus
from backend.voice.interfaces import VoiceSessionManager, TextToSpeechProvider
from backend.voice.session_manager import DatabaseVoiceSessionManager
from backend.voice.providers import get_tts_provider

if TYPE_CHECKING:
    from backend.database.service import DatabaseService

logger = logging.getLogger(__name__)


class VoiceTurnOrchestrator:
    """
    Orchestrates turn processing for active voice sessions.
    Serializes concurrent turns per session, invokes LangGraph, and records history.
    """

    def __init__(
        self,
        db_service: Optional["DatabaseService"] = None,
        session_manager: Optional[VoiceSessionManager] = None,
        groq_service: Optional[GroqService] = None,
        tool_registry: Optional[ToolRegistry] = None,
        tts_provider: Optional[TextToSpeechProvider] = None,
    ) -> None:
        if db_service is None:
            from backend.database.service import get_database_service
            self.db = get_database_service()
        else:
            self.db = db_service
        self.session_manager = session_manager or DatabaseVoiceSessionManager(self.db)
        self.groq_service = groq_service or get_groq_service()
        self.tool_registry = tool_registry or get_tool_registry()
        from backend.config import get_settings
        settings = get_settings()
        if settings.ENVIRONMENT == "production":
            self.tts_provider = tts_provider or (get_tts_provider("deepgram") if settings.is_deepgram_configured else None)
        else:
            self.tts_provider = tts_provider or get_tts_provider("default")

        # Session lock registry for turn serialization
        self._session_locks: Dict[str, threading.Lock] = {}
        self._locks_mutex = threading.Lock()

    def _get_session_lock(self, session_id: str) -> threading.Lock:
        """Retrieve or create an in-process serialization lock for a specific session."""
        with self._locks_mutex:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]

    def release_session_lock(self, session_id: str) -> None:
        """Clean up session lock when a call is terminated."""
        with self._locks_mutex:
            self._session_locks.pop(session_id, None)

    def process_turn(
        self,
        session_id: str,
        transcript: TranscriptEvent,
        synthesize_audio: bool = True,
    ) -> VoiceTurnResult:
        """
        Process an inbound transcript turn for an active voice session.
        Concurrent turns for the same session are serialized through a session lock.
        """
        session_lock = self._get_session_lock(session_id)

        with session_lock:
            # 1. Fetch and validate active voice session
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ValueError(f"Voice session '{session_id}' not found.")

            if session.status in [SessionStatus.TERMINATED.value, SessionStatus.COMPLETED.value]:
                raise ValueError(f"Voice session '{session_id}' has already ended (status: {session.status}).")

            # 2. Update turn activity timestamp
            self.session_manager.update_last_turn(session_id)

            user_text = transcript.text.strip()
            if not user_text:
                user_text = "..."

            # 3. Persist caller transcript turn in session-scoped message history
            self.session_manager.record_message(
                business_id=session.business_id,
                session_id=session_id,
                role="user",
                content=user_text,
            )

            # 4. Fetch full business profile (including FAQs and tool toggles)
            biz_profile = self.db.get_business_profile(session.business_id)
            if not biz_profile:
                raise ValueError(f"Business profile for tenant '{session.business_id}' not found.")

            # 5. Load isolated conversation history scoped specifically to this session
            history = self.session_manager.get_session_history(
                business_id=session.business_id,
                session_id=session_id,
                limit=50,
            )

            # 6. Execute shared LangGraph receptionist workflow with error boundary
            response_content: str = ""
            pending_action: Optional[Dict[str, Any]] = None
            tools_called: List[str] = []
            filler_phrase: Optional[str] = None
            should_terminate = False
            llm_duration_ms: Optional[float] = None

            try:
                import time
                t_start = time.perf_counter()
                workflow_result = invoke_receptionist_workflow(
                    business_id=session.business_id,
                    business_config=biz_profile,
                    enabled_tools=biz_profile.get("enabled_tools", {}),
                    messages=history,
                    groq_service=self.groq_service,
                    tool_registry=self.tool_registry,
                    session_id=session_id,
                )
                llm_duration_ms = (time.perf_counter() - t_start) * 1000

                if not workflow_result.get("success", False) or workflow_result.get("error"):
                    response_content = (
                        "I apologize, I am experiencing technical difficulties at the moment. "
                        "Please hold on or call back shortly."
                    )
                else:
                    response_content = workflow_result.get("response_content") or ""
                pending_action = workflow_result.get("pending_action")
                tools_called = workflow_result.get("tools_called") or []
                filler_phrase = workflow_result.get("filler_phrase")
                should_terminate = bool(workflow_result.get("should_terminate", False))

            except Exception as e:
                logger.error(
                    "Error executing LangGraph workflow for session %s: %s",
                    session_id,
                    str(e),
                    exc_info=True,
                )
                # Fail gracefully without hallucinating false success
                response_content = (
                    "I apologize, I am experiencing technical difficulties at the moment. "
                    "Please hold on or call back shortly."
                )

            if not response_content:
                response_content = "I'm listening. How can I help you today?"

            # 7. Record executed tools in session manager for call history auditing
            if tools_called:
                for t in tools_called:
                    self.session_manager.record_tool_used(session_id, t)

            # 8. Persist assistant reply in session history
            self.session_manager.record_message(
                business_id=session.business_id,
                session_id=session_id,
                role="assistant",
                content=response_content,
            )

            # 9. Persist pending action if action was yielded
            if pending_action:
                self.db.save_pending_action(session.business_id, pending_action, session_id=session_id)

            # 9. Synthesize speech audio frame if TTS provider is configured
            audio_payload: Optional[bytes] = None
            if synthesize_audio and self.tts_provider and response_content:
                try:
                    audio_payload = self.tts_provider.synthesize(response_content)
                except Exception as tts_err:
                    logger.warning("TTS synthesis failed for turn %s: %s", transcript.turn_id, str(tts_err))

            # 10. Check if user or conversation signalled call termination
            lower_response = response_content.lower()
            farewell_terms = ["goodbye", "have a great day", "have a wonderful day", "bye for now", "alvida", "shubh din"]
            if any(term in lower_response for term in farewell_terms) and (
                workflow_result.get("followup_intent") == "no_further_query"
                or "thank you for calling" in lower_response
                or "कॉल करने के लिए धन्यवाद" in response_content
            ):
                should_terminate = True

            session_status = SessionStatus.COMPLETED.value if should_terminate else SessionStatus.ACTIVE.value
            if should_terminate:
                try:
                    self.session_manager.terminate_session(session_id, reason="completed")
                except Exception as term_err:
                    logger.debug("Auto-terminating session %s on call completion: %s", session_id, str(term_err))

            return VoiceTurnResult(
                session_id=session_id,
                turn_id=transcript.turn_id,
                user_text=user_text,
                assistant_text=response_content,
                audio_payload=audio_payload,
                tool_calls_executed=tools_called,
                pending_action=pending_action,
                filler_phrase=filler_phrase,
                llm_duration_ms=llm_duration_ms,
                session_status=session_status,
                should_terminate=should_terminate,
                timestamp=utcnow(),
            )
