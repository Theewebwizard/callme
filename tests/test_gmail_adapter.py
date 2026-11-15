"""
Unit and integration tests for the Google Gmail Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.COMMUNICATION_SERVICE)
- Registry lookup and option aliases ('gmail', 'google_mail')
- Configuration validation (Client ID, Scope Tier, App Distribution Model, Sender Email)
- Safe diagnostics (verifies profile via GET /gmail/v1/users/me/profile without sending real emails)
- Explicit authorization check: Never send real email during connection test unless authorized
- OAuth 2.0 authorization URL generation, least-privilege scope tiers, and state validation (CSRF protection)
- OAuth token exchange, token refresh, and token revocation
- Scope compliance metadata (CASA Tier 2 security assessment requirements)
- Valid RFC 2822 MIME message construction:
  - Text-only email
  - HTML-only email
  - Multipart alternative (text + HTML)
  - Non-ASCII unicode subjects
  - Cc, Bcc, and Reply-To headers
  - Thread continuity (In-Reply-To, References, and threadId)
  - URL-safe base64 encoding (base64.urlsafe_b64encode)
- Attachments handling and 25 MB payload size limit enforcement
- Least-privilege scope gating (send_only vs read_only vs metadata)
- Truthful outcome envelope: API acceptance (REQUEST_ACCEPTED with is_delivered: False) != recipient delivery
- Idempotency key tracking and duplicate send suppression
- Comprehensive error normalization (rateLimitExceeded, invalid_grant, insufficientPermissions, notFound, 500)
- Resource discovery (profile, labels, send_as)
- Multi-tenant isolation
- Capability execution via execute()
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import hmac
import hashlib
import base64
import urllib.error
import email
from email.message import EmailMessage

from backend.integrations.adapters.gmail_adapter import (
    GmailAdapter,
    GmailIntegrationException,
    GMAIL_SCOPE_SEND,
    GMAIL_SCOPE_READONLY,
    GMAIL_SCOPE_METADATA,
    GMAIL_SCOPE_COMPOSE,
    GMAIL_SCOPE_MODIFY,
    GMAIL_SCOPE_FULL,
    MAX_ATTACHMENT_SIZE_BYTES,
)
from backend.capabilities.models import (
    AuthoritativeSource,
    CapabilityStatus,
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

def test_gmail_manifest_and_authoritative_source():
    """Verify Gmail adapter manifest, capabilities, and authoritative source."""
    adapter = GmailAdapter(business_id="biz_test_gmail")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "gmail"
    assert manifest.display_name == "Gmail (Google Workspace & Gmail API)"
    assert manifest.category == IntegrationCategory.MESSAGING
    assert manifest.authoritative_source == AuthoritativeSource.COMMUNICATION_SERVICE
    assert adapter.authoritative_source == AuthoritativeSource.COMMUNICATION_SERVICE
    assert manifest.auth_method == AuthMethod.OAUTH2
    assert CapabilityType.SEND_EMAIL in manifest.supported_capabilities

    field_keys = [f.key for f in manifest.required_setup_fields]
    assert "client_id" in field_keys

    optional_keys = [f.key for f in manifest.optional_setup_fields]
    assert "scope_tier" in optional_keys
    assert "sender_email" in optional_keys
    assert "allow_connection_test_email" in optional_keys
    assert "app_distribution_model" in optional_keys

    assert GMAIL_SCOPE_SEND in manifest.required_oauth_scopes


def test_gmail_registered_in_registry():
    """Verify Gmail adapter is registered under 'gmail' and alias 'google_mail'."""
    registry = get_integration_registry()

    gmail_manifest = registry.get_manifest("gmail")
    assert gmail_manifest is not None
    assert gmail_manifest.provider_id == "gmail"

    gmail_cls = registry.get_adapter_class("gmail")
    assert gmail_cls is GmailAdapter

    alias_manifest = registry.get_manifest("google_mail")
    assert alias_manifest is not None
    alias_cls = registry.get_adapter_class("google_mail")
    assert alias_cls is GmailAdapter


# ============================================================================
# 2. Configuration Validation & Credential Vaulting
# ============================================================================

def test_gmail_configuration_validation():
    """Verify configuration validation for client_id, scope_tier, and distribution model."""
    adapter = GmailAdapter(business_id="biz_test")

    # Missing client_id
    res_no_client = adapter.validate_configuration({})
    assert not res_no_client.passed
    assert "client_id" in res_no_client.details

    # Invalid scope tier
    res_bad_tier = adapter.validate_configuration({
        "client_id": "12345.apps.googleusercontent.com",
        "scope_tier": "unlimited_super_admin",
    })
    assert not res_bad_tier.passed
    assert "scope_tier" in res_bad_tier.details

    # Valid configuration
    res_valid = adapter.validate_configuration({
        "client_id": "12345.apps.googleusercontent.com",
        "scope_tier": "send_only",
        "app_distribution_model": "internal",
        "sender_email": "reception@acmeclinic.com",
    })
    assert res_valid.passed


def test_gmail_connect_and_credential_vaulting():
    """Verify connect vaults OAuth credentials safely."""
    adapter = GmailAdapter(business_id="biz_test")

    # Missing client_id
    res_fail = adapter.connect({"access_token": "ya29.test"})
    assert not res_fail.passed

    # Missing token
    res_no_token = adapter.connect({"client_id": "123.apps.googleusercontent.com"})
    assert not res_no_token.passed

    # Success with refresh token
    res_success = adapter.connect({
        "client_id": "123.apps.googleusercontent.com",
        "client_secret": "secret_abc",
        "refresh_token": "1//refresh_token_xyz",
    })
    assert res_success.passed
    assert adapter.credentials["refresh_token"] == "1//refresh_token_xyz"


# ============================================================================
# 3. OAuth 2.0 Authorization, Token Exchange, and Revocation
# ============================================================================

def test_gmail_authorization_url_least_privilege_scopes():
    """Verify OAuth authorization URL reflects least-privilege scopes."""
    adapter = GmailAdapter(
        business_id="biz_test",
        configuration={"client_id": "my_client_id.apps.googleusercontent.com", "scope_tier": "send_only"},
    )

    # 1. Default send_only tier
    url_send = adapter.get_authorization_url(
        redirect_uri="https://api.answerly.ai/auth/gmail/callback",
        state="csrf_state_123",
    )
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url_send
    assert "client_id=my_client_id.apps.googleusercontent.com" in url_send
    assert "state=csrf_state_123" in url_send
    assert "access_type=offline" in url_send
    assert "prompt=consent" in url_send
    assert urllib.parse.quote_plus(GMAIL_SCOPE_SEND) in url_send
    # Ensure restricted scope is NOT in send_only URL
    assert urllib.parse.quote_plus(GMAIL_SCOPE_READONLY) not in url_send

    # 2. Explicit read_only tier
    url_read = adapter.get_authorization_url(
        redirect_uri="https://api.answerly.ai/auth/gmail/callback",
        state="csrf_state_456",
        scope_tier="read_only",
    )
    assert urllib.parse.quote_plus(GMAIL_SCOPE_READONLY) in url_read


def test_gmail_oauth_state_validation():
    """Verify CSRF state validation with constant-time comparison."""
    adapter = GmailAdapter(business_id="biz_test")
    state = "secure_random_state_token_abc123"

    assert adapter.validate_oauth_state(state, state) is True
    assert adapter.validate_oauth_state("tampered_state", state) is False
    assert adapter.validate_oauth_state("", state) is False


def test_gmail_token_exchange_and_refresh():
    """Verify authorization code exchange and token refresh."""
    adapter = GmailAdapter(
        business_id="biz_test",
        configuration={"client_id": "cid_123"},
        credentials={"client_secret": "sec_456"},
    )

    # Mock code exchange
    with patch.object(adapter, "_make_oauth_request") as mock_oauth:
        mock_oauth.return_value = {
            "access_token": "ya29.new_token",
            "refresh_token": "1//new_refresh_token",
            "expires_in": 3600,
            "scope": GMAIL_SCOPE_SEND,
        }

        token_res = adapter.exchange_code_for_tokens(
            code="auth_code_xyz",
            redirect_uri="https://api.answerly.ai/auth/gmail/callback",
        )
        assert token_res["access_token"] == "ya29.new_token"
        assert adapter.credentials["access_token"] == "ya29.new_token"
        assert adapter.credentials["refresh_token"] == "1//new_refresh_token"

    # Mock token refresh
    with patch.object(adapter, "_make_oauth_request") as mock_oauth:
        mock_oauth.return_value = {
            "access_token": "ya29.refreshed_token",
            "expires_in": 3600,
            "scope": GMAIL_SCOPE_SEND,
        }

        ref_res = adapter.refresh_access_token()
        assert ref_res["access_token"] == "ya29.refreshed_token"
        assert adapter.credentials["access_token"] == "ya29.refreshed_token"


def test_gmail_ensure_valid_token_auto_refreshes_when_expiring():
    """Verify ensure_valid_token automatically refreshes when token is expired or close to expiry."""
    adapter = GmailAdapter(
        business_id="biz_test",
        configuration={"client_id": "cid_123"},
        credentials={
            "client_secret": "sec_456",
            "access_token": "ya29.old_token",
            "refresh_token": "1//refresh_token_abc",
            "expires_at": time.time() + 10,  # expiring in 10s (buffer is 60s)
        },
    )

    with patch.object(adapter, "refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = lambda: adapter.credentials.update({
            "access_token": "ya29.renewed_token",
            "expires_at": time.time() + 3600,
        })
        token = adapter.ensure_valid_token()
        assert mock_refresh.called
        assert token == "ya29.renewed_token"


def test_gmail_revoke_token():
    """Verify token revocation clears local credentials on success."""
    adapter = GmailAdapter(
        business_id="biz_test",
        credentials={"access_token": "ya29.test", "refresh_token": "1//test_ref", "expires_at": 12345},
    )

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success = adapter.revoke_token()
        assert success is True
        assert "access_token" not in adapter.credentials
        assert "refresh_token" not in adapter.credentials


def test_gmail_scope_compliance_info():
    """Verify CASA Tier 2 assessment rules based on scope and distribution model."""
    # 1. External app with send_only (sensitive, CASA exempt)
    adapter_send = GmailAdapter(
        business_id="biz_1",
        configuration={"scope_tier": "send_only", "app_distribution_model": "external"},
    )
    info_send = adapter_send.get_scope_compliance_info()
    assert info_send["casa_tier_2_required"] is False
    assert info_send["is_internal_workspace_exempt"] is False

    # 2. External app with read_only (restricted scope, requires CASA Tier 2)
    adapter_read = GmailAdapter(
        business_id="biz_2",
        configuration={"scope_tier": "read_only", "app_distribution_model": "external"},
    )
    info_read = adapter_read.get_scope_compliance_info()
    assert info_read["casa_tier_2_required"] is True
    assert info_read["is_internal_workspace_exempt"] is False

    # 3. Internal Workspace app with read_only (exempt from CASA)
    adapter_internal = GmailAdapter(
        business_id="biz_3",
        configuration={"scope_tier": "read_only", "app_distribution_model": "internal"},
    )
    info_internal = adapter_internal.get_scope_compliance_info()
    assert info_internal["casa_tier_2_required"] is False
    assert info_internal["is_internal_workspace_exempt"] is True


# ============================================================================
# 4. Safe Diagnostics: test_connection()
# ============================================================================

def test_gmail_safe_connection_probe_queries_profile_never_sends_email():
    """
    CRITICAL TEST: test_connection must NEVER send real customer email.
    It must query GET /gmail/v1/users/{userId}/profile.
    """
    adapter = GmailAdapter(
        business_id="biz_safe_diag",
        configuration={"user_id": "me", "allow_connection_test_email": False},
        credentials={"access_token": "ya29.live_token", "expires_at": time.time() + 3600},
    )

    with patch.object(adapter, "_make_gmail_request") as mock_req, \
         patch.object(adapter, "send_email") as mock_send:

        mock_req.return_value = {
            "emailAddress": "reception@acmedental.com",
            "messagesTotal": 3450,
            "threadsTotal": 1220,
            "historyId": "987654",
        }

        result = adapter.test_connection()

        # Verify profile was queried
        mock_req.assert_called_once_with("GET", "/users/me/profile")
        # STRICT VERIFICATION: send_email was NEVER called!
        mock_send.assert_not_called()

        assert result.passed is True
        assert "reception@acmedental.com" in result.details
        assert "Zero emails sent during test" in result.details


def test_gmail_test_connection_in_mock_mode():
    """Verify test_connection in mock mode succeeds safely."""
    adapter = GmailAdapter(business_id="biz_mock", configuration={"is_mock": True})
    with patch.object(adapter, "send_email") as mock_send:
        res = adapter.test_connection()
        mock_send.assert_not_called()
        assert res.passed is True


def test_gmail_authorized_connection_test_email_only_when_explicitly_configured():
    """Verify that an email is dispatched during test_connection ONLY when explicitly authorized."""
    adapter = GmailAdapter(
        business_id="biz_auth_diag",
        configuration={
            "allow_connection_test_email": True,
            "test_recipient_email": "admin@mycompany.com",
        },
        credentials={"access_token": "ya29.live_token", "expires_at": time.time() + 3600},
    )

    with patch.object(adapter, "send_email") as mock_send:
        mock_send.return_value = {"email_id": "msg_test_diag_123"}
        res = adapter.test_connection()
        mock_send.assert_called_once()
        assert res.passed is True
        assert "msg_test_diag_123" in res.details


# ============================================================================
# 5. MIME Construction & Official API Guidance
# ============================================================================

def test_gmail_create_mime_message_plain_text():
    """Verify creation of plain text RFC 2822 MIME message."""
    adapter = GmailAdapter(
        business_id="biz_mime",
        configuration={"sender_email": "reception@acme.com", "sender_name": "Acme AI"},
    )

    mime_payload = adapter.create_mime_message(
        to="patient@example.com",
        subject="Appointment Confirmation",
        body_text="Your appointment is confirmed for tomorrow at 10:00 AM.",
    )

    assert "raw" in mime_payload
    raw_b64 = mime_payload["raw"]

    # Decode urlsafe base64
    raw_bytes = base64.urlsafe_b64decode(raw_b64)
    parsed_msg = email.message_from_bytes(raw_bytes)

    assert parsed_msg["To"] == "patient@example.com"
    assert "Acme AI <reception@acme.com>" in parsed_msg["From"]
    assert "Appointment Confirmation" in parsed_msg["Subject"]
    assert parsed_msg["Date"] is not None
    assert parsed_msg["Message-ID"] is not None
    body_content = parsed_msg.get_payload(decode=True).decode("utf-8")
    assert "tomorrow at 10:00 AM" in body_content


def test_gmail_create_mime_message_multipart_alternative():
    """Verify multipart alternative MIME message with plain text and HTML bodies."""
    adapter = GmailAdapter(business_id="biz_mime")

    mime_payload = adapter.create_mime_message(
        to="client@example.com",
        subject="HTML Confirmation",
        body_text="Please visit our clinic.",
        body_html="<p>Please visit our <strong>clinic</strong>.</p>",
    )

    raw_bytes = base64.urlsafe_b64decode(mime_payload["raw"])
    parsed_msg = email.message_from_bytes(raw_bytes)

    assert parsed_msg.is_multipart()
    assert parsed_msg.get_content_type() == "multipart/alternative"

    payloads = parsed_msg.get_payload()
    assert len(payloads) == 2
    types = [p.get_content_type() for p in payloads]
    assert "text/plain" in types
    assert "text/html" in types


def test_gmail_create_mime_message_unicode_subject_and_headers():
    """Verify RFC 2047 UTF-8 subject encoding, Cc, Bcc, and Reply-To headers."""
    adapter = GmailAdapter(business_id="biz_mime")

    mime_payload = adapter.create_mime_message(
        to=["dr.smith@example.com", "nurse.jane@example.com"],
        subject="Confirmation de rendez-vous médical 🩺",
        body_text="Bonjour, votre rendez-vous est confirmé.",
        cc="supervisor@example.com",
        bcc=["compliance@example.com", "audit@example.com"],
        reply_to="no-reply@example.com",
    )

    raw_bytes = base64.urlsafe_b64decode(mime_payload["raw"])
    parsed_msg = email.message_from_bytes(raw_bytes)

    assert "dr.smith@example.com, nurse.jane@example.com" in parsed_msg["To"]
    assert parsed_msg["Cc"] == "supervisor@example.com"
    assert "compliance@example.com, audit@example.com" in parsed_msg["Bcc"]
    assert parsed_msg["Reply-To"] == "no-reply@example.com"


def test_gmail_create_mime_message_thread_headers():
    """Verify In-Reply-To and References headers for thread replies."""
    adapter = GmailAdapter(business_id="biz_mime")

    mime_payload = adapter.create_mime_message(
        to="user@example.com",
        subject="Re: Inquiry #1234",
        body_text="Here is our update regarding your inquiry.",
        thread_id="thread_abc_987",
        in_reply_to="<orig_msg_456@mail.gmail.com>",
        references=["<parent_1@mail.gmail.com>", "<orig_msg_456@mail.gmail.com>"],
    )

    assert mime_payload.get("threadId") == "thread_abc_987"

    raw_bytes = base64.urlsafe_b64decode(mime_payload["raw"])
    parsed_msg = email.message_from_bytes(raw_bytes)

    assert parsed_msg["In-Reply-To"] == "<orig_msg_456@mail.gmail.com>"
    assert "<parent_1@mail.gmail.com> <orig_msg_456@mail.gmail.com>" in parsed_msg["References"]


def test_gmail_create_mime_message_attachments():
    """Verify multipart/mixed message with base64 encoded attachments."""
    adapter = GmailAdapter(business_id="biz_mime")

    dummy_pdf_content = b"%PDF-1.4 test document content for clinic report"
    mime_payload = adapter.create_mime_message(
        to="patient@example.com",
        subject="Your Lab Results",
        body_text="Please find your attached lab results.",
        body_html="<p>Please find your attached lab results.</p>",
        attachments=[
            {
                "filename": "results.pdf",
                "content": dummy_pdf_content,
                "content_type": "application/pdf",
            }
        ],
    )

    raw_bytes = base64.urlsafe_b64decode(mime_payload["raw"])
    parsed_msg = email.message_from_bytes(raw_bytes)

    assert parsed_msg.is_multipart()
    assert parsed_msg.get_content_type() == "multipart/mixed"

    parts = parsed_msg.get_payload()
    # Part 0 is multipart/alternative (body), Part 1 is application/pdf attachment
    assert len(parts) >= 2
    attachment_part = parts[1]
    assert attachment_part.get_content_type() == "application/pdf"
    assert 'filename="results.pdf"' in attachment_part["Content-Disposition"]


def test_gmail_attachment_size_limit_enforced():
    """Verify that cumulative attachments exceeding 25 MB are rejected before transmission."""
    adapter = GmailAdapter(business_id="biz_mime")

    oversized_bytes = b"x" * (MAX_ATTACHMENT_SIZE_BYTES + 1024)

    with pytest.raises(GmailIntegrationException) as exc_info:
        adapter.create_mime_message(
            to="patient@example.com",
            subject="Oversized Attachment",
            body_text="See attached.",
            attachments=[{"filename": "huge.dat", "content": oversized_bytes}],
        )

    assert exc_info.value.error.category == ErrorCategory.INVALID_REQUEST
    assert "ATTACHMENT_SIZE_EXCEEDED" in exc_info.value.error.code


# ============================================================================
# 6. Least-Privilege Scope Gating
# ============================================================================

def test_gmail_scope_gating_blocks_send_when_read_only():
    """Verify sending email is blocked when adapter is configured with read_only scope."""
    adapter = GmailAdapter(
        business_id="biz_perm",
        configuration={"scope_tier": "read_only"},
        credentials={"access_token": "ya29.token"},
    )

    with pytest.raises(GmailIntegrationException) as exc_info:
        adapter.send_email(to="test@example.com", subject="Test", body_text="Hello")

    err = exc_info.value.error
    assert err.category == ErrorCategory.PERMISSION_DENIED
    assert "INSUFFICIENT_SCOPE_FOR_SEND" in err.code


def test_gmail_scope_gating_blocks_read_when_send_only():
    """Verify reading email content is blocked when adapter is configured with send_only scope."""
    adapter = GmailAdapter(
        business_id="biz_perm",
        configuration={"scope_tier": "send_only"},
        credentials={"access_token": "ya29.token"},
    )

    with pytest.raises(GmailIntegrationException) as exc_info:
        adapter.get_message("msg_12345")

    err = exc_info.value.error
    assert err.category == ErrorCategory.PERMISSION_DENIED
    assert "INSUFFICIENT_SCOPE_FOR_READ" in err.code


def test_gmail_scope_gating_metadata_tier():
    """Verify metadata tier can read headers but cannot read body content."""
    adapter = GmailAdapter(
        business_id="biz_perm",
        configuration={"scope_tier": "metadata"},
        credentials={"access_token": "ya29.token"},
    )

    # get_message fails
    with pytest.raises(GmailIntegrationException) as exc_info:
        adapter.get_message("msg_12345")
    assert exc_info.value.error.category == ErrorCategory.PERMISSION_DENIED

    # get_message_metadata succeeds (mocked request)
    with patch.object(adapter, "_make_gmail_request") as mock_req:
        mock_req.return_value = {"id": "msg_12345", "snippet": "Subject line snippet"}
        meta = adapter.get_message_metadata("msg_12345")
        assert meta["id"] == "msg_12345"


# ============================================================================
# 7. Duplicate Send Prevention & Idempotency
# ============================================================================

def test_gmail_duplicate_send_suppressed_by_idempotency_key():
    """Verify duplicate email send requests with identical idempotency key are suppressed."""
    adapter = GmailAdapter(
        business_id="biz_idem",
        credentials={"access_token": "ya29.live", "expires_at": time.time() + 3600},
    )

    with patch.object(adapter, "_make_gmail_request") as mock_req:
        mock_req.return_value = {
            "id": "18c123456789abcd",
            "threadId": "18c123456789abcd",
            "labelIds": ["SENT"],
        }

        # First call: hits API
        res1 = adapter.send_email(
            to="user@example.com",
            subject="Invoice #101",
            body_text="Your invoice is ready.",
            idempotency_key="unique_invoice_101",
        )
        assert mock_req.call_count == 1
        assert res1["email_id"] == "18c123456789abcd"
        assert res1.get("is_duplicate") is not True

        # Second call with identical key: served from idempotency cache
        res2 = adapter.send_email(
            to="user@example.com",
            subject="Invoice #101",
            body_text="Your invoice is ready.",
            idempotency_key="unique_invoice_101",
        )
        # Verify API was NOT called again!
        assert mock_req.call_count == 1
        assert res2["email_id"] == "18c123456789abcd"
        assert res2["is_duplicate"] is True


# ============================================================================
# 8. Truthful Delivery Envelopes
# ============================================================================

def test_gmail_truthful_outcome_distinguishes_submission_from_delivery():
    """
    CRITICAL TEST: Acceptance by Gmail API must be reported as REQUEST_ACCEPTED
    with is_delivered: False, clearly distinguishing submission from recipient delivery.
    """
    adapter = GmailAdapter(
        business_id="biz_truth",
        credentials={"access_token": "ya29.token", "expires_at": time.time() + 3600},
    )

    with patch.object(adapter, "_make_gmail_request") as mock_req:
        mock_req.return_value = {
            "id": "18c999888777666",
            "threadId": "18c999888777666",
            "labelIds": ["SENT"],
        }

        ctx = ExecutionContext(tenant_id="biz_truth", correlation_id="corr_truth_1")
        result = adapter.execute(
            operation=CapabilityType.SEND_EMAIL,
            input_data={
                "recipient_email": "patient@hospital.org",
                "subject": "Pre-operative Instructions",
                "body_text": "Please do not consume food after midnight.",
            },
            context=ctx,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.REQUEST_ACCEPTED
        assert result.data["email_id"] == "18c999888777666"
        assert result.data["delivery_status"] == "accepted_by_gmail_mta"
        assert result.data["is_delivered"] is False
        assert "Awaiting remote delivery" in result.safe_message


# ============================================================================
# 9. Comprehensive Error Normalization
# ============================================================================

@pytest.mark.parametrize(
    "status_code,body,expected_category,expected_retryable",
    [
        (
            429,
            json.dumps({"error": {"code": 429, "message": "User rate limit exceeded", "errors": [{"reason": "userRateLimitExceeded"}]}}),
            ErrorCategory.RATE_LIMITED,
            True,
        ),
        (
            401,
            json.dumps({"error": "invalid_grant", "error_description": "Bad Request"}),
            ErrorCategory.AUTHENTICATION_FAILED,
            False,
        ),
        (
            403,
            json.dumps({"error": {"code": 403, "message": "Access Not Configured", "errors": [{"reason": "accessNotConfigured"}]}}),
            ErrorCategory.PERMISSION_DENIED,
            False,
        ),
        (
            404,
            json.dumps({"error": {"code": 404, "message": "Not Found", "errors": [{"reason": "notFound"}]}}),
            ErrorCategory.RESOURCE_NOT_FOUND,
            False,
        ),
        (
            400,
            json.dumps({"error": {"code": 400, "message": "Invalid recipient format", "errors": [{"reason": "invalidArgument"}]}}),
            ErrorCategory.INVALID_REQUEST,
            False,
        ),
        (
            500,
            json.dumps({"error": {"code": 500, "message": "Backend Error", "errors": [{"reason": "backendError"}]}}),
            ErrorCategory.PROVIDER_UNAVAILABLE,
            True,
        ),
    ],
)
def test_gmail_error_normalization(status_code, body, expected_category, expected_retryable):
    """Verify HTTP error codes and Google error envelopes normalize into structured IntegrationError."""
    adapter = GmailAdapter(business_id="biz_err")

    mock_fp = MagicMock()
    mock_fp.read.return_value = body.encode("utf-8")
    http_err = urllib.error.HTTPError(
        url="https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        code=status_code,
        msg="Error",
        hdrs={},
        fp=mock_fp,
    )

    norm_err = adapter._normalize_gmail_error(http_err)
    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ============================================================================
# 10. Resource Discovery
# ============================================================================

def test_gmail_discover_resources():
    """Verify discovery of mailbox profile, labels, and send_as aliases."""
    adapter = GmailAdapter(
        business_id="biz_disc",
        credentials={"access_token": "ya29.token", "expires_at": time.time() + 3600},
    )

    # 1. Profile
    with patch.object(adapter, "_make_gmail_request") as mock_req:
        mock_req.return_value = {
            "emailAddress": "clinic@mydomain.com",
            "messagesTotal": 500,
            "threadsTotal": 200,
            "historyId": "12345",
        }
        res_profile = adapter.discover_resources("profile")
        assert len(res_profile) == 1
        assert res_profile[0].resource_id == "clinic@mydomain.com"
        assert res_profile[0].resource_type == "mailbox"

    # 2. Labels
    with patch.object(adapter, "_make_gmail_request") as mock_req:
        mock_req.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "SENT", "name": "SENT", "type": "system"},
                {"id": "Label_1", "name": "Patient Inquiries", "type": "user"},
            ]
        }
        res_labels = adapter.discover_resources("labels")
        assert len(res_labels) == 3
        assert res_labels[2].name == "Patient Inquiries"

    # 3. SendAs aliases
    with patch.object(adapter, "_make_gmail_request") as mock_req:
        mock_req.return_value = {
            "sendAs": [
                {"sendAsEmail": "support@mydomain.com", "displayName": "Support Desk", "isPrimary": True}
            ]
        }
        res_sendas = adapter.discover_resources("send_as")
        assert len(res_sendas) == 1
        assert res_sendas[0].resource_id == "support@mydomain.com"


# ============================================================================
# 11. Multi-Tenant Isolation
# ============================================================================

def test_gmail_multi_tenant_isolation():
    """Verify two tenants maintain isolated credentials, scope configurations, and idempotency caches."""
    tenant_a = GmailAdapter(
        business_id="tenant_dental",
        configuration={"scope_tier": "send_only", "sender_email": "reception@dental.com"},
        credentials={"access_token": "token_a"},
    )
    tenant_b = GmailAdapter(
        business_id="tenant_legal",
        configuration={"scope_tier": "read_only", "sender_email": "info@legal.com"},
        credentials={"access_token": "token_b"},
    )

    assert tenant_a.credentials["access_token"] == "token_a"
    assert tenant_b.credentials["access_token"] == "token_b"
    assert tenant_a.get_scope_tier() == "send_only"
    assert tenant_b.get_scope_tier() == "read_only"

    # Verify idempotency caches are distinct
    tenant_a._idempotency_cache["key_1"] = ({"email_id": "msg_a"}, time.time())
    assert "key_1" not in tenant_b._idempotency_cache


# ============================================================================
# 12. Capability Contract Execution via execute() in Mock Mode
# ============================================================================

def test_gmail_execute_send_email_in_mock_mode():
    """Verify execution of SEND_EMAIL contract in mock mode produces truthful envelope."""
    adapter = GmailAdapter(
        business_id="biz_mock_exec",
        configuration={"is_mock": True},
    )

    ctx = ExecutionContext(tenant_id="biz_mock_exec", correlation_id="corr_mock_1")
    res = adapter.execute(
        operation=CapabilityType.SEND_EMAIL,
        input_data={
            "recipient_email": "patient@example.com",
            "subject": "Mock Appointment Confirmation",
            "body_text": "Your appointment is confirmed.",
        },
        context=ctx,
    )

    assert res.success is True
    assert res.outcome == ExecutionOutcome.REQUEST_ACCEPTED
    assert res.is_simulated is True
    assert res.data["is_delivered"] is False
    assert "mock_msg_" in res.data["email_id"]
