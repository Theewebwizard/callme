"""
Deterministic test suite for SevenRooms Reservation and Guest-Management Adapter.
Validates:
1. Manifest declaration, authoritative source (EXTERNAL_RESERVATION), and verified capabilities
2. Partner approval prerequisite and gating (distinguishing PENDING_PROVIDER_APPROVAL from READY)
3. Live reservation execution blocked when partner approval is pending (never substitutes local database or guessed endpoints)
4. Offering built-in reservation manager (builtin_dining) as a separate, distinct option
5. Documented partner approval onboarding checklist (4 stages)
6. SevenRooms REST API v2_4 availability search payload mapping (venue_id, date, time, party_size, seating_area)
7. Reservation creation with X-Request-Id / client_reference_id idempotency tokens and guest profile mapping
8. Full reservation lifecycle: GET, PATCH (reschedule), and DELETE (cancel)
9. Provider error normalization (429 RATE_LIMITED, 400 CONFLICT, 401/403 PERMISSION_DENIED, 404 RESOURCE_NOT_FOUND)
10. Seating section resource discovery
11. Setup wizard gating integration (prevents live activation when pending approval)
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from backend.capabilities.models import CapabilityStatus, AuthoritativeSource
from backend.integrations.models import (
    CapabilityType,
    ExecutionOutcome,
    ErrorCategory,
    ExecutionContext,
)
from backend.integrations.adapters.sevenrooms_adapter import (
    SevenRoomsAdapter,
    SEVENROOMS_US_BASE_URL,
    SEVENROOMS_EU_BASE_URL,
)
from backend.integrations.registry import get_integration_registry
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.capabilities.specs import get_capability_spec
from backend.database.service import get_database_service


# ==============================================================================
# 1. Manifest and Authoritative Source Tests
# ==============================================================================

def test_sevenrooms_manifest_and_authoritative_source():
    """Verify manifest declares external reservation source, verified operations, and partner gating."""
    adapter = SevenRoomsAdapter(
        business_id="biz_hospitality_001",
        tool_id="check_table_availability",
        option_id="sevenrooms",
    )
    manifest = adapter.get_manifest()

    assert adapter.authoritative_source == AuthoritativeSource.EXTERNAL_RESERVATION
    assert manifest.provider_id == "sevenrooms"
    assert manifest.authoritative_source == AuthoritativeSource.EXTERNAL_RESERVATION
    assert manifest.partner_approval_required is True

    # Check verified operations in manifest
    assert CapabilityType.CHECK_AVAILABILITY in manifest.supported_capabilities
    assert CapabilityType.CREATE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.GET_BOOKING in manifest.supported_capabilities
    assert CapabilityType.RESCHEDULE_BOOKING in manifest.supported_capabilities
    assert CapabilityType.CANCEL_BOOKING in manifest.supported_capabilities

    # Check webhook support recorded in manifest
    assert "reservation.created" in manifest.webhook_events
    assert "reservation.updated" in manifest.webhook_events
    assert "reservation.cancelled" in manifest.webhook_events
    assert "guest.updated" in manifest.webhook_events

    # Check setup fields
    keys = [f.key for f in manifest.required_setup_fields]
    assert "venue_id" in keys
    assert "api_key" in keys

    # Check optional fields have dict-structured options
    env_field = next(f for f in manifest.optional_setup_fields if f.key == "environment")
    assert env_field.options is not None
    assert all(isinstance(opt, dict) and "value" in opt and "label" in opt for opt in env_field.options)


def test_sevenrooms_registered_in_registry():
    """Verify SevenRoomsAdapter and external_sevenrooms alias are registered in registry."""
    registry = get_integration_registry()

    # Direct provider lookup
    sr_manifest = registry.get_manifest("sevenrooms")
    sr_cls = registry.get_adapter_class("sevenrooms")
    assert sr_manifest is not None
    assert sr_manifest.provider_id == "sevenrooms"
    assert sr_cls is SevenRoomsAdapter

    # Catalog alias lookup
    alias_cls = registry.get_adapter_class("external_sevenrooms")
    assert alias_cls is SevenRoomsAdapter


# ==============================================================================
# 2. Partner Approval Gating & Readiness Tests
# ==============================================================================

def test_unapproved_partner_readiness_pending_provider_approval():
    """
    When partner_approved is False or omitted, assess_readiness must report
    status = PENDING_PROVIDER_APPROVAL and is_ready = False.
    """
    adapter = SevenRoomsAdapter(
        business_id="biz_venue_001",
        tool_id="create_table_booking",
        option_id="external_sevenrooms",
        configuration={
            "venue_id": "sr_venue_9981",
            "partner_approved": False,
        },
        credentials={
            "api_key": "sandbox_key_verified",
        },
    )

    report = adapter.assess_readiness()
    assert report.is_ready is False
    assert report.status == CapabilityStatus.PENDING_PROVIDER_APPROVAL
    assert any("Partner Program Approval" in req for req in report.missing_requirements)

    # Capabilities must not be advertised for live execution
    assert adapter.get_supported_capabilities() == []


def test_unapproved_partner_strictly_blocks_execution_without_database_fallback():
    """
    Live reservation execution must be strictly blocked with PERMISSION_DENIED
    when partner approval is pending. Under no circumstances may it fall back
    to querying or modifying the local built-in table database.
    """
    adapter = SevenRoomsAdapter(
        business_id="biz_venue_001",
        tool_id="create_table_booking",
        option_id="external_sevenrooms",
        configuration={
            "venue_id": "sr_venue_9981",
            "partner_approved": False,
        },
        credentials={
            "api_key": "sandbox_key_verified",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_venue_001",
        business_id="biz_venue_001",
        tool_id="create_table_booking",
        provider_id="sevenrooms",
        correlation_id="test_sr_corr_123",
    )

    # Attempting to create booking
    res = adapter.execute(
        CapabilityType.CREATE_BOOKING,
        {
            "party_size": 4,
            "start_time": "2026-11-10T19:30:00",
            "customer_name": "Eleanor Vance",
            "customer_phone": "+14155552345",
        },
        ctx,
    )

    assert res.success is False
    assert res.outcome == ExecutionOutcome.OPERATION_FAILED
    assert res.error is not None
    assert res.error.category == ErrorCategory.PERMISSION_DENIED
    assert res.error.code == "PARTNER_APPROVAL_REQUIRED"
    assert "partner approval is pending" in res.safe_message.lower()

    # Backwards-compatible interface methods must also fail closed
    avail = adapter.check_availability(
        start_time=datetime(2026, 11, 10, 19, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc),
        party_size=4,
    )
    assert avail["available"] is False
    assert avail["count"] == 0

    booking = adapter.create_reservation(
        customer_name="Eleanor Vance",
        customer_phone="+14155552345",
        party_size=4,
    )
    assert booking["success"] is False
    assert booking["status"] == "failed"


def test_approved_partner_readiness_ready():
    """
    When partner approval is confirmed and credentials are provided,
    assess_readiness must report status = READY and is_ready = True.
    """
    adapter = SevenRoomsAdapter(
        business_id="biz_venue_001",
        tool_id="create_table_booking",
        option_id="sevenrooms",
        configuration={
            "venue_id": "sr_venue_9981",
            "partner_approved": True,
            "environment": "us_production",
        },
        credentials={
            "api_key": "sandbox_key_verified",
        },
    )

    report = adapter.assess_readiness()
    assert report.is_ready is True
    assert report.status == CapabilityStatus.READY
    assert len(report.missing_requirements) == 0

    # All capabilities advertised
    caps = adapter.get_supported_capabilities()
    assert CapabilityType.CHECK_AVAILABILITY in caps
    assert CapabilityType.CREATE_BOOKING in caps
    assert CapabilityType.GET_BOOKING in caps
    assert CapabilityType.RESCHEDULE_BOOKING in caps
    assert CapabilityType.CANCEL_BOOKING in caps


def test_partner_approval_checklist():
    """
    Verify partner approval checklist returns the 4 documented onboarding stages
    and tracks completion state truthfully.
    """
    adapter = SevenRoomsAdapter(
        business_id="biz_venue_001",
        tool_id="create_table_booking",
        option_id="sevenrooms",
        configuration={
            "venue_id": "",
            "partner_approved": False,
        },
    )

    checklist = adapter.get_partner_approval_checklist()
    assert len(checklist) == 4
    assert checklist[0]["step"] == 1
    assert "Commercial Integration Agreement" in checklist[0]["title"]
    assert checklist[0]["completed"] is False
    assert checklist[1]["completed"] is False  # Missing credentials
    assert checklist[2]["completed"] is False  # Missing venue_id

    # Now update with venue_id, credentials, and partner approval
    adapter.configuration["partner_approved"] = True
    adapter.configuration["venue_id"] = "sr_venue_9981"
    adapter.credentials["api_key"] = "sec_token_sr_123"

    updated_checklist = adapter.get_partner_approval_checklist()
    assert updated_checklist[0]["completed"] is True
    assert updated_checklist[1]["completed"] is True
    assert updated_checklist[2]["completed"] is True
    assert updated_checklist[3]["completed"] is True


# ==============================================================================
# 3. SevenRooms REST API v2_4 Availability & Reservation Operations
# ==============================================================================

def test_availability_search_payload_and_mapping():
    """
    Verify availability search passes venue_id, date, time, party_size,
    and seating area to SevenRooms REST API v2_4.
    """
    adapter = SevenRoomsAdapter(
        business_id="biz_hospitality",
        tool_id="check_table_availability",
        option_id="sevenrooms",
        configuration={
            "venue_id": "sr_venue_772910",
            "partner_approved": True,
            "environment": "us_production",
        },
        credentials={
            "api_key": "live_bearer_token",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_hospitality",
        business_id="biz_hospitality",
        tool_id="check_table_availability",
        provider_id="sevenrooms",
        correlation_id="corr_sr_avail_99",
    )

    mock_resp_data = {
        "status": True,
        "data": {
            "timeslots": [
                {"time": "19:30", "max_covers": 6, "access_key": "slot_key_1"},
                {"time": "19:45", "max_covers": 4, "access_key": "slot_key_2"},
            ]
        },
    }

    with patch.object(adapter, "_execute_sevenrooms_request", return_value=(200, mock_resp_data, {})) as mock_req:
        res = adapter.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {
                "party_size": 4,
                "start_time": "2026-11-20T19:30:00Z",
                "seating_preference": "Outdoor",
            },
            ctx,
        )

        assert res.success is True
        assert res.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert res.data["available"] is True
        assert len(res.data["available_slots"]) == 2

        # Verify request parameters sent to SevenRooms API
        mock_req.assert_called_once()
        method, path = mock_req.call_args[0][:2]
        payload = mock_req.call_args[1].get("payload")

        assert method == "POST"
        assert path == "/availability"
        assert payload["venue_id"] == "sr_venue_772910"
        assert payload["party_size"] == 4
        assert payload["date"] == "2026-11-20"
        assert payload["time"] == "19:30"
        assert payload["seating_area"] == "Outdoor"


def test_reservation_creation_with_idempotency_request_id():
    """
    Verify reservation creation passes X-Request-Id idempotency token,
    guest details, notes, and returns confirmed reservation ID.
    """
    adapter = SevenRoomsAdapter(
        business_id="biz_hospitality",
        tool_id="create_table_booking",
        option_id="sevenrooms",
        configuration={
            "venue_id": "sr_venue_772910",
            "partner_approved": True,
            "environment": "us_production",
        },
        credentials={
            "api_key": "live_bearer_token",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_hospitality",
        business_id="biz_hospitality",
        tool_id="create_table_booking",
        provider_id="sevenrooms",
        correlation_id="corr_sr_create_001",
        idempotency_key="idemp_sr_res_777",
    )

    mock_resp_data = {
        "status": True,
        "code": 200,
        "data": {
            "reservation_id": "sr_res_987654321",
            "status": "confirmed",
            "datetime": "2026-11-20T19:30",
            "party_size": 2,
            "venue_id": "sr_venue_772910",
            "guest": {
                "guest_id": "sr_guest_12345",
                "first_name": "Julius",
                "last_name": "Caesar",
                "email": "julius@rome.org",
                "phone": "+14155558900",
            },
            "cancellation_policy": "Cancel up to 2 hours before dining time.",
        },
    }

    with patch.object(adapter, "_execute_sevenrooms_request", return_value=(201, mock_resp_data, {})) as mock_req:
        res = adapter.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "party_size": 2,
                "start_time": "2026-11-20T19:30:00",
                "customer_name": "Julius Caesar",
                "customer_phone": "+14155558900",
                "customer_email": "julius@rome.org",
                "special_requests": "Quiet booth for private discussion.",
            },
            ctx,
        )

        assert res.success is True
        assert res.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert res.data["booking_reference"] == "sr_res_987654321"
        assert res.data["status"] == "confirmed"

        mock_req.assert_called_once()
        method, path = mock_req.call_args[0][:2]
        payload = mock_req.call_args[1].get("payload")
        req_id = mock_req.call_args[1].get("request_id")

        assert method == "POST"
        assert path == "/reservations"
        assert req_id == "idemp_sr_res_777"
        assert payload["venue_id"] == "sr_venue_772910"
        assert payload["party_size"] == 2
        assert payload["datetime"] == "2026-11-20T19:30"
        assert payload["guest"]["first_name"] == "Julius"
        assert payload["guest"]["last_name"] == "Caesar"
        assert payload["guest"]["phone"] == "+14155558900"
        assert payload["guest"]["email"] == "julius@rome.org"
        assert payload["client_request_notes"] == "Quiet booth for private discussion."
        assert payload["client_reference_id"] == "idemp_sr_res_777"


def test_reservation_lifecycle_get_reschedule_cancel():
    """Verify retrieval, modification (reschedule), and cancellation of SevenRooms reservations."""
    adapter = SevenRoomsAdapter(
        business_id="biz_hospitality",
        tool_id="create_table_booking",
        option_id="sevenrooms",
        configuration={
            "venue_id": "sr_venue_772910",
            "partner_approved": True,
        },
        credentials={
            "api_key": "live_bearer_token",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_hospitality",
        business_id="biz_hospitality",
        tool_id="create_table_booking",
        provider_id="sevenrooms",
        correlation_id="corr_sr_life_001",
    )

    # 1. GET Reservation
    with patch.object(adapter, "_execute_sevenrooms_request", return_value=(200, {"data": {"status": "confirmed", "party_size": 4, "datetime": "2026-11-20T20:00"}}, {})) as mock_get:
        get_res = adapter.execute(
            CapabilityType.GET_BOOKING,
            {"booking_id": "sr_res_987654321"},
            ctx,
        )
        assert get_res.success is True
        assert get_res.data["status"] == "confirmed"
        mock_get.assert_called_with("GET", "/reservations/sr_res_987654321", request_id="corr_sr_life_001")

    # 2. Reschedule Reservation (PATCH)
    with patch.object(adapter, "_execute_sevenrooms_request", return_value=(200, {"data": {"status": "rescheduled"}}, {})) as mock_patch:
        resched_res = adapter.execute(
            CapabilityType.RESCHEDULE_BOOKING,
            {
                "booking_id": "sr_res_987654321",
                "new_start_time": "2026-11-20T20:30:00",
                "party_size": 4,
            },
            ctx,
        )
        assert resched_res.success is True
        assert resched_res.data["status"] == "rescheduled"
        mock_patch.assert_called_with(
            "PATCH",
            "/reservations/sr_res_987654321",
            payload={"datetime": "2026-11-20T20:30", "party_size": 4},
            request_id="corr_sr_life_001",
        )

    # 3. Cancel Reservation (DELETE)
    with patch.object(adapter, "_execute_sevenrooms_request", return_value=(204, {}, {})) as mock_delete:
        cancel_res = adapter.execute(
            CapabilityType.CANCEL_BOOKING,
            {"booking_id": "sr_res_987654321"},
            ctx,
        )
        assert cancel_res.success is True
        assert cancel_res.data["status"] == "cancelled"
        mock_delete.assert_called_with("DELETE", "/reservations/sr_res_987654321", request_id="corr_sr_life_001")


# ==============================================================================
# 4. Error Normalization Tests
# ==============================================================================

@pytest.mark.parametrize(
    "status_code,err_payload,expected_category,expected_retryable",
    [
        (429, {"error": {"code": "rate_limit_exceeded", "message": "SevenRooms rate limit reached"}}, ErrorCategory.RATE_LIMITED, True),
        (400, {"error": {"code": "slot_unavailable", "message": "Shift capacity reached"}}, ErrorCategory.CONFLICT, False),
        (401, {"error": {"code": "invalid_token", "message": "Expired API Bearer token"}}, ErrorCategory.PERMISSION_DENIED, False),
        (403, {"error": {"code": "unauthorized", "message": "Venue access not permitted"}}, ErrorCategory.PERMISSION_DENIED, False),
        (404, {"error": {"code": "not_found", "message": "Venue or reservation does not exist"}}, ErrorCategory.RESOURCE_NOT_FOUND, False),
    ],
)
def test_error_normalization(status_code, err_payload, expected_category, expected_retryable):
    """Verify SevenRooms REST API errors are mapped to standard platform categories."""
    adapter = SevenRoomsAdapter(business_id="biz_hospitality")
    norm_err = adapter._normalize_sevenrooms_error(err_payload, status_code)

    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ==============================================================================
# 5. Resource Discovery Tests
# ==============================================================================

def test_resource_discovery_sections():
    """Verify seating sections are discovered with venue_id and section metadata."""
    adapter = SevenRoomsAdapter(
        business_id="biz_hospitality",
        configuration={"venue_id": "sr_venue_772910"},
        credentials={"api_key": "live_key"},
    )

    mock_sections_resp = {
        "data": [
            {"id": "sec_1", "name": "Main Dining Room", "type": "Default"},
            {"id": "sec_2", "name": "Rooftop Garden", "type": "Outdoor"},
            {"id": "sec_3", "name": "Cocktail Bar", "type": "Bar"},
        ]
    }

    with patch.object(adapter, "_execute_sevenrooms_request", return_value=(200, mock_sections_resp, {})):
        sections = adapter.discover_resources("seating_area")
        assert len(sections) == 3
        assert sections[0].resource_id == "sec_1"
        assert sections[0].name == "Main Dining Room"
        assert sections[0].metadata["section"] == "Default"
        assert sections[1].metadata["section"] == "Outdoor"


# ==============================================================================
# 6. Setup Wizard Integration & Separate Option Guarantee
# ==============================================================================

def test_setup_wizard_distinguishes_pending_provider_approval_and_blocks_activation():
    """
    Setup wizard integration test:
    1. Saving SevenRooms configuration without partner approval reports pending_provider_approval.
    2. Attempting to activate capability raises ValueError and leaves execution disabled.
    3. Confirming partner approval allows readiness to pass and activation to succeed.
    """
    db = get_database_service()
    wizard = CapabilitySetupWizard(db_service=db)
    business_id = "tenant_osteria"

    db.create_business({
        "id": business_id,
        "name": "Osteria del Sole",
        "industry": "restaurant",
    })

    # Start setup session for create_table_booking using SevenRooms (external_sevenrooms)
    start_res = wizard.start_setup_session(
        business_id=business_id,
        tool_id="create_table_booking",
        option_id="external_sevenrooms",
    )
    sess_id = start_res["session_id"]

    # Save configuration without partner approval
    wizard.save_step(
        business_id=business_id,
        session_id=sess_id,
        step_id="configuration",
        input_data={
            "venue_id": "sr_venue_772910",
            "api_key": "secret_sr_token_abc",
            "partner_approved": False,
        },
    )

    # Validate session: must report pending_provider_approval
    report = wizard.validate_session(business_id=business_id, session_id=sess_id)
    assert report.is_ready is False
    assert report.status == CapabilityStatus.PENDING_PROVIDER_APPROVAL

    # Activation MUST fail closed
    with pytest.raises(ValueError, match="Cannot activate capability.*Partner Program Approval"):
        wizard.activate_capability(business_id=business_id, tool_id="create_table_booking")

    # Confirm capability state summary shows pending_provider_approval and disabled
    summary = wizard.get_capability_summary(business_id, "create_table_booking")
    assert summary.is_enabled is False
    assert summary.status == CapabilityStatus.PENDING_PROVIDER_APPROVAL

    # Now update configuration with partner approval confirmed
    wizard.save_step(
        business_id=business_id,
        session_id=sess_id,
        step_id="configuration",
        input_data={
            "venue_id": "sr_venue_772910",
            "api_key": "sandbox_key_verified",
            "partner_approved": True,
            "environment": "us_production",
        },
    )

    ready_report = wizard.validate_session(business_id=business_id, session_id=sess_id)
    assert ready_report.is_ready is True
    assert ready_report.status == CapabilityStatus.READY

    # Activation now succeeds!
    act_res = wizard.activate_capability(business_id=business_id, tool_id="create_table_booking")
    assert act_res["success"] is True
    assert act_res["is_enabled"] is True
    assert act_res["status"] == CapabilityStatus.READY.value


def test_builtin_dining_offered_as_separate_independent_option():
    """
    Verify the built-in reservation manager (builtin_dining) is offered as a separate,
    first-party option and is never conflated with SevenRooms.
    """
    spec = get_capability_spec("create_table_booking")
    assert spec is not None

    option_ids = [opt.option_id for opt in spec.supported_options]
    assert "builtin_dining" in option_ids
    assert "external_sevenrooms" in option_ids

    builtin_opt = next(opt for opt in spec.supported_options if opt.option_id == "builtin_dining")
    sr_opt = next(opt for opt in spec.supported_options if opt.option_id == "external_sevenrooms")

    # Built-in is first-party with AuthoritativeSource.BUILTIN_DATABASE
    assert builtin_opt.is_built_in is True
    assert builtin_opt.requires_external_connection is False
    assert builtin_opt.authoritative_source == AuthoritativeSource.BUILTIN_DATABASE

    # SevenRooms is third-party with AuthoritativeSource.EXTERNAL_RESERVATION
    assert sr_opt.is_built_in is False
    assert sr_opt.requires_external_connection is True
    assert sr_opt.authoritative_source == AuthoritativeSource.EXTERNAL_RESERVATION
    assert "builtin" not in sr_opt.name.lower()
