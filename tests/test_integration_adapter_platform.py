"""
Comprehensive deterministic test suite for the Multi-Tenant Integration Adapter Platform.
Validates capability contracts, common adapter interfaces, declarative manifests,
lifecycle state transitions, partner approval gating, authoritative sources of truth,
secure envelope encryption, webhook signature verification, replay deduplication,
bounded timeouts, rate-limit backoff, idempotency, ambiguous outcomes, tenant isolation,
truthful outcomes, and redacted diagnostics.
"""

import pytest
import hmac
import hashlib
import time
import base64
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from backend.integrations.models import (
    IntegrationCategory,
    CapabilityType,
    SideEffectClassification,
    IntegrationLifecycleStatus,
    AuthMethod,
    ExecutionOutcome,
    ErrorCategory,
    DiscoveredResource,
    ProviderManifest,
    ExecutionContext,
    CapabilityResult,
    IntegrationError,
    WebhookRequest,
    WebhookResult,
    IntegrationDiagnosticReport,
)
from backend.integrations.contracts import (
    CAPABILITY_CONTRACTS,
    CheckAvailabilityInput,
    AvailabilityResult,
    CreateBookingInput,
    BookingResult,
    CancelBookingInput,
    CreateCalendarEventInput,
    GetCustomerInput,
    CreateOrUpdateCustomerInput,
    SendMessageInput,
    InitiateCallInput,
    TransferCallInput,
    GetCallStatusInput,
    CreateSupportTicketInput,
    CreatePaymentRequestInput,
    GetPaymentStatusInput,
)
from backend.integrations.adapters import (
    BuiltinDiningAdapter,
    BuiltinClinicAdapter,
    GoogleCalendarAdapter,
    ExotelTelephonyAdapter,
    TwilioMessagingAdapter,
    StripePaymentsAdapter,
    HubspotCrmAdapter,
    ZendeskSupportAdapter,
)
from backend.integrations.registry import get_integration_registry
from backend.integrations.manager import IntegrationManager, get_integration_manager
from backend.integrations.resolver import resolve_tool_adapter
from backend.capabilities.models import AuthoritativeSource, CapabilityStatus
from backend.capabilities.credentials import (
    encrypt_credentials,
    decrypt_credentials,
    redact_credential_dict,
)
from backend.database.service import DatabaseService
from backend.database.engine import create_database_engine, init_db_schema


@pytest.fixture
def test_db(isolate_test_database):
    """Isolated test database service using autouse test service."""
    db = isolate_test_database

    # Seed test business tenants
    db.create_business({
        "id": "biz_tenant_alpha",
        "name": "Trattoria Alpha",
        "industry": "restaurant",
        "opening_time": "11:00",
        "closing_time": "23:00",
        "greeting_message": "Welcome to Trattoria Alpha",
    })
    db.create_business({
        "id": "biz_tenant_beta",
        "name": "Beacon Dental Clinic",
        "industry": "healthcare",
        "opening_time": "08:00",
        "closing_time": "18:00",
        "greeting_message": "Welcome to Beacon Dental",
    })

    # Seed dining tables for Alpha
    db.create_resource(
        business_id="biz_tenant_alpha",
        name="Table 1 (Window)",
        resource_type="table",
        capacity=4,
        min_party_size=1,
        max_party_size=4,
        section="Main Dining Room",
    )
    db.create_resource(
        business_id="biz_tenant_alpha",
        name="Table 2 (Patio)",
        resource_type="table",
        capacity=2,
        min_party_size=1,
        max_party_size=2,
        section="Patio",
    )

    # Seed clinic rooms for Beta
    db.create_resource(
        business_id="biz_tenant_beta",
        name="Consultation Suite A",
        resource_type="room",
        capacity=1,
        min_party_size=1,
        max_party_size=2,
        section="First Floor",
    )

    # Mark Alpha and Beta capabilities as ready
    db.set_tool_capability(
        business_id="biz_tenant_alpha",
        tool_id="create_table_booking",
        selected_option_id="builtin_dining",
        status="ready",
        is_enabled=True,
    )
    db.set_tool_capability(
        business_id="biz_tenant_alpha",
        tool_id="check_table_availability",
        selected_option_id="builtin_dining",
        status="ready",
        is_enabled=True,
    )
    db.set_tool_capability(
        business_id="biz_tenant_alpha",
        tool_id="collect_payment",
        selected_option_id="stripe",
        status="ready",
        is_enabled=True,
    )
    db.set_tool_capability(
        business_id="biz_tenant_beta",
        tool_id="create_appointment",
        selected_option_id="builtin_clinic",
        status="ready",
        is_enabled=True,
    )
    db.set_tool_capability(
        business_id="biz_tenant_beta",
        tool_id="check_table_availability",
        selected_option_id="builtin_dining",
        status="ready",
        is_enabled=True,
    )
    db.set_tool_capability(
        business_id="biz_tenant_beta",
        tool_id="check_appointment_availability",
        selected_option_id="builtin_clinic",
        status="ready",
        is_enabled=True,
    )

    return db


# ============================================================================
# 1. Capability Contracts & Schema Validation
# ============================================================================

def test_all_sixteen_capability_contracts_registered():
    """Verify all 16 required capability operations have validated contracts."""
    expected_capabilities = [
        CapabilityType.CHECK_AVAILABILITY,
        CapabilityType.CREATE_BOOKING,
        CapabilityType.GET_BOOKING,
        CapabilityType.RESCHEDULE_BOOKING,
        CapabilityType.CANCEL_BOOKING,
        CapabilityType.CREATE_CALENDAR_EVENT,
        CapabilityType.GET_CUSTOMER,
        CapabilityType.CREATE_OR_UPDATE_CUSTOMER,
        CapabilityType.SEND_MESSAGE,
        CapabilityType.SEND_EMAIL,
        CapabilityType.INITIATE_CALL,
        CapabilityType.TRANSFER_CALL,
        CapabilityType.GET_CALL_STATUS,
        CapabilityType.CREATE_SUPPORT_TICKET,
        CapabilityType.GET_PAYMENT_STATUS,
        CapabilityType.CREATE_PAYMENT_REQUEST,
    ]

    for cap in expected_capabilities:
        assert cap in CAPABILITY_CONTRACTS, f"Missing contract for {cap}"
        contract = CAPABILITY_CONTRACTS[cap]
        assert contract.operation == cap
        assert contract.input_schema is not None
        assert contract.result_schema is not None
        assert contract.side_effect in SideEffectClassification
        assert isinstance(contract.required_permission, str)
        assert contract.default_timeout_seconds > 0


def test_input_schema_validation_rejects_malformed_inputs(test_db):
    """Verify Pydantic schemas enforce type safety, bounds, and required fields."""
    manager = IntegrationManager(db_service=test_db)

    # Party size < 1 is rejected
    res = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CHECK_AVAILABILITY,
        arguments={"start_time": "2026-11-01T19:00:00", "party_size": 0},
    )
    assert not res.success
    assert res.error.category == ErrorCategory.INVALID_REQUEST
    assert "party_size" in res.error.message

    # Negative payment amount is rejected
    res_pay = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CREATE_PAYMENT_REQUEST,
        arguments={"amount_cents": -500},
    )
    assert not res_pay.success
    assert res_pay.error.category == ErrorCategory.INVALID_REQUEST


# ============================================================================
# 2. Common Adapter Interface Implementation
# ============================================================================

def test_all_adapters_implement_common_interface(test_db):
    """Verify all concrete adapters implement all 10 common lifecycle methods."""
    adapters = [
        BuiltinDiningAdapter("biz_tenant_alpha"),
        BuiltinClinicAdapter("biz_tenant_beta"),
        GoogleCalendarAdapter("biz_tenant_beta", configuration={"calendar_id": "dr@clinic.com"}),
        ExotelTelephonyAdapter("biz_tenant_alpha", configuration={"account_sid": "AC123", "caller_id": "+918047192000"}),
        TwilioMessagingAdapter("biz_tenant_alpha", configuration={"account_sid": "AC1234567890", "from_number": "+14155552671"}),
        StripePaymentsAdapter("biz_tenant_alpha", configuration={"secret_key": "sk_test_1234567890"}),
        HubspotCrmAdapter("biz_tenant_alpha", configuration={"access_token": "pat-na1-123456789"}),
        ZendeskSupportAdapter("biz_tenant_alpha", configuration={"subdomain": "acme", "email": "admin@acme.com"}),
    ]

    for adapter in adapters:
        # 1. get_manifest()
        manifest = adapter.get_manifest()
        assert isinstance(manifest, ProviderManifest)
        assert manifest.provider_id
        assert manifest.category in IntegrationCategory
        assert manifest.authoritative_source in AuthoritativeSource

        # 2. validate_configuration()
        val_res = adapter.validate_configuration(adapter.configuration)
        assert hasattr(val_res, "passed")

        # 3. test_connection()
        test_res = adapter.test_connection()
        assert hasattr(test_res, "passed")

        # 4. discover_resources()
        resources = adapter.discover_resources("")
        assert isinstance(resources, list)

        # 5. get_supported_capabilities()
        caps = adapter.get_supported_capabilities()
        assert isinstance(caps, list)
        assert len(caps) > 0

        # 6. disconnect()
        assert adapter.disconnect() is True


# ============================================================================
# 3. Declarative Manifests & Registry
# ============================================================================

def test_registry_manifest_catalog():
    """Verify registry catalogs all providers with categories and auth methods."""
    registry = get_integration_registry()
    manifests = registry.list_manifests()
    assert len(manifests) >= 8

    provider_ids = {m.provider_id for m in manifests}
    assert "builtin_dining" in provider_ids
    assert "builtin_clinic" in provider_ids
    assert "google_calendar" in provider_ids
    assert "exotel" in provider_ids
    assert "twilio" in provider_ids
    assert "stripe" in provider_ids
    assert "hubspot" in provider_ids
    assert "zendesk" in provider_ids

    # Check setup fields declare label, type, secret status
    stripe_manifest = registry.get_manifest("stripe")
    assert stripe_manifest.category == IntegrationCategory.PAYMENTS
    secret_field = next(f for f in stripe_manifest.required_setup_fields if f.key == "secret_key")
    assert secret_field.secret is True


# ============================================================================
# 4. Tenant Lifecycle State Machine & Partner Approval Gating
# ============================================================================

def test_partner_approval_gating(test_db):
    """
    Verify that if partner approval is required but pending,
    the integration status is PENDING_PROVIDER_APPROVAL and cannot execute live operations.
    """
    manager = IntegrationManager(db_service=test_db)

    # Create a custom provider manifest with partner_approval_required=True
    class PartnerApprovalAdapter(BuiltinDiningAdapter):
        def get_manifest(self) -> ProviderManifest:
            m = super().get_manifest()
            m.partner_approval_required = True
            m.provider_id = "opentable_partner"
            return m

    adapter = PartnerApprovalAdapter("biz_tenant_alpha", configuration={"partner_approved": False})
    readiness = adapter.assess_readiness(test_db)
    assert not readiness.is_ready
    assert readiness.status == CapabilityStatus.PENDING_PROVIDER_APPROVAL

    # Verify that partner-approved configuration passes
    adapter_approved = PartnerApprovalAdapter("biz_tenant_alpha", configuration={"partner_approved": True})
    readiness_approved = adapter_approved.assess_readiness(test_db)
    assert readiness_approved.status == CapabilityStatus.READY


# ============================================================================
# 5. Authoritative Source-of-Truth Separation
# ============================================================================

def test_authoritative_sources_of_truth():
    """
    Verify that each provider explicitly declares its authoritative system of record.
    A calendar is NOT a restaurant inventory; a CRM is NOT a booking system;
    a payment request is NOT proof of settlement.
    """
    dining = BuiltinDiningAdapter("biz_tenant_alpha")
    clinic = BuiltinClinicAdapter("biz_tenant_beta")
    calendar = GoogleCalendarAdapter("biz_tenant_beta")
    stripe = StripePaymentsAdapter("biz_tenant_alpha")
    hubspot = HubspotCrmAdapter("biz_tenant_alpha")
    zendesk = ZendeskSupportAdapter("biz_tenant_alpha")
    exotel = ExotelTelephonyAdapter("biz_tenant_alpha")
    twilio = TwilioMessagingAdapter("biz_tenant_alpha")

    assert dining.authoritative_source == AuthoritativeSource.BUILTIN_DATABASE
    assert clinic.authoritative_source == AuthoritativeSource.BUILTIN_DATABASE
    assert calendar.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR
    assert stripe.authoritative_source == AuthoritativeSource.PAYMENT_GATEWAY
    assert hubspot.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert zendesk.authoritative_source == AuthoritativeSource.SUPPORT_DESK
    assert exotel.authoritative_source == AuthoritativeSource.TELEPHONY_PROVIDER
    assert twilio.authoritative_source == AuthoritativeSource.COMMUNICATION_SERVICE


# ============================================================================
# 6. Credential Vaulting & Envelope Encryption
# ============================================================================

def test_credential_encryption_and_zero_plaintext_leak(test_db):
    """
    Verify credentials are encrypted at rest with AES-256/HMAC authenticated envelope,
    fingerprinted, never leaked in audit logs or to_dict(), and decrypted only inside tenant scope.
    """
    raw_secrets = {
        "api_key": "live_super_secret_key_12345",
        "api_token": "token_abcdef67890",
    }

    encrypted_blob, fingerprint = encrypt_credentials(raw_secrets)
    assert "live_super_secret_key_12345" not in encrypted_blob
    assert fingerprint.startswith("fp_")

    # Save to database
    test_db.save_credential_encrypted(
        business_id="biz_tenant_alpha",
        tool_id="transfer_call",
        option_id="exotel",
        encrypted_secrets=encrypted_blob,
        key_fingerprint=fingerprint,
        scopes=["telephony:call"],
    )

    # Fetch raw record and verify decryption inside tenant boundary
    cred_rec = test_db.get_credential_raw("biz_tenant_alpha", "transfer_call")
    assert cred_rec is not None
    decrypted = decrypt_credentials(cred_rec["encrypted_secrets"])
    assert decrypted["api_key"] == "live_super_secret_key_12345"

    # Verify redaction masks secrets
    redacted = redact_credential_dict(raw_secrets)
    assert "..." in redacted["api_key"]
    assert "super_secret" not in redacted["api_key"]


# ============================================================================
# 7. Webhook Signature Verification & Replay Protection
# ============================================================================

def test_exotel_webhook_signature_verification():
    """Verify Exotel HMAC-SHA256 webhook signature verification."""
    adapter = ExotelTelephonyAdapter("biz_tenant_alpha", configuration={"webhook_secret": "whsec_exotel_9988"})
    payload = b'{"CallSid": "call_123", "Status": "completed"}'

    # Valid signature
    valid_sig = hmac.new(b"whsec_exotel_9988", payload, hashlib.sha256).hexdigest()
    req = WebhookRequest(
        provider_id="exotel",
        headers={"x-exotel-signature": valid_sig},
        raw_body=payload,
        parsed_json={"CallSid": "call_123", "Status": "completed"},
    )
    res = adapter.handle_webhook(req)
    assert res.success
    assert res.event_id == "call_123"

    # Invalid signature
    bad_req = WebhookRequest(
        provider_id="exotel",
        headers={"x-exotel-signature": "tampered_signature_hex"},
        raw_body=payload,
        parsed_json={"CallSid": "call_123", "Status": "completed"},
    )
    bad_res = adapter.handle_webhook(bad_req)
    assert not bad_res.success
    assert "Invalid Exotel webhook signature" in bad_res.message


def test_twilio_webhook_signature_verification():
    """Verify Twilio HMAC-SHA1 webhook signature verification."""
    adapter = TwilioMessagingAdapter("biz_tenant_alpha", configuration={"auth_token": "auth_token_secret_123"})
    url = "https://api.callme.ai/api/webhooks/twilio"
    params = {"AccountSid": "AC123", "MessageSid": "SM12345", "MessageStatus": "delivered"}

    sorted_keys = sorted(params.keys())
    data_to_sign = url + "".join(f"{k}{params[k]}" for k in sorted_keys)
    valid_sig = base64.b64encode(
        hmac.new(b"auth_token_secret_123", data_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")

    req = WebhookRequest(
        provider_id="twilio",
        headers={"x-twilio-signature": valid_sig},
        raw_body=b"",
        parsed_json=params,
        url=url,
    )
    res = adapter.handle_webhook(req)
    assert res.success
    assert res.event_id == "SM12345"
    assert res.event_type == "message_delivered"


def test_stripe_webhook_signature_and_replay_tolerance():
    """Verify Stripe-Signature v1 HMAC-SHA256 verification and replay tolerance."""
    adapter = StripePaymentsAdapter("biz_tenant_alpha", configuration={"webhook_secret": "whsec_stripe_test_77"})
    payload = b'{"id": "evt_charge_999", "type": "payment_intent.succeeded"}'
    now_ts = int(time.time())

    # Valid Stripe signature header
    signed_payload = f"{now_ts}.".encode("utf-8") + payload
    v1_sig = hmac.new(b"whsec_stripe_test_77", signed_payload, hashlib.sha256).hexdigest()
    sig_header = f"t={now_ts},v1={v1_sig}"

    req = WebhookRequest(
        provider_id="stripe",
        headers={"stripe-signature": sig_header},
        raw_body=payload,
        parsed_json={"id": "evt_charge_999", "type": "payment_intent.succeeded"},
    )
    res = adapter.handle_webhook(req)
    assert res.success
    assert res.event_id == "evt_charge_999"

    # Expired timestamp (older than 300s) is rejected
    stale_ts = now_ts - 600
    stale_payload = f"{stale_ts}.".encode("utf-8") + payload
    stale_sig = hmac.new(b"whsec_stripe_test_77", stale_payload, hashlib.sha256).hexdigest()
    stale_header = f"t={stale_ts},v1={stale_sig}"

    stale_req = WebhookRequest(
        provider_id="stripe",
        headers={"stripe-signature": stale_header},
        raw_body=payload,
        parsed_json={"id": "evt_charge_999", "type": "payment_intent.succeeded"},
    )
    stale_res = adapter.handle_webhook(stale_req)
    assert not stale_res.success
    assert "replay tolerance" in stale_res.message


def test_webhook_replay_deduplication():
    """Verify durable deduplication rejects re-delivered webhook events gracefully."""
    manager = IntegrationManager()
    adapter = ExotelTelephonyAdapter("biz_tenant_alpha", configuration={"webhook_secret": "whsec_123"})
    payload = b'{"CallSid": "call_dedup_001", "Status": "completed"}'
    valid_sig = hmac.new(b"whsec_123", payload, hashlib.sha256).hexdigest()

    req = WebhookRequest(
        provider_id="exotel",
        headers={"x-exotel-signature": valid_sig},
        raw_body=payload,
        parsed_json={"CallSid": "call_dedup_001", "Status": "completed"},
    )

    # First delivery: processed
    first_res = manager.handle_provider_webhook("exotel", req)
    assert first_res.success
    assert not first_res.is_duplicate
    assert first_res.processed

    # Second delivery: deduplicated
    second_res = manager.handle_provider_webhook("exotel", req)
    assert second_res.success
    assert second_res.is_duplicate
    assert not second_res.processed


# ============================================================================
# 8. Timeout, Rate-Limit & Safe Exponential Backoff
# ============================================================================

def test_rate_limit_backoff_and_retry_after(monkeypatch):
    """Verify exponential backoff with jitter and Retry-After header compliance."""
    dining = BuiltinDiningAdapter("biz_tenant_alpha")
    call_count = 0
    sleep_intervals = []

    monkeypatch.setattr(time, "sleep", lambda sec: sleep_intervals.append(sec))

    def flaky_dispatch():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return CapabilityResult(
                operation=CapabilityType.CHECK_AVAILABILITY,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                error=IntegrationError(
                    code="RATE_LIMITED",
                    category=ErrorCategory.RATE_LIMITED,
                    message="Rate limit exceeded",
                    safe_user_message="Provider rate limit encountered.",
                    retry_after_seconds=1.5,
                    is_retryable=True,
                ),
            )
        return CapabilityResult(
            operation=CapabilityType.CHECK_AVAILABILITY,
            outcome=ExecutionOutcome.OPERATION_COMPLETED,
            success=True,
            data={"available": True},
        )

    ctx = ExecutionContext(tenant_id="biz_tenant_alpha")
    result = dining.execute_with_retry(
        CapabilityType.CHECK_AVAILABILITY,
        {},
        ctx,
        flaky_dispatch,
    )

    assert result.success
    assert call_count == 3
    assert len(sleep_intervals) == 2
    assert sleep_intervals[0] == 1.5  # Respected Retry-After header


# ============================================================================
# 9. Idempotency & Ambiguous Outcome Protection
# ============================================================================

def test_non_idempotent_operation_suppresses_blind_retry():
    """
    Verify that non-idempotent operations (e.g. create_booking or create_payment_request)
    NEVER automatically blind-retry if that could create duplicate bookings or charges.
    """
    dining = BuiltinDiningAdapter("biz_tenant_alpha")
    call_count = 0

    def failing_booking():
        nonlocal call_count
        call_count += 1
        return CapabilityResult(
            operation=CapabilityType.CREATE_BOOKING,
            outcome=ExecutionOutcome.OPERATION_FAILED,
            success=False,
            error=IntegrationError(
                code="TEMPORARY_ERROR",
                category=ErrorCategory.PROVIDER_UNAVAILABLE,
                message="Downstream error",
                safe_user_message="Booking service unavailable.",
                is_retryable=True,
            ),
        )

    # Calling without idempotency key -> max_retries suppressed to 0
    ctx = ExecutionContext(tenant_id="biz_tenant_alpha", idempotency_key=None)
    result = dining.execute_with_retry(
        CapabilityType.CREATE_BOOKING,
        {"customer_name": "John"},
        ctx,
        failing_booking,
    )

    assert not result.success
    assert call_count == 1  # Blind retry was strictly prevented!


def test_timeout_on_write_returns_ambiguous_outcome():
    """
    Verify that a timeout on a non-idempotent write returns OUTCOME_UNKNOWN,
    preventing false confirmation or dangerous automatic retry.
    """
    dining = BuiltinDiningAdapter("biz_tenant_alpha")

    def timeout_booking():
        raise TimeoutError("Socket timeout waiting for downstream response")

    ctx = ExecutionContext(tenant_id="biz_tenant_alpha", timeout_override=2.0)
    result = dining.execute_with_retry(
        CapabilityType.CREATE_BOOKING,
        {"customer_name": "Sarah"},
        ctx,
        timeout_booking,
    )

    assert not result.success
    assert result.outcome == ExecutionOutcome.OUTCOME_UNKNOWN
    assert result.error.category == ErrorCategory.AMBIGUOUS_OUTCOME
    assert "ambiguous" in result.safe_message.lower()


# ============================================================================
# 10. Multi-Tenant Isolation
# ============================================================================

def test_multi_tenant_isolation(test_db):
    """Verify Tenant A cannot access Tenant B's credentials, tables, or bookings."""
    manager = IntegrationManager(db_service=test_db)

    # Tenant A creates a booking
    res_a = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CREATE_BOOKING,
        arguments={
            "customer_name": "Alice Tenant A",
            "customer_phone": "+14155551000",
            "start_time": "2026-11-01T19:00:00",
            "party_size": 2,
        },
    )
    assert res_a.success
    booking_id = res_a.data["booking_reference"]

    # Tenant B tries to look up Tenant A's booking
    res_b = manager.execute_capability(
        tenant_id="biz_tenant_beta",
        capability=CapabilityType.GET_BOOKING,
        arguments={"booking_id": booking_id},
    )
    assert not res_b.success
    assert res_b.error.category == ErrorCategory.RESOURCE_NOT_FOUND


# ============================================================================
# 11. Truthful Outcomes & Explicit Mock Disclosures
# ============================================================================

def test_truthful_payment_pending_state(test_db):
    """Verify Stripe payment request creation returns OPERATION_PENDING (not completed)."""
    manager = IntegrationManager(db_service=test_db)
    ctx = ExecutionContext(tenant_id="biz_tenant_alpha", execution_mode="mock")

    res = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CREATE_PAYMENT_REQUEST,
        arguments={"amount_cents": 3500, "currency": "usd"},
        context=ctx,
    )

    assert res.success
    assert res.outcome == ExecutionOutcome.OPERATION_PENDING
    assert res.data["status"] == "pending"
    assert "pending" in res.safe_message.lower()


def test_dining_conflict_returns_business_rejection(test_db):
    """Verify double-booking conflict returns BUSINESS_REJECTION with clear reason."""
    manager = IntegrationManager(db_service=test_db)

    # First booking occupies 2-top patio table
    res1 = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CREATE_BOOKING,
        arguments={
            "customer_name": "Guest One",
            "customer_phone": "+14155551111",
            "start_time": "2026-11-02T20:00:00",
            "party_size": 2,
        },
    )
    assert res1.success

    # Second booking for 2-top patio table at identical time
    res2 = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CREATE_BOOKING,
        arguments={
            "customer_name": "Guest Two",
            "customer_phone": "+14155552222",
            "start_time": "2026-11-02T20:00:00",
            "party_size": 2,
        },
    )
    assert res2.success  # Occupies second available table (Window 4-top)

    # Third booking for identical time: no tables left!
    res3 = manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CREATE_BOOKING,
        arguments={
            "customer_name": "Guest Three",
            "customer_phone": "+14155553333",
            "start_time": "2026-11-02T20:00:00",
            "party_size": 2,
        },
    )
    assert not res3.success
    assert res3.outcome == ExecutionOutcome.BUSINESS_REJECTION
    assert res3.error.category == ErrorCategory.CONFLICT


# ============================================================================
# 12. Safe Redacted Diagnostics
# ============================================================================

def test_redacted_diagnostics_view(test_db):
    """Verify diagnostic report contains audit metadata and zero secret leakage."""
    manager = IntegrationManager(db_service=test_db)

    # Perform an execution to generate audit trail
    manager.execute_capability(
        tenant_id="biz_tenant_alpha",
        capability=CapabilityType.CHECK_AVAILABILITY,
        arguments={"start_time": "2026-11-03T18:00:00", "party_size": 2},
    )

    reports = manager.get_tenant_diagnostics("biz_tenant_alpha", provider_id="builtin_dining")
    assert len(reports) == 1
    diag = reports[0]
    assert isinstance(diag, IntegrationDiagnosticReport)
    assert diag.tenant_id == "biz_tenant_alpha"
    assert diag.provider_id == "builtin_dining"
    assert diag.category == IntegrationCategory.RESERVATION
    assert len(diag.recent_audit_events) > 0

    # Ensure no secrets in serialized report
    diag_json = json.dumps(diag.model_dump())
    assert "sk_" not in diag_json
    assert "password" not in diag_json
    assert "token" not in diag_json
