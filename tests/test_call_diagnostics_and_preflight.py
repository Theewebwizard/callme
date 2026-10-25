"""
Automated unit and integration tests for Step 9F: Call Diagnostics and Pre-Flight Gate.
Tests:
1. CallDiagnostics lifecycle tracking, timestamp recording, and identifier masking.
2. CallDiagnostics error recording and to_dict() sanitization (no raw transcripts/secrets).
3. PreFlightRunner execution, database/migration inspection, and tenant isolation validation.
4. PreFlightRunner missing secret and placeholder detection.
5. WebSocket integration verifying real-time diagnostic recording during media stream lifecycle.
"""

import json
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import Settings
from backend.voice.diagnostics import CallDiagnostics, mask_identifier
from backend.voice.preflight import PreFlightRunner
from backend.api.routers.voice import get_last_call_diagnostics


def test_call_diagnostics_lifecycle_and_masking():
    """Verify CallDiagnostics records complete call lifecycle with masked identifiers."""
    diag = CallDiagnostics()

    # 1. Connect & Auth
    diag.record_ws_connected()
    assert diag.ws_connected_at is not None
    assert diag.ws_authenticated is False

    diag.record_ws_authenticated(True)
    assert diag.ws_authenticated is True

    # 2. Start
    diag.record_start("CA1234567890abcdef", "MZ9876543210fedcba")
    assert diag.call_sid_masked == "CA12...cdef"
    assert diag.stream_sid_masked == "MZ98...dcba"

    # 3. Routing
    diag.record_routing(True, business_id="biz_spice_garden")
    assert diag.tenant_routing_status == "success"
    assert diag.business_id == "biz_spice_garden"

    # 4. Audio frames
    diag.record_audio_frame(320)
    assert diag.first_audio_received_at is not None
    assert diag.total_audio_frames == 1
    assert diag.total_audio_bytes == 320

    diag.record_audio_frame(640)
    assert diag.total_audio_frames == 2
    assert diag.total_audio_bytes == 960

    # 5. Transcript & LLM
    diag.record_final_transcript(confidence=0.96, char_count=35)
    assert diag.first_final_transcript_at is not None
    assert diag.turn_count == 1
    assert diag.last_speech_confidence == 0.96
    assert diag.last_speech_char_count == 35

    diag.record_llm_turn(duration_ms=145.2, tools_called=["check_table_availability"])
    assert diag.llm_duration_ms == 145.2

    # 6. TTS & Barge-In
    diag.record_tts_first_chunk(duration_ms=62.5, total_bytes=16000)
    assert diag.tts_duration_ms == 62.5
    assert diag.tts_first_chunk_sent_at is not None

    diag.record_barge_in()
    assert diag.barge_in_count == 1

    # 7. Termination
    diag.record_termination(persisted=True, reason="completed")
    assert diag.session_terminated_at is not None
    assert diag.session_persisted is True
    assert diag.termination_reason == "completed"

    # 8. Sanitized export
    dump = diag.to_dict()
    assert dump["call_sid_masked"] == "CA12...cdef"
    assert dump["barge_in_count"] == 1
    assert dump["session_persisted"] is True
    # Ensure no raw audio or transcript payload exists in export
    assert "audio" not in dump or dump.get("audio") is None
    assert "raw" not in dump


def test_call_diagnostics_error_paths():
    """Verify diagnostics record failed routing and short/empty identifier masking safely."""
    diag = CallDiagnostics()

    # Masking edge cases
    assert mask_identifier(None) == "[UNKNOWN]"
    assert mask_identifier("") == "[UNKNOWN]"
    assert mask_identifier("short") == "****"

    # Failed auth
    diag.record_ws_authenticated(False)
    assert diag.ws_authenticated is False

    # Failed routing
    diag.record_routing(False, error_code="TenantMismatch")
    assert diag.tenant_routing_status == "failed(TenantMismatch)"

    # Failed persistence on termination
    diag.record_termination(persisted=False, reason="error")
    assert diag.session_persisted is False
    assert diag.termination_reason == "error"


def test_preflight_runner_local_checks_pass(monkeypatch):
    """
    Verify PreFlightRunner passes when provided valid configuration,
    detecting Supabase persistence, migration 002, and test business isolation.
    """
    runner = PreFlightRunner(target_business_id="biz_spice_garden")

    # Mock settings with valid keys for testing
    monkeypatch.setattr(runner.settings, "GROQ_API_KEY", "gsk_test_mock_key")
    monkeypatch.setattr(runner.settings, "EXOTEL_ACCOUNT_SID", "AC_test_sid")
    monkeypatch.setattr(runner.settings, "EXOTEL_API_KEY", "exo_key_test")
    monkeypatch.setattr(runner.settings, "EXOTEL_API_TOKEN", "exo_token_test")
    monkeypatch.setattr(runner.settings, "EXOTEL_WEBHOOK_SECRET", "exo_secret_test")
    monkeypatch.setattr(runner.settings, "EXOTEL_STREAM_URL", "wss://api.example.com/api/voice/exotel/ws")
    monkeypatch.setattr(runner.settings, "DEEPGRAM_API_KEY", "dg_test_key")

    from contextlib import contextmanager
    from unittest.mock import MagicMock
    import backend.voice.preflight as pf_mod

    mock_db = MagicMock()
    mock_db.is_available.return_value = True
    mock_db.get_business_profile.return_value = {
        "id": "biz_spice_garden",
        "name": "Spice Garden Bistro",
        "assigned_number_status": "Active & Connected",
        "phone_number": "+918041235678",
        "enabled_tools": {
            "answer_faq": True,
            "check_table_availability": True,
            "create_table_booking": True,
            "check_appointment_availability": False,
            "create_appointment": False,
        },
    }
    mock_db.get_business_by_phone_number.return_value = {"id": "biz_spice_garden"}
    mock_db.get_all_businesses.return_value = {
        "biz_spice_garden": {"phone_number": "+918041235678"},
    }

    @contextmanager
    def mock_session_scope():
        sess = MagicMock()
        sess.execute.return_value.scalar.return_value = "005_password_auth"
        yield sess

    monkeypatch.setattr(pf_mod, "check_database_connection", lambda: {"connected": True, "dialect": "postgresql"})
    monkeypatch.setattr(pf_mod, "session_scope", mock_session_scope)
    monkeypatch.setattr(pf_mod, "get_database_service", lambda: mock_db)

    success = runner.run_all(test_live_apis=False)
    assert success is True

    # Confirm key checks were evaluated
    names = [r.name for r in runner.results]
    assert "Production Environment Secrets" in names
    assert "Supabase PostgreSQL Connectivity" in names
    assert "Alembic Migration Revision" in names
    assert "Test Business Active Status" in names
    assert "Unambiguous Phone Number Mapping" in names
    assert "Tool Scoping & Permission Boundary" in names
    assert "Production Mock Fallback Prohibition" in names


def test_preflight_runner_detects_missing_and_placeholder_secrets(monkeypatch):
    """Verify PreFlightRunner fails when secrets are missing or contain placeholder values."""
    runner = PreFlightRunner(target_business_id="biz_spice_garden")

    # Set placeholder in DATABASE_URL
    monkeypatch.setattr(runner.settings, "DATABASE_URL", "postgresql://postgres:[YOUR-PASSWORD]@localhost:5432/postgres")
    monkeypatch.setattr(runner.settings, "EXOTEL_API_KEY", None)

    runner._check_required_environment_variables()
    secret_check = [r for r in runner.results if r.name == "Production Environment Secrets"][0]
    assert secret_check.passed is False
    assert "EXOTEL_API_KEY" in secret_check.details
    assert "DATABASE_URL" in secret_check.details
    assert "Placeholder detected" in secret_check.details


def test_preflight_runner_detects_unknown_test_business():
    """Verify PreFlightRunner rejects non-existent test business ID."""
    runner = PreFlightRunner(target_business_id="biz_non_existent_tenant_999")
    runner._check_test_business_isolation()

    biz_check = [r for r in runner.results if r.name == "Test Business Profile"][0]
    assert biz_check.passed is False
    assert "not found in database" in biz_check.details


def test_websocket_stream_records_diagnostics(monkeypatch):
    """
    Verify that an Exotel WebSocket connection records live diagnostic events
    into the global diagnostics tracker.
    """
    client = TestClient(app)

    with client.websocket_connect("/api/voice/exotel/ws") as ws:
        # Start stream for Spice Garden
        ws.send_text(json.dumps({
            "event": "start",
            "start": {
                "stream_sid": "stream_diag_test_001",
                "call_sid": "call_diag_test_001",
                "to": "+91 80 4123 5678",
            }
        }))
        ws.receive_json()  # greeting media
        ws.receive_json()  # greeting mark

        # Send stop event
        ws.send_text(json.dumps({
            "event": "stop",
            "stream_sid": "stream_diag_test_001",
        }))

    # Verify diagnostics recorded
    diag = get_last_call_diagnostics()
    assert diag is not None
    assert diag.ws_connected_at is not None
    assert diag.ws_authenticated is True
    assert diag.call_sid_masked == "call..._001"
    assert diag.stream_sid_masked == "stre..._001"
    assert diag.tenant_routing_status == "success"
    assert diag.business_id == "biz_spice_garden"
    assert diag.session_terminated_at is not None
    assert diag.session_persisted is True
