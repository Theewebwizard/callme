"""
Deterministic test suite for Acuity Scheduling Integration Adapter.
Validates:
1. Manifest declaration, authoritative source (EXTERNAL_CALENDAR), and supported capabilities
2. Registry lookup and alias resolution ('acuity' and 'acuity_scheduling')
3. Authentication: Numeric User ID & API Key (Basic Auth) vs OAuth2 Bearer token, zero credential leakage
4. Resource discovery: Calendars (/calendars) and Appointment Types (/appointment-types)
5. Live availability querying: Two-step /availability/dates and /availability/times (never inferred from existing bookings)
6. Appointment creation with timezone offset, customer mapping, and notes idempotency key
7. Clear separation of confirmed (OPERATION_COMPLETED) vs pending/awaiting payment (OPERATION_PENDING) appointments
8. Appointment retrieval, rescheduling, and cancellation
9. Webhook signature verification (HMAC-SHA256 via x-acuity-signature) and replay deduplication
10. Downstream error normalization (429 RATE_LIMITED, 400 CONFLICT, 401 INVALID_CREDENTIALS, 404 RESOURCE_NOT_FOUND)
11. Capability setup wizard integration with envelope-encrypted secrets
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
from backend.integrations.adapters.acuity_adapter import (
    AcuityAdapter,
    ACUITY_BASE_URL,
)
from backend.integrations.registry import get_integration_registry
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.capabilities.specs import get_capability_spec
from backend.database.service import get_database_service
from backend.integrations.manager import get_integration_manager


# ==============================================================================
# 1. Manifest and Authoritative Source Tests
# ==============================================================================

def test_acuity_manifest_and_authoritative_source():
    """Verify manifest declares external calendar source, verified operations, and setup fields."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        option_id="acuity",
    )
    manifest = adapter.get_manifest()

    assert adapter.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR
    assert manifest.provider_id == "acuity"
    assert manifest.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR
    assert manifest.partner_approval_required is False

    # Check verified operations in manifest
    assert CapabilityType.CHECK_AVAILABILITY in manifest.supported_capabilities
    assert CapabilityType.CREATE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.GET_BOOKING in manifest.supported_capabilities
    assert CapabilityType.RESCHEDULE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.CANCEL_BOOKING in manifest.supported_capabilities

    # Check webhook support recorded in manifest
    assert "appointment.scheduled" in manifest.webhook_events
    assert "appointment.rescheduled" in manifest.webhook_events
    assert "appointment.canceled" in manifest.webhook_events

    # Check setup fields: user_id and api_key are required; access_token is optional
    req_keys = [f.key for f in manifest.required_setup_fields]
    assert "user_id" in req_keys
    assert "api_key" in req_keys

    opt_keys = [f.key for f in manifest.optional_setup_fields]
    assert "access_token" in opt_keys
    assert "calendar_id" in opt_keys
    assert "appointment_type_id" in opt_keys


def test_acuity_registered_in_registry():
    """Verify AcuityAdapter and acuity_scheduling alias are registered in registry."""
    registry = get_integration_registry()

    manifest = registry.get_manifest("acuity")
    cls = registry.get_adapter_class("acuity")
    assert manifest is not None
    assert manifest.provider_id == "acuity"
    assert cls is AcuityAdapter

    # Catalog alias lookup
    alias_cls = registry.get_adapter_class("acuity_scheduling")
    assert alias_cls is AcuityAdapter


# ==============================================================================
# 2. Authentication and Credential Validation Tests
# ==============================================================================

def test_acuity_authentication_basic_auth_numeric_id():
    """Verify basic auth format with numeric user ID and base64 header generation."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={
            "user_id": "19283746",
            "api_key": "sec_acuity_live_key_998877",
        },
    )

    # Validation should pass
    val_res = adapter.validate_configuration({})
    assert val_res.passed is True
    assert "19283746" in val_res.details

    # Check HTTP headers generated for request
    headers = adapter._get_headers()
    expected_token = base64.b64encode(b"19283746:sec_acuity_live_key_998877").decode("utf-8")
    assert headers["Authorization"] == f"Basic {expected_token}"
    assert headers["Accept"] == "application/json"


def test_acuity_authentication_rejects_non_numeric_user_id():
    """Verify non-numeric user ID is rejected during validation."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={
            "user_id": "non_numeric_user",
            "api_key": "some_api_key",
        },
    )
    val_res = adapter.validate_configuration({})
    assert val_res.passed is False
    assert "numeric identifier" in val_res.details.lower()


def test_acuity_authentication_oauth2_bearer():
    """Verify OAuth2 access token creates Bearer header."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={
            "access_token": "oauth2_bearer_token_xyz123",
        },
    )
    val_res = adapter.validate_configuration({})
    assert val_res.passed is True
    assert "OAuth2" in val_res.details

    headers = adapter._get_headers()
    assert headers["Authorization"] == "Bearer oauth2_bearer_token_xyz123"


def test_acuity_secrets_never_exposed_in_diagnostics():
    """Verify API keys and access tokens are never exposed in readiness or diagnostics."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={
            "user_id": "123456",
            "api_key": "super_secret_acuity_key_abc",
        },
    )
    # Check manifest fields
    for field in adapter.get_manifest().required_setup_fields:
        if field.key == "api_key":
            assert field.secret is True

    for field in adapter.get_manifest().optional_setup_fields:
        if field.key == "access_token":
            assert field.secret is True

    # Check test_connection diagnostics
    with patch.object(adapter, "_execute_acuity_request", return_value=(200, {"id": 123456, "name": "Dr. Smith"}, {})):
        res = adapter.test_connection()
        assert res.passed is True
        assert "super_secret_acuity_key_abc" not in res.details


# ==============================================================================
# 3. Resource Discovery Tests
# ==============================================================================

def test_acuity_discover_resources_calendars_and_types():
    """Verify discovery of calendars and appointment types via official endpoints."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )

    calendars_mock = [
        {"id": 482910, "name": "Dr. Sarah Adams - Room 101", "email": "sarah@clinic.com", "timezone": "America/New_York"},
        {"id": 482911, "name": "Dr. John Doe - Room 102", "email": "john@clinic.com", "timezone": "America/New_York"},
    ]
    types_mock = [
        {"id": 1029384, "name": "General Checkup", "duration": 45, "price": "150.00", "category": "General"},
        {"id": 1029385, "name": "Dental Cleaning", "duration": 30, "price": "120.00", "category": "Dental"},
    ]

    def mock_execute(method, endpoint, **kwargs):
        if endpoint == "/calendars":
            return (200, calendars_mock, {})
        elif endpoint == "/appointment-types":
            return (200, types_mock, {})
        return (404, {}, {})

    with patch.object(adapter, "_execute_acuity_request", side_effect=mock_execute):
        resources = adapter.discover_resources("all")
        assert len(resources) == 4

        cals = [r for r in resources if r.resource_type == "calendar"]
        assert len(cals) == 2
        assert cals[0].resource_id == "482910"
        assert cals[0].name == "Dr. Sarah Adams - Room 101"
        assert cals[0].metadata["timezone"] == "America/New_York"

        types = [r for r in resources if r.resource_type == "appointment_type"]
        assert len(types) == 2
        assert types[0].resource_id == "1029384"
        assert types[0].name == "General Checkup"
        assert types[0].metadata["duration"] == 45


# ==============================================================================
# 4. Live Availability Tests (Two-Step Lookup, No Inference)
# ==============================================================================

def test_acuity_check_availability_two_step_live():
    """Verify live availability querying via /availability/dates and /availability/times."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        configuration={"appointment_type_id": "1029384", "calendar_id": "482910", "timezone": "America/New_York"},
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
        correlation_id="corr_acuity_avail_1",
    )

    dates_response = [{"date": "2026-11-05"}, {"date": "2026-11-06"}]
    times_response = [
        {"time": "2026-11-05T09:00:00-0500", "slotsAvailable": 1},
        {"time": "2026-11-05T10:00:00-0500", "slotsAvailable": 1},
        {"time": "2026-11-05T14:00:00-0500", "slotsAvailable": 1},
    ]

    def mock_avail(method, endpoint, query_params=None, **kwargs):
        if endpoint == "/availability/dates":
            assert query_params["appointmentTypeID"] == "1029384"
            assert query_params["month"] == "2026-11"
            return (200, dates_response, {})
        elif endpoint == "/availability/times":
            assert query_params["date"] == "2026-11-05"
            assert query_params["appointmentTypeID"] == "1029384"
            return (200, times_response, {})
        return (404, {}, {})

    with patch.object(adapter, "_execute_acuity_request", side_effect=mock_avail):
        result = adapter.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {"start_time": "2026-11-05T09:00:00Z"},
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["available"] is True
        assert len(result.data["slots"]) == 3
        assert result.authoritative_source == AuthoritativeSource.EXTERNAL_CALENDAR.value


def test_acuity_check_availability_date_has_no_slots():
    """Verify business rejection when requested date is not in available dates."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        configuration={"appointment_type_id": "1029384"},
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
    )

    dates_response = [{"date": "2026-11-10"}]  # Requested date 2026-11-05 is missing

    with patch.object(adapter, "_execute_acuity_request", return_value=(200, dates_response, {})):
        result = adapter.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {"start_time": "2026-11-05T09:00:00Z"},
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.BUSINESS_REJECTION
        assert result.data["available"] is False
        assert result.data["reason"] == "no_available_dates"


# ==============================================================================
# 5. Appointment Creation & Status Separation Tests
# ==============================================================================

def test_acuity_create_appointment_confirmed():
    """Verify appointment creation yielding confirmed status maps to OPERATION_COMPLETED."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        configuration={"calendar_id": "482910"},
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
        idempotency_key="acuity_idem_test_001",
    )

    api_response = {
        "id": 99887766,
        "datetime": "2026-11-05T09:00:00-0500",
        "appointmentTypeID": 1029384,
        "calendarID": 482910,
        "firstName": "Alice",
        "lastName": "Walker",
        "email": "alice@example.com",
        "phone": "+15551234567",
        "status": "confirmed",
    }

    with patch.object(adapter, "_execute_acuity_request", return_value=(200, api_response, {})) as mock_req:
        result = adapter.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "start_time": "2026-11-05T09:00:00-05:00",
                "customer_name": "Alice Walker",
                "customer_email": "alice@example.com",
                "customer_phone": "+15551234567",
                "appointment_type_id": 1029384,
                "notes": "First consultation",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["id"] == "99887766"
        assert result.data["status"] == "confirmed"

        # Verify request payload sent to Acuity
        call_kwargs = mock_req.call_args[1]
        payload = call_kwargs["payload"]
        assert payload["appointmentTypeID"] == 1029384
        assert payload["firstName"] == "Alice"
        assert payload["lastName"] == "Walker"
        assert "acuity_idem_test_001" in payload["notes"]


def test_acuity_create_appointment_pending_awaiting_payment():
    """Verify appointment requiring confirmation/payment maps to OPERATION_PENDING."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
    )

    api_response = {
        "id": 99887767,
        "datetime": "2026-11-05T09:00:00-0500",
        "firstName": "Bob",
        "lastName": "Taylor",
        "status": "awaiting_payment",  # Pending payment / approval
    }

    with patch.object(adapter, "_execute_acuity_request", return_value=(200, api_response, {})):
        result = adapter.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "start_time": "2026-11-05T09:00:00-05:00",
                "customer_name": "Bob Taylor",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_PENDING
        assert result.data["id"] == "99887767"
        assert result.data["status"] == "awaiting_payment"
        assert "pending" in result.safe_message.lower()


# ==============================================================================
# 6. Lookup, Reschedule, and Cancellation Tests
# ==============================================================================

def test_acuity_get_appointment():
    """Verify lookup returns appointment details."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
    )

    api_response = {
        "id": 11223344,
        "datetime": "2026-11-05T10:00:00-0500",
        "firstName": "Carol",
        "lastName": "Danvers",
        "status": "confirmed",
    }

    with patch.object(adapter, "_execute_acuity_request", return_value=(200, api_response, {})):
        result = adapter.execute(
            CapabilityType.GET_BOOKING,
            {"appointment_id": "11223344"},
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["appointment_reference"] == "11223344"
        assert result.data["firstName"] == "Carol"


def test_acuity_reschedule_appointment():
    """Verify reschedule invokes PUT /appointments/{id}/reschedule."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
    )

    api_response = {
        "id": 11223344,
        "datetime": "2026-11-06T14:00:00-0500",
        "status": "rescheduled",
    }

    with patch.object(adapter, "_execute_acuity_request", return_value=(200, api_response, {})) as mock_req:
        result = adapter.execute(
            CapabilityType.RESCHEDULE_BOOKING,
            {
                "appointment_id": "11223344",
                "new_start_time": "2026-11-06T14:00:00Z",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["status"] == "rescheduled"

        # Verify endpoint called
        endpoint = mock_req.call_args[0][1]
        assert endpoint == "/appointments/11223344/reschedule"


def test_acuity_cancel_appointment():
    """Verify cancellation invokes PUT /appointments/{id}/cancel with admin flag."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    context = ExecutionContext(
        tenant_id="biz_clinic_001",
        business_id="biz_clinic_001",
        tool_id="book_appointment",
        provider_id="acuity",
    )

    with patch.object(adapter, "_execute_acuity_request", return_value=(200, {"id": 11223344, "status": "canceled"}, {})) as mock_req:
        result = adapter.execute(
            CapabilityType.CANCEL_BOOKING,
            {
                "appointment_id": "11223344",
                "reason": "Patient requested cancellation",
            },
            context,
        )

        assert result.success is True
        assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert result.data["status"] == "canceled"

        # Verify endpoint and query params
        method = mock_req.call_args[0][0]
        endpoint = mock_req.call_args[0][1]
        query_params = mock_req.call_args[1].get("query_params", {})
        assert method == "PUT"
        assert endpoint == "/appointments/11223344/cancel"
        assert query_params.get("admin") == "true"


# ==============================================================================
# 7. Webhook Processing & Cryptographic Verification Tests
# ==============================================================================

def test_acuity_webhook_signature_verification_success():
    """Verify HMAC-SHA256 signature verification matches Acuity specification."""
    api_key = "test_webhook_secret_key_123"
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": api_key},
    )

    raw_body = b"action=appointment.scheduled&id=998877&calendarID=482910&appointmentTypeID=1029384"
    signature = base64.b64encode(
        hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")

    headers = {"x-acuity-signature": signature, "content-type": "application/x-www-form-urlencoded"}

    # Test verify_webhook_signature directly
    assert adapter.verify_webhook_signature(raw_body, headers) is True

    # Test handle_webhook
    req = WebhookRequest(
        provider_id="acuity",
        headers=headers,
        raw_body=raw_body,
        parsed_json={"action": "appointment.scheduled", "id": 998877},
        url="https://api.answerly.ai/api/webhooks/acuity",
    )
    result = adapter.handle_webhook(req)
    assert result.success is True
    assert result.event_type == "appointment.scheduled"
    assert result.event_id == "acuity_appointment.scheduled_998877"


def test_acuity_webhook_signature_tampered_fails():
    """Verify tampered webhook payload fails signature verification."""
    api_key = "test_webhook_secret_key_123"
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": api_key},
    )

    raw_body = b"action=appointment.scheduled&id=998877"
    bad_signature = "invalid_base64_signature_here"
    headers = {"x-acuity-signature": bad_signature}

    assert adapter.verify_webhook_signature(raw_body, headers) is False

    req = WebhookRequest(
        provider_id="acuity",
        headers=headers,
        raw_body=raw_body,
        parsed_json={},
        url="https://api.answerly.ai/api/webhooks/acuity",
    )
    result = adapter.handle_webhook(req)
    assert result.success is False
    assert "Invalid Acuity webhook signature" in result.message


def test_acuity_webhook_replay_deduplication():
    """Verify duplicate webhook deliveries are acknowledged but flagged as duplicates."""
    manager = get_integration_manager()
    api_key = "test_webhook_secret_key_123"

    raw_body = b'{"action": "appointment.canceled", "id": 554433}'
    signature = base64.b64encode(
        hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")

    headers = {"x-acuity-signature": signature, "content-type": "application/json"}

    # Mock adapter creation inside manager
    mock_adapter = MagicMock()
    mock_adapter.handle_webhook.return_value = WebhookResult(
        success=True,
        event_id="acuity_appointment.canceled_554433",
        event_type="appointment.canceled",
        processed=True,
        is_duplicate=False,
    )

    with patch("backend.integrations.registry.IntegrationRegistry.create_adapter", return_value=mock_adapter):
        req = WebhookRequest(
            provider_id="acuity",
            headers=headers,
            raw_body=raw_body,
            parsed_json={"action": "appointment.canceled", "id": 554433},
            url="https://api.answerly.ai/api/webhooks/acuity",
        )

        res1 = manager.handle_provider_webhook("acuity", req)
        assert res1.success is True
        assert res1.is_duplicate is False

        # Deliver same webhook a second time
        res2 = manager.handle_provider_webhook("acuity", req)
        assert res2.success is True
        assert res2.is_duplicate is True
        assert "duplicate" in res2.message.lower()


# ==============================================================================
# 8. Downstream Error Normalization Tests
# ==============================================================================

def test_acuity_error_normalization_rate_limited():
    """Verify HTTP 429 maps to ErrorCategory.RATE_LIMITED and is_retryable=True."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    err_body = {"status_code": 429, "message": "Too many requests. Please slow down."}
    norm_err = adapter._normalize_acuity_error(err_body, 429)

    assert norm_err.category == ErrorCategory.RATE_LIMITED
    assert norm_err.is_retryable is True


def test_acuity_error_normalization_conflict():
    """Verify HTTP 400 slot conflict maps to ErrorCategory.CONFLICT."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    err_body = {"status_code": 400, "message": "That time slot is no longer available.", "error": "conflict"}
    norm_err = adapter._normalize_acuity_error(err_body, 400)

    assert norm_err.category == ErrorCategory.CONFLICT
    assert norm_err.is_retryable is False


def test_acuity_error_normalization_unauthorized():
    """Verify HTTP 401 maps to ErrorCategory.AUTHENTICATION_FAILED."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    err_body = {"status_code": 401, "message": "Invalid API key or user ID."}
    norm_err = adapter._normalize_acuity_error(err_body, 401)

    assert norm_err.category == ErrorCategory.AUTHENTICATION_FAILED
    assert norm_err.is_retryable is False


def test_acuity_error_normalization_not_found():
    """Verify HTTP 404 maps to ErrorCategory.RESOURCE_NOT_FOUND."""
    adapter = AcuityAdapter(
        business_id="biz_clinic_001",
        credentials={"user_id": "12345", "api_key": "live_key"},
    )
    err_body = {"status_code": 404, "message": "Appointment not found."}
    norm_err = adapter._normalize_acuity_error(err_body, 404)

    assert norm_err.category == ErrorCategory.RESOURCE_NOT_FOUND
    assert norm_err.is_retryable is False


# ==============================================================================
# 9. Setup Wizard and Capability Integration Tests
# ==============================================================================

def test_acuity_setup_wizard_flow():
    """Verify CapabilitySetupWizard end-to-end setup with Acuity credentials."""
    db_service = get_database_service()
    biz_id = "biz_clinic_wizard_001"
    db_service.create_business({
        "id": biz_id,
        "name": "Midtown Dental Practice",
        "industry": "healthcare",
    })

    wizard = CapabilitySetupWizard(db_service)
    session = wizard.start_setup_session(
        business_id=biz_id,
        tool_id="check_appointment_availability",
        option_id="acuity",
    )
    assert session["tool_id"] == "check_appointment_availability"
    assert session["selected_option_id"] == "acuity"
    assert session["status"] == "needs_input"

    # Step 2: Save credentials and configuration
    save_res = wizard.save_step(
        business_id=biz_id,
        tool_id="check_appointment_availability",
        data={
            "user_id": "998877",
            "api_key": "live_acuity_api_key_123",
            "calendar_id": "482910",
        },
        is_completed=True,
    )
    assert save_res["success"] is True
    assert save_res["status"] == "validating"

    # Verify credential in database is encrypted
    cred = db_service.get_credential_raw(biz_id, "check_appointment_availability")
    assert cred is not None
    assert "encrypted_secrets" in cred
    assert "live_acuity_api_key_123" not in str(cred["encrypted_secrets"])

    from backend.capabilities.credentials import decrypt_credentials
    decrypted = decrypt_credentials(cred["encrypted_secrets"])
    assert decrypted["api_key"] == "live_acuity_api_key_123"
    assert save_res["step_data"]["user_id"] == "998877"
    assert save_res["step_data"]["calendar_id"] == "482910"


# ==============================================================================
# 10. End-to-End Tool Execution & Webhook HTTP Endpoint Tests
# ==============================================================================

def test_acuity_tool_execution_integration():
    """Verify healthcare handle_create_appointment executes AcuityAdapter and returns SUCCESS."""
    from backend.tools.implementations.healthcare import handle_create_appointment
    from backend.tools.definitions import CreateAppointmentInput
    from backend.tools.base import ToolExecutionStatus
    from backend.capabilities.credentials import encrypt_credentials

    db_service = get_database_service()
    biz_id = "biz_clinic_tool_001"
    db_service.create_business({
        "id": biz_id,
        "name": "Dr. Sarah Dental Practice",
        "industry": "healthcare",
    })

    # Configure tool with Acuity option
    db_service.set_tool_capability(
        business_id=biz_id,
        tool_id="create_appointment",
        is_enabled=True,
        selected_option_id="acuity",
        status="ready",
        configuration={"calendar_id": "482910", "appointment_type_id": "1029384"},
    )
    encrypted_payload, fp = encrypt_credentials({"user_id": "192837", "api_key": "live_acuity_key_tool"})
    db_service.save_credential(
        business_id=biz_id,
        tool_id="create_appointment",
        option_id="acuity",
        encrypted_secrets=encrypted_payload,
        key_fingerprint=fp,
    )

    api_response = {
        "id": 88776655,
        "datetime": "2026-11-10T14:00:00-0500",
        "status": "confirmed",
        "firstName": "David",
        "lastName": "Kim",
    }

    input_data = CreateAppointmentInput(
        patient_name="David Kim",
        patient_phone="+15559876543",
        service_or_department="Dentistry",
        appointment_date="2026-11-10",
        appointment_time="14:00",
        notes="Routine checkup",
        idempotency_key="acuity_e2e_tool_001",
    )
    biz_config = {
        "id": biz_id,
        "name": "Dr. Sarah Dental Practice",
        "industry": "healthcare",
        "execution_mode": "live",
    }

    with patch.object(AcuityAdapter, "_execute_acuity_request", return_value=(200, api_response, {})):
        exec_res = handle_create_appointment(input_data, biz_config)

        assert exec_res.status == ToolExecutionStatus.SUCCESS
        assert exec_res.data["appointment_reference"] == "88776655"
        assert exec_res.data["authoritative_source"] == AuthoritativeSource.EXTERNAL_CALENDAR.value
        assert "confirmed" in exec_res.data["status"]


def test_acuity_tool_execution_failure_maps_to_error():
    """Verify healthcare handle_create_appointment returns ERROR when Acuity rejects the slot."""
    from backend.tools.implementations.healthcare import handle_create_appointment
    from backend.tools.definitions import CreateAppointmentInput
    from backend.tools.base import ToolExecutionStatus
    from backend.capabilities.credentials import encrypt_credentials

    db_service = get_database_service()
    biz_id = "biz_clinic_tool_fail_001"
    db_service.create_business({
        "id": biz_id,
        "name": "Dr. Sarah Dental Practice",
        "industry": "healthcare",
    })

    db_service.set_tool_capability(
        business_id=biz_id,
        tool_id="create_appointment",
        is_enabled=True,
        selected_option_id="acuity",
        status="ready",
        configuration={"calendar_id": "482910"},
    )
    encrypted_payload, fp = encrypt_credentials({"user_id": "192837", "api_key": "live_acuity_key_tool"})
    db_service.save_credential(
        business_id=biz_id,
        tool_id="create_appointment",
        option_id="acuity",
        encrypted_secrets=encrypted_payload,
        key_fingerprint=fp,
    )

    input_data = CreateAppointmentInput(
        patient_name="David Kim",
        patient_phone="+15559876543",
        service_or_department="Dentistry",
        appointment_date="2026-11-10",
        appointment_time="14:00",
        notes="Routine checkup",
    )
    biz_config = {
        "id": biz_id,
        "name": "Dr. Sarah Dental Practice",
        "industry": "healthcare",
        "execution_mode": "live",
    }

    conflict_err = {"status_code": 400, "message": "Time slot unavailable.", "error": "conflict"}
    with patch.object(AcuityAdapter, "_execute_acuity_request", return_value=(400, conflict_err, {})):
        exec_res = handle_create_appointment(input_data, biz_config)

        assert exec_res.status == ToolExecutionStatus.ERROR
        assert not exec_res.success
        assert "unable to" in exec_res.message.lower()


def test_acuity_webhook_http_endpoint():
    """Verify POST /api/webhooks/acuity HTTP endpoint verifies signature and returns 200."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    api_key = "webhook_secret_for_http_test"

    raw_body = b"action=appointment.scheduled&id=883311&calendarID=482910"
    signature = base64.b64encode(
        hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")

    mock_adapter = MagicMock()
    mock_adapter.handle_webhook.return_value = WebhookResult(
        success=True,
        event_id="acuity_appointment.scheduled_883311",
        event_type="appointment.scheduled",
        processed=True,
        is_duplicate=False,
    )

    with patch("backend.integrations.registry.IntegrationRegistry.create_adapter", return_value=mock_adapter):
        res_ok = client.post(
            "/api/webhooks/acuity",
            content=raw_body,
            headers={"x-acuity-signature": signature, "content-type": "application/x-www-form-urlencoded"},
        )
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["received"] is True
        assert data["status"] == "processed"
        assert data["event_type"] == "appointment.scheduled"

