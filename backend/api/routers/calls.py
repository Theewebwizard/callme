"""
Call History and Auditing endpoints.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status, Depends

from backend.auth import verify_business_access
from backend.api.schemas import CallHistoryResponse, CallRecordResponse
from backend.database.service import get_database_service

router = APIRouter(
    prefix="/businesses/{business_id}/calls",
    tags=["Call History"],
    dependencies=[Depends(verify_business_access)],
)


@router.get("", response_model=CallHistoryResponse)
def get_call_history(
    business_id: str,
    outcome: Optional[str] = Query(None, description="Filter by call outcome (e.g. 'Booking Completed')"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> CallHistoryResponse:
    """Retrieve audited call records for a business tenant with pagination and outcome filtering."""
    db_service = get_database_service()
    if not db_service.business_exists(business_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    outcome_filter = None if outcome in (None, "", "All Outcomes") else outcome
    paged_calls, total_count = db_service.get_call_history_and_count(
        business_id,
        outcome_filter=outcome_filter,
        limit=limit,
        offset=offset,
    )

    call_responses = [CallRecordResponse(**c) for c in paged_calls]

    return CallHistoryResponse(
        business_id=business_id,
        total=total_count,
        limit=limit,
        offset=offset,
        calls=call_responses,
    )
