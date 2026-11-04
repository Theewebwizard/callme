"""
Tests ensuring strict separation of requirements and inventory between
Restaurant (Dining Tables & Seating) and Clinic (Doctor Practices & Appointments).
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from backend.database.engine import session_scope
from backend.database.models import Business, ReservableResource, Reservation
from backend.database.repositories.reservation_repo import ReservationRepository


def test_restaurant_table_and_clinic_doctor_separation(isolate_test_database):
    """
    Verify that restaurant tables and clinic doctors are completely isolated
    in resource typing, availability checks, and reservation creation.
    """
    uid = uuid.uuid4().hex[:6]
    rest_biz_id = f"biz_test_bistro_{uid}"
    clinic_biz_id = f"biz_test_clinic_{uid}"

    with session_scope() as session:
        # 1. Setup Restaurant Business and Dining Tables
        rest_biz = Business(
            id=rest_biz_id,
            name="The Gourmet Bistro",
            industry="Restaurant",
            greeting_message="Welcome to Gourmet Bistro! How may I assist you?",
            phone_number=f"+91 99887 {uid[:4]}",
            timezone="Asia/Kolkata",
        )
        session.add(rest_biz)

        table1 = ReservableResource(
            id=f"res_tbl_window_{uid}",
            business_id=rest_biz_id,
            name="Table 1 (Window Booth)",
            resource_type="table",
            section="Main Dining",
            capacity=4,
            min_party_size=2,
            max_party_size=4,
            is_active=True,
        )
        session.add(table1)

        # 2. Setup Clinic Business and Doctor
        clinic_biz = Business(
            id=clinic_biz_id,
            name="City Dental Clinic",
            industry="Clinic / Medical",
            greeting_message="Welcome to City Dental Clinic. How can I help you book your consultation?",
            phone_number=f"+91 99888 {uid[:4]}",
            timezone="Asia/Kolkata",
        )
        session.add(clinic_biz)

        doctor1 = ReservableResource(
            id=f"res_dr_mehta_{uid}",
            business_id=clinic_biz_id,
            name="Dr. Mehta (Orthodontist)",
            resource_type="practitioner",
            section="Orthodontics",
            capacity=1,
            min_party_size=1,
            max_party_size=1,
            is_active=True,
            metadata_json={
                "available_days": ["Tue", "Wed", "Thu", "Fri", "Sat"],
                "off_days": ["Mon", "Sun"],
            },
        )
        session.add(doctor1)
        session.commit()

        repo = ReservationRepository(session)

        # 3. Test Restaurant Availability & Table Reservation
        now = datetime.now(timezone.utc)
        days_ahead = (1 - now.weekday()) % 7  # 1 = Tuesday
        if days_ahead == 0:
            days_ahead = 7
        tue_date = (now + timedelta(days=days_ahead)).replace(hour=19, minute=30, second=0, microsecond=0)

        # Restaurant queries tables for party of 4
        avail_tables = repo.find_available_resources(
            business_id=rest_biz_id,
            start_time=tue_date,
            end_time=tue_date + timedelta(minutes=90),
            party_size=4,
            resource_type="table",
        )
        assert len(avail_tables) == 1
        assert avail_tables[0].name == "Table 1 (Window Booth)"
        assert avail_tables[0].resource_type == "table"

        # Create restaurant table reservation
        dining_booking = repo.create_reservation_atomic(
            business_id=rest_biz_id,
            customer_name="Rajesh Khanna",
            customer_phone="+91 98111 22233",
            party_size=4,
            start_time=tue_date,
            end_time=tue_date + timedelta(minutes=90),
            resource_type="table",
            resource_id=avail_tables[0].id,
            special_requests="Window booth for family dinner",
        )
        assert dining_booking.id.startswith("TB-")
        assert dining_booking.party_size == 4

        # 4. Test Clinic Doctor Availability & 30-min Appointment
        tue_morning = tue_date.replace(hour=10, minute=0)
        avail_doctors = repo.find_available_resources(
            business_id=clinic_biz_id,
            start_time=tue_morning,
            end_time=tue_morning + timedelta(minutes=30),
            party_size=1,
            resource_type="practitioner",
        )
        assert len(avail_doctors) == 1
        assert avail_doctors[0].name == "Dr. Mehta (Orthodontist)"
        assert avail_doctors[0].resource_type == "practitioner"

        clinic_booking = repo.create_reservation_atomic(
            business_id=clinic_biz_id,
            customer_name="Aarav Verma",
            customer_phone="+91 98222 33344",
            party_size=1,
            start_time=tue_morning,
            end_time=tue_morning + timedelta(minutes=30),
            resource_type="practitioner",
            resource_id=avail_doctors[0].id,
            special_requests="Routine Dental Cleaning & Scaling",
        )
        assert clinic_booking.id.startswith("APT-")
        assert clinic_booking.party_size == 1

        # 5. Doctor Weekly Off (Monday) Blocking
        mon_days_ahead = (0 - now.weekday()) % 7  # 0 = Monday
        if mon_days_ahead == 0:
            mon_days_ahead = 7
        mon_morning = (now + timedelta(days=mon_days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)

        mon_avail_doctors = repo.find_available_resources(
            business_id=clinic_biz_id,
            start_time=mon_morning,
            end_time=mon_morning + timedelta(minutes=30),
            party_size=1,
            resource_type="practitioner",
        )
        assert len(mon_avail_doctors) == 0

        # 6. Verify Complete Domain Isolation
        # Restaurant must NEVER return doctors
        rest_doctors = repo.find_available_resources(
            business_id=rest_biz_id,
            start_time=tue_date,
            end_time=tue_date + timedelta(minutes=90),
            party_size=1,
            resource_type="practitioner",
        )
        assert len(rest_doctors) == 0

        # Clinic must NEVER return dining tables
        clinic_tables = repo.find_available_resources(
            business_id=clinic_biz_id,
            start_time=tue_date,
            end_time=tue_date + timedelta(minutes=90),
            party_size=4,
            resource_type="table",
        )
        assert len(clinic_tables) == 0
