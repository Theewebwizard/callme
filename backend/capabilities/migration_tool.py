"""
Resumable Credential Migration Tool & Rollback Safeguards (Phase 4).
Upgrades legacy v1 credentials to NIST SP 800-38D AES-256-GCM v2 format,
synthesizes default IntegrationConnection entities for orphan credentials,
supports idempotent resumability, dry-run mode, and zero-leakage redacted audit reports.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import argparse
import json
import logging
import sys
import uuid

from sqlalchemy import select, text, func
from sqlalchemy.orm import Session

from backend.database.engine import get_engine
from backend.database.models import (
    IntegrationConnection,
    IntegrationCredential,
    BusinessToolConfig,
    utcnow,
)
from backend.database.service import DatabaseService, get_database_service
from backend.capabilities.vault import (
    encrypt_vault_payload,
    decrypt_vault_payload,
    validate_and_decode_key,
    CredentialDecryptionError,
)

logger = logging.getLogger(__name__)


def is_v2_envelope(encrypted_payload: Optional[str]) -> bool:
    """Check if an encrypted payload is in Envelope v2 (AES-256-GCM) format."""
    if not encrypted_payload:
        return False
    try:
        data = json.loads(encrypted_payload)
        return isinstance(data, dict) and data.get("v") == 2 and data.get("alg") == "AES-256-GCM"
    except Exception:
        return False


@dataclass
class RecordMigrationAudit:
    """Audit entry for a single credential record migration attempt."""
    credential_id: str
    business_id: str
    tool_id: str
    provider_id: str
    connection_id: Optional[str]
    status: str  # "MIGRATED", "SKIPPED_ALREADY_MIGRATED", "FAILED"
    reason: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "business_id": self.business_id,
            "tool_id": self.tool_id,
            "provider_id": self.provider_id,
            "connection_id": self.connection_id,
            "status": self.status,
            "reason": self.reason,
            "error": self.error,
        }


@dataclass
class CredentialMigrationResult:
    """Aggregate result of a credential migration run."""
    dry_run: bool
    started_at: datetime
    completed_at: datetime
    total_inspected: int = 0
    migrated_count: int = 0
    already_migrated_count: int = 0
    failed_count: int = 0
    records: List[RecordMigrationAudit] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def success(self) -> bool:
        return self.failed_count == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert migration summary and records to JSON-serializable dictionary."""
        return {
            "summary": {
                "dry_run": self.dry_run,
                "success": self.success,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
                "duration_seconds": round(self.duration_seconds, 3),
                "total_inspected": self.total_inspected,
                "migrated_count": self.migrated_count,
                "already_migrated_count": self.already_migrated_count,
                "failed_count": self.failed_count,
            },
            "records": [r.to_dict() for r in self.records],
        }

    def to_markdown(self) -> str:
        """Generate human-readable markdown audit report (zero secrets exposed)."""
        mode_str = "DRY-RUN (No Database Changes Persisted)" if self.dry_run else "LIVE MIGRATION (Committed to Database)"
        status_str = "SUCCESS" if self.success else "COMPLETED WITH ERRORS"

        lines = [
            f"# Credential Vault Migration Report: {status_str}",
            f"**Execution Mode:** `{mode_str}`  ",
            f"**Started At:** `{self.started_at.isoformat()}`  ",
            f"**Completed At:** `{self.completed_at.isoformat()}`  ",
            f"**Duration:** `{round(self.duration_seconds, 3)}s`  ",
            "",
            "## Summary Metrics",
            f"- **Total Records Inspected:** {self.total_inspected}",
            f"- **Migrated:** {self.migrated_count}",
            f"- **Skipped (Already Migrated):** {self.already_migrated_count}",
            f"- **Failed:** {self.failed_count}",
            "",
            "## Record Audit Trail",
            "| Credential ID | Business ID | Tool ID | Provider | Connection ID | Status | Reason / Error |",
            "|---|---|---|---|---|---|---|",
        ]

        if not self.records:
            lines.append("| - | - | - | - | - | NONE | No credential records found in database |")
        else:
            for r in self.records:
                err_msg = f" (`{r.error}`)" if r.error else ""
                lines.append(
                    f"| `{r.credential_id}` | `{r.business_id}` | `{r.tool_id}` | "
                    f"`{r.provider_id}` | `{r.connection_id or 'None'}` | "
                    f"**{r.status}** | {r.reason}{err_msg} |"
                )

        return "\n".join(lines)


def _find_or_synthesize_connection(
    session: Session,
    business_id: str,
    provider_id: str,
    tool_id: str,
) -> Tuple[IntegrationConnection, bool]:
    """
    Find existing active connection for (business_id, provider_id), or synthesize
    a default IntegrationConnection entity to link with legacy orphan credentials.
    Returns (connection, was_created).
    """
    # 1. Check for existing default connection
    stmt_def = (
        select(IntegrationConnection)
        .where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider_id == provider_id,
            IntegrationConnection.is_default == True,
        )
    )
    existing_default = session.scalar(stmt_def)
    if existing_default:
        return existing_default, False

    # 2. Check for any existing connection for this provider
    stmt_any = (
        select(IntegrationConnection)
        .where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider_id == provider_id,
        )
        .order_by(IntegrationConnection.created_at.asc())
    )
    existing_any = session.scalars(stmt_any).first()
    if existing_any:
        # Promote to default if none is currently default
        existing_any.is_default = True
        return existing_any, False

    # 3. Synthesize a brand new default connection
    # Determine unique slug
    base_slug = "default"
    slug = base_slug
    attempt = 1
    while True:
        check_slug = session.scalar(
            select(IntegrationConnection.id).where(
                IntegrationConnection.business_id == business_id,
                IntegrationConnection.provider_id == provider_id,
                IntegrationConnection.connection_slug == slug,
            )
        )
        if not check_slug:
            break
        slug = f"{base_slug}-{tool_id[:16]}-{attempt}"
        attempt += 1

    display_name = provider_id.replace("_", " ").title()
    now = utcnow()
    new_conn = IntegrationConnection(
        id=f"conn_{uuid.uuid4().hex[:12]}",
        business_id=business_id,
        provider_id=provider_id,
        connection_slug=slug,
        display_label=f"Migrated {display_name} Connection",
        is_default=True,
        status="active",
        metadata_json={
            "migrated_from_legacy": True,
            "migrated_tool_id": tool_id,
            "migrated_at": now.isoformat(),
        },
        created_at=now,
        updated_at=now,
    )
    session.add(new_conn)
    session.flush()
    return new_conn, True


def _process_credential_migration(
    session: Session,
    cred: IntegrationCredential,
    master_key_bytes: Optional[bytes],
    result: CredentialMigrationResult,
) -> None:
    # Check if already migrated
    is_v2_cipher = is_v2_envelope(cred.encrypted_secrets)
    has_connection = bool(cred.connection_id)
    is_v2_schema = (cred.schema_version or 1) >= 2

    # Verify connection exists if connection_id is set
    connection_valid = False
    if has_connection:
        conn_check = session.get(IntegrationConnection, cred.connection_id)
        if conn_check:
            connection_valid = True

    if is_v2_cipher and has_connection and is_v2_schema and connection_valid:
        result.already_migrated_count += 1
        result.records.append(
            RecordMigrationAudit(
                credential_id=cred.id,
                business_id=cred.business_id,
                tool_id=cred.tool_id,
                provider_id=cred.option_id,
                connection_id=cred.connection_id,
                status="SKIPPED_ALREADY_MIGRATED",
                reason="Record already at schema_version=2 with valid connection_id and v2 AES-GCM ciphertext.",
            )
        )
        return

    # Record needs migration: attempt lossless decryption
    try:
        plaintext_secrets = decrypt_vault_payload(cred.encrypted_secrets, master_key=master_key_bytes)
    except CredentialDecryptionError as dec_err:
        logger.error(
            "Migration failed for credential %s (tenant %s, tool %s): Decryption error: %s",
            cred.id, cred.business_id, cred.tool_id, dec_err,
        )
        result.failed_count += 1
        result.records.append(
            RecordMigrationAudit(
                credential_id=cred.id,
                business_id=cred.business_id,
                tool_id=cred.tool_id,
                provider_id=cred.option_id,
                connection_id=cred.connection_id,
                status="FAILED",
                reason="Decryption failed - ciphertext may be corrupted or encrypted with different key.",
                error=str(dec_err),
            )
        )
        return
    except Exception as exc:
        logger.error("Unexpected error decrypting credential %s: %s", cred.id, exc)
        result.failed_count += 1
        result.records.append(
            RecordMigrationAudit(
                credential_id=cred.id,
                business_id=cred.business_id,
                tool_id=cred.tool_id,
                provider_id=cred.option_id,
                connection_id=cred.connection_id,
                status="FAILED",
                reason="Unexpected exception during trial decryption.",
                error=str(exc),
            )
        )
        return

    # Ensure IntegrationConnection entity is linked
    conn_id = cred.connection_id
    conn_created = False
    if not connection_valid:
        conn_obj, conn_created = _find_or_synthesize_connection(
            session=session,
            business_id=cred.business_id,
            provider_id=cred.option_id,
            tool_id=cred.tool_id,
        )
        conn_id = conn_obj.id

    # Re-encrypt secrets into v2 format (96-bit nonce, 128-bit auth tag)
    new_ciphertext, new_fingerprint = encrypt_vault_payload(plaintext_secrets, master_key=master_key_bytes)

    # Apply changes to record
    cred.connection_id = conn_id
    cred.encrypted_secrets = new_ciphertext
    cred.key_fingerprint = new_fingerprint
    cred.schema_version = 2
    cred.updated_at = utcnow()

    result.migrated_count += 1
    reason_parts = []
    if not is_v2_cipher:
        reason_parts.append("Re-encrypted legacy ciphertext to AES-256-GCM v2")
    if not connection_valid:
        action = "Synthesized and linked default connection" if conn_created else "Linked to existing default connection"
        reason_parts.append(action)
    if not is_v2_schema:
        reason_parts.append("Advanced schema_version to 2")

    result.records.append(
        RecordMigrationAudit(
            credential_id=cred.id,
            business_id=cred.business_id,
            tool_id=cred.tool_id,
            provider_id=cred.option_id,
            connection_id=conn_id,
            status="MIGRATED",
            reason="; ".join(reason_parts) or "Re-encrypted and verified.",
        )
    )


def migrate_credentials(
    db_service: Optional[DatabaseService] = None,
    dry_run: bool = False,
    batch_size: int = 100,
    raw_key: Optional[str] = None,
) -> CredentialMigrationResult:
    """
    Execute resumable credential migration with dry-run support, batch pagination, and rollback safeguards.
    1. Scans integration_credentials in configurable batches.
    2. Identifies unmigrated or legacy envelope records.
    3. Re-encrypts secret material to NIST SP 800-38D AES-256-GCM v2 format.
    4. Synthesizes and links IntegrationConnection entities for orphan records.
    5. Updates schema_version = 2 and key fingerprints.
    6. In live mode, commits each batch in its own independent database transaction.
    7. Emits zero-leakage redacted audit report.
    """
    if db_service is None:
        db_service = get_database_service()

    if batch_size <= 0:
        batch_size = 100

    started_at = datetime.now(timezone.utc)
    result = CredentialMigrationResult(
        dry_run=dry_run,
        started_at=started_at,
        completed_at=started_at,
    )

    # Decode and validate override key if supplied
    master_key_bytes: Optional[bytes] = None
    if raw_key:
        if isinstance(raw_key, str):
            master_key_bytes = validate_and_decode_key(raw_key)
        elif isinstance(raw_key, bytes):
            master_key_bytes = raw_key

    engine = db_service.engine

    # Count total records first
    with engine.connect() as probe_conn:
        with Session(bind=probe_conn) as probe_session:
            result.total_inspected = probe_session.scalar(
                select(func.count(IntegrationCredential.id))
            ) or 0

    if result.total_inspected == 0:
        result.completed_at = datetime.now(timezone.utc)
        return result

    if dry_run:
        with engine.connect() as connection:
            trans = connection.begin()
            session = Session(bind=connection)
            try:
                offset = 0
                while True:
                    stmt = (
                        select(IntegrationCredential)
                        .order_by(IntegrationCredential.created_at.asc(), IntegrationCredential.id.asc())
                        .offset(offset)
                        .limit(batch_size)
                    )
                    batch = list(session.scalars(stmt).all())
                    if not batch:
                        break

                    for cred in batch:
                        _process_credential_migration(
                            session=session,
                            cred=cred,
                            master_key_bytes=master_key_bytes,
                            result=result,
                        )
                    offset += len(batch)

                trans.rollback()
                logger.info("Dry-run migration complete. All %d records processed and rolled back.", result.total_inspected)
            except Exception as exc:
                trans.rollback()
                logger.critical("Fatal error during dry-run migration: %s", exc)
                result.failed_count += 1
                result.records.append(
                    RecordMigrationAudit(
                        credential_id="GLOBAL",
                        business_id="GLOBAL",
                        tool_id="GLOBAL",
                        provider_id="GLOBAL",
                        connection_id=None,
                        status="FAILED",
                        reason="Fatal exception during dry-run simulation.",
                        error=str(exc),
                    )
                )
            finally:
                session.close()
    else:
        offset = 0
        while True:
            with engine.connect() as connection:
                trans = connection.begin()
                session = Session(bind=connection)
                try:
                    stmt = (
                        select(IntegrationCredential)
                        .order_by(IntegrationCredential.created_at.asc(), IntegrationCredential.id.asc())
                        .offset(offset)
                        .limit(batch_size)
                    )
                    batch = list(session.scalars(stmt).all())
                    if not batch:
                        trans.rollback()
                        session.close()
                        break

                    for cred in batch:
                        _process_credential_migration(
                            session=session,
                            cred=cred,
                            master_key_bytes=master_key_bytes,
                            result=result,
                        )

                    session.flush()
                    trans.commit()
                    offset += len(batch)
                    logger.debug("Committed migration batch of %d records (offset %d).", len(batch), offset)
                except Exception as exc:
                    trans.rollback()
                    logger.critical("Fatal error during live batch migration at offset %d: %s", offset, exc)
                    result.failed_count += 1
                    result.records.append(
                        RecordMigrationAudit(
                            credential_id="GLOBAL",
                            business_id="GLOBAL",
                            tool_id="GLOBAL",
                            provider_id="GLOBAL",
                            connection_id=None,
                            status="FAILED",
                            reason=f"Fatal exception during batch migration at offset {offset}.",
                            error=str(exc),
                        )
                    )
                    break
                finally:
                    session.close()

        logger.info(
            "Credential migration complete: %d migrated, %d skipped, %d failed.",
            result.migrated_count, result.already_migrated_count, result.failed_count,
        )

    result.completed_at = datetime.now(timezone.utc)
    return result



def main() -> None:
    """CLI entrypoint for running the credential vault migration."""
    parser = argparse.ArgumentParser(
        description="Resumable Integration Credential Vault Migration Tool"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration and generate audit report without persisting database changes.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records to process per batch (default: 100).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output audit report formatted as JSON instead of Markdown.",
    )
    parser.add_argument(
        "--key",
        type=str,
        default=None,
        help="Optional custom 32-byte encryption key (default: read from environment).",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    result = migrate_credentials(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        raw_key=args.key,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.to_markdown())

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
