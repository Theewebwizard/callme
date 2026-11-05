"""
Business Tool Configuration endpoints.
"""

from typing import List, Dict
from fastapi import APIRouter, HTTPException, status, Depends

from backend.auth import verify_business_access
from backend.api.schemas import (
    BusinessToolsResponse,
    ToolItemResponse,
    ToolStatusUpdateRequest,
    ToolDemandCreateRequest,
    ToolDemandResponse,
)
from backend.database.service import get_database_service
from backend.tools.registry import get_tool_registry

router = APIRouter(
    prefix="/businesses/{business_id}/tools",
    tags=["Tools"],
    dependencies=[Depends(verify_business_access)],
)


@router.get("", response_model=BusinessToolsResponse)
def get_business_tools(business_id: str) -> BusinessToolsResponse:
    """
    Retrieve tool catalog and activation statuses filtered strictly
    by the business tenant's industry category.
    """
    db_service = get_database_service()
    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    biz_industry = profile.get("industry") or "Other"
    enabled_map = profile.get("enabled_tools", {})
    registry = get_tool_registry()

    # Retrieve only tools authorized for this business's industry type
    industry_tools = registry.get_tools_for_industry(biz_industry)
    allowed_ids = {t.id for t in industry_tools}

    # Filter enabled map strictly to authorized tools for this industry
    filtered_enabled_map = {k: bool(v) for k, v in enabled_map.items() if k in allowed_ids}

    tool_items = []
    for tool_def in industry_tools:
        t_id = tool_def.id
        tool_items.append(
            ToolItemResponse(
                id=t_id,
                name=tool_def.name,
                description=tool_def.description,
                category=tool_def.category.value if hasattr(tool_def.category, "value") else str(tool_def.category),
                icon=getattr(tool_def, "icon", "🔧"),
                is_enabled=filtered_enabled_map.get(t_id, False),
                allowed_industries=tool_def.allowed_industries,
                is_industry_compatible=True,
                is_implemented=getattr(tool_def, "is_implemented", True),
            )
        )

    return BusinessToolsResponse(
        business_id=business_id,
        industry=biz_industry,
        tools=tool_items,
        enabled_tools=filtered_enabled_map,
        total_available=len(tool_items),
    )


@router.put("", response_model=BusinessToolsResponse)
def update_business_tools(
    business_id: str,
    update_req: ToolStatusUpdateRequest,
) -> BusinessToolsResponse:
    """
    Update enabled/disabled statuses for canonical tools.
    Validates that the tenant only activates tools allowed for their industry.
    Safely disables or ignores disallowed/foreign tools rather than blocking requests.
    """
    db_service = get_database_service()
    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    biz_industry = profile.get("industry") or "Other"
    registry = get_tool_registry()
    allowed_tools = {t.id: t for t in registry.get_tools_for_industry(biz_industry)}

    for tool_id, is_enabled in update_req.tool_statuses.items():
        if tool_id in allowed_tools:
            db_service.set_tool_status(business_id, tool_id, bool(is_enabled))
            if not is_enabled:
                # Also deactivate capability configuration state when toggled off
                try:
                    db_service.set_tool_capability(business_id=business_id, tool_id=tool_id, is_enabled=False)
                except Exception:
                    pass
        else:
            # If a tool belongs to another industry, ensure it is turned off for this tenant
            db_service.set_tool_status(business_id, tool_id, False)
            try:
                db_service.set_tool_capability(business_id=business_id, tool_id=tool_id, is_enabled=False)
            except Exception:
                pass

    return get_business_tools(business_id)


@router.get("/demands", response_model=List[ToolDemandResponse])
def list_tool_demands(business_id: str) -> List[ToolDemandResponse]:
    """Retrieve all custom tool features demanded by a business tenant."""
    db_service = get_database_service()
    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    demands = db_service.list_tool_demands(business_id)
    return [ToolDemandResponse(**d) for d in demands]


@router.post("/demands", response_model=ToolDemandResponse, status_code=status.HTTP_201_CREATED)
def create_tool_demand(
    business_id: str,
    req: ToolDemandCreateRequest,
) -> ToolDemandResponse:
    """Submit a new custom tool or integration feature request for a business receptionist."""
    db_service = get_database_service()
    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    demand_dict = db_service.create_tool_demand(business_id, req.model_dump())
    return ToolDemandResponse(**demand_dict)
