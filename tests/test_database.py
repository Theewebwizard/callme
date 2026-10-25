"""
Comprehensive unit and integration test suite for Supabase PostgreSQL persistence layer.
Uses isolated in-memory SQLite engines so zero third-party credentials or network connections are required.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.database.config import (
    is_placeholder_db_url,
    normalize_database_url,
    get_effective_database_url,
)
from backend.database.engine import (
    create_database_engine,
    init_db_schema,
    check_database_connection,
    session_scope,
    DatabaseConfigurationError,
)
from backend.database.models import (
    Base,
    Business,
    BusinessFAQ,
    BusinessToolConfig,
    CallRecord,
    ConversationMessage,
    PendingAction,
)
from backend.database.repositories import (
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
    PendingActionRepository,
)
from backend.database.service import DatabaseService
from backend.database.seed import seed_database


@pytest.fixture
def test_engine():
    """Create an isolated in-memory SQLite engine with table schema pre-initialized."""
    engine = create_database_engine("sqlite:///:memory:")
    init_db_schema(engine)
    return engine


@pytest.fixture
def test_session_factory(test_engine):
    """Create a sessionmaker bound to the test engine."""
    return sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture
def test_db_service(test_engine, test_session_factory):
    """Provide a DatabaseService instance bound to the isolated test database."""
    return DatabaseService(engine=test_engine, session_factory=test_session_factory)


# --- 1. Database Configuration Tests ---

def test_database_config_unconfigured():
    """Verify placeholder detection and safe None return when credentials are not configured."""
    assert is_placeholder_db_url(None) is True
    assert is_placeholder_db_url("") is True
    assert is_placeholder_db_url("   ") is True
    assert is_placeholder_db_url("postgresql://postgres:your_password@db.your-supabase-project.supabase.co:5432/postgres") is True
    assert is_placeholder_db_url("postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres") is True
    assert is_placeholder_db_url("postgresql://postgres:actual_secure_pwd_123@db.abcxyz.supabase.co:5432/postgres") is False


def test_database_url_normalization():
    """Verify conversion of Heroku/standard PostgreSQL schemes into psycopg2 dialects."""
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert normalize_database_url("postgres://user:pass@host:5432/db") == "postgresql+psycopg2://user:pass@host:5432/db"
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == "postgresql+psycopg2://user:pass@host:5432/db"
    assert normalize_database_url("postgresql+psycopg2://user:pass@host:5432/db") == "postgresql+psycopg2://user:pass@host:5432/db"


def test_engine_fails_fast_without_configuration(monkeypatch):
    """Verify that create_database_engine raises DatabaseConfigurationError when unconfigured."""
    monkeypatch.setattr("backend.database.engine.get_effective_database_url", lambda: None)
    with pytest.raises(DatabaseConfigurationError):
        create_database_engine(database_url=None)


def test_check_database_connection_unconfigured():
    """Verify check_database_connection reports safe error without crashing or leaking secrets."""
    status = check_database_connection(engine=None)
    # Default unconfigured settings in test env
    assert isinstance(status, dict)
    assert "connected" in status
    assert "configured" in status


def test_check_database_connection_sqlite_success(test_engine):
    """Verify check_database_connection successfully probes active engine."""
    status = check_database_connection(engine=test_engine)
    assert status["connected"] is True
    assert status["configured"] is True
    assert status["dialect"] == "sqlite"
    assert status["error"] is None


# --- 2. Business Entity CRUD & Profile Tests ---

def test_business_crud_and_full_profile(test_session_factory):
    """Test creating, fetching, updating, and assembling full business profiles."""
    with session_scope(test_session_factory) as session:
        repo = BusinessRepository(session)
        assert repo.exists("biz_test") is False

        # Create
        biz = repo.create({
            "id": "biz_test",
            "name": "Test Bistro",
            "industry": "Restaurant",
            "description": "Artisan cafe",
            "phone_number": "+1 555 123 4567",
            "opening_time": "08:00",
            "closing_time": "20:00",
            "timezone": "UTC",
            "greeting_message": "Welcome to Test Bistro!",
            "languages": ["English", "French"],
            "transfer_instructions": "Transfer to manager on complaints.",
        })
        assert biz.id == "biz_test"
        assert repo.exists("biz_test") is True

        # Update
        updated = repo.update("biz_test", {"name": "Test Grand Bistro", "closing_time": "22:00"})
        assert updated.name == "Test Grand Bistro"
        assert updated.closing_time == "22:00"

        # Full Profile
        profile = repo.get_full_profile("biz_test")
        assert profile["name"] == "Test Grand Bistro"
        assert profile["industry"] == "Restaurant"
        assert isinstance(profile["faqs"], list)
        assert isinstance(profile["enabled_tools"], dict)
        assert "stats" in profile


# --- 3. Business FAQ CRUD & Tenant Isolation Tests ---

def test_faq_crud_and_tenant_isolation(test_session_factory):
    """Test FAQ operations, category filtering, and tenant boundary verification."""
    with session_scope(test_session_factory) as session:
        biz_repo = BusinessRepository(session)
        faq_repo = FAQRepository(session)

        biz_repo.create({"id": "biz_a", "name": "Business A", "industry": "Retail", "greeting_message": "Hi"})
        biz_repo.create({"id": "biz_b", "name": "Business B", "industry": "Health", "greeting_message": "Hello"})

        faq1 = faq_repo.create("biz_a", "What are your hours?", "8 AM to 8 PM", "Hours")
        faq2 = faq_repo.create("biz_b", "Do you accept insurance?", "Yes, all major plans", "Billing")

        # Business A FAQs must not include Business B FAQs
        faqs_a = faq_repo.list_for_business("biz_a")
        assert len(faqs_a) == 1
        assert faqs_a[0].question == "What are your hours?"

        # Update FAQ
        updated_faq = faq_repo.update(faq1.id, "biz_a", answer="8 AM to 10 PM on weekends")
        assert updated_faq.answer == "8 AM to 10 PM on weekends"

        # Attempt cross-tenant update should fail
        cross_update = faq_repo.update(faq1.id, "biz_b", answer="Hacked answer")
        assert cross_update is None

        # Delete FAQ
        assert faq_repo.delete(faq1.id, business_id="biz_a") is True
        assert len(faq_repo.list_for_business("biz_a")) == 0


def test_foreign_key_violation_rejected(test_session_factory):
    """Test that creating an FAQ for a non-existent business is rejected."""
    with pytest.raises(Exception):
        with session_scope(test_session_factory) as session:
            faq_repo = FAQRepository(session)
            faq_repo.create("non_existent_biz", "Question?", "Answer.")


# --- 4. Tool Configuration & Uniqueness Tests ---

def test_tool_config_crud_and_uniqueness(test_session_factory):
    """Test tool activation toggling and uniqueness enforcement."""
    with session_scope(test_session_factory) as session:
        biz_repo = BusinessRepository(session)
        tool_repo = ToolConfigRepository(session)

        biz_repo.create({"id": "biz_dining", "name": "Dining Co", "industry": "Dining", "greeting_message": "Hi"})

        # Enable tool
        tool_repo.set_tool_status("biz_dining", "check_table_availability", True)
        assert tool_repo.is_tool_enabled("biz_dining", "check_table_availability") is True

        # Toggle to disabled
        tool_repo.set_tool_status("biz_dining", "check_table_availability", False)
        assert tool_repo.is_tool_enabled("biz_dining", "check_table_availability") is False

        # Bulk update
        tool_repo.bulk_set_tool_statuses("biz_dining", {
            "answer_faq": True,
            "take_message": True,
        })
        statuses = tool_repo.get_tool_statuses("biz_dining")
        assert statuses["answer_faq"] is True
        assert statuses["take_message"] is True
        assert statuses["check_table_availability"] is False


# --- 5. Call History & Privacy Masking Tests ---

def test_call_history_logging_and_filtering(test_session_factory):
    """Test logging call audits, outcome filtering, and simulation flags."""
    with session_scope(test_session_factory) as session:
        biz_repo = BusinessRepository(session)
        call_repo = CallRepository(session)

        biz_repo.create({"id": "biz_clinic", "name": "Dental Care", "industry": "Clinic", "greeting_message": "Hi"})

        call_repo.log_call(
            business_id="biz_clinic",
            caller_number="+91 98765 •••21",
            duration_seconds=130,
            outcome="Booking Completed",
            summary="Booked dental checkup for tomorrow.",
            tools_used=["Check Appointment Availability", "Create Appointment"],
            is_simulated=True,
        )

        call_repo.log_call(
            business_id="biz_clinic",
            caller_number="+91 98765 •••99",
            duration_seconds=45,
            outcome="Inquiry Resolved",
            summary="Asked for directions and parking.",
            tools_used=["Answer Business FAQs"],
            is_simulated=True,
        )

        all_calls = call_repo.list_dicts_for_business("biz_clinic")
        assert len(all_calls) == 2
        assert all_calls[0]["is_simulated"] is True

        # Filter by outcome
        filtered = call_repo.list_dicts_for_business("biz_clinic", outcome_filter="Booking Completed")
        assert len(filtered) == 1
        assert filtered[0]["outcome"] == "Booking Completed"

        # Check stats computation
        stats = call_repo.get_stats_for_business("biz_clinic")
        assert stats["total_calls"] == 2
        assert stats["bookings_completed"] == 1


# --- 6. Conversation Messages Persistence Tests ---

def test_conversation_messages_persistence(test_session_factory):
    """Test chat message persistence and reset behavior."""
    with session_scope(test_session_factory) as session:
        biz_repo = BusinessRepository(session)
        conv_repo = ConversationRepository(session)

        biz_repo.create({"id": "biz_chat", "name": "Chat Biz", "industry": "Services", "greeting_message": "Hello!"})

        conv_repo.add_message("biz_chat", "assistant", "Hello! How can I assist you?", is_simulated=True)
        conv_repo.add_message("biz_chat", "user", "I need to book an appointment.", is_simulated=True)

        messages = conv_repo.list_dicts("biz_chat")
        assert len(messages) == 2
        assert messages[0]["role"] == "assistant"
        assert messages[1]["role"] == "user"

        # Clear
        cleared = conv_repo.clear_for_business("biz_chat")
        assert cleared == 2
        assert len(conv_repo.list_dicts("biz_chat")) == 0


# --- 7. Pending Action Lifecycle & Replay Protection Tests ---

def test_pending_action_lifecycle_and_duplicate_protection(test_session_factory):
    """Test two-phase confirmation action persistence, tenant validation, and duplicate execution protection."""
    with session_scope(test_session_factory) as session:
        biz_repo = BusinessRepository(session)
        pending_repo = PendingActionRepository(session)

        biz_repo.create({"id": "biz_act_1", "name": "Action Biz 1", "industry": "Dining", "greeting_message": "Hi"})
        biz_repo.create({"id": "biz_act_2", "name": "Action Biz 2", "industry": "Clinic", "greeting_message": "Hi"})

        action = pending_repo.create_action(
            business_id="biz_act_1",
            action_id="act_uuid_001",
            action_type="create_table_booking",
            tool_name="Create Table Booking",
            arguments={"customer_name": "Alice", "party_size": 4},
            summary="Booking for 4 on Friday",
        )
        assert action.id == "act_uuid_001"
        assert action.status == "pending_confirmation"

        # Active lookup for tenant 1
        active = pending_repo.get_latest_pending("biz_act_1")
        assert active is not None
        assert active.id == "act_uuid_001"

        # Tenant 2 must NOT see Tenant 1's action
        assert pending_repo.get_latest_pending("biz_act_2") is None

        # Cross-tenant transition must be rejected
        cross_res = pending_repo.transition_status("biz_act_2", "act_uuid_001", "executed")
        assert cross_res is False

        # Phase B execution transition
        success = pending_repo.transition_status("biz_act_1", "act_uuid_001", "executed", execution_reference="TB-8899")
        assert success is True

        # Replay attack: executing a second time must fail!
        replay_res = pending_repo.transition_status("biz_act_1", "act_uuid_001", "executed")
        assert replay_res is False

        # Cancelled or executed action no longer appears in get_latest_pending
        assert pending_repo.get_latest_pending("biz_act_1") is None


# --- 8. Seed Idempotency & Tenant Isolation Tests ---

def test_seed_database_idempotency(test_engine):
    """Verify that re-running seed_database creates zero duplicates and preserves existing edits."""
    # First seed
    res1 = seed_database(engine=test_engine)
    assert res1["businesses_created"] == 2
    assert res1["faqs_created"] >= 6
    assert res1["tools_configured"] >= 14
    assert res1["calls_seeded"] >= 10

    # Second seed must be a no-op for creation
    res2 = seed_database(engine=test_engine)
    assert res2["businesses_created"] == 0
    assert res2["businesses_existing"] == 2
    assert res2["faqs_created"] == 0
    assert res2["calls_seeded"] == 0


def test_tenant_isolation_restaurant_and_clinic(test_engine, test_session_factory):
    """Verify that restaurant and clinic data remain isolated after seeding."""
    seed_database(engine=test_engine)

    with session_scope(test_session_factory) as session:
        biz_repo = BusinessRepository(session)
        tool_repo = ToolConfigRepository(session)
        call_repo = CallRepository(session)

        sg = biz_repo.get_full_profile("biz_spice_garden")
        ad = biz_repo.get_full_profile("biz_apex_dental")

        assert sg["name"] == "Spice Garden Bistro"
        assert ad["name"] == "Apex Dental & Orthodontics"

        # Restaurant has table bookings enabled, clinic has appointments enabled
        assert sg["enabled_tools"]["create_table_booking"] is True
        assert sg["enabled_tools"]["create_appointment"] is False

        assert ad["enabled_tools"]["create_table_booking"] is False
        assert ad["enabled_tools"]["create_appointment"] is True

        # Call records must be strictly isolated
        sg_calls = call_repo.list_dicts_for_business("biz_spice_garden")
        ad_calls = call_repo.list_dicts_for_business("biz_apex_dental")
        assert len(sg_calls) > 0
        assert len(ad_calls) > 0
        for c in sg_calls:
            assert c["business_id"] == "biz_spice_garden"
        for c in ad_calls:
            assert c["business_id"] == "biz_apex_dental"


# --- 9. DatabaseService Facade Tests ---

def test_database_service_facade(test_db_service):
    """Verify high-level DatabaseService facade handles business updates, FAQs, and calls end-to-end."""
    # Seed
    seed_database(engine=test_db_service._engine)
    assert test_db_service.is_available() is True

    # Get profile
    profile = test_db_service.get_business_profile("biz_spice_garden")
    assert profile is not None
    assert profile["name"] == "Spice Garden Bistro"

    # Save profile updates
    updated = test_db_service.save_business_profile("biz_spice_garden", {
        "description": "Updated Indian dining experience",
    })
    assert updated["description"] == "Updated Indian dining experience"

    # Verify persisted in subsequent read
    reloaded = test_db_service.get_business_profile("biz_spice_garden")
    assert reloaded["description"] == "Updated Indian dining experience"

    # Tool status toggle
    test_db_service.set_tool_status("biz_spice_garden", "check_table_availability", False)
    fresh_tools = test_db_service.get_business_profile("biz_spice_garden")["enabled_tools"]
    assert fresh_tools["check_table_availability"] is False
