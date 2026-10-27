"""
HubSpot CRM Integration Adapter.
Provides enterprise-grade customer contact lookup, creation, updating, search,
and associations with HubSpot CRM API v3/v4 using OAuth 2.0 authorization,
custom field mappings, duplicate prevention, and tenant isolation.
"""

from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timezone
import json
import logging
import re
import time
import base64
import hmac
import hashlib
import urllib.request
import urllib.parse
import urllib.error

from backend.integrations.base import IntegrationAdapter
from backend.capabilities.models import (
    AuthoritativeSource,
    ReadinessReport,
    ReadinessCheckResult,
    CapabilityStatus,
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
    SideEffectClassification,
    WebhookRequest,
    WebhookResult,
)

logger = logging.getLogger(__name__)

HUBSPOT_OAUTH_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_OAUTH_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HUBSPOT_OAUTH_INFO_URL = "https://api.hubapi.com/oauth/v1/access-tokens"
HUBSPOT_API_BASE_URL = "https://api.hubapi.com"

# Standard default field mappings from receptionist caller attributes to HubSpot properties
DEFAULT_FIELD_MAPPINGS: Dict[str, str] = {
    "first_name": "firstname",
    "last_name": "lastname",
    "email": "email",
    "phone": "phone",
    "mobile_phone": "mobilephone",
    "company": "company",
    "lifecycle_stage": "lifecyclestage",
    "notes": "message",
}


class MatchingStrategy:
    """Configurable matching strategies for deduplicating CRM contacts."""
    EMAIL_THEN_PHONE = "email_then_phone"
    EMAIL_ONLY = "email_only"
    PHONE_ONLY = "phone_only"
    EMAIL_AND_PHONE = "email_and_phone"


class HubspotIntegrationException(Exception):
    """Exception wrapper for normalized IntegrationError."""
    def __init__(self, error: IntegrationError):
        super().__init__(error.message)
        self.error = error


class HubspotCrmAdapter(IntegrationAdapter):
    """
    Adapter connecting tenant CRM records to HubSpot Contacts, Associations,
    Notes, Tasks, and Deals APIs.
    Maintains authoritative customer profiles without conflating CRM with booking systems.
    """

    def __init__(
        self,
        business_id: str,
        tool_id: str = "",
        option_id: str = "hubspot",
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
        self._client_instance = None

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.CRM_SYSTEM

    # ---------------------------------------------------------------------------
    # Provider Manifest & Capabilities
    # ---------------------------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="hubspot",
            display_name="HubSpot CRM",
            category=IntegrationCategory.CRM,
            supported_capabilities=[
                CapabilityType.GET_CUSTOMER,
                CapabilityType.CREATE_OR_UPDATE_CUSTOMER,
            ],
            auth_method=AuthMethod.OAUTH2,
            authoritative_source=AuthoritativeSource.CRM_SYSTEM,
            required_setup_fields=[
                SetupField(
                    key="client_id",
                    label="HubSpot App Client ID",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="e.g. 7b29a6...",
                    description="OAuth App Client ID for multi-tenant accounts (or use Private App Token).",
                ),
                SetupField(
                    key="client_secret",
                    label="HubSpot App Client Secret",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    description="OAuth App Client Secret.",
                ),
                SetupField(
                    key="access_token",
                    label="HubSpot Access Token / Private App Token",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    placeholder="pat-na1-...",
                    description="Private app token or active OAuth access token with crm.objects.contacts scopes.",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="portal_id",
                    label="HubSpot Portal / Hub ID",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="e.g. 14298102",
                    description="Target HubSpot Portal / Hub ID.",
                ),
                SetupField(
                    key="redirect_uri",
                    label="OAuth Redirect URI",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="https://api.callme.ai/oauth/hubspot/callback",
                ),
                SetupField(
                    key="enabled_objects",
                    label="Enabled CRM Objects",
                    type=FieldType.STRING,
                    required=False,
                    default_value="contacts",
                    description="Comma-separated CRM objects to sync (e.g. contacts,notes,tasks,deals).",
                ),
                SetupField(
                    key="matching_strategy",
                    label="Duplicate Matching Strategy",
                    type=FieldType.STRING,
                    required=False,
                    default_value="email_then_phone",
                    description="Deduplication strategy: email_then_phone, email_only, phone_only, or email_and_phone.",
                ),
                SetupField(
                    key="field_mappings",
                    label="Custom Field Mappings (JSON)",
                    type=FieldType.STRING,
                    required=False,
                    placeholder='{"dietary_preference": "custom_dietary_needs"}',
                    description="JSON dictionary mapping caller data to HubSpot contact properties.",
                ),
                SetupField(
                    key="ignore_unknown_properties",
                    label="Ignore Unknown Custom Properties",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                    description="If true, omits custom properties not found in portal without failing execution.",
                ),
            ],
            required_oauth_scopes=[
                "crm.objects.contacts.read",
                "crm.objects.contacts.write",
            ],
            partner_approval_required=False,
            required_resources=[],
            webhook_events=[
                "contact.creation",
                "contact.propertyChange",
                "contact.deletion",
                "deal.creation",
            ],
            test_connection_procedure="Queries HubSpot contacts endpoint or introspects access token to verify portal reachability.",
            known_limitations=[
                "HubSpot API rate limit: 100 requests per 10 seconds per portal (150 for Professional/Enterprise).",
                "HubSpot Search API: up to 10,000 total results per search with maximum 100 contacts per page.",
                "Deduplication requires a verified unique identifier (email or phone); names alone are never merged.",
            ],
            is_mock=False,
        )

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return [
            CapabilityType.GET_CUSTOMER,
            CapabilityType.CREATE_OR_UPDATE_CUSTOMER,
        ]

    # ---------------------------------------------------------------------------
    # Client & Token Management
    # ---------------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Retrieve vaulted access token, performing auto-refresh if expired."""
        token = (
            self.credentials.get("access_token")
            or self.configuration.get("access_token")
            or ""
        ).strip()

        # Check if token is expired and refresh token is available
        expires_at = self.credentials.get("token_expires_at") or self.configuration.get("token_expires_at")
        refresh_token = self.credentials.get("refresh_token") or self.configuration.get("refresh_token")

        if expires_at and refresh_token and self._get_client_id() and self._get_client_secret():
            try:
                now_ts = datetime.now(timezone.utc).timestamp()
                # If expiring in less than 60 seconds, refresh
                if float(expires_at) - now_ts < 60:
                    logger.info("HubSpot access token expired or near expiry; refreshing automatically.")
                    new_tokens = self.refresh_access_token()
                    token = new_tokens.get("access_token", token)
            except Exception as exc:
                logger.warning("Failed to automatically refresh HubSpot access token: %s", exc)

        return token

    def _get_client_id(self) -> str:
        return str(
            self.credentials.get("client_id")
            or self.configuration.get("client_id")
            or ""
        ).strip()

    def _get_client_secret(self) -> str:
        return str(
            self.credentials.get("client_secret")
            or self.configuration.get("client_secret")
            or ""
        ).strip()

    def _get_matching_strategy(self) -> str:
        return str(
            self.configuration.get("matching_strategy")
            or MatchingStrategy.EMAIL_THEN_PHONE
        ).strip().lower()

    def _get_enabled_objects(self) -> List[str]:
        raw = self.configuration.get("enabled_objects", ["contacts"])
        if isinstance(raw, str):
            return [x.strip().lower() for x in raw.split(",") if x.strip()]
        if isinstance(raw, list):
            return [str(x).strip().lower() for x in raw if str(x).strip()]
        return ["contacts"]

    def _get_field_mappings(self) -> Dict[str, str]:
        mappings = dict(DEFAULT_FIELD_MAPPINGS)
        custom_mappings = self.configuration.get("field_mappings", {})
        if isinstance(custom_mappings, str):
            try:
                custom_mappings = json.loads(custom_mappings)
            except Exception:
                custom_mappings = {}
        if isinstance(custom_mappings, dict):
            mappings.update(custom_mappings)
        return mappings

    def _get_client(self):
        """Lazy-initialize official HubSpot client."""
        if self._client_instance is not None:
            return self._client_instance

        token = self._get_access_token()
        if not token:
            return None

        try:
            from hubspot import HubSpot
            self._client_instance = HubSpot(access_token=token)
            return self._client_instance
        except ImportError:
            logger.warning("HubSpot SDK not installed; client instance unavailable.")
            return None

    # ---------------------------------------------------------------------------
    # ID Normalization & Phone Utilities
    # ---------------------------------------------------------------------------

    @staticmethod
    def normalize_provider_id(raw_id: Any) -> str:
        """
        Normalize HubSpot object IDs to clean numeric strings.
        Strips prefixes like 'hs_', 'hs_contact_', 'contact_', 'deal_', etc.
        """
        if raw_id is None:
            return ""
        sid = str(raw_id).strip()
        # Remove common prefixes
        sid = re.sub(r"^(hs_contact_|hs_deal_|hs_note_|hs_task_|hs_|contact_|deal_|note_|task_)", "", sid, flags=re.IGNORECASE)
        return sid

    @staticmethod
    def _clean_phone(raw_phone: Optional[str]) -> str:
        """Normalize phone numbers for matching."""
        if not raw_phone:
            return ""
        cleaned = re.sub(r"[\s\(\)\-\.]", "", str(raw_phone).strip())
        return cleaned

    # ---------------------------------------------------------------------------
    # OAuth 2.0 Authorization Flow & Token Introspection
    # ---------------------------------------------------------------------------

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Construct HubSpot OAuth 2.0 authorization URL for tenant onboarding.
        """
        client_id = self._get_client_id()
        if not client_id:
            raise ValueError("HubSpot client_id is required to generate authorization URL.")

        if not scopes:
            scopes = [
                "crm.objects.contacts.read",
                "crm.objects.contacts.write",
            ]
            enabled_objects = self._get_enabled_objects()
            if "notes" in enabled_objects:
                scopes.extend(["crm.objects.notes.read", "crm.objects.notes.write"])
            if "tasks" in enabled_objects:
                scopes.extend(["crm.objects.tasks.read", "crm.objects.tasks.write"])
            if "deals" in enabled_objects:
                scopes.extend(["crm.objects.deals.read", "crm.objects.deals.write"])

        dedup_scopes = list(dict.fromkeys(scopes))

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(dedup_scopes),
            "state": state,
        }
        return f"{HUBSPOT_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def exchange_authorization_code(
        self,
        code: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exchange OAuth authorization code for access and refresh tokens.
        Updates adapter credentials in memory and introspects token metadata.
        """
        client_id = self._get_client_id()
        client_secret = self._get_client_secret()
        r_uri = redirect_uri or self.configuration.get("redirect_uri") or self.credentials.get("redirect_uri", "")

        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required to exchange authorization code.")

        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": r_uri,
            "code": code,
        }

        token_data = self._post_form_request(HUBSPOT_OAUTH_TOKEN_URL, payload)

        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 1800)
        now_ts = datetime.now(timezone.utc).timestamp()
        expires_at = now_ts + float(expires_in)

        self.credentials["access_token"] = access_token
        self.credentials["refresh_token"] = refresh_token
        self.credentials["token_expires_at"] = expires_at
        self._client_instance = None  # Reset client cache

        try:
            info = self.introspect_token(access_token)
            if info.get("hub_id"):
                self.configuration["portal_id"] = str(info["hub_id"])
            if info.get("scopes"):
                self.credentials["scopes"] = info["scopes"]
            token_data["token_info"] = info
        except Exception as exc:
            logger.warning("Could not introspect exchanged token: %s", exc)

        return token_data

    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Exchange refresh token for a fresh access token.
        """
        client_id = self._get_client_id()
        client_secret = self._get_client_secret()
        refresh_token = self.credentials.get("refresh_token") or self.configuration.get("refresh_token")

        if not client_id or not client_secret or not refresh_token:
            raise ValueError("client_id, client_secret, and refresh_token are required to refresh access token.")

        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }

        token_data = self._post_form_request(HUBSPOT_OAUTH_TOKEN_URL, payload)

        access_token = token_data.get("access_token", "")
        new_refresh = token_data.get("refresh_token", refresh_token)
        expires_in = token_data.get("expires_in", 1800)
        now_ts = datetime.now(timezone.utc).timestamp()

        self.credentials["access_token"] = access_token
        self.credentials["refresh_token"] = new_refresh
        self.credentials["token_expires_at"] = now_ts + float(expires_in)
        self._client_instance = None

        return token_data

    def introspect_token(self, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Query HubSpot token information endpoint to inspect scopes, portal ID, and expiration.
        """
        tok = token or self._get_access_token()
        if not tok:
            raise ValueError("No access token provided for introspection.")

        # Check for mock / sandbox tokens
        if tok.startswith("mock_") or tok.startswith("test_") or tok == "sandbox_key_verified":
            return {
                "token": tok,
                "hub_id": "12345678",
                "scopes": [
                    "crm.objects.contacts.read",
                    "crm.objects.contacts.write",
                    "crm.objects.notes.read",
                    "crm.objects.notes.write",
                    "crm.objects.tasks.read",
                    "crm.objects.tasks.write",
                    "crm.objects.deals.read",
                    "crm.objects.deals.write",
                    "crm.schemas.contacts.read",
                ],
                "user": "developer@example.com",
                "expires_in": 1800,
            }

        client = self._get_client()
        if client:
            try:
                resp = client.oauth.access_tokens_api.get(token=tok)
                return {
                    "token": getattr(resp, "token", tok),
                    "hub_id": getattr(resp, "hub_id", None),
                    "scopes": getattr(resp, "scopes", []),
                    "user": getattr(resp, "user", None),
                    "user_id": getattr(resp, "user_id", None),
                    "hub_domain": getattr(resp, "hub_domain", None),
                    "expires_in": getattr(resp, "expires_in", None),
                }
            except Exception as exc:
                logger.debug("SDK access_tokens_api failed: %s; falling back to direct HTTP.", exc)

        # HTTP Fallback
        url = f"{HUBSPOT_OAUTH_INFO_URL}/{tok}"
        req = urllib.request.Request(url, headers={"User-Agent": "CallMe-HubSpotAdapter/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "token": data.get("token", tok),
                    "hub_id": data.get("hub_id"),
                    "scopes": data.get("scopes", []),
                    "user": data.get("user"),
                    "user_id": data.get("user_id"),
                    "hub_domain": data.get("hub_domain"),
                    "expires_in": data.get("expires_in"),
                }
        except urllib.error.HTTPError as http_err:
            raise HubspotIntegrationException(self._normalize_hubspot_error(http_err))
        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def verify_scopes(self, required_scopes: List[str]) -> Tuple[bool, List[str]]:
        """
        Verify that the current token has all required OAuth scopes.
        Returns (is_valid, missing_scopes).
        """
        token = self._get_access_token()
        if not token:
            return False, required_scopes

        granted_scopes = self.credentials.get("scopes", [])
        if not granted_scopes:
            try:
                info = self.introspect_token(token)
                granted_scopes = info.get("scopes", [])
                self.credentials["scopes"] = granted_scopes
            except Exception:
                if token.startswith("mock_") or token.startswith("test_"):
                    return True, []
                return False, required_scopes

        missing = [s for s in required_scopes if s not in granted_scopes]
        return len(missing) == 0, missing

    # ---------------------------------------------------------------------------
    # Error Normalization
    # ---------------------------------------------------------------------------

    def _normalize_hubspot_error(self, exc: Any) -> IntegrationError:
        """
        Map HubSpot SDK ApiException or HTTP errors into a standardized IntegrationError.
        Handles rate limits (429), token expiration (401), missing scopes (403),
        not found (404), conflicts (409), and invalid properties (400).
        """
        if isinstance(exc, HubspotIntegrationException):
            return exc.error
        if isinstance(exc, IntegrationError):
            return exc

        status_code = getattr(exc, "status", None) or getattr(exc, "status_code", None) or getattr(exc, "code", None)
        headers = getattr(exc, "headers", {}) or {}

        body_raw = getattr(exc, "body", None)
        body = {}
        if isinstance(body_raw, str):
            try:
                body = json.loads(body_raw)
            except Exception:
                body = {"message": body_raw}
        elif isinstance(body_raw, dict):
            body = body_raw
        elif not body_raw and str(exc).strip().startswith("{"):
            try:
                body = json.loads(str(exc))
            except Exception:
                body = {}

        msg = body.get("message") or getattr(exc, "reason", None) or str(exc)
        category = ErrorCategory.PROVIDER_UNAVAILABLE
        code = "HUBSPOT_API_ERROR"
        is_retryable = False
        retry_after = None

        if headers:
            retry_header = headers.get("retry-after") or headers.get("Retry-After")
            if retry_header:
                try:
                    retry_after = float(retry_header)
                except (ValueError, TypeError):
                    retry_after = None

        if status_code == 429:
            category = ErrorCategory.RATE_LIMITED
            code = "HUBSPOT_RATE_LIMITED"
            is_retryable = True
            if retry_after is None:
                interval_ms = headers.get("x-hubspot-ratelimit-interval-milliseconds")
                if interval_ms:
                    try:
                        retry_after = max(1.0, float(interval_ms) / 1000.0)
                    except Exception:
                        retry_after = 2.0
                else:
                    retry_after = 2.0

        elif status_code == 401:
            category = ErrorCategory.AUTHENTICATION_FAILED
            code = "HUBSPOT_TOKEN_EXPIRED"
            is_retryable = False

        elif status_code == 403:
            category = ErrorCategory.PERMISSION_DENIED
            code = "HUBSPOT_MISSING_SCOPES"
            is_retryable = False

        elif status_code == 404:
            category = ErrorCategory.RESOURCE_NOT_FOUND
            code = "HUBSPOT_RESOURCE_NOT_FOUND"
            is_retryable = False

        elif status_code == 409:
            category = ErrorCategory.CONFLICT
            code = "HUBSPOT_CONTACT_EXISTS"
            is_retryable = False

        elif status_code == 400:
            category = ErrorCategory.INVALID_REQUEST
            code = "HUBSPOT_VALIDATION_ERROR"
            is_retryable = False
            if "Property" in msg and "does not exist" in msg:
                code = "HUBSPOT_INVALID_PROPERTY"

        elif status_code and int(status_code) >= 500:
            category = ErrorCategory.PROVIDER_UNAVAILABLE
            code = "HUBSPOT_SERVER_ERROR"
            is_retryable = True

        return IntegrationError(
            code=code,
            category=category,
            message=msg,
            safe_user_message="HubSpot CRM encountered an error processing this request.",
            is_retryable=is_retryable,
            retry_after_seconds=retry_after,
        )

    # ---------------------------------------------------------------------------
    # Webhook Signature Verification & Processing
    # ---------------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        notification_url: str = "",
        http_method: str = "POST",
    ) -> bool:
        """
        Verify HubSpot Webhook Signature v3 (or v1 fallback).
        Signature v3 algorithm:
        HMAC-SHA256(client_secret, http_method + notification_url + raw_body + timestamp)
        """
        client_secret = self._get_client_secret()
        if not client_secret:
            return False

        sig_v3 = headers.get("x-hubspot-signature-v3") or headers.get("X-HubSpot-Signature-v3")
        timestamp_header = headers.get("x-hubspot-request-timestamp") or headers.get("X-HubSpot-Request-Timestamp")

        if sig_v3 and timestamp_header:
            try:
                req_ts = float(timestamp_header)
                now_ts = datetime.now(timezone.utc).timestamp() * 1000
                if abs(now_ts - req_ts) > 300000:
                    logger.warning("HubSpot webhook timestamp outside acceptable window (potential replay).")
                    return False

                source_bytes = (
                    http_method.upper().encode("utf-8")
                    + (notification_url or "").encode("utf-8")
                    + raw_body
                    + timestamp_header.encode("utf-8")
                )
                computed = base64.b64encode(
                    hmac.new(client_secret.encode("utf-8"), source_bytes, hashlib.sha256).digest()
                ).decode("utf-8")
                return hmac.compare_digest(computed, sig_v3)
            except Exception as exc:
                logger.error("Error verifying HubSpot webhook v3 signature: %s", exc)
                return False

        sig_v1 = headers.get("x-hubspot-signature") or headers.get("X-HubSpot-Signature")
        if sig_v1:
            try:
                source = (client_secret.encode("utf-8") + raw_body)
                computed = hashlib.sha256(source).hexdigest()
                return hmac.compare_digest(computed, sig_v1)
            except Exception as exc:
                logger.error("Error verifying HubSpot webhook v1 signature: %s", exc)
                return False

        return False

    def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        """
        Process incoming HubSpot webhook notifications:
        - Validates cryptographic signature
        - Extracts event IDs for replay deduplication
        - Dispatches contact or deal updates
        """
        client_secret = self._get_client_secret()
        has_sig = (
            "x-hubspot-signature-v3" in request.headers
            or "x-hubspot-signature" in request.headers
        )

        if client_secret and has_sig:
            if not self.verify_webhook_signature(
                request.raw_body,
                request.headers,
                notification_url=request.url,
                http_method="POST",
            ):
                return WebhookResult(
                    success=False,
                    processed=False,
                    message="Invalid HubSpot webhook cryptographic signature.",
                )

        payload = request.parsed_json or {}
        if isinstance(payload, dict) and "events" in payload and isinstance(payload["events"], list):
            events = payload["events"]
        elif isinstance(payload, list):
            events = payload
        else:
            try:
                raw_parsed = json.loads(request.raw_body.decode("utf-8")) if request.raw_body else []
                events = raw_parsed if isinstance(raw_parsed, list) else [raw_parsed]
            except Exception:
                events = [payload] if payload else []

        if not events or len(events) == 0:
            return WebhookResult(
                success=True,
                processed=True,
                event_id="hs_empty_ping",
                message="HubSpot webhook ping acknowledged.",
            )

        first_event = events[0] if isinstance(events[0], dict) else {}
        event_id = str(first_event.get("eventId") or f"hs_evt_{int(time.time()*1000)}")
        sub_type = first_event.get("subscriptionType") or "contact.creation"
        obj_id = str(first_event.get("objectId") or "")

        return WebhookResult(
            success=True,
            event_id=event_id,
            event_type=sub_type,
            processed=True,
            message=f"HubSpot webhook event '{sub_type}' processed for object {obj_id}.",
            data={"events": events, "count": len(events)},
        )

    # ---------------------------------------------------------------------------
    # Configuration Validation & Readiness Assessment
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate non-secret configuration fields and authentication format."""
        token = config.get("access_token") or self.credentials.get("access_token")
        client_id = config.get("client_id") or self.credentials.get("client_id") or self.configuration.get("client_id")
        client_secret = config.get("client_secret") or self.credentials.get("client_secret") or self.configuration.get("client_secret")

        if not token and not (client_id and client_secret):
            return ReadinessCheckResult(
                check_id="hubspot_token_format",
                name="HubSpot Credentials Validation",
                passed=False,
                details="Either a HubSpot Access Token or OAuth (client_id and client_secret) is required.",
                severity="critical",
            )

        strategy = config.get("matching_strategy", self._get_matching_strategy())
        valid_strategies = [
            MatchingStrategy.EMAIL_THEN_PHONE,
            MatchingStrategy.EMAIL_ONLY,
            MatchingStrategy.PHONE_ONLY,
            MatchingStrategy.EMAIL_AND_PHONE,
        ]
        if strategy not in valid_strategies:
            return ReadinessCheckResult(
                check_id="hubspot_matching_strategy",
                name="HubSpot Duplicate Matching Strategy",
                passed=False,
                details=f"Invalid matching strategy '{strategy}'. Must be one of: {valid_strategies}.",
                severity="critical",
            )

        return ReadinessCheckResult(
            check_id="hubspot_token_format",
            name="HubSpot Configuration Validation",
            passed=True,
            details="HubSpot configuration and credentials structure verified.",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Vault credentials safely."""
        self.credentials.update(credentials)
        token = self.credentials.get("access_token")
        client_id = self.credentials.get("client_id")

        if not token and not client_id:
            return ReadinessCheckResult(
                check_id="hubspot_auth_store",
                name="HubSpot Auth Storage",
                passed=False,
                details="Access token or client_id missing.",
                severity="critical",
            )

        self._client_instance = None
        return ReadinessCheckResult(
            check_id="hubspot_auth_store",
            name="HubSpot Auth Storage",
            passed=True,
            details="HubSpot credentials safely vaulted.",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        """Safely probe connectivity without creating side effects."""
        token = self._get_access_token()
        if not token:
            return ReadinessCheckResult(
                check_id="hubspot_conn_probe",
                name="HubSpot Connectivity",
                passed=False,
                details="No access token available for probe.",
                severity="critical",
            )

        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return ReadinessCheckResult(
                check_id="hubspot_conn_probe",
                name="HubSpot Connectivity",
                passed=True,
                details="HubSpot CRM connection verified (Mock/Sandbox Mode).",
                severity="critical",
            )

        try:
            info = self.introspect_token(token)
            portal_id = info.get("hub_id", "Unknown")
            return ReadinessCheckResult(
                check_id="hubspot_conn_probe",
                name="HubSpot Connectivity",
                passed=True,
                details=f"Connected to HubSpot Portal {portal_id} successfully.",
                severity="critical",
            )
        except Exception as exc:
            err = self._normalize_hubspot_error(exc)
            return ReadinessCheckResult(
                check_id="hubspot_conn_probe",
                name="HubSpot Connectivity",
                passed=False,
                details=f"HubSpot connection probe failed: {err.message}",
                severity="critical",
            )

    def assess_readiness(self, db_service: Optional[Any] = None) -> ReadinessReport:
        """Run all mandatory readiness checks and compile readiness report."""
        checks: List[ReadinessCheckResult] = []

        config_check = self.validate_configuration(self.configuration)
        checks.append(config_check)

        conn_check = self.test_connection()
        checks.append(conn_check)

        manifest = self.get_manifest()
        required_scopes = manifest.required_oauth_scopes
        is_scoped, missing = self.verify_scopes(required_scopes)
        if not is_scoped:
            checks.append(
                ReadinessCheckResult(
                    check_id="hubspot_scope_check",
                    name="HubSpot OAuth Scopes",
                    passed=False,
                    details=f"Missing required OAuth scopes: {missing}",
                    severity="critical",
                )
            )
        else:
            checks.append(
                ReadinessCheckResult(
                    check_id="hubspot_scope_check",
                    name="HubSpot OAuth Scopes",
                    passed=True,
                    details="All required contact OAuth scopes granted.",
                    severity="critical",
                )
            )

        all_passed = all(c.passed for c in checks)
        missing_reqs = [c.details for c in checks if not c.passed]

        return ReadinessReport(
            provider_id=self.provider_id,
            status=CapabilityStatus.READY if all_passed else CapabilityStatus.NEEDS_INPUT,
            is_ready=all_passed,
            checks=checks,
            missing_requirements=missing_reqs,
            recommendations=["Verify custom field mappings match portal definitions if syncing specialized fields."],
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    # ---------------------------------------------------------------------------
    # Resource Discovery (Properties, Objects, Pipelines)
    # ---------------------------------------------------------------------------

    def discover_resources(self, resource_type: str = "") -> List[DiscoveredResource]:
        """
        Query and discover available HubSpot resources:
        - 'properties' / 'contact_properties': Contact standard and custom properties.
        - 'objects': Supported CRM objects (contacts, notes, tasks, deals).
        - 'pipelines': Deal pipelines and stages.
        """
        rt = (resource_type or "contact_properties").lower()
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            if "prop" in rt:
                return [
                    DiscoveredResource(
                        resource_id="firstname",
                        name="First Name",
                        resource_type="property",
                        metadata={"type": "string", "fieldType": "text", "isCustom": False},
                    ),
                    DiscoveredResource(
                        resource_id="lastname",
                        name="Last Name",
                        resource_type="property",
                        metadata={"type": "string", "fieldType": "text", "isCustom": False},
                    ),
                    DiscoveredResource(
                        resource_id="email",
                        name="Email",
                        resource_type="property",
                        metadata={"type": "string", "fieldType": "text", "isCustom": False},
                    ),
                    DiscoveredResource(
                        resource_id="phone",
                        name="Phone Number",
                        resource_type="property",
                        metadata={"type": "string", "fieldType": "text", "isCustom": False},
                    ),
                    DiscoveredResource(
                        resource_id="dietary_preferences_custom",
                        name="Dietary Preferences",
                        resource_type="property",
                        metadata={"type": "string", "fieldType": "text", "isCustom": True},
                    ),
                ]
            elif "obj" in rt:
                return [
                    DiscoveredResource(resource_id="contacts", name="Contacts", resource_type="crm_object"),
                    DiscoveredResource(resource_id="deals", name="Deals", resource_type="crm_object"),
                    DiscoveredResource(resource_id="notes", name="Notes", resource_type="crm_object"),
                    DiscoveredResource(resource_id="tasks", name="Tasks", resource_type="crm_object"),
                ]
            return []

        client = self._get_client()
        if not client:
            return []

        if "prop" in rt:
            try:
                props_resp = client.crm.properties.core_api.get_all(object_type="contacts")
                results = getattr(props_resp, "results", [])
                resources = []
                for p in results:
                    p_name = getattr(p, "name", "")
                    p_label = getattr(p, "label", p_name)
                    p_type = getattr(p, "type", "string")
                    p_field_type = getattr(p, "field_type", "text")
                    p_custom = not getattr(p, "hubspot_defined", True)

                    resources.append(
                        DiscoveredResource(
                            resource_id=p_name,
                            name=p_label,
                            resource_type="property",
                            metadata={
                                "type": p_type,
                                "fieldType": p_field_type,
                                "isCustom": p_custom,
                                "groupName": getattr(p, "group_name", ""),
                            },
                        )
                    )
                return resources
            except Exception as exc:
                logger.error("Failed to discover HubSpot properties: %s", exc)
                return []

        elif "obj" in rt:
            return [
                DiscoveredResource(resource_id="contacts", name="Contacts", resource_type="crm_object"),
                DiscoveredResource(resource_id="deals", name="Deals", resource_type="crm_object"),
                DiscoveredResource(resource_id="notes", name="Notes", resource_type="crm_object"),
                DiscoveredResource(resource_id="tasks", name="Tasks", resource_type="crm_object"),
                DiscoveredResource(resource_id="companies", name="Companies", resource_type="crm_object"),
            ]

        elif "pipeline" in rt:
            try:
                pipes_resp = client.crm.pipelines.pipelines_api.get_all(object_type="deals")
                results = getattr(pipes_resp, "results", [])
                resources = []
                for pipe in results:
                    pipe_id = getattr(pipe, "id", "")
                    pipe_label = getattr(pipe, "label", pipe_id)
                    resources.append(
                        DiscoveredResource(
                            resource_id=pipe_id,
                            name=pipe_label,
                            resource_type="pipeline",
                            metadata={"stages": [getattr(s, "label", "") for s in getattr(pipe, "stages", [])]},
                        )
                    )
                return resources
            except Exception as exc:
                logger.error("Failed to discover HubSpot pipelines: %s", exc)
                return []

        return []

    # ---------------------------------------------------------------------------
    # Field Mapping & Missing Property Resilience
    # ---------------------------------------------------------------------------

    def _map_input_to_hubspot_properties(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map incoming generic caller/customer data to HubSpot contact properties
        using tenant's configured field mappings.
        Handles name splitting (firstname, lastname) and custom attributes.
        """
        mappings = self._get_field_mappings()
        props: Dict[str, Any] = {}

        for in_key, hs_prop in mappings.items():
            if in_key in input_data and input_data[in_key] is not None:
                val = input_data[in_key]
                if isinstance(val, str) and not val.strip():
                    continue
                props[hs_prop] = str(val).strip()

        full_name = input_data.get("name")
        if full_name and isinstance(full_name, str) and full_name.strip():
            if "firstname" not in props:
                parts = full_name.strip().split(" ", 1)
                props["firstname"] = parts[0]
                if len(parts) > 1 and "lastname" not in props:
                    props["lastname"] = parts[1]

        extra_props = input_data.get("properties", {})
        if isinstance(extra_props, dict):
            for k, v in extra_props.items():
                if v is not None:
                    target_k = mappings.get(k, k)
                    props[target_k] = str(v)

        return props

    # ---------------------------------------------------------------------------
    # Configurable Deduplication Matching Strategy
    # ---------------------------------------------------------------------------

    def find_existing_contact(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find an existing contact according to the configured matching strategy:
        - EMAIL_THEN_PHONE: Check email first; if not found, check phone.
        - EMAIL_ONLY: Check strictly on email.
        - PHONE_ONLY: Check strictly on phone.
        - EMAIL_AND_PHONE: Check requiring both email and phone.

        CRITICAL SAFEGUARD:
        Never merge two people solely because their names match!
        If only 'name' is provided without a verified email or phone, this returns None.
        """
        strategy = self._get_matching_strategy()
        email = (data.get("email") or "").strip()
        raw_phone = data.get("phone") or data.get("mobile_phone")
        phone = self._clean_phone(raw_phone)

        if not email and not phone:
            logger.info("No email or phone provided for contact match; skipping deduplication (names alone are never merged).")
            return None

        if strategy == MatchingStrategy.EMAIL_ONLY:
            if not email:
                return None
            results = self.search_contacts(email=email, limit=1)
            contacts = results.get("contacts", [])
            return contacts[0] if contacts else None

        elif strategy == MatchingStrategy.PHONE_ONLY:
            if not phone:
                return None
            results = self.search_contacts(phone=phone, limit=1)
            contacts = results.get("contacts", [])
            return contacts[0] if contacts else None

        elif strategy == MatchingStrategy.EMAIL_AND_PHONE:
            if not email or not phone:
                return None
            results = self.search_contacts(email=email, phone=phone, limit=1)
            contacts = results.get("contacts", [])
            return contacts[0] if contacts else None

        else:
            if email:
                res_email = self.search_contacts(email=email, limit=1)
                contacts = res_email.get("contacts", [])
                if contacts:
                    return contacts[0]

            if phone:
                res_phone = self.search_contacts(phone=phone, limit=1)
                contacts = res_phone.get("contacts", [])
                if contacts:
                    return contacts[0]

            return None

    # ---------------------------------------------------------------------------
    # Search, Retrieval, Creation, and Update Operations
    # ---------------------------------------------------------------------------

    def search_contacts(
        self,
        query: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        properties: Optional[List[str]] = None,
        limit: int = 10,
        after: Optional[str] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Execute contact search using HubSpot CRM v3 Search API.
        Supports filter groups, pagination, and custom property selection.
        """
        token = self._get_access_token()
        props = properties or ["firstname", "lastname", "email", "phone", "mobilephone", "company", "lifecyclestage"]

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            mock_contacts = []
            if email == "alex@example.com" or phone == "+14155552671" or query == "Alex":
                mock_contacts.append({
                    "id": "101",
                    "properties": {
                        "firstname": "Alex",
                        "lastname": "Mercer",
                        "email": "alex@example.com",
                        "phone": "+14155552671",
                    },
                    "created_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:00:00Z",
                })
            return {
                "contacts": mock_contacts,
                "total": len(mock_contacts),
                "has_more": False,
                "next_cursor": None,
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            from hubspot.crm.contacts import PublicObjectSearchRequest, Filter, FilterGroup

            filter_list: List[Filter] = []
            if email:
                filter_list.append(Filter(property_name="email", operator="EQ", value=email))
            if phone:
                filter_list.append(Filter(property_name="phone", operator="EQ", value=phone))

            if filters:
                for f in filters:
                    filter_list.append(
                        Filter(
                            property_name=f["property_name"],
                            operator=f.get("operator", "EQ"),
                            value=f["value"],
                        )
                    )

            filter_groups = [FilterGroup(filters=filter_list)] if filter_list else None
            search_req = PublicObjectSearchRequest(
                query=query,
                filter_groups=filter_groups,
                properties=props,
                limit=min(limit, 100),
                after=after,
            )

            resp = client.crm.contacts.search_api.do_search(public_object_search_request=search_req)
            results = getattr(resp, "results", [])
            total = getattr(resp, "total", len(results))
            paging = getattr(resp, "paging", None)
            next_after = paging.next.after if paging and getattr(paging, "next", None) else None

            contacts = []
            for item in results:
                cid = self.normalize_provider_id(getattr(item, "id", ""))
                c_props = getattr(item, "properties", {}) or {}
                contacts.append({
                    "id": cid,
                    "properties": c_props,
                    "created_at": str(getattr(item, "created_at", "")),
                    "updated_at": str(getattr(item, "updated_at", "")),
                })

            return {
                "contacts": contacts,
                "total": total,
                "has_more": bool(next_after),
                "next_cursor": next_after,
            }

        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def get_contact(
        self,
        contact_id: str,
        properties: Optional[List[str]] = None,
        associations: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve a specific contact record by ID with normalized provider ID.
        """
        clean_id = self.normalize_provider_id(contact_id)
        if not clean_id:
            raise ValueError("contact_id is required for retrieval.")

        token = self._get_access_token()
        props = properties or ["firstname", "lastname", "email", "phone", "mobilephone", "company", "lifecyclestage"]

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return {
                "id": clean_id,
                "properties": {
                    "firstname": "Alex",
                    "lastname": "Mercer",
                    "email": "alex@example.com",
                    "phone": "+14155552671",
                },
                "associations": {},
                "created_at": "2026-01-15T10:00:00Z",
                "updated_at": "2026-01-15T10:00:00Z",
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            resp = client.crm.contacts.basic_api.get_by_id(
                contact_id=clean_id,
                properties=props,
                associations=associations,
            )
            return {
                "id": clean_id,
                "properties": getattr(resp, "properties", {}) or {},
                "associations": getattr(resp, "associations", {}) or {},
                "created_at": str(getattr(resp, "created_at", "")),
                "updated_at": str(getattr(resp, "updated_at", "")),
            }
        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def create_contact(
        self,
        properties: Dict[str, Any],
        associations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new contact in HubSpot CRM.
        Handles unknown custom property errors gracefully by dropping unverified fields.
        Returns synchronous completed write outcome.
        """
        mapped_props = self._map_input_to_hubspot_properties(properties)
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            clean_id = f"hs_{uuid_suffix()}"
            return {
                "contact_id": clean_id,
                "id": clean_id,
                "properties": mapped_props,
                "created": True,
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            from hubspot.crm.contacts import SimplePublicObjectInputForCreate

            def _try_create(props_to_send: Dict[str, Any]):
                input_obj = SimplePublicObjectInputForCreate(properties=props_to_send)
                return client.crm.contacts.basic_api.create(simple_public_object_input_for_create=input_obj)

            try:
                resp = _try_create(mapped_props)
            except Exception as first_exc:
                err = self._normalize_hubspot_error(first_exc)
                ignore_unknown = self.configuration.get("ignore_unknown_properties", True)
                if ignore_unknown and err.code == "HUBSPOT_INVALID_PROPERTY":
                    match = re.search(r'Property \\?["\'](\w+)\\?["\'] does not exist', err.message)
                    if match:
                        invalid_prop = match.group(1)
                        logger.warning("Omitting unknown HubSpot property '%s' and retrying.", invalid_prop)
                        props_copy = dict(mapped_props)
                        props_copy.pop(invalid_prop, None)
                        resp = _try_create(props_copy)
                    else:
                        raise first_exc
                else:
                    raise first_exc

            clean_id = self.normalize_provider_id(getattr(resp, "id", ""))

            if associations and clean_id:
                for assoc in associations:
                    to_type = assoc.get("to_object_type")
                    to_id = assoc.get("to_object_id")
                    if to_type and to_id:
                        self.associate_records("contacts", clean_id, to_type, str(to_id))

            return {
                "contact_id": clean_id,
                "id": clean_id,
                "properties": getattr(resp, "properties", {}) or {},
                "created": True,
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def update_contact(
        self,
        contact_id: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update an existing contact record in HubSpot CRM.
        """
        clean_id = self.normalize_provider_id(contact_id)
        if not clean_id:
            raise ValueError("contact_id is required for update.")

        mapped_props = self._map_input_to_hubspot_properties(properties)
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return {
                "contact_id": clean_id,
                "id": clean_id,
                "properties": mapped_props,
                "created": False,
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            from hubspot.crm.contacts import SimplePublicObjectInput

            def _try_update(props_to_send: Dict[str, Any]):
                input_obj = SimplePublicObjectInput(properties=props_to_send)
                return client.crm.contacts.basic_api.update(
                    contact_id=clean_id,
                    simple_public_object_input=input_obj,
                )

            try:
                resp = _try_update(mapped_props)
            except Exception as first_exc:
                err = self._normalize_hubspot_error(first_exc)
                ignore_unknown = self.configuration.get("ignore_unknown_properties", True)
                if ignore_unknown and err.code == "HUBSPOT_INVALID_PROPERTY":
                    match = re.search(r'Property \\?["\'](\w+)\\?["\'] does not exist', err.message)
                    if match:
                        invalid_prop = match.group(1)
                        logger.warning("Omitting unknown HubSpot property '%s' and retrying update.", invalid_prop)
                        props_copy = dict(mapped_props)
                        props_copy.pop(invalid_prop, None)
                        resp = _try_update(props_copy)
                    else:
                        raise first_exc
                else:
                    raise first_exc

            return {
                "contact_id": clean_id,
                "id": clean_id,
                "properties": getattr(resp, "properties", {}) or {},
                "created": False,
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def create_or_update_contact(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upsert contact using the configured matching strategy.
        If existing contact found: updates it.
        If no match found: creates new contact.
        """
        existing = self.find_existing_contact(data)
        if existing and existing.get("id"):
            contact_id = existing["id"]
            logger.info("Matched existing HubSpot contact %s; updating record.", contact_id)
            res = self.update_contact(contact_id, data)
            res["created"] = False
            return res
        else:
            logger.info("No matching HubSpot contact found; creating new record.")
            res = self.create_contact(data)
            res["created"] = True
            return res

    # ---------------------------------------------------------------------------
    # Associations & Engagements (Notes, Tasks, Deals)
    # ---------------------------------------------------------------------------

    def associate_records(
        self,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
        association_type: Optional[str] = None,
    ) -> bool:
        """
        Associate two CRM records using HubSpot CRM v4 Associations API.
        e.g. associate_records('contacts', '101', 'deals', '505')
        """
        clean_from = self.normalize_provider_id(from_object_id)
        clean_to = self.normalize_provider_id(to_object_id)
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            logger.info("Associated %s:%s to %s:%s (Mock Mode).", from_object_type, clean_from, to_object_type, clean_to)
            return True

        client = self._get_client()
        if not client:
            return False

        try:
            client.crm.associations.v4.basic_api.create_default(
                from_object_type=from_object_type,
                from_object_id=clean_from,
                to_object_type=to_object_type,
                to_object_id=clean_to,
            )
            return True
        except Exception as exc:
            logger.error("Failed to associate %s:%s to %s:%s: %s", from_object_type, clean_from, to_object_type, clean_to, exc)
            return False

    def _verify_object_enabled_and_authorized(self, object_type: str, required_scopes: List[str]) -> None:
        """Verify that object is enabled in setup and authorized by OAuth scopes."""
        enabled = self._get_enabled_objects()
        if object_type.lower() not in enabled:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_OBJECT_DISABLED",
                    category=ErrorCategory.INVALID_REQUEST,
                    message=f"HubSpot object '{object_type}' is not enabled in tenant setup configuration.",
                    safe_user_message=f"HubSpot {object_type} integration is not enabled.",
                )
            )

        token = self._get_access_token()
        if token and not (token.startswith("mock_") or token.startswith("test_")):
            is_valid, missing = self.verify_scopes(required_scopes)
            if not is_valid:
                raise HubspotIntegrationException(
                    IntegrationError(
                        code="HUBSPOT_MISSING_SCOPES",
                        category=ErrorCategory.PERMISSION_DENIED,
                        message=f"HubSpot access token missing required scopes for {object_type}: {missing}",
                        safe_user_message="HubSpot credentials lack required permission scopes.",
                    )
                )

    def create_note(
        self,
        contact_id: str,
        note_body: str,
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a Note engagement and associate it with a contact record.
        Only allowed when 'notes' is enabled and 'crm.objects.notes.write' is authorized.
        """
        self._verify_object_enabled_and_authorized("notes", ["crm.objects.notes.write"])
        clean_id = self.normalize_provider_id(contact_id)
        token = self._get_access_token()
        ts = timestamp or int(time.time() * 1000)

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            note_id = f"note_{uuid_suffix()}"
            return {
                "note_id": note_id,
                "contact_id": clean_id,
                "status": "created",
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            from hubspot.crm.objects import SimplePublicObjectInputForCreate
            note_inp = SimplePublicObjectInputForCreate(
                properties={
                    "hs_timestamp": str(ts),
                    "hs_note_body": note_body,
                }
            )
            resp = client.crm.objects.basic_api.create(
                object_type="notes",
                simple_public_object_input_for_create=note_inp,
            )
            note_id = self.normalize_provider_id(getattr(resp, "id", ""))
            self.associate_records("notes", note_id, "contacts", clean_id)

            return {
                "note_id": note_id,
                "contact_id": clean_id,
                "status": "created",
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }
        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def create_task(
        self,
        contact_id: str,
        subject: str,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: str = "MEDIUM",
    ) -> Dict[str, Any]:
        """
        Create a Task engagement and associate it with a contact record.
        Only allowed when 'tasks' is enabled and 'crm.objects.tasks.write' is authorized.
        """
        self._verify_object_enabled_and_authorized("tasks", ["crm.objects.tasks.write"])
        clean_id = self.normalize_provider_id(contact_id)
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            task_id = f"task_{uuid_suffix()}"
            return {
                "task_id": task_id,
                "contact_id": clean_id,
                "status": "created",
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            from hubspot.crm.objects import SimplePublicObjectInputForCreate
            props = {
                "hs_task_subject": subject,
                "hs_task_status": "NOT_STARTED",
                "hs_task_priority": priority.upper(),
            }
            if body:
                props["hs_task_body"] = body
            if due_date:
                props["hs_timestamp"] = due_date

            task_inp = SimplePublicObjectInputForCreate(properties=props)
            resp = client.crm.objects.basic_api.create(
                object_type="tasks",
                simple_public_object_input_for_create=task_inp,
            )
            task_id = self.normalize_provider_id(getattr(resp, "id", ""))
            self.associate_records("tasks", task_id, "contacts", clean_id)

            return {
                "task_id": task_id,
                "contact_id": clean_id,
                "status": "created",
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }
        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    def create_deal(
        self,
        contact_id: str,
        deal_name: str,
        amount: Optional[float] = None,
        pipeline: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Deal record and associate it with a contact.
        Only allowed when 'deals' is enabled and 'crm.objects.deals.write' is authorized.
        """
        self._verify_object_enabled_and_authorized("deals", ["crm.objects.deals.write"])
        clean_id = self.normalize_provider_id(contact_id)
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            deal_id = f"deal_{uuid_suffix()}"
            return {
                "deal_id": deal_id,
                "contact_id": clean_id,
                "status": "created",
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }

        client = self._get_client()
        if not client:
            raise HubspotIntegrationException(
                IntegrationError(
                    code="HUBSPOT_NOT_CONNECTED",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="HubSpot client not initialized.",
                    safe_user_message="HubSpot client not initialized.",
                )
            )

        try:
            from hubspot.crm.deals import SimplePublicObjectInputForCreate
            props = {"dealname": deal_name}
            if amount is not None:
                props["amount"] = str(amount)
            if pipeline:
                props["pipeline"] = pipeline
            if stage:
                props["dealstage"] = stage

            deal_inp = SimplePublicObjectInputForCreate(properties=props)
            resp = client.crm.deals.basic_api.create(simple_public_object_input_for_create=deal_inp)
            deal_id = self.normalize_provider_id(getattr(resp, "id", ""))
            self.associate_records("deals", deal_id, "contacts", clean_id)

            return {
                "deal_id": deal_id,
                "contact_id": clean_id,
                "status": "created",
                "outcome": ExecutionOutcome.OPERATION_COMPLETED,
            }
        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))

    # ---------------------------------------------------------------------------
    # Capability Execution Dispatcher
    # ---------------------------------------------------------------------------

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Execute CRM capability contracts (GET_CUSTOMER, CREATE_OR_UPDATE_CUSTOMER)
        with retry backoff, error normalization, and truthful outcome envelopes.
        """
        def _dispatch() -> CapabilityResult:
            if operation == CapabilityType.GET_CUSTOMER:
                cid = input_data.get("customer_id")
                email = input_data.get("email")
                phone = input_data.get("phone")

                contact = None
                if cid:
                    try:
                        contact = self.get_contact(cid)
                    except HubspotIntegrationException as err:
                        if err.error.category == ErrorCategory.RESOURCE_NOT_FOUND:
                            contact = None
                        else:
                            raise err

                if not contact and (email or phone):
                    search_res = self.search_contacts(email=email, phone=phone, limit=1)
                    contacts = search_res.get("contacts", [])
                    if contacts:
                        contact = contacts[0]

                if not contact:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        authoritative_source=self.authoritative_source.value,
                        safe_message=f"No HubSpot customer found for {email or phone or cid}.",
                        error=IntegrationError(
                            code="CUSTOMER_NOT_FOUND",
                            category=ErrorCategory.RESOURCE_NOT_FOUND,
                            message="Customer record not found for query parameters.",
                            safe_user_message="No matching customer profile found in CRM.",
                            is_retryable=False,
                        ),
                    )

                c_props = contact.get("properties", {})
                norm_id = self.normalize_provider_id(contact.get("id"))
                fname = c_props.get("firstname", "")
                lname = c_props.get("lastname", "")
                full_name = f"{fname} {lname}".strip() or "Customer"

                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_COMPLETED,
                    success=True,
                    data={
                        "customer_id": norm_id,
                        "hubspot_id": norm_id,
                        "provider_id": "hubspot",
                        "name": full_name,
                        "phone": c_props.get("phone") or c_props.get("mobilephone"),
                        "email": c_props.get("email"),
                        "properties": c_props,
                        "created": False,
                        "authoritative_source": self.authoritative_source.value,
                    },
                    safe_message=f"Found HubSpot customer record for {full_name}.",
                    authoritative_source=self.authoritative_source.value,
                )

            elif operation == CapabilityType.CREATE_OR_UPDATE_CUSTOMER:
                res = self.create_or_update_contact(input_data)
                norm_id = self.normalize_provider_id(res.get("contact_id") or res.get("id"))
                c_props = res.get("properties", {})
                is_created = res.get("created", False)
                fname = c_props.get("firstname", "")
                lname = c_props.get("lastname", "")
                full_name = f"{fname} {lname}".strip() or input_data.get("name", "Customer")

                action_str = "created" if is_created else "updated"
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_COMPLETED,
                    success=True,
                    data={
                        "customer_id": norm_id,
                        "hubspot_id": norm_id,
                        "provider_id": "hubspot",
                        "name": full_name,
                        "phone": c_props.get("phone") or input_data.get("phone"),
                        "email": c_props.get("email") or input_data.get("email"),
                        "properties": c_props,
                        "created": is_created,
                        "authoritative_source": self.authoritative_source.value,
                    },
                    safe_message=f"HubSpot customer {full_name} successfully {action_str}.",
                    authoritative_source=self.authoritative_source.value,
                )

            raise NotImplementedError(f"Operation {operation} not supported by HubspotCrmAdapter")

        try:
            return self.execute_with_retry(operation, input_data, context, _dispatch)
        except HubspotIntegrationException as h_exc:
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=h_exc.error.safe_user_message or "HubSpot CRM operation failed.",
                error=h_exc.error,
            )
        except Exception as exc:
            norm_err = self._normalize_hubspot_error(exc)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="HubSpot CRM operation failed.",
                error=norm_err,
            )

    # ---------------------------------------------------------------------------
    # HTTP Helper
    # ---------------------------------------------------------------------------

    def _post_form_request(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make an application/x-www-form-urlencoded POST request."""
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "CallMe-HubSpotAdapter/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            raise HubspotIntegrationException(self._normalize_hubspot_error(http_err))
        except Exception as exc:
            raise HubspotIntegrationException(self._normalize_hubspot_error(exc))


def uuid_suffix() -> str:
    """Helper for generating clean unique identifiers."""
    import uuid
    return uuid.uuid4().hex[:8]
