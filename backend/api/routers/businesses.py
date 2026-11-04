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


# -------------------------------------------------------------
# Restaurant Menu Management & Upload Endpoints
# -------------------------------------------------------------

class MenuItemPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., ge=0)
    currency: str = Field("INR", max_length=10)
    description: Optional[str] = Field(None, max_length=1000)
    dietary_tags: Optional[List[str]] = Field(default_factory=list)
    spice_level: Optional[str] = Field("medium", max_length=50)
    is_available: bool = True


class MenuUploadRequest(BaseModel):
    items: List[MenuItemPayload] = Field(..., min_length=1)
    replace: bool = Field(True, description="When true, replaces all existing items. When false, appends new items.")


@router.get("/{business_id}/menu")
def get_business_menu(
    business_id: str,
    category: Optional[str] = None,
    only_available: bool = False,
) -> Dict[str, Any]:
    """Retrieve full menu items for a business tenant."""
    db_service = get_database_service()
    if not db_service.business_exists(business_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )
    items = db_service.list_menu_items(business_id, category=category, only_available=only_available)
    return {
        "success": True,
        "business_id": business_id,
        "count": len(items),
        "items": items,
    }


@router.post("/{business_id}/menu/upload")
def upload_business_menu(
    business_id: str,
    req: MenuUploadRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Upload and persist structured restaurant menu items with semantic search tags."""
    db_service = get_database_service()
    if not db_service.business_exists(business_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )
    item_dicts = [item.model_dump() for item in req.items]
    persisted = db_service.upload_menu_items(business_id, item_dicts, replace=req.replace)
    return {
        "success": True,
        "business_id": business_id,
        "count": len(persisted),
        "message": f"Successfully {'replaced' if req.replace else 'added'} {len(persisted)} menu items for business '{business_id}'.",
        "items": persisted,
    }


@router.delete("/{business_id}/menu/{item_id}")
def delete_business_menu_item(
    business_id: str,
    item_id: str,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Delete a specific menu item."""
    db_service = get_database_service()
    deleted = db_service.delete_menu_item(business_id, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item '{item_id}' not found for business '{business_id}'.",
        )
    return {
        "success": True,
        "message": f"Menu item '{item_id}' successfully deleted.",
    }


@router.post("/{business_id}/menu/search")
def search_business_menu(
    business_id: str,
    query: str,
    category: Optional[str] = None,
    dietary_preference: Optional[str] = None,
    max_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """Semantically search menu items (useful for testing or UI search bar)."""
    db_service = get_database_service()
    results = db_service.search_menu_items_semantic(
        business_id=business_id,
        query=query,
        category=category,
        dietary_preference=dietary_preference,
        max_budget=max_budget,
    )
    return {
        "success": True,
        "business_id": business_id,
        "query": query,
        "count": len(results),
        "items": results,
    }


class ParseMenuTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    default_category: Optional[str] = "Mains"


@router.post("/{business_id}/menu/parse-text")
def parse_menu_text(
    business_id: str,
    req: ParseMenuTextRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """
    Parse unstructured or pasted menu text into structured dish objects with categories and prices.
    Enables restaurant owners to paste their menu directly without typing code.
    """
    lines = req.text.strip().splitlines()
    current_category = req.default_category or "Mains"
    parsed_items = []

    category_headers = {
        "starter": "Starters", "starters": "Starters", "appetizer": "Starters", "appetizers": "Starters", "snacks": "Starters",
        "main": "Mains", "mains": "Mains", "main course": "Mains", "curries": "Mains", "gravies": "Mains", "dal": "Mains",
        "bread": "Breads", "breads": "Breads", "rotis": "Breads", "naans": "Breads",
        "dessert": "Desserts", "desserts": "Desserts", "sweets": "Desserts", "mithai": "Desserts",
        "beverage": "Beverages", "beverages": "Beverages", "drinks": "Beverages", "shakes": "Beverages",
    }

    price_pattern = re.compile(r'(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d{1,2})?)\s*(?:/-)?', re.IGNORECASE)

    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue

        # Check if line is a category header
        clean_header = re.sub(r'[:\-_#\*\(\)]', '', raw_line).strip().lower()
        if clean_header in category_headers:
            current_category = category_headers[clean_header]
            continue

        # Look for price at the end or inside line
        matches = list(price_pattern.finditer(raw_line))
        if not matches:
            continue

        # Pick the most plausible price match (usually the last numeric figure)
        price_match = matches[-1]
        try:
            price_val = float(price_match.group(1))
        except (ValueError, TypeError):
            continue

        # Dish name is the text outside the price
        start_idx, end_idx = price_match.span()
        name_part = (raw_line[:start_idx] + " " + raw_line[end_idx:]).strip()
        name_part = re.sub(r'[\-–—:\.\(\)]+$', '', name_part).strip()
        name_part = re.sub(r'^[\-–—:\.\*\#]+', '', name_part).strip()

        if len(name_part) < 2:
            continue

        # Extract optional description if inside parentheses
        desc = ""
        desc_match = re.search(r'\((.*?)\)', name_part)
        if desc_match:
            desc = desc_match.group(1).strip()
            name_part = re.sub(r'\(.*?\)', '', name_part).strip()

        name_part = re.sub(r'[\-–—:\.\s]+$', '', name_part).strip()
        name_part = re.sub(r'^[\-–—:\.\*\#\s]+', '', name_part).strip()

        # Deduce category from dish keywords if not in specific header
        cat = current_category
        nl = name_part.lower()
        if any(w in nl for w in ["naan", "roti", "paratha", "kulcha", "chapati", "phulka"]):
            cat = "Breads"
        elif any(w in nl for w in ["jamun", "kulfi", "rasmalai", "halwa", "kheer", "ice cream", "pudding", "cake"]):
            cat = "Desserts"
        elif any(w in nl for w in ["lassi", "chaas", "soda", "juice", "tea", "chai", "coffee", "shake", "mojito", "water"]):
            cat = "Beverages"
        elif any(w in nl for w in ["tikka", "kabab", "corn", "pakoda", "roll", "soup", "chaat", "manchurian"]):
            cat = "Starters"

        # Deduce dietary tags
        tags = []
        if any(w in nl or w in desc.lower() for w in ["chicken", "mutton", "fish", "egg", "murgh", "meat", "prawn"]):
            tags.append("non-vegetarian")
        else:
            tags.append("vegetarian")

        if any(w in nl or w in desc.lower() for w in ["vegan", "dairy-free"]):
            tags.append("vegan")
        if any(w in nl or w in desc.lower() for w in ["gluten-free", "gluten free"]):
            tags.append("gluten-free")
        if any(w in nl or w in desc.lower() for w in ["jain"]):
            tags.append("jain-available")

        parsed_items.append({
            "name": name_part,
            "category": cat,
            "price": price_val,
            "currency": "INR",
            "description": desc or None,
            "dietary_tags": tags,
            "spice_level": "spicy" if "spicy" in desc.lower() else ("mild" if "mild" in desc.lower() else "medium"),
            "is_available": True,
        })

    return {
        "success": True,
        "count": len(parsed_items),
        "items": parsed_items,
    }


# =============================================================================
# Hotel Room Types & Rate Card Endpoints (Hospitality Domain)
# =============================================================================

class RoomTypePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    base_price: float = Field(..., ge=0)
    weekend_price: Optional[float] = Field(None, ge=0)
    currency: str = Field("INR", max_length=10)
    description: Optional[str] = Field(None, max_length=1000)
    bed_type: Optional[str] = Field("1 King Bed", max_length=100)
    max_occupancy: int = Field(2, ge=1, le=20)
    max_adults: int = Field(2, ge=1, le=20)
    max_children: int = Field(1, ge=0, le=10)
    amenities: Optional[List[str]] = Field(default_factory=list)
    inclusions: Optional[List[str]] = Field(default_factory=list)
    check_in_time: Optional[str] = Field("14:00", max_length=10)
    check_out_time: Optional[str] = Field("11:00", max_length=10)
    cancellation_policy: Optional[str] = Field("Free cancellation up to 48 hours prior to arrival", max_length=255)
    is_available: bool = True


class RoomUploadRequest(BaseModel):
    items: List[RoomTypePayload] = Field(..., min_length=1)
    replace: bool = Field(True, description="When true, replaces all existing rooms. When false, appends new rooms.")


@router.get("/{business_id}/rooms")
def get_business_rooms(
    business_id: str,
    category: Optional[str] = None,
    only_available: bool = False,
) -> Dict[str, Any]:
    """Retrieve full room types and rate cards for a hotel tenant."""
    db_service = get_database_service()
    if not db_service.business_exists(business_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )
    items = db_service.list_room_types(business_id, category=category, only_available=only_available)
    return {
        "success": True,
        "business_id": business_id,
        "count": len(items),
        "items": items,
    }


@router.post("/{business_id}/rooms/upload")
def upload_business_rooms(
    business_id: str,
    req: RoomUploadRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Upload and persist structured hotel room types with rate cards and amenities."""
    db_service = get_database_service()
    if not db_service.business_exists(business_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business tenant '{business_id}' not found.",
        )
    item_dicts = [item.model_dump() for item in req.items]
    persisted = db_service.upload_room_types(business_id, item_dicts, replace=req.replace)
    return {
        "success": True,
        "business_id": business_id,
        "count": len(persisted),
        "message": f"Successfully {'replaced' if req.replace else 'added'} {len(persisted)} room types for business '{business_id}'.",
        "items": persisted,
    }


@router.delete("/{business_id}/rooms/{room_id}")
def delete_business_room_type(
    business_id: str,
    room_id: str,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Delete a specific room type from hotel rate card."""
    db_service = get_database_service()
    deleted = db_service.delete_room_type(business_id, room_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room type '{room_id}' not found for business '{business_id}'.",
        )
    return {
        "success": True,
        "message": f"Room type '{room_id}' successfully deleted.",
    }


@router.post("/{business_id}/rooms/search")
def search_business_rooms(
    business_id: str,
    query: str,
    category: Optional[str] = None,
    amenity_preference: Optional[str] = None,
    guests_count: Optional[int] = None,
    max_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """Semantically search hotel room types and rates."""
    db_service = get_database_service()
    results = db_service.search_room_types_semantic(
        business_id=business_id,
        query=query,
        category=category,
        amenity_preference=amenity_preference,
        guests_count=guests_count,
        max_budget_per_night=max_budget,
    )
    return {
        "success": True,
        "business_id": business_id,
        "query": query,
        "count": len(results),
        "items": results,
    }


class ParseRoomTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    default_category: Optional[str] = "Rooms"


@router.post("/{business_id}/rooms/parse-text")
def parse_room_text(
    business_id: str,
    req: ParseRoomTextRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """
    Parse unstructured or pasted hotel room brochure text into structured room objects.
    Enables hotel managers to paste their room descriptions and rate sheet directly.
    """
    lines = req.text.strip().splitlines()
    current_category = req.default_category or "Rooms"
    parsed_items = []

    for line in lines:
        raw_line = line.strip()
        if not raw_line or len(raw_line) < 3:
            continue

        # Check for category header (e.g. "[Suites]" or "--- Executive Villas ---")
        cat_header_match = re.match(r'^[#\-*=\[\s]*(Suites|Rooms|Villas|Penthouses|Cottages|Deluxe)[#\-*=\]\s]*$', raw_line, re.IGNORECASE)
        if cat_header_match:
            current_category = cat_header_match.group(1).title()
            continue

        # Regex for price detection
        matches = list(re.finditer(r'(?:₹|INR|Rs\.?|\$)\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(?:₹|INR|Rs\.?|\$|per\s*night|/\s*night)', raw_line, re.IGNORECASE))
        if not matches:
            continue

        price_match = matches[-1]
        raw_price_str = (price_match.group(1) or price_match.group(2) or "").replace(",", "")
        try:
            price_val = float(raw_price_str)
        except (ValueError, TypeError):
            continue

        start_idx, end_idx = price_match.span()
        name_part = (raw_line[:start_idx] + " " + raw_line[end_idx:]).strip()
        name_part = re.sub(r'[\-–—:\.\(\)]+$', '', name_part).strip()
        name_part = re.sub(r'^[\-–—:\.\*\#]+', '', name_part).strip()

        if len(name_part) < 2:
            continue

        desc = ""
        desc_match = re.search(r'\((.*?)\)', name_part)
        if desc_match:
            desc = desc_match.group(1).strip()
            name_part = re.sub(r'\(.*?\)', '', name_part).strip()

        name_part = re.sub(r'[\-–—:\.\s]+$', '', name_part).strip()
        name_part = re.sub(r'^[\-–—:\.\*\#\s]+', '', name_part).strip()

        cat = current_category
        nl = name_part.lower()
        if any(w in nl for w in ["suite", "penthouse"]):
            cat = "Suites"
        elif any(w in nl for w in ["villa", "cottage", "bungalow"]):
            cat = "Villas"
        elif any(w in nl for w in ["room", "deluxe", "superior", "standard"]):
            cat = "Rooms"

        amenities = []
        if any(w in nl or w in desc.lower() for w in ["ocean view", "sea view", "beach view"]):
            amenities.append("Ocean View")
        if any(w in nl or w in desc.lower() for w in ["balcony", "terrace", "deck"]):
            amenities.append("Balcony")
        if any(w in nl or w in desc.lower() for w in ["pool", "private pool", "plunge pool"]):
            amenities.append("Private Pool")
        if any(w in nl or w in desc.lower() for w in ["bathtub", "tub", "jacuzzi"]):
            amenities.append("Bathtub")
        if not amenities:
            amenities = ["Wi-Fi", "Air Conditioning", "En-suite Bathroom"]

        inclusions = []
        if any(w in nl or w in desc.lower() for w in ["breakfast", "bfast"]):
            inclusions.append("Breakfast Included")
        if any(w in nl or w in desc.lower() for w in ["transfer", "airport", "shuttle"]):
            inclusions.append("Airport Transfer")

        bed = "1 King Bed"
        if "twin" in nl or "twin" in desc.lower():
            bed = "2 Twin Beds"
        elif "queen" in nl or "queen" in desc.lower():
            bed = "1 Queen Bed"

        parsed_items.append({
            "name": name_part,
            "category": cat,
            "base_price": price_val,
            "weekend_price": price_val * 1.15,
            "currency": "INR",
            "description": desc or None,
            "bed_type": bed,
            "max_occupancy": 4 if cat in ("Suites", "Villas") else 2,
            "max_adults": 4 if cat in ("Suites", "Villas") else 2,
            "max_children": 2 if cat in ("Suites", "Villas") else 1,
            "amenities": amenities,
            "inclusions": inclusions or ["Wi-Fi Access"],
            "check_in_time": "14:00",
            "check_out_time": "11:00",
            "cancellation_policy": "Free cancellation up to 48 hours prior to arrival",
            "is_available": True,
        })

    return {
        "success": True,
        "count": len(parsed_items),
        "items": parsed_items,
    }



# =========================================================================
# Hotel Floor Layout & PMS Operations (OYO-Style Front-Desk)
# =========================================================================

class HotelBulkSetupRequest(BaseModel):
    floors_count: int = Field(default=3, ge=1, le=20)
    rooms_per_floor: int = Field(default=4, ge=1, le=50)
    starting_floor: int = Field(default=1, ge=0, le=10)
    room_type_id: Optional[str] = None
    replace_existing: bool = False


class RoomStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="'clean', 'dirty', or 'maintenance'")


class HotelCheckInRequest(BaseModel):
    customer_name: str = Field(..., min_length=2)
    customer_phone: str = Field(..., min_length=5)
    nights: int = Field(default=1, ge=1, le=60)
    party_size: int = Field(default=2, ge=1, le=10)
    notes: Optional[str] = None


@router.get("/{business_id}/hotel/floors")
def get_hotel_floors(
    business_id: str,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Retrieve full floor grid, room occupancy, and housekeeping statuses."""
    db_service = get_database_service()
    return db_service.get_hotel_floor_layout(business_id)


@router.post("/{business_id}/hotel/floors/bulk-setup")
def bulk_setup_hotel_floors(
    business_id: str,
    req: HotelBulkSetupRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Bulk setup property layout by floors and room numbers (OYO Onboarding Parity)."""
    db_service = get_database_service()
    return db_service.bulk_setup_hotel_floors(
        business_id=business_id,
        floors_count=req.floors_count,
        rooms_per_floor=req.rooms_per_floor,
        starting_floor=req.starting_floor,
        room_type_id=req.room_type_id,
        replace_existing=req.replace_existing,
    )


@router.put("/{business_id}/hotel/rooms/{resource_id}/status")
def update_hotel_room_status(
    business_id: str,
    resource_id: str,
    req: RoomStatusUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Update room operational status (clean, dirty, maintenance)."""
    db_service = get_database_service()
    try:
        updated = db_service.update_room_housekeeping_status(
            business_id=business_id,
            resource_id=resource_id,
            status=req.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room resource not found.")
    return updated


@router.post("/{business_id}/hotel/rooms/{resource_id}/check-in")
def hotel_check_in(
    business_id: str,
    resource_id: str,
    req: HotelCheckInRequest,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Perform front-desk guest check-in (Walk-in or Online)."""
    db_service = get_database_service()
    try:
        return db_service.hotel_check_in(
            business_id=business_id,
            resource_id=resource_id,
            customer_name=req.customer_name,
            customer_phone=req.customer_phone,
            nights=req.nights,
            party_size=req.party_size,
            notes=req.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{business_id}/hotel/rooms/{resource_id}/check-out")
def hotel_check_out(
    business_id: str,
    resource_id: str,
    principal: AuthenticatedPrincipal = Depends(verify_business_access),
) -> Dict[str, Any]:
    """Perform front-desk guest check-out and mark room dirty."""
    db_service = get_database_service()
    try:
        return db_service.hotel_check_out(
            business_id=business_id,
            resource_id=resource_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
