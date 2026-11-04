"""
Idempotent database seeder for initial sample tenants and operational capabilities.
Seeds sample businesses across hospitality, healthcare, hotel resort, and service/wellness domains:
- 'biz_spice_garden' (Fine Dining Restaurant)
- 'biz_apex_dental' (Healthcare Clinic)
- 'biz_grand_hotel' (Luxury Resort & Hotel)
- 'biz_glow_salon' (Aesthetic Lounge & Spa)
Ensures every tenant has complete profile data, FAQs, reservable resource inventory,
verified tool capabilities with ready status and valid prerequisite configurations,
and representative call audit telemetry without destroying existing user edits.
"""

from typing import Optional, Dict, Any, List
import logging
from sqlalchemy.orm import Session
from sqlalchemy import Engine

from backend.database.engine import (
    get_engine,
    session_scope,
    init_db_schema,
    DatabaseConfigurationError,
)
from backend.database.models import utcnow
from backend.database.repositories import (
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
    ResourceRepository,
    MenuItemRepository,
    RoomTypeRepository,
    TreatmentRepository,
)
from backend.database.seed_data import INITIAL_BUSINESSES, INITIAL_TOOLS, MOCK_CALL_HISTORY

logger = logging.getLogger(__name__)

# Canonical resource definitions per tenant ensuring all booking tools have authoritative inventory
DOMAIN_RESERVABLE_RESOURCES: Dict[str, List[Dict[str, Any]]] = {
    "biz_spice_garden": [
        {"name": "Table 1 (Window)", "capacity": 2, "min_party_size": 1, "max_party_size": 2, "resource_type": "table", "section": "Window"},
        {"name": "Table 2 (Main Hall)", "capacity": 4, "min_party_size": 2, "max_party_size": 4, "resource_type": "table", "section": "Main Dining"},
        {"name": "Table 3 (Garden Patio)", "capacity": 4, "min_party_size": 2, "max_party_size": 4, "resource_type": "table", "section": "Garden Patio"},
        {"name": "Table 4 (Family Booth)", "capacity": 6, "min_party_size": 4, "max_party_size": 8, "resource_type": "table", "section": "Family Section"},
        {"name": "Table 5 (VIP Dining Room)", "capacity": 10, "min_party_size": 6, "max_party_size": 12, "resource_type": "table", "section": "VIP Lounge"},
    ],
    "biz_apex_dental": [
        {"name": "Dental Suite 1 (Consultation)", "capacity": 1, "min_party_size": 1, "max_party_size": 2, "resource_type": "clinic_room", "section": "1st Floor"},
        {"name": "Dental Suite 2 (Procedures & Scaling)", "capacity": 1, "min_party_size": 1, "max_party_size": 2, "resource_type": "procedure_room", "section": "1st Floor"},
        {"name": "Dental Surgery Suite (Orthodontics & Implants)", "capacity": 1, "min_party_size": 1, "max_party_size": 2, "resource_type": "procedure_room", "section": "2nd Floor"},
        {"name": "Dr. Sharma (Senior Orthodontist)", "capacity": 1, "min_party_size": 1, "max_party_size": 1, "resource_type": "practitioner", "section": "Specialists"},
        {"name": "Dr. Ananya Rao (Pediatric Dental Specialist)", "capacity": 1, "min_party_size": 1, "max_party_size": 1, "resource_type": "practitioner", "section": "Specialists"},
    ],
    "biz_grand_hotel": [
        {"name": "Room 101 - Deluxe King (Garden View)", "capacity": 2, "min_party_size": 1, "max_party_size": 3, "resource_type": "room", "section": "East Wing"},
        {"name": "Room 102 - Deluxe Twin (Garden View)", "capacity": 2, "min_party_size": 1, "max_party_size": 3, "resource_type": "room", "section": "East Wing"},
        {"name": "Suite 201 - Executive Oceanfront Suite", "capacity": 4, "min_party_size": 2, "max_party_size": 4, "resource_type": "room", "section": "Ocean Wing"},
        {"name": "Suite 202 - Azure Penthouse Suite", "capacity": 4, "min_party_size": 2, "max_party_size": 6, "resource_type": "room", "section": "Ocean Wing"},
        {"name": "Villa 1 - Private Pool Beach Villa", "capacity": 6, "min_party_size": 2, "max_party_size": 8, "resource_type": "room", "section": "Beachfront"},
        {"name": "Azure Pavilion - Table 1 (Ocean View)", "capacity": 4, "min_party_size": 2, "max_party_size": 4, "resource_type": "table", "section": "Azure Pavilion"},
        {"name": "Azure Pavilion - Table 2 (Terrace)", "capacity": 6, "min_party_size": 4, "max_party_size": 8, "resource_type": "table", "section": "Azure Pavilion"},
    ],
    "biz_glow_salon": [
        {"name": "Styling Station 1 - Master Hair Artist", "capacity": 1, "min_party_size": 1, "max_party_size": 1, "resource_type": "room", "section": "Salon Floor"},
        {"name": "Styling Station 2 - Senior Colorist", "capacity": 1, "min_party_size": 1, "max_party_size": 1, "resource_type": "room", "section": "Salon Floor"},
        {"name": "Therapy Suite A - Aromatherapy & Deep Tissue", "capacity": 1, "min_party_size": 1, "max_party_size": 2, "resource_type": "room", "section": "Wellness Wing"},
        {"name": "Therapy Suite B - Facial & Aesthetic Skincare", "capacity": 1, "min_party_size": 1, "max_party_size": 2, "resource_type": "room", "section": "Wellness Wing"},
        {"name": "Maya Patel (Master Stylist & Aesthetician)", "capacity": 1, "min_party_size": 1, "max_party_size": 1, "resource_type": "practitioner", "section": "Therapists"},
    ],
}


def _get_default_tool_metadata(tool_id: str, business_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return canonical option ID and non-secret configuration meeting all tool prerequisites."""
    tz = business_data.get("timezone", "Asia/Kolkata")
    phone = business_data.get("phone_number", "+91 80 4123 5678")
    email = business_data.get("owner_email", "manager@example.com")

    if tool_id in ("check_table_availability", "create_table_booking"):
        return {
            "selected_option_id": "builtin_dining",
            "configuration": {
                "reservation_duration_minutes": 90,
                "buffer_minutes": 15,
                "advance_booking_days": 30,
                "timezone": tz,
            },
        }
    elif tool_id in ("check_appointment_availability", "create_appointment"):
        return {
            "selected_option_id": "builtin_clinic",
            "configuration": {
                "slot_duration_minutes": 30,
                "buffer_minutes": 10,
                "advance_booking_days": 30,
                "timezone": tz,
            },
        }
    elif tool_id == "query_menu_pricing":
        return {
            "selected_option_id": "builtin_restaurant_menu",
            "configuration": {
                "currency": "INR",
                "default_category": "Mains",
            },
        }
    elif tool_id == "query_room_pricing":
        return {
            "selected_option_id": "builtin_hotel_rooms",
            "configuration": {
                "currency": "INR",
                "show_amenities": True,
            },
        }
    elif tool_id == "query_treatment_pricing":
        return {
            "selected_option_id": "builtin_clinic_treatments",
            "configuration": {
                "currency": "INR",
                "show_preparation_instructions": True,
            },
        }
    elif tool_id in ("check_room_availability", "create_room_booking"):
        return {
            "selected_option_id": "builtin_booking",
            "configuration": {
                "business_type": "hotel",
                "check_in_time": "14:00",
                "check_out_time": "11:00",
                "max_stay_nights": 30,
            },
        }
    elif tool_id == "answer_faq":
        return {
            "selected_option_id": "builtin_knowledge_base",
            "configuration": {
                "strict_business_hours_only": False,
            },
        }
    elif tool_id == "take_message":
        return {
            "selected_option_id": "builtin_messaging",
            "configuration": {
                "urgent_notification_email": email,
                "urgent_notification_phone": phone,
            },
        }
    elif tool_id == "transfer_call":
        return {
            "selected_option_id": "simulated_escalation",
            "configuration": {
                "destination_number": phone,
                "transfer_timeout_seconds": 30,
            },
        }
    return {
        "selected_option_id": None,
        "configuration": {},
    }


def seed_database(
    engine: Optional[Engine] = None,
    session: Optional[Session] = None,
    force_update_profile: bool = False,
) -> Dict[str, Any]:
    """
    Idempotent seeding operation for initial platform businesses.
    Ensures businesses exist with complete profiles, authoritative resources,
    canonical tool configurations with fulfilled prerequisites, FAQs, and simulated call audit logs.
    """
    stats = {
        "businesses_created": 0,
        "businesses_existing": 0,
        "faqs_created": 0,
        "resources_created": 0,
        "tools_configured": 0,
        "calls_seeded": 0,
    }

    def _execute_seed(sess: Session) -> None:
        biz_repo = BusinessRepository(sess)
        faq_repo = FAQRepository(sess)
        tool_repo = ToolConfigRepository(sess)
        call_repo = CallRepository(sess)
        conv_repo = ConversationRepository(sess)
        res_repo = ResourceRepository(sess)
        menu_repo = MenuItemRepository(sess)
        room_repo = RoomTypeRepository(sess)
        treatment_repo = TreatmentRepository(sess)

        for b_id, b_data in INITIAL_BUSINESSES.items():
            biz = biz_repo.get(b_id)
            if not biz:
                # 1. Create Business
                biz = biz_repo.create(b_data)
                stats["businesses_created"] += 1
                logger.info("Seeded new business: %s (%s)", b_id, b_data["name"])

                # 2. Seed FAQs
                for faq_item in b_data.get("faqs", []):
                    faq_repo.create(
                        business_id=b_id,
                        question=faq_item["question"],
                        answer=faq_item["answer"],
                        category="General",
                    )
                    stats["faqs_created"] += 1

                # 3. Seed Initial Greeting Message in Conversation
                conv_repo.add_message(
                    business_id=b_id,
                    role="assistant",
                    content=b_data["greeting_message"],
                    is_simulated=True,
                )

            else:
                stats["businesses_existing"] += 1
                logger.info("Business already exists, ensuring complete configuration: %s", b_id)

                if force_update_profile:
                    biz_repo.update(b_id, b_data)
                else:
                    updates = {}
                    if not biz.password_hash and b_data.get("password_hash"):
                        updates["password_hash"] = b_data["password_hash"]
                    if not biz.owner_email and b_data.get("owner_email"):
                        updates["owner_email"] = b_data["owner_email"]
                    if updates:
                        biz_repo.update(b_id, updates)

                # Ensure FAQs exist if missing
                existing_faqs = faq_repo.list_for_business(b_id)
                if not existing_faqs:
                    for faq_item in b_data.get("faqs", []):
                        faq_repo.create(
                            business_id=b_id,
                            question=faq_item["question"],
                            answer=faq_item["answer"],
                            category="General",
                        )
                        stats["faqs_created"] += 1

            # 3b. Seed Menu Items for this business if not yet seeded
            existing_menu = menu_repo.list_for_business(b_id)
            if not existing_menu and b_data.get("menu_items"):
                menu_repo.bulk_create(b_id, b_data["menu_items"])
                logger.info("Seeded %d menu items for tenant %s", len(b_data["menu_items"]), b_id)

            # 3c. Seed Room Types for this business if not yet seeded (Hospitality domain)
            existing_rooms = room_repo.list_for_business(b_id, only_available=False)
            if not existing_rooms and b_data.get("room_types"):
                room_repo.bulk_create(b_id, b_data["room_types"])
                logger.info("Seeded %d room types for tenant %s", len(b_data["room_types"]), b_id)

            # 3d. Seed Medical Treatments for this business if not yet seeded (Clinic domain)
            existing_treatments = treatment_repo.list_for_business(b_id, only_available=False)
            if not existing_treatments and b_data.get("treatments"):
                treatment_repo.bulk_create(b_id, b_data["treatments"])
                logger.info("Seeded %d treatments for tenant %s", len(b_data["treatments"]), b_id)

            # 4. Seed Reservable Resources for this business if not yet seeded
            existing_resources = res_repo.list_resources(b_id)
            if not existing_resources and b_id in DOMAIN_RESERVABLE_RESOURCES:
                for r in DOMAIN_RESERVABLE_RESOURCES[b_id]:
                    res_repo.create_resource(
                        business_id=b_id,
                        name=r["name"],
                        capacity=r.get("capacity", 4),
                        min_party_size=r.get("min_party_size", 1),
                        max_party_size=r.get("max_party_size", 4),
                        resource_type=r.get("resource_type", "table"),
                        section=r.get("section"),
                    )
                    stats["resources_created"] += 1
                logger.info("Seeded %d reservable resources for tenant %s", len(DOMAIN_RESERVABLE_RESOURCES[b_id]), b_id)

            # 5. Seed / Update Tool Capabilities with Prerequisites Fulfilled
            enabled_map = b_data.get("enabled_tools", {})
            now = utcnow()
            for t_id in INITIAL_TOOLS:
                is_enabled = bool(enabled_map.get(t_id, False))
                meta = _get_default_tool_metadata(t_id, b_data)

                if is_enabled:
                    tool_repo.set_tool_capability(
                        business_id=b_id,
                        tool_id=t_id,
                        is_enabled=True,
                        status="ready",
                        selected_option_id=meta["selected_option_id"],
                        configuration=meta["configuration"],
                        last_validated_at=now,
                    )
                else:
                    tool_repo.set_tool_capability(
                        business_id=b_id,
                        tool_id=t_id,
                        is_enabled=False,
                        status="not_configured",
                        selected_option_id=meta["selected_option_id"],
                        configuration=meta["configuration"],
                    )
                stats["tools_configured"] += 1

            # 6. Seed Mock Call Records if none exist
            existing_calls = call_repo.list_for_business(b_id, limit=1)
            if not existing_calls:
                calls = MOCK_CALL_HISTORY.get(b_id, [])
                for c in calls:
                    call_repo.log_call(
                        business_id=b_id,
                        caller_number=c["caller_number"],
                        duration_seconds=120,
                        duration_formatted=c.get("duration", "2m 00s"),
                        outcome=c["outcome"],
                        summary=c["summary"],
                        tools_used=c.get("tools_used", []),
                        is_simulated=True,
                        call_id=c["id"],
                    )
                    stats["calls_seeded"] += 1

    if session is not None:
        _execute_seed(session)
    else:
        eng = engine or get_engine()
        init_db_schema(eng)
        with session_scope(engine=eng) as sess:
            _execute_seed(sess)

    return stats


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("Connecting to database and running seed operation...")
    try:
        results = seed_database()
        print(f"Seed operation completed successfully:\n{results}")
    except DatabaseConfigurationError as err:
        print(f"Configuration Error: {err}")
        sys.exit(1)
    except Exception as exc:
        print(f"Seed Error: {type(exc).__name__}: {exc}")
        sys.exit(1)
