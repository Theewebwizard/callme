"""
Business FAQ and Knowledge Base endpoints.
"""

from typing import List
from fastapi import APIRouter, HTTPException, status

from backend.api.schemas import FAQItem, FAQListUpdateRequest
from backend.database.service import get_database_service

router = APIRouter(prefix="/businesses/{business_id}/faqs", tags=["FAQs"])


@router.get("", response_model=List[FAQItem])
def list_faqs(business_id: str) -> List[FAQItem]:
    """Retrieve all frequently asked questions configured for a business tenant."""
    db_service = get_database_service()
    if not db_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unreachable.",
        )

    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    return [FAQItem(**faq) for faq in profile.get("faqs", [])]


@router.put("", response_model=List[FAQItem])
def update_faqs(
    business_id: str,
    faq_req: FAQListUpdateRequest,
) -> List[FAQItem]:
    """Atomically replace or update FAQs for a specific business tenant."""
    db_service = get_database_service()
    if not db_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unreachable.",
        )

    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    raw_faqs = [item.model_dump() for item in faq_req.faqs]
    saved_faqs = db_service.save_business_faqs(business_id, raw_faqs)
    return [FAQItem(**f) for f in saved_faqs]
