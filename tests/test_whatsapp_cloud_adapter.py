"""
Unit and integration tests for the WhatsApp Business Platform (Cloud API) Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.COMMUNICATION_SERVICE)
- Registry lookup and option aliases ('whatsapp', 'whatsapp_cloud', 'whatsapp_business')
- Configuration validation (Phone Number ID, WABA ID, access token, app secret)
- Safe diagnostics (verifies registration via GET /{phone_number_id} without sending real customer messages)
- Recipient phone number normalization (E.164 without leading '+')
- 24-Hour Customer Service Window (CSW) policy enforcement:
  - Freeform text blocked outside 24h window
  - Inbound message opens/refreshes window
  - Freeform text allowed within window
  - Window expiration re-blocks freeform text
- Pre-approved Meta template messages (allowed outside 24h window)
- User opt-in / consent verification
- Template discovery from WABA (GET /{waba_id}/message_templates)
- Truthful outcome envelope: API acceptance (REQUEST_ACCEPTED with wamid) != actual device delivery
- Webhook challenge handshake (hub.mode, hub.verify_token, hub.challenge)
- Webhook authenticity verification via HMAC-SHA256 (X-Hub-Signature-256)
- Webhook event deduplication (at-least-once delivery protection)
- Delivery status normalization (sent, delivered, read, failed)
- Comprehensive error normalization (131047, 130429, 190, 132000, 131026, 500)
- Multi-tenant isolation
- Capability contract execution via execute()
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import hmac
import hashlib
import urllib.error
from datetime import datetime, timezone
import io

from backend.integrations.adapters.whatsapp_cloud_adapter import (
    WhatsAppCloudAdapter,
    WhatsAppIntegrationException,
    CUSTOMER_SERVICE_WINDOW_SECONDS,
    DEFAULT_GRAPH_VERSION,
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
    WebhookRequest,
    IntegrationError,
)
from backend.integrations.registry import get_integration_registry


# ==============================================================================
# Helper for Mocking HTTP Responses
# ==============================================================================

class MockHttpResponse:
    def __init__(self, data: bytes, code: int = 200, headers: dict = None):
        self._data = data
        self._code = code
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._data

    def getcode(self) -> int:
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def make_mock_graph_error(code: int, error_code: int, message: str, error_type: str = "OAuthException", headers: dict = None):
    body_dict = {
        "error": {
            "message": message,
            "type": error_type,
            "code": error_code,
            "fbtrace_id": "trace_xyz_123",
        }
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")
    fp = io.BytesIO(body_bytes)
    return urllib.error.HTTPError(
        url="https://graph.facebook.com/v21.0/messages",
        code=code,
        msg="HTTP Error",
        hdrs=headers or {},
        fp=fp,
    )


# ==============================================================================
# 1. Manifest, Registry & Authoritative Source
# ==============================================================================

def test_whatsapp_manifest_and_authoritative_source():
    """Verify WhatsApp Cloud adapter manifest declarations and COMMUNICATION_SERVICE source."""
    adapter = WhatsAppCloudAdapter(business_id="tenant_clinic")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "whatsapp"
    assert manifest.display_name == "WhatsApp Business Platform (Cloud API)"
    assert manifest.category == IntegrationCategory.MESSAGING
    assert manifest.authoritative_source == AuthoritativeSource.COMMUNICATION_SERVICE
    assert adapter.authoritative_source == AuthoritativeSource.COMMUNICATION_SERVICE
    assert manifest.auth_method == AuthMethod.BEARER_TOKEN

    # Scopes
    assert "whatsapp_business_messaging" in manifest.required_oauth_scopes
    assert "whatsapp_business_management" in manifest.required_oauth_scopes

    # Capabilities
    caps = adapter.get_supported_capabilities()
    assert CapabilityType.SEND_MESSAGE in caps


def test_whatsapp_registered_in_registry():
    """Verify registry catalogs WhatsApp under 'whatsapp', 'whatsapp_cloud', and 'whatsapp_business'."""
    registry = get_integration_registry()
    manifest_primary = registry.get_manifest("whatsapp")
    assert manifest_primary is not None
    assert manifest_primary.provider_id == "whatsapp"

    # Aliases
    assert registry.get_adapter_class("whatsapp_cloud") is WhatsAppCloudAdapter
    assert registry.get_adapter_class("whatsapp_business") is WhatsAppCloudAdapter


# ==============================================================================
# 2. Configuration Validation & Phone Number Normalization
# ==============================================================================

def test_whatsapp_configuration_validation():
    """Verify validate_configuration checks Phone Number ID, WABA ID, and token."""
    adapter = WhatsAppCloudAdapter(business_id="tenant_cfg")

    # Missing all
    r1 = adapter.validate_configuration({})
    assert r1.passed is False

    # Missing WABA ID
    r2 = adapter.validate_configuration({"phone_number_id": "100609349424111"})
    assert r2.passed is False

    # Missing token
    r3 = adapter.validate_configuration({"phone_number_id": "100609349424111", "waba_id": "1054344322"})
    assert r3.passed is False

    # Valid
    r4 = adapter.validate_configuration({
        "phone_number_id": "100609349424111",
        "waba_id": "1054344322",
        "access_token": "EAA_VALID_TOKEN",
    })
    assert r4.passed is True


@pytest.mark.parametrize(
    "raw_input, expected_clean",
    [
        ("+1 (415) 555-2671", "14155552671"),
        ("+44 7911 123456", "447911123456"),
        ("1-650-555-0199", "16505550199"),
        ("  +91 98765 43210  ", "919876543210"),
    ],
)
def test_whatsapp_phone_number_normalization(raw_input, expected_clean):
    """Verify recipient numbers are normalized to country code + digits without '+'."""
    assert WhatsAppCloudAdapter.clean_phone(raw_input) == expected_clean


# ==============================================================================
# 3. Safe Diagnostics: Never send real messages without authorization
# ==============================================================================

@patch("urllib.request.urlopen")
def test_whatsapp_safe_connection_probe_queries_phone_number(mock_urlopen):
    """
    CRITICAL: Never send a real customer message as a connection test without explicit authorization!
    Verify test_connection queries GET /{phone_number_id} to inspect registration safely.
    """
    phone_details_payload = {
        "verified_name": "Apex Dental Clinic",
        "code_verification_status": "VERIFIED",
        "display_phone_number": "+1 555-0199",
        "quality_rating": "GREEN",
        "id": "100609349424111",
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(phone_details_payload).encode("utf-8"))

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_probe",
        configuration={"phone_number_id": "100609349424111", "waba_id": "1054344322"},
        credentials={"access_token": "live_system_user_token"},
    )

    result = adapter.test_connection()
    assert result.passed is True
    assert "Apex Dental Clinic" in result.details
    assert "GREEN" in result.details

    # Assert urlopen called GET /{phone_number_id}, NOT POST /messages!
    req = mock_urlopen.call_args[0][0]
    assert req.method == "GET"
    assert "/messages" not in req.full_url
    assert "100609349424111" in req.full_url


def test_whatsapp_test_connection_mock_mode():
    """Verify test_connection passes in mock/sandbox mode."""
    adapter = WhatsAppCloudAdapter(
        business_id="tenant_mock",
        configuration={"phone_number_id": "100609349424111", "waba_id": "1054344322"},
        credentials={"access_token": "mock_token"},
    )
    result = adapter.test_connection()
    assert result.passed is True
    assert "Mock/Sandbox Mode" in result.details


# ==============================================================================
# 4. 24-Hour Customer Service Window (CSW) Policy Enforcement
# ==============================================================================

def test_whatsapp_freeform_text_blocked_outside_customer_service_window():
    """
    Policy Enforcement: Freeform text messages are strictly prohibited outside the
    24-hour Customer Service Window (opened only by inbound customer messages).
    """
    adapter = WhatsAppCloudAdapter(
        business_id="tenant_window",
        configuration={"phone_number_id": "100609349424111", "enforce_24h_window": True},
        credentials={"access_token": "live_token"},
    )
    recipient = "14155552671"

    # Window is closed (no inbound message received)
    assert adapter.is_customer_service_window_open(recipient) is False

    with pytest.raises(WhatsAppIntegrationException) as exc_info:
        adapter.send_text_message(recipient, "Hello, can we confirm your visit?")

    assert exc_info.value.error.code == "CUSTOMER_SERVICE_WINDOW_CLOSED"
    assert exc_info.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION
    assert "24-hour Customer Service Window is closed" in exc_info.value.error.message


@patch("urllib.request.urlopen")
def test_whatsapp_freeform_text_allowed_inside_customer_service_window(mock_urlopen):
    """Verify freeform text message succeeds once an inbound message has opened the 24h window."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "messaging_product": "whatsapp",
            "contacts": [{"input": "14155552671", "wa_id": "14155552671"}],
            "messages": [{"id": "wamid.HBgLMTRxNTU1MjY3MRA"}]
        }).encode("utf-8")
    )

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_window",
        configuration={"phone_number_id": "100609349424111", "enforce_24h_window": True},
        credentials={"access_token": "live_token"},
    )
    recipient = "14155552671"

    # Customer sends inbound message -> opens window
    adapter.update_customer_service_window(recipient)
    assert adapter.is_customer_service_window_open(recipient) is True

    # Sending freeform text now succeeds!
    res = adapter.send_text_message(recipient, "Thank you for contacting us! How can we assist you?")
    assert res["message_id"] == "wamid.HBgLMTRxNTU1MjY3MRA"
    assert res["outcome"] == ExecutionOutcome.REQUEST_ACCEPTED


def test_whatsapp_customer_service_window_expires_after_24_hours():
    """Verify the Customer Service Window closes when more than 24 hours have elapsed."""
    adapter = WhatsAppCloudAdapter(business_id="tenant_window")
    recipient = "14155552671"

    # Simulate message received 25 hours ago
    past_timestamp = time.time() - (CUSTOMER_SERVICE_WINDOW_SECONDS + 3600)
    adapter.update_customer_service_window(recipient, timestamp=past_timestamp)

    assert adapter.is_customer_service_window_open(recipient) is False


# ==============================================================================
# 5. Pre-Approved Meta Template Messages & Opt-In Verification
# ==============================================================================

@patch("urllib.request.urlopen")
def test_whatsapp_template_message_allowed_outside_24h_window(mock_urlopen):
    """
    Template messages are permitted outside the 24-hour window for business-initiated
    notifications (e.g. appointment reminders).
    """
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.HBgLTEMPLATE_MSG_ID"}]
        }).encode("utf-8")
    )

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_template",
        configuration={"phone_number_id": "100609349424111", "enforce_24h_window": True},
        credentials={"access_token": "live_token"},
    )
    recipient = "14155552671"

    # Window is closed
    assert adapter.is_customer_service_window_open(recipient) is False

    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Alex Mercer"},
                {"type": "text", "text": "Tuesday at 2:00 PM"},
            ],
        }
    ]

    res = adapter.send_template_message(
        to=recipient,
        template_name="appointment_reminder",
        language_code="en_US",
        components=components,
    )

    assert res["message_id"] == "wamid.HBgLTEMPLATE_MSG_ID"
    assert res["status"] == "accepted"
    assert res["type"] == "template"

    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "appointment_reminder"
    assert payload["template"]["language"]["code"] == "en_US"


def test_whatsapp_template_user_consent_opt_in_required():
    """Verify template message is blocked if customer has explicitly opted out."""
    adapter = WhatsAppCloudAdapter(
        business_id="tenant_opt_in",
        configuration={"require_opt_in": True},
        credentials={"access_token": "live_token"},
    )
    recipient = "14155552671"

    # Explicitly mark opted out
    adapter.record_user_opt_in(recipient, opted_in=False)

    with pytest.raises(WhatsAppIntegrationException) as exc_info:
        adapter.send_template_message(to=recipient, template_name="promo_update")

    assert exc_info.value.error.code == "USER_CONSENT_REQUIRED"
    assert exc_info.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION


@patch("urllib.request.urlopen")
def test_whatsapp_discover_templates(mock_urlopen):
    """Verify discover_resources retrieves approved templates from WABA."""
    templates_payload = {
        "data": [
            {"name": "appointment_reminder", "status": "APPROVED", "category": "UTILITY", "language": "en_US"},
            {"name": "billing_update", "status": "APPROVED", "category": "UTILITY", "language": "en_US"},
            {"name": "promo_spring", "status": "REJECTED", "category": "MARKETING", "language": "en_US"},
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(templates_payload).encode("utf-8"))

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_templates",
        configuration={"waba_id": "1054344322"},
        credentials={"access_token": "live_token"},
    )

    resources = adapter.discover_resources("templates")
    assert len(resources) == 3
    t_names = [r.resource_id for r in resources]
    assert "appointment_reminder" in t_names
    assert resources[0].metadata["status"] == "APPROVED"
    assert resources[2].metadata["status"] == "REJECTED"


# ==============================================================================
# 6. Truthful Envelopes: API Acceptance vs Actual Device Delivery
# ==============================================================================

@patch("urllib.request.urlopen")
def test_whatsapp_truthful_outcome_distinguishes_acceptance_from_delivery(mock_urlopen):
    """
    CRITICAL: Outbound send returns REQUEST_ACCEPTED and is_delivered=False.
    API acceptance by Meta does not mean final carrier/handset delivery.
    """
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.HBgLACCEPTANCE_ONLY"}]
        }).encode("utf-8")
    )

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_truthful",
        configuration={"phone_number_id": "100609349424111", "default_template_name": "general_notice"},
        credentials={"access_token": "live_token"},
    )
    ctx = ExecutionContext(tenant_id="tenant_truthful", business_id="tenant_truthful")

    result = adapter.execute(
        CapabilityType.SEND_MESSAGE,
        {"recipient_phone": "+1 (415) 555-2671", "template_name": "general_notice"},
        ctx,
    )

    assert result.success is True
    assert result.outcome == ExecutionOutcome.REQUEST_ACCEPTED
    assert result.data["is_delivered"] is False
    assert result.data["message_id"] == "wamid.HBgLACCEPTANCE_ONLY"


# ==============================================================================
# 7. Webhook Challenge Handshake & HMAC-SHA256 Signature Verification
# ==============================================================================

def test_whatsapp_webhook_challenge_handshake():
    """Verify Meta's GET webhook verification handshake."""
    adapter = WhatsAppCloudAdapter(
        business_id="tenant_wh",
        configuration={"webhook_verify_token": "my_secret_verify_token_123"},
    )

    # Valid token and subscribe mode -> returns challenge string
    challenge_val = "1158201444"
    res = adapter.verify_webhook_challenge(
        mode="subscribe",
        verify_token="my_secret_verify_token_123",
        challenge=challenge_val,
    )
    assert res == challenge_val

    # Token mismatch -> returns None
    assert adapter.verify_webhook_challenge("subscribe", "wrong_token", challenge_val) is None

    # Invalid mode -> returns None
    assert adapter.verify_webhook_challenge("unsubscribe", "my_secret_verify_token_123", challenge_val) is None


def test_whatsapp_webhook_signature_verification():
    """Verify HMAC-SHA256 signature verification (X-Hub-Signature-256)."""
    app_secret = "meta_app_secret_key_456"
    raw_body = b'{"entry":[{"id":"1054344322","changes":[]}]}'

    computed_sig = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_sig",
        configuration={"app_secret": app_secret},
    )

    # Valid signature
    assert adapter.verify_webhook_signature(raw_body, {"X-Hub-Signature-256": f"sha256={computed_sig}"}) is True

    # Invalid / forged signature
    assert adapter.verify_webhook_signature(raw_body, {"X-Hub-Signature-256": "sha256=forged_signature_val"}) is False

    # Missing header
    assert adapter.verify_webhook_signature(raw_body, {}) is False


# ==============================================================================
# 8. Inbound Messages, Customer Service Window Opening, & Deduplication
# ==============================================================================

def test_whatsapp_handle_webhook_inbound_message_opens_csw():
    """Verify receiving an inbound message webhook extracts text and opens the 24h CSW."""
    app_secret = "wh_secret_key"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1054344322",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "14155552671",
                                    "id": "wamid.HBgLINBOUND_MSG_1",
                                    "timestamp": str(int(time.time())),
                                    "text": {"body": "Hi, I have a question about my appointment."},
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    adapter = WhatsAppCloudAdapter(
        business_id="tenant_inbound",
        configuration={"app_secret": app_secret},
    )

    # Initially closed
    assert adapter.is_customer_service_window_open("14155552671") is False

    req = WebhookRequest(
        provider_id="whatsapp",
        headers={"X-Hub-Signature-256": f"sha256={sig}"},
        raw_body=raw_body,
        parsed_json=payload,
    )

    res = adapter.handle_webhook(req)
    assert res.success is True
    assert len(res.data["events"]) == 1
    event = res.data["events"][0]
    assert event["event_type"] == "inbound_message"
    assert event["body"] == "Hi, I have a question about my appointment."
    assert event["from"] == "14155552671"

    # Now the 24-hour Customer Service Window is OPEN!
    assert adapter.is_customer_service_window_open("14155552671") is True


def test_whatsapp_webhook_event_deduplication():
    """Verify duplicate webhooks delivering the same message ID are deduplicated."""
    app_secret = "wh_secret_key"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "14155552671",
                                    "id": "wamid.DUPLICATE_TEST_ID",
                                    "timestamp": str(int(time.time())),
                                    "text": {"body": "First delivery"},
                                    "type": "text",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    adapter = WhatsAppCloudAdapter(business_id="tenant_dedup", configuration={"app_secret": app_secret})
    req = WebhookRequest(
        provider_id="whatsapp",
        headers={"X-Hub-Signature-256": f"sha256={sig}"},
        raw_body=raw_body,
        parsed_json=payload,
    )

    # First delivery: processed
    res1 = adapter.handle_webhook(req)
    assert len(res1.data["events"]) == 1

    # Second delivery with identical wamid: deduplicated (0 new events)
    res2 = adapter.handle_webhook(req)
    assert len(res2.data["events"]) == 0


# ==============================================================================
# 9. Delivery Status Updates (Sent, Delivered, Read, Failed)
# ==============================================================================

def test_whatsapp_handle_webhook_delivery_statuses():
    """Verify delivery receipt webhooks are parsed into normalized status events."""
    app_secret = "wh_secret_key"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.HBgLSTATUS_TEST_1",
                                    "status": "delivered",
                                    "timestamp": str(int(time.time())),
                                    "recipient_id": "14155552671",
                                },
                                {
                                    "id": "wamid.HBgLSTATUS_TEST_2",
                                    "status": "read",
                                    "timestamp": str(int(time.time())),
                                    "recipient_id": "14155552671",
                                },
                                {
                                    "id": "wamid.HBgLSTATUS_TEST_3",
                                    "status": "failed",
                                    "timestamp": str(int(time.time())),
                                    "recipient_id": "14155552671",
                                    "errors": [
                                        {"code": 131047, "title": "Re-engagement message"}
                                    ],
                                },
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    adapter = WhatsAppCloudAdapter(business_id="tenant_status", configuration={"app_secret": app_secret})
    req = WebhookRequest(
        provider_id="whatsapp",
        headers={"X-Hub-Signature-256": f"sha256={sig}"},
        raw_body=raw_body,
        parsed_json=payload,
    )

    res = adapter.handle_webhook(req)
    assert res.success is True
    events = res.data["events"]
    assert len(events) == 3

    assert events[0]["event_type"] == "message_delivered"
    assert events[1]["event_type"] == "message_read"
    assert events[2]["event_type"] == "message_failed"
    assert events[2]["errors"][0]["code"] == 131047


# ==============================================================================
# 10. Comprehensive Error Normalization
# ==============================================================================

@pytest.mark.parametrize(
    "status_code, error_code, msg, expected_category, expected_retryable",
    [
        (400, 131047, "Message failed to send because more than 24 hours have passed since the customer last sent a message.", ErrorCategory.BUSINESS_RULE_VIOLATION, False),
        (429, 130429, "Rate limit hit for sending messages.", ErrorCategory.RATE_LIMITED, True),
        (401, 190, "Invalid OAuth access token - Cannot parse access token.", ErrorCategory.AUTHENTICATION_FAILED, False),
        (404, 132000, "Template does not exist.", ErrorCategory.RESOURCE_NOT_FOUND, False),
        (400, 131026, "Message undeliverable to this destination.", ErrorCategory.INVALID_REQUEST, False),
        (500, 2, "An unexpected server error occurred at Meta.", ErrorCategory.PROVIDER_UNAVAILABLE, True),
    ],
)
def test_whatsapp_error_normalization(status_code, error_code, msg, expected_category, expected_retryable):
    """Verify official Meta WhatsApp error codes map to standard ErrorCategory."""
    adapter = WhatsAppCloudAdapter(business_id="tenant_err")
    http_err = make_mock_graph_error(status_code, error_code, msg)

    norm_err = adapter._normalize_whatsapp_error(http_err)
    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ==============================================================================
# 11. Multi-Tenant Isolation
# ==============================================================================

def test_whatsapp_multi_tenant_isolation():
    """Verify distinct tenant adapter instances maintain separate configurations, tokens, and windows."""
    tenant_a = WhatsAppCloudAdapter(
        business_id="tenant_a",
        configuration={"phone_number_id": "100609349424111", "waba_id": "WABA_111"},
        credentials={"access_token": "token_tenant_a"},
    )
    tenant_b = WhatsAppCloudAdapter(
        business_id="tenant_b",
        configuration={"phone_number_id": "100609349424222", "waba_id": "WABA_222"},
        credentials={"access_token": "token_tenant_b"},
    )

    assert tenant_a._get_phone_number_id() == "100609349424111"
    assert tenant_b._get_phone_number_id() == "100609349424222"
    assert tenant_a._get_waba_id() == "WABA_111"
    assert tenant_b._get_waba_id() == "WABA_222"
    assert tenant_a._get_access_token() != tenant_b._get_access_token()

    # Customer service window for phone X in Tenant A does not bleed into Tenant B
    shared_phone = "14155552671"
    tenant_a.update_customer_service_window(shared_phone)

    assert tenant_a.is_customer_service_window_open(shared_phone) is True
    assert tenant_b.is_customer_service_window_open(shared_phone) is False


# ==============================================================================
# 12. Capability Execution via execute()
# ==============================================================================

def test_whatsapp_execute_send_message_in_mock_mode():
    """Verify CapabilityType.SEND_MESSAGE returns truthful REQUEST_ACCEPTED outcome."""
    adapter = WhatsAppCloudAdapter(
        business_id="tenant_exec",
        configuration={"default_template_name": "appointment_reminder"},
        credentials={"access_token": "mock_token"},
    )
    ctx = ExecutionContext(tenant_id="tenant_exec", business_id="tenant_exec", conversation_id="conv_wa_1")

    result = adapter.execute(
        CapabilityType.SEND_MESSAGE,
        {"recipient_phone": "+1 (415) 555-2671", "template_name": "appointment_reminder"},
        ctx,
    )

    assert result.success is True
    assert result.outcome == ExecutionOutcome.REQUEST_ACCEPTED
    assert result.authoritative_source == AuthoritativeSource.COMMUNICATION_SERVICE.value
    assert result.data["is_delivered"] is False
    assert result.data["recipient"] == "14155552671"
    assert result.data["message_id"].startswith("wamid.")
