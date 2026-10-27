"""
SQLAlchemy database engine and session management.
Provides connection pooling, lifecycle management, and connection health probing.
"""

from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any
import logging

from sqlalchemy import create_engine, Engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from backend.database.config import get_effective_database_url
from backend.database.models import Base

logger = logging.getLogger(__name__)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints for SQLite connections."""
    conn_type = type(dbapi_connection).__module__
    if "sqlite" in conn_type:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()



class DatabaseConfigurationError(Exception):
    """Raised when database operations are attempted without a valid configuration."""
    pass


class DatabaseConnectionError(Exception):
    """Raised when establishing a connection to the database fails."""
    pass


_ENGINE_CACHE: Dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: Dict[str, sessionmaker] = {}


def create_database_engine(
    database_url: Optional[str] = None,
    is_test: bool = False,
    echo: bool = False,
) -> Engine:
    """
    Factory creating a robust SQLAlchemy engine with connection pooling and timeouts.
    Supports PostgreSQL (Supabase) and SQLite (in-memory for tests).
    """
    url = database_url or get_effective_database_url()
    if not url:
        raise DatabaseConfigurationError(
            "DATABASE_URL is not configured. Please configure DATABASE_URL in your .env file "
            "or provide an explicit database URL."
        )

    if url.startswith("sqlite"):
        # SQLite configuration for testing and offline local development
        if ":memory:" in url:
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=echo,
            )
        else:
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                echo=echo,
            )
    else:
        # PostgreSQL / Supabase production configuration
        engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,  # Recycle connections after 30 minutes
            pool_pre_ping=False,  # Avoid adding 400-500ms roundtrip ping on every connection checkout
            echo=echo,
        )

    return engine


def get_engine(database_url: Optional[str] = None) -> Engine:
    """Retrieve or initialize singleton engine for the given URL."""
    url = database_url or get_effective_database_url()
    if not url:
        raise DatabaseConfigurationError("No valid DATABASE_URL configured.")
    
    if url not in _ENGINE_CACHE:
        _ENGINE_CACHE[url] = create_database_engine(database_url=url)
    return _ENGINE_CACHE[url]


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker:
    """Retrieve or create sessionmaker for the specified engine."""
    eng = engine or get_engine()
    cache_key = id(eng)
    if cache_key not in _SESSION_FACTORY_CACHE:
        _SESSION_FACTORY_CACHE[cache_key] = sessionmaker(
            bind=eng,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SESSION_FACTORY_CACHE[cache_key]


@contextmanager
def session_scope(
    session_factory: Optional[sessionmaker] = None,
    engine: Optional[Engine] = None,
) -> Generator[Session, None, None]:
    """
    Context manager for transactional database sessions.
    Automatically commits on clean exit, rolls back on exception, and reliably closes session.
    """
    factory = session_factory or get_session_factory(engine=engine)
    session: Session = factory()
    try:
        yield session
        if session.in_transaction():
            try:
                session.commit()
            except Exception as commit_err:
                if 'no transaction is active' not in str(commit_err).lower():
                    raise
    except Exception as exc:
        if session.in_transaction():
            try:
                session.rollback()
            except Exception:
                pass
        logger.error(f"Database session rolled back due to error: {exc}")
        raise
    finally:
        session.close()


import time
import threading

_DB_CONN_CACHE: Dict[str, Any] = {"result": None, "timestamp": 0.0}
_DB_CONN_CACHE_LOCK = threading.Lock()
_DB_CONN_CACHE_TTL = 30.0  # 30-second TTL cache for remote database probes


def check_database_connection(engine: Optional[Engine] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Probe database connectivity and return structured health status.
    Uses a 30-second thread-safe in-memory cache to prevent redundant remote DB probes.
    Never exposes passwords or sensitive credentials in error messages.
    """
    if engine is None and not force_refresh:
        now = time.time()
        with _DB_CONN_CACHE_LOCK:
            if _DB_CONN_CACHE["result"] is not None and (now - _DB_CONN_CACHE["timestamp"]) < _DB_CONN_CACHE_TTL:
                return _DB_CONN_CACHE["result"].copy()

    try:
        eng = engine or get_engine()
    except DatabaseConfigurationError as cfg_err:
        return {
            "connected": False,
            "configured": False,
            "dialect": None,
            "error": str(cfg_err),
        }
    except Exception as exc:
        return {
            "connected": False,
            "configured": False,
            "dialect": None,
            "error": f"Failed to initialize engine: {type(exc).__name__}",
        }

    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        res = {
            "connected": True,
            "configured": True,
            "dialect": eng.dialect.name,
            "error": None,
        }
        if engine is None:
            with _DB_CONN_CACHE_LOCK:
                _DB_CONN_CACHE["result"] = res
                _DB_CONN_CACHE["timestamp"] = time.time()
        return res
    except OperationalError as op_err:
        logger.warning(f"Database connectivity test failed: {op_err}")
        return {
            "connected": False,
            "configured": True,
            "dialect": eng.dialect.name,
            "error": "Database server unreachable or credentials rejected.",
        }
    except Exception as exc:
        logger.warning(f"Unexpected database probe error: {exc}")
        return {
            "connected": False,
            "configured": True,
            "dialect": eng.dialect.name,
            "error": f"{type(exc).__name__}: Connection probe failed.",
        }


def migrate_schema_columns(engine: Engine) -> None:
    """
    Safely apply non-destructive schema column migrations for local/test SQLite databases.
    PostgreSQL schema migrations are strictly managed authoritatively by Alembic version scripts
    to prevent unconstrained raw DDL and schema drift.
    """
    dialect = engine.dialect.name
    if dialect != "sqlite":
        logger.info(
            "Skipping dynamic schema column alteration for '%s' dialect; migrations are managed authoritatively by Alembic.",
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            res = conn.execute(text("PRAGMA table_info(business_tool_configs);")).fetchall()
            existing_cols = {row[1] for row in res}
            if existing_cols:
                if "status" not in existing_cols:
                    conn.execute(text("ALTER TABLE business_tool_configs ADD COLUMN status VARCHAR(50) DEFAULT 'not_configured';"))
                if "selected_option_id" not in existing_cols:
                    conn.execute(text("ALTER TABLE business_tool_configs ADD COLUMN selected_option_id VARCHAR(100);"))
                if "configuration" not in existing_cols:
                    conn.execute(text("ALTER TABLE business_tool_configs ADD COLUMN configuration JSON DEFAULT '{}';"))
                if "readiness_details" not in existing_cols:
                    conn.execute(text("ALTER TABLE business_tool_configs ADD COLUMN readiness_details JSON DEFAULT '{}';"))
                if "last_validated_at" not in existing_cols:
                    conn.execute(text("ALTER TABLE business_tool_configs ADD COLUMN last_validated_at DATETIME;"))
            res_res = conn.execute(text("PRAGMA table_info(reservations);")).fetchall()
            existing_res_cols = {row[1] for row in res_res}
            if existing_res_cols:
                if "hold_expires_at" not in existing_res_cols:
                    conn.execute(text("ALTER TABLE reservations ADD COLUMN hold_expires_at DATETIME;"))
                if "rescheduled_from_id" not in existing_res_cols:
                    conn.execute(text("ALTER TABLE reservations ADD COLUMN rescheduled_from_id VARCHAR(64);"))
                if "metadata_json" not in existing_res_cols:
                    conn.execute(text("ALTER TABLE reservations ADD COLUMN metadata_json JSON DEFAULT '{}';"))
            res_cred = conn.execute(text("PRAGMA table_info(integration_credentials);")).fetchall()
            existing_cred_cols = {row[1] for row in res_cred}
            if existing_cred_cols:
                if "connection_id" not in existing_cred_cols:
                    conn.execute(text("ALTER TABLE integration_credentials ADD COLUMN connection_id VARCHAR(64);"))
                if "lease_owner_id" not in existing_cred_cols:
                    conn.execute(text("ALTER TABLE integration_credentials ADD COLUMN lease_owner_id VARCHAR(64);"))
                if "lease_expires_at" not in existing_cred_cols:
                    conn.execute(text("ALTER TABLE integration_credentials ADD COLUMN lease_expires_at DATETIME;"))
                if "fencing_token" not in existing_cred_cols:
                    conn.execute(text("ALTER TABLE integration_credentials ADD COLUMN fencing_token BIGINT DEFAULT 0;"))
                if "schema_version" not in existing_cred_cols:
                    conn.execute(text("ALTER TABLE integration_credentials ADD COLUMN schema_version INTEGER DEFAULT 1;"))
    except Exception as exc:
        logger.warning(f"Schema column migration note: {exc}")



def init_db_schema(engine: Optional[Engine] = None) -> None:
    """Create all tables defined in Base metadata and migrate missing columns."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
    migrate_schema_columns(eng)
