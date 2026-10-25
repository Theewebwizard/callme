"""
SQLAlchemy ORM models for multi-tenant persistence.
All models support PostgreSQL and SQLite (for isolated unit tests).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow() -> datetime:
    """Return current UTC timestamp with timezone."""
    return datetime.now(timezone.utc)


class Business(Base):
    """
    Business tenant entity representing a subscriber business (restaurant, clinic, etc.).
    """
    __tablename__ = "businesses"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    phone_number = Column(String(50), nullable=True)
    assigned_number_status = Column(String(50), default="Active & Connected")
    opening_time = Column(String(10), nullable=False, default="09:00")
    closing_time = Column(String(10), nullable=False, default="22:00")
    timezone = Column(String(50), nullable=False, default="Asia/Kolkata")
    greeting_message = Column(Text, nullable=False)
    languages = Column(JSON, default=list, nullable=False)
    transfer_instructions = Column(Text, nullable=True)
    owner_email = Column(String(255), nullable=True, index=True)
    owner_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships with cascade delete
    faqs = relationship("BusinessFAQ", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    tool_configs = relationship("BusinessToolConfig", back_populates="business", cascade="all, delete-orphan", lazy="selectin")
    call_records = relationship("CallRecord", back_populates="business", cascade="all, delete-orphan", lazy="select")
    messages = relationship("ConversationMessage", back_populates="business", cascade="all, delete-orphan", lazy="select")
    pending_actions = relationship("PendingAction", back_populates="business", cascade="all, delete-orphan", lazy="select")
    voice_sessions = relationship("VoiceSession", back_populates="business", cascade="all, delete-orphan", lazy="select")
    tool_demands = relationship("ToolDemand", back_populates="business", cascade="all, delete-orphan", lazy="select")

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "description": self.description or "",
            "phone_number": self.phone_number or "",
            "assigned_number_status": self.assigned_number_status or "Active & Connected",
            "opening_time": self.opening_time,
            "closing_time": self.closing_time,
            "timezone": self.timezone,
            "greeting_message": self.greeting_message,
            "languages": self.languages or ["English"],
            "transfer_instructions": self.transfer_instructions or "",
            "owner_email": self.owner_email or "",
            "owner_name": self.owner_name or "",
            # NOTE: password_hash is intentionally excluded from serialization
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BusinessFAQ(Base):
    """
    Business-specific FAQ and knowledge-base record.
    """
    __tablename__ = "business_faqs"

    id = Column(String(64), primary_key=True, default=lambda: f"faq_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(100), default="General", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="faqs")

    def to_dict(self) -> Dict[str, Any]:
        """Convert FAQ to dictionary format."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BusinessToolConfig(Base):
    """
    Tenant-specific tool activation configuration.
    Enforces uniqueness per (business_id, tool_id).
    """
    __tablename__ = "business_tool_configs"

    id = Column(String(64), primary_key=True, default=lambda: f"tc_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_id = Column(String(64), nullable=False, index=True)
    is_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="tool_configs")

    __table_args__ = (
        UniqueConstraint("business_id", "tool_id", name="uq_business_tool"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert tool config to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "tool_id": self.tool_id,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CallRecord(Base):
    """
    Audited call record logging duration, caller (privacy-conscious), outcome, tools used, and simulation status.
    """
    __tablename__ = "call_records"

    id = Column(String(64), primary_key=True, default=lambda: f"call_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    caller_number = Column(String(50), nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    duration_formatted = Column(String(20), default="0m 00s", nullable=False)
    outcome = Column(String(100), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    tools_used = Column(JSON, default=list, nullable=False)
    is_simulated = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    business = relationship("Business", back_populates="call_records")

    __table_args__ = (
        Index("ix_call_business_timestamp", "business_id", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert call record to dictionary representation matching UI format."""
        dt_str = self.timestamp.strftime("%Y-%m-%d %H:%M") if self.timestamp else ""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "datetime": dt_str,
            "caller_number": self.caller_number,
            "duration": self.duration_formatted or f"{self.duration_seconds // 60}m {self.duration_seconds % 60:02d}s",
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome,
            "summary": self.summary or "",
            "tools_used": self.tools_used or [],
            "is_simulated": self.is_simulated,
        }


class VoiceSession(Base):
    """
    Active or completed voice telephony session linked to a business tenant.
    """
    __tablename__ = "voice_sessions"

    id = Column(String(64), primary_key=True)  # session_id UUID
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_call_id = Column(String(128), nullable=False, index=True)
    provider_name = Column(String(50), nullable=False, default="mock")
    called_number = Column(String(50), nullable=False)
    caller_number = Column(String(50), nullable=True)
    status = Column(String(30), nullable=False, default="initiated", index=True)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    last_turn_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String(64), nullable=True)
    call_record_id = Column(String(64), ForeignKey("call_records.id", ondelete="SET NULL"), nullable=True)
    session_metadata = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="voice_sessions")
    call_record = relationship("CallRecord")
    messages = relationship("ConversationMessage", back_populates="voice_session", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_voice_session_business_status", "business_id", "status"),
        Index("ix_voice_session_provider_call", "provider_name", "provider_call_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert voice session to dictionary format."""
        return {
            "session_id": self.id,
            "business_id": self.business_id,
            "provider_call_id": self.provider_call_id,
            "provider_name": self.provider_name,
            "called_number": self.called_number,
            "caller_number": self.caller_number,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "last_turn_at": self.last_turn_at.isoformat() if self.last_turn_at else None,
            "correlation_id": self.correlation_id,
            "call_record_id": self.call_record_id,
            "session_metadata": self.session_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConversationMessage(Base):
    """
    Conversation messages scoped to a business tenant and optionally to a voice session.
    """
    __tablename__ = "conversation_messages"

    id = Column(String(64), primary_key=True, default=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(64), ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    is_simulated = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    business = relationship("Business", back_populates="messages")
    voice_session = relationship("VoiceSession", back_populates="messages")

    __table_args__ = (
        Index("ix_msg_business_timestamp", "business_id", "timestamp"),
        Index("ix_msg_session_timestamp", "session_id", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else "Just now",
            "is_simulated": self.is_simulated,
        }


class PendingAction(Base):
    """
    Persisted state-modifying action awaiting human confirmation (Phase B).
    """
    __tablename__ = "pending_actions"

    id = Column(String(64), primary_key=True)  # Matches action_id UUID
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(64), nullable=False)
    tool_name = Column(String(100), nullable=False)
    arguments = Column(JSON, default=dict, nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(30), default="pending_confirmation", nullable=False, index=True)
    execution_reference = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)

    business = relationship("Business", back_populates="pending_actions")

    __table_args__ = (
        Index("ix_pending_business_status", "business_id", "status"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert pending action to dictionary."""
        return {
            "action_id": self.id,
            "business_id": self.business_id,
            "tool_id": self.action_type,
            "tool_name": self.tool_name,
            "arguments": self.arguments or {},
            "summary": self.summary or "",
            "status": self.status,
            "execution_reference": self.execution_reference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class ToolDemand(Base):
    """
    Custom tool demands and feature requests submitted by a business tenant.
    """
    __tablename__ = "tool_demands"

    id = Column(String(64), primary_key=True)
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), default="Custom Integration", nullable=False)
    integration_target = Column(String(100), nullable=True)
    priority = Column(String(30), default="Important", nullable=False)
    status = Column(String(30), default="Under Review", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    business = relationship("Business", back_populates="tool_demands")

    __table_args__ = (
        Index("ix_tool_demands_business_status", "business_id", "status"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert tool demand to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "tool_name": self.tool_name,
            "description": self.description,
            "category": self.category,
            "integration_target": self.integration_target or "Custom API",
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
