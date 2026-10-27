"""
Tenant Tool Capability Setup Wizard and Resource Management Router.
Provides guided configuration, secret vaulting, validation, readiness checks,
and first-party resource inventory management.
"""

from typing import List, Dict, Any, Optional
import logging
from fastapi import APIRouter, HTTPException, status, Query

from backend.api.schemas import (
    StartSetupRequest,
    SaveStepRequest,
    ResourceCreateRequest,
    ResourceResponse,
    ReservationResponse,
)
from backend.capabilities.wizard import get_setup_wizard
from backend.capabilities.specs import get_capability_spec, list_all_capability_specs
from backend.capabilities.models import CapabilityStatus
from backend.integrations.resolver import resolve_tool_adapter
from backend.database.service import get_database_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/businesses/{business_id}", tags=["Capabilities & Setup Wizard"])


def _verify_tenant(business_id: str) -> Dict[str, Any]:
    """Verify tenant exists and return trusted profile."""
    db_service = get_database_service()
    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )
    return profile


# --- Capability Overview & Schema ---

@router.get("/capabilities")
def list_business_capabilities(business_id: str) -> List[Dict[str, Any]]:
    """List all available capabilities and their current operational readiness for a tenant."""
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    summaries = wizard.list_capabilities(business_id)
    return [s.model_dump() for s in summaries]


@router.get("/capabilities/{tool_id}/schema")
def get_capability_schema(business_id: str, tool_id: str) -> Dict[str, Any]:
    """Retrieve declarative setup fields, supported options, and instructions for a tool."""
    _verify_tenant(business_id)
    spec = get_capability_spec(tool_id)
    if not spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No capability specification found for tool '{tool_id}'.",
        )
    return spec.model_dump()


# --- Setup Wizard Session Lifecycle ---

@router.post("/capabilities/{tool_id}/setup/start")
def start_capability_setup(
    business_id: str,
    tool_id: str,
    req: StartSetupRequest,
) -> Dict[str, Any]:
    """Start or resume a guided setup session for a capability."""
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    session = wizard.start_setup_session(business_id, tool_id, req.option_id)
    return session


@router.post("/capabilities/{tool_id}/setup/save")
def save_setup_step(
    business_id: str,
    tool_id: str,
    req: SaveStepRequest,
) -> Dict[str, Any]:
    """
    Save validated step configuration or credentials.
    Secrets are automatically encrypted in the tenant credential vault.
    """
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    session = wizard.save_step(
        business_id=business_id,
        tool_id=tool_id,
        step_name=req.step_name,
        data=req.data,
        is_completed=req.is_completed,
    )
    return session


@router.post("/capabilities/{tool_id}/setup/validate")
def validate_capability_setup(
    business_id: str,
    tool_id: str,
) -> Dict[str, Any]:
    """Execute live connectivity and readiness validation for the setup session."""
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    report = wizard.validate_session(business_id=business_id, tool_id=tool_id)
    return report.model_dump()


@router.post("/capabilities/{tool_id}/activate")
def activate_capability(
    business_id: str,
    tool_id: str,
) -> Dict[str, Any]:
    """
    Promote a validated setup into an active, operational capability.
    Rejects activation if mandatory readiness checks have not passed.
    """
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    try:
        res = wizard.activate_capability(business_id, tool_id)
        return res
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.post("/capabilities/{tool_id}/deactivate")
def deactivate_capability(
    business_id: str,
    tool_id: str,
) -> Dict[str, Any]:
    """Deactivate a capability without clearing its configuration."""
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    res = wizard.deactivate_capability(business_id, tool_id)
    return res


@router.delete("/capabilities/{tool_id}/integration")
def disconnect_capability_integration(
    business_id: str,
    tool_id: str,
) -> Dict[str, Any]:
    """
    Disconnect provider integration, revoke/purge credentials from vault,
    and transition capability state to disconnected.
    """
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    res = wizard.disconnect_integration(business_id, tool_id)
    return res


@router.post("/capabilities/{tool_id}/test-connection")
def test_capability_connection(
    business_id: str,
    tool_id: str,
) -> Dict[str, Any]:
    """Probe connectivity for the tenant's configured provider."""
    _verify_tenant(business_id)
    adapter = resolve_tool_adapter(business_id, tool_id)
    conn_result = adapter.check_connection()
    perm_result = adapter.validate_permissions()
    return {
        "tool_id": tool_id,
        "authoritative_source": adapter.authoritative_source.value,
        "connection": conn_result,
        "permissions": perm_result,
    }


@router.get("/capabilities/{tool_id}/resources/discover")
def discover_capability_resources(
    business_id: str,
    tool_id: str,
    resource_type: str = Query("", description="Resource type to filter by (calendar, table, room, phone)"),
) -> List[Dict[str, Any]]:
    """Discover available external or internal resources through the configured adapter."""
    _verify_tenant(business_id)
    wizard = get_setup_wizard()
    return wizard.discover_resources(business_id, tool_id, resource_type=resource_type)


@router.get("/capabilities/{tool_id}/diagnostics")
def get_capability_diagnostics(
    business_id: str,
    tool_id: str,
) -> Dict[str, Any]:
    """Retrieve redacted operational diagnostic report for a tenant capability."""
    _verify_tenant(business_id)
    from backend.integrations.manager import IntegrationManager
    manager = IntegrationManager(db_service=get_database_service())
    report = manager.get_diagnostics(business_id, tool_id)
    return report.model_dump()



@router.get("/capabilities/audit-log")
def get_capability_audit_log(
    business_id: str,
    tool_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    """Retrieve tenant-scoped audit events for capability lifecycle actions."""
    _verify_tenant(business_id)
    db_service = get_database_service()
    return db_service.list_audit_events(business_id, tool_id=tool_id, limit=limit)


# --- Resource Inventory & Reservation Management ---

@router.get("/resources", response_model=List[ResourceResponse])
def list_resources(
    business_id: str,
    resource_type: Optional[str] = Query(None),
) -> List[ResourceResponse]:
    """List active reservable resources (tables, rooms, suites) for tenant."""
    _verify_tenant(business_id)
    db_service = get_database_service()
    resources = db_service.list_resources(business_id, resource_type=resource_type)
    return [ResourceResponse.model_validate(r) for r in resources]


@router.post("/resources", response_model=ResourceResponse)
def create_resource(
    business_id: str,
    req: ResourceCreateRequest,
) -> ResourceResponse:
    """Register a new reservable table or consultation room."""
    _verify_tenant(business_id)
    db_service = get_database_service()
    created = db_service.create_resource(
        business_id=business_id,
        name=req.name,
        capacity=req.capacity,
        min_party_size=req.min_party_size,
        max_party_size=req.max_party_size,
        resource_type=req.resource_type,
        section=req.section,
    )
    return ResourceResponse.model_validate(created)


@router.delete("/resources/{resource_id}")
def delete_resource(
    business_id: str,
    resource_id: str,
) -> Dict[str, Any]:
    """Deactivate or remove a reservable resource."""
    _verify_tenant(business_id)
    db_service = get_database_service()
    success = db_service.delete_resource(business_id, resource_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found.",
        )
    return {"success": True, "resource_id": resource_id, "deleted": True}


@router.get("/reservations", response_model=List[ReservationResponse])
def list_reservations(
    business_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ReservationResponse]:
    """List bookings and appointments committed to the authoritative store."""
    _verify_tenant(business_id)
    db_service = get_database_service()
    reservations = db_service.list_reservations(business_id, status=status_filter, limit=limit)
    return [ReservationResponse.model_validate(r) for r in reservations]


@router.delete("/reservations/{reservation_id}")
def cancel_reservation(
    business_id: str,
    reservation_id: str,
    phone: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Cancel a confirmed booking or appointment."""
    _verify_tenant(business_id)
    db_service = get_database_service()
    success = db_service.cancel_reservation(business_id, reservation_id, customer_phone=phone)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation '{reservation_id}' not found or already cancelled.",
        )
    return {"success": True, "reservation_id": reservation_id, "status": "cancelled"}
