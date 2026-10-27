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
                is_enabled=enabled_map.get(t_id, False),
                allowed_industries=tool_def.allowed_industries,
                is_industry_compatible=True,
                is_implemented=getattr(tool_def, "is_implemented", True),
            )
        )

    return BusinessToolsResponse(
        business_id=business_id,
        industry=biz_industry,
        tools=tool_items,
        enabled_tools=enabled_map,
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
    valid_tool_ids = set(registry._tools.keys())

    # 1. Validate tool IDs against canonical registry
    invalid_ids = [t_id for t_id in update_req.tool_statuses if t_id not in valid_tool_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tool ID(s): {', '.join(invalid_ids)}. Tools must belong to canonical registry.",
        )

    # 2. Enforce industry boundaries: cannot enable tools not allowed for tenant's industry
    allowed_tools = {t.id: t for t in registry.get_tools_for_industry(biz_industry)}
    disallowed_enables = [
        t_id for t_id, is_en in update_req.tool_statuses.items()
        if is_en and t_id not in allowed_tools
    ]
    if disallowed_enables:
        disallowed_names = [registry.get_tool(t).name for t in disallowed_enables if registry.get_tool(t)]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Tools {disallowed_names} cannot be enabled for a '{biz_industry}' business. "
                "These tools are restricted to other industry types."
            ),
        )

    for tool_id, is_enabled in update_req.tool_statuses.items():
        db_service.set_tool_status(business_id, tool_id, is_enabled)

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
