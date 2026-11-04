import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import create_access_token
from backend.database.service import get_database_service

client = TestClient(app)

@pytest.fixture
def auth_headers():
    token = create_access_token(
        subject="biz_grand_hotel",
        role="business_owner",
        business_id="biz_grand_hotel",
    )
    return {"Authorization": f"Bearer {token}"}

def test_get_hotel_floors(auth_headers):
    """Verify hotel floor layout retrieval with floor grouping and counts."""
    resp = client.get("/api/businesses/biz_grand_hotel/hotel/floors", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "floors" in data
    assert "total_rooms" in data
    assert "occupancy_rate_pct" in data
    assert len(data["floors"]) >= 1

    first_floor = data["floors"][0]
    assert "floor_number" in first_floor
    assert "rooms" in first_floor
    assert len(first_floor["rooms"]) >= 1
    sample_room = first_floor["rooms"][0]
    assert "id" in sample_room
    assert "status" in sample_room
    assert sample_room["status"] in ("clean", "dirty", "occupied", "maintenance")

def test_hotel_room_status_update(auth_headers):
    """Verify changing room housekeeping status."""
    floors_resp = client.get("/api/businesses/biz_grand_hotel/hotel/floors", headers=auth_headers)
    assert floors_resp.status_code == 200
    room = floors_resp.json()["floors"][0]["rooms"][0]
    room_id = room["id"]

    # Mark dirty
    put_resp = client.put(
        f"/api/businesses/biz_grand_hotel/hotel/rooms/{room_id}/status",
        json={"status": "dirty"},
        headers=auth_headers,
    )
    assert put_resp.status_code == 200
    updated_data = put_resp.json()
    assert updated_data["dirty_count"] >= 1

    # Mark clean
    put_clean = client.put(
        f"/api/businesses/biz_grand_hotel/hotel/rooms/{room_id}/status",
        json={"status": "clean"},
        headers=auth_headers,
    )
    assert put_clean.status_code == 200

def test_hotel_check_in_and_check_out_flow(auth_headers):
    """Verify walk-in guest check-in and check-out lifecycle."""
    floors_resp = client.get("/api/businesses/biz_grand_hotel/hotel/floors", headers=auth_headers)
    room = floors_resp.json()["floors"][0]["rooms"][0]
    room_id = room["id"]

    # Check-in
    ci_resp = client.post(
        f"/api/businesses/biz_grand_hotel/hotel/rooms/{room_id}/check-in",
        json={
            "customer_name": "Rohan Mehra",
            "customer_phone": "+91 99887 76655",
            "nights": 2,
            "party_size": 2,
            "notes": "Late check-in requested",
        },
        headers=auth_headers,
    )
    assert ci_resp.status_code == 200
    ci_data = ci_resp.json()
    assert ci_data["occupied_count"] >= 1

    # Check-out
    co_resp = client.post(
        f"/api/businesses/biz_grand_hotel/hotel/rooms/{room_id}/check-out",
        headers=auth_headers,
    )
    assert co_resp.status_code == 200
    co_data = co_resp.json()
    assert co_data["dirty_count"] >= 1

    # Cleanup: restore to clean
    client.put(
        f"/api/businesses/biz_grand_hotel/hotel/rooms/{room_id}/status",
        json={"status": "clean"},
        headers=auth_headers,
    )

def test_bulk_setup_hotel_floors():
    """Verify bulk floor layout generation wizard."""
    token = create_access_token(
        subject="biz_grand_hotel",
        role="business_owner",
        business_id="biz_grand_hotel",
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/businesses/biz_grand_hotel/hotel/floors/bulk-setup",
        json={
            "floors_count": 2,
            "rooms_per_floor": 3,
            "starting_floor": 1,
            "replace_existing": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rooms"] >= 6
