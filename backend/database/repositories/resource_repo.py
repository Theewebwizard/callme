"""
Repository for Reservable Resources (dining tables, consultation rooms, etc.).
Provides authoritative resource inventory management for multi-tenant businesses.
"""

from typing import List, Optional, Dict, Any
import uuid
from sqlalchemy import select, and_, update, delete
from backend.database.models import ReservableResource, utcnow
from backend.database.repositories.base import BaseRepository


class ResourceRepository(BaseRepository):
    """Repository managing reservable asset inventory for tenants."""

    def list_resources(
        self,
        business_id: str,
        resource_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[ReservableResource]:
        """List resources for a business with optional filtering."""
        stmt = select(ReservableResource).where(ReservableResource.business_id == business_id)
        if resource_type:
            stmt = stmt.where(ReservableResource.resource_type == resource_type)
        if is_active is not None:
            stmt = stmt.where(ReservableResource.is_active == is_active)
        stmt = stmt.order_by(ReservableResource.name.asc())
        return list(self.session.scalars(stmt).all())

    def get_resource(self, resource_id: str, business_id: Optional[str] = None) -> Optional[ReservableResource]:
        """Fetch a resource by ID, optionally verifying tenant ownership."""
        stmt = select(ReservableResource).where(ReservableResource.id == resource_id)
        if business_id:
            stmt = stmt.where(ReservableResource.business_id == business_id)
        return self.session.scalar(stmt)

    def create_resource(
        self,
        business_id: str,
        name: str,
        capacity: int = 4,
        min_party_size: int = 1,
        max_party_size: int = 4,
        resource_type: str = "table",
        section: Optional[str] = None,
        is_active: bool = True,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> ReservableResource:
        """Create a new reservable resource."""
        res_id = f"res_{uuid.uuid4().hex[:12]}"
        now = utcnow()
        resource = ReservableResource(
            id=res_id,
            business_id=business_id,
            resource_type=resource_type,
            name=name.strip(),
            capacity=capacity,
            min_party_size=min_party_size,
            max_party_size=max_party_size,
            section=section.strip() if section else None,
            is_active=is_active,
            metadata_json=metadata_json or {},
            created_at=now,
            updated_at=now,
        )
        self.session.add(resource)
        self.session.flush()
        return resource

    def update_resource(
        self,
        business_id: str,
        resource_id: str,
        updates: Dict[str, Any],
    ) -> Optional[ReservableResource]:
        """Update an existing resource with tenant scoping."""
        resource = self.get_resource(resource_id, business_id=business_id)
        if not resource:
            return None

        updates_copy = dict(updates)
        if "metadata" in updates_copy and "metadata_json" not in updates_copy:
            updates_copy["metadata_json"] = updates_copy.pop("metadata")

        allowed_fields = {
            "name", "capacity", "min_party_size", "max_party_size",
            "section", "is_active", "metadata_json", "resource_type"
        }
        for field, val in updates_copy.items():
            if field in allowed_fields:
                setattr(resource, field, val)

        resource.updated_at = utcnow()
        self.session.flush()
        return resource

    def delete_resource(self, business_id: str, resource_id: str) -> bool:
        """Deactivate or remove a resource."""
        resource = self.get_resource(resource_id, business_id=business_id)
        if not resource:
            return False
        self.session.delete(resource)
        self.session.flush()
        return True
