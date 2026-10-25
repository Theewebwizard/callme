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
            pool_pre_ping=True,  # Test connections before checkout
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
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Database session rolled back due to error: {exc}")
        raise
    finally:
        session.close()


def check_database_connection(engine: Optional[Engine] = None) -> Dict[str, Any]:
    """
    Probe database connectivity and return structured health status.
    Never exposes passwords or sensitive credentials in error messages.
    """
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
        return {
            "connected": True,
            "configured": True,
            "dialect": eng.dialect.name,
            "error": None,
        }
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


def init_db_schema(engine: Optional[Engine] = None) -> None:
    """Create all tables defined in Base metadata on the target database."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
