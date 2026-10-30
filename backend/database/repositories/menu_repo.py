"""
Repository and semantic search engine for restaurant menu items.
Supports multi-tenant persistence, bulk ingestion, dietary filtering,
budget constraints, and semantic concept retrieval.
"""

from typing import Optional, List, Dict, Any, Set
import re
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.database.models import MenuItem
from backend.database.repositories.base import BaseRepository

# Category intents for food queries (multilingual Hindi/Hinglish & English)
CATEGORY_SYNONYMS: Dict[str, Set[str]] = {
    "Desserts": {
        "dessert", "desserts", "sweet", "sweets", "meetha", "mithai", "pudding",
        "sweet dish", "sweet dishes", "kuch meetha",
    },
    "Breads": {
        "bread", "breads", "roti", "rotis", "naan", "naans", "paratha", "parathas",
        "kulcha", "kulchas", "chapati", "chapatis",
    },
    "Beverages": {
        "beverage", "beverages", "drink", "drinks", "peena", "sharbat", "mocktail",
        "mocktails", "shake", "shakes", "cold drink", "cold drinks", "thanda",
    },
    "Starters": {
        "starter", "starters", "snack", "snacks", "appetizer", "appetizers",
        "finger food", "chakhna",
    },
    "Mains": {
        "main", "mains", "curry", "curries", "gravy", "gravies", "sabzi", "sabji",
        "entree", "main course", "thali", "meal",
    },
}

DIETARY_SYNONYMS: Dict[str, Set[str]] = {
    "vegetarian": {"veg", "vegetarian", "shakahari", "no meat", "pure veg", "green"},
    "vegan": {"vegan", "plant-based", "dairy-free", "dairy free", "no dairy"},
    "gluten-free": {"gluten-free", "gluten free", "no gluten", "wheat-free", "wheat free"},
    "jain": {"jain", "no onion no garlic", "bina pyaaz lehsun", "bina pyaz", "swaminarayan"},
    "non-vegetarian": {"non-veg", "non-vegetarian", "meat", "chicken", "mutton", "fish", "egg", "mansahari"},
}

SPICE_SYNONYMS: Dict[str, Set[str]] = {
    "spicy": {"spicy", "teekha", "chatpata", "hot", "chilli", "chili", "mirch", "masaledar"},
    "mild": {"mild", "kam teekha", "not spicy", "sweetish", "creamy", "malai", "soft", "less spicy"},
    "medium": {"medium", "normal", "balanced", "moderate"},
}

QUERY_STOP_WORDS: Set[str] = {
    "do", "you", "have", "any", "the", "a", "an", "what", "is", "are", "cost",
    "price", "how", "much", "kya", "hai", "aur", "pe", "mein", "batao", "for",
    "please", "give", "me", "some", "options", "option", "rate", "prices",
    "tell", "menu", "dishes", "dish", "items", "item", "available", "serve",
    "kuch", "kuchh", "koi", "chahiye", "kripya", "bhi", "toh", "ka", "ki", "ke",
    "mil", "milega", "hoga", "bataiye", "can", "get", "like", "want"
}


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words."""
    if not text:
        return []
    return [t for t in re.split(r"[^\w]+", text.lower()) if t]


def rank_menu_items_semantic(
    items: List[Dict[str, Any]],
    query: str,
    category: Optional[str] = None,
    dietary_preference: Optional[str] = None,
    max_budget: Optional[float] = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Core semantic ranking engine for restaurant menu items.
    Ranks items using intent expansion, token matching, dietary tags, and budget filters.
    """
    if not items:
        return []

    raw_query = query.strip().lower() if query else ""
    raw_tokens = _tokenize(raw_query)
    content_tokens = [t for t in raw_tokens if t not in QUERY_STOP_WORDS]
    content_tokens_set = set(content_tokens)

    # Detect category intent
    matched_category_intents: Set[str] = set()
    if category:
        cat_clean = category.strip().lower()
        for cat_name in CATEGORY_SYNONYMS:
            if cat_clean == cat_name.lower():
                matched_category_intents.add(cat_name)
                break
        if not matched_category_intents:
            matched_category_intents.add(category.strip())
    else:
        for cat_name, synonyms in CATEGORY_SYNONYMS.items():
            if any(syn in raw_query for syn in synonyms):
                matched_category_intents.add(cat_name)

    # Detect dietary preference
    detected_dietary: Set[str] = set()
    if dietary_preference:
        pref_clean = dietary_preference.strip().lower()
        for tag_name, synonyms in DIETARY_SYNONYMS.items():
            if pref_clean == tag_name or pref_clean in synonyms:
                detected_dietary.add(tag_name)
        if not detected_dietary:
            detected_dietary.add(pref_clean)
    else:
        for tag_name, synonyms in DIETARY_SYNONYMS.items():
            if any(syn in raw_query for syn in synonyms):
                detected_dietary.add(tag_name)

    # Detect spice preference
    detected_spice: Optional[str] = None
    for spice_level, synonyms in SPICE_SYNONYMS.items():
        if any(syn in raw_query for syn in synonyms):
            detected_spice = spice_level
            break

    scored_results: List[Dict[str, Any]] = []

    for item in items:
        if not item.get("is_available", True):
            continue

        price = float(item.get("price", 0.0))
        if max_budget is not None and price > (max_budget + 0.01):
            continue

        item_tags = [t.lower() for t in (item.get("dietary_tags") or [])]
        if "vegetarian" in detected_dietary and "vegetarian" not in item_tags and "vegan" not in item_tags:
            continue
        if "vegan" in detected_dietary and "vegan" not in item_tags:
            continue
        if "gluten-free" in detected_dietary and "gluten-free" not in item_tags:
            continue
        if "jain" in detected_dietary and "jain" not in item_tags and "jain-available" not in item_tags:
            continue

        name_lower = str(item.get("name", "")).lower()
        cat_lower = str(item.get("category", "")).lower()
        desc_lower = str(item.get("description", "") or "").lower()
        name_tokens = set(_tokenize(name_lower))
        desc_tokens = set(_tokenize(desc_lower))

        # Grounding check:
        # Require that at least one content token or detected intent relates to this dish
        if content_tokens_set:
            has_name_overlap = bool(content_tokens_set.intersection(name_tokens))
            has_desc_overlap = bool(content_tokens_set.intersection(desc_tokens))
            has_category_intent = bool(matched_category_intents and any(ci.lower() == cat_lower for ci in matched_category_intents))
            has_dietary_match = bool(detected_dietary and any(d in item_tags for d in detected_dietary))

            non_cat_tokens = [
                t for t in content_tokens
                if not any(t in syns for syns in CATEGORY_SYNONYMS.values())
                and not any(t in syns for syns in DIETARY_SYNONYMS.values())
            ]
            if non_cat_tokens:
                word_match = any(w in name_lower or w in desc_lower for w in non_cat_tokens)
                if not word_match:
                    continue
            elif not (has_name_overlap or has_desc_overlap or has_category_intent or has_dietary_match):
                continue

        # Score computation
        score = 0.0

        if raw_query and raw_query in name_lower:
            score += 20.0
        elif raw_query and any(word in name_lower for word in content_tokens if len(word) > 2):
            score += 10.0

        overlap_name = content_tokens_set.intersection(name_tokens)
        score += len(overlap_name) * 6.0

        if matched_category_intents:
            if any(ci.lower() == cat_lower for ci in matched_category_intents):
                score += 10.0

        overlap_desc = content_tokens_set.intersection(desc_tokens)
        score += len(overlap_desc) * 2.0

        if detected_dietary:
            for d in detected_dietary:
                if d in item_tags:
                    score += 4.0

        if detected_spice:
            item_spice = str(item.get("spice_level") or "medium").lower()
            if item_spice == detected_spice:
                score += 3.0
            elif detected_spice in desc_lower:
                score += 2.0

        if raw_query and score <= 0.0:
            continue

        item_dict = dict(item)
        item_dict["_relevance_score"] = round(score, 2)
        scored_results.append(item_dict)

    scored_results.sort(key=lambda x: (-x["_relevance_score"], x["price"]))

    final_results = []
    for r in scored_results[:limit]:
        clean_item = dict(r)
        clean_item.pop("_relevance_score", None)
        final_results.append(clean_item)

    return final_results


class MenuItemRepository(BaseRepository):
    """Repository handling business menu item persistence and semantic retrieval."""

    def list_for_business(
        self,
        business_id: str,
        category: Optional[str] = None,
        only_available: bool = True,
    ) -> List[MenuItem]:
        """Fetch all menu items belonging to the given business."""
        stmt = select(MenuItem).where(MenuItem.business_id == business_id)
        if category:
            stmt = stmt.where(MenuItem.category.ilike(category.strip()))
        if only_available:
            stmt = stmt.where(MenuItem.is_available.is_(True))
        stmt = stmt.order_by(MenuItem.category, MenuItem.name)
        return list(self.session.scalars(stmt).all())

    def list_dicts_for_business(
        self,
        business_id: str,
        category: Optional[str] = None,
        only_available: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return menu item dicts formatted for the UI and tools."""
        items = self.list_for_business(business_id, category=category, only_available=only_available)
        return [i.to_dict() for i in items]

    def get(self, item_id: str, business_id: Optional[str] = None) -> Optional[MenuItem]:
        """Fetch a specific menu item by ID with optional tenant check."""
        item = self.session.get(MenuItem, item_id)
        if item and business_id and item.business_id != business_id:
            return None
        return item

    def create(
        self,
        business_id: str,
        item_data: Dict[str, Any],
    ) -> MenuItem:
        """Create and persist a single menu item."""
        item = MenuItem(
            id=item_data.get("id") or f"item_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
            name=str(item_data.get("name", "")).strip(),
            category=str(item_data.get("category", "Mains")).strip(),
            price=float(item_data.get("price", 0.0)),
            currency=str(item_data.get("currency", "INR")).strip().upper(),
            description=str(item_data.get("description", "")).strip() or None,
            dietary_tags=list(item_data.get("dietary_tags") or []),
            spice_level=str(item_data.get("spice_level", "medium")).strip().lower() if item_data.get("spice_level") else "medium",
            is_available=bool(item_data.get("is_available", True)),
        )
        self.session.add(item)
        self.session.flush()
        return item

    def bulk_create(
        self,
        business_id: str,
        items: List[Dict[str, Any]],
    ) -> List[MenuItem]:
        """Bulk persist a list of menu items."""
        created = []
        for d in items:
            created.append(self.create(business_id, d))
        return created

    def replace_all_for_business(
        self,
        business_id: str,
        items: List[Dict[str, Any]],
    ) -> List[MenuItem]:
        """
        Replace all menu items for a business in a single transaction.
        Enables seamless menu upload and re-synchronization.
        """
        del_stmt = delete(MenuItem).where(MenuItem.business_id == business_id)
        self.session.execute(del_stmt)
        return self.bulk_create(business_id, items)

    def update(
        self,
        item_id: str,
        business_id: str,
        updates: Dict[str, Any],
    ) -> Optional[MenuItem]:
        """Update mutable fields of an existing menu item with strict tenant check."""
        item = self.get(item_id, business_id=business_id)
        if not item:
            return None

        allowed_fields = {
            "name", "category", "price", "currency", "description",
            "dietary_tags", "spice_level", "is_available"
        }
        for field, value in updates.items():
            if field in allowed_fields and hasattr(item, field):
                if field == "price":
                    setattr(item, field, float(value))
                elif field == "is_available":
                    setattr(item, field, bool(value))
                elif field == "dietary_tags":
                    setattr(item, field, list(value or []))
                else:
                    setattr(item, field, value)

        self.session.flush()
        return item

    def delete(self, item_id: str, business_id: Optional[str] = None) -> bool:
        """Delete a menu item with optional tenant isolation check."""
        item = self.get(item_id, business_id=business_id)
        if not item:
            return False
        self.session.delete(item)
        self.session.flush()
        return True

    def search_semantic(
        self,
        business_id: str,
        query: str,
        category: Optional[str] = None,
        dietary_preference: Optional[str] = None,
        max_budget: Optional[float] = None,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Search restaurant menu items using semantic concept matching, dietary filtering,
        and budget constraints.
        """
        all_items = self.list_dicts_for_business(business_id=business_id, only_available=True)
        return rank_menu_items_semantic(
            items=all_items,
            query=query,
            category=category,
            dietary_preference=dietary_preference,
            max_budget=max_budget,
            limit=limit,
        )
