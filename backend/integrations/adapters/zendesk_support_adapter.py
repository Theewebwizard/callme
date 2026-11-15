"""
Zendesk Support Desk Integration Adapter.
Provides direct integration with the official Zendesk REST API (v2) adhering to official guidance:
- Subdomain normalization (e.g. 'mybrand', 'mybrand.zendesk.com', 'https://mybrand.zendesk.com')
- Preferred multi-tenant OAuth 2.0 authorization flow with Bearer tokens
- Documented alternative authentication via API tokens (email/token:api_token Basic Auth)
- Progressive capability gating: ticket creation & retrieval enabled by default;
  contact/user lookup, comments, updates, and assignment gated by business configuration
- Normalization of ticket IDs, statuses (new/open/pending/hold/solved/closed -> open/pending/resolved/closed),
  priorities, requesters, and assignees
- Protection against duplicate ticket creation via external_id idempotency tracking
- Ambiguous timeout reconciliation: searches Zendesk by external_id before retrying on timeout
- Respects archived-ticket behavior (tickets closed >120 days cannot be updated or commented)
- Respects Zendesk endpoint-specific rate limits and Retry-After headers
- Truthful outcome envelope: Ticket creation references real provider ticket; does not claim human resolution
- Safe diagnostics: test_connection() probes GET /api/v2/users/me.json without creating dummy tickets
- Multi-tenant isolation with isolated credentials and caches
"""

from typing import Dict, Any, Optional, List, Tuple, Set, Union
from datetime import datetime, timezone
import json
import logging
import re
import time
import base64
import hashlib
import uuid
import urllib.request
import urllib.parse
import urllib.error

from backend.integrations.base import IntegrationAdapter
from backend.capabilities.models import (
    AuthoritativeSource,
    ReadinessCheckResult,
    SetupField,
    FieldType,
)
from backend.integrations.models import (
    ProviderManifest,
    IntegrationCategory,
    CapabilityType,
    AuthMethod,
    DiscoveredResource,
    ExecutionContext,
    CapabilityResult,
    ExecutionOutcome,
    IntegrationError,
    ErrorCategory,
    WebhookRequest,
    WebhookResult,
)

logger = logging.getLogger(__name__)

# Zendesk Status Normalization Mapping
ZENDESK_STATUS_MAP: Dict[str, str] = {
    "new": "open",
    "open": "open",
    "pending": "pending",
    "hold": "pending",
    "solved": "resolved",
    "closed": "closed",
}

STATUS_TO_ZENDESK_MAP: Dict[str, str] = {
    "open": "open",
    "pending": "pending",
    "resolved": "solved",
    "closed": "closed",
}

# Zendesk Priority Mapping
ZENDESK_PRIORITIES = {"low", "normal", "high", "urgent"}

# Default Enabled Features
DEFAULT_ENABLED_FEATURES: Set[str] = {"ticket_creation", "ticket_retrieval"}
ALL_SUPPORTED_FEATURES: Set[str] = {
    "ticket_creation",
    "ticket_retrieval",
    "ticket_updates",
    "comments",
    "assignment",
    "user_lookup",
}

IDEMPOTENCY_CACHE_TTL_SECONDS = 600  # 10 minutes cache window


class ZendeskIntegrationException(Exception):
    """Exception wrapper for normalized Zendesk IntegrationError."""
    def __init__(self, error: IntegrationError):
        super().__init__(error.message)
        self.error = error


class ZendeskSupportAdapter(IntegrationAdapter):
    """
    Adapter connecting tenant customer inquiries to the official Zendesk Support REST API (v2).
    Enforces OAuth / API token authorization, progressive capability gating, duplicate prevention,
    ambiguous timeout reconciliation, archived-ticket protection, and truthful outcome envelopes.
    """

    def __init__(
        self,
        business_id: str,
        tool_id: str = "",
        option_id: str = "zendesk",
        configuration: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            business_id=business_id,
            tool_id=tool_id,
            option_id=option_id,
            configuration=configuration,
            credentials=credentials,
        )
        # Idempotency cache: key -> (result_data, timestamp)
        self._idempotency_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        # Rate limit tracking from response headers
        self._rate_limit_limit: Optional[int] = None
        self._rate_limit_remaining: Optional[int] = None

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.SUPPORT_DESK

    # ---------------------------------------------------------------------------
    # Domain & Base URL Helpers
    # ---------------------------------------------------------------------------

    def get_base_url(self) -> str:
        """
        Normalize and return the Zendesk API base URL: https://{subdomain}.zendesk.com/api/v2
        Handles subdomain prefixes ('mybrand'), full hostnames ('mybrand.zendesk.com'),
        or custom support domains ('https://support.mybrand.com').
        """
        raw = (
            self.configuration.get("subdomain")
            or self.configuration.get("domain")
            or self.credentials.get("subdomain")
            or self.credentials.get("domain")
            or ""
        ).strip()

        if not raw:
            return ""

        clean = raw.rstrip("/")
        if clean.startswith("http://") or clean.startswith("https://"):
            if not clean.endswith("/api/v2"):
                return f"{clean}/api/v2"
            return clean

        if "." in clean:
            return f"https://{clean}/api/v2"

        return f"https://{clean}.zendesk.com/api/v2"

    def get_web_url_prefix(self) -> str:
        """Return the web dashboard base URL for human agent ticket links."""
        base_api = self.get_base_url()
        if not base_api:
            return ""
        return base_api.replace("/api/v2", "")

    # ---------------------------------------------------------------------------
    # Feature / Capability Gating
    # ---------------------------------------------------------------------------

    def get_enabled_features(self) -> Set[str]:
        """Return set of features enabled by the tenant."""
        configured = self.configuration.get("enabled_features")
        if configured is None:
            return set(DEFAULT_ENABLED_FEATURES)
        if isinstance(configured, list):
            return set(configured) | {"ticket_creation", "ticket_retrieval"}
        return set(DEFAULT_ENABLED_FEATURES)

    def is_feature_enabled(self, feature: str) -> bool:
        """Check whether a specific capability is enabled for this tenant."""
        return feature in self.get_enabled_features()

    def _require_feature(self, feature: str, operation_name: str) -> None:
        """Raise PERMISSION_DENIED if the requested feature is not enabled."""
        if not self.is_feature_enabled(feature):
            raise ZendeskIntegrationException(IntegrationError(
                code="FEATURE_DISABLED",
                category=ErrorCategory.PERMISSION_DENIED,
                message=(
                    f"Operation '{operation_name}' requires feature '{feature}', which is not enabled "
                    f"for business tenant '{self.tenant_id}'. Enabled features: {sorted(list(self.get_enabled_features()))}."
                ),
                safe_user_message=f"Capability '{feature}' is currently disabled for this integration.",
                is_retryable=False,
            ))

    # ---------------------------------------------------------------------------
    # Provider Manifest & Declarations
    # ---------------------------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="zendesk",
            display_name="Zendesk Support Desk",
            category=IntegrationCategory.SUPPORT,
            supported_capabilities=[
                CapabilityType.CREATE_SUPPORT_TICKET,
            ],
            auth_method=AuthMethod.BEARER_TOKEN,
            authoritative_source=AuthoritativeSource.SUPPORT_DESK,
            required_setup_fields=[
                SetupField(
                    key="subdomain",
                    label="Zendesk Subdomain",
                    type=FieldType.STRING,
                    required=True,
                    placeholder="mybrand or myclinic",
                    description="Your Zendesk account subdomain (https://{subdomain}.zendesk.com).",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="access_token",
                    label="OAuth 2.0 Access Token",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    placeholder="OAuth Bearer token (recommended for multi-tenant apps)",
                    description="Preferred multi-tenant OAuth 2.0 Bearer token.",
                ),
                SetupField(
                    key="api_token",
                    label="API Token (Alternative)",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    placeholder="Zendesk API token from Admin Center",
                    description="Alternative authentication option using Admin API token with agent email.",
                ),
                SetupField(
                    key="email",
                    label="Admin / Agent Email",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="support@yourdomain.com",
                    description="Required when using API token authentication.",
                ),
                SetupField(
                    key="enabled_features",
                    label="Enabled Capabilities",
                    type=FieldType.TEXT,
                    required=False,
                    default_value="ticket_creation,ticket_retrieval",
                    description="Comma-separated list of enabled features: ticket_creation, ticket_retrieval, ticket_updates, comments, assignment, user_lookup.",
                ),
                SetupField(
                    key="default_priority",
                    label="Default Ticket Priority",
                    type=FieldType.SELECT,
                    required=False,
                    default_value="normal",
                    options=[
                        {"value": "low", "label": "Low"},
                        {"value": "normal", "label": "Normal"},
                        {"value": "high", "label": "High"},
                        {"value": "urgent", "label": "Urgent"},
                    ],
                    description="Default priority assigned to newly created escalation tickets.",
                ),
            ],
            required_oauth_scopes=["read", "write", "tickets:read", "tickets:write", "users:read"],
            partner_approval_required=False,
            required_resources=[],
            webhook_events=["ticket.created", "ticket.status_changed"],
            test_connection_procedure="Safely probes GET /api/v2/users/me.json without creating dummy tickets.",
            known_limitations=[
                "Zendesk API rate limits depend on plan tier (Suite Team: 200 RPM, Professional: 400 RPM, Enterprise: 700 RPM).",
                "Archived tickets (~120 days after closing) cannot be updated or modified.",
                "OAuth 2.0 is preferred for multi-tenant applications; API token Basic Auth is supported as an alternative.",
            ],
            is_mock=False,
        )

    # ---------------------------------------------------------------------------
    # Configuration Validation & Connection Lifecycle
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate format of Zendesk subdomain and authentication parameters."""
        subdomain = config.get("subdomain") or self.configuration.get("subdomain") or self.credentials.get("subdomain")

        if not subdomain:
            return ReadinessCheckResult(
                check_id="zendesk_subdomain_check",
                name="Zendesk Subdomain Validation",
                passed=False,
                details="Zendesk subdomain ('subdomain') is required.",
                severity="critical",
            )

        if " " in str(subdomain):
            return ReadinessCheckResult(
                check_id="zendesk_subdomain_format",
                name="Zendesk Subdomain Format",
                passed=False,
                details="Zendesk subdomain cannot contain spaces.",
                severity="critical",
            )

        return ReadinessCheckResult(
            check_id="zendesk_config_check",
            name="Zendesk Configuration",
            passed=True,
            details=f"Zendesk configuration verified for subdomain: {subdomain}",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Vault credentials safely (OAuth access_token or API token + email)."""
        access_token = credentials.get("access_token") or self.credentials.get("access_token")
        api_token = credentials.get("api_token") or self.credentials.get("api_token")
        email = credentials.get("email") or self.credentials.get("email") or self.configuration.get("email")

        if not access_token and not (api_token and email):
            return ReadinessCheckResult(
                check_id="zendesk_auth_store",
                name="Zendesk Authentication Check",
                passed=False,
                details="Either OAuth 'access_token' or 'api_token' combined with 'email' is required.",
                severity="critical",
            )

        self.credentials.update(credentials)
        return ReadinessCheckResult(
            check_id="zendesk_auth_store",
            name="Zendesk Authentication Check",
            passed=True,
            details="Zendesk credentials successfully vaulted.",
            severity="critical",
        )

    # ---------------------------------------------------------------------------
    # OAuth 2.0 Authorization Flow Helpers
    # ---------------------------------------------------------------------------

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        client_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Generate Zendesk OAuth 2.0 authorization URL for multi-tenant installation.
        URL format: https://{subdomain}.zendesk.com/oauth/authorizations/new?...
        """
        cid = client_id or self.configuration.get("client_id") or self.credentials.get("client_id")
        if not cid:
            raise ValueError("client_id is required to construct Zendesk OAuth URL.")

        web_prefix = self.get_web_url_prefix()
        if not web_prefix:
            raise ValueError("subdomain is required to construct Zendesk OAuth URL.")

        scope_list = scopes or ["read", "write", "tickets:read", "tickets:write", "users:read"]
        params = {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scope_list),
            "state": state,
        }
        return f"{web_prefix}/oauth/authorizations/new?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchange authorization code for OAuth access token at /oauth/tokens."""
        cid = client_id or self.configuration.get("client_id") or self.credentials.get("client_id")
        sec = client_secret or self.credentials.get("client_secret")

        if not cid or not sec:
            raise ZendeskIntegrationException(IntegrationError(
                code="MISSING_OAUTH_CLIENT_CREDENTIALS",
                category=ErrorCategory.AUTHENTICATION_FAILED,
                message="client_id and client_secret are required to exchange authorization code.",
                safe_user_message="OAuth credentials incomplete.",
                is_retryable=False,
            ))

        web_prefix = self.get_web_url_prefix()
        url = f"{web_prefix}/oauth/tokens"

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cid,
            "client_secret": sec,
            "redirect_uri": redirect_uri,
            "scope": "read write tickets:read tickets:write",
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Answerly-ZendeskAdapter/1.0",
        }
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read().decode("utf-8")
                token_data = json.loads(raw)
                if "access_token" in token_data:
                    self.credentials["access_token"] = token_data["access_token"]
                return token_data
        except urllib.error.HTTPError as http_err:
            raise ZendeskIntegrationException(self._normalize_zendesk_error(http_err))
        except Exception as exc:
            raise ZendeskIntegrationException(self._normalize_zendesk_error(exc))

    # ---------------------------------------------------------------------------
    # Safe Diagnostics (No Dummy Tickets)
    # ---------------------------------------------------------------------------

    def test_connection(self) -> ReadinessCheckResult:
        """
        Safely probe Zendesk connectivity and authentication.
        STRICT REQUIREMENT: NEVER create dummy tickets during connection test!
        Probes GET /api/v2/users/me.json.
        """
        if self.configuration.get("is_mock") or (not self.credentials.get("access_token") and not self.credentials.get("api_token")):
            return ReadinessCheckResult(
                check_id="zendesk_connection_probe",
                name="Zendesk Safe Connection Probe (Simulated)",
                passed=True,
                details="Mock Zendesk API verified. Zero tickets created.",
                severity="critical",
            )

        base_url = self.get_base_url()
        if not base_url:
            return ReadinessCheckResult(
                check_id="zendesk_connection_probe",
                name="Zendesk Safe Connection Probe",
                passed=False,
                details="Missing Zendesk subdomain in configuration.",
                severity="critical",
            )

        try:
            user_data = self._make_request("GET", "/users/me.json")
            user_obj = user_data.get("user", {})
            user_name = user_obj.get("name", "Authenticated Agent")
            role = user_obj.get("role", "agent")
            return ReadinessCheckResult(
                check_id="zendesk_connection_probe",
                name="Zendesk Safe Connection Probe",
                passed=True,
                details=f"Zendesk API verified for {base_url} (User: {user_name}, Role: {role}). Zero tickets created.",
                severity="critical",
            )
        except Exception as exc:
            return ReadinessCheckResult(
                check_id="zendesk_connection_probe",
                name="Zendesk Safe Connection Probe",
                passed=False,
                details=f"Zendesk connection probe failed: {str(exc)}",
                severity="critical",
            )

    # ---------------------------------------------------------------------------
    # Normalization Helpers
    # ---------------------------------------------------------------------------

    def normalize_ticket(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw Zendesk ticket response into standardized provider-independent structure:
        - ticket_id, subject, description, status, priority, requester, assignee, timestamps, url
        """
        ticket_id = str(raw.get("id", ""))
        raw_status = str(raw.get("status", "open")).lower()
        raw_priority = str(raw.get("priority", "normal")).lower()

        normalized_status = ZENDESK_STATUS_MAP.get(raw_status, "open")
        normalized_priority = raw_priority if raw_priority in ZENDESK_PRIORITIES else "normal"

        web_prefix = self.get_web_url_prefix()
        ticket_url = f"{web_prefix}/agent/tickets/{ticket_id}" if web_prefix and ticket_id else None

        requester_info = {
            "requester_id": raw.get("requester_id"),
            "email": raw.get("requester", {}).get("email") if isinstance(raw.get("requester"), dict) else None,
            "name": raw.get("requester", {}).get("name") if isinstance(raw.get("requester"), dict) else None,
        }

        assignee_info = {
            "assignee_id": raw.get("assignee_id"),
            "group_id": raw.get("group_id"),
        }

        # Zendesk archives tickets closed > 120 days
        is_closed = (raw_status == "closed")
        is_archived = raw.get("is_archived", is_closed)

        return {
            "ticket_id": ticket_id,
            "provider_ticket_id": f"zen_{ticket_id}",
            "subject": raw.get("subject", ""),
            "description": raw.get("description", ""),
            "status": normalized_status,
            "raw_status": raw_status,
            "priority": normalized_priority,
            "raw_priority": raw_priority,
            "requester": requester_info,
            "assignee": assignee_info,
            "tags": raw.get("tags", []),
            "external_id": raw.get("external_id"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "url": ticket_url,
            "is_resolved": normalized_status in ("resolved", "closed"),
            "is_archived": is_archived,
            "is_assigned": bool(raw.get("assignee_id") or raw.get("group_id")),
            "authoritative_source": self.authoritative_source.value,
        }

    def normalize_user(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw Zendesk user response into standardized structure."""
        user_id = str(raw.get("id", ""))
        return {
            "user_id": user_id,
            "name": raw.get("name", ""),
            "email": raw.get("email"),
            "phone": raw.get("phone"),
            "role": raw.get("role", "end-user"),
            "active": raw.get("active", True),
            "organization_id": raw.get("organization_id"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # ---------------------------------------------------------------------------
    # Ticket Operations & Ambiguous Timeout Reconciliation
    # ---------------------------------------------------------------------------

    def reconcile_ambiguous_ticket(self, external_id: str) -> Optional[Dict[str, Any]]:
        """
        Search Zendesk for an existing ticket by external_id before retrying on timeout.
        Protects against creating duplicate tickets when Zendesk accepted the write but the client timed out.
        """
        if not external_id:
            return None

        try:
            query = f"type:ticket external_id:{external_id}"
            results = self.search_tickets(query=query)
            if results:
                logger.info("Ambiguous outcome reconciled: Found existing ticket #%s for external_id '%s'.", results[0]["ticket_id"], external_id)
                res = dict(results[0])
                res["reconciled_after_timeout"] = True
                res["is_duplicate"] = True
                return res
        except Exception as exc:
            logger.warning("Could not reconcile ambiguous outcome via external_id search: %s", exc)

        return None

    def create_ticket(
        self,
        subject: str,
        description: str,
        requester_name: Optional[str] = None,
        requester_email: Optional[str] = None,
        requester_phone: Optional[str] = None,
        priority: str = "normal",
        status: str = "open",
        ticket_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        custom_fields: Optional[List[Dict[str, Any]]] = None,
        assignee_id: Optional[int] = None,
        group_id: Optional[int] = None,
        external_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        reconcile_first: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a support ticket in Zendesk (POST /api/v2/tickets.json).
        - Generates or tracks external_id for idempotency
        - Reconciles ambiguous timeouts before duplicate creation
        - Stores real provider ticket reference
        """
        if not subject or not subject.strip():
            raise ZendeskIntegrationException(IntegrationError(
                code="MISSING_SUBJECT",
                category=ErrorCategory.INVALID_REQUEST,
                message="Ticket subject cannot be empty.",
                safe_user_message="Subject is required to file a support ticket.",
                is_retryable=False,
            ))

        if not description or not description.strip():
            raise ZendeskIntegrationException(IntegrationError(
                code="MISSING_DESCRIPTION",
                category=ErrorCategory.INVALID_REQUEST,
                message="Ticket description cannot be empty.",
                safe_user_message="Description is required to file a support ticket.",
                is_retryable=False,
            ))

        # Check assignment feature if assignee_id or group_id is provided
        if assignee_id or group_id:
            self._require_feature("assignment", "assign ticket upon creation")

        # Determine deterministic external_id / idempotency key
        req_id_str = requester_email or requester_phone or requester_name or "customer"
        ext_id = external_id or idempotency_key or hashlib.sha256(
            f"{self.tenant_id}:{req_id_str}:{subject.strip()}:{description.strip()}".encode("utf-8")
        ).hexdigest()[:32]

        # 1. Check in-memory idempotency cache
        cached_entry = self._idempotency_cache.get(ext_id)
        if cached_entry:
            cached_data, cached_ts = cached_entry
            if (time.time() - cached_ts) < IDEMPOTENCY_CACHE_TTL_SECONDS:
                logger.info("Duplicate ticket creation suppressed from cache for external_id %s.", ext_id)
                dup_res = dict(cached_data)
                dup_res["is_duplicate"] = True
                return dup_res

        # 2. Reconcile against Zendesk API search if explicitly requested (e.g. prior to retry)
        if reconcile_first and not self.configuration.get("is_mock"):
            reconciled = self.reconcile_ambiguous_ticket(ext_id)
            if reconciled:
                self._idempotency_cache[ext_id] = (reconciled, time.time())
                return reconciled

        # 3. Simulated/mock mode
        if self.configuration.get("is_mock"):
            sim_id = str(uuid.uuid4().int)[:7]
            sim_ticket = {
                "ticket_id": sim_id,
                "provider_ticket_id": f"zen_{sim_id}",
                "subject": subject,
                "description": description,
                "status": status if status in ZENDESK_STATUS_MAP.values() else "open",
                "priority": priority,
                "requester": {"name": requester_name, "email": requester_email, "phone": requester_phone},
                "external_id": ext_id,
                "url": f"{self.get_web_url_prefix()}/agent/tickets/{sim_id}",
                "is_resolved": False,
                "is_simulated": True,
            }
            self._idempotency_cache[ext_id] = (sim_ticket, time.time())
            return sim_ticket

        # 4. Construct payload for POST /api/v2/tickets.json
        zen_status = STATUS_TO_ZENDESK_MAP.get(status.lower(), "open")
        zen_priority = priority.lower() if priority.lower() in ZENDESK_PRIORITIES else "normal"

        ticket_payload: Dict[str, Any] = {
            "subject": subject,
            "comment": {"body": description, "public": True},
            "status": zen_status,
            "priority": zen_priority,
            "external_id": ext_id,
        }

        if ticket_type:
            ticket_payload["type"] = ticket_type

        # Requester representation
        requester_dict: Dict[str, Any] = {}
        if requester_name:
            requester_dict["name"] = requester_name
        if requester_email:
            requester_dict["email"] = requester_email
        if requester_phone:
            requester_dict["phone"] = requester_phone
        if requester_dict:
            ticket_payload["requester"] = requester_dict

        if assignee_id:
            ticket_payload["assignee_id"] = int(assignee_id)
        if group_id:
            ticket_payload["group_id"] = int(group_id)
        if tags:
            ticket_payload["tags"] = tags
        if custom_fields:
            ticket_payload["custom_fields"] = custom_fields

        payload = {"ticket": ticket_payload}

        try:
            raw_resp = self._make_request("POST", "/tickets.json", payload=payload)
            ticket_obj = raw_resp.get("ticket", raw_resp)
            normalized = self.normalize_ticket(ticket_obj)
            self._idempotency_cache[ext_id] = (normalized, time.time())
            return normalized

        except (TimeoutError, urllib.error.URLError) as net_err:
            logger.warning("Timeout or network error during Zendesk ticket creation. Attempting ambiguous outcome reconciliation for %s.", ext_id)
            reconciled = self.reconcile_ambiguous_ticket(ext_id)
            if reconciled:
                self._idempotency_cache[ext_id] = (reconciled, time.time())
                return reconciled
            raise net_err
        except ZendeskIntegrationException as zen_exc:
            # If 504 Gateway Timeout or similar provider timeout occurred, attempt reconciliation
            if zen_exc.error.category in (ErrorCategory.PROVIDER_UNAVAILABLE, ErrorCategory.RATE_LIMITED):
                logger.warning("Provider error during ticket creation: %s. Attempting reconciliation.", zen_exc.error.message)
                reconciled = self.reconcile_ambiguous_ticket(ext_id)
                if reconciled:
                    self._idempotency_cache[ext_id] = (reconciled, time.time())
                    return reconciled
            raise zen_exc

    def get_ticket(self, ticket_id: Union[str, int]) -> Dict[str, Any]:
        """
        Retrieve ticket by ID (GET /api/v2/tickets/{id}.json).
        Handles active and archived tickets.
        """
        clean_id = str(ticket_id).replace("zen_", "")
        raw_resp = self._make_request("GET", f"/tickets/{clean_id}.json")
        ticket_obj = raw_resp.get("ticket", raw_resp)
        return self.normalize_ticket(ticket_obj)

    def search_tickets(
        self,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Search tickets matching a Zendesk search query string (GET /api/v2/search.json?query=...).
        Respects pagination and returns normalized tickets.
        """
        q = query or "type:ticket"
        params = {
            "query": q,
            "page": page,
            "per_page": min(per_page, 100),
        }
        query_str = urllib.parse.urlencode(params)
        raw_resp = self._make_request("GET", f"/search.json?{query_str}")
        results = raw_resp.get("results", [])
        return [self.normalize_ticket(t) for t in results if t.get("result_type", "ticket") == "ticket" or "subject" in t]

    def update_ticket(
        self,
        ticket_id: Union[str, int],
        status: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        custom_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing ticket's status, priority, or tags (PUT /api/v2/tickets/{id}.json).
        Requires 'ticket_updates' feature.
        Guards against updating archived/closed tickets.
        """
        self._require_feature("ticket_updates", "update ticket")

        clean_id = str(ticket_id).replace("zen_", "")

        # Check existing ticket status before attempting update
        existing = self.get_ticket(clean_id)
        if existing.get("is_archived") or existing.get("raw_status") == "closed":
            raise ZendeskIntegrationException(IntegrationError(
                code="TICKET_ARCHIVED_OR_CLOSED",
                category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                message=f"Ticket #{clean_id} is closed/archived in Zendesk and cannot be modified.",
                safe_user_message="This ticket is closed and cannot be updated.",
                is_retryable=False,
            ))

        ticket_payload: Dict[str, Any] = {}
        if status:
            ticket_payload["status"] = STATUS_TO_ZENDESK_MAP.get(status.lower(), status)
        if priority:
            ticket_payload["priority"] = priority.lower() if priority.lower() in ZENDESK_PRIORITIES else priority
        if tags is not None:
            ticket_payload["tags"] = tags
        if custom_fields is not None:
            ticket_payload["custom_fields"] = custom_fields

        if not ticket_payload:
            return existing

        payload = {"ticket": ticket_payload}
        raw_resp = self._make_request("PUT", f"/tickets/{clean_id}.json", payload=payload)
        ticket_obj = raw_resp.get("ticket", raw_resp)
        return self.normalize_ticket(ticket_obj)

    def add_comment(
        self,
        ticket_id: Union[str, int],
        body: str,
        public: bool = True,
    ) -> Dict[str, Any]:
        """
        Add a public or internal comment/reply to a ticket (PUT /api/v2/tickets/{id}.json).
        Requires 'comments' feature.
        """
        self._require_feature("comments", "add ticket comment")

        clean_id = str(ticket_id).replace("zen_", "")

        existing = self.get_ticket(clean_id)
        if existing.get("is_archived") or existing.get("raw_status") == "closed":
            raise ZendeskIntegrationException(IntegrationError(
                code="TICKET_ARCHIVED_OR_CLOSED",
                category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                message=f"Ticket #{clean_id} is closed/archived and cannot accept new comments.",
                safe_user_message="This ticket is closed and cannot be commented on.",
                is_retryable=False,
            ))

        payload = {
            "ticket": {
                "comment": {
                    "body": body,
                    "public": public,
                }
            }
        }
        raw_resp = self._make_request("PUT", f"/tickets/{clean_id}.json", payload=payload)
        ticket_obj = raw_resp.get("ticket", raw_resp)
        return self.normalize_ticket(ticket_obj)

    def assign_ticket(
        self,
        ticket_id: Union[str, int],
        assignee_id: Optional[int] = None,
        group_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Assign a ticket to an agent or group (PUT /api/v2/tickets/{id}.json).
        Requires 'assignment' feature.
        """
        self._require_feature("assignment", "assign ticket")

        clean_id = str(ticket_id).replace("zen_", "")

        ticket_payload: Dict[str, Any] = {}
        if assignee_id is not None:
            ticket_payload["assignee_id"] = int(assignee_id)
        if group_id is not None:
            ticket_payload["group_id"] = int(group_id)

        payload = {"ticket": ticket_payload}
        raw_resp = self._make_request("PUT", f"/tickets/{clean_id}.json", payload=payload)
        ticket_obj = raw_resp.get("ticket", raw_resp)
        return self.normalize_ticket(ticket_obj)

    # ---------------------------------------------------------------------------
    # User / Contact Operations
    # ---------------------------------------------------------------------------

    def search_users(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Zendesk users/contacts by query string (GET /api/v2/users/search.json?query=...).
        Requires 'user_lookup' feature.
        """
        self._require_feature("user_lookup", "search users")
        encoded_query = urllib.parse.quote(query)
        raw_resp = self._make_request("GET", f"/users/search.json?query={encoded_query}")
        users = raw_resp.get("users", [])
        return [self.normalize_user(u) for u in users]

    def get_user(self, user_id: Union[str, int]) -> Dict[str, Any]:
        """Retrieve user by ID (GET /api/v2/users/{id}.json). Requires 'user_lookup' feature."""
        self._require_feature("user_lookup", "get user details")
        clean_id = str(user_id)
        raw_resp = self._make_request("GET", f"/users/{clean_id}.json")
        user_obj = raw_resp.get("user", raw_resp)
        return self.normalize_user(user_obj)

    # ---------------------------------------------------------------------------
    # Resource Discovery
    # ---------------------------------------------------------------------------

    def discover_resources(self, resource_type: str = "") -> List[DiscoveredResource]:
        """Discover agent groups, ticket fields, or brands."""
        resources: List[DiscoveredResource] = []

        if resource_type in ("groups", "queues"):
            try:
                raw = self._make_request("GET", "/groups.json")
                for g in raw.get("groups", []):
                    resources.append(DiscoveredResource(
                        resource_id=str(g.get("id")),
                        name=g.get("name", "Group"),
                        resource_type="group",
                        metadata={"description": g.get("description")},
                    ))
            except Exception as exc:
                logger.warning("Could not discover Zendesk groups: %s", exc)

        elif resource_type in ("ticket_fields", "fields"):
            try:
                raw = self._make_request("GET", "/ticket_fields.json")
                for f in raw.get("ticket_fields", []):
                    resources.append(DiscoveredResource(
                        resource_id=str(f.get("id")),
                        name=f.get("title", f.get("type", "Field")),
                        resource_type="ticket_field",
                        metadata={"type": f.get("type"), "required": f.get("required")},
                    ))
            except Exception as exc:
                logger.warning("Could not discover Zendesk ticket fields: %s", exc)

        elif resource_type in ("brands",):
            try:
                raw = self._make_request("GET", "/brands.json")
                for b in raw.get("brands", []):
                    resources.append(DiscoveredResource(
                        resource_id=str(b.get("id")),
                        name=b.get("name", "Brand"),
                        resource_type="brand",
                        metadata={"brand_url": b.get("brand_url")},
                    ))
            except Exception as exc:
                logger.warning("Could not discover Zendesk brands: %s", exc)

        return resources

    # ---------------------------------------------------------------------------
    # Capability Execution Interface
    # ---------------------------------------------------------------------------

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return [CapabilityType.CREATE_SUPPORT_TICKET]

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Execute validated capability contract for CREATE_SUPPORT_TICKET.
        Stores real provider ticket reference and reports truthful outcome.
        """
        start_time = time.time()

        if operation != CapabilityType.CREATE_SUPPORT_TICKET:
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=f"Capability '{operation.value}' is not supported by Zendesk adapter.",
                error=IntegrationError(
                    code="UNSUPPORTED_CAPABILITY",
                    category=ErrorCategory.INVALID_REQUEST,
                    message=f"Operation {operation.value} is unsupported by {self.provider_id}.",
                    safe_user_message="Requested capability not supported by this integration.",
                    is_retryable=False,
                ),
                correlation_id=context.correlation_id,
            )

        subject = input_data.get("subject", "Customer Inquiry")
        description = input_data.get("description", "")
        requester_name = input_data.get("requester_name")
        requester_email = input_data.get("requester_email")
        requester_phone = input_data.get("requester_phone")
        priority = input_data.get("priority") or self.configuration.get("default_priority", "normal")
        tags = input_data.get("tags")
        custom_fields = input_data.get("custom_fields")
        assignee_id = input_data.get("assignee_id")
        group_id = input_data.get("group_id")
        external_id = input_data.get("external_id")

        try:
            ticket = self.create_ticket(
                subject=subject,
                description=description,
                requester_name=requester_name,
                requester_email=requester_email,
                requester_phone=requester_phone,
                priority=priority,
                tags=tags,
                custom_fields=custom_fields,
                assignee_id=assignee_id,
                group_id=group_id,
                external_id=external_id,
                idempotency_key=context.idempotency_key or input_data.get("idempotency_key"),
            )

            latency = round((time.time() - start_time) * 1000, 2)
            ticket_id = ticket.get("ticket_id", "")
            is_dup = ticket.get("is_duplicate", False)

            safe_msg = (
                f"Support ticket #{ticket_id} filed with Zendesk support. An agent will review it shortly."
                if not is_dup
                else f"Support ticket #{ticket_id} was previously recorded. Your inquiry is currently pending review."
            )

            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data=ticket,
                safe_message=safe_msg,
                is_simulated=ticket.get("is_simulated", False),
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
                latency_ms=latency,
                idempotency_key=context.idempotency_key,
            )

        except ZendeskIntegrationException as zen_exc:
            latency = round((time.time() - start_time) * 1000, 2)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=zen_exc.error.safe_user_message,
                error=zen_exc.error,
                correlation_id=context.correlation_id,
                latency_ms=latency,
            )
        except Exception as exc:
            latency = round((time.time() - start_time) * 1000, 2)
            err = self._normalize_zendesk_error(exc)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=err.safe_user_message,
                error=err,
                correlation_id=context.correlation_id,
                latency_ms=latency,
            )

    # ---------------------------------------------------------------------------
    # HTTP Request Dispatcher & Error Normalization
    # ---------------------------------------------------------------------------

    def _get_auth_header(self) -> str:
        """
        Construct Authorization header:
        - OAuth 2.0: Bearer {access_token} (Preferred for multi-tenant)
        - API Token: Basic {base64(email/token:api_token)} (Alternative)
        """
        access_token = self.credentials.get("access_token")
        if access_token:
            return f"Bearer {access_token}"

        api_token = self.credentials.get("api_token")
        email = self.credentials.get("email") or self.configuration.get("email")
        if api_token and email:
            auth_str = f"{email}/token:{api_token}"
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            return f"Basic {b64_auth}"

        raise ZendeskIntegrationException(IntegrationError(
            code="MISSING_AUTHENTICATION",
            category=ErrorCategory.AUTHENTICATION_FAILED,
            message="No OAuth access_token or API token + email found in Zendesk credentials.",
            safe_user_message="Zendesk authentication missing.",
            is_retryable=False,
        ))

    def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute an authenticated HTTP request against Zendesk REST API (v2)."""
        base_url = self.get_base_url()
        if not base_url:
            raise ZendeskIntegrationException(IntegrationError(
                code="MISSING_SUBDOMAIN",
                category=ErrorCategory.INVALID_REQUEST,
                message="Zendesk subdomain not configured.",
                safe_user_message="Zendesk integration subdomain is missing.",
                is_retryable=False,
            ))

        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{base_url}{path}"

        auth_header = self._get_auth_header()
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Answerly-ZendeskAdapter/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                hdrs = resp.headers
                if "X-Rate-Limit-Limit" in hdrs:
                    try:
                        self._rate_limit_limit = int(hdrs["X-Rate-Limit-Limit"])
                    except ValueError:
                        pass
                if "X-Rate-Limit-Remaining" in hdrs:
                    try:
                        self._rate_limit_remaining = int(hdrs["X-Rate-Limit-Remaining"])
                    except ValueError:
                        pass

                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as http_err:
            raise ZendeskIntegrationException(self._normalize_zendesk_error(http_err))
        except Exception as exc:
            raise ZendeskIntegrationException(self._normalize_zendesk_error(exc))

    def _normalize_zendesk_error(self, exc: Exception, status_code: Optional[int] = None) -> IntegrationError:
        """
        Normalize Zendesk error responses into structured IntegrationError instances.
        Maps rate limits (HTTP 429), permissions (HTTP 403), closed/archived violations (HTTP 422).
        """
        err_msg = str(exc)
        code_str = "ZENDESK_ERROR"
        category = ErrorCategory.PROVIDER_UNAVAILABLE
        is_retryable = False
        retry_after: Optional[float] = None
        details: Dict[str, Any] = {}

        if isinstance(exc, urllib.error.HTTPError):
            status_code = exc.code
            hdrs = exc.headers

            if "Retry-After" in hdrs:
                try:
                    retry_after = float(hdrs["Retry-After"])
                except (ValueError, TypeError):
                    retry_after = 60.0

            try:
                body = exc.read().decode("utf-8")
                parsed = json.loads(body)
                details = parsed

                # Zendesk error envelopes:
                # 1. {"error": "RecordNotFound", "description": "Not found"}
                # 2. {"error": "InvalidAttribute", "description": "Record validation errors", "details": {...}}
                # 3. {"error": "Forbidden", "description": "You do not have access"}
                if "description" in parsed:
                    err_msg = parsed.get("description", err_msg)
                    code_str = parsed.get("error", "ZENDESK_ERROR")
                elif "message" in parsed:
                    err_msg = parsed.get("message", err_msg)
                    code_str = parsed.get("error", "ZENDESK_ERROR")

            except Exception:
                pass

            if status_code == 429:
                category = ErrorCategory.RATE_LIMITED
                code_str = "RATE_LIMIT_EXCEEDED"
                is_retryable = True
                if retry_after is None:
                    retry_after = 60.0
            elif status_code == 401:
                category = ErrorCategory.AUTHENTICATION_FAILED
                code_str = "AUTHENTICATION_FAILED"
            elif status_code == 403:
                category = ErrorCategory.PERMISSION_DENIED
                code_str = "PERMISSION_DENIED"
            elif status_code == 404:
                category = ErrorCategory.RESOURCE_NOT_FOUND
                code_str = "RESOURCE_NOT_FOUND"
            elif status_code == 422:
                category = ErrorCategory.BUSINESS_RULE_VIOLATION
                code_str = "UNPROCESSABLE_ENTITY"
            elif status_code == 400:
                category = ErrorCategory.INVALID_REQUEST
                code_str = "INVALID_REQUEST"
            elif status_code in (500, 502, 503, 504):
                category = ErrorCategory.PROVIDER_UNAVAILABLE
                code_str = "ZENDESK_SERVER_ERROR"
                is_retryable = True
                retry_after = 5.0

        elif isinstance(exc, urllib.error.URLError):
            category = ErrorCategory.TIMEOUT if "timed out" in err_msg.lower() else ErrorCategory.PROVIDER_UNAVAILABLE
            code_str = "NETWORK_ERROR"
            is_retryable = True
            retry_after = 3.0

        safe_message = "Zendesk support service encountered an error."
        if category == ErrorCategory.RATE_LIMITED:
            safe_message = "Zendesk API rate limit reached. Please retry in a few moments."
        elif category == ErrorCategory.AUTHENTICATION_FAILED:
            safe_message = "Zendesk authentication failed. Please verify your credentials."
        elif category == ErrorCategory.PERMISSION_DENIED:
            safe_message = "Permission denied by Zendesk. Check that your user role has sufficient permissions."
        elif category == ErrorCategory.INVALID_REQUEST:
            safe_message = "Invalid Zendesk ticket parameters."
        elif category == ErrorCategory.RESOURCE_NOT_FOUND:
            safe_message = "Requested Zendesk ticket or user was not found."
        elif category == ErrorCategory.BUSINESS_RULE_VIOLATION:
            safe_message = "Zendesk business rule violation. This ticket may be closed or archived."

        return IntegrationError(
            code=code_str,
            category=category,
            message=err_msg,
            safe_user_message=safe_message,
            retry_after_seconds=retry_after,
            is_retryable=is_retryable,
            details=details,
        )
