"""
Repository for Business Tool Configuration and Capability Lifecycle Management.
Manages capability statuses, setup sessions, encrypted credentials, and audit telemetry.
"""

from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from backend.database.models import (
    BusinessToolConfig,
    IntegrationCredential,
    CapabilitySetupSession,
    CapabilityAuditEvent,
    utcnow,
)
from backend.database.repositories.base import BaseRepository


class ToolConfigRepository(BaseRepository):
    """Repository handling business tool activation settings and capability lifecycle."""

    # ---------------------------------------------------------------------------
    # 1. Tool Status & Capability Config
    # ---------------------------------------------------------------------------

    def get_tool_statuses(self, business_id: str) -> Dict[str, bool]:
        """Fetch dictionary of {tool_id: is_enabled} for the business."""
        stmt = select(BusinessToolConfig).where(BusinessToolConfig.business_id == business_id)
        records = self.session.scalars(stmt).all()
        return {r.tool_id: r.is_enabled for r in records}

    def is_tool_enabled(self, business_id: str, tool_id: str) -> bool:
        """Check whether a specific tool is enabled for the business."""
        stmt = (
            select(BusinessToolConfig.is_enabled)
            .where(
                BusinessToolConfig.business_id == business_id,
                BusinessToolConfig.tool_id == tool_id,
            )
        )
        result = self.session.scalar(stmt)
        return bool(result)

    def get_tool_config(self, business_id: str, tool_id: str) -> Optional[BusinessToolConfig]:
        """Fetch complete tool capability record for a tenant."""
        stmt = (
            select(BusinessToolConfig)
            .where(
                BusinessToolConfig.business_id == business_id,
                BusinessToolConfig.tool_id == tool_id,
            )
        )
        return self.session.scalar(stmt)

    def list_tool_configs(self, business_id: str) -> List[BusinessToolConfig]:
        """Fetch all tool configurations for a business tenant."""
        stmt = select(BusinessToolConfig).where(BusinessToolConfig.business_id == business_id)
        return list(self.session.scalars(stmt).all())

    def set_tool_status(
        self,
        business_id: str,
        tool_id: str,
        is_enabled: bool,
    ) -> BusinessToolConfig:
        """Insert or update tool activation status for a tenant."""
        record = self.get_tool_config(business_id, tool_id)
        now = utcnow()
        if record:
            record.is_enabled = is_enabled
            record.updated_at = now
        else:
            record = BusinessToolConfig(
                id=f"tc_{uuid.uuid4().hex[:12]}",
                business_id=business_id,
                tool_id=tool_id,
                is_enabled=is_enabled,
                status="ready" if is_enabled else "not_configured",
                configuration={},
                readiness_details={},
                created_at=now,
                updated_at=now,
            )
            self.session.add(record)

        self.session.flush()
        return record

    def set_tool_capability(
        self,
        business_id: str,
        tool_id: str,
        is_enabled: Optional[bool] = None,
        status: Optional[str] = None,
        selected_option_id: Optional[str] = None,
        configuration: Optional[Dict[str, Any]] = None,
        readiness_details: Optional[Dict[str, Any]] = None,
        last_validated_at: Optional[datetime] = None,
    ) -> BusinessToolConfig:
        """Deep update of capability state, configuration, and readiness."""
        record = self.get_tool_config(business_id, tool_id)
        now = utcnow()
        if not record:
            record = BusinessToolConfig(
                id=f"tc_{uuid.uuid4().hex[:12]}",
                business_id=business_id,
                tool_id=tool_id,
                is_enabled=is_enabled if is_enabled is not None else False,
                status=status or "not_configured",
                selected_option_id=selected_option_id,
                configuration=configuration or {},
                readiness_details=readiness_details or {},
                last_validated_at=last_validated_at,
                created_at=now,
                updated_at=now,
            )
            self.session.add(record)
        else:
            if is_enabled is not None:
                record.is_enabled = is_enabled
            if status is not None:
                record.status = status
            if selected_option_id is not None:
                record.selected_option_id = selected_option_id
            if configuration is not None:
                # Merge or replace configuration
                updated_conf = dict(record.configuration or {})
                updated_conf.update(configuration)
                record.configuration = updated_conf
            if readiness_details is not None:
                record.readiness_details = readiness_details
            if last_validated_at is not None:
                record.last_validated_at = last_validated_at
            record.updated_at = now

        self.session.flush()
        return record

    def bulk_set_tool_statuses(
        self,
        business_id: str,
        statuses: Dict[str, bool],
    ) -> None:
        """Update multiple tool statuses in batch for a tenant."""
        for tool_id, enabled in statuses.items():
            self.set_tool_status(business_id, tool_id, enabled)
        self.session.flush()

    # ---------------------------------------------------------------------------
    # 2. Setup Sessions (Wizard State Machine)
    # ---------------------------------------------------------------------------

    def save_setup_session(
        self,
        business_id: str,
        tool_id: str,
        session_id: Optional[str] = None,
        selected_option_id: Optional[str] = None,
        current_step: str = "select_option",
        step_data: Optional[Dict[str, Any]] = None,
        status: str = "needs_input",
        validation_errors: Optional[List[Dict[str, Any]]] = None,
    ) -> CapabilitySetupSession:
        """Create or update a resumable capability setup session."""
        session_record = None
        if session_id:
            session_record = self.get_setup_session(session_id, business_id=business_id)

        now = utcnow()
        if not session_record:
            # Check if there is an active session for (business_id, tool_id)
            session_record = self.get_setup_session_by_tool(business_id, tool_id)

        if session_record:
            if selected_option_id is not None:
                session_record.selected_option_id = selected_option_id
            session_record.current_step = current_step
            if step_data is not None:
                current_data = dict(session_record.step_data or {})
                current_data.update(step_data)
                session_record.step_data = current_data
            session_record.status = status
            if validation_errors is not None:
                session_record.validation_errors = validation_errors
            session_record.updated_at = now
        else:
            session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
            session_record = CapabilitySetupSession(
                id=session_id,
                business_id=business_id,
                tool_id=tool_id,
                selected_option_id=selected_option_id,
                current_step=current_step,
                step_data=step_data or {},
                status=status,
                validation_errors=validation_errors or [],
                created_at=now,
                updated_at=now,
            )
            self.session.add(session_record)

        self.session.flush()
        return session_record

    def get_setup_session(self, session_id: str, business_id: Optional[str] = None) -> Optional[CapabilitySetupSession]:
        """Fetch setup session by ID with optional tenant scoping."""
        stmt = select(CapabilitySetupSession).where(CapabilitySetupSession.id == session_id)
        if business_id:
            stmt = stmt.where(CapabilitySetupSession.business_id == business_id)
        return self.session.scalar(stmt)

    def get_setup_session_by_tool(self, business_id: str, tool_id: str) -> Optional[CapabilitySetupSession]:
        """Fetch latest setup session for a tool."""
        stmt = (
            select(CapabilitySetupSession)
            .where(
                CapabilitySetupSession.business_id == business_id,
                CapabilitySetupSession.tool_id == tool_id,
            )
            .order_by(desc(CapabilitySetupSession.updated_at))
            .limit(1)
        )
        return self.session.scalar(stmt)

    def delete_setup_session(self, session_id: str, business_id: Optional[str] = None) -> bool:
        """Delete a completed or abandoned setup session."""
        sess = self.get_setup_session(session_id, business_id=business_id)
        if not sess:
            return False
        self.session.delete(sess)
        self.session.flush()
        return True

    # ---------------------------------------------------------------------------
    # 3. Integration Credentials (Encrypted Secret Vault)
    # ---------------------------------------------------------------------------

    def save_credential(
        self,
        business_id: str,
        tool_id: str,
        option_id: str,
        encrypted_secrets: str,
        key_fingerprint: str,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> IntegrationCredential:
        """Store or replace encrypted credential record for an integration."""
        cred = self.get_credential(business_id, tool_id)
        now = utcnow()
        if cred:
            cred.option_id = option_id
            cred.encrypted_secrets = encrypted_secrets
            cred.key_fingerprint = key_fingerprint
            cred.scopes = scopes or []
            cred.expires_at = expires_at
            cred.updated_at = now
        else:
            cred = IntegrationCredential(
                id=f"cred_{uuid.uuid4().hex[:12]}",
                business_id=business_id,
                tool_id=tool_id,
                option_id=option_id,
                encrypted_secrets=encrypted_secrets,
                key_fingerprint=key_fingerprint,
                scopes=scopes or [],
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            self.session.add(cred)

        self.session.flush()
        return cred

    def get_credential(self, business_id: str, tool_id: str) -> Optional[IntegrationCredential]:
        """Retrieve credential record for a business and tool."""
        stmt = (
            select(IntegrationCredential)
            .where(
                IntegrationCredential.business_id == business_id,
                IntegrationCredential.tool_id == tool_id,
            )
        )
        return self.session.scalar(stmt)

    def delete_credential(self, business_id: str, tool_id: str) -> bool:
        """Purge stored integration credentials upon disconnect."""
        cred = self.get_credential(business_id, tool_id)
        if not cred:
            return False
        self.session.delete(cred)
        self.session.flush()
        return True

    # ---------------------------------------------------------------------------
    # 4. Audit Telemetry
    # ---------------------------------------------------------------------------

    def record_audit_event(
        self,
        business_id: str,
        tool_id: str,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> CapabilityAuditEvent:
        """Record tenant-scoped operational audit event."""
        event_id = f"aud_{uuid.uuid4().hex[:12]}"
        audit = CapabilityAuditEvent(
            id=event_id,
            business_id=business_id,
            tool_id=tool_id,
            event_type=event_type,
            details=details or {},
            correlation_id=correlation_id,
            created_at=utcnow(),
        )
        self.session.add(audit)
        self.session.flush()
        return audit

    def list_audit_events(
        self,
        business_id: str,
        tool_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[CapabilityAuditEvent]:
        """Fetch audit trail for business."""
        stmt = (
            select(CapabilityAuditEvent)
            .where(CapabilityAuditEvent.business_id == business_id)
            .order_by(desc(CapabilityAuditEvent.created_at))
            .limit(limit)
        )
        if tool_id:
            stmt = stmt.where(CapabilityAuditEvent.tool_id == tool_id)
        return list(self.session.scalars(stmt).all())
