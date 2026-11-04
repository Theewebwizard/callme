"""
Clinic Medical Treatment and Consultation Fee Repository.
Provides authoritative CRUD operations and semantic search for clinic procedures and doctor fees.
"""

from typing import List, Dict, Any, Optional
import re
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.database.models import MedicalTreatment, utcnow


# Domain-specific synonym mappings for dental and medical procedures
CATEGORY_SYNONYMS: Dict[str, List[str]] = {
    "consultation": ["consultation", "checkup", "exam", "examination", "visit", "first visit", "doctor fee", "visiting charges", "second opinion", "opg"],
    "preventive": ["cleaning", "scaling", "polishing", "tartar", "plaque", "hygiene", "preventive", "deep cleaning"],
    "restoration": ["rct", "root canal", "filling", "cavity", "toothache", "tooth pain", "restoration", "composite filling"],
    "orthodontics": ["braces", "aligners", "invisalign", "teeth straightening", "crooked teeth", "bite correction", "retainer"],
    "prosthodontics": ["implant", "implants", "crown", "cap", "bridge", "denture", "replacement", "fixed teeth"],
    "cosmetic": ["whitening", "bleaching", "smile makeover", "veneers", "bonding", "teeth polish", "brightening"],
    "surgery": ["extraction", "wisdom tooth", "surgical", "minor surgery", "tooth removal", "gum surgery"],
    "pediatric": ["kids", "child", "pediatric", "milk teeth", "baby teeth"],
}

PROCEDURE_KEYWORD_SYNONYMS: Dict[str, List[str]] = {
    "root canal": ["rct", "nerve treatment", "pulp", "infection", "tooth pain", "cavity"],
    "teeth cleaning": ["scaling", "ultrasonic", "polishing", "plaque", "stains"],
    "braces": ["metal braces", "ceramic braces", "invisible aligners", "invisalign", "straightening"],
    "whitening": ["bleaching", "laser whitening", "smile glow", "stain removal"],
    "implant": ["titanium implant", "single tooth implant", "permanent tooth", "screw"],
    "consultation": ["general checkup", "doctor examination", "x-ray", "opg"],
    "wisdom tooth": ["impacted tooth", "extraction", "surgical removal"],
}


def rank_treatments_semantic(
    treatments: List[MedicalTreatment],
    query: str,
    category: Optional[str] = None,
    practitioner_type: Optional[str] = None,
    max_budget: Optional[float] = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Ranks clinical treatments and procedures against caller inquiries using
    domain-aware lexical and synonym expansion.
    """
    clean_query = query.strip().lower() if query else ""
    query_tokens = set(re.findall(r"\w+", clean_query))

    expanded_tokens = set(query_tokens)
    for canonical_cat, syns in CATEGORY_SYNONYMS.items():
        if any(tok in clean_query for tok in syns):
            expanded_tokens.add(canonical_cat)
            expanded_tokens.update(syns)

    for canonical_proc, syns in PROCEDURE_KEYWORD_SYNONYMS.items():
        if canonical_proc in clean_query or any(syn in clean_query for syn in syns):
            expanded_tokens.update(re.findall(r"\w+", canonical_proc))
            expanded_tokens.update(syns)

    scored: List[tuple[float, Any]] = []

    for tr in treatments:
        # Extract attributes safely for both ORM objects and dicts
        tr_name = tr.name if hasattr(tr, "name") else tr.get("name", "")
        tr_cat = tr.category if hasattr(tr, "category") else tr.get("category", "")
        tr_doc = tr.practitioner_type if hasattr(tr, "practitioner_type") else tr.get("practitioner_type", "")
        tr_fee = tr.base_fee if hasattr(tr, "base_fee") else float(tr.get("base_fee", 0.0))
        tr_desc = tr.description if hasattr(tr, "description") else (tr.get("description") or "")
        is_avail = tr.is_available if hasattr(tr, "is_available") else tr.get("is_available", True)

        if not is_avail:
            continue

        # Category filter
        if category and category.lower() not in (tr_cat or "").lower():
            continue

        # Practitioner type filter
        if practitioner_type and practitioner_type.lower() not in (tr_doc or "").lower():
            continue

        # Budget constraint
        if max_budget is not None and tr_fee > (max_budget * 1.15):
            continue

        score = 0.0
        tr_name_lower = (tr_name or "").lower()
        tr_cat_lower = (tr_cat or "").lower()
        tr_desc_lower = (tr_desc or "").lower()
        tr_doc_lower = (tr_doc or "").lower()

        # Exact name match
        if clean_query and clean_query in tr_name_lower:
            score += 60.0

        # Token matching against name
        tr_name_tokens = set(re.findall(r"\w+", tr_name_lower))
        matched_name = expanded_tokens.intersection(tr_name_tokens)
        score += len(matched_name) * 15.0

        # Category matching
        tr_cat_tokens = set(re.findall(r"\w+", tr_cat_lower))
        matched_cat = expanded_tokens.intersection(tr_cat_tokens)
        score += len(matched_cat) * 8.0

        # Practitioner type matching
        tr_doc_tokens = set(re.findall(r"\w+", tr_doc_lower))
        matched_doc = expanded_tokens.intersection(tr_doc_tokens)
        score += len(matched_doc) * 10.0

        # Explicit practitioner_type filter boost
        if practitioner_type and practitioner_type.lower() in tr_doc_lower:
            score += 30.0

        # Generic inquiry tokens boost (e.g. "procedure", "treatment", "doctor", "services")
        generic_words = {"procedure", "procedures", "treatment", "treatments", "doctor", "service", "services", "charge", "charges", "cost", "fee"}
        if query_tokens and any(tok in generic_words for tok in query_tokens):
            score += 15.0

        # Description keywords
        if clean_query:
            for tok in query_tokens:
                if len(tok) >= 4 and tok in tr_desc_lower:
                    score += 4.0

        # Budget proximity bonus
        if max_budget is not None:
            diff = max_budget - tr_fee
            if diff >= 0:
                score += 5.0

        # Default score if query is generic
        if not clean_query:
            score = 10.0

        if score > 0:
            scored.append((score, tr))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [item[1].to_dict() if hasattr(item[1], "to_dict") else dict(item[1]) for item in scored[:limit]]
    return results


class TreatmentRepository:
    """Repository handling persistence and search for MedicalTreatment models."""

    def __init__(self, session: Session):
        self.session = session

    def list_for_business(
        self,
        business_id: str,
        category: Optional[str] = None,
        only_available: bool = True,
    ) -> List[MedicalTreatment]:
        stmt = (
            select(MedicalTreatment)
            .where(MedicalTreatment.business_id == business_id)
            .order_by(MedicalTreatment.category.asc(), MedicalTreatment.base_fee.asc())
        )
        if category:
            stmt = stmt.where(MedicalTreatment.category == category)
        if only_available:
            stmt = stmt.where(MedicalTreatment.is_available.is_(True))
        return list(self.session.execute(stmt).scalars().all())

    def list_dicts_for_business(
        self,
        business_id: str,
        category: Optional[str] = None,
        only_available: bool = True,
    ) -> List[Dict[str, Any]]:
        items = self.list_for_business(business_id, category, only_available)
        return [item.to_dict() for item in items]

    def get(self, treatment_id: str, business_id: Optional[str] = None) -> Optional[MedicalTreatment]:
        stmt = select(MedicalTreatment).where(MedicalTreatment.id == treatment_id)
        if business_id:
            stmt = stmt.where(MedicalTreatment.business_id == business_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def create(self, business_id: str, data: Dict[str, Any]) -> MedicalTreatment:
        now = utcnow()
        treatment_id = data.get("id") or f"treat_{uuid.uuid4().hex[:12]}"
        item = MedicalTreatment(
            id=treatment_id,
            business_id=business_id,
            name=data["name"].strip(),
            category=data.get("category", "Consultation").strip(),
            base_fee=float(data["base_fee"]),
            fee_range_max=float(data.get("fee_range_max") or data["base_fee"]),
            currency=data.get("currency", "INR").strip().upper(),
            duration_minutes=int(data.get("duration_minutes", 30)),
            practitioner_type=data.get("practitioner_type", "General Dentist").strip(),
            description=data.get("description", "").strip() or None,
            preparation_instructions=data.get("preparation_instructions", "").strip() or None,
            is_available=bool(data.get("is_available", True)),
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def bulk_create(self, business_id: str, items_data: List[Dict[str, Any]]) -> List[MedicalTreatment]:
        created = []
        for d in items_data:
            created.append(self.create(business_id, d))
        return created

    def replace_all_for_business(
        self, business_id: str, items_data: List[Dict[str, Any]]
    ) -> List[MedicalTreatment]:
        self.session.execute(
            delete(MedicalTreatment).where(MedicalTreatment.business_id == business_id)
        )
        self.session.flush()
        return self.bulk_create(business_id, items_data)

    def update(
        self, treatment_id: str, business_id: str, updates: Dict[str, Any]
    ) -> Optional[MedicalTreatment]:
        item = self.get(treatment_id, business_id=business_id)
        if not item:
            return None

        allowed = {
            "name", "category", "base_fee", "fee_range_max", "currency",
            "duration_minutes", "practitioner_type", "description",
            "preparation_instructions", "is_available"
        }
        for k, v in updates.items():
            if k in allowed:
                setattr(item, k, v)

        item.updated_at = utcnow()
        self.session.flush()
        return item

    def delete(self, treatment_id: str, business_id: str) -> bool:
        item = self.get(treatment_id, business_id=business_id)
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
        practitioner_type: Optional[str] = None,
        max_budget: Optional[float] = None,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        all_treatments = self.list_for_business(business_id, only_available=True)
        return rank_treatments_semantic(
            all_treatments,
            query=query,
            category=category,
            practitioner_type=practitioner_type,
            max_budget=max_budget,
            limit=limit,
        )
