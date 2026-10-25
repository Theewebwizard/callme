"""
Admin Command Center endpoints for platform operators.
Provides full platform visibility into all live agents, user info,
master canonical tools repository, and cross-tenant tool usage.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.database.service import get_database_service
from tools.registry import get_tool_registry
from ui.mock_data import INITIAL_TOOLS

router = APIRouter(prefix="/admin", tags=["Admin Command Center"])


class DemandStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Under Review, In Development, Ready, or Rejected")


@router.get("/overview")
def get_admin_overview() -> Dict[str, Any]:
    """
    Retrieve comprehensive platform overview: all registered agents,
    telemetry metrics, line statuses, and active tools.
    """
    db_service = get_database_service()
    if not db_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unreachable.",
        )

    all_businesses = db_service.get_all_businesses()
    demands = db_service.list_all_tool_demands()

    agents_list = []
    total_calls_handled = 0
    active_lines_count = 0

    for b_id, b_data in all_businesses.items():
        stats = b_data.get("stats", {})
        calls_count = stats.get("total_calls", 0)
        total_calls_handled += calls_count

        line_status = b_data.get("assigned_number_status", "Active & Connected")
        if "Active" in line_status:
            active_lines_count += 1

        agents_list.append({
            "id": b_id,
            "name": b_data["name"],
            "industry": b_data.get("industry", "Other"),
            "phone_number": b_data.get("phone_number", ""),
            "assigned_number_status": line_status,
            "opening_time": b_data.get("opening_time", "09:00"),
            "closing_time": b_data.get("closing_time", "21:00"),
            "timezone": b_data.get("timezone", "Asia/Kolkata"),
            "greeting_message": b_data.get("greeting_message", ""),
            "languages": b_data.get("languages", ["English"]),
            "transfer_instructions": b_data.get("transfer_instructions", ""),
            "stats": stats,
            "enabled_tools": b_data.get("enabled_tools", {}),
            "created_at": b_data.get("created_at"),
        })

    return {
        "total_agents": len(all_businesses),
        "total_calls": total_calls_handled,
        "active_phone_lines": active_lines_count,
        "total_demands": len(demands),
        "agents": agents_list,
    }


@router.get("/tools")
def get_admin_tool_repository() -> Dict[str, Any]:
    """
    Retrieve master canonical tools repository and cross-agent adoption analytics.
    Shows exactly which business agents are using which tools.
    """
    db_service = get_database_service()
    if not db_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unreachable.",
        )

    all_businesses = db_service.get_all_businesses()
    registry = get_tool_registry()
    canonical_tools = registry.list_tools()

    tools_report = []

    for tool_def in canonical_tools:
        t_id = tool_def.id
        meta = INITIAL_TOOLS.get(t_id, {})
        category = meta.get("category", tool_def.category.value.title())
        icon = meta.get("icon", "🔧")

        agent_usage = []
        active_for_count = 0

        for b_id, b_data in all_businesses.items():
            enabled_map = b_data.get("enabled_tools", {})
            is_enabled = enabled_map.get(t_id, False)
            if is_enabled:
                active_for_count += 1

            agent_usage.append({
                "business_id": b_id,
                "business_name": b_data["name"],
                "is_enabled": is_enabled,
            })

        tools_report.append({
            "id": t_id,
            "name": tool_def.name,
            "description": tool_def.description,
            "category": category,
            "icon": icon,
            "allowed_industries": tool_def.allowed_industries,
            "is_universal": "*" in tool_def.allowed_industries,
            "active_agents_count": active_for_count,
            "total_agents_count": len(all_businesses),
            "adoption_rate": f"{round((active_for_count / max(1, len(all_businesses))) * 100)}%",
            "agent_usage": agent_usage,
        })

    return {
        "total_canonical_tools": len(canonical_tools),
        "total_agents": len(all_businesses),
        "tools": tools_report,
    }


@router.get("/demands")
def get_admin_all_demands() -> List[Dict[str, Any]]:
    """Retrieve all custom tool and feature requests demanded by businesses."""
    db_service = get_database_service()
    if not db_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unreachable.",
        )

    all_businesses = db_service.get_all_businesses()
    demands = db_service.list_all_tool_demands()

    # Enrich with business name
    enriched = []
    for d in demands:
        b_id = d["business_id"]
        biz = all_businesses.get(b_id, {})
        d_copy = dict(d)
        d_copy["business_name"] = biz.get("name", b_id)
        d_copy["business_industry"] = biz.get("industry", "Other")
        enriched.append(d_copy)

    return enriched


@router.patch("/demands/{demand_id}")
def update_demand_status(demand_id: str, req: DemandStatusUpdateRequest) -> Dict[str, Any]:
    """Admin endpoint to update the review or deployment status of a custom tool demand."""
    db_service = get_database_service()
    if not db_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unreachable.",
        )

    updated = db_service.update_tool_demand_status(demand_id, req.status)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool demand '{demand_id}' not found.",
        )

    return updated
