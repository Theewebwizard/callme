"""
Repository for Call History Records.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func

from backend.database.models import CallRecord, utcnow
from backend.database.repositories.base import BaseRepository


class CallRepository(BaseRepository):
    """Repository handling call history auditing, logging, and metrics."""

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
        timestamp: Optional[datetime] = None,
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> CallRecord:
        """Create and persist a call audit record."""
        # Format duration string if not supplied
        fmt = duration_formatted or f"{duration_seconds // 60}m {duration_seconds % 60:02d}s"

        call = CallRecord(
            id=call_id or f"call_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
            timestamp=timestamp or utcnow(),
            caller_number=caller_number,
            duration_seconds=duration_seconds,
            duration_formatted=fmt,
            outcome=outcome,
            summary=summary,
            tools_used=tools_used or [],
            transcript=transcript or [],
            is_simulated=is_simulated,
        )
        self.session.add(call)
        self.session.flush()
        return call

    def count_for_business(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
    ) -> int:
        """Return total count of call records matching filters."""
        stmt = select(func.count(CallRecord.id)).where(CallRecord.business_id == business_id)
        if outcome_filter and outcome_filter != "All Outcomes":
            stmt = stmt.where(CallRecord.outcome == outcome_filter)
        return self.session.scalar(stmt) or 0

    def list_for_business(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CallRecord]:
        """Fetch call records for a business tenant with optional outcome filtering and offset pagination."""
        stmt = (
            select(CallRecord)
            .where(CallRecord.business_id == business_id)
            .order_by(desc(CallRecord.timestamp))
            .offset(offset)
            .limit(limit)
        )
        if outcome_filter and outcome_filter != "All Outcomes":
            stmt = stmt.where(CallRecord.outcome == outcome_filter)

        return list(self.session.scalars(stmt).all())

    def list_dicts_for_business(
        self,
        business_id: str,
        outcome_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return list of call dictionaries for UI display."""
        records = self.list_for_business(
            business_id=business_id,
            outcome_filter=outcome_filter,
            limit=limit,
            offset=offset,
        )
        return [r.to_dict() for r in records]

    def get_stats_for_business(self, business_id: str) -> Dict[str, Any]:
        """Compute summary analytics for dashboard display."""
        calls = self.list_for_business(business_id=business_id, limit=500)
        total_calls = len(calls)
        bookings = sum(1 for c in calls if "Booking" in c.outcome or "Completed" in c.outcome)
        escalated = sum(1 for c in calls if "Transferred" in c.outcome or "Escalated" in c.outcome)
        avg_secs = (sum(c.duration_seconds for c in calls) // total_calls) if total_calls > 0 else 0
        avg_fmt = f"{avg_secs // 60}m {avg_secs % 60:02d}s"

        return {
            "active_status": "Active",
            "total_calls": total_calls,
            "bookings_completed": bookings,
            "escalated_calls": escalated,
            "avg_duration": avg_fmt,
        }
