"""
Regression and verification tests for:
- POST /api/businesses/access issuing valid signed JWT bearer tokens
- Authentication token propagation to protected tenant endpoints (/calls, /tools)
- Rejection of missing, plaintext, malformed, and cross-tenant tokens
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.auth import decode_access_token


def test_access_business_issues_jwt_by_id():
    """Verify POST /api/businesses/access returns access_token when matching by business_id."""
    client = TestClient(app)
    resp = client.post("/api/businesses/access", json={"identifier": "biz_spice_garden"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert "access_token" in data, "Response must include access_token"
    assert data.get("token_type") == "bearer"
    assert data.get("id") == "biz_spice_garden"

    # Verify token payload
    token = data["access_token"]
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("sub") == "biz_spice_garden"
    assert payload.get("business_id") == "biz_spice_garden"
    assert payload.get("role") == "business_owner"


def test_access_business_issues_jwt_by_email():
    """Verify POST /api/businesses/access returns access_token when matching by owner email."""
    client = TestClient(app)
    resp = client.post("/api/businesses/access", json={"identifier": "haveli.restaurant@gmail.com"})
    assert resp.status_code == 200
    data = resp.json()

    assert "access_token" in data
    assert data.get("token_type") == "bearer"
    assert data.get("id") == "biz_spice_garden"


def test_access_business_issues_jwt_by_phone():
    """Verify POST /api/businesses/access returns access_token when matching by phone number."""
    client = TestClient(app)
    resp = client.post("/api/businesses/access", json={"identifier": "+91 80 4123 5678"})
    assert resp.status_code == 200
    data = resp.json()

    assert "access_token" in data
    assert data.get("id") == "biz_spice_garden"


def test_issued_token_authorizes_calls_and_tools():
    """Verify that token returned by /access authorizes calls to /calls and /tools."""
    client = TestClient(app)
    access_resp = client.post("/api/businesses/access", json={"identifier": "biz_spice_garden"})
    assert access_resp.status_code == 200
    token = access_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Test /calls endpoint
    calls_resp = client.get("/api/businesses/biz_spice_garden/calls", headers=headers)
    assert calls_resp.status_code == 200, f"Expected 200, got {calls_resp.status_code}: {calls_resp.text}"
    calls_data = calls_resp.json()
    assert "calls" in calls_data
    assert isinstance(calls_data["calls"], list)

    # Test /tools endpoint
    tools_resp = client.get("/api/businesses/biz_spice_garden/tools", headers=headers)
    assert tools_resp.status_code == 200, f"Expected 200, got {tools_resp.status_code}: {tools_resp.text}"
    tools_data = tools_resp.json()
    assert tools_data["business_id"] == "biz_spice_garden"
    assert "tools" in tools_data
    assert len(tools_data["tools"]) >= 5


def test_unauthenticated_requests_fail_with_401():
    """Verify endpoints strictly enforce authentication when no token header is provided."""
    client = TestClient(app)
    calls_resp = client.get("/api/businesses/biz_spice_garden/calls")
    assert calls_resp.status_code == 401
    assert "credentials were not provided" in calls_resp.json()["detail"].lower()

    tools_resp = client.get("/api/businesses/biz_spice_garden/tools")
    assert tools_resp.status_code == 401


def test_poisoned_plaintext_token_rejected_with_401():
    """Verify that sending a raw business ID as token (the reproduction bug) returns 401."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer biz_spice_garden"}
    calls_resp = client.get("/api/businesses/biz_spice_garden/calls", headers=headers)
    assert calls_resp.status_code == 401
    assert "invalid" in calls_resp.json()["detail"].lower()


def test_cross_tenant_access_rejected_with_403():
    """Verify token for Spice Garden cannot access Grand Hotel calls."""
    client = TestClient(app)
    access_resp = client.post("/api/businesses/access", json={"identifier": "biz_spice_garden"})
    assert access_resp.status_code == 200
    token = access_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/businesses/biz_grand_hotel/calls", headers=headers)
    assert resp.status_code == 403


def test_nonexistent_business_access_fails_with_404():
    """Verify non-existent identifier returns 404."""
    client = TestClient(app)
    resp = client.post("/api/businesses/access", json={"identifier": "nonexistent_business_id_9999"})
    assert resp.status_code == 404
