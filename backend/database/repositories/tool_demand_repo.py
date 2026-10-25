"""
ToolDemand repository for managing custom tool and feature requests per business tenant.
"""

import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.database.models import ToolDemand


class ToolDemandRepository:
    """Repository managing tenant tool demand entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, business_id: str, data: Dict[str, Any]) -> ToolDemand:
        """Create a new custom tool demand record."""
        demand_id = f"dem_{uuid.uuid4().hex[:12]}"
        demand = ToolDemand(
            id=demand_id,
            business_id=business_id,
            tool_name=data["tool_name"],
            description=data["description"],
            category=data.get("category", "Custom Integration"),
            integration_target=data.get("integration_target", "Custom API"),
            priority=data.get("priority", "Important"),
            status=data.get("status", "Under Review"),
        )
        self.session.add(demand)
        self.session.flush()
        return demand

    def list_for_business(self, business_id: str) -> List[ToolDemand]:
        """List all tool demands for a specific business tenant."""
        return (
            self.session.query(ToolDemand)
            .filter(ToolDemand.business_id == business_id)
            .order_by(ToolDemand.created_at.desc())
            .all()
        )

    def list_dicts_for_business(self, business_id: str) -> List[Dict[str, Any]]:
        """List all tool demands as dictionaries."""
        demands = self.list_for_business(business_id)
        return [d.to_dict() for d in demands]

    def list_all_demands(self) -> List[Dict[str, Any]]:
        """List all tool demands across all businesses for platform administration."""
        demands = self.session.query(ToolDemand).order_by(ToolDemand.created_at.desc()).all()
        return [d.to_dict() for d in demands]

    def update_status(self, demand_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """Update review or development status of a tool demand."""
        demand = self.session.query(ToolDemand).filter(ToolDemand.id == demand_id).first()
        if not demand:
            return None
        demand.status = new_status
        self.session.flush()
        return demand.to_dict()
