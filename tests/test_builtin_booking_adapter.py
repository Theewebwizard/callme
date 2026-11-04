"""
Deterministic unit and integration test suite for BuiltinBookingAdapter.
Validates:
1. Manifest declarations and multi-domain configuration validation.
2. Domain-specific resource models (Dining, Hotel, Clinic, Service).
3. Authoritative inventory availability and capacity checks.
4. Shared booking lifecycle (Create, Retrieve, Reschedule, Cancel).
5. Concurrency control, double-booking prevention, and transaction rollback.
6. Booking holds, hold expiration, and conversion to confirmed reservations.
7. Explicit waiting lists with FIFO queue positions.
8. Cancellation policies (deadlines, strict rejection, reasons).
9. Strict multi-tenant isolation.
10. Timezone handling and Daylight-Saving Transitions (fall-back & spring-forward).
11. Operating rules (hours, days, lead time, booking window).
12. Dynamic setup wizard and safe demo data seeding.
13. Standard CapabilityType execution dispatch.
"""

import pytest
from datetime import datetime, timezone, timedelta
import zoneinfo

from backend.integrations.adapters.builtin_booking_adapter import (
    BuiltinBookingAdapter,
    DiningTableConfig,
    HotelRoomConfig,
    ClinicRoomConfig,
    PractitionerConfig,
    ServiceStaffConfig,
    ServiceItemConfig,
)
from backend.integrations.models import (
    CapabilityType,
    ExecutionOutcome,
    ExecutionContext,
)
from backend.capabilities.models import AuthoritativeSource
from backend.database.repositories.reservation_repo import (
    ReservationConflictError,
    CancellationPolicyViolation,
)


@pytest.fixture
def make_business(isolate_test_database):
    """Helper fixture to seed business tenant records required by foreign keys."""
    def _create(
        biz_id: str,
        name: str = "Test Business",
        industry: str = "restaurant",
        opening: str = "08:00",
        closing: str = "23:00",
        tz_name: str = "UTC",
    ):
        isolate_test_database.create_business({
            "id": biz_id,
            "name": name,
            "industry": industry,
            "opening_time": opening,
            "closing_time": closing,
            "timezone": tz_name,
        })
        return biz_id
    return _create


# ============================================================================
# 1. Manifest and Configuration Validation
# ============================================================================

def test_manifest_and_metadata():
    adapter = BuiltinBookingAdapter(business_id="test_biz")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "builtin_booking"
    assert manifest.authoritative_source == AuthoritativeSource.BUILTIN_DATABASE
    assert adapter.authoritative_source == AuthoritativeSource.BUILTIN_DATABASE
    assert CapabilityType.CHECK_AVAILABILITY in manifest.supported_capabilities
    assert CapabilityType.CREATE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.GET_BOOKING in manifest.supported_capabilities
    assert CapabilityType.RESCHEDULE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.CANCEL_BOOKING in manifest.supported_capabilities


def test_configuration_validation_success_and_failure():
    adapter = BuiltinBookingAdapter(business_id="test_biz")

    # Valid configs
    assert adapter.validate_configuration({"business_type": "restaurant", "timezone": "UTC"}).passed
    assert adapter.validate_configuration({"business_type": "hotel", "timezone": "America/New_York", "opening_time": "08:00"}).passed
    assert adapter.validate_configuration({"business_type": "clinic", "timezone": "Europe/London"}).passed
    assert adapter.validate_configuration({"business_type": "service", "timezone": "Asia/Kolkata"}).passed

    # Invalid business type
    res_btype = adapter.validate_configuration({"business_type": "spaceship"})
    assert not res_btype.passed
    assert "Invalid business type" in res_btype.details

    # Invalid timezone
    res_tz = adapter.validate_configuration({"business_type": "restaurant", "timezone": "Atlantis/Lost"})
    assert not res_tz.passed
    assert "Invalid IANA timezone" in res_tz.details

    # Invalid hours format
    res_hr = adapter.validate_configuration({"business_type": "restaurant", "opening_time": "25:99"})
    assert not res_hr.passed

    # Negative duration
    res_dur = adapter.validate_configuration({"business_type": "restaurant", "slot_duration_minutes": -30})
    assert not res_dur.passed


# ============================================================================
# 2. Domain-Specific Resource Models & Validation
# ============================================================================

def test_dining_table_config_validation():
    # Valid
    cfg = DiningTableConfig(name="Table 1", seating_area="Patio", min_party_size=2, max_party_size=4, capacity=4)
    cfg.validate()

    # Empty name
    with pytest.raises(ValueError, match="cannot be empty"):
        DiningTableConfig(name="").validate()

    # min > max
    with pytest.raises(ValueError, match="cannot be less than min_party_size"):
        DiningTableConfig(name="T2", min_party_size=4, max_party_size=2).validate()

    # capacity < max
    with pytest.raises(ValueError, match="cannot be less than max_party_size"):
        DiningTableConfig(name="T3", min_party_size=2, max_party_size=6, capacity=4).validate()


def test_hotel_room_config_validation():
    # Valid
    cfg = HotelRoomConfig(room_number="101", room_type="deluxe", max_occupancy=3)
    cfg.validate()

    # Invalid room type
    with pytest.raises(ValueError, match="Invalid room_type"):
        HotelRoomConfig(room_number="102", room_type="igloo").validate()

    # Invalid occupancy
    with pytest.raises(ValueError, match="max_occupancy must be at least 1"):
        HotelRoomConfig(room_number="103", room_type="standard", max_occupancy=0).validate()


def test_clinic_practitioner_and_service_validation():
    # Valid clinic room
    ClinicRoomConfig(name="Exam 1", room_number="101").validate()
    with pytest.raises(ValueError, match="cannot be empty"):
        ClinicRoomConfig(name="", room_number="101").validate()

    # Valid practitioner
    PractitionerConfig(name="Dr. Smith", license_number="LIC-123", slot_duration_minutes=20).validate()
    with pytest.raises(ValueError, match="Slot duration must be at least 5 minutes"):
        PractitionerConfig(name="Dr. Smith", license_number="LIC-123", slot_duration_minutes=2).validate()

    # Valid service
    ServiceItemConfig(name="Haircut", duration_minutes=45, price_minor=3500).validate()
    with pytest.raises(ValueError, match="Service price cannot be negative"):
        ServiceItemConfig(name="Haircut", price_minor=-100).validate()


# ============================================================================
# 3. Restaurant Tables: Availability, Turnover Buffers & Booking
# ============================================================================

def test_restaurant_tables_lifecycle_and_turnover_buffer(make_business):
    biz_id = make_business("biz_dining_test", name="Bistro Alpha", industry="restaurant", opening="10:00", closing="23:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={
            "business_type": "restaurant",
            "timezone": "UTC",
            "opening_time": "10:00",
            "closing_time": "23:00",
            "slot_duration_minutes": 90,
            "turnover_buffer_minutes": 15,
        },
    )

    # Register 2 tables: Patio (2-top) and Dining Room (4-top)
    t1 = adapter.register_dining_table(
        name="Table 1 (Patio)",
        seating_area="Patio",
        min_party_size=1,
        max_party_size=2,
        capacity=2,
    )
    t2 = adapter.register_dining_table(
        name="Table 2 (Main Hall)",
        seating_area="Main Hall",
        min_party_size=2,
        max_party_size=4,
        capacity=4,
    )

    base_time = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_time = base_time + timedelta(minutes=90)

    # Check availability for party of 2
    avail = adapter.check_availability(start_time=base_time, end_time=end_time, party_size=2)
    assert avail["available"] is True
    assert avail["count"] == 2

    # Check availability for party of 4 (only Table 2 matches)
    avail_4 = adapter.check_availability(start_time=base_time, end_time=end_time, party_size=4)
    assert avail_4["available"] is True
    assert avail_4["count"] == 1
    assert avail_4["available_resources"][0]["name"] == "Table 2 (Main Hall)"

    # Book Table 1
    booking = adapter.create_reservation(
        customer_name="Gordon Ramsay",
        customer_phone="+1234567890",
        party_size=2,
        start_time=base_time,
        end_time=end_time,
        resource_id=t1["id"],
    )
    assert booking["status"] == "confirmed"
    assert booking["booking_id"].startswith("TB-")
    assert booking["resource_name"] == "Table 1 (Patio)"

    # Buffer test: Attempting to book Table 1 10 minutes after previous booking ends
    # (violating the 15-minute turnover buffer) must be rejected
    conflict_start = end_time + timedelta(minutes=10)
    conflict_end = conflict_start + timedelta(minutes=90)

    avail_buffer = adapter.check_availability(
        start_time=conflict_start,
        end_time=conflict_end,
        party_size=2,
        section="Patio",
    )
    assert avail_buffer["available"] is False

    # After buffer (e.g. 20 minutes after end_time), Table 1 is available again
    clean_start = end_time + timedelta(minutes=20)
    clean_end = clean_start + timedelta(minutes=90)
    avail_clean = adapter.check_availability(
        start_time=clean_start,
        end_time=clean_end,
        party_size=2,
        section="Patio",
    )
    assert avail_clean["available"] is True


# ============================================================================
# 4. Hotel Rooms: Room Types & Occupancy
# ============================================================================

def test_hotel_rooms_inventory_and_occupancy(make_business):
    biz_id = make_business("biz_hotel_test", name="The Grand Hotel", industry="hotel", opening="00:00", closing="23:59")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={
            "business_type": "hotel",
            "timezone": "UTC",
            "opening_time": "00:00",
            "closing_time": "23:59",
            "slot_duration_minutes": 1440,
            "turnover_buffer_minutes": 120,
        },
    )

    r101 = adapter.register_hotel_room("101", room_type="standard", floor=1, max_occupancy=2)
    r201 = adapter.register_hotel_room("201", room_type="suite", floor=2, max_occupancy=4)

    check_in = datetime.now(timezone.utc).replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=2)
    check_out = check_in + timedelta(days=2)

    # 3 guests -> only suite 201 has capacity
    avail_3 = adapter.check_availability(start_time=check_in, end_time=check_out, party_size=3, resource_type="room")
    assert avail_3["available"] is True
    assert avail_3["count"] == 1
    assert avail_3["available_resources"][0]["name"] == "Room 201 (Suite)"

    # Book Room 201
    booking = adapter.create_reservation(
        customer_name="Sherlock Holmes",
        customer_phone="+442079460912",
        party_size=3,
        start_time=check_in,
        end_time=check_out,
        resource_id=r201["id"],
        resource_type="room",
    )
    assert booking["booking_id"].startswith("HTL-")
    assert booking["status"] == "confirmed"

    # Verify Room 201 is now booked for those dates
    avail_again = adapter.check_availability(start_time=check_in, end_time=check_out, party_size=3, resource_type="room")
    assert avail_again["available"] is False


# ============================================================================
# 5. Clinic Rooms and Practitioners
# ============================================================================

def test_clinic_practitioners_and_sanitization(make_business):
    biz_id = make_business("biz_clinic_test", name="Beacon Clinic", industry="healthcare", opening="08:00", closing="18:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={
            "business_type": "clinic",
            "timezone": "UTC",
            "opening_time": "08:00",
            "closing_time": "18:00",
            "slot_duration_minutes": 30,
            "turnover_buffer_minutes": 10,
        },
    )

    c1 = adapter.register_clinic_room("Consultation Room A", room_number="101")
    doc = adapter.register_practitioner("Dr. Watson", license_number="DOC-1234")

    start_slot = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_slot = start_slot + timedelta(minutes=30)

    booking = adapter.create_reservation(
        customer_name="John Doe",
        customer_phone="+15551234567",
        party_size=1,
        start_time=start_slot,
        end_time=end_slot,
        resource_id=c1["id"],
        resource_type="clinic_room",
    )
    assert booking["booking_id"].startswith("CLN-")

    # Conflict within sanitization buffer
    sanitization_conflict = start_slot + timedelta(minutes=35)
    with pytest.raises(ReservationConflictError):
        adapter.create_reservation(
            customer_name="Jane Doe",
            customer_phone="+15559876543",
            party_size=1,
            start_time=sanitization_conflict,
            end_time=sanitization_conflict + timedelta(minutes=30),
            resource_id=c1["id"],
            resource_type="clinic_room",
        )


# ============================================================================
# 6. Service Staff & Services
# ============================================================================

def test_service_staff_lifecycle(make_business):
    biz_id = make_business("biz_salon_test", name="Luxe Salon", industry="service", opening="09:00", closing="19:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={
            "business_type": "service",
            "timezone": "UTC",
            "opening_time": "09:00",
            "closing_time": "19:00",
            "slot_duration_minutes": 45,
            "turnover_buffer_minutes": 15,
        },
    )

    stylist = adapter.register_service_staff("Alice Senior Stylist", services_offered=["Haircut", "Color"])

    start_dt = datetime.now(timezone.utc).replace(hour=11, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_dt = start_dt + timedelta(minutes=45)

    booking = adapter.create_reservation(
        customer_name="Clara Oswald",
        customer_phone="+447700900123",
        party_size=1,
        start_time=start_dt,
        end_time=end_dt,
        resource_id=stylist["id"],
        resource_type="service_staff",
    )
    assert booking["booking_id"].startswith("SRV-")
    assert booking["status"] == "confirmed"


# ============================================================================
# 7. Concurrency Control, Conflict Detection, and Rollback Behavior
# ============================================================================

def test_concurrent_booking_rollback_and_truthful_state(make_business):
    """
    Simulates concurrent booking attempts on the same inventory slot.
    The first transaction commits; the second must raise ReservationConflictError
    and roll back cleanly, never creating an orphan or confirmed duplicate.
    """
    biz_id = make_business("biz_concurrency_test", opening="08:00", closing="22:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={"timezone": "UTC", "opening_time": "08:00", "closing_time": "22:00"},
    )
    t1 = adapter.register_dining_table("Table 10", min_party_size=2, max_party_size=4, capacity=4)

    start_time = datetime.now(timezone.utc).replace(hour=19, minute=0, second=0, microsecond=0) + timedelta(days=3)
    end_time = start_time + timedelta(minutes=90)

    # First request books Table 10
    first_booking = adapter.create_reservation(
        customer_name="Alice First",
        customer_phone="+1111111111",
        party_size=2,
        start_time=start_time,
        end_time=end_time,
        resource_id=t1["id"],
        idempotency_key="key_concurrency_1",
    )
    assert first_booking["status"] == "confirmed"
    confirmed_id = first_booking["booking_id"]

    # Verify first booking exists in database
    retrieved = adapter.get_reservation(confirmed_id)
    assert retrieved is not None
    assert retrieved["id"] == confirmed_id

    # Second concurrent attempt on the exact same resource
    with pytest.raises(ReservationConflictError) as exc_info:
        adapter.create_reservation(
            customer_name="Bob Second",
            customer_phone="+2222222222",
            party_size=2,
            start_time=start_time,
            end_time=end_time,
            resource_id=t1["id"],
            idempotency_key="key_concurrency_2",
        )
    assert "already reserved" in str(exc_info.value) or "No available" in str(exc_info.value)

    # Idempotent retry of first request with same key returns original confirmed booking
    replay = adapter.create_reservation(
        customer_name="Alice First",
        customer_phone="+1111111111",
        party_size=2,
        start_time=start_time,
        end_time=end_time,
        resource_id=t1["id"],
        idempotency_key="key_concurrency_1",
    )
    assert replay["booking_id"] == confirmed_id


# ============================================================================
# 8. Temporary Holds and Expiration
# ============================================================================

def test_booking_holds_expiration_and_confirmation(make_business):
    biz_id = make_business("biz_holds_test", opening="08:00", closing="22:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={"timezone": "UTC", "opening_time": "08:00", "closing_time": "22:00"},
    )
    res = adapter.register_dining_table("Table VIP", capacity=4)

    start_time = datetime.now(timezone.utc).replace(hour=20, minute=0, second=0, microsecond=0) + timedelta(days=2)
    end_time = start_time + timedelta(minutes=90)

    # 1. Place a 15-minute hold
    hold = adapter.create_hold(
        customer_name="Grace Hopper",
        customer_phone="+19998887777",
        party_size=2,
        start_time=start_time,
        end_time=end_time,
        hold_minutes=15,
        resource_id=res["id"],
    )
    assert hold["status"] == "hold"
    assert hold["hold_expires_at"] is not None

    # While hold is active, slot is unavailable to other requests
    avail_during_hold = adapter.check_availability(start_time=start_time, end_time=end_time, party_size=2)
    assert avail_during_hold["available"] is False

    # 2. Confirm hold before expiration -> transitions to confirmed
    confirmed = adapter.confirm_hold(hold["id"], customer_phone="+19998887777")
    assert confirmed["status"] == "confirmed"
    assert confirmed["hold_expires_at"] is None

    # 3. Test expired hold
    hold_expired = adapter.create_hold(
        customer_name="Expired User",
        customer_phone="+18887776666",
        party_size=2,
        start_time=start_time + timedelta(days=1),
        end_time=end_time + timedelta(days=1),
        hold_minutes=-5,  # already in the past
        resource_id=res["id"],
    )
    # Confirming expired hold must fail and transition to cancelled
    with pytest.raises(ReservationConflictError, match="expired"):
        adapter.confirm_hold(hold_expired["id"])

    # Verify inventory was freed
    avail_after_expiry = adapter.check_availability(
        start_time=start_time + timedelta(days=1),
        end_time=end_time + timedelta(days=1),
        party_size=2,
    )
    assert avail_after_expiry["available"] is True


# ============================================================================
# 9. Rescheduling and Audit History
# ============================================================================

def test_reschedule_with_audit_history(make_business):
    biz_id = make_business("biz_reschedule_test", opening="08:00", closing="22:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={"timezone": "UTC", "opening_time": "08:00", "closing_time": "22:00"},
    )
    res = adapter.register_dining_table("Table R1", capacity=4)

    start_time = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=2)
    end_time = start_time + timedelta(minutes=90)

    booking = adapter.create_reservation(
        customer_name="Alan Turing",
        customer_phone="+44123456789",
        party_size=2,
        start_time=start_time,
        end_time=end_time,
        resource_id=res["id"],
    )

    # Reschedule to next day
    new_start = start_time + timedelta(days=1)
    new_end = end_time + timedelta(days=1)

    rescheduled = adapter.reschedule_reservation(
        reservation_id=booking["booking_id"],
        new_start_time=new_start,
        new_end_time=new_end,
        customer_phone="+44123456789",
    )
    assert rescheduled["id"] == booking["booking_id"]
    assert rescheduled["start_time"] == new_start.isoformat()
    assert rescheduled["rescheduled_from_id"] == booking["booking_id"]

    # Verify audit history in metadata
    meta = rescheduled.get("metadata", {})
    history = meta.get("reschedule_history", [])
    assert len(history) == 1
    assert history[0]["previous_start"] == start_time.isoformat()

    # Original time slot should now be free
    avail_original = adapter.check_availability(start_time=start_time, end_time=end_time, party_size=2)
    assert avail_original["available"] is True


# ============================================================================
# 10. Cancellation Policies
# ============================================================================

def test_cancellation_policies_strict_and_free(make_business):
    # Strict cancellation with 24-hour deadline
    biz_id = make_business("biz_cancel_strict", opening="00:00", closing="23:59")
    adapter_strict = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={
            "timezone": "UTC",
            "opening_time": "00:00",
            "closing_time": "23:59",
            "cancellation_deadline_hours": 24,
            "strict_cancellation": True,
        },
    )
    t = adapter_strict.register_dining_table("Table C", capacity=4)

    # Booking 3 hours in future (within 24h deadline)
    soon_start = datetime.now(timezone.utc) + timedelta(hours=3)
    soon_booking = adapter_strict.create_reservation(
        customer_name="Late Canceller",
        customer_phone="+1234567890",
        party_size=2,
        start_time=soon_start,
        end_time=soon_start + timedelta(minutes=60),
        resource_id=t["id"],
    )

    # Cancelling within deadline raises CancellationPolicyViolation under strict policy
    with pytest.raises(CancellationPolicyViolation, match="Cancellation deadline"):
        adapter_strict.cancel_reservation(
            reservation_id=soon_booking["booking_id"],
            customer_phone="+1234567890",
            reason="Change of plans",
        )

    # Booking 48 hours in future (outside 24h deadline) succeeds
    far_start = datetime.now(timezone.utc) + timedelta(hours=48)
    far_booking = adapter_strict.create_reservation(
        customer_name="Early Canceller",
        customer_phone="+1234567890",
        party_size=2,
        start_time=far_start,
        end_time=far_start + timedelta(minutes=60),
        resource_id=t["id"],
    )
    assert adapter_strict.cancel_reservation(
        reservation_id=far_booking["booking_id"],
        customer_phone="+1234567890",
        reason="Advance notice cancellation",
    ) is True

    record = adapter_strict.get_reservation(far_booking["booking_id"])
    assert record["status"] == "cancelled"
    assert record["metadata"].get("cancellation_reason") == "Advance notice cancellation"


# ============================================================================
# 11. Waiting Lists
# ============================================================================

def test_waiting_list_fifo_queue(make_business):
    biz_id = make_business("biz_waitlist_test", opening="08:00", closing="23:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={"timezone": "UTC", "allow_waitlist": True},
    )

    req_time = datetime.now(timezone.utc).replace(hour=20, minute=0, second=0, microsecond=0) + timedelta(days=2)

    # Customer 1 joins waitlist
    w1 = adapter.add_to_waitlist(
        customer_name="Waitlist Guest 1",
        customer_phone="+1000000001",
        requested_time=req_time,
        party_size=2,
        resource_type="table",
        notes="Window preference",
    )
    assert w1["id"].startswith("WL-")
    assert w1["status"] == "waitlisted"
    assert w1["metadata"]["waitlist_position"] == 1

    # Customer 2 joins waitlist
    w2 = adapter.add_to_waitlist(
        customer_name="Waitlist Guest 2",
        customer_phone="+1000000002",
        requested_time=req_time,
        party_size=4,
        resource_type="table",
    )
    assert w2["metadata"]["waitlist_position"] == 2

    # Query waitlist
    queue = adapter.get_waitlist(resource_type="table")
    assert len(queue) == 2
    assert queue[0]["id"] == w1["id"]
    assert queue[1]["id"] == w2["id"]


# ============================================================================
# 12. Strict Multi-Tenant Isolation
# ============================================================================

def test_multi_tenant_isolation(make_business):
    alpha_id = make_business("biz_alpha_tenant", name="Alpha Bistro")
    beta_id = make_business("biz_beta_tenant", name="Beta Bistro")

    adapter_alpha = BuiltinBookingAdapter(business_id=alpha_id)
    adapter_beta = BuiltinBookingAdapter(business_id=beta_id)

    # Alpha registers a resource and makes a booking
    t_alpha = adapter_alpha.register_dining_table("Alpha Table 1", capacity=4)
    start_dt = datetime.now(timezone.utc).replace(hour=19, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_dt = start_dt + timedelta(minutes=90)

    booking_alpha = adapter_alpha.create_reservation(
        customer_name="Alpha VIP",
        customer_phone="+1112223333",
        party_size=2,
        start_time=start_dt,
        end_time=end_dt,
        resource_id=t_alpha["id"],
    )

    # Beta attempts to view Alpha's reservation -> returns None
    assert adapter_beta.get_reservation(booking_alpha["booking_id"]) is None

    # Beta attempts to cancel Alpha's reservation -> returns False
    assert adapter_beta.cancel_reservation(booking_alpha["booking_id"]) is False

    # Beta discovers resources -> cannot see Alpha's table
    beta_resources = adapter_beta.discover_resources()
    assert all(r.resource_id != t_alpha["id"] for r in beta_resources)


# ============================================================================
# 13. Daylight-Saving Transitions (DST)
# ============================================================================

def test_daylight_saving_transitions_handling():
    """
    Validates timezone awareness and explicit rules for daylight-saving transitions
    in America/New_York (US Eastern Time):
    - Fall-back: clocks move from 02:00 to 01:00, 01:30 AM occurs twice.
      Rule: fold=0 selected and documented.
    - Spring-forward: clocks jump from 02:00 to 03:00, 02:30 AM does not exist.
      Rule: detect gap and shift forward to valid operational time (03:30 AM).
    """
    adapter = BuiltinBookingAdapter(
        business_id="biz_dst_test",
        configuration={"timezone": "America/New_York"},
    )

    # 1. Fall Back Overlap (November 1, 2026 at 01:30 AM in America/New_York)
    fall_back_dt = datetime(2026, 11, 1, 1, 30)
    utc_dt, meta_fb = adapter.handle_dst_transitions(fall_back_dt, "America/New_York")
    assert meta_fb["dst_transition"] == "fall_back_overlap"
    assert meta_fb["resolution"] == "standard_fold_0_selected"
    assert utc_dt.tzinfo == timezone.utc

    # 2. Spring Forward Gap (March 8, 2026 at 02:30 AM in America/New_York)
    spring_forward_dt = datetime(2026, 3, 8, 2, 30)
    utc_gap, meta_sf = adapter.handle_dst_transitions(spring_forward_dt, "America/New_York")
    assert meta_sf["dst_transition"] == "spring_forward_gap"
    assert meta_sf["gap_minutes"] == 60
    assert "03:30" in meta_sf["adjusted_wall_clock"]


# ============================================================================
# 14. Operating Rules: Hours, Lead Time, and Booking Windows
# ============================================================================

def test_operating_rules_enforcement():
    adapter = BuiltinBookingAdapter(
        business_id="biz_rules_test",
        configuration={
            "timezone": "UTC",
            "opening_time": "11:00",
            "closing_time": "22:00",
            "operating_days": [0, 1, 2, 3, 4],  # Monday to Friday only (closed Sat, Sun)
            "min_lead_time_minutes": 60,
            "max_booking_window_days": 30,
            "min_party_size": 2,
            "max_party_size": 10,
        },
    )

    now = datetime.now(timezone.utc)

    # 1. Outside hours (09:00 AM on business with 11:00 opening)
    adapter_closed = BuiltinBookingAdapter(
        business_id="biz_rules_test_closed",
        configuration={
            "timezone": "UTC",
            "opening_time": "11:00",
            "closing_time": "22:00",
            "operating_days": [0, 1, 2, 3, 4, 5, 6],
        },
    )
    outside_hours = (now + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
    allowed, reason = adapter_closed.is_within_operating_rules(outside_hours, outside_hours + timedelta(minutes=60), 4)
    assert not allowed
    assert "outside operating hours" in reason

    # 2. Insufficient lead time (10 minutes from now on business with 24h opening and 60m lead time)
    adapter_lead = BuiltinBookingAdapter(
        business_id="biz_rules_test_lead",
        configuration={
            "timezone": "UTC",
            "opening_time": "00:00",
            "closing_time": "23:59",
            "operating_days": [0, 1, 2, 3, 4, 5, 6],
            "min_lead_time_minutes": 60,
        },
    )
    soon = now + timedelta(minutes=10)
    allowed_lead, reason_lead = adapter_lead.is_within_operating_rules(soon, soon + timedelta(minutes=60), 4)
    assert not allowed_lead
    assert "advance notice" in reason_lead

    # 3. Beyond booking window (45 days in future)
    far = (now + timedelta(days=45)).replace(hour=14, minute=0, second=0, microsecond=0)
    while far.weekday() > 4:
        far += timedelta(days=1)
    allowed_win, reason_win = adapter.is_within_operating_rules(far, far + timedelta(minutes=60), 4)
    assert not allowed_win
    assert "advance" in reason_win

    # 4. Party size violation
    valid_time = (now + timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)
    # Ensure it lands on a weekday (0..4)
    while valid_time.weekday() > 4:
        valid_time += timedelta(days=1)

    allowed_party, reason_party = adapter.is_within_operating_rules(valid_time, valid_time + timedelta(minutes=60), 12)
    assert not allowed_party
    assert "must be between" in reason_party


# ============================================================================
# 15. Setup Wizard and Safe Demo Data Seeding
# ============================================================================

def test_setup_wizard_steps():
    adapter = BuiltinBookingAdapter(business_id="biz_wizard_test")

    dining_steps = adapter.get_setup_wizard_steps("restaurant")
    assert any("dining_rules" in s["step_id"] for s in dining_steps)

    hotel_steps = adapter.get_setup_wizard_steps("hotel")
    assert any("hotel_rules" in s["step_id"] for s in hotel_steps)

    clinic_steps = adapter.get_setup_wizard_steps("clinic")
    assert any("clinical_rules" in s["step_id"] for s in clinic_steps)

    service_steps = adapter.get_setup_wizard_steps("service")
    assert any("service_rules" in s["step_id"] for s in service_steps)


def test_safe_demo_inventory_seeding(make_business):
    biz_id = make_business("biz_demo_test")
    adapter = BuiltinBookingAdapter(business_id=biz_id)

    # Safety check: seeding in production environment or with is_demo=False MUST be rejected
    with pytest.raises(PermissionError, match="designated demo environment"):
        adapter.seed_demo_data(business_type="restaurant", is_demo=False, environment="production")

    with pytest.raises(PermissionError, match="designated demo environment"):
        adapter.seed_demo_data(business_type="restaurant", is_demo=True, environment="production")

    # Seeding in demo environment succeeds
    res_dining = adapter.seed_demo_data(business_type="restaurant", is_demo=True, environment="demo")
    assert res_dining["status"] == "seeded"
    assert res_dining["resources_created"] == 5

    # Resources are now in active inventory
    resources = adapter.discover_resources()
    assert len(resources) == 5
    assert any("Patio" in r.name for r in resources)


# ============================================================================
# 16. Standard CapabilityType Execution Dispatch
# ============================================================================

def test_execute_dispatcher_all_operations(make_business):
    biz_id = make_business("biz_exec_test", opening="08:00", closing="22:00")
    adapter = BuiltinBookingAdapter(
        business_id=biz_id,
        configuration={"timezone": "UTC", "opening_time": "08:00", "closing_time": "22:00"},
    )
    table = adapter.register_dining_table("Table Dispatch", capacity=4)
    ctx = ExecutionContext(tenant_id=biz_id, idempotency_key="dispatch_idem_1")

    base_time = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
    end_time = base_time + timedelta(minutes=90)

    # 1. CHECK_AVAILABILITY
    res_avail = adapter.execute(
        operation=CapabilityType.CHECK_AVAILABILITY,
        input_data={
            "start_time": base_time.isoformat(),
            "end_time": end_time.isoformat(),
            "party_size": 2,
        },
        context=ctx,
    )
    assert res_avail.success is True
    assert res_avail.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert res_avail.data["available"] is True

    # 2. CREATE_BOOKING
    res_create = adapter.execute(
        operation=CapabilityType.CREATE_BOOKING,
        input_data={
            "customer_name": "Katherine Johnson",
            "customer_phone": "+14445556666",
            "party_size": 2,
            "start_time": base_time.isoformat(),
            "end_time": end_time.isoformat(),
            "resource_id": table["id"],
        },
        context=ctx,
    )
    assert res_create.success is True
    assert res_create.outcome == ExecutionOutcome.OPERATION_COMPLETED
    booking_id = res_create.data["booking_id"]

    # 3. GET_BOOKING
    res_get = adapter.execute(
        operation=CapabilityType.GET_BOOKING,
        input_data={"booking_id": booking_id},
        context=ctx,
    )
    assert res_get.success is True
    assert res_get.data["id"] == booking_id

    # 4. RESCHEDULE_BOOKING
    new_start = base_time + timedelta(days=1)
    new_end = end_time + timedelta(days=1)
    res_resched = adapter.execute(
        operation=CapabilityType.RESCHEDULE_BOOKING,
        input_data={
            "booking_id": booking_id,
            "new_start_time": new_start.isoformat(),
            "new_end_time": new_end.isoformat(),
            "customer_phone": "+14445556666",
        },
        context=ctx,
    )
    assert res_resched.success is True
    assert res_resched.outcome == ExecutionOutcome.OPERATION_COMPLETED

    # 5. CANCEL_BOOKING
    res_cancel = adapter.execute(
        operation=CapabilityType.CANCEL_BOOKING,
        input_data={
            "booking_id": booking_id,
            "customer_phone": "+14445556666",
            "reason": "Customer request",
        },
        context=ctx,
    )
    assert res_cancel.success is True
    assert res_cancel.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert res_cancel.data["status"] == "cancelled"
