"""
Unit and integration tests for:
1. Hotel room booking tools registration (check_room_availability, create_room_booking)
2. Industry normalization map (hotel vs restaurant)
3. Automated Token Refresh endpoint (POST /api/businesses/refresh)
4. First-party reservation creation, listing, and cancellation
5. Capability wizard caching speed and resilience
"""

import pytest
import time
from fastapi.testclient import TestClient

from backend.main import app
from backend.tools.base import INDUSTRY_NORMALIZATION_MAP, normalize_industry_name
from backend.database.seed_data import INITIAL_TOOLS, INITIAL_BUSINESSES
from backend.tools.registry import build_default_tool_registry
from backend.tools.implementations.hospitality import (
    handle_check_room_availability,
    handle_create_room_booking,
    format_hotel_reservation_summary,
)
from backend.tools.definitions import (
    CheckRoomAvailabilityInput,
    CreateRoomBookingInput,
)
from backend.auth import create_access_token, ROLE_BUSINESS_OWNER
from backend.database.service import get_database_service
from backend.capabilities.wizard import get_setup_wizard, invalidate_capability_cache


@pytest.fixture
def client():
    return TestClient(app)


def test_industry_normalization_hotel():
    """Verify hotel variants map to 'hotel' and restaurant maps to 'restaurant'."""
    assert normalize_industry_name("hotel") == "hotel"
    assert normalize_industry_name("resort") == "hotel"
    assert normalize_industry_name("Hotel & Resort") == "hotel"
    assert normalize_industry_name("lodging") == "hotel"
    assert normalize_industry_name("hospitality") == "hotel"
    assert normalize_industry_name("inn") == "hotel"
    assert normalize_industry_name("motel") == "hotel"
    assert normalize_industry_name("restaurant") == "restaurant"
    assert normalize_industry_name("cafe") == "restaurant"


def test_hotel_tools_in_initial_tools():
    """Verify check_room_availability and create_room_booking are in INITIAL_TOOLS."""
    assert "check_room_availability" in INITIAL_TOOLS
    assert "create_room_booking" in INITIAL_TOOLS

    room_avail = INITIAL_TOOLS["check_room_availability"]
    assert room_avail["category"] == "Hospitality & Lodging"

    room_book = INITIAL_TOOLS["create_room_booking"]
    assert room_book["category"] == "Hospitality & Lodging"


def test_tool_registry_hotel_tools():
    """Verify default tool registry builds check_room_availability and create_room_booking."""
    reg = build_default_tool_registry()
    assert reg.get_tool("check_room_availability") is not None
    assert reg.get_tool("create_room_booking") is not None

    hotel_tools = reg.get_tools_for_industry("hotel")
    hotel_ids = [t.id for t in hotel_tools]
    assert "check_room_availability" in hotel_ids
    assert "create_room_booking" in hotel_ids
    assert "check_table_availability" not in hotel_ids
    assert "create_table_booking" not in hotel_ids


def test_handle_check_room_availability():
    """Test check_room_availability execution."""
    input_data = CheckRoomAvailabilityInput(
        check_in_date="2026-11-01",
        check_out_date="2026-11-04",
        room_type="Deluxe Suite",
        guests_count=2,
    )
    res = handle_check_room_availability(
        input_data=input_data,
        business_config={"id": "biz_grand_hotel", "name": "The Grand Azure Resort"},
    )
    assert res.success is True
    assert res.data["available"] is True
    assert res.data["check_in_date"] == "2026-11-01"
    assert res.data["check_out_date"] == "2026-11-04"


def test_handle_create_room_booking():
    """Test create_room_booking execution."""
    input_data = CreateRoomBookingInput(
        check_in_date="2026-12-10",
        check_out_date="2026-12-15",
        guest_name="Lady Eleanor",
        guest_phone="+14155558899",
        guest_email="eleanor@example.com",
        room_type="Executive Suite",
        guests_count=2,
        special_requests="High floor with balcony",
    )
    res = handle_create_room_booking(
        input_data=input_data,
        business_config={"id": "biz_grand_hotel", "name": "The Grand Azure Resort"},
    )
    assert res.success is True
    assert "booking_reference" in res.data
    assert res.data["guest_name"] == "Lady Eleanor"
    assert "High floor with balcony" in res.data["special_requests"]


def test_token_refresh_endpoint(client):
    """Test POST /api/businesses/refresh generates a fresh valid token."""
    # 1. Unauthenticated request must fail
    res_unauth = client.post("/api/businesses/refresh")
    assert res_unauth.status_code in (401, 403)

    # 2. Authenticated request with valid token
    valid_token = create_access_token(subject="biz_spice_garden", business_id="biz_spice_garden", role=ROLE_BUSINESS_OWNER)
    res = client.post(
        "/api/businesses/refresh",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["business_id"] == "biz_spice_garden"
    assert data["expires_in"] == 3600

    # 3. New token must work on authenticated endpoint
    new_token = data["access_token"]
    res_auth = client.get(
        "/api/businesses/biz_spice_garden/tools",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert res_auth.status_code == 200


def test_first_party_reservation_api(client):
    """Test creating, listing, and cancelling reservations via capabilities router."""
    token = create_access_token(subject="biz_spice_garden", business_id="biz_spice_garden", role=ROLE_BUSINESS_OWNER)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a reservation
    payload = {
        "customer_name": "Test Guest Marcus",
        "customer_phone": "+14155554321",
        "party_size": 4,
        "start_time": "2026-10-29T19:30:00",
        "end_time": "2026-10-29T21:30:00",
        "resource_type": "table",
        "special_requests": "Window booth preferred",
        "status": "confirmed",
    }
    create_res = client.post(
        "/api/businesses/biz_spice_garden/reservations",
        json=payload,
        headers=headers,
    )
    assert create_res.status_code == 200
    booking_data = create_res.json()
    assert booking_data["customer_name"] == "Test Guest Marcus"
    assert booking_data["party_size"] == 4
    booking_id = booking_data["id"]

    # 2. List reservations
    list_res = client.get(
        "/api/businesses/biz_spice_garden/reservations",
        headers=headers,
    )
    assert list_res.status_code == 200
    bookings = list_res.json()
    found = [b for b in bookings if b["id"] == booking_id]
    assert len(found) == 1

    # 3. Cancel reservation
    del_res = client.delete(
        f"/api/businesses/biz_spice_garden/reservations/{booking_id}",
        headers=headers,
    )
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "cancelled"


def test_capability_cache_speed():
    """Verify capabilities caching provides sub-second response times."""
    invalidate_capability_cache("biz_spice_garden")
    wizard = get_setup_wizard()

    # First run (computes parallel checks)
    t0 = time.time()
    caps1 = wizard.list_capabilities("biz_spice_garden")
    dur1 = time.time() - t0
    assert len(caps1) > 0

    # Second run (instant in-memory cache)
    t1 = time.time()
    caps2 = wizard.list_capabilities("biz_spice_garden")
    dur2 = time.time() - t1
    assert len(caps2) == len(caps1)
    # Cached run must be practically instantaneous (< 0.05 seconds)
    assert dur2 < 0.05
