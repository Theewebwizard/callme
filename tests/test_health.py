"""
Unit tests for the FastAPI health check endpoint.
"""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_check_status_code():
    """Verify that the /health endpoint returns HTTP 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_response_body():
    """Verify that the /health endpoint returns the expected JSON structure."""
    response = client.get("/health")
    payload = response.json()

    assert payload.get("status") == "healthy"
    assert payload.get("app") == "AI Receptionist Platform"
    assert "version" in payload
    assert "environment" in payload
