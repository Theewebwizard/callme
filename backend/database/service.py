"""
Unified Database Service coordinating repositories across business operations.
Provides transactional boundaries, fallback detection, and decoupled data access for UI and agents.
"""

from typing import Optional, Dict, List, Any, Tuple
import time
import logging
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import Engine

from backend.database.engine import (
    get_engine,
    get_session_factory,
    session_scope,
    check_database_connection,
    DatabaseConfigurationError,
)
from backend.database.repositories import (
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
    PendingActionRepository,
    VoiceSessionRepository,
    ToolDemandRepository,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """Unified service providing safe, tenant-scoped data access."""

    def __init__(
        self,
        engine: Optional[Engine] = None,
        session_factory: Optional[sessionmaker] = None,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._profile_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def invalidate_profile_cache(self, business_id: Optional[str] = None) -> None:
        """Clear cached business profile for real-time consistency."""
        if business_id:
            self._profile_cache.pop(business_id, None)
        else:
            self._profile_cache.clear()

    @property
    def session_factory(self) -> sessionmaker:
        """Lazy-loaded session factory."""
        if self._session_factory is None:
            self._session_factory = get_session_factory(engine=self._engine)
        return self._session_factory

    def is_available(self) -> bool:
        """Check if database is configured and operational."""
        status = check_database_connection(engine=self._engine)
        return bool(status.get("connected", False))

    def get_connection_info(self) -> Dict[str, Any]:
        """Return connectivity diagnosis information."""
        return check_database_connection(engine=self._engine)

    def get_all_businesses(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve full profiles for all registered businesses."""
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            return repo.list_all_full()

    def get_business_profile(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full profile for a specific business with in-memory TTL caching."""
        cached = self._profile_cache.get(business_id)
        if cached:
            ts, profile = cached
            if (time.time() - ts) < 180.0:
                return profile

        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            profile = repo.get_full_profile(business_id)
            if profile:
                self._profile_cache[business_id] = (time.time(), profile)
            return profile

    def get_business_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve full profile for a business by owner Gmail address."""
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            biz = repo.get_by_owner_email(email)
            if not biz:
                return None
            return repo.get_full_profile(biz.id)

    def authenticate_business(self, email_or_identifier: str, plain_password: str) -> Optional[Dict[str, Any]]:
        """Verify business tenant Gmail/identifier and password, returning full profile if valid."""
        from backend.auth import verify_password
        with session_scope(self.session_factory) as session:
            repo = BusinessRepository(session)
            target = email_or_identifier.strip().lower()

            # 1. Look up by owner_email
            biz = repo.get_by_owner_email(target)

            # 2. Look up by business ID or Name if email lookup misses
            if not biz:
                all_b = repo.list_all()
                for b in all_b:
                    clean_phone = (b.phone_number or "").replace(" ", "").replace("+", "").replace("-", "")
                    clean_t = target.replace(" ", "").replace("+", "").replace("-", "")
                    if (
                        b.id.lower() == target
                        or b.name.lower() == target
                        or (b.owner_email and b.owner_email.strip().lower() == target)
                        or (clean_t and clean_t == clean_phone)
                    ):
                        biz = b
                        break

            if not biz:
                return None

            # Verify password
            if biz.password_hash:
                if not verify_password(plain_password, biz.password_hash):
                    return None
            else:
                # If no password hash is saved in DB, verify against standard demo password
                if plain_password != "haveli123":
                    return None

            return repo.get_full_profile(biz.id)

    def save_business_profile(
        self,
        business_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update business profile fields and optionally replace FAQs if supplied.
        Runs in a single transactional unit.
        """
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            updated_biz = biz_repo.update(business_id, updates)
            if not updated_biz:
                return None

            # If FAQs are included in updates, replace them atomically
            if "faqs" in updates:
                faq_repo = FAQRepository(session)
                faq_repo.replace_all_for_business(business_id, updates["faqs"])

            session.flush()
            profile = biz_repo.get_full_profile(business_id)
            if profile:
                self._profile_cache[business_id] = (time.time(), profile)
            return profile

    def create_business(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new business record."""
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            biz = biz_repo.create(data)
            return biz.to_dict()

    def update_business(self, business_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update mutable fields of a business."""
        return self.save_business_profile(business_id, updates)

    def delete_business(self, business_id: str) -> bool:
        """Delete a business and cascade delete related records."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            return biz_repo.delete(business_id)

    def save_business_faqs(
        self,
        business_id: str,
        faqs: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Replace all FAQs for a business."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            faq_repo = FAQRepository(session)
            created = faq_repo.replace_all_for_business(business_id, faqs)
            return [f.to_dict() for f in created]

    def set_tool_status(
        self,
        business_id: str,
        tool_id: str,
        is_enabled: bool,
    ) -> None:
        """Update tool activation status for a tenant."""
        self.invalidate_profile_cache(business_id)
        with session_scope(self.session_factory) as session:
            tool_repo = ToolConfigRepository(session)
            tool_repo.set_tool_status(business_id, tool_id, is_enabled)

    def create_tool_demand(self, business_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Record a custom tool/feature request demanded by a business tenant."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            demand = repo.create(business_id, data)
            return demand.to_dict()

    def list_tool_demands(self, business_id: str) -> List[Dict[str, Any]]:
        """List all custom tool demands requested by a business tenant."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            return repo.list_dicts_for_business(business_id)

    def list_all_tool_demands(self) -> List[Dict[str, Any]]:
        """List all custom tool demands across all businesses."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            return repo.list_all_demands()

    def update_tool_demand_status(self, demand_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """Update lifecycle status of a tool demand."""
        with session_scope(self.session_factory) as session:
            repo = ToolDemandRepository(session)
            return repo.update_status(demand_id, new_status)

    def get_call_history(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve audited call history records for a tenant."""
        with session_scope(self.session_factory) as session:
            call_repo = CallRepository(session)
            return call_repo.list_dicts_for_business(
                business_id=business_id,
                outcome_filter=outcome_filter,
                limit=limit,
            )

    def log_call(
        self,
        business_id: str,
        caller_number: str,
        duration_seconds: int,
        outcome: str,
        summary: str,
        tools_used: Optional[List[str]] = None,
        duration_formatted: Optional[str] = None,
        is_simulated: bool = True,
        call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an inbound call audit log."""
        with session_scope(self.session_factory) as session:
            call_repo = CallRepository(session)
            call = call_repo.log_call(
                business_id=business_id,
                caller_number=caller_number,
                duration_seconds=duration_seconds,
                duration_formatted=duration_formatted,
                outcome=outcome,
                summary=summary,
                tools_used=tools_used,
                is_simulated=is_simulated,
                call_id=call_id,
            )
            return call.to_dict()

    def get_conversation_messages(
        self,
        business_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation history for the playground."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            return conv_repo.list_dicts(business_id, limit=limit)

    def add_conversation_message(
        self,
        business_id: str,
        role: str,
        content: str,
        is_simulated: bool = True,
    ) -> Dict[str, Any]:
        """Persist a conversation message turn."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            msg = conv_repo.add_message(
                business_id=business_id,
                role=role,
                content=content,
                is_simulated=is_simulated,
            )
            return msg.to_dict()

    def reset_conversation_messages(self, business_id: str) -> None:
        """Clear conversation history and restore default greeting."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            conv_repo.clear_for_business(business_id)

            # Insert initial business greeting
            biz_repo = BusinessRepository(session)
            biz = biz_repo.get(business_id)
            if biz and biz.greeting_message:
                conv_repo.add_message(
                    business_id=business_id,
                    role="assistant",
                    content=biz.greeting_message,
                    is_simulated=True,
                )

    def get_pending_action(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Fetch active pending confirmation action for a business."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            action = pending_repo.get_latest_pending(business_id)
            return action.to_dict() if action else None

    def get_pending_action_by_id(self, business_id: str, action_id: str) -> Optional[Dict[str, Any]]:
        """Fetch pending action by exact action_id and verify business ownership."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            action = pending_repo.get(action_id)
            if not action or action.business_id != business_id:
                return None
            return action.to_dict()

    def save_pending_action(
        self,
        business_id: str,
        pending_action: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Persist a newly intercepted pending action awaiting confirmation."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            action = pending_repo.create_action(
                business_id=business_id,
                action_id=pending_action["action_id"],
                action_type=pending_action.get("tool_id", "unknown"),
                tool_name=pending_action.get("tool_name", "Unknown Action"),
                arguments=pending_action.get("arguments", {}),
                summary=pending_action.get("summary", ""),
            )
            return action.to_dict()

    def transition_pending_action(
        self,
        business_id: str,
        action_id: str,
        new_status: str,
        execution_reference: Optional[str] = None,
    ) -> bool:
        """Update status of a pending action to executed or cancelled."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            return pending_repo.transition_status(
                business_id=business_id,
                action_id=action_id,
                new_status=new_status,
                execution_reference=execution_reference,
            )

    def clear_pending_actions(self, business_id: str) -> int:
        """Cancel all pending confirmation actions for a tenant."""
        with session_scope(self.session_factory) as session:
            pending_repo = PendingActionRepository(session)
            return pending_repo.cancel_all_pending(business_id)

    def get_business_by_phone_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Lookup business by phone number with E.164 normalization."""
        with session_scope(self.session_factory) as session:
            biz_repo = BusinessRepository(session)
            biz = biz_repo.get_by_phone_number(phone_number)
            return biz.to_dict() if biz else None

    def create_voice_session(
        self,
        session_id: str,
        business_id: str,
        provider_call_id: str,
        provider_name: str,
        called_number: str,
        caller_number: Optional[str] = None,
        correlation_id: Optional[str] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and persist a new voice session."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            voice_session = repo.create_session(
                session_id=session_id,
                business_id=business_id,
                provider_call_id=provider_call_id,
                provider_name=provider_name,
                called_number=called_number,
                caller_number=caller_number,
                correlation_id=correlation_id,
                session_metadata=session_metadata,
            )
            return voice_session.to_dict()

    def get_voice_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve voice session by session ID."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.get(session_id)
            return s.to_dict() if s else None

    def get_voice_session_by_provider_call_id(
        self,
        provider_call_id: str,
        provider_name: str = "mock",
    ) -> Optional[Dict[str, Any]]:
        """Retrieve voice session by external provider call ID."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.get_by_provider_call_id(provider_call_id, provider_name=provider_name)
            return s.to_dict() if s else None

    def get_voice_session_by_correlation_id(
        self,
        correlation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve voice session by correlation ID (e.g. stream_sid)."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.get_by_correlation_id(correlation_id)
            return s.to_dict() if s else None

    def update_voice_session_metadata(
        self,
        session_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update session_metadata for a voice session."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.update_metadata(session_id, metadata_updates)
            return s.to_dict() if s else None

    def transition_voice_session_status(
        self,
        session_id: str,
        new_status: str,
        ended_at: Optional[Any] = None,
        call_record_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Transition voice session status and optional completion data."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.transition_status(
                session_id=session_id,
                new_status=new_status,
                ended_at=ended_at,
                call_record_id=call_record_id,
            )
            return s.to_dict() if s else None

    def update_voice_session_last_turn(
        self,
        session_id: str,
        timestamp: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update last_turn_at timestamp on a voice session."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            s = repo.update_last_turn(session_id=session_id, timestamp=timestamp)
            return s.to_dict() if s else None

    def list_active_voice_sessions(self, business_id: str) -> List[Dict[str, Any]]:
        """Retrieve all active voice sessions for a tenant."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            return [s.to_dict() for s in repo.list_active_for_business(business_id)]

    def list_voice_sessions(self, business_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent voice sessions for a tenant."""
        with session_scope(self.session_factory) as session:
            repo = VoiceSessionRepository(session)
            return [s.to_dict() for s in repo.list_for_business(business_id, limit=limit)]

    def add_session_message(
        self,
        business_id: str,
        session_id: str,
        role: str,
        content: str,
        is_simulated: bool = True,
    ) -> Dict[str, Any]:
        """Persist a conversation message scoped to a voice session."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            msg = conv_repo.add_message(
                business_id=business_id,
                role=role,
                content=content,
                is_simulated=is_simulated,
                session_id=session_id,
            )
            return msg.to_dict()

    def get_session_messages(
        self,
        business_id: str,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve message history scoped to a voice session."""
        with session_scope(self.session_factory) as session:
            conv_repo = ConversationRepository(session)
            return conv_repo.list_session_dicts(business_id=business_id, session_id=session_id, limit=limit)



_DEFAULT_SERVICE: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Retrieve or initialize singleton DatabaseService."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = DatabaseService()
    return _DEFAULT_SERVICE
