"""
Unit and integration tests for the official Zendesk Support Desk Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.SUPPORT_DESK)
- Registry lookup and option aliases ('zendesk', 'zendesk_support')
- Subdomain normalization (e.g. 'mybrand', 'mybrand.zendesk.com', 'https://mybrand.zendesk.com')
- Authentication:
  - OAuth 2.0 Bearer token support
  - OAuth authorization URL construction (/oauth/authorizations/new)
  - Authorization code exchange (/oauth/tokens)
  - API token Basic auth (email/token:api_token)
  - Credential validation and failure on missing credentials
- Safe diagnostics: test_connection() probes GET /api/v2/users/me.json without creating dummy tickets
- Ticket creation, external_id assignment, and field normalization (status, priority, url)
- Validation of missing required fields (subject, description)
- Truthful outcome envelope: Ticket creation references real provider ticket; does not claim human resolution
- Progressive capability gating:
  - Ticket updates blocked when 'ticket_updates' feature is disabled
  - Comments blocked when 'comments' feature is disabled
  - Assignment blocked when 'assignment' feature is disabled
  - User lookup blocked when 'user_lookup' feature is disabled
  - Operations succeed when capabilities are explicitly enabled in configuration
- Ambiguous timeout reconciliation via external_id search (prevents duplicate tickets after network timeout)
- Idempotency key tracking and duplicate ticket suppression
- Archived ticket behavior: attempting to modify a closed/archived ticket raises BUSINESS_RULE_VIOLATION
- Endpoint-specific rate limiting and Retry-After header tracking (HTTP 429 -> RATE_LIMITED)
- Permission restrictions (HTTP 403 -> PERMISSION_DENIED)
- Error normalization (HTTP 400, 401, 403, 404, 422, 500)
- Resource discovery (groups, ticket_fields, brands)
- Multi-tenant isolation
- Capability contract execution via execute()
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import base64
import urllib.error

from backend.integrations.adapters.zendesk_support_adapter import (
    ZendeskSupportAdapter,
    ZendeskIntegrationException,
    ZENDESK_STATUS_MAP,
    ZENDESK_PRIORITIES,
)
from backend.capabilities.models import (
    AuthoritativeSource,
)
from backend.integrations.models import (
    ProviderManifest,
    CapabilityType,
    AuthMethod,
    IntegrationCategory,
    ExecutionContext,
    ExecutionOutcome,
    ErrorCategory,
    IntegrationError,
)
from backend.integrations.registry import get_integration_registry


# ============================================================================
# 1. Manifest & Registry Verification
# ============================================================================

def test_zendesk_manifest_and_authoritative_source():
    """Verify Zendesk adapter manifest, capabilities, and authoritative source."""
    adapter = ZendeskSupportAdapter(business_id="biz_test_zendesk")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "zendesk"
    assert manifest.display_name == "Zendesk Support Desk"
    assert manifest.category == IntegrationCategory.SUPPORT
    assert manifest.authoritative_source == AuthoritativeSource.SUPPORT_DESK
    assert adapter.authoritative_source == AuthoritativeSource.SUPPORT_DESK
    assert CapabilityType.CREATE_SUPPORT_TICKET in manifest.supported_capabilities

    field_keys = [f.key for f in manifest.required_setup_fields]
    assert "subdomain" in field_keys


def test_zendesk_registered_in_registry():
    """Verify Zendesk adapter is registered under 'zendesk' and alias 'zendesk_support'."""
    registry = get_integration_registry()

    manifest = registry.get_manifest("zendesk")
    assert manifest is not None
    assert manifest.provider_id == "zendesk"

    cls = registry.get_adapter_class("zendesk")
    assert cls is ZendeskSupportAdapter

    alias_manifest = registry.get_manifest("zendesk_support")
    assert alias_manifest is not None
    alias_cls = registry.get_adapter_class("zendesk_support")
    assert alias_cls is ZendeskSupportAdapter


# ============================================================================
# 2. Subdomain Normalization & Authentication
# ============================================================================

@pytest.mark.parametrize(
    "input_subdomain,expected_base_url,expected_web_prefix",
    [
        ("acme", "https://acme.zendesk.com/api/v2", "https://acme.zendesk.com"),
        ("acme.zendesk.com", "https://acme.zendesk.com/api/v2", "https://acme.zendesk.com"),
        ("https://acme.zendesk.com", "https://acme.zendesk.com/api/v2", "https://acme.zendesk.com"),
        ("https://support.acmehealth.com", "https://support.acmehealth.com/api/v2", "https://support.acmehealth.com"),
    ],
)
def test_zendesk_subdomain_normalization(input_subdomain, expected_base_url, expected_web_prefix):
    """Verify subdomain normalization across formats."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_norm",
        configuration={"subdomain": input_subdomain},
    )
    assert adapter.get_base_url() == expected_base_url
    assert adapter.get_web_url_prefix() == expected_web_prefix


def test_zendesk_oauth_authorization_url_and_token_exchange():
    """Verify OAuth authorization URL formatting and code exchange at /oauth/tokens."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_oauth",
        configuration={"subdomain": "acmeclinic", "client_id": "oauth_client_123"},
        credentials={"client_secret": "oauth_sec_456"},
    )

    # 1. Authorization URL
    auth_url = adapter.get_authorization_url(
        redirect_uri="https://api.answerly.ai/auth/zendesk/callback",
        state="csrf_state_xyz",
    )
    assert "https://acmeclinic.zendesk.com/oauth/authorizations/new" in auth_url
    assert "client_id=oauth_client_123" in auth_url
    assert "state=csrf_state_xyz" in auth_url
    assert "response_type=code" in auth_url

    # 2. Code Exchange
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({
        "access_token": "ya29.zendesk_oauth_token_789",
        "token_type": "Bearer",
        "scope": "read write",
    }).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        token_data = adapter.exchange_code_for_tokens(
            code="auth_code_999",
            redirect_uri="https://api.answerly.ai/auth/zendesk/callback",
        )
        assert token_data["access_token"] == "ya29.zendesk_oauth_token_789"
        assert adapter.credentials["access_token"] == "ya29.zendesk_oauth_token_789"


def test_zendesk_auth_headers_oauth_and_api_token():
    """Verify Bearer token header for OAuth and Basic Auth header for API token."""
    # OAuth Bearer
    adapter_oauth = ZendeskSupportAdapter(
        business_id="biz_1",
        credentials={"access_token": "bearer_token_123"},
    )
    assert adapter_oauth._get_auth_header() == "Bearer bearer_token_123"

    # API Token Basic Auth ({email}/token:{api_token})
    adapter_api_token = ZendeskSupportAdapter(
        business_id="biz_2",
        configuration={"email": "agent@acme.com"},
        credentials={"api_token": "token_abc"},
    )
    header = adapter_api_token._get_auth_header()
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.replace("Basic ", "")).decode("utf-8")
    assert decoded == "agent@acme.com/token:token_abc"


def test_zendesk_connect_validation():
    """Verify connect requires valid OAuth access_token or api_token + email."""
    adapter = ZendeskSupportAdapter(business_id="biz_test")

    # Missing credentials
    res_fail = adapter.connect({})
    assert not res_fail.passed

    # API token without email
    res_no_email = adapter.connect({"api_token": "token_123"})
    assert not res_no_email.passed

    # Success with OAuth access token
    res_oauth = adapter.connect({"access_token": "bearer_token_xyz"})
    assert res_oauth.passed


# ============================================================================
# 3. Safe Diagnostics: test_connection()
# ============================================================================

def test_zendesk_safe_connection_probe_never_creates_dummy_tickets():
    """
    CRITICAL TEST: test_connection must query GET /api/v2/users/me.json
    and NEVER create a dummy ticket.
    """
    adapter = ZendeskSupportAdapter(
        business_id="biz_safe_diag",
        configuration={"subdomain": "acme"},
        credentials={"access_token": "ya29.live_token"},
    )

    with patch.object(adapter, "_make_request") as mock_req, \
         patch.object(adapter, "create_ticket") as mock_create:

        mock_req.return_value = {
            "user": {
                "id": 1001,
                "name": "Dr. Gregory House",
                "role": "admin",
                "email": "house@princeton.edu",
            }
        }

        res = adapter.test_connection()

        # Verify users/me.json was probed
        mock_req.assert_called_once_with("GET", "/users/me.json")
        # STRICT CHECK: create_ticket was NEVER called!
        mock_create.assert_not_called()

        assert res.passed is True
        assert "Dr. Gregory House" in res.details
        assert "Zero tickets created" in res.details


def test_zendesk_test_connection_mock_mode():
    """Verify test_connection in mock mode succeeds safely without external calls."""
    adapter = ZendeskSupportAdapter(business_id="biz_mock", configuration={"is_mock": True})
    with patch.object(adapter, "create_ticket") as mock_create:
        res = adapter.test_connection()
        mock_create.assert_not_called()
        assert res.passed is True
        assert "Zero tickets created" in res.details


# ============================================================================
# 4. Ticket Creation & Data Normalization
# ============================================================================

def test_zendesk_create_ticket_success_and_normalization():
    """Verify creating a ticket parses fields and normalizes status, priority, and URL."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_create",
        configuration={"subdomain": "acmehealth"},
        credentials={"access_token": "token_123"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "ticket": {
                "id": 90210,
                "subject": "Insurance Verification Inquiry",
                "description": "Please verify coverage for procedure code 99213.",
                "status": "new",  # Normalizes to 'open'
                "priority": "urgent",
                "requester_id": 88123,
                "requester": {"name": "John Doe", "email": "johndoe@example.com"},
                "assignee_id": None,
                "group_id": None,
                "external_id": "ext_claim_123",
                "created_at": "2026-10-27T10:00:00Z",
                "updated_at": "2026-10-27T10:00:00Z",
            }
        }

        ticket = adapter.create_ticket(
            subject="Insurance Verification Inquiry",
            description="Please verify coverage for procedure code 99213.",
            requester_name="John Doe",
            requester_email="johndoe@example.com",
            priority="urgent",
            external_id="ext_claim_123",
        )

        mock_req.assert_called_once()
        call_method, call_endpoint = mock_req.call_args[0][:2]
        call_payload = mock_req.call_args[1].get("payload") or mock_req.call_args[0][2]

        assert call_method == "POST"
        assert call_endpoint == "/tickets.json"
        assert call_payload["ticket"]["subject"] == "Insurance Verification Inquiry"
        assert call_payload["ticket"]["external_id"] == "ext_claim_123"

        # Verify normalization
        assert ticket["ticket_id"] == "90210"
        assert ticket["provider_ticket_id"] == "zen_90210"
        assert ticket["status"] == "open"  # 'new' normalized to 'open'
        assert ticket["priority"] == "urgent"
        assert ticket["url"] == "https://acmehealth.zendesk.com/agent/tickets/90210"
        assert ticket["is_resolved"] is False


def test_zendesk_create_ticket_validation_missing_fields():
    """Verify validation errors when subject or description is missing."""
    adapter = ZendeskSupportAdapter(business_id="biz_val")

    # Missing subject
    with pytest.raises(ZendeskIntegrationException) as exc_subj:
        adapter.create_ticket(subject="", description="Valid Description")
    assert exc_subj.value.error.category == ErrorCategory.INVALID_REQUEST
    assert "MISSING_SUBJECT" in exc_subj.value.error.code

    # Missing description
    with pytest.raises(ZendeskIntegrationException) as exc_desc:
        adapter.create_ticket(subject="Valid Subject", description="")
    assert exc_desc.value.error.category == ErrorCategory.INVALID_REQUEST
    assert "MISSING_DESCRIPTION" in exc_desc.value.error.code


# ============================================================================
# 5. Truthful Outcome Envelope
# ============================================================================

def test_zendesk_truthful_outcome_envelope():
    """
    CRITICAL TEST: Ticket creation returns OPERATION_COMPLETED referencing the real ticket ID.
    Strictly does not claim resolution until Zendesk state is 'solved' or 'closed'.
    """
    adapter = ZendeskSupportAdapter(
        business_id="biz_truth",
        configuration={"subdomain": "acme"},
        credentials={"access_token": "token_123"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "ticket": {
                "id": 55123,
                "subject": "Prescription Refill Request",
                "description": "Refill for medication XYZ",
                "status": "open",
                "priority": "normal",
                "created_at": "2026-10-27T10:00:00Z",
            }
        }

        ctx = ExecutionContext(tenant_id="biz_truth", correlation_id="corr_truth_1")
        result = adapter.execute(
            operation=CapabilityType.CREATE_SUPPORT_TICKET,
            input_data={
                "subject": "Prescription Refill Request",
                "description": "Refill for medication XYZ",
            },
            context=ctx,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["ticket_id"] == "55123"
        assert result.data["status"] == "open"
        assert result.data["is_resolved"] is False
        assert "Support ticket #55123 filed with Zendesk support" in result.safe_message


# ============================================================================
# 6. Progressive Capability Gating
# ============================================================================

def test_zendesk_progressive_capability_gating_disabled_features():
    """Verify operations fail when optional capabilities are disabled in configuration."""
    # Default configuration only enables ticket_creation & ticket_retrieval
    adapter = ZendeskSupportAdapter(
        business_id="biz_gating",
        configuration={"subdomain": "acme"},
        credentials={"access_token": "token_123"},
    )

    # 1. Update ticket blocked
    with pytest.raises(ZendeskIntegrationException) as exc_upd:
        adapter.update_ticket(ticket_id="101", status="solved")
    assert exc_upd.value.error.category == ErrorCategory.PERMISSION_DENIED
    assert "FEATURE_DISABLED" in exc_upd.value.error.code

    # 2. Add comment blocked
    with pytest.raises(ZendeskIntegrationException) as exc_com:
        adapter.add_comment(ticket_id="101", body="Agent reply")
    assert exc_com.value.error.category == ErrorCategory.PERMISSION_DENIED
    assert "FEATURE_DISABLED" in exc_com.value.error.code

    # 3. Assign ticket blocked
    with pytest.raises(ZendeskIntegrationException) as exc_ass:
        adapter.assign_ticket(ticket_id="101", assignee_id=123)
    assert exc_ass.value.error.category == ErrorCategory.PERMISSION_DENIED
    assert "FEATURE_DISABLED" in exc_ass.value.error.code

    # 4. User lookup blocked
    with pytest.raises(ZendeskIntegrationException) as exc_usr:
        adapter.search_users("patient@example.com")
    assert exc_usr.value.error.category == ErrorCategory.PERMISSION_DENIED
    assert "FEATURE_DISABLED" in exc_usr.value.error.code


def test_zendesk_progressive_capability_gating_enabled_features():
    """Verify operations succeed when optional capabilities are explicitly enabled."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_enabled",
        configuration={
            "subdomain": "acme",
            "enabled_features": ["ticket_updates", "comments", "assignment", "user_lookup"],
        },
        credentials={"access_token": "token_123"},
    )

    with patch.object(adapter, "_make_request") as mock_req, \
         patch.object(adapter, "get_ticket") as mock_get:

        mock_get.return_value = {"ticket_id": "101", "status": "open", "raw_status": "open", "is_archived": False}

        # 1. Update ticket
        mock_req.return_value = {"ticket": {"id": 101, "status": "solved", "priority": "high"}}
        upd_res = adapter.update_ticket(ticket_id="101", status="solved", priority="high")
        assert upd_res["status"] == "resolved"
        assert upd_res["is_resolved"] is True

        # 2. Add comment
        mock_req.return_value = {"ticket": {"id": 101, "status": "open"}}
        com_res = adapter.add_comment(ticket_id="101", body="We are looking into this.")
        assert com_res["ticket_id"] == "101"

        # 3. Assign ticket
        mock_req.return_value = {"ticket": {"id": 101, "assignee_id": 555, "group_id": 777}}
        ass_res = adapter.assign_ticket(ticket_id="101", assignee_id=555, group_id=777)
        assert ass_res["assignee"]["assignee_id"] == 555

        # 4. Search users
        mock_req.return_value = {"users": [{"id": 555, "name": "Agent Smith", "email": "smith@acme.com", "role": "agent"}]}
        users = adapter.search_users("smith@acme.com")
        assert len(users) == 1
        assert users[0]["name"] == "Agent Smith"


# ============================================================================
# 7. Ambiguous Timeout Reconciliation & Deduplication
# ============================================================================

def test_zendesk_ambiguous_timeout_reconciliation():
    """
    CRITICAL TEST: When a timeout occurs, adapter queries Zendesk by external_id
    and recovers the existing ticket reference without creating a duplicate.
    """
    adapter = ZendeskSupportAdapter(
        business_id="biz_reconcile",
        configuration={"subdomain": "acme"},
        credentials={"access_token": "token_123"},
    )

    ext_id = "claim_reconcile_999"

    with patch.object(adapter, "_make_request") as mock_req, \
         patch.object(adapter, "search_tickets") as mock_search:

        # Simulate timeout on POST /tickets.json
        mock_req.side_effect = TimeoutError("HTTP connection timed out")

        # Simulate search returning the ticket that was actually created by Zendesk
        mock_search.return_value = [
            {
                "ticket_id": "887766",
                "provider_ticket_id": "zen_887766",
                "subject": "Urgent Claim Inquiry",
                "status": "open",
                "priority": "urgent",
                "external_id": ext_id,
            }
        ]

        ticket = adapter.create_ticket(
            subject="Urgent Claim Inquiry",
            description="Claim details",
            external_id=ext_id,
        )

        # Verify search was queried with external_id
        mock_search.assert_called_once_with(query=f"type:ticket external_id:{ext_id}")
        assert ticket["ticket_id"] == "887766"
        assert ticket["reconciled_after_timeout"] is True
        assert ticket["is_duplicate"] is True


def test_zendesk_duplicate_ticket_creation_suppressed_by_idempotency_cache():
    """Verify repeated create_ticket calls within cache window return cached result."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_idem",
        configuration={"subdomain": "acme"},
        credentials={"access_token": "token_123"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "ticket": {
                "id": 12345,
                "subject": "Billing Question",
                "description": "Details",
                "status": "open",
                "priority": "normal",
            }
        }

        # 1. First invocation: hits API
        t1 = adapter.create_ticket(
            subject="Billing Question",
            description="Details",
            idempotency_key="billing_inq_12345",
        )
        assert mock_req.call_count == 1
        assert t1["ticket_id"] == "12345"
        assert t1.get("is_duplicate") is not True

        # 2. Second invocation with same key: served from cache
        t2 = adapter.create_ticket(
            subject="Billing Question",
            description="Details",
            idempotency_key="billing_inq_12345",
        )
        assert mock_req.call_count == 1  # No second API call!
        assert t2["ticket_id"] == "12345"
        assert t2["is_duplicate"] is True


# ============================================================================
# 8. Archived Ticket Protection
# ============================================================================

def test_zendesk_archived_ticket_modification_rejected():
    """Verify modifying or commenting on an archived/closed ticket raises BUSINESS_RULE_VIOLATION."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_arch",
        configuration={"subdomain": "acme", "enabled_features": ["ticket_updates", "comments"]},
        credentials={"access_token": "token_123"},
    )

    with patch.object(adapter, "get_ticket") as mock_get:
        # Simulate ticket closed > 120 days ago (archived)
        mock_get.return_value = {
            "ticket_id": "4001",
            "status": "closed",
            "raw_status": "closed",
            "is_archived": True,
        }

        # Attempting update on archived ticket fails
        with pytest.raises(ZendeskIntegrationException) as exc_upd:
            adapter.update_ticket("4001", priority="urgent")
        assert exc_upd.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION
        assert "TICKET_ARCHIVED_OR_CLOSED" in exc_upd.value.error.code

        # Attempting comment on archived ticket fails
        with pytest.raises(ZendeskIntegrationException) as exc_com:
            adapter.add_comment("4001", body="Follow up")
        assert exc_com.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION
        assert "TICKET_ARCHIVED_OR_CLOSED" in exc_com.value.error.code


# ============================================================================
# 9. Rate Limiting & Retry-After Tracking
# ============================================================================

def test_zendesk_rate_limiting_retry_after():
    """Verify HTTP 429 parses Retry-After header and normalizes to RATE_LIMITED."""
    adapter = ZendeskSupportAdapter(business_id="biz_rate")

    mock_fp = MagicMock()
    mock_fp.read.return_value = b'{"error": "TooManyRequests", "description": "Rate limit exceeded"}'
    hdrs = {"Retry-After": "30"}

    http_err = urllib.error.HTTPError(
        url="https://acme.zendesk.com/api/v2/tickets.json",
        code=429,
        msg="Too Many Requests",
        hdrs=hdrs,
        fp=mock_fp,
    )

    norm_err = adapter._normalize_zendesk_error(http_err)
    assert norm_err.category == ErrorCategory.RATE_LIMITED
    assert norm_err.is_retryable is True
    assert norm_err.retry_after_seconds == 30.0


# ============================================================================
# 10. Comprehensive Error Normalization
# ============================================================================

@pytest.mark.parametrize(
    "status_code,body,expected_category,expected_retryable",
    [
        (
            400,
            json.dumps({"error": "InvalidAttribute", "description": "Subject cannot be blank"}),
            ErrorCategory.INVALID_REQUEST,
            False,
        ),
        (
            401,
            json.dumps({"error": "Couldn't authenticate you"}),
            ErrorCategory.AUTHENTICATION_FAILED,
            False,
        ),
        (
            403,
            json.dumps({"error": "Forbidden", "description": "You do not have permission to view this ticket."}),
            ErrorCategory.PERMISSION_DENIED,
            False,
        ),
        (
            404,
            json.dumps({"error": "RecordNotFound", "description": "Not found"}),
            ErrorCategory.RESOURCE_NOT_FOUND,
            False,
        ),
        (
            422,
            json.dumps({"error": "UnprocessableEntity", "description": "Ticket is closed"}),
            ErrorCategory.BUSINESS_RULE_VIOLATION,
            False,
        ),
        (
            500,
            json.dumps({"error": "ServerFailure", "description": "Internal server error"}),
            ErrorCategory.PROVIDER_UNAVAILABLE,
            True,
        ),
    ],
)
def test_zendesk_error_normalization(status_code, body, expected_category, expected_retryable):
    """Verify Zendesk error envelopes normalize into structured IntegrationError."""
    adapter = ZendeskSupportAdapter(business_id="biz_err")

    mock_fp = MagicMock()
    mock_fp.read.return_value = body.encode("utf-8")
    http_err = urllib.error.HTTPError(
        url="https://acme.zendesk.com/api/v2/tickets.json",
        code=status_code,
        msg="Error",
        hdrs={},
        fp=mock_fp,
    )

    norm_err = adapter._normalize_zendesk_error(http_err)
    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ============================================================================
# 11. Resource Discovery
# ============================================================================

def test_zendesk_discover_resources():
    """Verify discovery of groups, ticket fields, and brands."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_disc",
        configuration={"subdomain": "acme"},
        credentials={"access_token": "live_token"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        # Groups
        mock_req.return_value = {"groups": [{"id": 1, "name": "Billing Tier 1", "description": "Billing"}]}
        res_groups = adapter.discover_resources("groups")
        assert len(res_groups) == 1
        assert res_groups[0].resource_id == "1"
        assert res_groups[0].name == "Billing Tier 1"

        # Ticket Fields
        mock_req.return_value = {"ticket_fields": [{"id": 2, "title": "Customer Tier", "type": "text"}]}
        res_fields = adapter.discover_resources("ticket_fields")
        assert len(res_fields) == 1
        assert res_fields[0].name == "Customer Tier"

        # Brands
        mock_req.return_value = {"brands": [{"id": 3, "name": "Acme Brand", "brand_url": "https://brand.acme.com"}]}
        res_brands = adapter.discover_resources("brands")
        assert len(res_brands) == 1
        assert res_brands[0].name == "Acme Brand"


# ============================================================================
# 12. Multi-Tenant Isolation
# ============================================================================

def test_zendesk_multi_tenant_isolation():
    """Verify two tenants maintain isolated subdomains, credentials, and idempotency caches."""
    tenant_1 = ZendeskSupportAdapter(
        business_id="tenant_dental",
        configuration={"subdomain": "dental-support"},
        credentials={"access_token": "token_dental"},
    )
    tenant_2 = ZendeskSupportAdapter(
        business_id="tenant_chiro",
        configuration={"subdomain": "chiro-support"},
        credentials={"access_token": "token_chiro"},
    )

    assert tenant_1.get_base_url() == "https://dental-support.zendesk.com/api/v2"
    assert tenant_2.get_base_url() == "https://chiro-support.zendesk.com/api/v2"
    assert tenant_1.credentials["access_token"] == "token_dental"
    assert tenant_2.credentials["access_token"] == "token_chiro"

    tenant_1._idempotency_cache["k1"] = ({"ticket_id": "1"}, time.time())
    assert "k1" not in tenant_2._idempotency_cache


# ============================================================================
# 13. Capability Contract Execution via execute() in Mock Mode
# ============================================================================

def test_zendesk_execute_in_mock_mode():
    """Verify execution of CREATE_SUPPORT_TICKET in mock mode."""
    adapter = ZendeskSupportAdapter(
        business_id="biz_mock_exec",
        configuration={"is_mock": True, "subdomain": "acme"},
    )

    ctx = ExecutionContext(tenant_id="biz_mock_exec", correlation_id="corr_mock_1")
    res = adapter.execute(
        operation=CapabilityType.CREATE_SUPPORT_TICKET,
        input_data={
            "subject": "Mock Billing Inquiry",
            "description": "Mock inquiry details",
            "requester_email": "patient@example.com",
        },
        context=ctx,
    )

    assert res.success is True
    assert res.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert res.is_simulated is True
    assert res.data["is_resolved"] is False
    assert res.data["status"] == "open"
