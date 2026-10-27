"""
Unit and integration tests for the official Razorpay Payments Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.PAYMENT_GATEWAY, IntegrationCategory.PAYMENTS)
- Registry lookup and aliases ('razorpay', 'razorpay_payments')
- Test vs. Live environment detection, configuration validation, and environment isolation
- Safe connection diagnostics: test_connection() probes GET /payments?count=1 without creating charges or orders
- Server-side amount and currency validation (minor units, minimums, 3-letter ISO currencies)
- Authoritative order binding & anti-tampering (rejecting agent attempts to invent prices or alter totals)
- Order creation via Orders API (POST /orders) with receipt and tenant binding
- Payment Link creation via Payment Links API (POST /payment_links) with customer details and short URL
- Authoritative payment status retrieval via Payments API (GET /payments/{id})
- Truthful outcome envelope: CREATE_PAYMENT_REQUEST returns OPERATION_PENDING; never claims paid until authoritative state confirms it
- Cryptographic HMAC-SHA256 webhook signature verification via X-Razorpay-Signature
- Standard checkout callback signature verification (order_id|payment_id signed with key_secret)
- Webhook replay deduplication and authoritative is_paid verification
- Idempotency cache preventing duplicate order or payment link generation
- PCI-DSS compliance: raw card numbers, CVVs, or PINs immediately rejected with CARD_DATA_FORBIDDEN
- Endpoint-specific error normalization (HTTP 400, 401, 403, 404, 429, 500)
- Multi-tenant credential and cache isolation
- Execution in mock mode
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import base64
import hmac
import hashlib
import urllib.error

from backend.integrations.adapters.razorpay_adapter import (
    RazorpayAdapter,
    RazorpayIntegrationException,
    CURRENCY_MINIMUM_MINOR_UNITS,
)
from backend.capabilities.models import AuthoritativeSource
from backend.integrations.models import (
    ProviderManifest,
    CapabilityType,
    AuthMethod,
    IntegrationCategory,
    ExecutionContext,
    ExecutionOutcome,
    ErrorCategory,
    IntegrationError,
    WebhookRequest,
)
from backend.integrations.registry import get_integration_registry


# ============================================================================
# 1. Manifest & Registry Verification
# ============================================================================

def test_razorpay_manifest_and_authoritative_source():
    """Verify Razorpay adapter declares authoritative source and capability manifest."""
    adapter = RazorpayAdapter(
        business_id="biz_rzp_alpha",
        credentials={"key_id": "rzp_test_dummy123", "key_secret": "sec_test_dummy"},
    )
    assert adapter.authoritative_source == AuthoritativeSource.PAYMENT_GATEWAY

    manifest = adapter.get_manifest()
    assert manifest.provider_id == "razorpay"
    assert manifest.category == IntegrationCategory.PAYMENTS
    assert manifest.auth_method == AuthMethod.API_KEY
    assert CapabilityType.CREATE_PAYMENT_REQUEST in manifest.supported_capabilities
    assert CapabilityType.GET_PAYMENT_STATUS in manifest.supported_capabilities

    # Required setup fields
    keys = {f.key: f for f in manifest.required_setup_fields}
    assert "key_id" in keys
    assert "key_secret" in keys
    assert keys["key_secret"].secret is True

    # Webhook signature method
    assert manifest.webhook_signature_method == "HMAC_SHA256"


def test_razorpay_registered_in_registry():
    """Verify Razorpay is registered in IntegrationRegistry with aliases."""
    registry = get_integration_registry()
    manifest_rzp = registry.get_manifest("razorpay")
    assert manifest_rzp.provider_id == "razorpay"

    manifest_alias = registry.get_manifest("razorpay_payments")
    assert manifest_alias.provider_id == "razorpay"

    cls_primary = registry.get_adapter_class("razorpay")
    cls_alias = registry.get_adapter_class("razorpay_payments")
    assert cls_primary is RazorpayAdapter
    assert cls_alias is RazorpayAdapter


# ============================================================================
# 2. Test vs. Live Environment Detection & Isolation
# ============================================================================

@pytest.mark.parametrize(
    "key_id, declared_env, expected_env, should_pass",
    [
        ("rzp_test_1DP5mmOlF5G5ag", "auto", "test", True),
        ("rzp_live_9QP2mmOlF5G5zz", "auto", "live", True),
        ("rzp_test_1DP5mmOlF5G5ag", "test", "test", True),
        ("rzp_live_9QP2mmOlF5G5zz", "live", "live", True),
        ("rzp_test_1DP5mmOlF5G5ag", "live", "test", False),  # Test key in live declared env
        ("rzp_live_9QP2mmOlF5G5zz", "test", "live", False),  # Live key in test declared env
        ("invalid_prefix_key", "auto", "test", False),       # Invalid prefix
        ("", "auto", "test", False),                         # Empty key
    ],
)
def test_razorpay_environment_detection_and_validation(key_id, declared_env, expected_env, should_pass):
    """Verify strict test vs. live key validation and environment detection."""
    adapter = RazorpayAdapter(
        business_id="biz_env",
        configuration={"environment": declared_env},
        credentials={"key_id": key_id, "key_secret": "dummy_secret"} if key_id else {},
    )

    check = adapter.validate_configuration({"key_id": key_id, "environment": declared_env})
    assert check.passed is should_pass

    if key_id.startswith("rzp_"):
        assert adapter.get_environment() == expected_env


# ============================================================================
# 3. Safe Connection Diagnostics (Zero Dummy Charges)
# ============================================================================

def test_razorpay_safe_connection_probe_never_creates_dummy_charges():
    """Verify test_connection probes GET /payments?count=1 and never creates charges/orders."""
    adapter = RazorpayAdapter(
        business_id="biz_safe_probe",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {"entity": "collection", "count": 0, "items": []}

        res = adapter.test_connection()
        assert res.passed is True
        assert "TEST mode" in res.details
        # Strictly assert only a read-only GET call was issued
        mock_req.assert_called_once_with("GET", "/payments?count=1")


def test_razorpay_test_connection_mock_mode():
    """Verify test_connection passes in simulated/mock mode without network calls."""
    adapter = RazorpayAdapter(
        business_id="biz_mock_probe",
        configuration={"is_mock": True},
    )
    res = adapter.test_connection()
    assert res.passed is True
    assert "Simulated" in res.name


# ============================================================================
# 4. Server-Side Amount and Currency Validation
# ============================================================================

def test_razorpay_amount_validation_negative_or_zero_rejected():
    """Verify zero or negative payment amount is rejected with INVALID_REQUEST."""
    adapter = RazorpayAdapter(
        business_id="biz_val",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    with pytest.raises(RazorpayIntegrationException) as exc_info:
        adapter.validate_payment_amount(0, "INR")
    assert exc_info.value.error.code == "INVALID_AMOUNT"

    with pytest.raises(RazorpayIntegrationException) as exc_info2:
        adapter.validate_payment_amount(-500, "INR")
    assert exc_info2.value.error.code == "INVALID_AMOUNT"


def test_razorpay_amount_validation_below_minimum_rejected():
    """Verify payment amount below Razorpay minimum (e.g. < 100 paise for INR) is rejected."""
    adapter = RazorpayAdapter(
        business_id="biz_val",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    # 50 paise is below 100 paise minimum
    with pytest.raises(RazorpayIntegrationException) as exc_info:
        adapter.validate_payment_amount(50, "INR")
    assert exc_info.value.error.code == "AMOUNT_BELOW_MINIMUM"
    assert exc_info.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION


def test_razorpay_currency_validation_invalid_code_rejected():
    """Verify invalid currency code is rejected."""
    adapter = RazorpayAdapter(
        business_id="biz_val",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    with pytest.raises(RazorpayIntegrationException) as exc_info:
        adapter.validate_payment_amount(5000, "INVALID_CURRENCY")
    assert exc_info.value.error.code == "INVALID_CURRENCY"


def test_razorpay_amount_validation_valid():
    """Verify valid amounts and standard currencies normalize correctly."""
    adapter = RazorpayAdapter(
        business_id="biz_val",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    amt, curr = adapter.validate_payment_amount(50000, "inr")
    assert amt == 50000
    assert curr == "INR"

    amt_usd, curr_usd = adapter.validate_payment_amount(2500, "usd")
    assert amt_usd == 2500
    assert curr_usd == "USD"


# ============================================================================
# 5. Authoritative Order Binding & Anti-Tampering Protection
# ============================================================================

def test_razorpay_anti_tampering_amount_mismatch_rejected():
    """Verify an agent cannot modify authoritative order totals or invent prices."""
    adapter = RazorpayAdapter(
        business_id="biz_tamper",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    # Authoritative invoice is ₹500 (50,000 paise). Agent attempts to bill ₹300 (30,000 paise).
    with pytest.raises(RazorpayIntegrationException) as exc_info:
        adapter.create_payment_link(
            amount_minor=30000,
            currency="INR",
            reference_id="inv_clinic_8899",
            authoritative_amount_minor=50000,
        )
    assert exc_info.value.error.code == "AMOUNT_MISMATCH"
    assert exc_info.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION


def test_razorpay_transaction_binding_missing_receipt_rejected():
    """Verify payment requests require a valid business transaction ID / receipt."""
    adapter = RazorpayAdapter(
        business_id="biz_bind",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    with pytest.raises(RazorpayIntegrationException) as exc_info:
        adapter.bind_and_verify_transaction("", 5000)
    assert exc_info.value.error.code == "MISSING_TRANSACTION_BINDING"


# ============================================================================
# 6. Product 1: Orders API (POST /orders, GET /orders/{id})
# ============================================================================

def test_razorpay_create_order_success_and_normalization():
    """Verify creating an order via Orders API binds tenant notes and normalizes fields."""
    adapter = RazorpayAdapter(
        business_id="biz_order",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    mock_resp = {
        "id": "order_EKwxwAgItmmXdp",
        "entity": "order",
        "amount": 50000,
        "amount_paid": 0,
        "amount_due": 50000,
        "currency": "INR",
        "receipt": "rcpt_dining_404",
        "status": "created",
        "attempts": 0,
        "notes": {"tenant_id": "biz_order", "table_id": "table_7"},
        "created_at": 1600000000,
    }

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = mock_resp

        order = adapter.create_order(
            amount_minor=50000,
            currency="INR",
            receipt="rcpt_dining_404",
            notes={"table_id": "table_7"},
        )

        mock_req.assert_called_once()
        assert order["order_id"] == "order_EKwxwAgItmmXdp"
        assert order["amount"] == 50000
        assert order["currency"] == "INR"
        assert order["status"] == "created"
        assert order["normalized_status"] == "pending"
        assert order["is_paid"] is False
        assert order["environment"] == "test"


def test_razorpay_get_order():
    """Verify retrieving an order by ID."""
    adapter = RazorpayAdapter(
        business_id="biz_order",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    mock_resp = {
        "id": "order_EKwxwAgItmmXdp",
        "entity": "order",
        "amount": 50000,
        "amount_paid": 50000,
        "amount_due": 0,
        "currency": "INR",
        "receipt": "rcpt_dining_404",
        "status": "paid",
        "attempts": 1,
        "created_at": 1600000000,
    }

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = mock_resp
        order = adapter.get_order("order_EKwxwAgItmmXdp")
        assert order["is_paid"] is True
        assert order["normalized_status"] == "succeeded"


# ============================================================================
# 7. Product 2: Payment Links API (POST /payment_links, GET /payment_links/{id})
# ============================================================================

def test_razorpay_create_payment_link_success():
    """Verify creating a hosted payment link for out-of-band conversational collection."""
    adapter = RazorpayAdapter(
        business_id="biz_plink",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    mock_resp = {
        "id": "plink_G5zzAgItmmXdp",
        "entity": "payment_link",
        "amount": 25000,
        "amount_paid": 0,
        "currency": "INR",
        "reference_id": "ref_consult_101",
        "description": "Telehealth Consultation Copay",
        "short_url": "https://rzp.io/i/Xyz123",
        "status": "created",
        "customer": {
            "name": "Jane Smith",
            "contact": "+919876543210",
            "email": "janesmith@example.com",
        },
        "created_at": 1600000000,
    }

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = mock_resp

        link = adapter.create_payment_link(
            amount_minor=25000,
            currency="INR",
            reference_id="ref_consult_101",
            description="Telehealth Consultation Copay",
            customer_name="Jane Smith",
            customer_phone="+919876543210",
            customer_email="janesmith@example.com",
        )

        mock_req.assert_called_once()
        assert link["payment_link_id"] == "plink_G5zzAgItmmXdp"
        assert link["short_url"] == "https://rzp.io/i/Xyz123"
        assert link["normalized_status"] == "pending"
        assert link["is_paid"] is False


# ============================================================================
# 8. Product 3: Payments API & Authoritative Status Verification
# ============================================================================

@pytest.mark.parametrize(
    "raw_status, captured_val, expected_norm_status, expected_is_paid",
    [
        ("created", False, "pending", False),
        ("authorized", False, "authorized", False),  # Two-step auth, not yet settled
        ("captured", True, "succeeded", True),       # Authoritative settlement
        ("failed", False, "failed", False),
        ("refunded", True, "refunded", False),
    ],
)
def test_razorpay_authoritative_payment_status(raw_status, captured_val, expected_norm_status, expected_is_paid):
    """Verify authoritative payment status mapping and that paid status requires captured state."""
    adapter = RazorpayAdapter(
        business_id="biz_pay_status",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    mock_resp = {
        "id": "pay_FNr8FzI7853684",
        "entity": "payment",
        "amount": 50000,
        "currency": "INR",
        "status": raw_status,
        "order_id": "order_EKwxwAgItmmXdp",
        "captured": captured_val,
        "method": "upi",
        "email": "customer@example.com",
        "contact": "+919876543210",
        "created_at": 1600000000,
    }

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = mock_resp
        payment = adapter.get_payment("pay_FNr8FzI7853684")

        assert payment["status"] == raw_status
        assert payment["normalized_status"] == expected_norm_status
        assert payment["is_paid"] is expected_is_paid


def test_razorpay_capture_payment_authorized():
    """Verify capturing an authorized payment."""
    adapter = RazorpayAdapter(
        business_id="biz_capture",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    mock_resp = {
        "id": "pay_FNr8FzI7853684",
        "entity": "payment",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
        "captured": True,
    }

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = mock_resp
        res = adapter.capture_payment("pay_FNr8FzI7853684", 50000, "INR")
        assert res["status"] == "captured"
        assert res["is_paid"] is True


# ============================================================================
# 9. Truthful Outcome Envelopes: Creating Request Returns OPERATION_PENDING
# ============================================================================

def test_razorpay_truthful_outcome_creation_is_pending_never_paid():
    """
    CRITICAL ARCHITECTURAL GUARANTEE:
    Generating a payment link or order returns OPERATION_PENDING.
    The agent must NEVER represent a payment request as completed/paid at generation time.
    """
    adapter = RazorpayAdapter(
        business_id="biz_truth",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = {
            "id": "plink_998877",
            "amount": 150000,
            "currency": "INR",
            "status": "created",
            "short_url": "https://rzp.io/i/Test99",
            "reference_id": "ref_tx_9988",
        }

        ctx = ExecutionContext(tenant_id="biz_truth", correlation_id="corr_99")
        result = adapter.execute(
            CapabilityType.CREATE_PAYMENT_REQUEST,
            {
                "amount_cents": 150000,
                "currency": "INR",
                "description": "Catering Deposit",
                "reference_id": "ref_tx_9988",
            },
            context=ctx,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_PENDING
        assert result.data["is_paid"] is False
        assert "pending customer payment" in result.safe_message.lower()


# ============================================================================
# 10. Cryptographic Webhook & Checkout Signature Verification
# ============================================================================

def test_razorpay_webhook_signature_verification_valid():
    """Verify valid HMAC-SHA256 signature in X-Razorpay-Signature header."""
    adapter = RazorpayAdapter(
        business_id="biz_wh",
        configuration={"webhook_secret": "my_super_secret_webhook_token_77"},
    )

    raw_body = b'{"entity":"event","event":"payment.captured"}'
    expected_sig = hmac.new(
        b"my_super_secret_webhook_token_77",
        raw_body,
        hashlib.sha256
    ).hexdigest()

    assert adapter.verify_webhook_signature(raw_body, expected_sig) is True


def test_razorpay_webhook_signature_verification_tampered_rejected():
    """Verify tampered payload or invalid signature is rejected."""
    adapter = RazorpayAdapter(
        business_id="biz_wh",
        configuration={"webhook_secret": "my_super_secret_webhook_token_77"},
    )

    raw_body = b'{"entity":"event","event":"payment.captured"}'
    wrong_sig = "deadbeef1234567890abcdef"

    assert adapter.verify_webhook_signature(raw_body, wrong_sig) is False


def test_razorpay_checkout_callback_signature_verification():
    """Verify Razorpay standard checkout client callback signature (order_id|payment_id)."""
    adapter = RazorpayAdapter(
        business_id="biz_checkout",
        credentials={"key_secret": "sec_client_secret_88"},
    )

    order_id = "order_EKwxwAgItmmXdp"
    payment_id = "pay_FNr8FzI7853684"
    valid_sig = hmac.new(
        b"sec_client_secret_88",
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    assert adapter.verify_checkout_signature(order_id, payment_id, valid_sig) is True
    # Tampered payment ID should fail
    assert adapter.verify_checkout_signature(order_id, "pay_TAMPERED", valid_sig) is False


def test_razorpay_webhook_replay_deduplication():
    """Verify incoming webhook events are deduplicated to protect against replays."""
    adapter = RazorpayAdapter(
        business_id="biz_wh_dedup",
        configuration={"webhook_secret": "whsec_test"},
    )

    raw_body = json.dumps({
        "id": "evt_duplicate_test_123",
        "entity": "event",
        "event": "payment.captured",
        "payload": {
            "payment": {"entity": {"id": "pay_11", "status": "captured"}}
        }
    }).encode("utf-8")

    sig = hmac.new(b"whsec_test", raw_body, hashlib.sha256).hexdigest()
    req = WebhookRequest(
        provider_id="razorpay",
        headers={"x-razorpay-signature": sig, "x-razorpay-event-id": "evt_duplicate_test_123"},
        raw_body=raw_body,
        parsed_json=json.loads(raw_body),
    )

    # First delivery: processed
    res1 = adapter.handle_webhook(req)
    assert res1.success is True
    assert res1.processed is True
    assert res1.is_duplicate is False

    # Second delivery: duplicate ignored
    res2 = adapter.handle_webhook(req)
    assert res2.success is True
    assert res2.processed is False
    assert res2.is_duplicate is True


# ============================================================================
# 11. Idempotency Cache Suppresses Duplicate Creation
# ============================================================================

def test_razorpay_duplicate_creation_suppressed_by_idempotency_cache():
    """Verify repeated create_payment_link calls with same receipt return cached entry."""
    adapter = RazorpayAdapter(
        business_id="biz_idem",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    mock_resp = {
        "id": "plink_first_call",
        "amount": 50000,
        "currency": "INR",
        "reference_id": "ref_idem_777",
        "status": "created",
        "short_url": "https://rzp.io/i/first",
    }

    with patch.object(adapter, "_make_request") as mock_req:
        mock_req.return_value = mock_resp

        # Call 1: makes API request
        l1 = adapter.create_payment_link(
            amount_minor=50000,
            currency="INR",
            reference_id="ref_idem_777",
        )
        assert mock_req.call_count == 1
        assert l1["payment_link_id"] == "plink_first_call"

        # Call 2: served from cache
        l2 = adapter.create_payment_link(
            amount_minor=50000,
            currency="INR",
            reference_id="ref_idem_777",
        )
        assert mock_req.call_count == 1  # No second API call!
        assert l2["payment_link_id"] == "plink_first_call"
        assert l2["is_duplicate"] is True


# ============================================================================
# 12. PCI-DSS Hygiene: Raw Card Data Scrubbed & Rejected
# ============================================================================

def test_razorpay_pci_dss_hygiene_card_data_forbidden():
    """Verify that any raw card data in input parameters is immediately blocked."""
    adapter = RazorpayAdapter(
        business_id="biz_pci",
        credentials={"key_id": "rzp_test_123", "key_secret": "sec_456"},
    )

    # Passing CVV
    with pytest.raises(RazorpayIntegrationException) as exc_info:
        adapter.execute(
            CapabilityType.CREATE_PAYMENT_REQUEST,
            {"amount_cents": 5000, "cvv": "123"},
            ExecutionContext(tenant_id="biz_pci"),
        )
    assert exc_info.value.error.code == "CARD_DATA_FORBIDDEN"
    assert exc_info.value.error.category == ErrorCategory.PERMISSION_DENIED

    # Passing raw card number
    with pytest.raises(RazorpayIntegrationException) as exc_info2:
        adapter.execute(
            CapabilityType.CREATE_PAYMENT_REQUEST,
            {"amount_cents": 5000, "card_number": "4111111111111111"},
            ExecutionContext(tenant_id="biz_pci"),
        )
    assert exc_info2.value.error.code == "CARD_DATA_FORBIDDEN"


# ============================================================================
# 13. Error Normalization
# ============================================================================

@pytest.mark.parametrize(
    "status_code, response_body, expected_category, expected_retryable",
    [
        (400, '{"error": {"code": "BAD_REQUEST_ERROR", "description": "Order amount exceeds maximum limit"}}', ErrorCategory.INVALID_REQUEST, False),
        (401, '{"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}}', ErrorCategory.AUTHENTICATION_FAILED, False),
        (403, '{"error": {"code": "FORBIDDEN_ERROR", "description": "Feature not enabled for your account"}}', ErrorCategory.PERMISSION_DENIED, False),
        (404, '{"error": {"code": "NOT_FOUND_ERROR", "description": "Payment ID does not exist"}}', ErrorCategory.RESOURCE_NOT_FOUND, False),
        (429, '{"error": {"code": "RATE_LIMIT_ERROR", "description": "Too many requests"}}', ErrorCategory.RATE_LIMITED, True),
        (500, '{"error": {"code": "GATEWAY_ERROR", "description": "Internal server error"}}', ErrorCategory.PROVIDER_UNAVAILABLE, True),
    ],
)
def test_razorpay_error_normalization(status_code, response_body, expected_category, expected_retryable):
    """Verify Razorpay HTTP errors are normalized into structured IntegrationError instances."""
    adapter = RazorpayAdapter("biz_err")
    http_err = urllib.error.HTTPError(
        url="https://api.razorpay.com/v1/orders",
        code=status_code,
        msg="Error",
        hdrs={},
        fp=MagicMock(read=MagicMock(return_value=response_body.encode("utf-8"))),
    )

    err = adapter._normalize_razorpay_error(http_err)
    assert err.category == expected_category
    assert err.is_retryable is expected_retryable


# ============================================================================
# 14. Multi-Tenant Isolation
# ============================================================================

def test_razorpay_multi_tenant_isolation():
    """Verify tenant instances have completely isolated credentials, caches, and environments."""
    adapter_live = RazorpayAdapter(
        business_id="biz_tenant_live",
        credentials={"key_id": "rzp_live_key999", "key_secret": "sec_live_999"},
    )
    adapter_test = RazorpayAdapter(
        business_id="biz_tenant_test",
        credentials={"key_id": "rzp_test_key111", "key_secret": "sec_test_111"},
    )

    assert adapter_live.get_environment() == "live"
    assert adapter_test.get_environment() == "test"
    assert adapter_live.credentials["key_id"] != adapter_test.credentials["key_id"]

    # Seed idempotency in live adapter
    adapter_live._idempotency_cache["tx_live_1"] = ({"order_id": "order_live_1"}, time.time())
    assert "tx_live_1" not in adapter_test._idempotency_cache


# ============================================================================
# 15. Mock Mode Execution
# ============================================================================

def test_razorpay_execute_in_mock_mode():
    """Verify capability execution in mock mode for development and testing."""
    adapter = RazorpayAdapter(
        business_id="biz_mock",
        configuration={"is_mock": True},
    )

    ctx = ExecutionContext(tenant_id="biz_mock", execution_mode="simulated")

    # 1. Create payment request
    res_create = adapter.execute(
        CapabilityType.CREATE_PAYMENT_REQUEST,
        {"amount_cents": 25000, "currency": "INR", "description": "Consultation"},
        context=ctx,
    )
    assert res_create.success is True
    assert res_create.outcome == ExecutionOutcome.OPERATION_PENDING
    assert res_create.data["is_paid"] is False
    assert "plink_" in res_create.data["payment_id"]

    # 2. Get payment status
    res_status = adapter.execute(
        CapabilityType.GET_PAYMENT_STATUS,
        {"payment_id": "pay_mock_123", "status_override": "captured"},
        context=ctx,
    )
    assert res_status.success is True
    assert res_status.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert res_status.data["is_paid"] is True
    assert res_status.data["status"] == "captured"
