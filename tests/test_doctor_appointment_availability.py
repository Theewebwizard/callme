"""
Targeted tests for Doctor Appointment Scheduling Parity:
1. Monday-Sunday week scheduling
2. 30-minute slot increments and atomic reservation
3. Blocking days based on doctor available days
4. Resource metadata and available_days update via API
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.database.engine import session_scope
from backend.database.models import ReservableResource, Reservation
from backend.database.repositories.resource_repo import ResourceRepository
from backend.database.repositories.reservation_repo import ReservationRepository
from backend.database.service import get_database_service


@pytest.fixture
def db_service():
    return get_database_service()


def test_doctor_available_days_filtering(db_service):
    """Verify that doctor resources are excluded on their off days."""
    with session_scope(db_service.session_factory) as session:
        resv_repo = ReservationRepository(session)

        # Retrieve Dr. Sharma from seeded test database
        sharma = session.query(ReservableResource).filter(
            ReservableResource.business_id == "biz_apex_dental",
            ReservableResource.name.like("%Sharma%"),
        ).first()
        assert sharma is not None, "Dr. Sharma should be seeded in biz_apex_dental"

        # Ensure available_days is Mon, Wed, Fri, Sat
        sharma.metadata_json = {"available_days": ["Mon", "Wed", "Fri", "Sat"], "slot_duration_minutes": 30}
        session.flush()

        # Next Monday: 2026-11-09 10:00 UTC (Sharma should be available)
        monday_10am = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        monday_1030am = datetime(2026, 11, 9, 10, 30, tzinfo=timezone.utc)

        avail_monday = resv_repo.find_available_resources(
            business_id="biz_apex_dental",
            start_time=monday_10am,
            end_time=monday_1030am,
            party_size=1,
            resource_type="practitioner",
        )
        sharma_ids_monday = [r.id for r in avail_monday if "sharma" in r.name.lower()]
        assert len(sharma_ids_monday) > 0, "Dr. Sharma must be available on Monday"

        # Next Tuesday: 2026-11-10 10:00 UTC (Sharma is off, must be excluded)
        tuesday_10am = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        tuesday_1030am = datetime(2026, 11, 10, 10, 30, tzinfo=timezone.utc)

        avail_tuesday = resv_repo.find_available_resources(
            business_id="biz_apex_dental",
            start_time=tuesday_10am,
            end_time=tuesday_1030am,
            party_size=1,
            resource_type="practitioner",
        )
        sharma_ids_tuesday = [r.id for r in avail_tuesday if "sharma" in r.name.lower()]
        assert len(sharma_ids_tuesday) == 0, "Dr. Sharma must be BLOCKED on Tuesday"


def test_doctor_30_min_slot_atomic_booking(db_service):
    """Verify booking a 30-minute consultation slot prevents double-booking."""
    with session_scope(db_service.session_factory) as session:
        sharma = session.query(ReservableResource).filter(
            ReservableResource.business_id == "biz_apex_dental",
            ReservableResource.name.like("%Sharma%"),
        ).first()
        assert sharma is not None
        sharma_id = sharma.id

    start_dt = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)  # Monday
    end_dt = datetime(2026, 11, 9, 11, 30, tzinfo=timezone.utc)

    # 1. Book first patient
    booking = db_service.create_reservation_atomic(
        business_id="biz_apex_dental",
        customer_name="Priya Sharma",
        customer_phone="+919876543210",
        party_size=1,
        start_time=start_dt,
        end_time=end_dt,
        resource_id=sharma_id,
        resource_type="practitioner",
        special_requests="Routine orthodontic checkup",
        status="confirmed",
    )
    assert booking["id"] is not None
    assert booking["status"] == "confirmed"

    # 2. Attempt overlapping booking for the same 30m slot (must raise conflict)
    with pytest.raises(Exception):
        db_service.create_reservation_atomic(
            business_id="biz_apex_dental",
            customer_name="Rohan Verma",
            customer_phone="+919876543211",
            party_size=1,
            start_time=start_dt,
            end_time=end_dt,
            resource_id=sharma_id,
            resource_type="practitioner",
            status="confirmed",
        )

    # 3. Cancel the test booking
    cancelled = db_service.cancel_reservation("biz_apex_dental", booking["id"], customer_phone="+919876543210")
    assert cancelled is True


def test_update_doctor_schedule_metadata(db_service):
    """Verify that updating a doctor's schedule metadata is persisted."""
    with session_scope(db_service.session_factory) as session:
        sharma = session.query(ReservableResource).filter(
            ReservableResource.business_id == "biz_apex_dental",
            ReservableResource.name.like("%Sharma%"),
        ).first()
        assert sharma is not None
        sharma_id = sharma.id

    updated = db_service.update_resource(
        business_id="biz_apex_dental",
        resource_id=sharma_id,
        updates={
            "metadata": {
                "available_days": ["Mon", "Wed", "Fri", "Sat"],
                "slot_duration_minutes": 30,
                "specialization": "Senior Orthodontist",
            }
        },
    )
    assert updated is not None
    assert updated["metadata"]["available_days"] == ["Mon", "Wed", "Fri", "Sat"]
    assert updated["metadata"]["slot_duration_minutes"] == 30
