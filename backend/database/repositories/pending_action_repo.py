"""
Repository for Phase B Pending Actions requiring human confirmation.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, update

from backend.database.models import PendingAction, utcnow
from backend.database.repositories.base import BaseRepository


class PendingActionRepository(BaseRepository):
    """Repository managing two-phase confirmation action persistence."""

    def create_action(
        self,
        business_id: str,
        action_id: str,
        action_type: str,
        tool_name: str,
        arguments: Dict[str, Any],
        summary: Optional[str] = None,
        expiry_seconds: int = 3600,
    ) -> PendingAction:
        """Create a pending confirmation record."""
        now = utcnow()
        expires = now + timedelta(seconds=expiry_seconds)

        action = PendingAction(
            id=action_id,
            business_id=business_id,
            action_type=action_type,
            tool_name=tool_name,
            arguments=arguments or {},
            summary=summary or "",
            status="pending_confirmation",
            created_at=now,
            expires_at=expires,
        )
        self.session.add(action)
        self.session.flush()
        return action

    def get(self, action_id: str) -> Optional[PendingAction]:
        """Fetch pending action by ID, evaluating expiration status."""
        action = self.session.get(PendingAction, action_id)
        if action and action.status == "pending_confirmation" and action.expires_at:
            exp = action.expires_at
            now = utcnow()
            if exp.tzinfo is None and now.tzinfo is not None:
                exp = exp.replace(tzinfo=timezone.utc)
            elif exp.tzinfo is not None and now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if exp < now:
                action.status = "expired"
                self.session.flush()
        return action

    def get_latest_pending(self, business_id: str) -> Optional[PendingAction]:
        """Fetch the most recent pending confirmation action for a tenant."""
        stmt = (
            select(PendingAction)
            .where(
                PendingAction.business_id == business_id,
                PendingAction.status == "pending_confirmation",
            )
            .order_by(desc(PendingAction.created_at))
            .limit(1)
        )
        action = self.session.scalar(stmt)
        if not action:
            return None

        # Check for expiry
        if action.expires_at:
            exp = action.expires_at
            now = utcnow()
            if exp.tzinfo is None and now.tzinfo is not None:
                exp = exp.replace(tzinfo=timezone.utc)
            elif exp.tzinfo is not None and now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if exp < now:
                action.status = "expired"
                self.session.flush()
                return None

        return action

    def transition_status(
        self,
        business_id: str,
        action_id: str,
        new_status: str,
        execution_reference: Optional[str] = None,
    ) -> bool:
        """
        Safely transition action status (e.g. from pending_confirmation to executed or cancelled).
        Strictly enforces tenant ownership and prevents duplicate execution replay via atomic SQL UPDATE.
        """
        values: Dict[str, Any] = {"status": new_status}
        if execution_reference:
            values["execution_reference"] = execution_reference
        if new_status == "executed":
            values["executed_at"] = utcnow()

        stmt = (
            update(PendingAction)
            .where(
                PendingAction.id == action_id,
                PendingAction.business_id == business_id,
                PendingAction.status == "pending_confirmation",
            )
            .values(**values)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return (result.rowcount or 0) > 0

    def set_execution_reference(
        self,
        business_id: str,
        action_id: str,
        execution_reference: str,
    ) -> bool:
        """Record external execution reference on an executed action record."""
        stmt = (
            update(PendingAction)
            .where(
                PendingAction.id == action_id,
                PendingAction.business_id == business_id,
            )
            .values(execution_reference=execution_reference)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return (result.rowcount or 0) > 0

    def cancel_all_pending(self, business_id: str) -> int:
        """Cancel all pending confirmation actions for a tenant."""
        stmt = (
            select(PendingAction)
            .where(
                PendingAction.business_id == business_id,
                PendingAction.status == "pending_confirmation",
            )
        )
        actions = list(self.session.scalars(stmt).all())
        for a in actions:
            a.status = "cancelled"
        self.session.flush()
        return len(actions)
