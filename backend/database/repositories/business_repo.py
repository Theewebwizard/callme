"""
Repository for Business tenant entities.
"""

from typing import Optional, List, Dict, Any
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from backend.database.models import Business, BusinessFAQ, BusinessToolConfig
from backend.database.repositories.base import BaseRepository
from backend.voice.utils import normalize_phone_number, mask_phone_number

logger = logging.getLogger(__name__)


class BusinessRepository(BaseRepository):
    """Repository handling business profile persistence and queries."""

    def get(self, business_id: str) -> Optional[Business]:
        """Fetch business model by primary key ID."""
        return self.session.get(Business, business_id)

    def exists(self, business_id: str) -> bool:
        """Check if business ID exists."""
        stmt = select(Business.id).where(Business.id == business_id)
        return self.session.scalar(stmt) is not None

    def get_by_phone_number(self, raw_phone: str) -> Optional[Business]:
        """
        Find a business tenant by inbound called phone number.
        Normalizes both the search query and stored phone numbers for resilient matching.
        Safely detects and handles ambiguous numbers shared across multiple tenants.
        """
        target = normalize_phone_number(raw_phone)
        if not target:
            return None

        # Scan registered businesses and compare normalized numbers (supports comma-separated aliases)
        all_businesses = self.list_all()
        matching = [
            b for b in all_businesses
            if b.phone_number and any(normalize_phone_number(num.strip()) == target for num in b.phone_number.split(","))
        ]

        if len(matching) == 1:
            return matching[0]
        elif len(matching) > 1:
            logger.warning(
                f"Ambiguous phone number mapping: {len(matching)} businesses share normalized number '{mask_phone_number(target)}'."
            )
            raise ValueError(f"Ambiguous phone number: {len(matching)} businesses share this number")

        return None

    def get_by_owner_email(self, raw_email: str) -> Optional[Business]:
        """Find a business tenant by owner email (case-insensitive)."""
        if not raw_email or not raw_email.strip():
            return None
        target = raw_email.strip().lower()
        stmt = select(Business).where(func.lower(Business.owner_email) == target).limit(1)
        return self.session.scalars(stmt).first()

    def get_raw_for_auth(self, email: str) -> Optional[Business]:
        """Fetch raw Business ORM object (with password_hash) by email for authentication.
        NEVER expose this via API — used only internally for auth logic."""
        return self.get_by_owner_email(email)

    def list_all(self) -> List[Business]:
        """Fetch all registered businesses ordered by name."""
        stmt = select(Business).order_by(Business.name)
        return list(self.session.scalars(stmt).all())

    def create(self, data: Dict[str, Any]) -> Business:
        """Create a new business record."""
        biz = Business(
            id=data["id"],
            name=data["name"],
            industry=data.get("industry", "Other"),
            description=data.get("description", ""),
            phone_number=data.get("phone_number", ""),
            assigned_number_status=data.get("assigned_number_status", "Active & Connected"),
            opening_time=data.get("opening_time", "09:00"),
            closing_time=data.get("closing_time", "22:00"),
            timezone=data.get("timezone", "Asia/Kolkata"),
            greeting_message=data.get("greeting_message", ""),
            languages=data.get("languages", ["English"]),
            transfer_instructions=data.get("transfer_instructions", ""),
            owner_email=data.get("owner_email", ""),
            owner_name=data.get("owner_name", ""),
            password_hash=data.get("password_hash"),
        )
        self.session.add(biz)
        self.session.flush()
        return biz

    def update(self, business_id: str, updates: Dict[str, Any]) -> Optional[Business]:
        """Update mutable fields of a business."""
        biz = self.get(business_id)
        if not biz:
            return None

        allowed_fields = {
            "name",
            "industry",
            "description",
            "phone_number",
            "assigned_number_status",
            "opening_time",
            "closing_time",
            "timezone",
            "greeting_message",
            "languages",
            "transfer_instructions",
            "owner_email",
            "owner_name",
            "password_hash",
        }
        for field, value in updates.items():
            if field in allowed_fields and hasattr(biz, field):
                setattr(biz, field, value)

        self.session.flush()
        return biz

    def delete(self, business_id: str) -> bool:
        """Delete a business and cascade delete related records."""
        biz = self.get(business_id)
        if not biz:
            return False
        self.session.delete(biz)
        self.session.flush()
        return True

    def get_full_profile(self, business_id: str) -> Optional[Dict[str, Any]]:
        """
        Assemble the complete business configuration dictionary expected by
        the LangGraph agent workflow, tool registry, and UI state.
        Includes loaded FAQs and enabled tools map.
        """
        from sqlalchemy.orm import joinedload
        stmt = (
            select(Business)
            .options(joinedload(Business.faqs), joinedload(Business.tool_configs))
            .where(Business.id == business_id)
            .limit(1)
        )
        biz = self.session.scalars(stmt).unique().first()
        if not biz:
            return None

        base_dict = biz.to_dict()

        # Gather FAQs
        faqs_list = [faq.to_dict() for faq in biz.faqs]
        base_dict["faqs"] = faqs_list

        # Gather enabled tools and capability configs
        tool_map = {tc.tool_id: tc.is_enabled for tc in biz.tool_configs}
        base_dict["enabled_tools"] = tool_map
        base_dict["tool_configs"] = {tc.tool_id: tc.to_dict() for tc in biz.tool_configs}

        # Attach default stats structure for prototype dashboards
        from backend.database.models import CallRecord
        from sqlalchemy import case
        stats_stmt = select(
            func.count(CallRecord.id).label("total_calls"),
            func.count(case((
                (CallRecord.outcome.ilike("%Booking%")) | (CallRecord.outcome.ilike("%Completed%")),
                CallRecord.id
            ))).label("completed"),
            func.count(case((
                CallRecord.outcome.ilike("%Transferred%"),
                CallRecord.id
            ))).label("escalated"),
        ).where(CallRecord.business_id == biz.id)
        stats_row = self.session.execute(stats_stmt).first()
        total_calls = stats_row[0] if stats_row else 0
        completed_bookings = stats_row[1] if stats_row else 0
        escalated = stats_row[2] if stats_row else 0

        base_dict["stats"] = {
            "active_status": "Active",
            "total_calls": total_calls,
            "bookings_completed": completed_bookings,
            "escalated_calls": escalated,
            "avg_duration": "1m 15s" if total_calls > 0 else "0m 00s",
        }

        return base_dict

    def list_all_full(self) -> Dict[str, Dict[str, Any]]:
        """Return full configuration dictionary for all businesses keyed by ID."""
        businesses = self.list_all()
        result = {}
        for b in businesses:
            full = self.get_full_profile(b.id)
            if full:
                result[b.id] = full
        return result
