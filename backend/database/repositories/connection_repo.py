"""
Repository for multi-account integration connections and distributed lease management.
Enforces multi-account invariants, default connection constraints, and atomic CAS refresh leases.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import uuid
import logging

from sqlalchemy import select, update, delete, or_, and_
from sqlalchemy.orm import Session

from backend.database.models import (
    IntegrationConnection,
    IntegrationCredential,
    utcnow,
)
from backend.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ConnectionRepository(BaseRepository):
    """Repository handling external provider connections and distributed credential leases."""

    # ---------------------------------------------------------------------------
    # 1. Multi-Account Connection Management
    # ---------------------------------------------------------------------------

    def create_connection(
        self,
        business_id: str,
        provider_id: str,
        connection_slug: str = "default",
        external_account_id: Optional[str] = None,
        display_label: Optional[str] = None,
        is_default: bool = False,
        status: str = "active",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IntegrationConnection:
        """
        Create a new provider connection for a tenant.
        If is_default is True, automatically unsets any existing default for this provider in the same transaction.
        """
        now = utcnow()
        if is_default:
            self.session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.business_id == business_id,
                    IntegrationConnection.provider_id == provider_id,
                    IntegrationConnection.is_default == True,
                )
                .values(is_default=False, updated_at=now)
            )

        conn_id = f"conn_{uuid.uuid4().hex[:12]}"
        connection = IntegrationConnection(
            id=conn_id,
            business_id=business_id,
            provider_id=provider_id,
            connection_slug=connection_slug,
            external_account_id=external_account_id,
            display_label=display_label,
            is_default=is_default,
            status=status,
            metadata_json=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.session.add(connection)
        self.session.flush()
        return connection

    def get_connection(
        self,
        connection_id: str,
        business_id: Optional[str] = None,
    ) -> Optional[IntegrationConnection]:
        """Fetch connection by ID, optionally scoped to a business tenant."""
        stmt = select(IntegrationConnection).where(IntegrationConnection.id == connection_id)
        if business_id:
            stmt = stmt.where(IntegrationConnection.business_id == business_id)
        return self.session.scalar(stmt)

    def get_connection_by_slug(
        self,
        business_id: str,
        provider_id: str,
        connection_slug: str,
    ) -> Optional[IntegrationConnection]:
        """Fetch connection by tenant, provider, and unique connection slug."""
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider_id == provider_id,
            IntegrationConnection.connection_slug == connection_slug,
        )
        return self.session.scalar(stmt)

    def get_default_connection(
        self,
        business_id: str,
        provider_id: str,
    ) -> Optional[IntegrationConnection]:
        """Fetch the default connection for a tenant and provider."""
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider_id == provider_id,
            IntegrationConnection.is_default == True,
            IntegrationConnection.status == "active",
        )
        return self.session.scalar(stmt)

    def list_connections(
        self,
        business_id: str,
        provider_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[IntegrationConnection]:
        """List connections for a business with optional provider and status filters."""
        stmt = select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
        if provider_id:
            stmt = stmt.where(IntegrationConnection.provider_id == provider_id)
        if status:
            stmt = stmt.where(IntegrationConnection.status == status)
        stmt = stmt.order_by(IntegrationConnection.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def set_default_connection(
        self,
        business_id: str,
        provider_id: str,
        connection_id: str,
    ) -> bool:
        """
        Atomically set a connection as the default for (business_id, provider_id).
        Clears any prior default in the same transaction.
        """
        target = self.get_connection(connection_id, business_id=business_id)
        if not target or target.provider_id != provider_id:
            return False

        now = utcnow()
        # 1. Clear previous default
        self.session.execute(
            update(IntegrationConnection)
            .where(
                IntegrationConnection.business_id == business_id,
                IntegrationConnection.provider_id == provider_id,
                IntegrationConnection.is_default == True,
            )
            .values(is_default=False, updated_at=now)
        )

        # 2. Set new default
        self.session.execute(
            update(IntegrationConnection)
            .where(
                IntegrationConnection.id == connection_id,
                IntegrationConnection.business_id == business_id,
            )
            .values(is_default=True, updated_at=now)
        )
        self.session.flush()
        return True

    def update_connection_status(
        self,
        connection_id: str,
        status: str,
        business_id: Optional[str] = None,
    ) -> Optional[IntegrationConnection]:
        """Update connection operational status (active, expired, revoked, disconnected)."""
        conn = self.get_connection(connection_id, business_id=business_id)
        if not conn:
            return None
        conn.status = status
        conn.updated_at = utcnow()
        self.session.flush()
        return conn

    def delete_connection(
        self,
        connection_id: str,
        business_id: Optional[str] = None,
    ) -> bool:
        """Purge connection record and cascade-delete associated credentials."""
        conn = self.get_connection(connection_id, business_id=business_id)
        if not conn:
            return False
        self.session.delete(conn)
        self.session.flush()
        return True

    # ---------------------------------------------------------------------------
    # 2. Distributed Lease Management & Fencing Tokens
    # ---------------------------------------------------------------------------

    def acquire_refresh_lease(
        self,
        cred_id: str,
        worker_id: str,
        ttl_seconds: int = 30,
        business_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Atomically acquire a token refresh lease via Compare-And-Swap (CAS).
        Succeeds only if lease is unheld or lease_expires_at < NOW().
        Requires valid non-empty business_id and strictly scopes to tenant.
        Increments fencing_token and returns the new token value if acquired, else None.
        """
        if not business_id or not str(business_id).strip():
            raise ValueError("business_id is required for acquire_refresh_lease and cannot be None or empty.")

        now = utcnow()
        new_expiry = now + timedelta(seconds=ttl_seconds)

        stmt = (
            update(IntegrationCredential)
            .where(
                IntegrationCredential.id == cred_id,
                IntegrationCredential.business_id == business_id,
                or_(
                    IntegrationCredential.lease_expires_at.is_(None),
                    IntegrationCredential.lease_expires_at < now,
                ),
            )
            .values(
                lease_owner_id=worker_id,
                lease_expires_at=new_expiry,
                fencing_token=IntegrationCredential.fencing_token + 1,
                updated_at=now,
            )
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            return None

        self.session.flush()
        stmt_get = (
            select(IntegrationCredential)
            .where(
                IntegrationCredential.id == cred_id,
                IntegrationCredential.business_id == business_id,
            )
        )
        cred = self.session.scalar(stmt_get)
        return cred.fencing_token if cred else None

    def commit_refreshed_credentials(
        self,
        cred_id: str,
        worker_id: str,
        acquired_fencing_token: int,
        new_encrypted_secrets: str,
        new_expires_at: Optional[datetime] = None,
        new_key_fingerprint: Optional[str] = None,
        business_id: Optional[str] = None,
    ) -> bool:
        """
        Atomically commit newly refreshed credentials and release the refresh lease.
        Enforces fencing token check: fails if another worker acquired a lease in the interim.
        Requires valid non-empty business_id and strictly scopes to tenant.
        Returns True if committed, False if superseded, expired, or tenant mismatch.
        """
        if not business_id or not str(business_id).strip():
            raise ValueError("business_id is required for commit_refreshed_credentials and cannot be None or empty.")

        now = utcnow()
        values: Dict[str, Any] = {
            "encrypted_secrets": new_encrypted_secrets,
            "lease_owner_id": None,
            "lease_expires_at": None,
            "fencing_token": IntegrationCredential.fencing_token + 1,
            "updated_at": now,
        }
        if new_expires_at is not None:
            values["expires_at"] = new_expires_at
        if new_key_fingerprint is not None:
            values["key_fingerprint"] = new_key_fingerprint

        stmt = (
            update(IntegrationCredential)
            .where(
                IntegrationCredential.id == cred_id,
                IntegrationCredential.business_id == business_id,
                IntegrationCredential.lease_owner_id == worker_id,
                IntegrationCredential.fencing_token == acquired_fencing_token,
            )
            .values(**values)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return bool(result.rowcount > 0)

    def release_refresh_lease(
        self,
        cred_id: str,
        worker_id: str,
        business_id: Optional[str] = None,
    ) -> bool:
        """
        Release a held refresh lease without updating credentials.
        Guarantees that a worker cannot release a lease owned by another worker or tenant.
        Requires valid non-empty business_id and strictly scopes to tenant.
        """
        if not business_id or not str(business_id).strip():
            raise ValueError("business_id is required for release_refresh_lease and cannot be None or empty.")

        stmt = (
            update(IntegrationCredential)
            .where(
                IntegrationCredential.id == cred_id,
                IntegrationCredential.business_id == business_id,
                IntegrationCredential.lease_owner_id == worker_id,
            )
            .values(
                lease_owner_id=None,
                lease_expires_at=None,
                updated_at=utcnow(),
            )
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return bool(result.rowcount > 0)

    def link_credential_to_connection(
        self,
        cred_id: str,
        connection_id: str,
    ) -> bool:
        """Associate an integration credential record with a connection entity."""
        stmt = (
            update(IntegrationCredential)
            .where(IntegrationCredential.id == cred_id)
            .values(
                connection_id=connection_id,
                updated_at=utcnow(),
            )
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return bool(result.rowcount > 0)

    def get_credential_by_connection(
        self,
        connection_id: str,
        business_id: Optional[str] = None,
    ) -> Optional[IntegrationCredential]:
        """Retrieve credential record associated with a connection ordered deterministically."""
        stmt = (
            select(IntegrationCredential)
            .where(IntegrationCredential.connection_id == connection_id)
            .order_by(
                IntegrationCredential.updated_at.desc(),
                IntegrationCredential.created_at.desc(),
                IntegrationCredential.id.desc(),
            )
        )
        if business_id:
            stmt = stmt.where(IntegrationCredential.business_id == business_id)
        return self.session.scalars(stmt).first()

    def save_connection_credential(
        self,
        connection_id: str,
        business_id: str,
        encrypted_secrets: str,
        key_fingerprint: str,
        option_id: str = "custom",
        tool_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> IntegrationCredential:
        """Store or update encrypted credential record directly attached to a connection."""
        cred = self.get_credential_by_connection(connection_id, business_id=business_id)
        now = utcnow()
        effective_tool_id = tool_id or f"conn_{connection_id}"
        if cred:
            cred.encrypted_secrets = encrypted_secrets
            cred.key_fingerprint = key_fingerprint
            if option_id:
                cred.option_id = option_id
            if scopes is not None:
                cred.scopes = scopes
            if expires_at is not None:
                cred.expires_at = expires_at
            cred.updated_at = now
        else:
            cred = IntegrationCredential(
                id=f"cred_{uuid.uuid4().hex[:12]}",
                business_id=business_id,
                connection_id=connection_id,
                tool_id=effective_tool_id,
                option_id=option_id,
                encrypted_secrets=encrypted_secrets,
                key_fingerprint=key_fingerprint,
                scopes=scopes or [],
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            self.session.add(cred)
        self.session.flush()
        return cred

    def delete_connection_credential(
        self,
        connection_id: str,
        business_id: str,
    ) -> bool:
        """Purge credential record attached to a connection for a specific tenant."""
        if not business_id or not str(business_id).strip():
            raise ValueError("business_id is required for delete_connection_credential and cannot be None or empty.")
        stmt = delete(IntegrationCredential).where(
            IntegrationCredential.connection_id == connection_id,
            IntegrationCredential.business_id == business_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return bool(result.rowcount > 0)
