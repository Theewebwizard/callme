"""
Database connection and URL configuration utilities.
"""

from typing import Optional
from urllib.parse import urlparse
from backend.config import get_settings


def is_placeholder_db_url(url: Optional[str]) -> bool:
    """Check if the provided database URL is empty or an unconfigured placeholder."""
    if not url or not url.strip():
        return True
    
    cleaned = url.strip().lower()
    placeholders = [
        "your_password",
        "your-supabase-project",
        "your-project",
        "example.com",
        "[your-password]",
        "[your-project-ref]",
    ]
    return any(p in cleaned for p in placeholders)


def normalize_database_url(url: str) -> str:
    """
    Normalize PostgreSQL URL dialect for SQLAlchemy + psycopg2 compatibility.
    Converts 'postgres://' or 'postgresql://' into 'postgresql+psycopg2://'
    while preserving sqlite:// and other explicit driver specifications.
    """
    if not url:
        return url
    
    trimmed = url.strip()
    if trimmed.startswith("sqlite://"):
        return trimmed
    
    if trimmed.startswith("postgres://"):
        return "postgresql+psycopg2://" + trimmed[len("postgres://"):]
    
    if trimmed.startswith("postgresql://") and not trimmed.startswith("postgresql+"):
        return "postgresql+psycopg2://" + trimmed[len("postgresql://"):]
    
    return trimmed


def get_effective_database_url(override_url: Optional[str] = None) -> Optional[str]:
    """
    Get the configured database URL from argument, settings, or return None if unconfigured.
    """
    if override_url:
        return normalize_database_url(override_url)
    
    settings = get_settings()
    raw_url = settings.DATABASE_URL
    if is_placeholder_db_url(raw_url):
        return None
    
    return normalize_database_url(raw_url)
