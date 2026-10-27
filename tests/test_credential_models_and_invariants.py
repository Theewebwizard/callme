"""
Unit and invariant tests for Phase 1: Credential models, database schema, and repository invariants.
Verifies multi-account connection management, single-default invariants, partial indexes,
and distributed refresh leases with fencing token CAS semantics.
"""

from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from backend.database.engine import init_db_schema
from backend.database.models import (
    Base,
    Business,
    IntegrationConnection,
    IntegrationCredential,
    utcnow,
)
from backend.database.service import DatabaseService
from backend.database.repositories.connection_repo import ConnectionRepository
from backend.database.repositories.tool_config_repo import ToolConfigRepository


@pytest.fixture
def clean_db_service():
    """Create isolated SQLite database with fresh schema for Phase 1 tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(engine)
    service = DatabaseService(engine=engine)
    # Create test business tenant
    service.create_business({
        "id": "biz_clinic_apex",
        "name": "Apex Dental Clinic",
        "industry": "Clinic",
        "phone_number": "+15551234567",
        "opening_time": "09:00",
        "closing_time": "18:00",
        "timezone": "UTC",
    })
    service.create_business({
        "id": "biz_dining_spice",
        "name": "Spice Garden",
        "industry": "Restaurant",
        "phone_number": "+15559876543",
        "opening_time": "11:00",
        "closing_time": "23:00",
        "timezone": "UTC",
    })
    return service


# ==============================================================================
# 1. Multi-Account Connection Creation and Serialization
# ==============================================================================

def test_create_and_serialize_connection(clean_db_service):
    """Verify connection creation, default values, and to_dict serialization."""
    conn = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="dr-smith-calendar",
        external_account_id="dr.smith@apex.com",
        display_label="Dr. Smith (Operatory 1)",
        is_default=True,
        metadata={"calendar_id": "c_primary_123"},
    )
    assert conn["id"].startswith("conn_")
    assert conn["business_id"] == "biz_clinic_apex"
    assert conn["provider_id"] == "google_calendar"
    assert conn["connection_slug"] == "dr-smith-calendar"
    assert conn["external_account_id"] == "dr.smith@apex.com"
    assert conn["display_label"] == "Dr. Smith (Operatory 1)"
    assert conn["is_default"] is True
    assert conn["status"] == "active"
    assert conn["metadata"]["calendar_id"] == "c_primary_123"
    assert conn["created_at"] is not None
    assert conn["updated_at"] is not None


def test_list_and_get_connections_with_tenant_isolation(clean_db_service):
    """Verify connections are strictly isolated by business tenant."""
    c1 = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="smith",
    )
    c2 = clean_db_service.create_connection(
        business_id="biz_dining_spice",
        provider_id="sevenrooms",
        connection_slug="main",
    )

    # Scoped retrieval
    assert clean_db_service.get_connection(c1["id"], business_id="biz_clinic_apex") is not None
    assert clean_db_service.get_connection(c1["id"], business_id="biz_dining_spice") is None

    # List scoping
    apex_conns = clean_db_service.list_connections("biz_clinic_apex")
    assert len(apex_conns) == 1
    assert apex_conns[0]["id"] == c1["id"]

    spice_conns = clean_db_service.list_connections("biz_dining_spice")
    assert len(spice_conns) == 1
    assert spice_conns[0]["id"] == c2["id"]


# ==============================================================================
# 2. Connection Uniqueness Invariants & Partial Indexes
# ==============================================================================

def test_connection_slug_uniqueness_per_tenant_and_provider(clean_db_service):
    """Verify (business_id, provider_id, connection_slug) is strictly unique."""
    clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="operatory-1",
    )

    # Same business + provider + slug fails
    with pytest.raises(IntegrityError):
        clean_db_service.create_connection(
            business_id="biz_clinic_apex",
            provider_id="google_calendar",
            connection_slug="operatory-1",
        )

    # Different provider with same slug succeeds
    conn_outlook = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="outlook_calendar",
        connection_slug="operatory-1",
    )
    assert conn_outlook["provider_id"] == "outlook_calendar"

    # Different tenant with same slug succeeds
    conn_spice = clean_db_service.create_connection(
        business_id="biz_dining_spice",
        provider_id="google_calendar",
        connection_slug="operatory-1",
    )
    assert conn_spice["business_id"] == "biz_dining_spice"


def test_external_account_id_partial_unique_index(clean_db_service):
    """
    Verify partial unique index on external_account_id:
    - Multiple connections with external_account_id=None are allowed.
    - Duplicate non-NULL external_account_id under same tenant/provider raises IntegrityError.
    """
    # 1. Multiple NULL external_account_ids succeed
    c1 = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="webhook_service",
        connection_slug="hook-1",
        external_account_id=None,
    )
    c2 = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="webhook_service",
        connection_slug="hook-2",
        external_account_id=None,
    )
    assert c1["id"] != c2["id"]

    # 2. Non-null external_account_id enforces uniqueness
    clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="dr-smith",
        external_account_id="dr.smith@apex.com",
    )
    with pytest.raises(IntegrityError):
        clean_db_service.create_connection(
            business_id="biz_clinic_apex",
            provider_id="google_calendar",
            connection_slug="dr-smith-duplicate-alias",
            external_account_id="dr.smith@apex.com",
        )


def test_single_default_connection_invariant(clean_db_service):
    """Verify single-default invariant: setting new default automatically clears old default."""
    # 1. Create first connection as default
    c1 = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="primary",
        is_default=True,
    )
    assert clean_db_service.get_default_connection("biz_clinic_apex", "google_calendar")["id"] == c1["id"]

    # 2. Create second connection as default -> c1 is automatically unset
    c2 = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="secondary",
        is_default=True,
    )
    assert clean_db_service.get_default_connection("biz_clinic_apex", "google_calendar")["id"] == c2["id"]
    assert clean_db_service.get_connection(c1["id"])["is_default"] is False

    # 3. Promote c1 back to default via set_default_connection()
    success = clean_db_service.set_default_connection("biz_clinic_apex", "google_calendar", c1["id"])
    assert success is True
    assert clean_db_service.get_default_connection("biz_clinic_apex", "google_calendar")["id"] == c1["id"]
    assert clean_db_service.get_connection(c2["id"])["is_default"] is False


def test_database_enforced_single_default_partial_index(clean_db_service):
    """Verify database-level partial unique index blocks concurrent bypass attempts."""
    clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="google_calendar",
        connection_slug="c1",
        is_default=True,
    )

    # Attempt to bypass repository logic by directly inserting a second row with is_default=True
    with pytest.raises(IntegrityError):
        with clean_db_service.session_factory() as session:
            session.add(IntegrationConnection(
                id="conn_bypass_attempt",
                business_id="biz_clinic_apex",
                provider_id="google_calendar",
                connection_slug="c2",
                is_default=True,
            ))
            session.commit()


# ==============================================================================
# 3. Distributed Refresh Lease & Fencing Token Invariants
# ==============================================================================

def test_refresh_lease_acquisition_and_fencing_token_increment(clean_db_service):
    """Verify atomic CAS lease acquisition increments fencing token."""
    # Create credential record
    cred = clean_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets="mock_encrypted_v1_payload",
        key_fingerprint="fp_test_1234",
    )
    cred_id = cred["id"]
    assert cred["fencing_token"] == 0

    # Worker 1 acquires lease
    token1 = clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_alpha",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )
    assert token1 == 1

    # Raw inspection
    raw = clean_db_service.get_credential_raw("biz_clinic_apex", "check_appointment_availability")
    assert raw["fencing_token"] == 1


def test_refresh_lease_collision_prevention(clean_db_service):
    """Verify second worker cannot acquire an active, unexpired lease."""
    cred = clean_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets="payload",
        key_fingerprint="fp_123",
    )
    cred_id = cred["id"]

    # Worker Alpha acquires 30s lease
    token_a = clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_alpha",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )
    assert token_a is not None

    # Worker Beta attempts acquisition while Alpha holds lease -> blocked!
    token_b = clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_beta",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )
    assert token_b is None


def test_refresh_lease_expiry_recovery(clean_db_service):
    """Verify second worker can acquire lease once TTL expires."""
    cred = clean_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets="payload",
        key_fingerprint="fp_123",
    )
    cred_id = cred["id"]

    # Worker Alpha acquires lease with expired TTL (simulated by setting lease_expires_at in past)
    with clean_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred_id)
        c.lease_owner_id = "worker_alpha"
        c.lease_expires_at = utcnow() - timedelta(seconds=5)
        c.fencing_token = 1
        session.commit()

    # Worker Beta attempts acquisition -> succeeds because Alpha's lease expired!
    token_b = clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_beta",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )
    assert token_b == 2


def test_stale_worker_commit_rejected_by_fencing_token(clean_db_service):
    """
    Verify anti-zombie fencing token protection:
    If Worker A's lease expires and Worker B acquires it, Worker A's late commit is rejected.
    """
    cred = clean_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets="initial_payload",
        key_fingerprint="fp_000",
    )
    cred_id = cred["id"]

    # 1. Worker A acquires lease (fencing=1)
    token_a = clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_alpha",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )
    assert token_a == 1

    # 2. Worker A stalls; lease expires; Worker B acquires lease (fencing=2)
    with clean_db_service.session_factory() as session:
        c = session.get(IntegrationCredential, cred_id)
        c.lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    token_b = clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_beta",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )
    assert token_b == 2

    # 3. Worker B finishes and commits Token B
    committed_b = clean_db_service.commit_refreshed_credentials(
        cred_id=cred_id,
        worker_id="worker_beta",
        acquired_fencing_token=token_b,
        new_encrypted_secrets="token_b_secrets",
        business_id="biz_clinic_apex",
    )
    assert committed_b is True

    # 4. Worker A wakes up and attempts to commit Token A with stale fencing=1 -> REJECTED!
    committed_a = clean_db_service.commit_refreshed_credentials(
        cred_id=cred_id,
        worker_id="worker_alpha",
        acquired_fencing_token=token_a,
        new_encrypted_secrets="token_a_stale_secrets",
        business_id="biz_clinic_apex",
    )
    assert committed_a is False

    # 5. Database contains Token B, not stale Token A
    raw = clean_db_service.get_credential_raw("biz_clinic_apex", "check_appointment_availability")
    assert raw["encrypted_secrets"] == "token_b_secrets"


def test_cross_worker_lease_release_prevention(clean_db_service):
    """Verify Worker A cannot release a lease owned by Worker B."""
    cred = clean_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="google_calendar",
        encrypted_secrets="payload",
        key_fingerprint="fp_123",
    )
    cred_id = cred["id"]

    # Worker Beta acquires lease
    clean_db_service.acquire_refresh_lease(
        cred_id,
        worker_id="worker_beta",
        ttl_seconds=30,
        business_id="biz_clinic_apex",
    )

    # Worker Alpha attempts to release -> fails!
    released_a = clean_db_service.release_refresh_lease(
        cred_id,
        worker_id="worker_alpha",
        business_id="biz_clinic_apex",
    )
    assert released_a is False

    # Worker Beta releases own lease -> succeeds!
    released_b = clean_db_service.release_refresh_lease(
        cred_id,
        worker_id="worker_beta",
        business_id="biz_clinic_apex",
    )
    assert released_b is True


# ==============================================================================
# 4. Backward Compatibility and Credential Linking
# ==============================================================================

def test_legacy_credentials_without_connection_id_work(clean_db_service):
    """Verify credentials created without connection_id maintain backward compatibility."""
    cred = clean_db_service.save_credential(
        business_id="biz_clinic_apex",
        tool_id="check_appointment_availability",
        option_id="builtin_clinic",
        encrypted_secrets="legacy_payload",
        key_fingerprint="fp_legacy",
    )
    raw = clean_db_service.get_credential_raw("biz_clinic_apex", "check_appointment_availability")
    assert raw["connection_id"] is None
    assert raw["schema_version"] == 1
    assert raw["fencing_token"] == 0

    # Link to a newly created connection
    conn = clean_db_service.create_connection(
        business_id="biz_clinic_apex",
        provider_id="builtin_clinic",
        connection_slug="default",
    )
    linked = clean_db_service.link_credential_to_connection(cred["id"], conn["id"])
    assert linked is True

    raw_after = clean_db_service.get_credential_raw("biz_clinic_apex", "check_appointment_availability")
    assert raw_after["connection_id"] == conn["id"]
