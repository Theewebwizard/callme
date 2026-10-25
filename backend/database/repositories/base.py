"""
Base repository class providing common session management.
"""

from typing import Optional
from sqlalchemy.orm import Session


class BaseRepository:
    """Base repository with direct session injection."""

    def __init__(self, session: Session) -> None:
        self.session = session
