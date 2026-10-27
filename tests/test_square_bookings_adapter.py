"""
Deterministic test suite for Square Bookings Integration Adapter.
Validates:
1. Manifest declaration, authoritative source (EXTERNAL_CALENDAR), and supported capabilities
2. Registry lookup and alias resolution ('square' and 'square_bookings')
3. Authentication and secret vaulting (OAuth2 access token with least-privilege scopes)
4. Seller eligibility validation (Appointments enabled, active locations, catalog services)
5. Resource discovery: Locations (/v2/locations), Services (/v2/catalog), and Team Members (/v2/bookings/team-member-booking-profiles)
6. Real-time availability lookup via /v2/bookings/availability/search (no slot inference)
7. Booking creation with customer resolution, appointment segments, and idempotency key
8. Separation of confirmed (ACCEPTED) vs pending (PENDING) appointments
9. Booking retrieval, update/reschedule with version concurrency check, and cancellation
10. Concurrency safeguard: 409 VERSION_MISMATCH normalization to ErrorCategory.CONFLICT
11. Webhook signature verification (HMAC-SHA256 via x-square-hmacsha256-signature) and replay deduplication
12. Downstream error normalization (429 RATE_LIMITED, 401 AUTHENTICATION_FAILED, 403 PERMISSION_DENIED, 404 RESOURCE_NOT_FOUND)
13. Capability setup wizard integration with envelope-encrypted secrets
14. End-to-end AI receptionist tool execution (handle_create_appointment) and webhook HTTP endpoint
"""

import json
import base64
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from backend.capabilities.models import CapabilityStatus, AuthoritativeSource
from backend.integrations.models import (
    CapabilityType,
    ExecutionOutcome,
    ErrorCategory,
    ExecutionContext,
    WebhookRequest,
    WebhookResult,
)
from backend.integrations.adapters.square_bookings_adapter import (
    SquareBookingsAdapter,
    SQUARE_PRODUCTION_URL,
    SQUARE_SANDBOX_URL,
)
from backend.integrations.registry import get_integration_registry
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.capabilities.specs import get_capability_spec
from backend.database.service import get_database_service
from backend.integrations.manager import get_integration_manager


# ==============================================================================
# 1. Manifest and Authoritative Source Tests
# ==============================================================================

def test_square_manifest_and_authoritative_source():
    """Verify manifest declares external calendar source, verified operations, and least-privilege scopes."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        tool_id="create_appointment",
        option_id="square",
    )
    manifest = adapter.get_manifest()

    assert adapter.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR
    assert manifest.provider_id == "square"
    assert manifest.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR
    assert manifest.partner_approval_required is False

    # Check verified operations in manifest
    assert CapabilityType.CHECK_AVAILABILITY in manifest.supported_capabilities
    assert CapabilityType.CREATE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.GET_BOOKING in manifest.supported_capabilities
    assert CapabilityType.RESCHEDULE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.CANCEL_BOOKING in manifest.supported_capabilities

    # Check least-privilege OAuth scopes
    scopes = manifest.required_oauth_scopes
    assert "APPOINTMENTS_READ" in scopes
    assert "APPOINTMENTS_WRITE" in scopes
    assert "APPOINTMENTS_BUSINESS_SETTINGS_READ" in scopes
    assert "MERCHANT_PROFILE_READ" in scopes
    assert "CUSTOMERS_READ" in scopes
    assert "CUSTOMERS_WRITE" in scopes
    assert "ITEMS_READ" in scopes

    # Check webhook support recorded in manifest
    assert "booking.created" in manifest.webhook_events
    assert "booking.updated" in manifest.webhook_events
    assert "booking.canceled" in manifest.webhook_events

    # Check setup fields: access_token is required and secret
    token_field = next(f for f in manifest.required_setup_fields if f.key == "access_token")
    assert token_field.secret is True
    assert token_field.required is True

    # Check optional fields: location_id, service_variation_id, team_member_id, environment
    opt_keys = [f.key for f in manifest.optional_setup_fields]
    assert "location_id" in opt_keys
    assert "service_variation_id" in opt_keys
    assert "team_member_id" in opt_keys
    assert "environment" in opt_keys
    assert "webhook_signature_key" in opt_keys


def test_square_registered_in_registry():
    """Verify SquareBookingsAdapter and square_bookings alias are registered in registry."""
    registry = get_integration_registry()

    manifest = registry.get_manifest("square")
    cls = registry.get_adapter_class("square")
    assert manifest is not None
    assert manifest.provider_id == "square"
    assert cls is SquareBookingsAdapter

    # Catalog alias lookup
    alias_cls = registry.get_adapter_class("square_bookings")
    assert alias_cls is SquareBookingsAdapter


# ==============================================================================
# 2. Authentication & Credential Validation Tests
# ==============================================================================

def test_square_authentication_and_secret_vaulting():
    """Verify access token presence validation and secret masking."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "EAAAExt_live_square_token_998877"},
    )

    val_res = adapter.validate_configuration({})
    assert val_res.passed is True
    assert "production" in val_res.details.lower()

    # Secret is never exposed
    assert "EAAAExt_live_square_token_998877" not in val_res.details


def test_square_authentication_missing_token_rejected():
    """Verify missing access token is rejected during validation."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={},
    )
    val_res = adapter.validate_configuration({})
    assert val_res.passed is False
    assert "missing" in val_res.details.lower()


# ==============================================================================
# 3. Seller Eligibility Validation Tests
# ==============================================================================

def test_square_seller_eligibility_online_bookings_disabled():
    """Verify readiness check fails when seller has online bookings disabled in booking profile."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )

    mock_client = MagicMock()
    # Mock business profile with booking_enabled = False
    mock_profile = MagicMock()
    mock_profile.booking_enabled = False
    mock_client.bookings.get_business_profile.return_value = MagicMock(business_booking_profile=mock_profile)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        res = adapter.test_connection()
        assert res.passed is False
        assert "online bookings are disabled" in res.details.lower()


def test_square_seller_eligibility_missing_permissions():
    """Verify readiness check fails when merchant lacks Appointments permissions."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )

    mock_client = MagicMock()
    from square.core.api_error import ApiError
    # Simulate 403 NOT_AUTHORIZED error from Square
    api_err = ApiError(
        status_code=403,
        headers={},
        body={"errors": [{"code": "NOT_AUTHORIZED", "category": "AUTHENTICATION_ERROR", "detail": "Merchant not authorized for Appointments."}]},
    )
    mock_client.bookings.get_business_profile.side_effect = api_err

    with patch.object(adapter, "_get_client", return_value=mock_client):
        res = adapter.test_connection()
        assert res.passed is False
        assert "authorization failed" in res.details.lower()


def test_square_seller_eligibility_no_active_locations():
    """Verify readiness check fails when merchant has zero active locations."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )

    mock_client = MagicMock()
    mock_profile = MagicMock()
    mock_profile.booking_enabled = True
    mock_client.bookings.get_business_profile.return_value = MagicMock(business_booking_profile=mock_profile)

    # Return only inactive location
    mock_loc = MagicMock(id="LOC_1", status="INACTIVE")
    mock_client.locations.list.return_value = MagicMock(locations=[mock_loc])

    with patch.object(adapter, "_get_client", return_value=mock_client):
        res = adapter.test_connection()
        assert res.passed is False
        assert "no active business locations" in res.details.lower()


# ==============================================================================
# 4. Resource Discovery Tests
# ==============================================================================

def test_square_discover_resources_locations_services_and_team():
    """Verify discovery of locations, catalog services, and bookable team members."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )

    mock_client = MagicMock()

    # 1. Locations
    mock_loc1 = MagicMock(id="LOC_MAIN", status="ACTIVE", timezone="America/New_York")
    mock_loc1.name = "Downtown Spa"
    mock_client.locations.list.return_value = MagicMock(locations=[mock_loc1])

    # 2. Catalog Service Variations
    mock_vdata = MagicMock(service_duration=3600000)  # 60 mins
    mock_vdata.name = "Signature Facial"
    mock_item_var = MagicMock(id="VAR_FACIAL_101", item_variation_data=mock_vdata)
    mock_client.catalog.list.return_value = MagicMock(objects=[mock_item_var])

    # 3. Team Member Booking Profiles
    mock_tm_profile = MagicMock(team_member_id="TM_EMILY", display_name="Emily Davis", is_bookable=True)
    mock_client.bookings.team_member_profiles.list.return_value = MagicMock(team_member_booking_profiles=[mock_tm_profile])

    with patch.object(adapter, "_get_client", return_value=mock_client):
        resources = adapter.discover_resources("all")
        assert len(resources) == 3

        loc = next(r for r in resources if r.resource_type == "location")
        assert loc.resource_id == "LOC_MAIN"
        assert loc.name == "Downtown Spa"
        assert loc.metadata["timezone"] == "America/New_York"

        serv = next(r for r in resources if r.resource_type == "service_variation")
        assert serv.resource_id == "VAR_FACIAL_101"
        assert serv.name == "Signature Facial"
        assert serv.metadata["duration_minutes"] == 60

        tm = next(r for r in resources if r.resource_type == "team_member")
        assert tm.resource_id == "TM_EMILY"
        assert tm.name == "Emily Davis"
        assert tm.metadata["is_bookable"] is True


# ==============================================================================
# 5. Live Availability Search Tests (No Inference)
# ==============================================================================

def test_square_check_availability_slots_available():
    """Verify availability search via /v2/bookings/availability/search returns OPERATION_COMPLETED."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        configuration={"location_id": "LOC_MAIN", "service_variation_id": "VAR_FACIAL_101"},
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="check_appointment_availability",
        provider_id="square",
    )

    mock_client = MagicMock()
    mock_avail1 = MagicMock(start_at="2026-11-15T14:00:00Z", location_id="LOC_MAIN")
    mock_avail2 = MagicMock(start_at="2026-11-15T15:00:00Z", location_id="LOC_MAIN")
    mock_client.bookings.search_availability.return_value = MagicMock(availabilities=[mock_avail1, mock_avail2])

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {"start_time": "2026-11-15T14:00:00Z"},
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["available"] is True
        assert len(result.data["slots"]) == 2
        assert result.data["slots"][0]["start_at"] == "2026-11-15T14:00:00Z"
        assert result.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR.value


def test_square_check_availability_no_slots():
    """Verify availability search returns BUSINESS_REJECTION when zero slots are open."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        configuration={"location_id": "LOC_MAIN", "service_variation_id": "VAR_FACIAL_101"},
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="check_appointment_availability",
        provider_id="square",
    )

    mock_client = MagicMock()
    mock_client.bookings.search_availability.return_value = MagicMock(availabilities=[])

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {"start_time": "2026-11-15T14:00:00Z"},
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.BUSINESS_REJECTION
        assert result.data["available"] is False


# ==============================================================================
# 6. Booking Creation & Status Separation Tests
# ==============================================================================

def test_square_create_booking_confirmed_accepted():
    """Verify booking creation with status ACCEPTED yields OPERATION_COMPLETED."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        configuration={"location_id": "LOC_MAIN", "service_variation_id": "VAR_FACIAL_101"},
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="create_appointment",
        provider_id="square",
        idempotency_key="sq_idem_key_001",
    )

    mock_client = MagicMock()
    # Mock customer creation
    mock_client.customers.create.return_value = MagicMock(customer=MagicMock(id="CUST_8877"))

    # Mock booking creation
    mock_booking = MagicMock(
        id="BK_SQUARE_9988",
        version=1,
        status="ACCEPTED",
        start_at="2026-11-15T14:00:00Z",
        location_id="LOC_MAIN",
        customer_id="CUST_8877",
    )
    mock_client.bookings.create.return_value = MagicMock(booking=mock_booking)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "start_time": "2026-11-15T14:00:00Z",
                "customer_name": "Sophia Bennett",
                "customer_phone": "+15559876543",
                "customer_email": "sophia@example.com",
                "notes": "First visit consultation",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["booking_id"] == "BK_SQUARE_9988"
        assert result.data["version"] == 1
        assert result.data["status"] == "ACCEPTED"
        assert result.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR.value

        # Verify idempotency key was forwarded
        call_kwargs = mock_client.bookings.create.call_args[1]
        assert call_kwargs["idempotency_key"] == "sq_idem_key_001"
        assert call_kwargs["booking"]["customer_id"] == "CUST_8877"


def test_square_create_booking_pending_approval():
    """Verify booking with status PENDING yields OPERATION_PENDING."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="create_appointment",
        provider_id="square",
    )

    mock_client = MagicMock()
    mock_booking = MagicMock(
        id="BK_SQUARE_PENDING_01",
        version=0,
        status="PENDING",
        start_at="2026-11-15T14:00:00Z",
    )
    mock_client.bookings.create.return_value = MagicMock(booking=mock_booking)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "start_time": "2026-11-15T14:00:00Z",
                "customer_name": "Liam Scott",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_PENDING
        assert result.data["status"] == "PENDING"
        assert "pending" in result.safe_message.lower()


# ==============================================================================
# 7. Booking Retrieval, Reschedule, and Cancellation Tests
# ==============================================================================

def test_square_get_booking():
    """Verify retrieving booking details and version."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="create_appointment",
        provider_id="square",
    )

    mock_client = MagicMock()
    mock_booking = MagicMock(
        id="BK_12345",
        version=2,
        status="ACCEPTED",
        start_at="2026-11-15T14:00:00Z",
    )
    mock_client.bookings.get.return_value = MagicMock(booking=mock_booking)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.GET_BOOKING,
            {"booking_id": "BK_12345"},
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["booking_id"] == "BK_12345"
        assert result.data["version"] == 2


def test_square_reschedule_booking_with_version_locking():
    """Verify reschedule fetches latest version and updates booking."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="create_appointment",
        provider_id="square",
    )

    mock_client = MagicMock()
    # Mock current booking fetch (version 1)
    mock_client.bookings.get.return_value = MagicMock(booking=MagicMock(version=1))

    # Mock update response (version 2)
    mock_updated = MagicMock(
        id="BK_12345",
        version=2,
        status="ACCEPTED",
        start_at="2026-11-16T15:00:00Z",
    )
    mock_client.bookings.update.return_value = MagicMock(booking=mock_updated)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.RESCHEDULE_BOOKING,
            {
                "booking_id": "BK_12345",
                "new_start_time": "2026-11-16T15:00:00Z",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["version"] == 2

        # Verify version 1 was sent in update payload
        call_kwargs = mock_client.bookings.update.call_args[1]
        assert call_kwargs["booking"]["version"] == 1


def test_square_reschedule_concurrency_version_mismatch():
    """Verify 409 VERSION_MISMATCH maps to ErrorCategory.CONFLICT."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="create_appointment",
        provider_id="square",
    )

    mock_client = MagicMock()
    from square.core.api_error import ApiError
    api_err = ApiError(
        status_code=409,
        headers={},
        body={"errors": [{"code": "VERSION_MISMATCH", "category": "CONFLICT", "detail": "The requested version does not match the latest version."}]},
    )
    mock_client.bookings.update.side_effect = api_err

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.RESCHEDULE_BOOKING,
            {
                "booking_id": "BK_12345",
                "version": 1,
                "new_start_time": "2026-11-16T15:00:00Z",
            },
            context,
        )

        assert result.success is False
        assert result.outcome == ExecutionOutcome.OPERATION_FAILED
        assert result.error.category == ErrorCategory.CONFLICT
        assert "VERSION_MISMATCH" in result.error.code


def test_square_cancel_booking():
    """Verify cancellation invokes bookings.cancel with version and idempotency key."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )
    context = ExecutionContext(
        tenant_id="biz_salon_001",
        business_id="biz_salon_001",
        tool_id="create_appointment",
        provider_id="square",
        idempotency_key="sq_can_idem_001",
    )

    mock_client = MagicMock()
    mock_client.bookings.cancel.return_value = MagicMock(
        booking=MagicMock(id="BK_12345", status="CANCELLED_BY_CUSTOMER")
    )

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.execute(
            CapabilityType.CANCEL_BOOKING,
            {
                "booking_id": "BK_12345",
                "version": 2,
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["status"] == "CANCELLED_BY_CUSTOMER"

        call_kwargs = mock_client.bookings.cancel.call_args[1]
        assert call_kwargs["booking_version"] == 2
        assert call_kwargs["idempotency_key"] == "sq_can_idem_001"


# ==============================================================================
# 8. Webhook Signature & Replay Deduplication Tests
# ==============================================================================

def test_square_webhook_signature_verification_success():
    """Verify HMAC-SHA256 signature verification over notification_url + raw_body."""
    sig_key = "sq_wh_secret_key_8899"
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123", "webhook_signature_key": sig_key},
    )

    notification_url = "https://api.callme.ai/api/webhooks/square"
    raw_body = b'{"type": "booking.created", "event_id": "evt_sq_101", "data": {"object": {"booking": {"id": "BK_7788", "version": 1}}}}'

    combined = notification_url.encode("utf-8") + raw_body
    signature = base64.b64encode(
        hmac.new(sig_key.encode("utf-8"), combined, hashlib.sha256).digest()
    ).decode("utf-8")

    headers = {"x-square-hmacsha256-signature": signature}

    # Verify signature check directly
    assert adapter.verify_webhook_signature(raw_body, headers, notification_url=notification_url) is True

    # Test handle_webhook
    req = WebhookRequest(
        provider_id="square",
        headers=headers,
        raw_body=raw_body,
        parsed_json=json.loads(raw_body.decode("utf-8")),
        url=notification_url,
    )
    result = adapter.handle_webhook(req)
    assert result.success is True
    assert result.event_type == "booking.created"
    assert result.event_id == "evt_sq_101"


def test_square_webhook_signature_tampered_fails():
    """Verify tampered webhook payload fails signature verification."""
    sig_key = "sq_wh_secret_key_8899"
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123", "webhook_signature_key": sig_key},
    )

    notification_url = "https://api.callme.ai/api/webhooks/square"
    raw_body = b'{"type": "booking.created"}'
    headers = {"x-square-hmacsha256-signature": "tampered_signature_value"}

    assert adapter.verify_webhook_signature(raw_body, headers, notification_url=notification_url) is False

    req = WebhookRequest(
        provider_id="square",
        headers=headers,
        raw_body=raw_body,
        parsed_json={},
        url=notification_url,
    )
    result = adapter.handle_webhook(req)
    assert result.success is False
    assert "Invalid Square webhook signature" in result.message


def test_square_webhook_replay_deduplication():
    """Verify duplicate webhook deliveries are recognized and flagged as duplicates."""
    manager = get_integration_manager()
    sig_key = "sq_wh_secret_key_8899"

    notification_url = "https://api.callme.ai/api/webhooks/square"
    raw_body = b'{"type": "booking.canceled", "event_id": "evt_unique_sq_dedup_01"}'

    combined = notification_url.encode("utf-8") + raw_body
    signature = base64.b64encode(
        hmac.new(sig_key.encode("utf-8"), combined, hashlib.sha256).digest()
    ).decode("utf-8")
    headers = {"x-square-hmacsha256-signature": signature}

    mock_adapter = MagicMock()
    mock_adapter.handle_webhook.return_value = WebhookResult(
        success=True,
        event_id="evt_unique_sq_dedup_01",
        event_type="booking.canceled",
        processed=True,
        is_duplicate=False,
    )

    with patch("backend.integrations.registry.IntegrationRegistry.create_adapter", return_value=mock_adapter):
        req = WebhookRequest(
            provider_id="square",
            headers=headers,
            raw_body=raw_body,
            parsed_json={"type": "booking.canceled", "event_id": "evt_unique_sq_dedup_01"},
            url=notification_url,
        )

        res1 = manager.handle_provider_webhook("square", req)
        assert res1.success is True
        assert res1.is_duplicate is False

        # Deliver second time
        res2 = manager.handle_provider_webhook("square", req)
        assert res2.success is True
        assert res2.is_duplicate is True


# ==============================================================================
# 9. Downstream Error Normalization Tests
# ==============================================================================

def test_square_error_normalization():
    """Verify mapping of Square ApiError codes to normalized ErrorCategory."""
    adapter = SquareBookingsAdapter(
        business_id="biz_salon_001",
        credentials={"access_token": "live_token_123"},
    )
    from square.core.api_error import ApiError

    # 429 RATE_LIMITED
    err_429 = ApiError(status_code=429, headers={"retry-after": "5"}, body={"errors": [{"code": "RATE_LIMITED", "category": "RATE_LIMIT_ERROR", "detail": "Slow down"}]})
    norm_429 = adapter._normalize_square_error(err_429)
    assert norm_429.category == ErrorCategory.RATE_LIMITED
    assert norm_429.is_retryable is True
    assert norm_429.retry_after_seconds == 5.0

    # 401 UNAUTHORIZED
    err_401 = ApiError(status_code=401, headers={}, body={"errors": [{"code": "UNAUTHORIZED", "category": "AUTHENTICATION_ERROR", "detail": "Bad token"}]})
    norm_401 = adapter._normalize_square_error(err_401)
    assert norm_401.category == ErrorCategory.AUTHENTICATION_FAILED

    # 403 NOT_AUTHORIZED
    err_403 = ApiError(status_code=403, headers={}, body={"errors": [{"code": "NOT_AUTHORIZED", "category": "AUTHENTICATION_ERROR", "detail": "Missing scope"}]})
    norm_403 = adapter._normalize_square_error(err_403)
    assert norm_403.category == ErrorCategory.PERMISSION_DENIED

    # 404 NOT_FOUND
    err_404 = ApiError(status_code=404, headers={}, body={"errors": [{"code": "NOT_FOUND", "category": "INVALID_REQUEST_ERROR", "detail": "Booking missing"}]})
    norm_404 = adapter._normalize_square_error(err_404)
    assert norm_404.category == ErrorCategory.RESOURCE_NOT_FOUND


# ==============================================================================
# 10. Setup Wizard & Tool Execution Tests
# ==============================================================================

def test_square_setup_wizard_flow():
    """Verify CapabilitySetupWizard onboarding with Square credentials and encryption."""
    db_service = get_database_service()
    biz_id = "biz_salon_wizard_001"
    db_service.create_business({
        "id": biz_id,
        "name": "Luxe Beauty Bar",
        "industry": "clinic",
    })

    wizard = CapabilitySetupWizard(db_service)
    session = wizard.start_setup_session(
        business_id=biz_id,
        tool_id="check_appointment_availability",
        option_id="square",
    )
    assert session["tool_id"] == "check_appointment_availability"
    assert session["selected_option_id"] == "square"
    assert session["status"] == "needs_input"

    # Step 2: Save credentials and configuration
    save_res = wizard.save_step(
        business_id=biz_id,
        tool_id="check_appointment_availability",
        data={
            "access_token": "EAAAExt_live_square_wizard_token",
            "location_id": "LOC_LUXE_01",
            "service_variation_id": "VAR_HAIRCUT_01",
        },
        is_completed=True,
    )
    assert save_res["success"] is True
    assert save_res["status"] == "validating"

    # Verify encrypted secrets in vault
    cred = db_service.get_credential_raw(biz_id, "check_appointment_availability")
    assert cred is not None
    assert "encrypted_secrets" in cred
    assert "EAAAExt_live_square_wizard_token" not in str(cred["encrypted_secrets"])

    from backend.capabilities.credentials import decrypt_credentials
    decrypted = decrypt_credentials(cred["encrypted_secrets"])
    assert decrypted["access_token"] == "EAAAExt_live_square_wizard_token"
    assert save_res["step_data"]["location_id"] == "LOC_LUXE_01"
    assert save_res["step_data"]["service_variation_id"] == "VAR_HAIRCUT_01"


def test_square_tool_execution_integration():
    """Verify healthcare handle_create_appointment executes SquareBookingsAdapter and returns SUCCESS."""
    from backend.tools.implementations.healthcare import handle_create_appointment
    from backend.tools.definitions import CreateAppointmentInput
    from backend.tools.base import ToolExecutionStatus
    from backend.capabilities.credentials import encrypt_credentials

    db_service = get_database_service()
    biz_id = "biz_salon_tool_001"
    db_service.create_business({
        "id": biz_id,
        "name": "Dr. Reed Wellness & Clinic",
        "industry": "clinic",
    })

    # Configure tool with Square option
    db_service.set_tool_capability(
        business_id=biz_id,
        tool_id="create_appointment",
        is_enabled=True,
        selected_option_id="square",
        status="ready",
        configuration={"location_id": "LOC_MAIN", "service_variation_id": "VAR_CONSULT"},
    )
    encrypted_payload, fp = encrypt_credentials({"access_token": "live_sq_tool_token"})
    db_service.save_credential(
        business_id=biz_id,
        tool_id="create_appointment",
        option_id="square",
        encrypted_secrets=encrypted_payload,
        key_fingerprint=fp,
    )

    mock_client = MagicMock()
    mock_booking = MagicMock(
        id="BK_SQ_TOOL_7788",
        version=1,
        status="ACCEPTED",
        start_at="2026-11-20T10:00:00Z",
    )
    mock_client.bookings.create.return_value = MagicMock(booking=mock_booking)

    input_data = CreateAppointmentInput(
        patient_name="Olivia Martinez",
        patient_phone="+15551239876",
        service_or_department="Dermatology",
        appointment_date="2026-11-20",
        appointment_time="10:00",
        notes="Skin consultation",
        idempotency_key="sq_e2e_tool_idem_001",
    )
    biz_config = {
        "id": biz_id,
        "name": "Dr. Reed Wellness & Clinic",
        "industry": "clinic",
        "execution_mode": "live",
    }

    with patch.object(SquareBookingsAdapter, "_get_client", return_value=mock_client):
        exec_res = handle_create_appointment(input_data, biz_config)

        assert exec_res.status == ToolExecutionStatus.SUCCESS
        assert exec_res.data["booking_id"] == "BK_SQ_TOOL_7788"
        assert exec_res.data["authoritative_source"] == AuthoritativeSource.EXTERNAL_CALENDAR.value
        assert "confirmed" in exec_res.message.lower() or "accepted" in exec_res.data["status"].lower()


def test_square_webhook_http_endpoint():
    """Verify POST /api/webhooks/square HTTP endpoint verifies signature and returns 200."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    sig_key = "webhook_secret_for_http_test"

    raw_body = b'{"type": "booking.created", "event_id": "evt_sq_http_9988"}'
    notification_url = "http://testserver/api/webhooks/square"

    combined = notification_url.encode("utf-8") + raw_body
    signature = base64.b64encode(
        hmac.new(sig_key.encode("utf-8"), combined, hashlib.sha256).digest()
    ).decode("utf-8")

    mock_adapter = MagicMock()
    mock_adapter.handle_webhook.return_value = WebhookResult(
        success=True,
        event_id="evt_sq_http_9988",
        event_type="booking.created",
        processed=True,
        is_duplicate=False,
    )

    with patch("backend.integrations.registry.IntegrationRegistry.create_adapter", return_value=mock_adapter):
        res_ok = client.post(
            "/api/webhooks/square",
            content=raw_body,
            headers={"x-square-hmacsha256-signature": signature, "content-type": "application/json"},
        )
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["received"] is True
        assert data["status"] == "processed"
        assert data["event_type"] == "booking.created"
