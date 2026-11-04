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
    Integer, Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    JSON,
    BigInteger,
    text,
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
    reservable_resources = relationship("ReservableResource", back_populates="business", cascade="all, delete-orphan", lazy="select")
    reservations = relationship("Reservation", back_populates="business", cascade="all, delete-orphan", lazy="select")
    menu_items = relationship("MenuItem", back_populates="business", cascade="all, delete-orphan", lazy="select")
    room_types = relationship("RoomType", back_populates="business", cascade="all, delete-orphan", lazy="select")

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


class MenuItem(Base):
    """
    Business-specific restaurant menu item record.
    Used for semantic menu retrieval, pricing inquiries, dietary filtering, and recommendations.
    """
    __tablename__ = "menu_items"

    id = Column(String(64), primary_key=True, default=lambda: f"item_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)  # e.g., 'Starters', 'Mains', 'Breads', 'Desserts', 'Beverages'
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="INR", nullable=False)
    description = Column(Text, nullable=True)
    dietary_tags = Column(JSON, default=list, nullable=False)  # e.g., ['vegetarian', 'vegan', 'gluten-free', 'jain']
    spice_level = Column(String(50), nullable=True)  # e.g., 'mild', 'medium', 'spicy'
    is_available = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="menu_items")

    __table_args__ = (
        Index("ix_menu_business_category", "business_id", "category"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert menu item to dictionary representation."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "currency": self.currency,
            "description": self.description or "",
            "dietary_tags": self.dietary_tags or [],
            "spice_level": self.spice_level or "medium",
            "is_available": self.is_available,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RoomType(Base):
    """
    Business-specific hotel room type and rate card record.
    Used for semantic room retrieval, rate inquiries, capacity filtering, and amenities matching.
    """
    __tablename__ = "room_types"

    id = Column(String(64), primary_key=True, default=lambda: f"room_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)  # e.g., 'Rooms', 'Suites', 'Villas', 'Penthouses'
    base_price = Column(Float, nullable=False)
    weekend_price = Column(Float, nullable=True)
    currency = Column(String(10), default="INR", nullable=False)
    description = Column(Text, nullable=True)
    bed_type = Column(String(100), default="1 King Bed", nullable=False)
    max_occupancy = Column(Integer, default=2, nullable=False)
    max_adults = Column(Integer, default=2, nullable=False)
    max_children = Column(Integer, default=1, nullable=False)
    amenities = Column(JSON, default=list, nullable=False)  # e.g., ['Ocean View', 'Balcony', 'Bathtub', 'High-Speed Wi-Fi']
    inclusions = Column(JSON, default=list, nullable=False)  # e.g., ['Breakfast Included', 'Airport Transfer', 'Pool Access']
    check_in_time = Column(String(10), default="14:00", nullable=False)
    check_out_time = Column(String(10), default="11:00", nullable=False)
    cancellation_policy = Column(String(255), default="Free cancellation up to 48 hours prior to arrival", nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="room_types")

    __table_args__ = (
        Index("ix_room_business_category", "business_id", "category"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert room type to dictionary representation."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "category": self.category,
            "base_price": self.base_price,
            "weekend_price": self.weekend_price if self.weekend_price is not None else self.base_price,
            "currency": self.currency,
            "description": self.description or "",
            "bed_type": self.bed_type or "1 King Bed",
            "max_occupancy": self.max_occupancy,
            "max_adults": self.max_adults,
            "max_children": self.max_children,
            "amenities": self.amenities or [],
            "inclusions": self.inclusions or [],
            "check_in_time": self.check_in_time or "14:00",
            "check_out_time": self.check_out_time or "11:00",
            "cancellation_policy": self.cancellation_policy or "Free cancellation up to 48 hours prior to arrival",
            "is_available": self.is_available,
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
    status = Column(String(32), default="not_configured", nullable=False)  # "not_configured", "needs_input", "awaiting_authorization", "validating", "ready", "degraded", "disconnected", "failed"
    selected_option_id = Column(String(64), nullable=True)  # e.g. "builtin_dining", "google_calendar"
    configuration = Column(JSON, default=dict, nullable=False)  # non-secret settings
    readiness_details = Column(JSON, default=dict, nullable=False)  # validation checks, timestamps, diagnostic summary
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
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
            "status": self.status,
            "selected_option_id": self.selected_option_id,
            "configuration": self.configuration or {},
            "readiness_details": self.readiness_details or {},
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
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
    transcript = Column(JSON, default=list, nullable=True)
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
            "transcript": self.transcript or [],
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
    session_id = Column(String(64), ForeignKey("voice_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
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
        Index("ix_pending_session_status", "session_id", "status"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert pending action to dictionary."""
        return {
            "action_id": self.id,
            "business_id": self.business_id,
            "session_id": self.session_id,
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


class IntegrationConnection(Base):
    """
    Multi-account integration connection entity.
    Represents an authenticated connection to an external provider (e.g. Google Calendar, Stripe, SevenRooms).
    Enables multi-calendar, multi-location, and multi-department accounts per business tenant.
    """
    __tablename__ = "integration_connections"

    id = Column(String(64), primary_key=True, default=lambda: f"conn_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(String(64), nullable=False, index=True)
    connection_slug = Column(String(64), nullable=False, default="default")
    external_account_id = Column(String(255), nullable=True)
    display_label = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    status = Column(String(32), default="active", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "provider_id", "connection_slug", name="uq_biz_provider_slug"),
        Index(
            "ix_uq_biz_provider_default",
            "business_id",
            "provider_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default = true"),
        ),
        Index(
            "ix_uq_biz_provider_external_acct",
            "business_id",
            "provider_id",
            "external_account_id",
            unique=True,
            sqlite_where=text("external_account_id IS NOT NULL"),
            postgresql_where=text("external_account_id IS NOT NULL"),
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert connection record to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "provider_id": self.provider_id,
            "connection_slug": self.connection_slug,
            "external_account_id": self.external_account_id,
            "display_label": self.display_label,
            "is_default": self.is_default,
            "status": self.status,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class IntegrationCredential(Base):
    """
    Secure tenant integration credential store.
    Stores encrypted secret material (tokens, keys, service account JSON)
    strictly separated from ordinary tenant configuration.
    """
    __tablename__ = "integration_credentials"

    id = Column(String(64), primary_key=True, default=lambda: f"cred_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(String(64), ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=True, index=True)
    tool_id = Column(String(64), nullable=False, index=True)
    option_id = Column(String(64), nullable=False)
    encrypted_secrets = Column(Text, nullable=False)
    key_fingerprint = Column(String(64), nullable=False)
    scopes = Column(JSON, default=list, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    lease_owner_id = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    fencing_token = Column(BigInteger, default=0, nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "tool_id", name="uq_business_tool_cred"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert credential record to dictionary with encrypted secrets suppressed."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "connection_id": self.connection_id,
            "tool_id": self.tool_id,
            "option_id": self.option_id,
            "key_fingerprint": self.key_fingerprint,
            "scopes": self.scopes or [],
            "fencing_token": self.fencing_token,
            "schema_version": self.schema_version,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ReservableResource(Base):
    """
    First-party reservable asset (dining table, clinical consultation room, dental chair).
    Authoritative resource definition for built-in booking and capacity management.
    """
    __tablename__ = "reservable_resources"

    id = Column(String(64), primary_key=True, default=lambda: f"res_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(32), default="table", nullable=False)  # "table", "room", "practitioner"
    name = Column(String(100), nullable=False)  # e.g. "Table 4 (Garden Patio)", "Dental Suite 1"
    capacity = Column(Integer, default=4, nullable=False)
    min_party_size = Column(Integer, default=1, nullable=False)
    max_party_size = Column(Integer, default=4, nullable=False)
    section = Column(String(100), nullable=True)  # e.g. "Patio", "Main Hall", "First Floor"
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="reservable_resources")
    reservations = relationship("Reservation", back_populates="resource", cascade="all, delete-orphan", lazy="select")

    __table_args__ = (
        Index("ix_resource_business_active", "business_id", "is_active"),
        Index("ix_resource_business_party", "business_id", "min_party_size", "max_party_size"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert resource to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "resource_type": self.resource_type,
            "name": self.name,
            "capacity": self.capacity,
            "min_party_size": self.min_party_size,
            "max_party_size": self.max_party_size,
            "section": self.section,
            "is_active": self.is_active,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Reservation(Base):
    """
    Authoritative transactional reservation or appointment record.
    Prevents double-booking and concurrent conflict via database-level checks.
    """
    __tablename__ = "reservations"

    id = Column(String(64), primary_key=True, default=lambda: f"BK-{uuid.uuid4().hex[:8].upper()}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id = Column(String(64), ForeignKey("reservable_resources.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(50), nullable=False)
    party_size = Column(Integer, default=2, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(32), default="confirmed", nullable=False)  # "confirmed", "hold", "pending_confirmation", "rescheduled", "cancelled", "completed", "no_show", "waitlisted"
    hold_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    rescheduled_from_id = Column(String(64), nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    special_requests = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    business = relationship("Business", back_populates="reservations")
    resource = relationship("ReservableResource", back_populates="reservations")

    __table_args__ = (
        Index("ix_res_business_start", "business_id", "start_time"),
        Index("ix_res_resource_window", "resource_id", "start_time", "end_time", "status"),
        Index("ix_res_business_idempotency", "business_id", "idempotency_key"),
        Index("ix_res_business_status", "business_id", "status"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert reservation to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "resource_id": self.resource_id,
            "resource_name": self.resource.name if self.resource else None,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "party_size": self.party_size,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "hold_expires_at": self.hold_expires_at.isoformat() if getattr(self, "hold_expires_at", None) else None,
            "rescheduled_from_id": getattr(self, "rescheduled_from_id", None),
            "metadata": getattr(self, "metadata_json", {}) or {},
            "special_requests": self.special_requests,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CapabilitySetupSession(Base):
    """
    Server-side stateful setup session for guided capability onboarding.
    Supports partial saving, step resumption, and credential isolation.
    """
    __tablename__ = "capability_setup_sessions"

    id = Column(String(64), primary_key=True, default=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_id = Column(String(64), nullable=False, index=True)
    selected_option_id = Column(String(64), nullable=True)
    current_step = Column(String(64), default="select_option", nullable=False)
    step_data = Column(JSON, default=dict, nullable=False)
    status = Column(String(32), default="needs_input", nullable=False)  # "needs_input", "awaiting_authorization", "validating", "ready", "failed"
    validation_errors = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_setup_sess_business_tool", "business_id", "tool_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert setup session to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "tool_id": self.tool_id,
            "selected_option_id": self.selected_option_id,
            "current_step": self.current_step,
            "step_data": self.step_data or {},
            "status": self.status,
            "validation_errors": self.validation_errors or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CapabilityAuditEvent(Base):
    """
    Tenant-scoped audit and observability telemetry for capability lifecycle events.
    """
    __tablename__ = "capability_audit_events"

    id = Column(String(64), primary_key=True, default=lambda: f"aud_{uuid.uuid4().hex[:12]}")
    business_id = Column(String(64), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)  # "state_transition", "readiness_checked", "booking_created", "conflict_prevented", etc.
    details = Column(JSON, default=dict, nullable=False)
    correlation_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_cap_audit_biz_event", "business_id", "event_type"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "tool_id": self.tool_id,
            "event_type": self.event_type,
            "details": self.details or {},
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
