"""
Business tenant endpoints.
"""

import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from backend.api.schemas import (
    BusinessSummaryResponse,
    BusinessDetailResponse,
    BusinessUpdateRequest,
    BusinessCreateRequest,
    BusinessLoginRequest,
    GoogleAuthRequest,
)
from backend.database.service import get_database_service
from backend.auth import (
    create_access_token,
    verify_business_access,
    verify_admin_key,
    get_current_principal,
    AuthenticatedPrincipal,
    ROLE_BUSINESS_OWNER,
    hash_password,
)

router = APIRouter(prefix="/businesses", tags=["Businesses"])


@router.get("", response_model=List[BusinessSummaryResponse])
def list_businesses(
    principal: AuthenticatedPrincipal = Depends(verify_admin_key),
) -> List[BusinessSummaryResponse]:
    """Retrieve list of all registered business tenants (platform admin only)."""
    db_service = get_database_service()
    all_businesses = db_service.get_all_businesses()
    summaries = []
    for b_id, b_data in all_businesses.items():
        summaries.append(
            BusinessSummaryResponse(
                id=b_id,
                name=b_data["name"],
                industry=b_data["industry"],
                phone_number=b_data.get("phone_number", ""),
                assigned_number_status=b_data.get("assigned_number_status", "Active & Connected"),
                opening_time=b_data["opening_time"],
                closing_time=b_data["closing_time"],
                timezone=b_data["timezone"],
            )
        )
    return summaries


class BusinessAccessRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=100, description="Business name, slug ID, or phone number")


@router.post("/login")
def login_business(req: BusinessLoginRequest) -> Dict[str, Any]:
    """Sign in to a business tenant workspace using Gmail ID and password."""
    db_service = get_database_service()
    profile = db_service.authenticate_business(req.email, req.password)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Gmail ID or password. Please check your credentials.",
        )

    token = create_access_token({
        "sub": profile["id"],
        "role": ROLE_BUSINESS_OWNER,
        "email": profile.get("owner_email") or req.email.strip().lower(),
        "name": profile.get("name"),
    })

    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "business": profile,
        "message": f"Welcome back, {profile['name']}!",
    }


@router.post("/access")
def access_business(req: BusinessAccessRequest) -> Dict[str, Any]:
    """Find and verify business tenant workspace access by name, ID, or phone number."""
    db_service = get_database_service()
    query = req.identifier.strip().lower()
    all_b = db_service.get_all_businesses()

    matched_b = None
    # 1. Exact ID
    if req.identifier.strip() in all_b:
        matched_b = all_b[req.identifier.strip()]
    else:
        # 2. Case-insensitive Name or ID or Phone or Email
        clean_q = query.replace(" ", "").replace("+", "").replace("-", "")
        for b_id, b in all_b.items():
            clean_phone = (b.get("phone_number") or "").replace(" ", "").replace("+", "").replace("-", "")
            clean_email = (b.get("owner_email") or "").strip().lower()
            if (
                b_id.lower() == query
                or b["name"].lower() == query
                or (clean_q and clean_q in clean_phone)
                or (query and query == clean_email)
            ):
                matched_b = b
                break

    if not matched_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No business found matching '{req.identifier.strip()}'. Check spelling or create your receptionist.",
        )

    token = create_access_token({
        "sub": matched_b["id"],
        "role": ROLE_BUSINESS_OWNER,
        "email": matched_b.get("owner_email") or "",
        "name": matched_b["name"],
    })
    return {
        "id": matched_b["id"],
        "name": matched_b["name"],
        "industry": matched_b["industry"],
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/refresh")
def refresh_token(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> Dict[str, Any]:
    """
    Refresh an active JWT token.
    Issues a fresh token with updated expiration for prolonged receptionist shifts.
    """
    new_token = create_access_token({
        "sub": principal.id or principal.business_id,
        "role": principal.role,
        "business_id": principal.business_id,
        "email": principal.email or "",
    })
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "business_id": principal.business_id,
        "expires_in": 3600,
    }


def get_default_tools_for_industry(industry: Optional[str]) -> Dict[str, bool]:
    """Return default tool activation map tailored to the business industry."""
    from backend.tools.registry import get_tool_registry
    registry = get_tool_registry()
    allowed = registry.get_tools_for_industry(industry or "Other")
    return {t.id: True for t in allowed}


@router.post("/google-auth")
def google_auth(req: GoogleAuthRequest) -> Dict[str, Any]:
    """Authenticate via Google / Gmail account for business tenant workspace."""
    db_service = get_database_service()
    clean_email = req.email.strip().lower()

    # 1. Check if business exists with this owner_email
    biz = db_service.get_business_by_email(clean_email)
    if biz:
        token = create_access_token({
            "sub": biz["id"],
            "role": ROLE_BUSINESS_OWNER,
            "email": clean_email,
            "name": biz.get("name"),
        })
        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "business": biz,
            "is_new": False,
            "message": f"Welcome back, {biz['name']}!",
        }

    # Also check if any business has an exact owner_email match in memory
    all_b = db_service.get_all_businesses()
    for b_id, b in all_b.items():
        if (b.get("owner_email") or "").strip().lower() == clean_email:
            full = db_service.get_business_profile(b_id)
            if full:
                token = create_access_token({
                    "sub": full["id"],
                    "role": ROLE_BUSINESS_OWNER,
                    "email": clean_email,
                    "name": full.get("name"),
                })
                return {
                    "success": True,
                    "access_token": token,
                    "token_type": "bearer",
                    "business": full,
                    "is_new": False,
                    "message": f"Welcome back, {full['name']}!",
                }

    # 2. If not found and not create_if_missing:
    if not req.create_if_missing:
        return {
            "success": False,
            "found": False,
            "email": clean_email,
            "name": req.name or clean_email.split("@")[0].title(),
            "message": f"No receptionist workspace found for {clean_email}. Register your business to get started.",
        }

    # 3. Auto-provision / register business linked to this Gmail
    b_name = req.business_name.strip() if req.business_name and req.business_name.strip() else f"{(req.name or clean_email.split('@')[0]).strip().title()}'s Business"
    cleaned_slug = re.sub(r"[^a-zA-Z0-9]+", "_", b_name.lower()).strip("_")
    slug_id = f"biz_{cleaned_slug}"
    if slug_id in all_b:
        import random
        slug_id = f"{slug_id}_{random.randint(100, 999)}"

    greeting = req.greeting_message or f"Namaste! Welcome to {b_name}. I am your virtual receptionist. How can I assist you today?"
    new_data = {
        "id": slug_id,
        "name": b_name,
        "industry": req.industry or "Restaurant",
        "description": f"AI Receptionist managed by {req.name or clean_email}.",
        "phone_number": req.phone_number or "+91 96969 67307",
        "assigned_number_status": "Active & Connected",
        "opening_time": "09:00",
        "closing_time": "21:00",
        "timezone": "Asia/Kolkata",
        "greeting_message": greeting,
        "languages": ["English", "Hindi"],
        "transfer_instructions": "Transfer to human agent if caller asks for manager or emergency attention.",
        "owner_email": clean_email,
        "owner_name": req.name or "",
    }

    db_service.create_business(new_data)

    # Initialize tools tailored to industry
    tools_to_enable = get_default_tools_for_industry(req.industry)
    if req.enabled_tools:
        tools_to_enable.update(req.enabled_tools)
    for t_id, en in tools_to_enable.items():
        db_service.set_tool_status(slug_id, t_id, en)

    created_profile = db_service.get_business_profile(slug_id)
    token = create_access_token({
        "sub": slug_id,
        "role": ROLE_BUSINESS_OWNER,
        "email": clean_email,
        "name": b_name,
    })
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "business": created_profile,
        "is_new": True,
        "message": f"Successfully created your receptionist workspace for {b_name}!",
    }


@router.get("/{business_id}", response_model=BusinessDetailResponse)
def get_business(
    business_id: str,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> BusinessDetailResponse:
    """Retrieve complete profile configuration and FAQs for a specific business."""
    db_service = get_database_service()
    profile = db_service.get_business_profile(business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    return BusinessDetailResponse(**profile)


@router.put("/{business_id}", response_model=BusinessDetailResponse)
def update_business(
    business_id: str,
    update_req: BusinessUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> BusinessDetailResponse:
    """
    Update permitted business profile fields.
    Does not permit modifying immutable tenant identifiers.
    """
    db_service = get_database_service()
    # Check existence
    existing = db_service.get_business_profile(business_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    update_dict = update_req.model_dump(exclude_unset=True)
    if "faqs" in update_dict and update_dict["faqs"] is not None:
        update_dict["faqs"] = [
            f.model_dump() if hasattr(f, "model_dump") else f for f in update_dict["faqs"]
        ]

    updated = db_service.save_business_profile(business_id, update_dict)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update business configuration.",
        )

    return BusinessDetailResponse(**updated)


@router.post("", response_model=BusinessDetailResponse, status_code=status.HTTP_201_CREATED)
def create_business(create_req: BusinessCreateRequest) -> BusinessDetailResponse:
    """
    Register a new business tenant with initial profile, FAQs, and enabled tools.
    """
    db_service = get_database_service()
    # 1. Determine or generate tenant slug/ID
    if create_req.id and create_req.id.strip():
        biz_id = create_req.id.strip()
    else:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", create_req.name.lower()).strip("_")
        biz_id = f"biz_{cleaned}" if not cleaned.startswith("biz_") else cleaned

    # Check for conflict
    existing = db_service.get_business_profile(biz_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Business tenant with ID '{biz_id}' already exists.",
        )

    # 2. Extract profile fields
    pwd_hash = None
    if create_req.password and create_req.password.strip():
        from backend.auth import hash_password
        pwd_hash = hash_password(create_req.password.strip())

    data = {
        "id": biz_id,
        "name": create_req.name.strip(),
        "industry": create_req.industry or "Other",
        "description": create_req.description or "",
        "phone_number": create_req.phone_number or "",
        "assigned_number_status": create_req.assigned_number_status or "Active & Connected",
        "opening_time": create_req.opening_time or "09:00",
        "closing_time": create_req.closing_time or "21:00",
        "timezone": create_req.timezone or "Asia/Kolkata",
        "greeting_message": create_req.greeting_message or f"Hello! Welcome to {create_req.name.strip()}. How can I assist you today?",
        "languages": create_req.languages or ["English", "Hindi"],
        "transfer_instructions": create_req.transfer_instructions or "Transfer to human agent if caller explicitly requests operator assistance or discusses complex matters.",
        "owner_email": (create_req.owner_email or "").strip().lower(),
        "owner_name": create_req.owner_name or "",
        "password_hash": pwd_hash,
    }

    try:
        db_service.create_business(data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create business record: {e}",
        )

    # 3. Configure initial FAQs if provided
    if create_req.faqs:
        faq_dicts = [
            f.model_dump() if hasattr(f, "model_dump") else f for f in create_req.faqs
        ]
        db_service.save_business_faqs(biz_id, faq_dicts)

    # 4. Configure default tools tailored to industry and specified tools
    default_tools = get_default_tools_for_industry(create_req.industry)
    if create_req.enabled_tools:
        default_tools.update(create_req.enabled_tools)

    for tool_id, is_enabled in default_tools.items():
        db_service.set_tool_status(biz_id, tool_id, is_enabled)

    created_profile = db_service.get_business_profile(biz_id)
    if not created_profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve registered business profile.",
        )

    token = create_access_token({
        "sub": biz_id,
        "role": ROLE_BUSINESS_OWNER,
        "email": data["owner_email"],
        "name": data["name"],
    })
    created_profile["access_token"] = token
    created_profile["token_type"] = "bearer"

    return BusinessDetailResponse(**created_profile)


@router.delete("/{business_id}")
def delete_business(
    business_id: str,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """
    Delete a business tenant and cascade delete all associated records
    (FAQs, tool configs, call records, conversation messages, pending actions, voice sessions).
    """
    db_service = get_database_service()
    existing = db_service.get_business_profile(business_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )

    deleted = db_service.delete_business(business_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete business tenant '{business_id}'.",
        )

    return {
        "success": True,
        "business_id": business_id,
        "message": f"Business tenant '{business_id}' and all associated records deleted successfully.",
    }
