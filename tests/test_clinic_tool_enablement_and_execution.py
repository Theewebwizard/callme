"""
Test Suite: Clinic Tool Enablement and End-to-End Live Execution.
Verifies that:
1. Enabling tools promotes their readiness status to 'ready' and configures authoritative adapter.
2. In-memory profile and capability caches are properly invalidated on tool toggle.
3. Appointment availability checks enforce doctor availability days (e.g. Mon off, Tue available).
4. Appointment creation atomically reserves real appointments in PostgreSQL with APT- prefixes.
5. Double bookings are detected and declined.
"""

import uuid
from datetime import datetime, timedelta
import pytest

from backend.database.service import get_database_service
from backend.database.engine import session_scope
from backend.database.models import Business
from backend.tools.registry import get_tool_registry
from backend.tools.base import ToolExecutionStatus


@pytest.fixture
def clinic_tenant():
    svc = get_database_service()
    biz_id = f"biz_test_clinic_{uuid.uuid4().hex[:6]}"
    with session_scope(svc.session_factory) as session:
        b = Business(
            id=biz_id,
            name="Apex Specialty Clinic",
            industry="Clinic / Medical",
            description="Specialized medical and dental clinic.",
            owner_email=f"clinic_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="testpasshash",
            greeting_message="Welcome to Apex Specialty Clinic.",
            phone_number="+15557778888",
        )
        session.add(b)

    # Add a practitioner resource with specific working days (Tue-Sat; Sun and Mon off)
    doc_res = svc.create_resource(
        business_id=biz_id,
        name="Dr. Kavita Verma (Senior Surgeon)",
        capacity=1,
        min_party_size=1,
        max_party_size=1,
        resource_type="practitioner",
        section="Surgery & Consultation",
        is_active=True,
        metadata_json={
            "specialization": "Surgery & Consultation",
            "available_days": ["Tue", "Wed", "Thu", "Fri", "Sat"],
            "off_days": ["Sun", "Mon"],
            "slot_duration_minutes": 30,
        },
    )

    yield {
        "business_id": biz_id,
        "doctor_resource_id": doc_res["id"],
        "doctor_name": doc_res["name"],
    }

    # Cleanup
    with session_scope(svc.session_factory) as session:
        biz_model = session.get(Business, biz_id)
        if biz_model:
            session.delete(biz_model)


def test_tool_enablement_and_status_promotion(clinic_tenant):
    svc = get_database_service()
    biz_id = clinic_tenant["business_id"]

    # Initially enable appointment availability and appointment creation
    svc.set_tool_status(biz_id, "check_appointment_availability", True)
    svc.set_tool_status(biz_id, "create_appointment", True)

    tools = svc.list_tool_configs(biz_id)
    tool_dict = {t["tool_id"]: t for t in tools}

    assert tool_dict["check_appointment_availability"]["is_enabled"] is True
    assert tool_dict["check_appointment_availability"]["status"] == "ready"
    assert tool_dict["check_appointment_availability"]["selected_option_id"] == "builtin_clinic"

    assert tool_dict["create_appointment"]["is_enabled"] is True
    assert tool_dict["create_appointment"]["status"] == "ready"
    assert tool_dict["create_appointment"]["selected_option_id"] == "builtin_clinic"


def test_appointment_availability_and_doctor_off_days(clinic_tenant):
    svc = get_database_service()
    biz_id = clinic_tenant["business_id"]
    biz_profile = svc.get_business_profile(biz_id)
    reg = get_tool_registry()

    # Enable tools
    svc.set_tool_status(biz_id, "check_appointment_availability", True)
    svc.set_tool_status(biz_id, "create_appointment", True)
    biz_profile = svc.get_business_profile(biz_id)

    # 2026-11-06 is Friday (Doctor is available)
    res_avail = reg.execute_tool(
        biz_id,
        biz_profile,
        "check_appointment_availability",
        {
            "service_or_department": "Surgery & Consultation",
            "preferred_date": "2026-11-06",
            "preferred_time": "11:00",
        },
    )
    assert res_avail.status == ToolExecutionStatus.SUCCESS
    assert res_avail.success is True
    assert res_avail.data["available"] is True
    assert len(res_avail.data["available_resources"]) >= 1

    # 2026-11-09 is Monday (Doctor is OFF)
    res_off = reg.execute_tool(
        biz_id,
        biz_profile,
        "check_appointment_availability",
        {
            "service_or_department": "Surgery & Consultation",
            "preferred_date": "2026-11-09",
            "preferred_time": "11:00",
        },
    )
    assert res_off.status == ToolExecutionStatus.BUSINESS_DECLINED
    assert res_off.success is True
    assert res_off.data["available"] is False
    assert len(res_off.data["available_resources"]) == 0


def test_appointment_booking_and_conflict_handling(clinic_tenant):
    svc = get_database_service()
    biz_id = clinic_tenant["business_id"]

    svc.set_tool_status(biz_id, "check_appointment_availability", True)
    svc.set_tool_status(biz_id, "create_appointment", True)
    biz_profile = svc.get_business_profile(biz_id)
    reg = get_tool_registry()

    # 1. Book appointment on Friday at 11:00
    res_booking = reg.execute_tool(
        biz_id,
        biz_profile,
        "create_appointment",
        {
            "patient_name": "Rohan Mehra",
            "patient_phone": "+919876500001",
            "service_or_department": "Surgery & Consultation",
            "appointment_date": "2026-11-06",
            "appointment_time": "11:00",
            "notes": "Pre-op surgical consultation",
        },
        confirmed=True,
    )
    assert res_booking.status == ToolExecutionStatus.SUCCESS
    assert res_booking.success is True
    assert res_booking.data["booking_reference"].startswith("APT-")
    assert res_booking.data["doctor_name"] == clinic_tenant["doctor_name"]

    # 2. Verify appointment committed to database
    reservations = svc.list_reservations(biz_id)
    assert len(reservations) == 1
    assert reservations[0]["id"] == res_booking.data["booking_reference"]
    assert reservations[0]["customer_name"] == "Rohan Mehra"

    # 3. Attempt to double book the same 11:00 slot
    res_conflict = reg.execute_tool(
        biz_id,
        biz_profile,
        "create_appointment",
        {
            "patient_name": "Simran Kaur",
            "patient_phone": "+919876500002",
            "service_or_department": "Surgery & Consultation",
            "appointment_date": "2026-11-06",
            "appointment_time": "11:00",
            "notes": "Second patient wanting same slot",
        },
        confirmed=True,
    )
    assert res_conflict.status == ToolExecutionStatus.BUSINESS_DECLINED
    assert res_conflict.success is True
    assert "scheduling conflict" in res_conflict.message
