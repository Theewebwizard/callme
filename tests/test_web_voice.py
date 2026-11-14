"""
Unit and integration tests for Browser Web Voice Calling endpoints:
- POST /api/voice/web/start
- POST /api/voice/web/turn (text & fallback)
- POST /api/voice/web/hangup
"""

import pytest
from starlette.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.database.service import get_database_service


@pytest.fixture
def client():
    return TestClient(app)


def test_web_voice_start_call(client):
    """POST /api/voice/web/start should initialize a valid voice session with greeting."""
    res = client.post("/api/voice/web/start", json={"business_id": "biz_spice_garden"})
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert data["session_id"].startswith("vses_") or data["session_id"].startswith("web_")
    assert data["business_id"] == "biz_spice_garden"
    assert "greeting_text" in data
    assert len(data["greeting_text"]) > 0


def test_web_voice_turn_with_text(client):
    """POST /api/voice/web/turn should process text turn and return receptionist answer."""
    # 1. Start session
    start_res = client.post("/api/voice/web/start", json={"business_id": "biz_spice_garden"})
    assert start_res.status_code == 200
    session_id = start_res.json()["session_id"]

    # 2. Send text turn
    turn_res = client.post(
        "/api/voice/web/turn",
        data={"session_id": session_id, "text": "What are your opening hours?"},
    )
    assert turn_res.status_code == 200
    turn_data = turn_res.json()
    assert turn_data["session_id"] == session_id
    assert turn_data["user_text"] == "What are your opening hours?"
    assert len(turn_data["assistant_text"]) > 0
    assert "should_terminate" in turn_data


def test_web_voice_turn_empty_text_fallback(client):
    """POST /api/voice/web/turn with empty text should return gentle fallback."""
    start_res = client.post("/api/voice/web/start", json={"business_id": "biz_spice_garden"})
    session_id = start_res.json()["session_id"]

    turn_res = client.post(
        "/api/voice/web/turn",
        data={"session_id": session_id, "text": ""},
    )
    assert turn_res.status_code == 200
    turn_data = turn_res.json()
    assert "didn't quite catch that" in turn_data["assistant_text"]


def test_web_voice_turn_invalid_session(client):
    """POST /api/voice/web/turn with invalid session should return 404."""
    turn_res = client.post(
        "/api/voice/web/turn",
        data={"session_id": "nonexistent_session_id_123", "text": "Hello"},
    )
    assert turn_res.status_code == 404


def test_web_voice_hangup(client):
    """POST /api/voice/web/hangup should terminate session."""
    start_res = client.post("/api/voice/web/start", json={"business_id": "biz_spice_garden"})
    session_id = start_res.json()["session_id"]

    hangup_res = client.post(
        "/api/voice/web/hangup",
        json={"session_id": session_id},
    )
    assert hangup_res.status_code == 200
    data = hangup_res.json()
    assert data["status"] == "terminated"
    assert data["session_id"] == session_id

