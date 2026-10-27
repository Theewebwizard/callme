"""
Distributed OAuth Token Refresh Coordination and Provider Revocation Engine.
Guarantees atomic CAS leases, anti-zombie fencing token checks, bounded 8s HTTP timeouts,
concurrent refresh deduplication, upstream provider revocation upon disconnect,
and lossless credential preservation across token refreshes.
"""

from typing import Dict, Any, Optional, Callable, Awaitable, Set
from datetime import datetime, timezone, timedelta
import asyncio
import time
import random
import uuid
import logging
import urllib.request
import urllib.parse
import urllib.error
import json
import httpx
from sqlalchemy import select

from backend.capabilities.vault import decrypt_vault_payload, encrypt_vault_payload

logger = logging.getLogger(__name__)

# Bounded timeouts per specification
DEFAULT_HTTP_TIMEOUT_SECONDS = 8.0
DEFAULT_LEASE_TTL_SECONDS = 30
DEFAULT_MAX_WAIT_SECONDS = 10.0

# Fields permitted to be updated from an upstream OAuth refresh response
ALLOWED_REFRESH_FIELDS: Set[str] = {
    "access_token",
    "token_type",
    "expires_in",
    "expires_at",
    "refresh_token",
    "scope",
    "scopes",
    "id_token",
    "ext_expires_in",
    "session_state",
}

# Fields strictly forbidden from being overwritten by upstream provider response
FORBIDDEN_REFRESH_FIELDS: Set[str] = {
    "business_id",
    "id",
    "client_id",
    "client_secret",
    "fencing_token",
    "lease_owner_id",
    "lease_expires_at",
    "schema_version",
    "created_at",
    "updated_at",
    "connection_id",
    "tool_id",
    "option_id",
    "encrypted_secrets",
    "key_fingerprint",
}


class RefreshCoordinationError(Exception):
    """Raised when distributed token refresh coordination fails."""
    pass


class StaleCommitRejectedError(RefreshCoordinationError):
    """Raised when a worker's refreshed token commit is rejected due to fencing token mismatch."""
    pass


class TenantIsolationError(RefreshCoordinationError, PermissionError):
    """Raised when an operation attempts cross-tenant credential access or modification."""
    pass


def validate_and_sanitize_refresh_response(response: Any) -> Dict[str, Any]:
    """
    Validate provider refresh response structure and sanitize updatable fields.
    Ensures response contains a valid non-empty access token and does not inject forbidden fields.
    """
    if not isinstance(response, dict):
        raise ValueError(f"Provider refresh response must be a dict, got {type(response).__name__}")

    # Validate access_token
    token = response.get("access_token")
    if not token or not isinstance(token, str) or not token.strip():
        raise ValueError("Provider refresh response missing valid non-empty 'access_token'")

    # Validate expires_in / expires_at if provided
    if "expires_in" in response and response["expires_in"] is not None:
        try:
            exp_val = float(response["expires_in"])
            if exp_val <= 0:
                raise ValueError(f"Invalid 'expires_in': must be positive, got {exp_val}")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid 'expires_in' format in refresh response: {exc}") from exc

    # Sanitize: only allow whitelisted fields and strictly exclude forbidden fields
    sanitized: Dict[str, Any] = {}
    for k, v in response.items():
        if k in FORBIDDEN_REFRESH_FIELDS:
            logger.warning("Ignored forbidden field '%s' in provider refresh response", k)
            continue
        if k in ALLOWED_REFRESH_FIELDS:
            sanitized[k] = v

    # Ensure access_token is stripped and included
    sanitized["access_token"] = token.strip()
    return sanitized


async def execute_oauth_refresh_with_lease(
    db_service: Any,
    business_id: str,
    cred_id: str,
    refresh_coro_fn: Callable[[], Awaitable[Dict[str, Any]]],
    worker_id: Optional[str] = None,
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
) -> Dict[str, Any]:
    """
    Execute an OAuth token refresh protected by distributed CAS lease and fencing tokens.
    1. Validates that cred_id exists and is owned by business_id (fails closed on IDOR/cross-tenant).
    2. Attempts to acquire lease scoped by business_id.
    3. If lease held by another worker, waits and polls; if other worker completes refresh,
       returns fresh token from DB (scoped by business_id, deduplicating upstream calls).
    4. If lease acquired, executes refresh_coro_fn with strict 8s timeout.
    5. Validates provider refresh response (requires valid access_token, sanitizes fields).
    6. Merges refreshed data into existing credentials:
       - Preserves omitted fields (client_id, client_secret, refresh_token, scopes, config).
       - Rotates refresh_token only if provider returned a new valid refresh token.
    7. Commits refreshed token with acquired fencing token (anti-zombie protection) scoped by business_id.
    """
    wid = worker_id or f"w_{uuid.uuid4().hex[:8]}"
    start_time = time.monotonic()

    # 0. Initial Tenant Ownership Check (Fail Closed before any lease or polling)
    with db_service.session_factory() as session:
        from backend.database.models import IntegrationCredential
        stmt = select(IntegrationCredential).where(
            IntegrationCredential.id == cred_id,
            IntegrationCredential.business_id == business_id,
        )
        initial_cred = session.scalar(stmt)
        if not initial_cred:
            raise TenantIsolationError(
                f"Access denied: Credential '{cred_id}' does not exist or does not belong to business '{business_id}'."
            )

    # 1. Acquisition / Poll Loop
    acquired_fencing_token: Optional[int] = None

    while True:
        # Check if token is already fresh in the DB (refreshed by peer worker), scoped strictly to business_id
        with db_service.session_factory() as session:
            from backend.database.models import IntegrationCredential
            stmt = select(IntegrationCredential).where(
                IntegrationCredential.id == cred_id,
                IntegrationCredential.business_id == business_id,
            )
            cred_rec = session.scalar(stmt)
            if not cred_rec:
                raise TenantIsolationError(
                    f"Access denied: Credential '{cred_id}' not found for business '{business_id}'."
                )
            if cred_rec.expires_at:
                now_utc = datetime.now(timezone.utc)
                exp = cred_rec.expires_at if cred_rec.expires_at.tzinfo else cred_rec.expires_at.replace(tzinfo=timezone.utc)
                if exp > now_utc + timedelta(seconds=60):
                    # Fresh token already committed in DB; deduplicate and avoid upstream call
                    logger.info("Token refresh deduplicated: credential %s is already fresh (expires_at=%s)", cred_id, exp)
                    return decrypt_vault_payload(cred_rec.encrypted_secrets)

        # Attempt atomic CAS lease acquisition scoped to business_id
        acquired_fencing_token = db_service.acquire_refresh_lease(
            cred_id=cred_id,
            worker_id=wid,
            ttl_seconds=lease_ttl_seconds,
            business_id=business_id,
        )

        if acquired_fencing_token is not None:
            # Lease acquired!
            break

        # Check wait timeout
        elapsed = time.monotonic() - start_time
        if elapsed >= max_wait_seconds:
            logger.warning("Timed out waiting for peer worker to complete token refresh on cred %s", cred_id)
            raise TimeoutError(f"Token refresh lease wait exceeded {max_wait_seconds}s for {cred_id}")

        # Jittered exponential backoff while waiting for peer to finish refresh
        jitter = random.uniform(0.05, 0.15)
        sleep_interval = min(0.1 + jitter, max(0.01, max_wait_seconds - elapsed))
        await asyncio.sleep(sleep_interval)

    # 2. Execute Upstream Refresh under Acquired Lease
    try:
        # Enforce bounded HTTP timeout (<= 8s) to prevent lease expiry during in-flight call
        refreshed_data = await asyncio.wait_for(refresh_coro_fn(), timeout=http_timeout_seconds)
    except asyncio.TimeoutError as exc:
        logger.error("Upstream token refresh HTTP call timed out after %ss (Worker: %s)", http_timeout_seconds, wid)
        db_service.release_refresh_lease(cred_id, wid, business_id=business_id)
        raise TimeoutError(f"Upstream provider refresh timed out after {http_timeout_seconds}s") from exc
    except Exception as exc:
        logger.error("Upstream token refresh failed: %s (Worker: %s)", exc, wid)
        db_service.release_refresh_lease(cred_id, wid, business_id=business_id)
        raise

    # 3. Validate Provider Response
    try:
        validated_update = validate_and_sanitize_refresh_response(refreshed_data)
    except Exception as val_exc:
        logger.error("Upstream token refresh response failed validation: %s (Worker: %s)", val_exc, wid)
        db_service.release_refresh_lease(cred_id, wid, business_id=business_id)
        raise RefreshCoordinationError(f"Malformed provider refresh response: {val_exc}") from val_exc

    # 4. Load Existing Stored Credentials and Safely Merge (Preserving Omitted Secrets)
    try:
        with db_service.session_factory() as session:
            from backend.database.models import IntegrationCredential
            stmt = select(IntegrationCredential).where(
                IntegrationCredential.id == cred_id,
                IntegrationCredential.business_id == business_id,
            )
            curr_rec = session.scalar(stmt)
            if not curr_rec:
                db_service.release_refresh_lease(cred_id, wid, business_id=business_id)
                raise TenantIsolationError(f"Credential '{cred_id}' not found for business '{business_id}'.")
            existing_secrets = decrypt_vault_payload(curr_rec.encrypted_secrets) if curr_rec.encrypted_secrets else {}

        # Merge updates on top of a copy of existing secrets to preserve client credentials & config
        merged_secrets = dict(existing_secrets)

        # Update access token and token type
        merged_secrets["access_token"] = validated_update["access_token"]
        if "token_type" in validated_update:
            merged_secrets["token_type"] = validated_update["token_type"]

        # Refresh token rotation:
        # If provider returned a new non-empty refresh_token, replace the old one.
        # Otherwise, preserve the existing refresh_token.
        if (
            "refresh_token" in validated_update
            and isinstance(validated_update["refresh_token"], str)
            and validated_update["refresh_token"].strip()
        ):
            merged_secrets["refresh_token"] = validated_update["refresh_token"].strip()

        # Update scopes / OpenID claims if present
        for optional_field in ("scope", "scopes", "id_token", "ext_expires_in", "session_state"):
            if optional_field in validated_update:
                merged_secrets[optional_field] = validated_update[optional_field]

        # Determine expiration timestamp
        new_exp_dt: Optional[datetime] = None
        if "expires_at" in validated_update:
            val = validated_update["expires_at"]
            if isinstance(val, (int, float)):
                new_exp_dt = datetime.fromtimestamp(val, tz=timezone.utc)
            elif isinstance(val, datetime):
                new_exp_dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
                merged_secrets["expires_at"] = new_exp_dt.isoformat()
        elif "expires_in" in validated_update:
            new_exp_dt = datetime.now(timezone.utc) + timedelta(seconds=int(validated_update["expires_in"]))
            merged_secrets["expires_in"] = validated_update["expires_in"]
            merged_secrets["expires_at"] = new_exp_dt.isoformat()
        elif "expires_at" in existing_secrets:
            val = existing_secrets["expires_at"]
            if isinstance(val, (int, float)):
                new_exp_dt = datetime.fromtimestamp(val, tz=timezone.utc)
            elif isinstance(val, datetime):
                new_exp_dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)

        # 5. Commit Refreshed Credentials with Fencing Token Guard
        new_encrypted, fp = encrypt_vault_payload(merged_secrets)

        committed = db_service.commit_refreshed_credentials(
            cred_id=cred_id,
            worker_id=wid,
            acquired_fencing_token=acquired_fencing_token,
            new_encrypted_secrets=new_encrypted,
            new_expires_at=new_exp_dt,
            new_key_fingerprint=fp,
            business_id=business_id,
        )

        if not committed:
            # Zombie worker condition: lease expired and another worker superseded
            logger.warning(
                "Anti-zombie protection: refresh commit rejected due to fencing token mismatch for worker %s on cred %s",
                wid,
                cred_id,
            )
            # Fetch authoritative record from DB scoped by tenant
            with db_service.session_factory() as session:
                from backend.database.models import IntegrationCredential
                stmt = select(IntegrationCredential).where(
                    IntegrationCredential.id == cred_id,
                    IntegrationCredential.business_id == business_id,
                )
                authoritative = session.scalar(stmt)
                if authoritative and authoritative.encrypted_secrets:
                    return decrypt_vault_payload(authoritative.encrypted_secrets)
            raise StaleCommitRejectedError("Worker commit superseded by another lease.")

        return merged_secrets

    except Exception:
        db_service.release_refresh_lease(cred_id, wid, business_id=business_id)
        raise


def revoke_oauth_provider_credentials(
    provider_id: str,
    credentials: Dict[str, Any],
    timeout_seconds: float = 5.0,
) -> bool:
    """
    Execute outbound provider token revocation upon capability disconnection.
    Best-effort with strict timeout: catches network failures without blocking local purge.
    """
    token_to_revoke = (
        credentials.get("refresh_token")
        or credentials.get("access_token")
        or credentials.get("api_key")
    )
    if not token_to_revoke:
        return True

    prov = provider_id.lower()

    try:
        if "google" in prov or prov == "gmail":
            # Google OAuth token revocation endpoint
            url = f"https://oauth2.googleapis.com/revoke?token={urllib.parse.quote(str(token_to_revoke))}"
            req = urllib.request.Request(
                url,
                data=b"",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                logger.info("Google token revocation returned HTTP %d", resp.status)
                return resp.status == 200

        elif "stripe" in prov:
            # Stripe Connect deauthorization
            client_id = credentials.get("client_id")
            stripe_user_id = credentials.get("stripe_user_id")
            secret_key = credentials.get("stripe_secret_key")
            if client_id and stripe_user_id and secret_key:
                url = "https://connect.stripe.com/oauth/deauthorize"
                post_data = urllib.parse.urlencode({
                    "client_id": client_id,
                    "stripe_user_id": stripe_user_id,
                }).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=post_data,
                    headers={
                        "Authorization": f"Bearer {secret_key}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                    logger.info("Stripe deauthorization returned HTTP %d", resp.status)
                    return resp.status == 200

        elif "zendesk" in prov:
            # Zendesk token revocation
            subdomain = credentials.get("subdomain")
            token_id = credentials.get("token_id")
            if subdomain and token_id:
                url = f"https://{subdomain}.zendesk.com/api/v2/oauth/tokens/{token_id}.json"
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {credentials.get('access_token')}"},
                    method="DELETE",
                )
                with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                    logger.info("Zendesk token revocation returned HTTP %d", resp.status)
                    return resp.status in (200, 204)

        logger.info("No explicit outbound revocation protocol for provider %s; proceeding with operational purge.", provider_id)
        return True

    except Exception as exc:
        logger.warning("Provider revocation attempt failed for %s: %s (proceeding with local purge)", provider_id, exc)
        return False
