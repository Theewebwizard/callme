"""
Deterministic test suite for the Capability Setup Wizard and Tenant-Specific Integration Architecture.
Validates:
- Declarative tool specifications and discovery
- Guided setup session lifecycle and resumption
- Authenticated credential vaulting, encryption, and secret redaction
- First-party built-in dining & clinic adapters
- Double-booking conflict prevention & transactional locking
- Idempotent booking replay safety
- Google Calendar external provider adapter
- Tenant-scoped adapter resolution
- Unauthorized tenant boundary protection
- Runtime execution readiness gating (live vs mock)
- Complete end-to-end REST API capability wizard lifecycle
"""

import json
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.database.engine import (
    create_database_engine,
    init_db_schema,
    session_scope,
)
from backend.database.models import (
    Business,
    BusinessToolConfig,
    ReservableResource,
    Reservation,
)
from backend.database.repositories import (
    BusinessRepository,
    ToolConfigRepository,
    ResourceRepository,
    ReservationRepository,
    ReservationConflictError,
)
from backend.database.service import DatabaseService
from backend.capabilities.models import (
    CapabilityStatus,
    AuthoritativeSource,
    FailureBehavior,
)
from backend.capabilities.specs import (
    get_capability_spec,
    list_all_capability_specs,
    TOOL_CAPABILITY_SPECS,
)
from backend.capabilities.credentials import (
    encrypt_credentials,
    decrypt_credentials,
    redact_credential_dict,
    redact_secret_value,
)
from backend.capabilities.wizard import CapabilitySetupWizard
from backend.integrations.base import BaseIntegrationAdapter
from backend.integrations.builtin_dining_adapter import BuiltinDiningAdapter
from backend.integrations.builtin_clinic_adapter import BuiltinClinicAdapter
from backend.integrations.google_calendar_adapter import GoogleCalendarAdapter
from backend.integrations.resolver import resolve_tool_adapter, UnconfiguredAdapter
from backend.tools.registry import build_default_tool_registry
from backend.tools.base import ToolExecutionStatus, ToolExecutionMode
from backend.main import app


@pytest.fixture
def test_engine():
    """Isolated in-memory SQLite database engine."""
    engine = create_database_engine("sqlite:///:memory:")
    init_db_schema(engine)
    return engine


@pytest.fixture
def test_session_factory(test_engine):
    """Sessionmaker bound to isolated in-memory engine."""
    return sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture
def test_db_service(test_engine, test_session_factory):
    """Isolated DatabaseService for testing."""
    return DatabaseService(engine=test_engine, session_factory=test_session_factory)


@pytest.fixture
def seeded_db_service(test_db_service):
    """Pre-populate test business tenants and tool configurations."""
    test_db_service.create_business(
        {
            "id": "biz_test_restaurant",
            "name": "The Test Bistro",
            "industry": "Restaurant",
            "phone_number": "+15551234567",
            "opening_time": "11:00",
            "closing_time": "23:00",
            "timezone": "UTC",
            "enabled_tools": {"check_table_availability": True, "create_table_booking": True},
        }
    )
    test_db_service.create_business(
        {
            "id": "biz_test_clinic",
            "name": "Apex Dental Test Clinic",
            "industry": "Clinic",
            "phone_number": "+15559876543",
            "opening_time": "09:00",
            "closing_time": "18:00",
            "timezone": "UTC",
            "enabled_tools": {"check_appointment_availability": True, "create_appointment": True},
        }
    )
    return test_db_service


# ==============================================================================
# 1. Declarative Tool Requirements & Discovery Tests
# ==============================================================================

def test_declarative_tool_spec_discovery():
    """Verify all canonical tools declare explicit requirements, options, and schemas."""
    specs = list_all_capability_specs()
    assert len(specs) >= 7

    spec_ids = {s.tool_id for s in specs}
    assert "check_table_availability" in spec_ids
    assert "create_table_booking" in spec_ids
    assert "check_appointment_availability" in spec_ids
    assert "create_appointment" in spec_ids
    assert "take_message" in spec_ids
    assert "transfer_call" in spec_ids
    assert "answer_faq" in spec_ids

    dining_spec = get_capability_spec("check_table_availability")
    assert dining_spec.version == "1.1.0"
    assert "restaurant" in dining_spec.allowed_canonical_industries
    assert dining_spec.failure_behavior in (FailureBehavior.FAIL_CLOSED, FailureBehavior.DEGRADED_RESPONSE)
    assert len(dining_spec.supported_options) >= 2

    # Check option structure
    builtin_opt = next(o for o in dining_spec.supported_options if o.option_id == "builtin_dining")
    assert builtin_opt.is_built_in is True
    assert builtin_opt.authoritative_source == AuthoritativeSource.BUILTIN_DATABASE
    assert any(f.key == "reservation_duration_minutes" for f in builtin_opt.setup_fields)


# ==============================================================================
# 2. Setup Wizard State Machine & Resumption Tests
# ==============================================================================

def test_setup_wizard_session_lifecycle(seeded_db_service):
    """Verify guided setup session initialization, step saving, and resumption."""
    wizard = CapabilitySetupWizard(seeded_db_service)

    # 1. Start setup
    session = wizard.start_setup_session(
        business_id="biz_test_restaurant",
        tool_id="check_table_availability",
        option_id="builtin_dining",
    )
    assert session["tool_id"] == "check_table_availability"
    assert session["selected_option_id"] == "builtin_dining"
    assert session["status"] == "needs_input"
    session_id = session["id"]

    # 2. Save configuration step
    updated = wizard.save_step(
        business_id="biz_test_restaurant",
        tool_id="check_table_availability",
        step_name="configuration",
        data={"reservation_duration_minutes": 120, "buffer_minutes": 15},
        is_completed=True,
    )
    assert updated["step_data"]["reservation_duration_minutes"] == 120
    assert updated["status"] == "validating"

    # 3. Resumption: starting again returns existing session
    resumed = wizard.start_setup_session(
        business_id="biz_test_restaurant",
        tool_id="check_table_availability",
        option_id="builtin_dining",
    )
    assert resumed["id"] == session_id
    assert resumed["step_data"]["reservation_duration_minutes"] == 120


# ==============================================================================
# 3. Authenticated Credential Vault & Redaction Tests
# ==============================================================================

def test_credential_encryption_and_redaction():
    """Verify credentials are encrypted with authenticated envelopes and redacted from logs."""
    secrets = {
        "api_key": "sec_live_998877665544332211",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgk...",
        "environment": "production",
    }

    # 1. Encrypt
    encrypted_blob, fingerprint = encrypt_credentials(secrets)
    assert isinstance(encrypted_blob, str)
    assert isinstance(fingerprint, str)
    assert "sec_live" not in encrypted_blob
    assert "BEGIN PRIVATE KEY" not in encrypted_blob

    # 2. Decrypt
    decrypted = decrypt_credentials(encrypted_blob)
    assert decrypted["api_key"] == "sec_live_998877665544332211"
    assert decrypted["environment"] == "production"

    # 3. Redact
    redacted = redact_credential_dict(secrets)
    assert redacted["api_key"] == "sec_...2211"
    assert redacted["private_key"] == "[REDACTED_SECRET]"
    assert redacted["environment"] == "production"


# ==============================================================================
# 4. Built-in Dining Adapter & Readiness Tests
# ==============================================================================

def test_builtin_dining_adapter_readiness(seeded_db_service):
    """Verify dining adapter assesses readiness based on table inventory in database."""
    adapter = BuiltinDiningAdapter(
        business_id="biz_test_restaurant",
        tool_id="check_table_availability",
        option_id="builtin_dining",
        configuration={"reservation_duration_minutes": 90},
    )

    # 1. Without tables registered, readiness fails with NEEDS_INPUT
    report1 = adapter.assess_readiness(seeded_db_service)
    assert report1.is_ready is False
    assert report1.status == CapabilityStatus.NEEDS_INPUT
    assert any("Resource Inventory" in req for req in report1.missing_requirements)

    # 2. Register active table
    seeded_db_service.create_resource(
        business_id="biz_test_restaurant",
        name="Table 1 (Window)",
        capacity=4,
        min_party_size=1,
        max_party_size=4,
        resource_type="table",
        section="Window",
    )

    # 3. With table registered, readiness passes
    report2 = adapter.assess_readiness(seeded_db_service)
    assert report2.is_ready is True
    assert report2.status == CapabilityStatus.READY
    assert len(report2.missing_requirements) == 0


# ==============================================================================
# 5. Concurrency & Double-Booking Conflict Prevention Tests
# ==============================================================================

def test_double_booking_conflict_prevention(seeded_db_service, monkeypatch):
    """Verify transactional reservation prevents overlapping bookings on same resource."""
    # Ensure get_database_service returns our isolated test instance
    from backend.database import service as db_mod
    monkeypatch.setattr(db_mod, "get_database_service", lambda: seeded_db_service)

    # 1. Add single 2-top table
    table = seeded_db_service.create_resource(
        business_id="biz_test_restaurant",
        name="Table Exclusive",
        capacity=2,
        min_party_size=1,
        max_party_size=2,
        resource_type="table",
    )

    adapter = BuiltinDiningAdapter(
        business_id="biz_test_restaurant",
        tool_id="create_table_booking",
        option_id="builtin_dining",
    )

    start1 = datetime(2026, 11, 15, 19, 0, 0, tzinfo=timezone.utc)
    end1 = datetime(2026, 11, 15, 20, 30, 0, tzinfo=timezone.utc)

    # First booking succeeds
    res1 = adapter.create_reservation(
        customer_name="Alice Smith",
        customer_phone="+15551112222",
        party_size=2,
        start_time=start1,
        end_time=end1,
    )
    assert res1["success"] is True
    assert res1["status"] == "confirmed"

    # Conflicting booking during overlapping window (19:30 - 21:00) must raise ReservationConflictError
    start2 = datetime(2026, 11, 15, 19, 30, 0, tzinfo=timezone.utc)
    end2 = datetime(2026, 11, 15, 21, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ReservationConflictError):
        adapter.create_reservation(
            customer_name="Bob Jones",
            customer_phone="+15553334444",
            party_size=2,
            start_time=start2,
            end_time=end2,
        )


# ==============================================================================
# 6. Idempotency & Duplicate Request Safety Tests
# ==============================================================================

def test_idempotent_booking_replay(seeded_db_service, monkeypatch):
    """Verify replaying a booking request with the same idempotency_key returns identical reference."""
    from backend.database import service as db_mod
    monkeypatch.setattr(db_mod, "get_database_service", lambda: seeded_db_service)

    seeded_db_service.create_resource(
        business_id="biz_test_restaurant",
        name="Table A",
        capacity=4,
        min_party_size=1,
        max_party_size=4,
    )

    adapter = BuiltinDiningAdapter(
        business_id="biz_test_restaurant",
        tool_id="create_table_booking",
        option_id="builtin_dining",
    )

    start = datetime(2026, 11, 16, 18, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 11, 16, 19, 30, 0, tzinfo=timezone.utc)
    idem_key = "idemp_test_tx_998877"

    # Initial call
    first_res = adapter.create_reservation(
        customer_name="Charlie Brown",
        customer_phone="+15557778888",
        party_size=3,
        start_time=start,
        end_time=end,
        idempotency_key=idem_key,
    )

    # Replay call with exact same idempotency_key
    replayed_res = adapter.create_reservation(
        customer_name="Charlie Brown",
        customer_phone="+15557778888",
        party_size=3,
        start_time=start,
        end_time=end,
        idempotency_key=idem_key,
    )

    assert first_res["booking_reference"] == replayed_res["booking_reference"]
    assert first_res["status"] == replayed_res["status"]

    # Verify only 1 reservation exists in database
    all_res = seeded_db_service.list_reservations("biz_test_restaurant")
    assert len(all_res) == 1


# ==============================================================================
# 7. Built-in Clinical Appointment Scheduling Tests
# ==============================================================================

def test_builtin_clinic_adapter_scheduling(seeded_db_service, monkeypatch):
    """Verify clinical adapter schedules consultations against registered suites."""
    from backend.database import service as db_mod
    monkeypatch.setattr(db_mod, "get_database_service", lambda: seeded_db_service)

    suite = seeded_db_service.create_resource(
        business_id="biz_test_clinic",
        name="Consultation Suite 1",
        capacity=1,
        min_party_size=1,
        max_party_size=2,
        resource_type="room",
        section="Level 1",
    )

    clinic_adapter = BuiltinClinicAdapter(
        business_id="biz_test_clinic",
        tool_id="create_appointment",
        option_id="builtin_clinic",
    )

    report = clinic_adapter.assess_readiness(seeded_db_service)
    assert report.is_ready is True
    assert report.status == CapabilityStatus.READY

    appt_start = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)
    appt_end = datetime(2026, 11, 18, 10, 30, 0, tzinfo=timezone.utc)

    booking = clinic_adapter.create_reservation(
        customer_name="David Miller",
        customer_phone="+15552223333",
        party_size=1,
        start_time=appt_start,
        end_time=appt_end,
        special_requests="Department: Dental Hygiene. Notes: Teeth cleaning",
    )

    assert booking["success"] is True
    assert booking["room_name"] == "Consultation Suite 1"
    assert booking["authoritative_source"] == "builtin_database"


# ==============================================================================
# 8. Google Calendar Adapter Validation Tests
# ==============================================================================

def test_google_calendar_adapter_validation():
    """Verify Google Calendar adapter validates service account json and permissions."""
    # 1. Missing credentials
    bad_adapter = GoogleCalendarAdapter(
        business_id="biz_test_clinic",
        tool_id="create_appointment",
        option_id="google_calendar",
        configuration={"calendar_id": "primary@example.com"},
        credentials={},
    )
    conn = bad_adapter.check_connection()
    assert conn["connected"] is False
    assert "missing" in conn["error"].lower()

    # 2. Valid mock service account
    mock_sa = {
        "type": "service_account",
        "project_id": "test-receptionist-proj",
        "client_email": "receptionist@test-receptionist-proj.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgk...\n-----END PRIVATE KEY-----\n",
    }
    good_adapter = GoogleCalendarAdapter(
        business_id="biz_test_clinic",
        tool_id="create_appointment",
        option_id="google_calendar",
        configuration={"calendar_id": "clinic-calendar@group.calendar.google.com"},
        credentials={"service_account_json": json.dumps(mock_sa)},
    )
    good_conn = good_adapter.check_connection()
    assert good_conn["connected"] is True
    assert good_conn["client_email"] == mock_sa["client_email"]

    perms = good_adapter.validate_permissions()
    assert perms["valid"] is True
    assert "https://www.googleapis.com/auth/calendar.events" in perms["scopes"]


# ==============================================================================
# 9. Tenant Isolation & Adapter Resolution Tests
# ==============================================================================

def test_adapter_resolution_tenant_isolation(seeded_db_service, monkeypatch):
    """Verify resolver chooses correct adapter based on tenant configuration."""
    from backend.database import service as db_mod
    monkeypatch.setattr(db_mod, "get_database_service", lambda: seeded_db_service)

    # 1. Restaurant resolves BuiltinDiningAdapter
    dining_adapter = resolve_tool_adapter("biz_test_restaurant", "create_table_booking", seeded_db_service)
    assert isinstance(dining_adapter, BuiltinDiningAdapter)

    # 2. Clinic resolves BuiltinClinicAdapter
    clinic_adapter = resolve_tool_adapter("biz_test_clinic", "create_appointment", seeded_db_service)
    assert isinstance(clinic_adapter, BuiltinClinicAdapter)

    # 3. Unconfigured arbitrary tool resolves UnconfiguredAdapter
    unconf = resolve_tool_adapter("biz_test_restaurant", "arbitrary_unconfigured_tool", seeded_db_service)
    assert isinstance(unconf, UnconfiguredAdapter)
    assert unconf.check_connection()["connected"] is False


# ==============================================================================
# 10. Capability Disconnection & Credential Purge Tests
# ==============================================================================

def test_capability_disconnection_and_purge(seeded_db_service):
    """Verify disconnecting integration purges credentials from vault and updates status."""
    wizard = CapabilitySetupWizard(seeded_db_service)

    # Save credentials in vault
    enc_blob, fp = encrypt_credentials({"api_token": "sec_sr_123456"})
    seeded_db_service.save_credential(
        business_id="biz_test_restaurant",
        tool_id="check_table_availability",
        provider_name="sevenrooms",
        encrypted_secrets=enc_blob,
        key_fingerprint=fp,
    )

    # Verify credential exists
    raw = seeded_db_service.get_credential_raw("biz_test_restaurant", "check_table_availability")
    assert raw is not None

    # Disconnect
    disc = wizard.disconnect_integration("biz_test_restaurant", "check_table_availability")
    assert disc["status"] == "disconnected"

    # Verify credentials purged
    raw_after = seeded_db_service.get_credential_raw("biz_test_restaurant", "check_table_availability")
    assert raw_after is None

    # Verify tool capability marked disconnected
    cfg = seeded_db_service.get_tool_config("biz_test_restaurant", "check_table_availability")
    assert cfg["status"] == "disconnected"
    assert cfg["is_enabled"] is False


# ==============================================================================
# 11. Runtime Execution Readiness Gating (Live vs Mock) Tests
# ==============================================================================

def test_runtime_execution_readiness_enforcement(seeded_db_service, monkeypatch):
    """Verify registry rejects live execution if tool capability status is not ready."""
    import backend.database.service as db_mod
    import backend.integrations.resolver as res_mod
    monkeypatch.setattr(db_mod, "get_database_service", lambda: seeded_db_service)
    monkeypatch.setattr(res_mod, "get_database_service", lambda: seeded_db_service)

    registry = build_default_tool_registry()

    # 1. Tool enabled but capability not marked ready in live mode -> UNAVAILABLE
    biz_config_unready = {
        "id": "biz_test_restaurant",
        "industry": "Restaurant",
        "execution_mode": "live",
        "enabled_tools": {"check_table_availability": True},
        "tool_configs": {
            "check_table_availability": {"status": "needs_input", "is_enabled": True}
        },
    }

    res_unready = registry.execute_tool(
        business_id="biz_test_restaurant",
        business_config=biz_config_unready,
        tool_id="check_table_availability",
        input_data={"date": "2026-11-20", "time": "19:00", "party_size": 2},
    )
    assert res_unready.status == ToolExecutionStatus.UNAVAILABLE
    assert res_unready.error_code == "LIVE_INTEGRATION_NOT_CONFIGURED"

    # 2. Tool capability status marked ready in live mode -> Executes live
    # Add table to inventory
    seeded_db_service.create_resource(
        business_id="biz_test_restaurant",
        name="Table Live 1",
        capacity=4,
        min_party_size=1,
        max_party_size=4,
    )

    biz_config_ready = {
        "id": "biz_test_restaurant",
        "name": "The Test Bistro",
        "industry": "Restaurant",
        "execution_mode": "live",
        "opening_time": "11:00",
        "closing_time": "23:00",
        "enabled_tools": {"check_table_availability": True},
        "tool_configs": {
            "check_table_availability": {"status": "ready", "is_enabled": True}
        },
    }

    res_ready = registry.execute_tool(
        business_id="biz_test_restaurant",
        business_config=biz_config_ready,
        tool_id="check_table_availability",
        input_data={"date": "2026-11-20", "time": "19:00", "party_size": 2},
    )
    assert res_ready.status == ToolExecutionStatus.SUCCESS
    assert res_ready.is_simulated is False
    assert res_ready.mode == ToolExecutionMode.LIVE
    assert "Tables are available" in res_ready.message


# ==============================================================================
# 12. End-to-End REST API Wizard Workflow Tests
# ==============================================================================

def test_e2e_capability_wizard_api(seeded_db_service, monkeypatch):
    """Verify complete end-to-end HTTP wizard workflow."""
    import backend.database.service as db_mod
    import backend.api.routers.capabilities as cap_mod
    import backend.capabilities.wizard as wiz_mod
    import backend.integrations.resolver as res_mod

    monkeypatch.setattr(db_mod, "get_database_service", lambda: seeded_db_service)
    monkeypatch.setattr(cap_mod, "get_database_service", lambda: seeded_db_service)
    monkeypatch.setattr(wiz_mod, "get_database_service", lambda: seeded_db_service)
    monkeypatch.setattr(res_mod, "get_database_service", lambda: seeded_db_service)
    monkeypatch.setattr(cap_mod, "get_setup_wizard", lambda: CapabilitySetupWizard(seeded_db_service))

    client = TestClient(app)

    # 1. GET /api/businesses/biz_test_restaurant/capabilities
    caps_resp = client.get("/api/businesses/biz_test_restaurant/capabilities")
    assert caps_resp.status_code == 200
    caps = caps_resp.json()
    assert any(c["tool_id"] == "check_table_availability" for c in caps)

    # 2. GET schema
    schema_resp = client.get("/api/businesses/biz_test_restaurant/capabilities/check_table_availability/schema")
    assert schema_resp.status_code == 200
    schema = schema_resp.json()
    assert schema["tool_id"] == "check_table_availability"

    # 3. POST start setup
    start_resp = client.post(
        "/api/businesses/biz_test_restaurant/capabilities/check_table_availability/setup/start",
        json={"option_id": "builtin_dining"},
    )
    assert start_resp.status_code == 200

    # 4. POST save step
    save_resp = client.post(
        "/api/businesses/biz_test_restaurant/capabilities/check_table_availability/setup/save",
        json={
            "step_name": "configuration",
            "data": {"reservation_duration_minutes": 90},
            "is_completed": True,
        },
    )
    assert save_resp.status_code == 200

    # 5. Add table resource
    add_res = client.post(
        "/api/businesses/biz_test_restaurant/resources",
        json={
            "name": "Bistro Table 1",
            "capacity": 4,
            "min_party_size": 1,
            "max_party_size": 4,
            "resource_type": "table",
            "section": "Dining Room",
        },
    )
    assert add_res.status_code == 200

    # 6. Validate setup
    val_resp = client.post("/api/businesses/biz_test_restaurant/capabilities/check_table_availability/setup/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["is_ready"] is True

    # 7. Activate capability
    act_resp = client.post("/api/businesses/biz_test_restaurant/capabilities/check_table_availability/activate")
    assert act_resp.status_code == 200
    assert act_resp.json()["success"] is True

    # 8. Test connection
    conn_resp = client.post("/api/businesses/biz_test_restaurant/capabilities/check_table_availability/test-connection")
    assert conn_resp.status_code == 200
    assert conn_resp.json()["connection"]["connected"] is True

    # 9. List resources
    res_list = client.get("/api/businesses/biz_test_restaurant/resources")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 10. Disconnect integration
    disc_resp = client.delete("/api/businesses/biz_test_restaurant/capabilities/check_table_availability/integration")
    assert disc_resp.status_code == 200
    assert disc_resp.json()["status"] == "disconnected"
