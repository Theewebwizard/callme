"""
Global pytest configuration and fixtures.
Ensures automated test suites run strictly in an isolated test environment
and never connect to or mutate the live production database.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.config import get_settings
from backend.database.engine import (
    _ENGINE_CACHE,
    _SESSION_FACTORY_CACHE,
    init_db_schema,
    create_database_engine,
)
from backend.database.seed import seed_database
import backend.database.service as db_service_mod


@pytest.fixture(scope="function", autouse=True)
def isolate_test_database():
    """
    Function-scoped fixture ensuring every automated test runs against a fresh,
    isolated in-memory SQLite database and never makes remote network calls to production.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db_schema(test_engine)
    seed_database(engine=test_engine)

    test_service = db_service_mod.DatabaseService(engine=test_engine)
    original_service = db_service_mod._DEFAULT_SERVICE
    db_service_mod._DEFAULT_SERVICE = test_service

    yield test_service

    from backend.voice.session_manager import flush_voice_background_tasks
    flush_voice_background_tasks(wait=True)

    db_service_mod._DEFAULT_SERVICE = original_service
    test_engine.dispose()
