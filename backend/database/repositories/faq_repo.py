"""
Repository for Business FAQs and knowledge-base items.
"""

from typing import Optional, List, Dict, Any
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.database.models import BusinessFAQ
from backend.database.repositories.base import BaseRepository


class FAQRepository(BaseRepository):
    """Repository handling business FAQ persistence and retrieval."""

    def list_for_business(self, business_id: str) -> List[BusinessFAQ]:
        """Fetch all FAQs belonging to the given business."""
        stmt = (
            select(BusinessFAQ)
            .where(BusinessFAQ.business_id == business_id)
            .order_by(BusinessFAQ.created_at)
        )
        return list(self.session.scalars(stmt).all())

    def list_dicts_for_business(self, business_id: str) -> List[Dict[str, Any]]:
        """Return FAQ dicts formatted for the UI and LangGraph tools."""
        faqs = self.list_for_business(business_id)
        return [f.to_dict() for f in faqs]

    def get(self, faq_id: str) -> Optional[BusinessFAQ]:
        """Fetch a specific FAQ by ID."""
        return self.session.get(BusinessFAQ, faq_id)

    def create(
        self,
        business_id: str,
        question: str,
        answer: str,
        category: str = "General",
        faq_id: Optional[str] = None,
    ) -> BusinessFAQ:
        """Create and persist a new business FAQ."""
        faq = BusinessFAQ(
            id=faq_id or f"faq_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
            question=question.strip(),
            answer=answer.strip(),
            category=category.strip() if category else "General",
        )
        self.session.add(faq)
        self.session.flush()
        return faq

    def update(
        self,
        faq_id: str,
        business_id: str,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[BusinessFAQ]:
        """Update an existing FAQ with strict tenant verification."""
        faq = self.get(faq_id)
        if not faq or faq.business_id != business_id:
            return None

        if question is not None:
            faq.question = question.strip()
        if answer is not None:
            faq.answer = answer.strip()
        if category is not None:
            faq.category = category.strip()

        self.session.flush()
        return faq

    def delete(self, faq_id: str, business_id: Optional[str] = None) -> bool:
        """Delete an FAQ with optional tenant isolation check."""
        faq = self.get(faq_id)
        if not faq:
            return False
        if business_id and faq.business_id != business_id:
            return False

        self.session.delete(faq)
        self.session.flush()
        return True

    def replace_all_for_business(
        self,
        business_id: str,
        faqs: List[Dict[str, str]],
    ) -> List[BusinessFAQ]:
        """
        Replace all FAQs for a business in a single transaction.
        Removes existing FAQs and recreates new entries.
        """
        # Delete existing FAQs for business
        del_stmt = delete(BusinessFAQ).where(BusinessFAQ.business_id == business_id)
        self.session.execute(del_stmt)

        created_faqs = []
        for item in faqs:
            q = item.get("question", "").strip()
            a = item.get("answer", "").strip()
            cat = item.get("category", "General").strip()
            if q and a:
                faq = self.create(
                    business_id=business_id,
                    question=q,
                    answer=a,
                    category=cat,
                    faq_id=item.get("id"),
                )
                created_faqs.append(faq)

        self.session.flush()
        return created_faqs
