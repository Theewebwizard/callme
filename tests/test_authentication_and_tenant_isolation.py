"""
Comprehensive security test suite for Phase 1:
- PyJWT token lifecycle, signature verification, expiration, and tampering protection
- Password hashing and verification via bcrypt
- Platform admin authentication via ADMIN_API_KEY and platform_admin JWT
- Strict multi-tenant isolation across all business endpoints
- Rejection of cross-tenant token access (Owner A cannot access Owner B)
- Protection of platform admin endpoints (/api/admin/*) from business owners and anonymous callers
- Voice session transcript and recording access tenant isolation
- Credential vault encryption key resolution prioritizing CAPABILITY_ENCRYPTION_KEY
"""

import time
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    AuthenticatedPrincipal,
)
from backend.capabilities.credentials import get_vault_master_key


# ==============================================================================
# 1. Password Hashing Tests
# ==============================================================================

def test_password_hashing_and_verification():
    """Verify passwords are securely hashed using bcrypt and cannot be verified with wrong inputs."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2b$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(password, "") is False


# ==============================================================================
# 2. JWT Generation & Verification Tests
# ==============================================================================

def test_jwt_token_roundtrip_and_claims():
    """Verify PyJWT generates and decodes tokens with standard claims."""
    token = create_access_token(
        subject="biz_spice_garden",
        role="business_owner",
        business_id="biz_spice_garden",
        expires_delta=timedelta(minutes=30),
    )
    assert isinstance(token, str)
    assert len(token) > 20

    payload = decode_access_token(token)
    assert payload["sub"] == "biz_spice_garden"
    assert payload["role"] == "business_owner"
    assert payload["business_id"] == "biz_spice_garden"
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_token_expiration_rejection():
    """Verify expired JWT tokens are rejected with 401 Unauthorized."""
    expired_token = create_access_token(
        subject="biz_spice_garden",
        role="business_owner",
        business_id="biz_spice_garden",
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )
    with pytest.raises(Exception) as exc_info:
        decode_access_token(expired_token)
    assert "expired" in str(exc_info.value.detail).lower()


def test_jwt_token_tampered_signature_rejection():
    """Verify tampered JWT tokens or mismatched signatures are rejected with 401."""
    valid_token = create_access_token(
        subject="biz_spice_garden",
        role="business_owner",
        business_id="biz_spice_garden",
    )
    # Tamper with the payload part
    parts = valid_token.split(".")
    tampered_token = f"{parts[0]}.eyJzdWIiOiAiaGFja2VyIn0.{parts[2]}"
    with pytest.raises(Exception) as exc_info:
        decode_access_token(tampered_token)
    assert "invalid" in str(exc_info.value.detail).lower() or "signature" in str(exc_info.value.detail).lower()


# ==============================================================================
# 3. Platform Admin Protection Tests (/api/admin/*)
# ==============================================================================

def test_admin_endpoints_reject_anonymous_caller():
    """Anonymous callers cannot access /api/admin/overview."""
    client = TestClient(app)
    resp = client.get("/api/admin/overview")
    assert resp.status_code == 401
    assert "Valid platform admin credentials required" in resp.json()["detail"]


def test_admin_endpoints_reject_business_owner_jwt():
    """A business owner token cannot access platform admin endpoints."""
    token = create_access_token(subject="biz_spice_garden", role="business_owner", business_id="biz_spice_garden")
    client = TestClient(app)
    resp = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (401, 403)
    assert "Valid platform admin credentials required" in resp.json()["detail"]


def test_admin_endpoints_accept_valid_admin_api_key():
    """Valid X-Admin-API-Key grants full access to /api/admin/overview."""
    settings = get_settings()
    client = TestClient(app)
    resp = client.get("/api/admin/overview", headers={"X-Admin-API-Key": settings.ADMIN_API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_agents" in data
    assert "agents" in data


def test_admin_endpoints_accept_platform_admin_jwt():
    """Valid JWT with role=platform_admin grants access to /api/admin/overview."""
    admin_token = create_access_token(subject="admin_user", role="platform_admin")
    client = TestClient(app)
    resp = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_agents" in data


def test_admin_endpoints_locked_if_no_key_configured(monkeypatch):
    """If ADMIN_API_KEY is not configured in the environment, admin endpoints are strictly locked."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)

    client = TestClient(app)
    resp = client.get("/api/admin/overview", headers={"X-Admin-API-Key": "any_guess"})
    assert resp.status_code == 403
    assert "ADMIN_API_KEY is not configured" in resp.json()["detail"]


# ==============================================================================
# 4. Multi-Tenant Isolation Tests
# ==============================================================================

def test_business_endpoints_reject_anonymous_caller():
    """Unauthenticated requests to business tenant endpoints return 401 Unauthorized."""
    client = TestClient(app)
    endpoints = [
        "/api/businesses/biz_spice_garden",
        "/api/businesses/biz_spice_garden/faqs",
        "/api/businesses/biz_spice_garden/tools",
        "/api/businesses/biz_spice_garden/calls",
        "/api/businesses/biz_spice_garden/capabilities",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 401, f"Expected 401 for anonymous access to {ep}, got {resp.status_code}"


def test_cross_tenant_access_is_forbidden():
    """
    Business Owner of Tenant A ('biz_spice_garden') attempting to read or mutate
    Tenant B ('biz_apex_dental') is rejected with 403 Forbidden.
    """
    token_spice = create_access_token(
        subject="biz_spice_garden",
        role="business_owner",
        business_id="biz_spice_garden",
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token_spice}"}

    # 1. Get profile
    resp = client.get("/api/businesses/biz_apex_dental", headers=headers)
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]

    # 2. Get FAQs
    resp = client.get("/api/businesses/biz_apex_dental/faqs", headers=headers)
    assert resp.status_code == 403

    # 3. Get Tools
    resp = client.get("/api/businesses/biz_apex_dental/tools", headers=headers)
    assert resp.status_code == 403

    # 4. Update FAQs
    resp = client.put("/api/businesses/biz_apex_dental/faqs", json={"faqs": []}, headers=headers)
    assert resp.status_code == 403

    # 5. Capabilities
    resp = client.get("/api/businesses/biz_apex_dental/capabilities", headers=headers)
    assert resp.status_code == 403


def test_business_owner_can_access_own_tenant():
    """Business Owner of Tenant A can access and manage their own resources."""
    token_spice = create_access_token(
        subject="biz_spice_garden",
        role="business_owner",
        business_id="biz_spice_garden",
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token_spice}"}

    # Access profile
    resp = client.get("/api/businesses/biz_spice_garden", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == "biz_spice_garden"

    # Access FAQs
    resp = client.get("/api/businesses/biz_spice_garden/faqs", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # Access Tools
    resp = client.get("/api/businesses/biz_spice_garden/tools", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["business_id"] == "biz_spice_garden"


def test_platform_admin_can_access_any_tenant():
    """Platform Admin key allows cross-tenant inspection and management."""
    settings = get_settings()
    client = TestClient(app)
    headers = {"X-Admin-API-Key": settings.ADMIN_API_KEY}

    resp1 = client.get("/api/businesses/biz_spice_garden", headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["id"] == "biz_spice_garden"

    resp2 = client.get("/api/businesses/biz_apex_dental", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == "biz_apex_dental"


# ==============================================================================
# 5. Login & Token Issuance Tests
# ==============================================================================

def test_login_endpoint_issues_valid_jwt():
    """POST /api/businesses/login returns a valid JWT token on successful authentication."""
    client = TestClient(app)
    # 1. Register a new business with a password
    create_resp = client.post(
        "/api/businesses",
        json={
            "name": "Auth Test Salon",
            "industry": "Salon & Spa",
            "owner_email": "owner@authtest.com",
            "password": "testpass123",
            "phone_number": "+15551234567",
        },
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    biz_id = created_data["id"]
    assert "access_token" in created_data

    # 2. Log in using email and password
    login_resp = client.post(
        "/api/businesses/login",
        json={"email": "owner@authtest.com", "password": "testpass123"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["business"]["id"] == biz_id

    # 3. Verify returned token works to query protected endpoint
    token = data["access_token"]
    verify_resp = client.get(
        f"/api/businesses/{biz_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["id"] == biz_id


def test_google_auth_endpoint_issues_valid_jwt():
    """POST /api/businesses/google-auth returns a valid JWT token on successful sign-in."""
    client = TestClient(app)
    resp = client.post(
        "/api/businesses/google-auth",
        json={
            "credential": "mock_google_id_token",
            "email": "haveli.restaurant@gmail.com",
            "name": "Spice Garden Owner",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["business"]["id"] == "biz_spice_garden"


# ==============================================================================
# 6. Voice Session Isolation Tests
# ==============================================================================

def test_voice_session_inspection_isolation():
    """Voice session transcripts and details cannot be inspected across tenants."""
    token_spice = create_access_token(subject="biz_spice_garden", role="business_owner", business_id="biz_spice_garden")
    token_apex = create_access_token(subject="biz_apex_dental", role="business_owner", business_id="biz_apex_dental")

    client = TestClient(app)

    # Simulate inbound call for Spice Garden
    sim_resp = client.post(
        "/api/voice/simulation/inbound",
        json={
            "provider_call_id": "auth_test_sess",
            "called_number": "+91 80 4123 5678",  # Spice Garden
            "caller_number": "+91 98 7654 3210",
        },
        headers={"Authorization": f"Bearer {token_spice}"},
    )
    assert sim_resp.status_code == 200
    session_id = sim_resp.json()["session_id"]

    # Spice Garden owner can read their session
    read_resp = client.get(
        f"/api/voice/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_spice}"},
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["session_id"] == session_id

    # Apex Dental owner is forbidden from inspecting Spice Garden's session
    cross_resp = client.get(
        f"/api/voice/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_apex}"},
    )
    assert cross_resp.status_code == 403


# ==============================================================================
# 7. Capability Vault Master Key Priority Tests
# ==============================================================================

def test_vault_master_key_prefers_capability_encryption_key(monkeypatch):
    """
    get_vault_master_key() must prioritize CAPABILITY_ENCRYPTION_KEY when provided,
    preventing key desynchronization.
    """
    from backend.capabilities.vault import generate_vault_key, validate_and_decode_key
    custom_key = generate_vault_key()
    monkeypatch.setenv("CAPABILITY_ENCRYPTION_KEY", custom_key)
    monkeypatch.setenv("SECRET_KEY", "fallback-secret-key-123")
    key = get_vault_master_key()
    assert key == validate_and_decode_key(custom_key)


# ==============================================================================
# 8. Concurrent Call Pending Action Isolation & Cleanup Tests
# ==============================================================================

def test_concurrent_calls_pending_action_session_isolation():
    """
    Verify that when two concurrent calls for the SAME business generate pending actions:
    1. Each pending action is accurately scoped to its own voice session.
    2. One call does not overwrite or shadow the other call's pending action.
    3. Terminating Call 1 cancels only Call 1's pending action without touching Call 2.
    """
    from backend.database.service import get_database_service
    from backend.voice.session_manager import DatabaseVoiceSessionManager
    from backend.voice.events import InboundCallEvent

    db = get_database_service()
    sm = DatabaseVoiceSessionManager(db)

    # Call 1
    ev1 = InboundCallEvent(
        provider_call_id="call_conc_1",
        provider_name="test_call",
        called_number="+91 80 4123 5678",
        caller_number="+91 99 1111 2222",
    )
    sess1 = sm.create_session(ev1, "biz_spice_garden")

    # Call 2 (concurrent to same business)
    ev2 = InboundCallEvent(
        provider_call_id="call_conc_2",
        provider_name="test_call",
        called_number="+91 80 4123 5678",
        caller_number="+91 99 3333 4444",
    )
    sess2 = sm.create_session(ev2, "biz_spice_garden")

    assert sess1.session_id != sess2.session_id

    # Create pending action in Call 1
    act1_data = {
        "action_id": "act_sess1_table2",
        "tool_id": "create_table_booking",
        "tool_name": "Reserve Table",
        "arguments": {"party_size": 2, "date": "2026-10-30", "time": "19:00"},
        "summary": "Table for 2 on Oct 30 at 7pm",
    }
    db.save_pending_action("biz_spice_garden", act1_data, session_id=sess1.session_id)

    # Create pending action in Call 2
    act2_data = {
        "action_id": "act_sess2_table6",
        "tool_id": "create_table_booking",
        "tool_name": "Reserve Table",
        "arguments": {"party_size": 6, "date": "2026-10-31", "time": "20:00"},
        "summary": "Table for 6 on Oct 31 at 8pm",
    }
    db.save_pending_action("biz_spice_garden", act2_data, session_id=sess2.session_id)

    # 1. Verify isolated session lookup
    retrieved_1 = db.get_pending_action("biz_spice_garden", session_id=sess1.session_id)
    retrieved_2 = db.get_pending_action("biz_spice_garden", session_id=sess2.session_id)

    assert retrieved_1 is not None
    assert retrieved_1["action_id"] == "act_sess1_table2"
    assert retrieved_1["session_id"] == sess1.session_id
    assert retrieved_1["arguments"]["party_size"] == 2

    assert retrieved_2 is not None
    assert retrieved_2["action_id"] == "act_sess2_table6"
    assert retrieved_2["session_id"] == sess2.session_id
    assert retrieved_2["arguments"]["party_size"] == 6

    # 2. Cancel Call 1 unconfirmed actions explicitly
    db.cancel_session_pending_actions(sess1.session_id)

    # Call 1 pending action must be cancelled
    updated_1 = db.get_pending_action_by_id("biz_spice_garden", "act_sess1_table2")
    assert updated_1["status"] == "cancelled"

    # Call 2 pending action must remain active and pending confirmation
    active_2 = db.get_pending_action("biz_spice_garden", session_id=sess2.session_id)
    assert active_2 is not None
    assert active_2["action_id"] == "act_sess2_table6"
    assert active_2["status"] == "pending_confirmation"

    # 3. Terminate Call 1 (caller hangup)
    term_sess1 = sm.terminate_session(sess1.session_id, reason="caller_hangup")
    assert term_sess1.status in ["terminated", "completed"]

    # Call 2 session and pending action are still active in session manager
    sess2_check = sm.get_session(sess2.session_id)
    assert sess2_check is not None
    assert sess2_check.status in ["initiated", "active"]
