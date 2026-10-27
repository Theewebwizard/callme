"""
Comprehensive test suite for Step 8: FastAPI REST API Layer and Client Integration.
Covers:
- System and database health check
- Business tenant CRUD and isolation
- FAQ management
- Canonical tool listing and authorization validation
- Call history pagination and outcome filtering
- Playground LangGraph orchestration via API
- Human-in-the-loop pending action confirmation and cancellation (replay protection)
- ApiClient integration and error handling
"""

import json
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.groq_service import GroqService, LLMResponse
import backend.services.groq_service as groq_service_mod
from backend.database.service import get_database_service
from backend.api_client import ApiClient, ApiClientError, ApiConnectionError, ApiNotFoundError


@pytest.fixture
def api_client():
    """TestClient instance for FastAPI application with platform admin authentication."""
    client = TestClient(app)
    client.headers.update({"X-Admin-API-Key": "test-admin-secret-key-12345"})
    return client


# ==============================================================================
# 1. Health Endpoint Tests
# ==============================================================================

def test_health_endpoint_healthy(api_client, monkeypatch):
    """GET /health returns 200, system info, and database status."""
    from backend.database import engine
    monkeypatch.setattr(engine, "check_database_connection", lambda: {"connected": True, "configured": True, "dialect": "postgresql"})
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "version" in data
    assert "database" in data
    assert data["database"]["connected"] is True


# ==============================================================================
# 2. Business Profile Endpoints
# ==============================================================================

def test_list_businesses(api_client):
    """GET /api/businesses returns summaries of all registered businesses."""
    response = api_client.get("/api/businesses")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2

    ids = [b["id"] for b in data]
    assert "biz_spice_garden" in ids
    assert "biz_apex_dental" in ids

    # Check summary fields
    first = data[0]
    for field in ["id", "name", "industry", "opening_time", "closing_time", "timezone"]:
        assert field in first


def test_get_business_detail_success(api_client):
    """GET /api/businesses/{id} returns full configuration profile."""
    response = api_client.get("/api/businesses/biz_spice_garden")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "biz_spice_garden"
    assert data["name"] == "Spice Garden Bistro"
    assert data["industry"] == "Restaurant"
    assert "faqs" in data
    assert "enabled_tools" in data
    assert "stats" in data


def test_get_business_not_found(api_client):
    """GET /api/businesses/{id} returns 404 for unknown business."""
    response = api_client.get("/api/businesses/biz_nonexistent_999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_business_success(api_client):
    """PUT /api/businesses/{id} updates permitted fields and persists them."""
    payload = {
        "name": "The Spice Garden Bistro",
        "closing_time": "23:30",
        "greeting_message": "Welcome to The Spice Garden Bistro! How may I help you?",
    }
    response = api_client.put("/api/businesses/biz_spice_garden", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "The Spice Garden Bistro"
    assert data["closing_time"] == "23:30"
    assert data["greeting_message"] == "Welcome to The Spice Garden Bistro! How may I help you?"

    # Verify retrieval
    get_resp = api_client.get("/api/businesses/biz_spice_garden")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "The Spice Garden Bistro"


def test_update_business_not_found(api_client):
    """PUT /api/businesses/{id} returns 404 for nonexistent tenant."""
    response = api_client.put("/api/businesses/biz_unknown_xyz", json={"name": "Ghost"})
    assert response.status_code == 404


# ==============================================================================
# 3. FAQ Endpoints
# ==============================================================================

def test_list_faqs(api_client):
    """GET /api/businesses/{id}/faqs lists business FAQs."""
    response = api_client.get("/api/businesses/biz_spice_garden/faqs")
    assert response.status_code == 200
    faqs = response.json()
    assert isinstance(faqs, list)
    assert len(faqs) > 0
    assert "question" in faqs[0]
    assert "answer" in faqs[0]


def test_update_faqs(api_client):
    """PUT /api/businesses/{id}/faqs replaces or updates knowledge base items."""
    new_faqs = [
        {"question": "Do you provide valet parking?", "answer": "Yes, complimentary valet parking is available.", "category": "Parking"},
        {"question": "Is outdoor seating available?", "answer": "Yes, on our garden terrace.", "category": "Seating"},
    ]
    response = api_client.put("/api/businesses/biz_spice_garden/faqs", json={"faqs": new_faqs})
    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 2
    assert faqs[0]["question"] == "Do you provide valet parking?"

    # Verify persistence
    get_resp = api_client.get("/api/businesses/biz_spice_garden/faqs")
    assert len(get_resp.json()) == 2


def test_faqs_tenant_not_found(api_client):
    """FAQ endpoints return 404 for unknown business."""
    assert api_client.get("/api/businesses/biz_unknown/faqs").status_code == 404
    assert api_client.put("/api/businesses/biz_unknown/faqs", json={"faqs": []}).status_code == 404


# ==============================================================================
# 4. Canonical Tool Endpoints
# ==============================================================================

def test_get_business_tools(api_client):
    """GET /api/businesses/{id}/tools returns tool listing and activation states."""
    response = api_client.get("/api/businesses/biz_spice_garden/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["business_id"] == "biz_spice_garden"
    assert "tools" in data
    assert "enabled_tools" in data

    tool_ids = [t["id"] for t in data["tools"]]
    assert "check_table_availability" in tool_ids
    assert "create_table_booking" in tool_ids


def test_update_tools_success(api_client):
    """PUT /api/businesses/{id}/tools updates tool activation states."""
    payload = {"tool_statuses": {"check_table_availability": False, "transfer_call": True}}
    response = api_client.put("/api/businesses/biz_spice_garden/tools", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["enabled_tools"]["check_table_availability"] is False
    assert data["enabled_tools"]["transfer_call"] is True


def test_update_tools_rejects_invalid_tool_id(api_client):
    """PUT /api/businesses/{id}/tools rejects unknown tools not in canonical registry with 400."""
    payload = {"tool_statuses": {"arbitrary_unregistered_tool": True}}
    response = api_client.put("/api/businesses/biz_spice_garden/tools", json=payload)
    assert response.status_code == 400
    assert "Invalid tool ID" in response.json()["detail"]


# ==============================================================================
# 5. Call History Endpoints
# ==============================================================================

def test_get_call_history_pagination(api_client):
    """GET /api/businesses/{id}/calls returns paginated call records."""
    response = api_client.get("/api/businesses/biz_spice_garden/calls?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["business_id"] == "biz_spice_garden"
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["calls"]) <= 2
    assert data["total"] >= len(data["calls"])


def test_get_call_history_filter_outcome(api_client):
    """GET /api/businesses/{id}/calls?outcome=... filters by call outcome."""
    response = api_client.get("/api/businesses/biz_spice_garden/calls?outcome=Booking%20Completed")
    assert response.status_code == 200
    data = response.json()
    for call in data["calls"]:
        assert call["outcome"] == "Booking Completed"


def test_get_call_history_not_found(api_client):
    """GET /api/businesses/{id}/calls returns 404 for unknown business."""
    response = api_client.get("/api/businesses/biz_unknown_999/calls")
    assert response.status_code == 404


# ==============================================================================
# 6. Playground Conversation Workflow Endpoints
# ==============================================================================

def test_playground_message_unconfigured_groq(api_client, monkeypatch):
    """POST /api/businesses/{id}/playground/messages returns 503 if Groq is unconfigured."""
    import backend.api.routers.playground as playground_router_mod
    mock_unconfigured = MagicMock(is_configured=False)
    monkeypatch.setattr(playground_router_mod, "get_groq_service", lambda: mock_unconfigured)

    payload = {"message": "Hello!"}
    response = api_client.post("/api/businesses/biz_spice_garden/playground/messages", json=payload)
    assert response.status_code == 503
    assert "Groq LLM service is not configured" in response.json()["detail"]


def test_playground_message_success_with_mock_groq(api_client, monkeypatch):
    """POST /api/businesses/{id}/playground/messages processes message and returns assistant response."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Welcome to The Spice Garden! Would you like to reserve a table?"
    mock_choice.message.tool_calls = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    mock_service = GroqService(api_key="mock_key", client=mock_client)
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    payload = {"message": "Hi, what are your opening hours?"}
    response = api_client.post("/api/businesses/biz_spice_garden/playground/messages", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["role"] == "assistant"
    assert "Welcome to The Spice Garden" in data["content"]

    # Verify persistent chat history updated
    db = get_database_service()
    messages = db.get_conversation_messages("biz_spice_garden")
    user_msgs = [m for m in messages if m["content"] == "Hi, what are your opening hours?"]
    assert len(user_msgs) >= 1


def test_playground_message_tenant_not_found(api_client, monkeypatch):
    """POST /api/businesses/{id}/playground/messages returns 404 for unknown business."""
    mock_service = GroqService(api_key="mock_key", client=MagicMock())
    monkeypatch.setattr(groq_service_mod, "_cached_groq_service", mock_service)

    response = api_client.post("/api/businesses/biz_ghost/playground/messages", json={"message": "Hello"})
    assert response.status_code == 404


# ==============================================================================
# 7. Pending Action Confirmation and Cancellation
# ==============================================================================

def test_confirm_pending_action_success_and_replay_protection(api_client):
    """
    Test Phase B explicit confirmation:
    1. Pending action is confirmed and executed.
    2. Attempting to execute the same action again is rejected with HTTP 400.
    """
    db = get_database_service()
    action_id = "act_test_confirm_123"
    pending_data = {
        "action_id": action_id,
        "tool_id": "create_table_booking",
        "tool_name": "Reserve Dining Table",
        "arguments": {
            "customer_name": "Arjun Sharma",
            "customer_phone": "+91 98765 43210",
            "date": "2026-10-25",
            "time": "19:00",
            "party_size": 2,
        },
        "summary": "Reserve table for 2 under Arjun Sharma on 2026-10-25 at 19:00",
        "status": "pending_confirmation",
    }
    db.save_pending_action("biz_spice_garden", pending_data)

    # 1. First confirmation -> Success (HTTP 200)
    resp = api_client.post(f"/api/businesses/biz_spice_garden/pending-actions/{action_id}/confirm")
    assert resp.status_code == 200
    result = resp.json()
    assert result["success"] is True
    assert result["status"] == "executed"
    assert result["reference_id"] is not None

    # 2. Second confirmation -> Replay protection triggers HTTP 400
    replay_resp = api_client.post(f"/api/businesses/biz_spice_garden/pending-actions/{action_id}/confirm")
    assert replay_resp.status_code == 400
    assert "already been executed" in replay_resp.json()["detail"].lower()


def test_cancel_pending_action_success_and_replay_protection(api_client):
    """
    Test human-in-the-loop cancellation:
    1. Pending action is cancelled.
    2. Attempting to cancel or confirm again is rejected with HTTP 400.
    """
    db = get_database_service()
    action_id = "act_test_cancel_456"
    pending_data = {
        "action_id": action_id,
        "tool_id": "create_table_booking",
        "tool_name": "Reserve Dining Table",
        "arguments": {"customer_name": "Rohan Patel"},
        "summary": "Reserve table for Rohan",
        "status": "pending_confirmation",
    }
    db.save_pending_action("biz_spice_garden", pending_data)

    # 1. Cancel action -> Success (HTTP 200)
    resp = api_client.post(f"/api/businesses/biz_spice_garden/pending-actions/{action_id}/cancel")
    assert resp.status_code == 200
    result = resp.json()
    assert result["success"] is True
    assert result["status"] == "cancelled"

    # 2. Re-cancelling -> HTTP 400
    replay_cancel = api_client.post(f"/api/businesses/biz_spice_garden/pending-actions/{action_id}/cancel")
    assert replay_cancel.status_code == 400

    # 3. Confirming cancelled action -> HTTP 400
    replay_confirm = api_client.post(f"/api/businesses/biz_spice_garden/pending-actions/{action_id}/confirm")
    assert replay_confirm.status_code == 400


def test_pending_action_tenant_scoping_isolation(api_client):
    """Verifies that an action belonging to Tenant A cannot be confirmed under Tenant B."""
    db = get_database_service()
    action_id = "act_isolation_999"
    pending_data = {
        "action_id": action_id,
        "tool_id": "book_table",
        "tool_name": "Reserve Table",
        "arguments": {},
        "summary": "Action for Spice Garden",
        "status": "pending_confirmation",
    }
    db.save_pending_action("biz_spice_garden", pending_data)

    # Attempt to confirm action under biz_apex_dental -> 404
    resp = api_client.post(f"/api/businesses/biz_apex_dental/pending-actions/{action_id}/confirm")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ==============================================================================
# 8. ApiClient End-to-End & Error Handling Tests
# ==============================================================================

def test_api_client_direct_integration(api_client):
    """Verify ApiClient methods communicate correctly with the backend."""
    # Use api_client (TestClient) as the transport
    client = ApiClient(client=api_client)

    health = client.health_check()
    assert health["status"] == "healthy"

    businesses = client.list_businesses()
    assert len(businesses) >= 2

    spice_garden = client.get_business("biz_spice_garden")
    assert spice_garden["name"] == "Spice Garden Bistro"

    # Test tools
    tools_resp = client.get_tools("biz_spice_garden")
    assert "tools" in tools_resp

    # Test call history
    calls_resp = client.get_call_history("biz_spice_garden", limit=5)
    assert "calls" in calls_resp


def test_api_client_not_found_exception(api_client):
    """Verify ApiClient raises ApiNotFoundError on 404 responses."""
    client = ApiClient(client=api_client)
    with pytest.raises(ApiNotFoundError) as exc_info:
        client.get_business("biz_completely_unknown")
    assert exc_info.value.status_code == 404


def test_api_client_connection_error():
    """Verify ApiClient raises ApiConnectionError when server is unreachable."""
    # Point to an unallocated port where no service runs
    offline_client = ApiClient(base_url="http://127.0.0.1:59981")
    with pytest.raises(ApiConnectionError):
        offline_client.health_check()
