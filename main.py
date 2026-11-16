"""
Root entrypoint for Vercel deployment of the FastAPI backend service.
Re-exports the core FastAPI application instance from backend.main.
"""

from backend.main import app

__all__ = ["app"]

