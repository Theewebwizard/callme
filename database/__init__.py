"""
Database connection and data-access layer.

Re-exports core symbols from backend.database for clean root-level module access.
"""

from backend.database import (
    Base,
    Business,
    BusinessFAQ,
    BusinessToolConfig,
    CallRecord,
    ConversationMessage,
    PendingAction,
    create_database_engine,
    get_engine,
    get_session_factory,
    session_scope,
    check_database_connection,
    init_db_schema,
    DatabaseConnectionError,
    DatabaseConfigurationError,
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
    PendingActionRepository,
    DatabaseService,
    get_database_service,
    seed_database,
)

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
