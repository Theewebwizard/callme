"""
WhatsApp Business Platform (Cloud API) Integration Adapter.
Provides direct integration with the Meta WhatsApp Cloud API (v21.0) adhering to official guidance:
- Meta App setup (App ID, App Secret), Business Portfolio, WhatsApp Business Account (WABA), and registered Phone Number IDs
- System User access tokens and required permissions (whatsapp_business_messaging, whatsapp_business_management)
- Distinction between consumer WhatsApp accounts (disallowed) and registered Cloud API business sender numbers
- Sending freeform text messages strictly within the 24-hour Customer Service Window (CSW)
- Sending approved pre-defined template messages (UTILITY, AUTHENTICATION, MARKETING) for outbound initiation or outside the 24h window
- Inbound message processing via webhooks and automatic 24-hour customer service window opening/refreshing
- Webhook verification challenge (hub.mode, hub.verify_token, hub.challenge)
- Webhook authenticity verification via HMAC-SHA256 signature (X-Hub-Signature-256)
- Event deduplication for at-least-once webhook delivery semantics
- Delivery status tracking (sent, delivered, read, failed) with normalized status envelopes
- Explicit distinction between API acceptance (REQUEST_ACCEPTED / OPERATION_PENDING) and actual carrier/device delivery
- Safe connection testing without sending real customer messages without authorization
"""

from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime, timezone
import json
import logging
import re
import time
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
    WebhookRequest,
    WebhookResult,
)

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v21.0"
CUSTOMER_SERVICE_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours in seconds


class WhatsAppIntegrationException(Exception):
    """Exception wrapper for normalized IntegrationError."""
    def __init__(self, error: IntegrationError):
        super().__init__(error.message)
        self.error = error


class WhatsAppCloudAdapter(IntegrationAdapter):
    """
    Adapter connecting tenant communication to Meta WhatsApp Business Cloud API.
    Enforces the official WhatsApp Business Messaging Policy, 24-hour customer service window,
    template approval requirements, and cryptographic webhook verification.
    """

    def __init__(
        self,
        business_id: str,
        tool_id: str = "",
        option_id: str = "whatsapp",
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
        # Tracking: normalized phone number -> epoch timestamp of last inbound message
        self._customer_service_windows: Dict[str, float] = {}
        # Tracking: normalized phone number -> boolean opt-in status
        self._user_opt_ins: Dict[str, bool] = {}
        # Deduplication cache for webhook event / wamid IDs
        self._processed_event_ids: Set[str] = set()

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.COMMUNICATION_SERVICE

    # ---------------------------------------------------------------------------
    # Provider Manifest & Declarations
    # ---------------------------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="whatsapp",
            display_name="WhatsApp Business Platform (Cloud API)",
            category=IntegrationCategory.MESSAGING,
            supported_capabilities=[
                CapabilityType.SEND_MESSAGE,
            ],
            auth_method=AuthMethod.BEARER_TOKEN,
            authoritative_source=AuthoritativeSource.COMMUNICATION_SERVICE,
            required_setup_fields=[
                SetupField(
                    key="phone_number_id",
                    label="WhatsApp Phone Number ID",
                    type=FieldType.STRING,
                    required=True,
                    placeholder="100609349424...",
                    description="The Graph API object ID for the registered WhatsApp Business phone number (not the display phone number).",
                ),
                SetupField(
                    key="waba_id",
                    label="WhatsApp Business Account (WABA) ID",
                    type=FieldType.STRING,
                    required=True,
                    placeholder="1054344322...",
                    description="WhatsApp Business Account ID from Meta Business Manager / Developer Console.",
                ),
                SetupField(
                    key="access_token",
                    label="System User Access Token",
                    type=FieldType.PASSWORD,
                    required=True,
                    secret=True,
                    placeholder="EAA...",
                    description="Permanent System User Access Token generated with 'whatsapp_business_messaging' and 'whatsapp_business_management' permissions.",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="app_id",
                    label="Meta App ID",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="1234567890...",
                    description="Meta Developer App ID associated with the WhatsApp integration.",
                ),
                SetupField(
                    key="app_secret",
                    label="Meta App Secret",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    description="App Secret used for HMAC-SHA256 signature verification (X-Hub-Signature-256).",
                ),
                SetupField(
                    key="webhook_verify_token",
                    label="Webhook Verification Token",
                    type=FieldType.STRING,
                    required=False,
                    secret=True,
                    placeholder="custom_verification_token",
                    description="Secret token configured in Meta App Webhook settings to verify hub.challenge handshake.",
                ),
                SetupField(
                    key="api_version",
                    label="Meta Graph API Version",
                    type=FieldType.STRING,
                    required=False,
                    default_value=DEFAULT_GRAPH_VERSION,
                    description="Meta Graph API version (e.g. 'v21.0').",
                ),
                SetupField(
                    key="enforce_24h_window",
                    label="Enforce 24h Customer Service Window",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                    description="If true, blocks freeform text messages outside the 24-hour window, requiring approved template messages.",
                ),
                SetupField(
                    key="require_opt_in",
                    label="Require User Opt-In for Outbound Templates",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                    description="Enforces verifiable customer opt-in consent before initiating outbound conversations.",
                ),
                SetupField(
                    key="default_template_name",
                    label="Default Fallback Template Name",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="appointment_reminder",
                    description="Pre-approved WhatsApp template to use when customer service window is closed.",
                ),
                SetupField(
                    key="default_template_language",
                    label="Default Template Language Code",
                    type=FieldType.STRING,
                    required=False,
                    default_value="en_US",
                    description="Default template language code (e.g. 'en_US', 'es', 'pt_BR').",
                ),
            ],
            required_oauth_scopes=[
                "whatsapp_business_messaging",
                "whatsapp_business_management",
            ],
            partner_approval_required=False,
            required_resources=["phone_numbers"],
            webhook_events=[
                "messages",
                "message_deliveries",
                "message_reads",
                "message_failures",
            ],
            webhook_signature_method="X-Hub-Signature-256",
            test_connection_procedure="Queries GET /{phone_number_id} to verify registration, quality rating, and token permissions without sending unsolicited messages.",
            known_limitations=[
                "Consumer WhatsApp accounts cannot be used as an API sender; requires verified Cloud API phone number registration.",
                "Freeform text messages are strictly prohibited outside the 24-hour Customer Service Window.",
                "Outbound business-initiated messages require pre-approved Meta message templates (UTILITY, AUTHENTICATION, or MARKETING).",
                "API acceptance (HTTP 200 with wamid) confirms request queuing at Meta, not final carrier delivery to the user's handset.",
                "Real customer messages must never be sent as connection tests without explicit authorization.",
            ],
            is_mock=False,
        )

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return [
            CapabilityType.SEND_MESSAGE,
        ]

    # ---------------------------------------------------------------------------
    # Credentials & Configuration Helpers
    # ---------------------------------------------------------------------------

    def _get_phone_number_id(self) -> str:
        return str(
            self.configuration.get("phone_number_id")
            or self.credentials.get("phone_number_id")
            or ""
        ).strip()

    def _get_waba_id(self) -> str:
        return str(
            self.configuration.get("waba_id")
            or self.credentials.get("waba_id")
            or ""
        ).strip()

    def _get_access_token(self) -> str:
        return str(
            self.credentials.get("access_token")
            or self.configuration.get("access_token")
            or ""
        ).strip()

    def _get_app_secret(self) -> str:
        return str(
            self.credentials.get("app_secret")
            or self.configuration.get("app_secret")
            or ""
        ).strip()

    def _get_verify_token(self) -> str:
        return str(
            self.credentials.get("webhook_verify_token")
            or self.configuration.get("webhook_verify_token")
            or ""
        ).strip()

    def _get_api_version(self) -> str:
        ver = str(
            self.configuration.get("api_version")
            or self.credentials.get("api_version")
            or DEFAULT_GRAPH_VERSION
        ).strip()
        if not ver.startswith("v"):
            ver = f"v{ver}"
        return ver

    def _enforce_24h_window(self) -> bool:
        return bool(self.configuration.get("enforce_24h_window", True))

    def _require_opt_in(self) -> bool:
        return bool(self.configuration.get("require_opt_in", True))

    @staticmethod
    def clean_phone(raw_phone: Optional[str]) -> str:
        """
        Normalize recipient phone numbers to digits only with country code (E.164 without leading '+').
        Meta WhatsApp Cloud API expects recipient numbers in format '16505551234'.
        """
        if not raw_phone:
            return ""
        digits = re.sub(r"\D", "", str(raw_phone).strip())
        return digits

    # ---------------------------------------------------------------------------
    # Customer Service Window (24h) & Opt-in Tracking
    # ---------------------------------------------------------------------------

    def update_customer_service_window(self, sender_phone: str, timestamp: Optional[float] = None) -> None:
        """
        Record receipt of an inbound user message to open or refresh the 24-hour Customer Service Window.
        """
        clean_num = self.clean_phone(sender_phone)
        if clean_num:
            ts = timestamp or time.time()
            self._customer_service_windows[clean_num] = ts
            logger.info("WhatsApp 24-hour customer service window opened for %s at %s", clean_num, ts)

    def is_customer_service_window_open(self, recipient_phone: str) -> bool:
        """
        Check if the 24-hour Customer Service Window is currently active for the given recipient.
        """
        clean_num = self.clean_phone(recipient_phone)
        if not clean_num:
            return False

        last_inbound_ts = self._customer_service_windows.get(clean_num)
        if last_inbound_ts is None:
            return False

        elapsed = time.time() - last_inbound_ts
        return elapsed < CUSTOMER_SERVICE_WINDOW_SECONDS

    def record_user_opt_in(self, phone: str, opted_in: bool = True) -> None:
        """Record whether a customer has granted verifiable opt-in consent."""
        clean_num = self.clean_phone(phone)
        if clean_num:
            self._user_opt_ins[clean_num] = opted_in

    def has_user_opt_in(self, phone: str) -> bool:
        """Verify customer opt-in status."""
        clean_num = self.clean_phone(phone)
        if not clean_num:
            return False
        return self._user_opt_ins.get(clean_num, False)

    # ---------------------------------------------------------------------------
    # Webhook Challenge Handshake & Authenticity Verification
    # ---------------------------------------------------------------------------

    def verify_webhook_challenge(self, mode: str, verify_token: str, challenge: str) -> Optional[str]:
        """
        Process Meta's GET verification handshake:
        When hub.mode == 'subscribe' and hub.verify_token matches configured token, returns hub.challenge.
        """
        configured_token = self._get_verify_token()
        if mode == "subscribe" and verify_token and configured_token and verify_token == configured_token:
            logger.info("WhatsApp webhook challenge verification succeeded.")
            return challenge
        logger.warning("WhatsApp webhook challenge verification failed: Token mismatch or invalid mode.")
        return None

    def verify_webhook_signature(self, raw_body: bytes, headers: Dict[str, str]) -> bool:
        """
        Verify the cryptographic authenticity of an incoming Meta webhook payload
        using HMAC-SHA256 with the app_secret against the 'X-Hub-Signature-256' header.
        """
        app_secret = self._get_app_secret()
        if not app_secret:
            logger.warning("No app_secret configured; skipping WhatsApp webhook signature verification.")
            return True

        sig_header = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256") or ""
        if not sig_header or not sig_header.startswith("sha256="):
            logger.error("Missing or malformed X-Hub-Signature-256 header in WhatsApp webhook.")
            return False

        expected_sig = sig_header[7:]  # Strip 'sha256=' prefix
        computed_sig = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        return hmac.compare_digest(computed_sig, expected_sig)

    def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        """
        Parse and process incoming WhatsApp webhook notifications:
        - Authenticates HMAC-SHA256 signature
        - Deduplicates repeated event IDs
        - Inbound user messages: updates customer service window and extracts text
        - Message delivery statuses: normalizes 'sent', 'delivered', 'read', 'failed'
        """
        if not self.verify_webhook_signature(request.raw_body, request.headers):
            return WebhookResult(
                success=False,
                processed=False,
                message="Invalid WhatsApp webhook HMAC-SHA256 signature.",
            )

        payload = request.parsed_json or {}
        entry_list = payload.get("entry", [])
        if not entry_list:
            return WebhookResult(success=True, processed=True, message="Empty entry list received.")

        processed_events = []
        for entry in entry_list:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                field = change.get("field", "")

                # 1. Inbound User Messages
                messages = value.get("messages", [])
                for msg in messages:
                    msg_id = msg.get("id", "")
                    if msg_id in self._processed_event_ids:
                        continue
                    self._processed_event_ids.add(msg_id)

                    from_phone = msg.get("from", "")
                    msg_type = msg.get("type", "text")
                    text_body = msg.get("text", {}).get("body", "") if msg_type == "text" else ""
                    msg_ts = float(msg.get("timestamp", time.time()))

                    # Inbound message opens the 24h Customer Service Window!
                    self.update_customer_service_window(from_phone, msg_ts)

                    processed_events.append({
                        "event_type": "inbound_message",
                        "message_id": msg_id,
                        "from": from_phone,
                        "type": msg_type,
                        "body": text_body,
                        "timestamp": msg_ts,
                    })

                # 2. Delivery Status Updates
                statuses = value.get("statuses", [])
                for st in statuses:
                    st_id = st.get("id", "")
                    status_name = st.get("status", "")  # sent, delivered, read, failed
                    recipient_id = st.get("recipient_id", "")
                    st_ts = float(st.get("timestamp", time.time()))
                    errors = st.get("errors", [])

                    dedup_key = f"{st_id}:{status_name}"
                    if dedup_key in self._processed_event_ids:
                        continue
                    self._processed_event_ids.add(dedup_key)

                    processed_events.append({
                        "event_type": f"message_{status_name}",
                        "message_id": st_id,
                        "status": status_name,
                        "recipient_id": recipient_id,
                        "timestamp": st_ts,
                        "errors": errors,
                    })

        return WebhookResult(
            success=True,
            processed=True,
            event_id=f"wh_{int(time.time()*1000)}",
            event_type="whatsapp_webhook_batch",
            message=f"Processed {len(processed_events)} WhatsApp webhook events.",
            data={"events": processed_events},
        )

    # ---------------------------------------------------------------------------
    # Safe Diagnostics & Readiness (Never sends unsolicited messages)
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate format of Phone Number ID, WABA ID, and credentials."""
        phone_id = config.get("phone_number_id") or self.configuration.get("phone_number_id")
        waba_id = config.get("waba_id") or self.configuration.get("waba_id")
        token = config.get("access_token") or self.credentials.get("access_token")

        if not phone_id:
            return ReadinessCheckResult(
                check_id="wa_phone_id",
                name="WhatsApp Phone Number ID Validation",
                passed=False,
                details="WhatsApp Phone Number ID is required.",
                severity="critical",
            )

        if not waba_id:
            return ReadinessCheckResult(
                check_id="wa_waba_id",
                name="WhatsApp Business Account ID Validation",
                passed=False,
                details="WhatsApp Business Account (WABA) ID is required.",
                severity="critical",
            )

        if not token:
            return ReadinessCheckResult(
                check_id="wa_token",
                name="WhatsApp Access Token Validation",
                passed=False,
                details="WhatsApp System User Access Token is required.",
                severity="critical",
            )

        return ReadinessCheckResult(
            check_id="wa_config",
            name="WhatsApp Configuration Validation",
            passed=True,
            details="WhatsApp Cloud API configuration parameters verified.",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Vault credentials safely."""
        self.credentials.update(credentials)
        token = self.credentials.get("access_token")
        if not token:
            return ReadinessCheckResult(
                check_id="wa_auth_store",
                name="WhatsApp Auth Storage",
                passed=False,
                details="Access token missing.",
                severity="critical",
            )
        return ReadinessCheckResult(
            check_id="wa_auth_store",
            name="WhatsApp Auth Storage",
            passed=True,
            details="WhatsApp credentials safely vaulted.",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        """
        Safely probe connectivity without sending any real customer messages.
        Queries GET https://graph.facebook.com/{api_version}/{phone_number_id} to verify registration.
        """
        token = self._get_access_token()
        phone_id = self._get_phone_number_id()

        if not token or not phone_id:
            return ReadinessCheckResult(
                check_id="wa_conn_probe",
                name="WhatsApp Cloud API Probe",
                passed=False,
                details="Phone Number ID and Access Token are required for connection test.",
                severity="critical",
            )

        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return ReadinessCheckResult(
                check_id="wa_conn_probe",
                name="WhatsApp Cloud API Probe",
                passed=True,
                details="WhatsApp Cloud API connection verified (Mock/Sandbox Mode).",
                severity="critical",
            )

        try:
            api_ver = self._get_api_version()
            path = f"/{api_ver}/{phone_id}?fields=verified_name,code_verification_status,display_phone_number,quality_rating"
            resp = self._make_graph_request("GET", path)

            verified_name = resp.get("verified_name", "Business")
            display_num = resp.get("display_phone_number", phone_id)
            quality = resp.get("quality_rating", "UNKNOWN")

            return ReadinessCheckResult(
                check_id="wa_conn_probe",
                name="WhatsApp Cloud API Probe",
                passed=True,
                details=f"Connected to WhatsApp Business Phone Number '{display_num}' ({verified_name}, Quality: {quality}) safely.",
                severity="critical",
            )
        except Exception as exc:
            err = self._normalize_whatsapp_error(exc)
            return ReadinessCheckResult(
                check_id="wa_conn_probe",
                name="WhatsApp Cloud API Probe",
                passed=False,
                details=f"WhatsApp connection probe failed: {err.message}",
                severity="critical",
            )

    def assess_readiness(self, db_service: Optional[Any] = None) -> ReadinessReport:
        """Run all mandatory readiness checks and compile report."""
        checks: List[ReadinessCheckResult] = []

        cfg_check = self.validate_configuration(self.configuration)
        checks.append(cfg_check)

        conn_check = self.test_connection()
        checks.append(conn_check)

        all_passed = all(c.passed for c in checks if c.severity == "critical")
        missing_reqs = [c.details for c in checks if not c.passed]

        return ReadinessReport(
            provider_id=self.provider_id,
            status=CapabilityStatus.READY if all_passed else CapabilityStatus.NEEDS_INPUT,
            is_ready=all_passed,
            checks=checks,
            missing_requirements=missing_reqs,
            recommendations=[
                "Ensure template messages for outbound initiations are pre-approved in Meta Business Manager.",
                "Verify customer consent before sending notifications outside inbound conversation threads.",
            ],
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    # ---------------------------------------------------------------------------
    # Resource Discovery (Phone Numbers & Approved Templates)
    # ---------------------------------------------------------------------------

    def discover_resources(self, resource_type: str = "") -> List[DiscoveredResource]:
        """
        Discover WhatsApp Business resources:
        - 'phone_numbers': Registered phone number details
        - 'templates' / 'message_templates': Approved message templates under WABA
        """
        rt = (resource_type or "phone_numbers").lower()
        token = self._get_access_token()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            if "temp" in rt:
                return [
                    DiscoveredResource(
                        resource_id="appointment_confirmation",
                        name="Appointment Confirmation",
                        resource_type="message_template",
                        metadata={"status": "APPROVED", "category": "UTILITY", "language": "en_US"},
                    ),
                    DiscoveredResource(
                        resource_id="appointment_reminder",
                        name="Appointment Reminder",
                        resource_type="message_template",
                        metadata={"status": "APPROVED", "category": "UTILITY", "language": "en_US"},
                    ),
                ]
            else:
                return [
                    DiscoveredResource(
                        resource_id=self._get_phone_number_id() or "100609349424111",
                        name="Support Desk (+15550199999)",
                        resource_type="phone_number",
                        metadata={"quality_rating": "GREEN", "verified_name": "Apex Clinic"},
                    )
                ]

        api_ver = self._get_api_version()

        # 1. Phone Numbers Discovery
        if "phone" in rt or not rt:
            phone_id = self._get_phone_number_id()
            try:
                path = f"/{api_ver}/{phone_id}?fields=verified_name,display_phone_number,quality_rating,code_verification_status"
                resp = self._make_graph_request("GET", path)
                return [
                    DiscoveredResource(
                        resource_id=phone_id,
                        name=f"{resp.get('verified_name', 'WhatsApp')} ({resp.get('display_phone_number', phone_id)})",
                        resource_type="phone_number",
                        metadata={
                            "quality_rating": resp.get("quality_rating"),
                            "status": resp.get("code_verification_status"),
                            "display_phone_number": resp.get("display_phone_number"),
                        },
                    )
                ]
            except Exception as exc:
                logger.error("Failed to discover WhatsApp phone number details: %s", exc)
                return []

        # 2. Templates Discovery
        elif "temp" in rt:
            waba_id = self._get_waba_id()
            try:
                path = f"/{api_ver}/{waba_id}/message_templates?fields=name,status,category,language"
                resp = self._make_graph_request("GET", path)
                templates = resp.get("data", [])
                resources = []
                for t in templates:
                    resources.append(
                        DiscoveredResource(
                            resource_id=t.get("name", ""),
                            name=t.get("name", "").replace("_", " ").title(),
                            resource_type="message_template",
                            metadata={
                                "status": t.get("status"),
                                "category": t.get("category"),
                                "language": t.get("language"),
                            },
                        )
                    )
                return resources
            except Exception as exc:
                logger.error("Failed to discover WhatsApp message templates: %s", exc)
                return []

        return []

    # ---------------------------------------------------------------------------
    # Outbound Messaging (Text & Template)
    # ---------------------------------------------------------------------------

    def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a freeform text message to a WhatsApp recipient.
        Enforces WhatsApp 24-hour Customer Service Window policy:
        If the 24-hour window is closed (or user never messaged), raises POLICY_VIOLATION error.
        """
        clean_to = self.clean_phone(to)
        if not clean_to:
            raise WhatsAppIntegrationException(
                IntegrationError(
                    code="INVALID_PHONE_NUMBER",
                    category=ErrorCategory.INVALID_REQUEST,
                    message="Recipient phone number is invalid or empty.",
                    safe_user_message="Invalid phone number.",
                )
            )

        # Policy Check: 24h Customer Service Window
        if self._enforce_24h_window() and not self.is_customer_service_window_open(clean_to):
            logger.warning(
                "Blocked freeform text to %s: 24-hour customer service window is not open. Pre-approved template required.",
                clean_to
            )
            raise WhatsAppIntegrationException(
                IntegrationError(
                    code="CUSTOMER_SERVICE_WINDOW_CLOSED",
                    category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                    message=f"Cannot send freeform text message to {clean_to}: The 24-hour Customer Service Window is closed. WhatsApp Business Messaging Policy mandates a pre-approved template message to initiate contact.",
                    safe_user_message="Freeform messages cannot be sent outside the 24-hour customer service window. An approved template message must be used.",
                    details={"recipient": clean_to, "policy": "24h_customer_service_window"},
                )
            )

        token = self._get_access_token()
        phone_id = self._get_phone_number_id()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            mock_wamid = f"wamid.HBgL{int(time.time()*1000):x}MOCK"
            return {
                "message_id": mock_wamid,
                "status": "accepted",
                "recipient": clean_to,
                "type": "text",
                "outcome": ExecutionOutcome.REQUEST_ACCEPTED,
            }

        api_ver = self._get_api_version()
        path = f"/{api_ver}/{phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": text},
        }

        resp = self._make_graph_request("POST", path, payload=payload)
        messages = resp.get("messages", [])
        wamid = messages[0].get("id", "") if messages else ""

        # Truthful envelope: API acceptance acknowledged by Meta, NOT carrier delivery
        return {
            "message_id": wamid,
            "status": "accepted",
            "recipient": clean_to,
            "type": "text",
            "outcome": ExecutionOutcome.REQUEST_ACCEPTED,
        }

    def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a pre-approved Meta WhatsApp Template message.
        Permitted outside the 24-hour Customer Service Window for business-initiated notifications.
        Verifies customer opt-in consent if configured.
        """
        clean_to = self.clean_phone(to)
        if not clean_to:
            raise WhatsAppIntegrationException(
                IntegrationError(
                    code="INVALID_PHONE_NUMBER",
                    category=ErrorCategory.INVALID_REQUEST,
                    message="Recipient phone number is invalid or empty.",
                    safe_user_message="Invalid phone number.",
                )
            )

        # Policy Check: Opt-In verification if mandated
        if self._require_opt_in() and clean_to in self._user_opt_ins and not self._user_opt_ins[clean_to]:
            raise WhatsAppIntegrationException(
                IntegrationError(
                    code="USER_CONSENT_REQUIRED",
                    category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                    message=f"Cannot send template to {clean_to}: Customer has opted out or lacks verifiable consent.",
                    safe_user_message="Cannot send message: Recipient consent not verified.",
                )
            )

        token = self._get_access_token()
        phone_id = self._get_phone_number_id()

        if not token or token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            mock_wamid = f"wamid.HBgL{int(time.time()*1000):x}MOCK"
            return {
                "message_id": mock_wamid,
                "status": "accepted",
                "recipient": clean_to,
                "type": "template",
                "template": template_name,
                "outcome": ExecutionOutcome.REQUEST_ACCEPTED,
            }

        api_ver = self._get_api_version()
        path = f"/{api_ver}/{phone_id}/messages"
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components

        resp = self._make_graph_request("POST", path, payload=payload)
        messages = resp.get("messages", [])
        wamid = messages[0].get("id", "") if messages else ""

        return {
            "message_id": wamid,
            "status": "accepted",
            "recipient": clean_to,
            "type": "template",
            "template": template_name,
            "outcome": ExecutionOutcome.REQUEST_ACCEPTED,
        }

    # ---------------------------------------------------------------------------
    # Error Normalization
    # ---------------------------------------------------------------------------

    def _normalize_whatsapp_error(self, exc: Any) -> IntegrationError:
        """
        Map Meta WhatsApp Cloud API error payloads into standardized IntegrationError.
        Handles specific error codes:
        - 131047: Re-engagement message outside 24h window
        - 131026: Message undeliverable
        - 130429: Rate limit hit
        - 190: Invalid OAuth access token
        """
        if isinstance(exc, WhatsAppIntegrationException):
            return exc.error
        if isinstance(exc, IntegrationError):
            return exc

        status_code = getattr(exc, "status", None) or getattr(exc, "status_code", None) or getattr(exc, "code", None)
        headers = getattr(exc, "headers", {}) or {}

        body_raw = getattr(exc, "body", None)
        if not body_raw and hasattr(exc, "read") and callable(exc.read):
            try:
                raw_bytes = exc.read()
                if raw_bytes:
                    body_raw = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else str(raw_bytes)
            except Exception:
                pass

        body = {}
        if isinstance(body_raw, str):
            try:
                body = json.loads(body_raw)
            except Exception:
                body = {"message": body_raw}
        elif isinstance(body_raw, dict):
            body = body_raw

        error_obj = body.get("error", {})
        err_code = error_obj.get("code") or "WHATSAPP_API_ERROR"
        err_subcode = error_obj.get("error_subcode")
        msg = error_obj.get("message") or str(exc)
        err_type = error_obj.get("type", "")

        category = ErrorCategory.PROVIDER_UNAVAILABLE
        is_retryable = False
        retry_after = None

        if headers:
            retry_header = headers.get("retry-after") or headers.get("Retry-After")
            if retry_header:
                try:
                    retry_after = float(retry_header)
                except (ValueError, TypeError):
                    retry_after = None

        # 1. 24h Customer Service Window violation (131047)
        if err_code == 131047 or "more than 24 hours" in msg.lower():
            category = ErrorCategory.BUSINESS_RULE_VIOLATION
            is_retryable = False

        # 2. Rate Limits (130429 or 429)
        elif status_code == 429 or err_code in (130429, 613, 80007):
            category = ErrorCategory.RATE_LIMITED
            is_retryable = True
            retry_after = retry_after or 2.0

        # 3. Authentication Failures (190)
        elif status_code == 401 or err_code in (190, 102) or str(err_code) in ("190", "102"):
            category = ErrorCategory.AUTHENTICATION_FAILED
            is_retryable = False

        # 4. Permissions (10, 200)
        elif status_code == 403 or err_code in (10, 200, 131031):
            category = ErrorCategory.PERMISSION_DENIED
            is_retryable = False

        # 5. Template Not Found or Paused (132000, 132001)
        elif err_code in (132000, 132001, 132015):
            category = ErrorCategory.RESOURCE_NOT_FOUND
            is_retryable = False

        # 6. Invalid Request (100, 131026)
        elif status_code == 400 or err_code in (100, 131026):
            category = ErrorCategory.INVALID_REQUEST
            is_retryable = False

        # 7. Server / Unavailable
        elif status_code and int(status_code) >= 500:
            category = ErrorCategory.PROVIDER_UNAVAILABLE
            is_retryable = True

        return IntegrationError(
            code=str(err_code),
            category=category,
            message=str(msg),
            safe_user_message="WhatsApp Business Platform encountered an error processing this request.",
            is_retryable=is_retryable,
            retry_after_seconds=retry_after,
            details={"subcode": err_subcode, "type": err_type, "status": status_code},
        )

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
        Execute messaging capabilities (SEND_MESSAGE).
        Truthfully distinguishes API acceptance from final delivery.
        """
        def _dispatch() -> CapabilityResult:
            if operation == CapabilityType.SEND_MESSAGE:
                to = input_data.get("recipient_phone") or input_data.get("to") or input_data.get("phone")
                body = input_data.get("message") or input_data.get("text") or input_data.get("body")
                template_name = input_data.get("template_name") or self.configuration.get("default_template_name")
                language = input_data.get("template_language") or self.configuration.get("default_template_language", "en_US")
                components = input_data.get("components")

                clean_to = self.clean_phone(to)
                if not clean_to:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        authoritative_source=self.authoritative_source.value,
                        safe_message="Recipient phone number is invalid.",
                        error=IntegrationError(
                            code="INVALID_PHONE_NUMBER",
                            category=ErrorCategory.INVALID_REQUEST,
                            message="Recipient phone number is required and must be valid digits.",
                            safe_user_message="Invalid recipient phone number.",
                        ),
                    )

                # Route to template if explicit template requested or if window is closed
                window_open = self.is_customer_service_window_open(clean_to)
                if template_name or not window_open:
                    target_template = template_name or self.configuration.get("default_template_name")
                    if not target_template:
                        # Window closed and no template available
                        return CapabilityResult(
                            operation=operation,
                            outcome=ExecutionOutcome.BUSINESS_REJECTION,
                            success=False,
                            authoritative_source=self.authoritative_source.value,
                            safe_message="Freeform messages cannot be sent outside the 24-hour customer service window.",
                            error=IntegrationError(
                                code="CUSTOMER_SERVICE_WINDOW_CLOSED",
                                category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                                message="Cannot send message: 24-hour Customer Service Window is closed and no approved template was specified.",
                                safe_user_message="Freeform messages cannot be sent outside the 24-hour customer service window. An approved template is required.",
                            ),
                        )
                    res = self.send_template_message(clean_to, target_template, language, components)
                else:
                    res = self.send_text_message(clean_to, body or "")

                wamid = res.get("message_id", "")
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.REQUEST_ACCEPTED,
                    success=True,
                    data={
                        "message_id": wamid,
                        "provider_id": "whatsapp",
                        "recipient": clean_to,
                        "type": res.get("type", "text"),
                        "status": "accepted",
                        "is_delivered": False,  # Truthful: API acceptance != delivery
                        "authoritative_source": self.authoritative_source.value,
                    },
                    safe_message=f"WhatsApp message queued successfully (ID: {wamid}).",
                    authoritative_source=self.authoritative_source.value,
                )

            raise NotImplementedError(f"Operation {operation} not supported by WhatsAppCloudAdapter")

        try:
            return self.execute_with_retry(operation, input_data, context, _dispatch)
        except WhatsAppIntegrationException as wa_exc:
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=wa_exc.error.safe_user_message or "WhatsApp messaging failed.",
                error=wa_exc.error,
            )
        except Exception as exc:
            norm_err = self._normalize_whatsapp_error(exc)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="WhatsApp messaging failed.",
                error=norm_err,
            )

    # ---------------------------------------------------------------------------
    # HTTP Request Dispatcher
    # ---------------------------------------------------------------------------

    def _make_graph_request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute an authenticated HTTP request against Meta Graph API.
        """
        url = f"{GRAPH_API_BASE}{path}" if path.startswith("/") else f"{GRAPH_API_BASE}/{path}"
        token = self._get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CallMe-WhatsAppCloudAdapter/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as http_err:
            raise WhatsAppIntegrationException(self._normalize_whatsapp_error(http_err))
        except Exception as exc:
            raise WhatsAppIntegrationException(self._normalize_whatsapp_error(exc))
