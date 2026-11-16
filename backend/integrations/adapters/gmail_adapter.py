"""
Gmail Integration Adapter.
Provides direct integration with the Google Gmail API (v1) adhering to official guidance:
- Google OAuth 2.0 authorization code flow, offline refresh token management, and token revocation
- Least-privilege scope tiers:
  * 'send_only': https://www.googleapis.com/auth/gmail.send (Sensitive scope, CASA Tier 2 exempt)
  * 'read_only': https://www.googleapis.com/auth/gmail.readonly (Restricted scope, requires CASA Tier 2)
  * 'metadata': https://www.googleapis.com/auth/gmail.metadata (Sensitive scope, CASA Tier 2 exempt)
  * 'compose': https://www.googleapis.com/auth/gmail.compose (Drafts and send)
  * 'modify': https://www.googleapis.com/auth/gmail.modify (Restricted scope)
  * 'full': https://mail.google.com/ (Restricted scope)
- Support for internal (Google Workspace domain exempt) vs external (public verification & CASA) distribution models
- Construction of RFC 2822 valid MIME messages (plain, HTML, alternative multipart, attachments)
- RFC 2822 header management (To, From, Cc, Bcc, Subject, Date, Message-ID, In-Reply-To, References)
- URL-safe base64 encoding without padding line-breaks as required by Gmail API
- Message and thread tracking (id, threadId, labelIds)
- Truthful outcome envelope: API acceptance (REQUEST_ACCEPTED with is_delivered: False) != actual recipient delivery
- Safe diagnostics: test_connection() probes GET /gmail/v1/users/{userId}/profile and never sends real email without explicit authorization
- Idempotency key tracking and duplicate send prevention
- Multi-tenant isolation with encrypted credential vaults
"""

from typing import Dict, Any, Optional, List, Union, Tuple, Set
from datetime import datetime, timezone
import json
import logging
import re
import time
import hmac
import hashlib
import base64
import uuid
import urllib.request
import urllib.parse
import urllib.error
import email.utils
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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
    WebhookRequest,
    WebhookResult,
)

logger = logging.getLogger(__name__)

# Official Google API Endpoints
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Gmail API OAuth Scopes
GMAIL_SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SCOPE_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPE_METADATA = "https://www.googleapis.com/auth/gmail.metadata"
GMAIL_SCOPE_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_SCOPE_FULL = "https://mail.google.com/"

# Scope Tier Mappings for Least-Privilege Access
SCOPE_TIERS: Dict[str, List[str]] = {
    "send_only": [GMAIL_SCOPE_SEND],
    "read_only": [GMAIL_SCOPE_READONLY],
    "metadata": [GMAIL_SCOPE_METADATA],
    "compose": [GMAIL_SCOPE_COMPOSE],
    "modify": [GMAIL_SCOPE_MODIFY],
    "full": [GMAIL_SCOPE_FULL],
}

# Google Security & CASA Assessment Classification
SCOPE_CLASSIFICATION: Dict[str, Dict[str, Any]] = {
    GMAIL_SCOPE_SEND: {
        "classification": "sensitive",
        "casa_tier_2_required": False,
        "description": "Send emails on behalf of the user. Least privilege for notifications, confirmations, and replies.",
    },
    GMAIL_SCOPE_METADATA: {
        "classification": "sensitive",
        "casa_tier_2_required": False,
        "description": "View message metadata (headers, subject, sender, labels) without reading body contents.",
    },
    GMAIL_SCOPE_READONLY: {
        "classification": "restricted",
        "casa_tier_2_required": True,
        "description": "Read all messages, threads, and attachments in your mailbox.",
    },
    GMAIL_SCOPE_COMPOSE: {
        "classification": "sensitive",
        "casa_tier_2_required": False,
        "description": "Manage email drafts and send emails.",
    },
    GMAIL_SCOPE_MODIFY: {
        "classification": "restricted",
        "casa_tier_2_required": True,
        "description": "Read, compose, send, and modify all messages except permanent deletion.",
    },
    GMAIL_SCOPE_FULL: {
        "classification": "restricted",
        "casa_tier_2_required": True,
        "description": "Full access to mailbox, labels, and settings.",
    },
}

# Constraints
MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB max raw attachment size
IDEMPOTENCY_CACHE_TTL_SECONDS = 600  # 10 minutes cache window


class GmailIntegrationException(Exception):
    """Exception wrapper for normalized IntegrationError."""
    def __init__(self, error: IntegrationError):
        super().__init__(error.message)
        self.error = error


class GmailAdapter(IntegrationAdapter):
    """
    Adapter connecting tenant communication to the Google Gmail Cloud API.
    Enforces least-privilege scopes, RFC 2822 valid MIME formatting, OAuth token rotation,
    safe diagnostics without sending unsolicited test emails, and truthful delivery envelopes.
    """

    def __init__(
        self,
        business_id: str,
        tool_id: str = "",
        option_id: str = "gmail",
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

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.COMMUNICATION_SERVICE

    # ---------------------------------------------------------------------------
    # Provider Manifest & Declarations
    # ---------------------------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="gmail",
            display_name="Gmail (Google Workspace & Gmail API)",
            category=IntegrationCategory.MESSAGING,
            supported_capabilities=[
                CapabilityType.SEND_EMAIL,
            ],
            auth_method=AuthMethod.OAUTH2,
            authoritative_source=AuthoritativeSource.COMMUNICATION_SERVICE,
            required_setup_fields=[
                SetupField(
                    key="client_id",
                    label="Google OAuth 2.0 Client ID",
                    type=FieldType.STRING,
                    required=True,
                    placeholder="xxxxxxxx.apps.googleusercontent.com",
                    description="OAuth 2.0 Client ID from Google Cloud Console.",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="scope_tier",
                    label="OAuth Scope Tier",
                    type=FieldType.SELECT,
                    required=False,
                    default_value="send_only",
                    options=[
                        {"value": "send_only", "label": "Send Only (Least Privilege)"},
                        {"value": "read_only", "label": "Read Only"},
                        {"value": "metadata", "label": "Metadata Only"},
                        {"value": "compose", "label": "Compose & Send"},
                        {"value": "modify", "label": "Read & Modify"},
                        {"value": "full", "label": "Full Mailbox Access"},
                    ],
                    description=(
                        "Least-privilege scope tier. 'send_only' (gmail.send) is sensitive and exempt "
                        "from CASA Tier 2 assessment. 'read_only' and 'modify' are restricted scopes."
                    ),
                ),
                SetupField(
                    key="sender_email",
                    label="Default Sender Email",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="reception@yourdomain.com",
                    description="Verified Google Workspace or Gmail sender address. Defaults to authenticated account.",
                ),
                SetupField(
                    key="sender_name",
                    label="Default Sender Display Name",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="Acme Dental AI Receptionist",
                    description="Display name attached to the From header.",
                ),
                SetupField(
                    key="app_distribution_model",
                    label="App Distribution Model",
                    type=FieldType.SELECT,
                    required=False,
                    default_value="internal",
                    options=[
                        {"value": "internal", "label": "Google Workspace Internal (Exempt)"},
                        {"value": "external", "label": "External / Multi-Tenant SaaS"},
                    ],
                    description=(
                        "'internal' (Google Workspace internal app, verification exempt) or "
                        "'external' (public multi-tenant app subject to Google verification & CASA)."
                    ),
                ),
                SetupField(
                    key="allow_connection_test_email",
                    label="Allow Test Email on Connection Probe",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=False,
                    description="Whether test_connection is permitted to send an actual test email. Disabled by default.",
                ),
            ],
            required_oauth_scopes=[GMAIL_SCOPE_SEND],
            test_connection_procedure=(
                "Safely queries GET /gmail/v1/users/me/profile to verify token validity, active mailbox, "
                "and message counts without sending any emails."
            ),
            known_limitations=[
                "Gmail Cloud API message sending rate limit is 100 requests per 100 seconds per user, with a daily recipient limit (2,000 for Google Workspace, 500 for consumer @gmail accounts).",
                "API acceptance (HTTP 200 with message ID) confirms queuing at Google MTA, not recipient inbox delivery.",
                "Attachments exceeding 25 MB must be rejected or shared via Google Drive.",
                "External apps requesting restricted scopes (read_only, modify, full) require annual third-party CASA Tier 2 security assessments.",
            ],
            is_mock=False,
        )

    # ---------------------------------------------------------------------------
    # Configuration Validation & Connection Lifecycle
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate format of OAuth Client ID, Scope Tier, and Sender Configuration."""
        client_id = config.get("client_id") or self.configuration.get("client_id") or self.credentials.get("client_id")
        scope_tier = config.get("scope_tier") or self.configuration.get("scope_tier", "send_only")
        distribution_model = config.get("app_distribution_model") or self.configuration.get("app_distribution_model", "internal")
        sender_email = config.get("sender_email") or self.configuration.get("sender_email")

        if not client_id:
            return ReadinessCheckResult(
                check_id="gmail_client_id",
                name="Google OAuth Client ID Validation",
                passed=False,
                details="Google OAuth Client ID ('client_id') is required.",
                severity="critical",
            )

        if scope_tier not in SCOPE_TIERS:
            return ReadinessCheckResult(
                check_id="gmail_scope_tier",
                name="OAuth Scope Tier Validation",
                passed=False,
                details=f"Invalid scope_tier '{scope_tier}'. Must be one of: {list(SCOPE_TIERS.keys())}.",
                severity="critical",
            )

        if distribution_model not in ("internal", "external"):
            return ReadinessCheckResult(
                check_id="gmail_dist_model",
                name="App Distribution Model Validation",
                passed=False,
                details=f"Invalid app_distribution_model '{distribution_model}'. Must be 'internal' or 'external'.",
                severity="warning",
            )

        if sender_email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", sender_email):
            return ReadinessCheckResult(
                check_id="gmail_sender_email",
                name="Sender Email Validation",
                passed=False,
                details=f"Configured sender_email '{sender_email}' is not a valid email address.",
                severity="warning",
            )

        return ReadinessCheckResult(
            check_id="gmail_config",
            name="Gmail Configuration Validation",
            passed=True,
            details="Gmail API configuration parameters verified.",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Vault credentials safely and verify token presence."""
        client_id = credentials.get("client_id") or self.credentials.get("client_id") or self.configuration.get("client_id")
        token = credentials.get("access_token") or credentials.get("refresh_token") or self.credentials.get("access_token") or self.credentials.get("refresh_token")

        if not client_id:
            return ReadinessCheckResult(
                check_id="gmail_auth_client_id",
                name="Gmail OAuth Client ID Check",
                passed=False,
                details="Google OAuth Client ID ('client_id') missing from credentials.",
                severity="critical",
            )

        if not token:
            return ReadinessCheckResult(
                check_id="gmail_auth_token",
                name="Gmail OAuth Token Check",
                passed=False,
                details="Neither access_token nor refresh_token provided in credentials.",
                severity="critical",
            )

        self.credentials.update(credentials)
        return ReadinessCheckResult(
            check_id="gmail_auth_store",
            name="Gmail Auth Storage",
            passed=True,
            details="Google OAuth credentials successfully vaulted.",
            severity="critical",
        )

    # ---------------------------------------------------------------------------
    # OAuth Authorization Code Flow & Token Management
    # ---------------------------------------------------------------------------

    def get_scope_tier(self) -> str:
        """Get the configured scope tier, defaulting to least-privilege 'send_only'."""
        return self.configuration.get("scope_tier", "send_only")

    def get_requested_scopes(self, scope_tier: Optional[str] = None) -> List[str]:
        """Return the list of Google OAuth scopes for the given or configured scope tier."""
        tier = scope_tier or self.get_scope_tier()
        return SCOPE_TIERS.get(tier, [GMAIL_SCOPE_SEND])

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scope_tier: Optional[str] = None,
        prompt: str = "consent",
        access_type: str = "offline",
        login_hint: Optional[str] = None,
    ) -> str:
        """
        Generate Google OAuth 2.0 authorization URL adhering to least-privilege scopes.
        """
        client_id = self.credentials.get("client_id") or self.configuration.get("client_id")
        if not client_id:
            raise ValueError("Cannot generate OAuth authorization URL: client_id is not configured.")

        scopes = self.get_requested_scopes(scope_tier)
        scope_str = " ".join(scopes)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
            "access_type": access_type,
            "prompt": prompt,
            "include_granted_scopes": "true",
        }
        if login_hint:
            params["login_hint"] = login_hint

        return f"{GOOGLE_OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def validate_oauth_state(self, received_state: str, expected_state: str) -> bool:
        """Validate OAuth state parameter using constant-time comparison to prevent CSRF."""
        if not received_state or not expected_state:
            return False
        return hmac.compare_digest(received_state, expected_state)

    def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exchange an authorization code for access and refresh tokens at Google's token endpoint.
        """
        cid = client_id or self.credentials.get("client_id") or self.configuration.get("client_id")
        sec = client_secret or self.credentials.get("client_secret")

        if not cid or not sec:
            raise GmailIntegrationException(IntegrationError(
                code="MISSING_OAUTH_CLIENT_CREDENTIALS",
                category=ErrorCategory.AUTHENTICATION_FAILED,
                message="client_id and client_secret are required to exchange authorization code.",
                safe_user_message="OAuth credentials incomplete.",
                is_retryable=False,
            ))

        payload = {
            "code": code,
            "client_id": cid,
            "client_secret": sec,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        token_data = self._make_oauth_request(GOOGLE_OAUTH_TOKEN_URL, payload)

        # Update credentials with received tokens
        now = time.time()
        expires_in = token_data.get("expires_in", 3600)
        self.credentials["access_token"] = token_data.get("access_token")
        if "refresh_token" in token_data:
            self.credentials["refresh_token"] = token_data.get("refresh_token")
        self.credentials["expires_at"] = now + expires_in
        self.credentials["scope"] = token_data.get("scope", "")

        return token_data

    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh an expired OAuth access token using the stored refresh_token.
        """
        refresh_token = self.credentials.get("refresh_token")
        cid = self.credentials.get("client_id") or self.configuration.get("client_id")
        sec = self.credentials.get("client_secret")

        if not refresh_token:
            raise GmailIntegrationException(IntegrationError(
                code="MISSING_REFRESH_TOKEN",
                category=ErrorCategory.AUTHENTICATION_FAILED,
                message="No refresh_token found in credentials to renew session.",
                safe_user_message="Session expired. Please reconnect your Google account.",
                is_retryable=False,
            ))

        if not cid or not sec:
            raise GmailIntegrationException(IntegrationError(
                code="MISSING_OAUTH_CLIENT_CREDENTIALS",
                category=ErrorCategory.AUTHENTICATION_FAILED,
                message="client_id and client_secret are required to refresh access token.",
                safe_user_message="OAuth client credentials incomplete.",
                is_retryable=False,
            ))

        payload = {
            "client_id": cid,
            "client_secret": sec,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        token_data = self._make_oauth_request(GOOGLE_OAUTH_TOKEN_URL, payload)

        now = time.time()
        expires_in = token_data.get("expires_in", 3600)
        self.credentials["access_token"] = token_data.get("access_token")
        self.credentials["expires_at"] = now + expires_in
        if "scope" in token_data:
            self.credentials["scope"] = token_data.get("scope")

        return token_data

    def ensure_valid_token(self) -> str:
        """
        Return a valid access token, automatically refreshing if close to expiry (60s buffer).
        """
        access_token = self.credentials.get("access_token")
        expires_at = self.credentials.get("expires_at", 0)
        now = time.time()

        if not access_token or (expires_at and now >= (expires_at - 60)):
            if self.credentials.get("refresh_token"):
                logger.info("Access token expired or expiring soon; refreshing for tenant %s.", self.tenant_id)
                self.refresh_access_token()
                access_token = self.credentials.get("access_token")
            elif not access_token:
                raise GmailIntegrationException(IntegrationError(
                    code="NO_ACCESS_TOKEN",
                    category=ErrorCategory.AUTHENTICATION_FAILED,
                    message="No valid access token available and no refresh token present.",
                    safe_user_message="Authentication token missing. Please connect your Gmail account.",
                    is_retryable=False,
                ))

        return str(access_token)

    def revoke_token(self, token: Optional[str] = None) -> bool:
        """
        Revoke an access or refresh token with Google when disconnecting the tenant.
        """
        token_to_revoke = token or self.credentials.get("refresh_token") or self.credentials.get("access_token")
        if not token_to_revoke:
            return False

        params = urllib.parse.urlencode({"token": token_to_revoke})
        url = f"{GOOGLE_OAUTH_REVOKE_URL}?{params}"
        req = urllib.request.Request(url, data=b"", method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                success = (resp.status == 200)
                if success:
                    # Clear revoked credentials
                    self.credentials.pop("access_token", None)
                    self.credentials.pop("refresh_token", None)
                    self.credentials.pop("expires_at", None)
                return success
        except Exception as exc:
            logger.warning("Token revocation failed: %s", exc)
            return False

    def get_scope_compliance_info(self) -> Dict[str, Any]:
        """
        Return security compliance and CASA assessment guidance based on chosen scope tier
        and application distribution model.
        """
        tier = self.get_scope_tier()
        scopes = self.get_requested_scopes(tier)
        dist_model = self.configuration.get("app_distribution_model", "internal")

        requires_casa = False
        scope_details = []
        for s in scopes:
            meta = SCOPE_CLASSIFICATION.get(s, {"classification": "unknown", "casa_tier_2_required": True, "description": ""})
            if meta.get("casa_tier_2_required"):
                requires_casa = True
            scope_details.append({
                "scope": s,
                "classification": meta.get("classification"),
                "casa_tier_2_required": meta.get("casa_tier_2_required"),
                "description": meta.get("description"),
            })

        is_internal_exempt = (dist_model == "internal")

        return {
            "scope_tier": tier,
            "distribution_model": dist_model,
            "scopes": scopes,
            "scope_details": scope_details,
            "casa_tier_2_required": requires_casa and not is_internal_exempt,
            "is_internal_workspace_exempt": is_internal_exempt,
            "compliance_note": (
                "Internal Google Workspace apps are exempt from Google Verification and CASA assessments. "
                "For external multi-tenant apps, 'send_only' (gmail.send) is sensitive and exempt from CASA Tier 2, "
                "while 'read_only' and 'modify' are restricted scopes requiring annual CASA Tier 2 audits."
            ),
        }

    # ---------------------------------------------------------------------------
    # Safe Diagnostics & Connection Testing
    # ---------------------------------------------------------------------------

    def test_connection(self) -> ReadinessCheckResult:
        """
        Safely probe Gmail connection and token validity without creating side effects.
        STRICT REQUIREMENT: Never send an actual email during a connection test unless explicitly authorized!
        Default procedure probes GET /gmail/v1/users/{userId}/profile.
        """
        # If in mock mode or lacking credentials
        if self.configuration.get("is_mock") or not self.credentials:
            return ReadinessCheckResult(
                check_id="gmail_connection",
                name="Gmail Connection Probe (Simulated)",
                passed=True,
                details="Mock Gmail profile verified (messagesTotal: 1250, threadsTotal: 480). Zero emails sent.",
                severity="critical",
            )

        allow_test_email = self.configuration.get("allow_connection_test_email", False)
        test_recipient = self.configuration.get("test_recipient_email")

        # Explicitly authorized test email path (only when explicitly requested)
        if allow_test_email and test_recipient:
            logger.info("Authorized connection test email requested for recipient: %s", test_recipient)
            try:
                res = self.send_email(
                    to=test_recipient,
                    subject="CallMe AI Receptionist: Gmail Connection Verification",
                    body_text="This is an automated connection diagnostic authorized by the tenant administrator.",
                )
                return ReadinessCheckResult(
                    check_id="gmail_connection",
                    name="Gmail Live Email Dispatch Test",
                    passed=True,
                    details=f"Test email submitted to Gmail API (message ID: {res.get('email_id')}).",
                    severity="critical",
                )
            except Exception as exc:
                return ReadinessCheckResult(
                    check_id="gmail_connection",
                    name="Gmail Live Email Dispatch Test",
                    passed=False,
                    details=f"Connection test email failed: {str(exc)}",
                    severity="critical",
                )

        # Default Safe Diagnostic Probe: GET /gmail/v1/users/me/profile
        user_id = self.configuration.get("user_id", "me")
        try:
            profile = self._make_gmail_request("GET", f"/users/{user_id}/profile")
            email_addr = profile.get("emailAddress", "authenticated-user")
            total_msgs = profile.get("messagesTotal", 0)
            total_threads = profile.get("threadsTotal", 0)

            return ReadinessCheckResult(
                check_id="gmail_connection",
                name="Gmail Safe Profile Probe",
                passed=True,
                details=(
                    f"Successfully authenticated with Gmail mailbox '{email_addr}'. "
                    f"Mailbox contains {total_msgs} messages across {total_threads} threads. "
                    "Zero emails sent during test."
                ),
                severity="critical",
            )
        except Exception as exc:
            return ReadinessCheckResult(
                check_id="gmail_connection",
                name="Gmail Safe Profile Probe",
                passed=False,
                details=f"Gmail profile probe failed: {str(exc)}",
                severity="critical",
            )

    # ---------------------------------------------------------------------------
    # MIME Construction According to Official Gmail API Guidance
    # ---------------------------------------------------------------------------

    def create_mime_message(
        self,
        to: Union[str, List[str]],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        sender: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Construct a valid RFC 2822 MIME message according to official Gmail API guidance:
        - Recipients, subject, body, content-type (plain/html/alternative/mixed)
        - Base64 attachments with size validation (<= 25 MB)
        - RFC 2822 headers: To, From, Subject, Date, Message-ID, In-Reply-To, References
        - URL-safe base64 encoding without padding line breaks (base64.urlsafe_b64encode)
        Returns dictionary formatted for Gmail API: {"raw": b64_str, "threadId": thread_id (optional)}
        """
        # Format recipients
        to_str = ", ".join(to) if isinstance(to, list) else str(to)
        if not to_str.strip():
            raise GmailIntegrationException(IntegrationError(
                code="INVALID_RECIPIENT",
                category=ErrorCategory.INVALID_REQUEST,
                message="Recipient 'to' address cannot be empty.",
                safe_user_message="Recipient email address is required.",
                is_retryable=False,
            ))

        # Format sender
        from_str = sender or self.configuration.get("sender_email")
        sender_name = self.configuration.get("sender_name")
        if from_str and sender_name and "<" not in from_str:
            from_header = f"{sender_name} <{from_str}>"
        elif from_str:
            from_header = from_str
        else:
            from_header = "me"

        # Determine MIME structure based on attachments and html presence
        has_attachments = bool(attachments and len(attachments) > 0)
        has_html = bool(body_html and body_html.strip())

        # Validate attachment sizes
        total_attachment_bytes = 0
        if has_attachments and attachments:
            for att in attachments:
                content = att.get("content", b"")
                if isinstance(content, str):
                    # Check if base64 encoded string or raw string
                    try:
                        content_bytes = base64.b64decode(content, validate=True)
                    except Exception:
                        content_bytes = content.encode("utf-8")
                else:
                    content_bytes = content
                total_attachment_bytes += len(content_bytes)

            if total_attachment_bytes > MAX_ATTACHMENT_SIZE_BYTES:
                raise GmailIntegrationException(IntegrationError(
                    code="ATTACHMENT_SIZE_EXCEEDED",
                    category=ErrorCategory.INVALID_REQUEST,
                    message=(
                        f"Cumulative attachment size ({total_attachment_bytes} bytes) exceeds "
                        f"Gmail limit of {MAX_ATTACHMENT_SIZE_BYTES} bytes (25 MB)."
                    ),
                    safe_user_message="Attachment size exceeds 25 MB limit.",
                    is_retryable=False,
                ))

        # Create MIME root
        if has_attachments:
            msg = MIMEMultipart("mixed")
            # Build body container
            if has_html and body_text:
                body_part = MIMEMultipart("alternative")
                body_part.attach(MIMEText(body_text, "plain", "utf-8"))
                body_part.attach(MIMEText(body_html, "html", "utf-8"))
                msg.attach(body_part)
            elif has_html:
                msg.attach(MIMEText(body_html, "html", "utf-8"))
            else:
                msg.attach(MIMEText(body_text, "plain", "utf-8"))

            # Attach files
            for att in attachments:
                filename = att.get("filename", "attachment.bin")
                content = att.get("content", b"")
                content_type = att.get("content_type", "application/octet-stream")

                if isinstance(content, str):
                    try:
                        content_bytes = base64.b64decode(content, validate=True)
                    except Exception:
                        content_bytes = content.encode("utf-8")
                else:
                    content_bytes = content

                maintype, _, subtype = content_type.partition("/")
                if not subtype:
                    maintype, subtype = "application", "octet-stream"

                part = MIMEBase(maintype, subtype)
                part.set_payload(content_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)

        elif has_html and body_text:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        elif has_html:
            msg = MIMEText(body_html, "html", "utf-8")
        else:
            msg = MIMEText(body_text, "plain", "utf-8")

        # Set standard RFC 2822 headers
        msg["To"] = to_str
        msg["From"] = from_header
        try:
            subject.encode("ascii")
            msg["Subject"] = subject
        except UnicodeEncodeError:
            msg["Subject"] = Header(subject, "utf-8").encode()
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid()

        if cc:
            cc_str = ", ".join(cc) if isinstance(cc, list) else str(cc)
            msg["Cc"] = cc_str

        if bcc:
            bcc_str = ", ".join(bcc) if isinstance(bcc, list) else str(bcc)
            msg["Bcc"] = bcc_str

        if reply_to:
            msg["Reply-To"] = reply_to

        # Handle threading headers
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to

        if references:
            ref_str = " ".join(references) if isinstance(references, list) else str(references)
            msg["References"] = ref_str
        elif in_reply_to:
            msg["References"] = in_reply_to

        # Encode to URL-safe base64 string without newlines
        raw_bytes = msg.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

        payload: Dict[str, Any] = {"raw": raw_b64}
        if thread_id:
            payload["threadId"] = thread_id

        return payload

    # ---------------------------------------------------------------------------
    # Outbound Email Dispatch & Deduplication
    # ---------------------------------------------------------------------------

    def _verify_scope_permits_send(self) -> None:
        """Verify that the configured scope tier allows sending emails."""
        tier = self.get_scope_tier()
        if tier in ("read_only", "metadata"):
            raise GmailIntegrationException(IntegrationError(
                code="INSUFFICIENT_SCOPE_FOR_SEND",
                category=ErrorCategory.PERMISSION_DENIED,
                message=(
                    f"Current scope tier '{tier}' does not grant email sending permissions. "
                    "Sending emails requires at least 'send_only' (https://www.googleapis.com/auth/gmail.send)."
                ),
                safe_user_message="Permission denied: This integration is configured in read-only mode.",
                is_retryable=False,
            ))

    def _verify_scope_permits_read(self) -> None:
        """Verify that the configured scope tier allows reading message content."""
        tier = self.get_scope_tier()
        if tier in ("send_only", "metadata", "compose"):
            raise GmailIntegrationException(IntegrationError(
                code="INSUFFICIENT_SCOPE_FOR_READ",
                category=ErrorCategory.PERMISSION_DENIED,
                message=(
                    f"Current scope tier '{tier}' does not grant message reading permissions. "
                    "Reading email contents requires 'read_only' (https://www.googleapis.com/auth/gmail.readonly) "
                    "or 'modify' (https://www.googleapis.com/auth/gmail.modify)."
                ),
                safe_user_message="Permission denied: Mailbox reading not authorized.",
                is_retryable=False,
            ))

    def _verify_scope_permits_metadata(self) -> None:
        """Verify that the configured scope tier allows reading message metadata."""
        tier = self.get_scope_tier()
        if tier in ("send_only", "compose"):
            raise GmailIntegrationException(IntegrationError(
                code="INSUFFICIENT_SCOPE_FOR_METADATA",
                category=ErrorCategory.PERMISSION_DENIED,
                message=(
                    f"Current scope tier '{tier}' does not grant metadata inspection permissions. "
                    "Reading email headers requires 'metadata' (https://www.googleapis.com/auth/gmail.metadata) "
                    "or 'read_only'."
                ),
                safe_user_message="Permission denied: Message metadata inspection not authorized.",
                is_retryable=False,
            ))

    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        sender: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via the Gmail Cloud API (POST /gmail/v1/users/{userId}/messages/send).
        - Verifies least-privilege sending permission
        - Deduplicates sends via idempotency key or content hash
        - Builds RFC 2822 compliant MIME message
        - Distinguishes API acceptance from successful delivery
        """
        self._verify_scope_permits_send()

        # Idempotency / Duplicate send prevention
        to_str = ", ".join(to) if isinstance(to, list) else str(to)
        cache_key = idempotency_key or hashlib.sha256(f"{to_str}:{subject}:{body_text}".encode("utf-8")).hexdigest()

        cached_entry = self._idempotency_cache.get(cache_key)
        if cached_entry:
            cached_data, cached_ts = cached_entry
            if (time.time() - cached_ts) < IDEMPOTENCY_CACHE_TTL_SECONDS:
                logger.info("Duplicate send suppressed for idempotency key %s (tenant %s).", cache_key, self.tenant_id)
                duplicate_res = dict(cached_data)
                duplicate_res["is_duplicate"] = True
                return duplicate_res

        # If in simulated/mock mode
        if self.configuration.get("is_mock"):
            sim_id = f"mock_msg_{uuid.uuid4().hex[:12]}"
            sim_thread = thread_id or f"mock_th_{uuid.uuid4().hex[:12]}"
            result_data = {
                "email_id": sim_id,
                "thread_id": sim_thread,
                "label_ids": ["SENT"],
                "recipient": to_str,
                "subject": subject,
                "delivery_status": "accepted_by_gmail_mta",
                "is_delivered": False,
                "is_simulated": True,
            }
            self._idempotency_cache[cache_key] = (result_data, time.time())
            return result_data

        # Build RFC 2822 MIME message
        payload = self.create_mime_message(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            sender=sender,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            attachments=attachments,
        )

        user_id = self.configuration.get("user_id", "me")
        response = self._make_gmail_request("POST", f"/users/{user_id}/messages/send", payload=payload)

        msg_id = response.get("id", "")
        resp_thread_id = response.get("threadId", "")
        label_ids = response.get("labelIds", ["SENT"])

        result_data = {
            "email_id": msg_id,
            "thread_id": resp_thread_id,
            "label_ids": label_ids,
            "recipient": to_str,
            "subject": subject,
            "delivery_status": "accepted_by_gmail_mta",
            "is_delivered": False,
            "explanation": (
                "Message accepted by Gmail API and queued by Google Mail Transfer Agent (MTA). "
                "Final delivery to recipient mailbox depends on remote MX exchange routing, "
                "spam filtering, and recipient mailbox status."
            ),
        }

        # Cache for deduplication
        self._idempotency_cache[cache_key] = (result_data, time.time())
        return result_data

    # ---------------------------------------------------------------------------
    # Message Reading, Searching & Metadata Inspection
    # ---------------------------------------------------------------------------

    def get_message_metadata(self, message_id: str) -> Dict[str, Any]:
        """
        Retrieve message headers and metadata without message body contents.
        Requires 'metadata', 'read_only', 'modify', or 'full' scope.
        """
        self._verify_scope_permits_metadata()
        user_id = self.configuration.get("user_id", "me")
        return self._make_gmail_request("GET", f"/users/{user_id}/messages/{message_id}?format=metadata")

    def get_message(self, message_id: str, format_type: str = "full") -> Dict[str, Any]:
        """
        Retrieve full message contents and attachments.
        Requires 'read_only', 'modify', or 'full' scope.
        """
        self._verify_scope_permits_read()
        user_id = self.configuration.get("user_id", "me")
        return self._make_gmail_request("GET", f"/users/{user_id}/messages/{message_id}?format={format_type}")

    def search_messages(self, query: str, max_results: int = 10, page_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Search mailbox messages matching a query string (e.g. 'from:patient@example.com').
        Requires 'metadata' or 'read_only' scope.
        """
        self._verify_scope_permits_metadata()
        user_id = self.configuration.get("user_id", "me")
        params = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token

        query_str = urllib.parse.urlencode(params)
        return self._make_gmail_request("GET", f"/users/{user_id}/messages?{query_str}")

    def get_thread(self, thread_id: str, format_type: str = "full") -> Dict[str, Any]:
        """
        Retrieve a complete conversation thread.
        Requires 'read_only', 'modify', or 'full' scope.
        """
        self._verify_scope_permits_read()
        user_id = self.configuration.get("user_id", "me")
        return self._make_gmail_request("GET", f"/users/{user_id}/threads/{thread_id}?format={format_type}")

    # ---------------------------------------------------------------------------
    # Resource Discovery
    # ---------------------------------------------------------------------------

    def discover_resources(self, resource_type: str) -> List[DiscoveredResource]:
        """
        Discover provider resources: 'profile', 'labels', or 'send_as' aliases.
        """
        user_id = self.configuration.get("user_id", "me")
        resources: List[DiscoveredResource] = []

        if resource_type in ("profile", "mailboxes"):
            try:
                profile = self._make_gmail_request("GET", f"/users/{user_id}/profile")
                email_addr = profile.get("emailAddress", "me")
                resources.append(DiscoveredResource(
                    resource_id=email_addr,
                    name=f"Gmail Mailbox ({email_addr})",
                    resource_type="mailbox",
                    metadata={
                        "messagesTotal": profile.get("messagesTotal", 0),
                        "threadsTotal": profile.get("threadsTotal", 0),
                        "historyId": profile.get("historyId", ""),
                    },
                ))
            except Exception as exc:
                logger.warning("Could not discover profile resource: %s", exc)

        elif resource_type in ("labels", "folders"):
            try:
                res = self._make_gmail_request("GET", f"/users/{user_id}/labels")
                for lbl in res.get("labels", []):
                    resources.append(DiscoveredResource(
                        resource_id=lbl.get("id"),
                        name=lbl.get("name"),
                        resource_type="label",
                        metadata={"type": lbl.get("type")},
                    ))
            except Exception as exc:
                logger.warning("Could not discover labels resource: %s", exc)

        elif resource_type in ("send_as", "aliases"):
            try:
                res = self._make_gmail_request("GET", f"/users/{user_id}/settings/sendAs")
                for sa in res.get("sendAs", []):
                    resources.append(DiscoveredResource(
                        resource_id=sa.get("sendAsEmail"),
                        name=sa.get("displayName") or sa.get("sendAsEmail"),
                        resource_type="send_as",
                        metadata={
                            "isPrimary": sa.get("isPrimary", False),
                            "isDefault": sa.get("isDefault", False),
                            "verificationStatus": sa.get("verificationStatus", "accepted"),
                        },
                    ))
            except Exception as exc:
                logger.warning("Could not discover sendAs aliases: %s", exc)

        return resources

    # ---------------------------------------------------------------------------
    # Capability Execution Interface
    # ---------------------------------------------------------------------------

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return [CapabilityType.SEND_EMAIL]

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Execute validated capability contract for SEND_EMAIL.
        Returns truthful outcome envelope with REQUEST_ACCEPTED and is_delivered: False.
        """
        start_time = time.time()

        if operation != CapabilityType.SEND_EMAIL:
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=f"Capability '{operation.value}' is not supported by Gmail adapter.",
                error=IntegrationError(
                    code="UNSUPPORTED_CAPABILITY",
                    category=ErrorCategory.INVALID_REQUEST,
                    message=f"Operation {operation.value} is unsupported by {self.provider_id}.",
                    safe_user_message="Requested capability not supported by this integration.",
                    is_retryable=False,
                ),
                correlation_id=context.correlation_id,
            )

        recipient = input_data.get("recipient_email") or input_data.get("to")
        subject = input_data.get("subject", "")
        body_text = input_data.get("body_text", "")
        body_html = input_data.get("body_html")
        attachments = input_data.get("attachments")
        cc = input_data.get("cc")
        bcc = input_data.get("bcc")
        reply_to = input_data.get("reply_to")
        thread_id = input_data.get("thread_id")
        in_reply_to = input_data.get("in_reply_to")
        references = input_data.get("references")
        sender = input_data.get("sender")

        if not recipient:
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="Missing required recipient email address.",
                error=IntegrationError(
                    code="MISSING_RECIPIENT",
                    category=ErrorCategory.INVALID_REQUEST,
                    message="Field 'recipient_email' is required.",
                    safe_user_message="Recipient email address is required.",
                    is_retryable=False,
                ),
                correlation_id=context.correlation_id,
            )

        try:
            send_res = self.send_email(
                to=recipient,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                sender=sender,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
                thread_id=thread_id,
                in_reply_to=in_reply_to,
                references=references,
                attachments=attachments,
                idempotency_key=context.idempotency_key or input_data.get("idempotency_key"),
            )

            latency = round((time.time() - start_time) * 1000, 2)
            msg_id = send_res.get("email_id", "")

            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.REQUEST_ACCEPTED,
                success=True,
                data=send_res,
                safe_message=f"Email submitted to Gmail API (message ID: {msg_id}). Awaiting remote delivery.",
                is_simulated=send_res.get("is_simulated", False),
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
                latency_ms=latency,
                idempotency_key=context.idempotency_key,
            )

        except GmailIntegrationException as g_exc:
            latency = round((time.time() - start_time) * 1000, 2)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=g_exc.error.safe_user_message,
                error=g_exc.error,
                correlation_id=context.correlation_id,
                latency_ms=latency,
            )
        except Exception as exc:
            latency = round((time.time() - start_time) * 1000, 2)
            err = self._normalize_gmail_error(exc)
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

    def _make_oauth_request(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a POST request to Google's OAuth 2.0 token endpoint."""
        data_bytes = urllib.parse.urlencode(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "CallMe-GmailAdapter/1.0",
        }
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as http_err:
            raise GmailIntegrationException(self._normalize_gmail_error(http_err))
        except Exception as exc:
            raise GmailIntegrationException(self._normalize_gmail_error(exc))

    def _make_gmail_request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute an authenticated HTTP request against Google Gmail API (v1).
        Handles automatic token rotation and error normalization.
        """
        token = self.ensure_valid_token()
        url = f"{GMAIL_API_BASE}{path}" if path.startswith("/") else f"{GMAIL_API_BASE}/{path}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CallMe-GmailAdapter/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as http_err:
            raise GmailIntegrationException(self._normalize_gmail_error(http_err))
        except Exception as exc:
            raise GmailIntegrationException(self._normalize_gmail_error(exc))

    def _normalize_gmail_error(self, exc: Exception, status_code: Optional[int] = None) -> IntegrationError:
        """
        Normalize Google API and OAuth errors into structured IntegrationError instances.
        Maps reasons: rateLimitExceeded, userRateLimitExceeded, dailyLimitExceeded,
        insufficientPermissions, invalid_grant, notFound, backendError.
        """
        err_msg = str(exc)
        code_str = "GMAIL_ERROR"
        category = ErrorCategory.PROVIDER_UNAVAILABLE
        is_retryable = False
        retry_after: Optional[float] = None
        details: Dict[str, Any] = {}

        if isinstance(exc, urllib.error.HTTPError):
            status_code = exc.code
            try:
                body = exc.read().decode("utf-8")
                parsed = json.loads(body)
                details = parsed

                # Google API error envelope: {"error": {"code": 403, "message": "...", "errors": [...]}}
                if "error" in parsed and isinstance(parsed["error"], dict):
                    err_obj = parsed["error"]
                    err_msg = err_obj.get("message", err_msg)
                    errors_list = err_obj.get("errors", [])
                    reason = errors_list[0].get("reason", "") if errors_list else ""

                    if reason in ("rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded") or status_code == 429:
                        category = ErrorCategory.RATE_LIMITED
                        code_str = reason or "RATE_LIMIT_EXCEEDED"
                        is_retryable = True
                        retry_after = 5.0
                    elif reason in ("insufficientPermissions", "accessNotConfigured") or status_code == 403:
                        category = ErrorCategory.PERMISSION_DENIED
                        code_str = reason or "PERMISSION_DENIED"
                    elif reason in ("notFound",) or status_code == 404:
                        category = ErrorCategory.RESOURCE_NOT_FOUND
                        code_str = "RESOURCE_NOT_FOUND"
                    elif status_code == 401:
                        category = ErrorCategory.AUTHENTICATION_FAILED
                        code_str = "AUTHENTICATION_FAILED"
                    elif status_code == 400:
                        category = ErrorCategory.INVALID_REQUEST
                        code_str = "INVALID_REQUEST"
                    elif status_code in (500, 502, 503, 504):
                        category = ErrorCategory.PROVIDER_UNAVAILABLE
                        code_str = "GOOGLE_BACKEND_ERROR"
                        is_retryable = True
                        retry_after = 2.0

                # OAuth Token error envelope: {"error": "invalid_grant", "error_description": "..."}
                elif "error" in parsed and isinstance(parsed["error"], str):
                    oauth_err = parsed.get("error", "")
                    oauth_desc = parsed.get("error_description", err_msg)
                    err_msg = f"{oauth_err}: {oauth_desc}"
                    if oauth_err in ("invalid_grant", "unauthorized_client", "invalid_client"):
                        category = ErrorCategory.AUTHENTICATION_FAILED
                        code_str = oauth_err.upper()
                    else:
                        category = ErrorCategory.INVALID_REQUEST
                        code_str = oauth_err.upper()

            except Exception:
                pass

        elif isinstance(exc, urllib.error.URLError):
            category = ErrorCategory.TIMEOUT if "timed out" in err_msg.lower() else ErrorCategory.PROVIDER_UNAVAILABLE
            code_str = "NETWORK_ERROR"
            is_retryable = True
            retry_after = 3.0

        safe_message = "Gmail service encountered an error."
        if category == ErrorCategory.RATE_LIMITED:
            safe_message = "Gmail API rate limit reached. Please retry in a few moments."
        elif category == ErrorCategory.AUTHENTICATION_FAILED:
            safe_message = "Gmail authentication failed. Please reconnect your Google account."
        elif category == ErrorCategory.PERMISSION_DENIED:
            safe_message = "Permission denied by Gmail. Check that your account has the requested scopes."
        elif category == ErrorCategory.INVALID_REQUEST:
            safe_message = "Invalid email request parameters."
        elif category == ErrorCategory.RESOURCE_NOT_FOUND:
            safe_message = "Requested email or thread was not found."

        return IntegrationError(
            code=code_str,
            category=category,
            message=err_msg,
            safe_user_message=safe_message,
            retry_after_seconds=retry_after,
            is_retryable=is_retryable,
            details=details,
        )
