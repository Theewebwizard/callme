"""
Database persistence package for Supabase PostgreSQL.
Exports ORM models, session management, repositories, services, and seeder.
"""

from backend.database.models import (
    Base,
    Business,
    BusinessFAQ,
    BusinessToolConfig,
    CallRecord,
    ConversationMessage,
    PendingAction,
)
from backend.database.engine import (
    create_database_engine,
    get_engine,
    get_session_factory,
    session_scope,
    check_database_connection,
    init_db_schema,
    DatabaseConnectionError,
    DatabaseConfigurationError,
)
from backend.database.repositories import (
    BaseRepository,
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
    PendingActionRepository,
)
from backend.database.service import (
    DatabaseService,
    get_database_service,
)
from backend.database.seed import seed_database

__all__ = [
    "Base",
    "Business",
    "BusinessFAQ",
    "BusinessToolConfig",
    "CallRecord",
    "ConversationMessage",
    "PendingAction",
    "create_database_engine",
    "get_engine",
    "get_session_factory",
    "session_scope",
    "check_database_connection",
    "init_db_schema",
    "DatabaseConnectionError",
    "DatabaseConfigurationError",
    "BaseRepository",
    "BusinessRepository",
    "FAQRepository",
    "ToolConfigRepository",
    "CallRepository",
    "ConversationRepository",
    "PendingActionRepository",
    "DatabaseService",
    "get_database_service",
    "seed_database",
]
