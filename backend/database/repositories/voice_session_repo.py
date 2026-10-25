"""
Repository for Voice Sessions (telephony state management).
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from backend.database.models import VoiceSession, utcnow
from backend.database.repositories.base import BaseRepository


class VoiceSessionRepository(BaseRepository):
    """Repository handling voice telephony session lifecycle and queries."""

    def create_session(
        self,
        session_id: str,
        business_id: str,
        provider_call_id: str,
        provider_name: str,
        called_number: str,
        caller_number: Optional[str] = None,
        correlation_id: Optional[str] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> VoiceSession:
        """Create and persist a new voice session."""
        now = utcnow()
        session_obj = VoiceSession(
            id=session_id,
            business_id=business_id,
            provider_call_id=provider_call_id,
            provider_name=provider_name,
            called_number=called_number,
            caller_number=caller_number,
            status="initiated",
            started_at=now,
            correlation_id=correlation_id,
            session_metadata=session_metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.session.add(session_obj)
        self.session.flush()
        return session_obj

    def get(self, session_id: str) -> Optional[VoiceSession]:
        """Fetch a voice session by its unique session_id."""
        stmt = select(VoiceSession).where(VoiceSession.id == session_id)
        return self.session.scalars(stmt).first()

    def get_by_provider_call_id(
        self,
        provider_call_id: str,
        provider_name: str = "mock",
    ) -> Optional[VoiceSession]:
        """Lookup voice session by external telephony provider call ID."""
        stmt = select(VoiceSession).where(
            VoiceSession.provider_call_id == provider_call_id,
            VoiceSession.provider_name == provider_name,
        )
        return self.session.scalars(stmt).first()

    def get_by_correlation_id(self, correlation_id: str) -> Optional[VoiceSession]:
        """Lookup voice session by correlation ID (e.g. stream_sid)."""
        stmt = select(VoiceSession).where(VoiceSession.correlation_id == correlation_id)
        return self.session.scalars(stmt).first()

    def update_metadata(
        self,
        session_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Optional[VoiceSession]:
        """Update session_metadata dictionary for an existing session."""
        session_obj = self.get(session_id)
        if not session_obj:
            return None

        current = dict(session_obj.session_metadata or {})
        current.update(metadata_updates)
        session_obj.session_metadata = current
        session_obj.updated_at = utcnow()
        self.session.flush()
        return session_obj

    def transition_status(
        self,
        session_id: str,
        new_status: str,
        ended_at: Optional[datetime] = None,
        call_record_id: Optional[str] = None,
    ) -> Optional[VoiceSession]:
        """Update session status and optional completion fields."""
        session_obj = self.get(session_id)
        if not session_obj:
            return None

        session_obj.status = new_status
        session_obj.updated_at = utcnow()
        if ended_at is not None:
            session_obj.ended_at = ended_at
        if call_record_id is not None:
            session_obj.call_record_id = call_record_id

        self.session.flush()
        return session_obj

    def update_last_turn(
        self,
        session_id: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[VoiceSession]:
        """Update last_turn_at timestamp for an active session."""
        session_obj = self.get(session_id)
        if not session_obj:
            return None

        now = timestamp or utcnow()
        session_obj.last_turn_at = now
        session_obj.updated_at = now
        if session_obj.status == "initiated":
            session_obj.status = "active"

        self.session.flush()
        return session_obj

    def list_active_for_business(self, business_id: str) -> List[VoiceSession]:
        """Retrieve all currently active or initiated sessions for a tenant."""
        stmt = (
            select(VoiceSession)
            .where(
                VoiceSession.business_id == business_id,
                VoiceSession.status.in_(["initiated", "active"]),
            )
            .order_by(VoiceSession.started_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def list_for_business(self, business_id: str, limit: int = 50) -> List[VoiceSession]:
        """Retrieve recent voice sessions for a tenant."""
        stmt = (
            select(VoiceSession)
            .where(VoiceSession.business_id == business_id)
            .order_by(VoiceSession.started_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())
