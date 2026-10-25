"""
Repository for Conversation Messages (Playground chats).
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.database.models import ConversationMessage, utcnow
from backend.database.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    """Repository handling playground chat message persistence."""

    def add_message(
        self,
        business_id: str,
        role: str,
        content: str,
        is_simulated: bool = True,
        timestamp: Optional[datetime] = None,
        session_id: Optional[str] = None,
    ) -> ConversationMessage:
        """Append a message turn to the persistent chat history."""
        msg = ConversationMessage(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
            session_id=session_id,
            role=role,
            content=content,
            timestamp=timestamp or utcnow(),
            is_simulated=is_simulated,
        )
        self.session.add(msg)
        self.session.flush()
        return msg

    def list_messages(
        self,
        business_id: str,
        limit: int = 100,
        session_id: Optional[str] = None,
        playground_only: bool = True,
    ) -> List[ConversationMessage]:
        """Fetch chronological message history for a tenant."""
        stmt = select(ConversationMessage).where(ConversationMessage.business_id == business_id)
        if session_id is not None:
            stmt = stmt.where(ConversationMessage.session_id == session_id)
        elif playground_only:
            stmt = stmt.where(ConversationMessage.session_id.is_(None))
        stmt = stmt.order_by(ConversationMessage.timestamp).limit(limit)
        return list(self.session.scalars(stmt).all())

    def list_session_messages(
        self,
        business_id: str,
        session_id: str,
        limit: int = 100,
    ) -> List[ConversationMessage]:
        """Fetch chronological message history scoped to a voice session."""
        stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.business_id == business_id,
                ConversationMessage.session_id == session_id,
            )
            .order_by(ConversationMessage.timestamp)
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_dicts(
        self,
        business_id: str,
        limit: int = 100,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of message dicts for UI rendering."""
        msgs = self.list_messages(business_id=business_id, limit=limit, session_id=session_id)
        return [m.to_dict() for m in msgs]

    def list_session_dicts(
        self,
        business_id: str,
        session_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return list of message dicts for a voice session."""
        msgs = self.list_session_messages(business_id=business_id, session_id=session_id, limit=limit)
        return [m.to_dict() for m in msgs]

    def clear_for_business(self, business_id: str) -> int:
        """Clear all conversation messages for a tenant."""
        stmt = delete(ConversationMessage).where(ConversationMessage.business_id == business_id)
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount or 0
