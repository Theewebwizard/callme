"""
Deterministic test suite for OpenTable Partner-Gated Reservation Adapter.
Validates:
1. Manifest declaration and authoritative source (EXTERNAL_RESERVATION_SYSTEM)
2. Partner approval prerequisite and gating (distinguishing PENDING_PROVIDER_APPROVAL from READY)
3. Live reservation execution blocked when partner approval is pending (never substitutes local database or guessed endpoints)
4. Documented partner approval onboarding checklist
5. OpenTable Consumer API v2 availability search payload mapping (YYYY-MM-DDTHH:MM, partySize, seatingArea)
6. Reservation creation with X-OT-Request-Id idempotency token and diner payload
7. Reservation lifecycle: GET, PATCH (reschedule), and DELETE (cancel)
8. Provider error normalization (429 RATE_LIMITED, 400 CONFLICT, 401/403 PERMISSION_DENIED, 404 RESOURCE_NOT_FOUND)
9. Seating area resource discovery
10. Setup wizard gating integration (prevents live activation when pending approval)
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
from backend.integrations.adapters.opentable_adapter import (
    OpenTableAdapter,
    OPENTABLE_SANDBOX_BASE_URL,
    OPENTABLE_PRODUCTION_BASE_URL,
)
from backend.integrations.registry import get_integration_registry
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.database.service import get_database_service


# ==============================================================================
# 1. Manifest and Authoritative Source Tests
# ==============================================================================

def test_opentable_manifest_and_authoritative_source():
    """Verify manifest declares external reservation source and partner approval requirement."""
    adapter = OpenTableAdapter(
        business_id="biz_dining_001",
        tool_id="check_table_availability",
        option_id="opentable",
    )
    manifest = adapter.get_manifest()

    assert adapter.authoritative_source == AuthoritativeSource.EXTERNAL_RESERVATION_SYSTEM
    assert manifest.provider_id == "opentable"
    assert manifest.authoritative_source == AuthoritativeSource.EXTERNAL_RESERVATION_SYSTEM
    assert manifest.partner_approval_required is True

    # Check setup fields
    keys = [f.key for f in manifest.required_setup_fields]
    assert "restaurant_id" in keys
    assert "partner_id" in keys
    assert "partner_api_key" in keys

    # Check optional fields have dict-structured options
    env_field = next(f for f in manifest.optional_setup_fields if f.key == "environment")
    assert env_field.options is not None
    assert all(isinstance(opt, dict) and "value" in opt and "label" in opt for opt in env_field.options)


def test_opentable_registered_in_registry():
    """Verify OpenTableAdapter is registered in central integration registry."""
    registry = get_integration_registry()
    manifest = registry.get_manifest("opentable")
    adapter_cls = registry.get_adapter_class("opentable")

    assert manifest is not None
    assert manifest.provider_id == "opentable"
    assert adapter_cls is OpenTableAdapter


# ==============================================================================
# 2. Partner Approval Gating & Readiness Tests
# ==============================================================================

def test_unapproved_partner_readiness_pending_provider_approval():
    """
    When partner_approved is False or omitted, assess_readiness must report
    status = PENDING_PROVIDER_APPROVAL and is_ready = False.
    """
    adapter = OpenTableAdapter(
        business_id="biz_bistro_001",
        tool_id="create_table_booking",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "callme_partner_sandbox",
            "partner_approved": False,
        },
        credentials={
            "partner_api_key": "sandbox_key_verified",
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
    adapter = OpenTableAdapter(
        business_id="biz_bistro_001",
        tool_id="create_table_booking",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "callme_partner_sandbox",
            "partner_approved": False,
        },
        credentials={
            "partner_api_key": "sandbox_key_verified",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_bistro_001",
        business_id="biz_bistro_001",
        tool_id="create_table_booking",
        provider_id="opentable",
        correlation_id="test_corr_123",
    )

    # Attempting to create booking
    res = adapter.execute(
        CapabilityType.CREATE_BOOKING,
        {
            "party_size": 4,
            "start_time": "2026-11-01T19:00:00",
            "customer_name": "Alice Johnson",
            "customer_phone": "+14155552671",
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
        start_time=datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 1, 20, 30, tzinfo=timezone.utc),
        party_size=4,
    )
    assert avail["available"] is False
    assert avail["count"] == 0

    booking = adapter.create_reservation(
        customer_name="Alice Johnson",
        customer_phone="+14155552671",
        party_size=4,
    )
    assert booking["success"] is False
    assert booking["status"] == "failed"


def test_approved_partner_readiness_ready():
    """
    When partner approval is confirmed and credentials are provided,
    assess_readiness must report status = READY and is_ready = True.
    """
    adapter = OpenTableAdapter(
        business_id="biz_bistro_001",
        tool_id="create_table_booking",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "callme_partner_sandbox",
            "partner_approved": True,
            "environment": "sandbox",
        },
        credentials={
            "partner_api_key": "sandbox_key_verified",
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
    Verify partner approval checklist returns the 4 documented stages
    and tracks completion state truthfully.
    """
    adapter = OpenTableAdapter(
        business_id="biz_dining",
        tool_id="create_table_booking",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "",
            "partner_approved": False,
        },
    )

    checklist = adapter.get_partner_approval_checklist()
    assert len(checklist) == 4
    assert checklist[0]["step"] == 1
    assert "Commercial Integration Agreement" in checklist[0]["title"]
    assert checklist[0]["completed"] is False
    assert checklist[1]["completed"] is False  # Missing partner credentials

    # Now update with partner approval & credentials
    adapter.configuration["partner_approved"] = True
    adapter.configuration["partner_id"] = "callme_ot"
    adapter.credentials["partner_api_key"] = "sec_test_123"

    updated_checklist = adapter.get_partner_approval_checklist()
    assert updated_checklist[0]["completed"] is True
    assert updated_checklist[1]["completed"] is True
    assert updated_checklist[2]["completed"] is True


# ==============================================================================
# 3. Consumer API v2 Availability & Reservation Operations
# ==============================================================================

def test_availability_search_payload_and_mapping():
    """
    Verify availability search formats local date/time (YYYY-MM-DDTHH:MM),
    party size, and seating area for OpenTable Consumer API v2.
    """
    adapter = OpenTableAdapter(
        business_id="biz_dining",
        tool_id="check_table_availability",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "callme_partner",
            "partner_approved": True,
            "environment": "sandbox",
        },
        credentials={
            "partner_api_key": "live_sandbox_token",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_dining",
        business_id="biz_dining",
        tool_id="check_table_availability",
        provider_id="opentable",
        correlation_id="corr_avail_99",
    )

    mock_resp_data = {
        "restaurantId": "104291",
        "slots": [
            {"dateTime": "2026-11-05T19:00", "token": "tok_slot_1", "seatingArea": "Default"},
            {"dateTime": "2026-11-05T19:15", "token": "tok_slot_2", "seatingArea": "Default"},
        ],
    }

    with patch.object(adapter, "_execute_opentable_request", return_value=(200, mock_resp_data, {})) as mock_req:
        res = adapter.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {
                "party_size": 4,
                "start_time": "2026-11-05T19:00:00Z",
                "seating_preference": "Outdoor",
            },
            ctx,
        )

        assert res.success is True
        assert res.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert res.data["available"] is True
        assert len(res.data["available_slots"]) == 2

        # Verify request parameters sent to OpenTable API v2
        mock_req.assert_called_once()
        method, path = mock_req.call_args[0][:2]
        payload = mock_req.call_args[1].get("payload")

        assert method == "POST"
        assert path == "/restaurants/104291/availability"
        assert payload["partySize"] == 4
        assert payload["dateTime"] == "2026-11-05T19:00"
        assert payload["seatingArea"] == "Outdoor"


def test_reservation_creation_with_idempotency_request_id():
    """
    Verify reservation creation passes X-OT-Request-Id idempotency token,
    diner contact information, and returns confirmed booking reference.
    """
    adapter = OpenTableAdapter(
        business_id="biz_dining",
        tool_id="create_table_booking",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "callme_partner",
            "partner_approved": True,
            "environment": "sandbox",
        },
        credentials={
            "partner_api_key": "live_sandbox_token",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_dining",
        business_id="biz_dining",
        tool_id="create_table_booking",
        provider_id="opentable",
        correlation_id="corr_create_001",
        idempotency_key="idemp_ot_res_888",
    )

    mock_resp_data = {
        "confirmationNumber": "OT-104291-774411",
        "reservationId": "res_99220",
        "restaurantId": "104291",
        "dateTime": "2026-11-05T19:30",
        "partySize": 2,
        "status": "confirmed",
        "cancellationPolicy": "Cancel at least 2 hours before dining time to avoid fee.",
    }

    with patch.object(adapter, "_execute_opentable_request", return_value=(201, mock_resp_data, {})) as mock_req:
        res = adapter.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "party_size": 2,
                "start_time": "2026-11-05T19:30:00",
                "customer_name": "Marcus Aurelius",
                "customer_phone": "+14155550199",
                "customer_email": "marcus@rome.org",
                "special_requests": "Quiet table near window please.",
            },
            ctx,
        )

        assert res.success is True
        assert res.outcome == ExecutionOutcome.OPERATION_COMPLETED
        assert res.data["booking_reference"] == "OT-104291-774411"
        assert res.data["status"] == "confirmed"

        mock_req.assert_called_once()
        method, path = mock_req.call_args[0][:2]
        payload = mock_req.call_args[1].get("payload")
        req_id = mock_req.call_args[1].get("request_id")

        assert method == "POST"
        assert path == "/restaurants/104291/reservations"
        assert req_id == "idemp_ot_res_888"  # Idempotency token sent as request-ID
        assert payload["partySize"] == 2
        assert payload["dateTime"] == "2026-11-05T19:30"
        assert payload["diner"]["firstName"] == "Marcus"
        assert payload["diner"]["lastName"] == "Aurelius"
        assert payload["diner"]["phoneNumber"] == "+14155550199"
        assert payload["diner"]["email"] == "marcus@rome.org"
        assert payload["specialRequests"] == "Quiet table near window please."


def test_reservation_lifecycle_get_reschedule_cancel():
    """Verify retrieval, modification (reschedule), and cancellation of OpenTable reservations."""
    adapter = OpenTableAdapter(
        business_id="biz_dining",
        tool_id="create_table_booking",
        option_id="opentable",
        configuration={
            "restaurant_id": "104291",
            "partner_id": "callme_partner",
            "partner_approved": True,
        },
        credentials={
            "partner_api_key": "live_sandbox_token",
        },
    )

    ctx = ExecutionContext(
        tenant_id="biz_dining",
        business_id="biz_dining",
        tool_id="create_table_booking",
        provider_id="opentable",
        correlation_id="corr_life_001",
    )

    # 1. GET Reservation
    with patch.object(adapter, "_execute_opentable_request", return_value=(200, {"status": "confirmed", "partySize": 4, "dateTime": "2026-11-05T20:00"}, {})) as mock_get:
        get_res = adapter.execute(
            CapabilityType.GET_BOOKING,
            {"booking_id": "OT-104291-774411"},
            ctx,
        )
        assert get_res.success is True
        assert get_res.data["status"] == "confirmed"
        mock_get.assert_called_with("GET", "/restaurants/104291/reservations/OT-104291-774411", request_id="corr_life_001")

    # 2. Reschedule Reservation (PATCH)
    with patch.object(adapter, "_execute_opentable_request", return_value=(200, {"status": "rescheduled"}, {})) as mock_patch:
        resched_res = adapter.execute(
            CapabilityType.RESCHEDULE_BOOKING,
            {
                "booking_id": "OT-104291-774411",
                "new_start_time": "2026-11-05T20:30:00",
                "party_size": 4,
            },
            ctx,
        )
        assert resched_res.success is True
        assert resched_res.data["status"] == "rescheduled"
        mock_patch.assert_called_with(
            "PATCH",
            "/restaurants/104291/reservations/OT-104291-774411",
            payload={"dateTime": "2026-11-05T20:30", "partySize": 4},
            request_id="corr_life_001",
        )

    # 3. Cancel Reservation (DELETE)
    with patch.object(adapter, "_execute_opentable_request", return_value=(204, {}, {})) as mock_delete:
        cancel_res = adapter.execute(
            CapabilityType.CANCEL_BOOKING,
            {"booking_id": "OT-104291-774411"},
            ctx,
        )
        assert cancel_res.success is True
        assert cancel_res.data["status"] == "cancelled"
        mock_delete.assert_called_with("DELETE", "/restaurants/104291/reservations/OT-104291-774411", request_id="corr_life_001")


# ==============================================================================
# 4. Error Normalization Tests
# ==============================================================================

@pytest.mark.parametrize(
    "status_code,err_payload,expected_category,expected_retryable",
    [
        (429, {"error": {"code": "throttled", "message": "Rate limit exceeded"}}, ErrorCategory.RATE_LIMITED, True),
        (400, {"error": {"code": "slot_unavailable", "message": "Table no longer available"}}, ErrorCategory.CONFLICT, False),
        (401, {"error": {"code": "unauthorized", "message": "Invalid partner credentials"}}, ErrorCategory.PERMISSION_DENIED, False),
        (403, {"error": {"code": "forbidden", "message": "Partner agreement does not cover this RID"}}, ErrorCategory.PERMISSION_DENIED, False),
        (404, {"error": {"code": "not_found", "message": "Reservation not found"}}, ErrorCategory.RESOURCE_NOT_FOUND, False),
    ],
)
def test_error_normalization(status_code, err_payload, expected_category, expected_retryable):
    """Verify OpenTable API v2 errors are mapped to standard platform categories."""
    adapter = OpenTableAdapter(business_id="biz_dining")
    norm_err = adapter._normalize_opentable_error(err_payload, status_code)

    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ==============================================================================
# 5. Resource Discovery Tests
# ==============================================================================

def test_resource_discovery_seating_areas():
    """Verify seating areas are discovered with RID and area metadata."""
    adapter = OpenTableAdapter(
        business_id="biz_dining",
        configuration={"restaurant_id": "104291"},
        credentials={"partner_api_key": "live_key"},
    )

    mock_areas_resp = {
        "items": [
            {"id": "sa_1", "name": "Main Dining Room", "type": "Default"},
            {"id": "sa_2", "name": "Heated Garden Patio", "type": "Outdoor"},
            {"id": "sa_3", "name": "Chefs Counter", "type": "Bar"},
        ]
    }

    with patch.object(adapter, "_execute_opentable_request", return_value=(200, mock_areas_resp, {})):
        areas = adapter.discover_resources("seating_area")
        assert len(areas) == 3
        assert areas[0].resource_id == "sa_1"
        assert areas[0].name == "Main Dining Room"
        assert areas[0].metadata["seatingArea"] == "Default"
        assert areas[1].metadata["seatingArea"] == "Outdoor"


# ==============================================================================
# 6. Setup Wizard Integration & Gating Tests
# ==============================================================================

def test_setup_wizard_distinguishes_pending_provider_approval_and_blocks_activation():
    """
    Setup wizard integration test:
    1. Saving OpenTable configuration without partner approval reports pending_provider_approval.
    2. Attempting to activate capability raises ValueError and leaves execution disabled.
    3. Confirming partner approval allows readiness to pass and activation to succeed.
    """
    db = get_database_service()
    wizard = CapabilitySetupWizard(db_service=db)
    business_id = "tenant_trattoria"

    db.create_business({
        "id": business_id,
        "name": "Trattoria Romana",
        "industry": "restaurant",
    })

    # Start setup session for create_table_booking using OpenTable
    start_res = wizard.start_setup_session(
        business_id=business_id,
        tool_id="create_table_booking",
        option_id="opentable",
    )
    sess_id = start_res["session_id"]

    # Save configuration without partner approval
    wizard.save_step(
        business_id=business_id,
        session_id=sess_id,
        step_id="configuration",
        input_data={
            "restaurant_id": "104291",
            "partner_id": "callme_partner_id",
            "partner_api_key": "secret_ot_token_xyz",
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
            "restaurant_id": "104291",
            "partner_id": "callme_partner_id",
            "partner_api_key": "sandbox_key_verified",
            "partner_approved": True,
            "environment": "sandbox",
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
