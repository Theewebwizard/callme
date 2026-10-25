"""
Repository for Phase B Pending Actions requiring human confirmation.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

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
        """Fetch pending action by ID."""
        return self.session.get(PendingAction, action_id)

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
        Strictly enforces tenant ownership and prevents duplicate execution replay.
        """
        action = self.get(action_id)
        if not action:
            return False
        if action.business_id != business_id:
            return False
        if action.status != "pending_confirmation":
            return False  # Already executed, cancelled, or expired

        action.status = new_status
        if execution_reference:
            action.execution_reference = execution_reference
        if new_status == "executed":
            action.executed_at = utcnow()

        self.session.flush()
        return True

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
