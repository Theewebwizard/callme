"""
Repository and semantic search engine for hotel room types and rate cards.
Supports multi-tenant persistence, bulk ingestion, amenity filtering,
capacity constraints, budget limits, and semantic intent retrieval.
Mirrors the structure and design of MenuItemRepository for hospitality domain parity.
"""

from typing import Optional, List, Dict, Any, Set
import re
import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.database.models import RoomType
from backend.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Category intents for lodging queries (multilingual Hindi/Hinglish & English)
ROOM_CATEGORY_SYNONYMS: Dict[str, Set[str]] = {
    "Suites": {
        "suite", "suites", "executive", "presidential", "penthouse", "luxury suite",
    },
    "Rooms": {
        "room", "rooms", "deluxe", "standard", "superior", "classic", "single",
        "double", "kamra", "kamre",
    },
    "Villas": {
        "villa", "villas", "cottage", "cottages", "beach house", "chalet", "bungalow",
        "private villa", "pool villa",
    },
    "Penthouses": {
        "penthouse", "penthouses", "rooftop suite", "sky suite",
    },
}

AMENITY_SYNONYMS: Dict[str, Set[str]] = {
    "ocean view": {"ocean view", "sea view", "beach view", "water view", "coastal view", "sea facing"},
    "garden view": {"garden view", "pool view", "nature view", "lawn view", "mountain view"},
    "balcony": {"balcony", "terrace", "deck", "veranda", "patio", "private balcony"},
    "bathtub": {"bathtub", "tub", "jacuzzi", "whirlpool", "soaking tub", "bath"},
    "wifi": {"wifi", "wi-fi", "internet", "high speed internet", "free wifi"},
    "pool": {"pool", "private pool", "swimming pool", "plunge pool", "pool access"},
    "mini-bar": {"mini-bar", "minibar", "fridge", "refrigerator"},
    "work desk": {"work desk", "desk", "office desk", "workstation"},
}

INCLUSION_SYNONYMS: Dict[str, Set[str]] = {
    "breakfast": {"breakfast", "bfast", "morning meal", "nashta", "complimentary breakfast", "free breakfast", "buffet breakfast"},
    "airport transfer": {"airport transfer", "airport pick up", "airport pickup", "airport drop", "shuttle", "cab", "airport limousine"},
    "spa access": {"spa access", "spa credit", "sauna", "steam room"},
    "parking": {"parking", "valet", "free parking", "car park"},
}

BED_SYNONYMS: Dict[str, Set[str]] = {
    "king": {"king", "king bed", "king size", "bada bed", "large bed"},
    "twin": {"twin", "twin beds", "two beds", "separate beds", "single beds"},
    "queen": {"queen", "queen bed", "queen size"},
}

QUERY_STOP_WORDS: Set[str] = {
    "do", "you", "have", "any", "the", "a", "an", "what", "is", "are", "cost",
    "price", "how", "much", "kya", "hai", "aur", "pe", "mein", "batao", "for",
    "please", "give", "me", "some", "options", "option", "rate", "rates", "prices",
    "tell", "rooms", "room", "suites", "suite", "available", "per", "night",
    "kuch", "kuchh", "koi", "chahiye", "kripya", "bhi", "toh", "ka", "ki", "ke",
    "mil", "milega", "hoga", "bataiye", "can", "get", "like", "want", "stay",
    "booking", "staying", "tariff"
}


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words."""
    if not text:
        return []
    return [t for t in re.split(r"[^\w]+", text.lower()) if t]


def rank_room_types_semantic(
    rooms: List[Dict[str, Any]],
    query: str,
    category: Optional[str] = None,
    amenity_preference: Optional[str] = None,
    guests_count: Optional[int] = None,
    max_budget_per_night: Optional[float] = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Core semantic ranking engine for hotel room types and rate cards.
    Ranks rooms using intent expansion, token matching, amenities, and budget filters.
    """
    if not rooms:
        return []

    raw_query = query.strip().lower() if query else ""
    raw_tokens = _tokenize(raw_query)
    content_tokens = [t for t in raw_tokens if t not in QUERY_STOP_WORDS]
    content_tokens_set = set(content_tokens)

    # Detect category intent
    matched_category_intents: Set[str] = set()
    if category:
        cat_clean = category.strip().lower()
        for cat_name in ROOM_CATEGORY_SYNONYMS:
            if cat_clean == cat_name.lower():
                matched_category_intents.add(cat_name)
                break
        if not matched_category_intents:
            matched_category_intents.add(category.strip())

    for cat_name, syns in ROOM_CATEGORY_SYNONYMS.items():
        if any(syn in raw_query for syn in syns):
            matched_category_intents.add(cat_name)

    # Detect amenity intent
    matched_amenity_intents: Set[str] = set()
    if amenity_preference:
        pref_clean = amenity_preference.strip().lower()
        for amenity_key, syns in AMENITY_SYNONYMS.items():
            if pref_clean in syns or pref_clean in amenity_key:
                matched_amenity_intents.add(amenity_key)
        if not matched_amenity_intents:
            matched_amenity_intents.add(pref_clean)

    for amenity_key, syns in AMENITY_SYNONYMS.items():
        if any(syn in raw_query for syn in syns):
            matched_amenity_intents.add(amenity_key)

    # Detect inclusion intent (e.g. breakfast)
    matched_inclusion_intents: Set[str] = set()
    for inc_key, syns in INCLUSION_SYNONYMS.items():
        if any(syn in raw_query for syn in syns):
            matched_inclusion_intents.add(inc_key)

    # Detect bed type intent
    matched_bed_intents: Set[str] = set()
    for bed_key, syns in BED_SYNONYMS.items():
        if any(syn in raw_query for syn in syns):
            matched_bed_intents.add(bed_key)

    scored_rooms = []
    for r in rooms:
        # Check availability
        if not r.get("is_available", True):
            continue

        base_price = float(r.get("base_price", 0.0))

        # Budget hard constraint
        if max_budget_per_night and base_price > max_budget_per_night:
            continue

        # Occupancy hard constraint
        if guests_count and r.get("max_occupancy", 2) < guests_count:
            continue

        score = 0.0
        room_name = (r.get("name") or "").lower()
        room_desc = (r.get("description") or "").lower()
        room_cat = (r.get("category") or "")
        room_bed = (r.get("bed_type") or "").lower()
        amenities_raw = r.get("amenities") or []
        amenities_lower = [str(a).lower() for a in amenities_raw]
        inclusions_raw = r.get("inclusions") or []
        inclusions_lower = [str(i).lower() for i in inclusions_raw]

        # 1. Category boost
        if matched_category_intents:
            if room_cat in matched_category_intents or room_cat.lower() in [c.lower() for c in matched_category_intents]:
                score += 5.0
            elif any(c.lower() in room_name for c in matched_category_intents):
                score += 3.5

        # 2. Amenity boost
        if matched_amenity_intents:
            for am in matched_amenity_intents:
                am_syns = AMENITY_SYNONYMS.get(am, {am})
                if any(any(syn in a for syn in am_syns) for a in amenities_lower) or any(syn in room_desc for syn in am_syns):
                    score += 4.5

        # 3. Inclusion boost (e.g. breakfast)
        if matched_inclusion_intents:
            for inc in matched_inclusion_intents:
                inc_syns = INCLUSION_SYNONYMS.get(inc, {inc})
                if any(any(syn in i for syn in inc_syns) for i in inclusions_lower) or any(syn in room_desc for syn in inc_syns):
                    score += 4.0

        # 4. Bed type boost
        if matched_bed_intents:
            for b in matched_bed_intents:
                if b in room_bed or any(syn in room_bed for syn in BED_SYNONYMS.get(b, set())):
                    score += 3.0

        # 5. Token text matching
        if content_tokens_set:
            room_tokens = set(_tokenize(room_name) + _tokenize(room_desc))
            overlap = content_tokens_set.intersection(room_tokens)
            score += len(overlap) * 2.0

            # Substring match
            for t in content_tokens:
                if t in room_name:
                    score += 1.5
                elif t in room_desc:
                    score += 0.8

        # 6. Exact phrase match
        if raw_query and (raw_query in room_name or raw_query in room_desc):
            score += 6.0

        # Base popularity fallback
        if score == 0.0 and not content_tokens_set and not matched_category_intents and not matched_amenity_intents:
            score = 1.0

        if score > 0.0:
            scored_rooms.append((score, r))

    # Sort descending by score, then ascending by price
    scored_rooms.sort(key=lambda x: (-x[0], x[1].get("base_price", 0)))
    return [item for _, item in scored_rooms[:limit]]


class RoomTypeRepository(BaseRepository):
    """Data access repository for hotel room types and rate cards."""

    def get(self, room_id: str, business_id: Optional[str] = None) -> Optional[RoomType]:
        stmt = select(RoomType).where(RoomType.id == room_id)
        if business_id:
            stmt = stmt.where(RoomType.business_id == business_id)
        return self.session.execute(stmt).scalars().first()

    def list_for_business(
        self,
        business_id: str,
        category: Optional[str] = None,
        only_available: bool = True,
    ) -> List[RoomType]:
        stmt = select(RoomType).where(RoomType.business_id == business_id)
        if category:
            stmt = stmt.where(RoomType.category == category)
        if only_available:
            stmt = stmt.where(RoomType.is_available.is_(True))
        stmt = stmt.order_by(RoomType.base_price.asc())
        return list(self.session.execute(stmt).scalars().all())

    def list_dicts_for_business(
        self,
        business_id: str,
        category: Optional[str] = None,
        only_available: bool = True,
    ) -> List[Dict[str, Any]]:
        rooms = self.list_for_business(business_id=business_id, category=category, only_available=only_available)
        return [r.to_dict() for r in rooms]

    def create(self, business_id: str, data: Dict[str, Any]) -> RoomType:
        room_id = data.get("id") or f"room_{uuid.uuid4().hex[:12]}"
        room = RoomType(
            id=room_id,
            business_id=business_id,
            name=str(data["name"]).strip(),
            category=str(data.get("category") or "Rooms").strip(),
            base_price=float(data["base_price"]),
            weekend_price=float(data.get("weekend_price") or data["base_price"]),
            currency=str(data.get("currency") or "INR").strip(),
            description=str(data.get("description")).strip() if data.get("description") is not None else None,
            bed_type=str(data.get("bed_type") or "1 King Bed").strip(),
            max_occupancy=int(data.get("max_occupancy", 2) or 2),
            max_adults=int(data.get("max_adults", 2) or 2),
            max_children=int(data.get("max_children", 1) or 0),
            amenities=list(data.get("amenities") or []),
            inclusions=list(data.get("inclusions") or []),
            check_in_time=str(data.get("check_in_time") or "14:00").strip(),
            check_out_time=str(data.get("check_out_time") or "11:00").strip(),
            cancellation_policy=str(data.get("cancellation_policy") or "Free cancellation up to 48 hours prior to arrival").strip(),
            is_available=bool(data.get("is_available", True)),
        )
        self.session.add(room)
        self.session.flush()
        return room

    def bulk_create(self, business_id: str, items: List[Dict[str, Any]]) -> List[RoomType]:
        created = []
        for d in items:
            created.append(self.create(business_id, d))
        return created

    def replace_all_for_business(self, business_id: str, items: List[Dict[str, Any]]) -> List[RoomType]:
        del_stmt = delete(RoomType).where(RoomType.business_id == business_id)
        self.session.execute(del_stmt)
        self.session.flush()
        return self.bulk_create(business_id, items)

    def update(self, room_id: str, business_id: str, updates: Dict[str, Any]) -> Optional[RoomType]:
        room = self.get(room_id, business_id=business_id)
        if not room:
            return None
        allowed_fields = {
            "name", "category", "base_price", "weekend_price", "currency",
            "description", "bed_type", "max_occupancy", "max_adults", "max_children",
            "amenities", "inclusions", "check_in_time", "check_out_time",
            "cancellation_policy", "is_available",
        }
        for k, v in updates.items():
            if k in allowed_fields:
                if k in ("base_price", "weekend_price") and v is not None:
                    v = float(v)
                elif k in ("max_occupancy", "max_adults", "max_children") and v is not None:
                    v = int(v)
                setattr(room, k, v)
        self.session.flush()
        return room

    def delete(self, room_id: str, business_id: str) -> bool:
        room = self.get(room_id, business_id=business_id)
        if not room:
            return False
        self.session.delete(room)
        self.session.flush()
        return True

    def search_semantic(
        self,
        business_id: str,
        query: str,
        category: Optional[str] = None,
        amenity_preference: Optional[str] = None,
        guests_count: Optional[int] = None,
        max_budget_per_night: Optional[float] = None,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        all_rooms = self.list_dicts_for_business(business_id=business_id, only_available=True)
        return rank_room_types_semantic(
            rooms=all_rooms,
            query=query,
            category=category,
            amenity_preference=amenity_preference,
            guests_count=guests_count,
            max_budget_per_night=max_budget_per_night,
            limit=limit,
        )
