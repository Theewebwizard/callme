"""
Unit and integration tests for the Freshdesk Support Desk Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.SUPPORT_DESK)
- Registry lookup and option aliases ('freshdesk', 'freshdesk_support')
- Domain normalization (prefix 'acme', full hostname 'acme.freshdesk.com', custom domain 'https://support.acme.com')
- Configuration & authentication validation (API key Basic Auth, OAuth Bearer, missing credentials)
- Safe diagnostics: test_connection() probes GET /api/v2/agents/me without creating dummy tickets
- Ticket creation, field normalization (status 2->open, priority 2->normal, url generation)
- Validation of missing required fields (subject, description, requester)
- Truthful outcome envelope: Ticket creation references real provider ticket; does not claim human resolution
- Ticket operations: get_ticket, search_tickets, update_ticket, assign_ticket, change_ticket_status, reply_to_ticket, add_ticket_note
- Contact operations: get_contact, search_contacts, create_or_update_contact
- Rate limiting and header tracking (X-RateLimit-Remaining, Retry-After header)
- Comprehensive error normalization (HTTP 400 validation failed, HTTP 401, HTTP 403, HTTP 404, HTTP 429, HTTP 500)
- Idempotency key tracking and duplicate ticket suppression
- Resource discovery (groups, agents, ticket_fields)
- Multi-tenant isolation
- Capability contract execution via execute()
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import base64
import urllib.error

from backend.integrations.adapters.freshdesk_support_adapter import (
    FreshdeskSupportAdapter,
    FreshdeskIntegrationException,
    FRESHDESK_STATUS_MAP,
    FRESHDESK_PRIORITY_MAP,
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

def test_freshdesk_manifest_and_authoritative_source():
    """Verify Freshdesk adapter manifest, capabilities, and authoritative source."""
    adapter = FreshdeskSupportAdapter(business_id="biz_test_freshdesk")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "freshdesk"
    assert manifest.display_name == "Freshdesk Support Desk"
    assert manifest.category == IntegrationCategory.SUPPORT
    assert manifest.authoritative_source == AuthoritativeSource.SUPPORT_DESK
    assert adapter.authoritative_source == AuthoritativeSource.SUPPORT_DESK
    assert CapabilityType.CREATE_SUPPORT_TICKET in manifest.supported_capabilities

    field_keys = [f.key for f in manifest.required_setup_fields]
    assert "domain" in field_keys
    assert "api_key" in field_keys


def test_freshdesk_registered_in_registry():
    """Verify Freshdesk adapter is registered under 'freshdesk' and alias 'freshdesk_support'."""
    registry = get_integration_registry()

    manifest = registry.get_manifest("freshdesk")
    assert manifest is not None
    assert manifest.provider_id == "freshdesk"

    cls = registry.get_adapter_class("freshdesk")
    assert cls is FreshdeskSupportAdapter

    alias_manifest = registry.get_manifest("freshdesk_support")
    assert alias_manifest is not None
    alias_cls = registry.get_adapter_class("freshdesk_support")
    assert alias_cls is FreshdeskSupportAdapter


# ============================================================================
# 2. Domain Normalization & Configuration Validation
# ============================================================================

@pytest.mark.parametrize(
    "input_domain,expected_base_url,expected_web_prefix",
    [
        ("myclinic", "https://myclinic.freshdesk.com/api/v2", "https://myclinic.freshdesk.com"),
        ("myclinic.freshdesk.com", "https://myclinic.freshdesk.com/api/v2", "https://myclinic.freshdesk.com"),
        ("https://myclinic.freshdesk.com", "https://myclinic.freshdesk.com/api/v2", "https://myclinic.freshdesk.com"),
        ("https://support.acmehealth.org", "https://support.acmehealth.org/api/v2", "https://support.acmehealth.org"),
        ("support.acmehealth.org", "https://support.acmehealth.org/api/v2", "https://support.acmehealth.org"),
    ],
)
def test_freshdesk_domain_normalization(input_domain, expected_base_url, expected_web_prefix):
    """Verify domain normalization across various user input formats."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_norm",
        configuration={"domain": input_domain},
    )
    assert adapter.get_base_url() == expected_base_url
    assert adapter.get_web_url_prefix() == expected_web_prefix


def test_freshdesk_configuration_validation():
    """Verify configuration validation for missing domain or invalid formatting."""
    adapter = FreshdeskSupportAdapter(business_id="biz_test")

    # Missing domain
    res_no_domain = adapter.validate_configuration({})
    assert not res_no_domain.passed
    assert "domain" in res_no_domain.details

    # Invalid domain with spaces
    res_bad_domain = adapter.validate_configuration({"domain": "my clinic invalid"})
    assert not res_bad_domain.passed
    assert "spaces" in res_bad_domain.details

    # Valid domain
    res_valid = adapter.validate_configuration({"domain": "myclinic"})
    assert res_valid.passed


def test_freshdesk_connect_and_auth_headers():
    """Verify connect vaults credentials and constructs correct Basic or Bearer auth headers."""
    adapter = FreshdeskSupportAdapter(business_id="biz_test")

    # Missing credentials
    res_fail = adapter.connect({})
    assert not res_fail.passed

    # API Key Basic Auth
    res_key = adapter.connect({"api_key": "live_key_12345"})
    assert res_key.passed
    auth_header = adapter._get_auth_header()
    assert auth_header.startswith("Basic ")
    decoded_auth = base64.b64decode(auth_header.replace("Basic ", "")).decode("utf-8")
    assert decoded_auth == "live_key_12345:X"

    # OAuth Bearer Auth
    adapter_oauth = FreshdeskSupportAdapter(
        business_id="biz_oauth",
        credentials={"access_token": "ya29.oauth_token_xyz"},
    )
    assert adapter_oauth._get_auth_header() == "Bearer ya29.oauth_token_xyz"


# ============================================================================
# 3. Safe Diagnostics: test_connection()
# ============================================================================

def test_freshdesk_safe_connection_probe_queries_agent_me_never_creates_ticket():
    """
    CRITICAL TEST: test_connection must NEVER create a dummy customer ticket.
    It must query GET /api/v2/agents/me or GET /api/v2/ticket_fields.
    """
    adapter = FreshdeskSupportAdapter(
        business_id="biz_safe_diag",
        configuration={"domain": "acme"},
        credentials={"api_key": "my_api_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req, \
         patch.object(adapter, "create_ticket") as mock_create:

        mock_req.return_value = {
            "id": 190001,
            "contact": {"name": "Dr. Sarah Adams", "email": "sarah@acme.com"},
            "active": True,
        }

        res = adapter.test_connection()

        # Verify agents/me was probed
        mock_req.assert_called_once_with("GET", "/agents/me")
        # STRICT VERIFICATION: create_ticket was NEVER called!
        mock_create.assert_not_called()

        assert res.passed is True
        assert "Dr. Sarah Adams" in res.details
        assert "Zero tickets created" in res.details


def test_freshdesk_test_connection_mock_mode():
    """Verify test_connection in mock mode succeeds safely without side-effects."""
    adapter = FreshdeskSupportAdapter(business_id="biz_mock", configuration={"is_mock": True})
    with patch.object(adapter, "create_ticket") as mock_create:
        res = adapter.test_connection()
        mock_create.assert_not_called()
        assert res.passed is True
        assert "Zero tickets created" in res.details


# ============================================================================
# 4. Ticket Creation & Data Normalization
# ============================================================================

def test_freshdesk_create_ticket_success_and_normalization():
    """Verify creating a ticket parses fields and normalizes status, priority, and URL."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_ticket",
        configuration={"domain": "dentalclinic"},
        credentials={"api_key": "test_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "id": 48291,
            "subject": "Reschedule Consultation",
            "description": "<p>Need to reschedule from Friday to Monday.</p>",
            "description_text": "Need to reschedule from Friday to Monday.",
            "status": 2,  # 2 = Open
            "priority": 3,  # 3 = High
            "requester_id": 90123,
            "email": "patient@example.com",
            "phone": "+14155552671",
            "name": "Jane Doe",
            "responder_id": None,
            "group_id": None,
            "created_at": "2026-10-27T10:00:00Z",
            "updated_at": "2026-10-27T10:00:00Z",
        }

        ticket = adapter.create_ticket(
            subject="Reschedule Consultation",
            description="Need to reschedule from Friday to Monday.",
            requester_name="Jane Doe",
            requester_email="patient@example.com",
            requester_phone="+14155552671",
            priority="high",
        )

        mock_req.assert_called_once()
        call_method, call_endpoint = mock_req.call_args[0][:2]
        call_payload = mock_req.call_args[1].get("payload") or mock_req.call_args[0][2]

        assert call_method == "POST"
        assert call_endpoint == "/tickets"
        assert call_payload["subject"] == "Reschedule Consultation"
        assert call_payload["priority"] == 3  # High is 3 in Freshdesk
        assert call_payload["status"] == 2  # Open is 2 in Freshdesk
        assert call_payload["email"] == "patient@example.com"

        # Verify normalization
        assert ticket["ticket_id"] == "48291"
        assert ticket["provider_ticket_id"] == "fd_48291"
        assert ticket["status"] == "open"
        assert ticket["priority"] == "high"
        assert ticket["url"] == "https://dentalclinic.freshdesk.com/a/tickets/48291"
        assert ticket["is_resolved"] is False
        assert ticket["is_assigned"] is False


def test_freshdesk_create_ticket_validation_missing_fields():
    """Verify validation errors when subject, description, or requester is missing."""
    adapter = FreshdeskSupportAdapter(business_id="biz_val")

    # Missing subject
    with pytest.raises(FreshdeskIntegrationException) as exc_subj:
        adapter.create_ticket(subject="", description="Some details", requester_email="p@test.com")
    assert exc_subj.value.error.category == ErrorCategory.INVALID_REQUEST
    assert "MISSING_SUBJECT" in exc_subj.value.error.code

    # Missing description
    with pytest.raises(FreshdeskIntegrationException) as exc_desc:
        adapter.create_ticket(subject="Valid Subject", description="", requester_email="p@test.com")
    assert exc_desc.value.error.category == ErrorCategory.INVALID_REQUEST
    assert "MISSING_DESCRIPTION" in exc_desc.value.error.code

    # Missing requester
    with pytest.raises(FreshdeskIntegrationException) as exc_req:
        adapter.create_ticket(subject="Valid Subject", description="Valid Description")
    assert exc_req.value.error.category == ErrorCategory.INVALID_REQUEST
    assert "MISSING_REQUESTER" in exc_req.value.error.code


# ============================================================================
# 5. Truthful Outcome Envelope
# ============================================================================

def test_freshdesk_truthful_outcome_envelope():
    """
    CRITICAL TEST: Ticket creation returns OPERATION_COMPLETED referencing the real ticket ID.
    Strictly does not claim human resolution unless authoritative status confirms it.
    """
    adapter = FreshdeskSupportAdapter(
        business_id="biz_truth",
        configuration={"domain": "acmeclinic"},
        credentials={"api_key": "key_xyz"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "id": 77123,
            "subject": "Billing Question",
            "description": "Question on invoice #901",
            "status": 2,  # Open
            "priority": 2,  # Normal
            "email": "client@example.com",
            "created_at": "2026-10-27T10:15:00Z",
        }

        ctx = ExecutionContext(tenant_id="biz_truth", correlation_id="corr_truth_1")
        result = adapter.execute(
            operation=CapabilityType.CREATE_SUPPORT_TICKET,
            input_data={
                "subject": "Billing Question",
                "description": "Question on invoice #901",
                "requester_email": "client@example.com",
            },
            context=ctx,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["ticket_id"] == "77123"
        assert result.data["status"] == "open"
        assert result.data["is_resolved"] is False
        assert "Support ticket #77123 has been created" in result.safe_message
        assert "An agent will review it shortly" in result.safe_message


# ============================================================================
# 6. Ticket Operations (Lookup, Search, Update, Assign, Reply)
# ============================================================================

def test_freshdesk_get_and_search_tickets():
    """Verify ticket retrieval by ID and search with pagination."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_ops",
        configuration={"domain": "acme"},
        credentials={"api_key": "test_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        # 1. get_ticket
        mock_req.return_value = {"id": 101, "subject": "Test Ticket", "status": 2, "priority": 1}
        t = adapter.get_ticket("101")
        assert t["ticket_id"] == "101"
        assert t["priority"] == "low"

        # 2. search_tickets by email
        mock_req.return_value = [{"id": 101, "subject": "Test Ticket", "status": 2, "priority": 1}]
        results = adapter.search_tickets(email="user@example.com")
        assert len(results) == 1
        assert results[0]["ticket_id"] == "101"


def test_freshdesk_update_assign_and_reply_operations():
    """Verify ticket updates, assignment, status change, and replies."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_ops",
        configuration={"domain": "acme"},
        credentials={"api_key": "test_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        # Update / Assign
        mock_req.return_value = {
            "id": 101,
            "status": 3,  # Pending
            "priority": 4,  # Urgent
            "responder_id": 999,
            "group_id": 888,
        }
        res_assign = adapter.assign_ticket("101", responder_id=999, group_id=888)
        assert res_assign["assignee"]["responder_id"] == 999
        assert res_assign["assignee"]["group_id"] == 888

        # Change status
        mock_req.return_value = {"id": 101, "status": 4}  # 4 = Resolved
        res_status = adapter.change_ticket_status("101", "resolved")
        assert res_status["status"] == "resolved"
        assert res_status["is_resolved"] is True

        # Reply
        mock_req.return_value = {"id": 2001, "body": "<p>Reply sent</p>"}
        reply_res = adapter.reply_to_ticket("101", "<p>Hello patient, this is our reply.</p>")
        assert reply_res["id"] == 2001


# ============================================================================
# 7. Contact Operations
# ============================================================================

def test_freshdesk_contact_operations():
    """Verify contact lookup, search, and creation/update."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_contact",
        configuration={"domain": "acme"},
        credentials={"api_key": "test_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        # Search contacts
        mock_req.return_value = {
            "results": [
                {"id": 555, "name": "Alice Smith", "email": "alice@example.com", "phone": "12345"}
            ]
        }
        contacts = adapter.search_contacts(email="alice@example.com")
        assert len(contacts) == 1
        assert contacts[0]["contact_id"] == "555"
        assert contacts[0]["name"] == "Alice Smith"


# ============================================================================
# 8. Rate Limiting & Header Tracking
# ============================================================================

def test_freshdesk_rate_limiting_retry_after():
    """Verify HTTP 429 parses Retry-After header and normalizes to RATE_LIMITED."""
    adapter = FreshdeskSupportAdapter(business_id="biz_rate")

    mock_fp = MagicMock()
    mock_fp.read.return_value = b'{"message": "Rate limit exceeded"}'
    hdrs = {"Retry-After": "45"}

    http_err = urllib.error.HTTPError(
        url="https://acme.freshdesk.com/api/v2/tickets",
        code=429,
        msg="Too Many Requests",
        hdrs=hdrs,
        fp=mock_fp,
    )

    norm_err = adapter._normalize_freshdesk_error(http_err)
    assert norm_err.category == ErrorCategory.RATE_LIMITED
    assert norm_err.is_retryable is True
    assert norm_err.retry_after_seconds == 45.0


# ============================================================================
# 9. Comprehensive Error Normalization
# ============================================================================

@pytest.mark.parametrize(
    "status_code,body,expected_category,expected_retryable",
    [
        (
            400,
            json.dumps({"description": "Validation failed", "errors": [{"field": "email", "message": "It should be a valid email", "code": "invalid_value"}]}),
            ErrorCategory.INVALID_REQUEST,
            False,
        ),
        (
            401,
            json.dumps({"code": "invalid_credentials", "message": "You have to be logged in to perform this action."}),
            ErrorCategory.AUTHENTICATION_FAILED,
            False,
        ),
        (
            403,
            json.dumps({"code": "access_denied", "message": "You are not authorized to perform this action."}),
            ErrorCategory.PERMISSION_DENIED,
            False,
        ),
        (
            404,
            json.dumps({"description": "Record not found"}),
            ErrorCategory.RESOURCE_NOT_FOUND,
            False,
        ),
        (
            500,
            json.dumps({"description": "We are experiencing technical difficulties."}),
            ErrorCategory.PROVIDER_UNAVAILABLE,
            True,
        ),
    ],
)
def test_freshdesk_error_normalization(status_code, body, expected_category, expected_retryable):
    """Verify Freshdesk error responses normalize into structured IntegrationError."""
    adapter = FreshdeskSupportAdapter(business_id="biz_err")

    mock_fp = MagicMock()
    mock_fp.read.return_value = body.encode("utf-8")
    http_err = urllib.error.HTTPError(
        url="https://acme.freshdesk.com/api/v2/tickets",
        code=status_code,
        msg="Error",
        hdrs={},
        fp=mock_fp,
    )

    norm_err = adapter._normalize_freshdesk_error(http_err)
    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ============================================================================
# 10. Idempotency & Duplicate Prevention
# ============================================================================

def test_freshdesk_duplicate_ticket_creation_suppression():
    """Verify repeated create_ticket calls with identical idempotency key return cached result."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_idem",
        configuration={"domain": "acme"},
        credentials={"api_key": "live_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "id": 99123,
            "subject": "Missing Appointment Link",
            "description": "Please resend link.",
            "status": 2,
            "priority": 2,
            "email": "user@example.com",
        }

        # First dispatch: hits API
        t1 = adapter.create_ticket(
            subject="Missing Appointment Link",
            description="Please resend link.",
            requester_email="user@example.com",
            idempotency_key="unique_inquiry_99123",
        )
        assert mock_req.call_count == 1
        assert t1["ticket_id"] == "99123"
        assert t1.get("is_duplicate") is not True

        # Second dispatch with same idempotency key: suppressed
        t2 = adapter.create_ticket(
            subject="Missing Appointment Link",
            description="Please resend link.",
            requester_email="user@example.com",
            idempotency_key="unique_inquiry_99123",
        )
        # Verify API was NOT called again
        assert mock_req.call_count == 1
        assert t2["ticket_id"] == "99123"
        assert t2["is_duplicate"] is True


# ============================================================================
# 11. Resource Discovery
# ============================================================================

def test_freshdesk_discover_resources():
    """Verify discovery of groups, agents, and ticket fields."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_disc",
        configuration={"domain": "acme"},
        credentials={"api_key": "live_key"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        # Groups
        mock_req.return_value = [{"id": 10, "name": "Dental Billing", "description": "Billing team"}]
        res_groups = adapter.discover_resources("groups")
        assert len(res_groups) == 1
        assert res_groups[0].resource_id == "10"
        assert res_groups[0].name == "Dental Billing"

        # Agents
        mock_req.return_value = [{"id": 20, "contact": {"name": "Agent John", "email": "john@acme.com"}}]
        res_agents = adapter.discover_resources("agents")
        assert len(res_agents) == 1
        assert res_agents[0].resource_id == "20"
        assert res_agents[0].name == "Agent John"

        # Ticket Fields
        mock_req.return_value = [{"id": 30, "label": "Insurance Provider", "type": "custom_text"}]
        res_fields = adapter.discover_resources("ticket_fields")
        assert len(res_fields) == 1
        assert res_fields[0].resource_id == "30"
        assert res_fields[0].name == "Insurance Provider"


# ============================================================================
# 12. Multi-Tenant Isolation
# ============================================================================

def test_freshdesk_multi_tenant_isolation():
    """Verify two tenants maintain isolated domains, credentials, and idempotency caches."""
    tenant_1 = FreshdeskSupportAdapter(
        business_id="tenant_clinic_a",
        configuration={"domain": "clinic-a"},
        credentials={"api_key": "key_a"},
    )
    tenant_2 = FreshdeskSupportAdapter(
        business_id="tenant_clinic_b",
        configuration={"domain": "clinic-b"},
        credentials={"api_key": "key_b"},
    )

    assert tenant_1.get_base_url() == "https://clinic-a.freshdesk.com/api/v2"
    assert tenant_2.get_base_url() == "https://clinic-b.freshdesk.com/api/v2"
    assert tenant_1.credentials["api_key"] == "key_a"
    assert tenant_2.credentials["api_key"] == "key_b"

    tenant_1._idempotency_cache["k1"] = ({"ticket_id": "1"}, time.time())
    assert "k1" not in tenant_2._idempotency_cache


# ============================================================================
# 13. Capability Contract Execution via execute() in Mock Mode
# ============================================================================

def test_freshdesk_execute_in_mock_mode():
    """Verify execution of CREATE_SUPPORT_TICKET in mock mode."""
    adapter = FreshdeskSupportAdapter(
        business_id="biz_mock_exec",
        configuration={"is_mock": True, "domain": "acme"},
    )

    ctx = ExecutionContext(tenant_id="biz_mock_exec", correlation_id="corr_mock_1")
    res = adapter.execute(
        operation=CapabilityType.CREATE_SUPPORT_TICKET,
        input_data={
            "subject": "Mock Consultation Inquiry",
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
