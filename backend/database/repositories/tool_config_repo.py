"""
Repository for Business Tool Configuration.
"""

from typing import Dict, Any, Optional
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.database.models import BusinessToolConfig
from backend.database.repositories.base import BaseRepository


class ToolConfigRepository(BaseRepository):
    """Repository handling business tool activation settings."""

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

    def set_tool_status(
        self,
        business_id: str,
        tool_id: str,
        is_enabled: bool,
    ) -> BusinessToolConfig:
        """Insert or update tool activation status for a tenant."""
        stmt = (
            select(BusinessToolConfig)
            .where(
                BusinessToolConfig.business_id == business_id,
                BusinessToolConfig.tool_id == tool_id,
            )
        )
        record = self.session.scalar(stmt)
        if record:
            record.is_enabled = is_enabled
        else:
            record = BusinessToolConfig(
                id=f"tc_{uuid.uuid4().hex[:12]}",
                business_id=business_id,
                tool_id=tool_id,
                is_enabled=is_enabled,
            )
            self.session.add(record)

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
