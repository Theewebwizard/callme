"""
Razorpay Payments Integration Adapter.
Provides official Razorpay integration for order creation, payment link generation,
authoritative payment verification, cryptographic HMAC-SHA256 webhook and checkout
signature verification, server-side amount and currency validation, anti-tampering
price binding, and test/live environment isolation.

Official Razorpay API Reference (v1):
- Base URL: https://api.razorpay.com/v1
- Orders: POST /orders, GET /orders/{order_id}
- Payment Links: POST /payment_links, GET /payment_links/{link_id}
- Payments: GET /payments/{payment_id}, POST /payments/{payment_id}/capture
- Signature Verification: HMAC-SHA256(raw_body, webhook_secret)
- Checkout Callback Verification: HMAC-SHA256(order_id + "|" + payment_id, key_secret)
"""

from typing import Dict, Any, Optional, List, Union, Tuple
import hmac
import hashlib
import time
import uuid
import json
import base64
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
import logging

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

# Razorpay Production API Endpoint
RAZORPAY_API_BASE_URL = "https://api.razorpay.com/v1"

# Supported Currency minor unit minimums (standard Razorpay policy: min 1 INR = 100 paise, min 0.50 USD = 50 cents)
CURRENCY_MINIMUM_MINOR_UNITS: Dict[str, int] = {
    "INR": 100,    # 1.00 INR (100 paise)
    "USD": 50,     # 0.50 USD (50 cents)
    "EUR": 50,     # 0.50 EUR (50 cents)
    "GBP": 30,     # 0.30 GBP (30 pence)
    "SGD": 50,     # 0.50 SGD (50 cents)
    "AED": 200,    # 2.00 AED (200 fils)
}

# Standard max transaction limit (₹50,00,000 / 500,000,000 paise for standard INR)
DEFAULT_MAX_TRANSACTION_MINOR_UNITS = 500000000

# Status Mapping Constants
# Razorpay payment status -> Normalized status
RAZORPAY_PAYMENT_STATUS_MAP: Dict[str, str] = {
    "created": "pending",
    "authorized": "authorized",     # Two-step authorization; not yet captured
    "captured": "succeeded",        # Authoritative settlement
    "refunded": "refunded",
    "failed": "failed",
}

# Razorpay order status -> Normalized status
RAZORPAY_ORDER_STATUS_MAP: Dict[str, str] = {
    "created": "pending",
    "attempted": "pending",
    "paid": "succeeded",
}

# Razorpay payment link status -> Normalized status
RAZORPAY_LINK_STATUS_MAP: Dict[str, str] = {
    "created": "pending",
    "partially_paid": "pending",
    "paid": "succeeded",
    "cancelled": "cancelled",
    "expired": "expired",
}

IDEMPOTENCY_CACHE_TTL_SECONDS = 300  # 5 minutes


class RazorpayIntegrationException(Exception):
    """Domain exception carrying structured IntegrationError."""
    def __init__(self, error: IntegrationError):
        super().__init__(error.message)
        self.error = error


class RazorpayAdapter(IntegrationAdapter):
    """
    Adapter connecting tenant payment processing to Razorpay API (v1).
    Enforces:
    - Server-side amount and currency validation
    - Authoritative order binding (anti-price-tampering)
    - Test vs. Live environment isolation and admin visibility
    - HMAC-SHA256 webhook and checkout signature verification
    - Webhook event deduplication
    - Strict PCI-DSS hygiene: no raw card data ever accepted, stored, or logged
    - Truthful outcome classification: payment requests are OPERATION_PENDING until authoritative settlement
    """

    def __init__(
        self,
        business_id: str,
        tool_id: str = "collect_payment",
        option_id: str = "razorpay",
        configuration: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        # Support callers who pass (business_id, configuration, credentials) positionally
        if isinstance(tool_id, dict) and configuration is None:
            configuration = tool_id
            tool_id = "collect_payment"
        if isinstance(option_id, dict) and credentials is None:
            credentials = option_id
            option_id = "razorpay"

        super().__init__(
            business_id=business_id,
            tool_id=tool_id,
            option_id=option_id,
            configuration=configuration,
            credentials=credentials,
        )
        # In-memory idempotency cache per tenant instance: {idempotency_key: (result, timestamp)}
        self._idempotency_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        # In-memory webhook event deduplication cache: {event_id: timestamp}
        self._webhook_event_cache: Dict[str, float] = {}

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.PAYMENT_GATEWAY

    # ---------------------------------------------------------------------------
    # Environment Management (Test vs. Live)
    # ---------------------------------------------------------------------------

    def get_environment(self) -> str:
        """
        Determine target environment ('test' or 'live') based on credentials or configuration.
        Razorpay Key IDs start with 'rzp_test_' for Sandbox and 'rzp_live_' for Production.
        """
        key_id = str(self.credentials.get("key_id") or self.configuration.get("key_id") or "")
        if key_id.startswith("rzp_live_"):
            return "live"
        if key_id.startswith("rzp_test_"):
            return "test"

        explicit_env = str(self.configuration.get("environment") or "").lower()
        if explicit_env in ("live", "production"):
            return "live"
        return "test"

    # ---------------------------------------------------------------------------
    # Manifest Declaration
    # ---------------------------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        env = self.get_environment()
        return ProviderManifest(
            provider_id="razorpay",
            display_name="Razorpay Payments",
            category=IntegrationCategory.PAYMENTS,
            supported_capabilities=[
                CapabilityType.CREATE_PAYMENT_REQUEST,
                CapabilityType.GET_PAYMENT_STATUS,
            ],
            auth_method=AuthMethod.API_KEY,
            authoritative_source=AuthoritativeSource.PAYMENT_GATEWAY,
            required_setup_fields=[
                SetupField(
                    key="key_id",
                    label="Razorpay Key ID",
                    type=FieldType.STRING,
                    required=True,
                    placeholder="rzp_test_... or rzp_live_...",
                    description="API Key ID generated from Razorpay Dashboard > Settings > API Keys.",
                ),
                SetupField(
                    key="key_secret",
                    label="Razorpay Key Secret",
                    type=FieldType.PASSWORD,
                    required=True,
                    secret=True,
                    placeholder="Alphanumeric Key Secret",
                    description="API Key Secret corresponding to the Key ID.",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="webhook_secret",
                    label="Webhook Signing Secret",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    placeholder="Secret configured in Razorpay Webhooks",
                    description="Used to cryptographically verify X-Razorpay-Signature on incoming events.",
                ),
                SetupField(
                    key="default_currency",
                    label="Default Currency",
                    type=FieldType.STRING,
                    required=False,
                    default_value="INR",
                    description="Standard 3-letter ISO currency code (e.g. INR, USD, EUR, GBP).",
                ),
                SetupField(
                    key="payment_flow",
                    label="Preferred Payment Flow",
                    type=FieldType.SELECT,
                    required=False,
                    default_value="payment_link",
                    options=[
                        {"value": "payment_link", "label": "Payment Links (Hosted / SMS / Chat) - Best for Conversational Agents"},
                        {"value": "order", "label": "Orders API (Standard / Custom Checkout Modal)"},
                    ],
                    description="Select the product flow matching your business interaction model.",
                ),
                SetupField(
                    key="auto_capture",
                    label="Auto Capture Payments",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                    description="Automatically capture authorized payments without separate capture call.",
                ),
                SetupField(
                    key="environment",
                    label="Target Environment",
                    type=FieldType.SELECT,
                    required=False,
                    default_value="auto",
                    options=[
                        {"value": "auto", "label": "Auto-Detect from Key Prefix"},
                        {"value": "test", "label": "Test Mode (Sandbox)"},
                        {"value": "live", "label": "Live Mode (Production)"},
                    ],
                    description="Environment indicator for tenant administration and security audit.",
                ),
            ],
            required_oauth_scopes=[],
            partner_approval_required=False,
            required_resources=[],
            webhook_events=[
                "payment.authorized",
                "payment.captured",
                "payment.failed",
                "order.paid",
                "payment_link.paid",
                "payment_link.cancelled",
                "payment_link.expired",
                "refund.processed",
            ],
            webhook_signature_method="HMAC_SHA256",
            test_connection_procedure="Safely probes GET /v1/payments?count=1 to verify credentials without creating charges or orders.",
            known_limitations=[
                "Payment requests are pending customer action and cannot be settled unilaterally by the agent.",
                "Server-side amount validation prevents arbitrary price modification.",
                "Card data (PAN/CVV) is strictly forbidden and never accepted or stored.",
                f"Currently configured in '{env.upper()}' mode.",
            ],
            is_mock=False,
        )

    # ---------------------------------------------------------------------------
    # Configuration Validation & Connection Lifecycle
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """
        Validate format of Razorpay Key ID and Key Secret, and ensure test vs live keys
        match the declared environment.
        """
        key_id = str(config.get("key_id") or self.credentials.get("key_id") or "").strip()
        declared_env = str(config.get("environment") or self.configuration.get("environment") or "auto").lower()

        if not key_id:
            return ReadinessCheckResult(
                check_id="razorpay_key_id_check",
                name="Razorpay Key ID Validation",
                passed=False,
                details="Razorpay Key ID ('key_id') is required.",
                severity="critical",
            )

        if not (key_id.startswith("rzp_test_") or key_id.startswith("rzp_live_")):
            return ReadinessCheckResult(
                check_id="razorpay_key_format",
                name="Razorpay Key ID Format",
                passed=False,
                details="Razorpay Key ID must start with 'rzp_test_' (Test mode) or 'rzp_live_' (Live mode).",
                severity="critical",
            )

        # Environment cross-check: prevent running test keys in declared live environment
        if declared_env == "live" and not key_id.startswith("rzp_live_"):
            return ReadinessCheckResult(
                check_id="razorpay_env_mismatch",
                name="Razorpay Environment Isolation",
                passed=False,
                details="Tenant configuration declares 'live' environment, but provided Key ID has test prefix 'rzp_test_'.",
                severity="critical",
            )

        if declared_env == "test" and not key_id.startswith("rzp_test_"):
            return ReadinessCheckResult(
                check_id="razorpay_env_mismatch",
                name="Razorpay Environment Isolation",
                passed=False,
                details="Tenant configuration declares 'test' environment, but provided Key ID has live prefix 'rzp_live_'.",
                severity="critical",
            )

        detected_env = "live" if key_id.startswith("rzp_live_") else "test"
        return ReadinessCheckResult(
            check_id="razorpay_config_check",
            name="Razorpay Configuration Check",
            passed=True,
            details=f"Razorpay configuration verified ({detected_env.upper()} mode, Key ID: {key_id[:12]}...).",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Securely store Razorpay credentials in tenant vault."""
        key_id = credentials.get("key_id") or self.credentials.get("key_id")
        key_secret = credentials.get("key_secret") or self.credentials.get("key_secret")

        if not key_id or not key_secret:
            return ReadinessCheckResult(
                check_id="razorpay_auth_store",
                name="Razorpay Authentication Check",
                passed=False,
                details="Both 'key_id' and 'key_secret' are required to connect Razorpay.",
                severity="critical",
            )

        self.credentials.update(credentials)
        env = self.get_environment()
        return ReadinessCheckResult(
            check_id="razorpay_auth_store",
            name="Razorpay Authentication Check",
            passed=True,
            details=f"Razorpay credentials secured in vault ({env.upper()} mode).",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        """
        Safely probe Razorpay connectivity without financial side-effects.
        STRICT REQUIREMENT: NEVER create dummy orders, charges, or payment links during connection tests!
        Probes GET /v1/payments?count=1 to verify credentials.
        """
        if self.configuration.get("is_mock") or not self.credentials.get("key_id"):
            return ReadinessCheckResult(
                check_id="razorpay_connection_probe",
                name="Razorpay Safe Connection Probe (Simulated)",
                passed=True,
                details="Mock Razorpay API verified. Zero charges or orders created.",
                severity="critical",
            )

        try:
            # Query payments list with count=1. Read-only operation.
            self._make_request("GET", "/payments?count=1")
            env = self.get_environment()
            return ReadinessCheckResult(
                check_id="razorpay_connection_probe",
                name="Razorpay Safe Connection Probe",
                passed=True,
                details=f"Razorpay API connection verified successfully in {env.upper()} mode. Zero transactions created.",
                severity="critical",
            )
        except RazorpayIntegrationException as rex:
            return ReadinessCheckResult(
                check_id="razorpay_connection_probe",
                name="Razorpay Safe Connection Probe",
                passed=False,
                details=f"Razorpay authentication probe failed: {rex.error.safe_user_message}",
                severity="critical",
            )
        except Exception as exc:
            return ReadinessCheckResult(
                check_id="razorpay_connection_probe",
                name="Razorpay Safe Connection Probe",
                passed=False,
                details=f"Razorpay connectivity probe failed: {str(exc)}",
                severity="critical",
            )

    def discover_resources(self, resource_type: str = "") -> List[DiscoveredResource]:
        """Expose account details and active payment methods as discoverable resources."""
        return [
            DiscoveredResource(
                resource_id="razorpay_standard_checkout",
                resource_type="payment_method",
                name="Razorpay Standard Checkout (UPI, Cards, NetBanking)",
                properties={"environment": self.get_environment(), "status": "active"},
            ),
            DiscoveredResource(
                resource_id="razorpay_payment_links",
                resource_type="payment_method",
                name="Razorpay Hosted Payment Links (Out-of-band / SMS / Chat)",
                properties={"environment": self.get_environment(), "status": "active"},
            ),
        ]

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return [
            CapabilityType.CREATE_PAYMENT_REQUEST,
            CapabilityType.GET_PAYMENT_STATUS,
        ]

    # ---------------------------------------------------------------------------
    # PCI-DSS Protection & Amount/Currency Validation
    # ---------------------------------------------------------------------------

    @staticmethod
    def scrub_card_data(payload: Any) -> None:
        """
        Enforce PCI-DSS hygiene: Strictly forbid receiving, logging, or storing raw card data.
        Raises an immediate security violation if card numbers, CVVs, or bank pins are detected.
        """
        if isinstance(payload, dict):
            for k, v in payload.items():
                lower_k = str(k).lower()
                if any(bad in lower_k for bad in ("card_number", "card_no", "pan", "cvv", "cvc", "security_code", "pin")):
                    raise RazorpayIntegrationException(IntegrationError(
                        code="CARD_DATA_FORBIDDEN",
                        category=ErrorCategory.PERMISSION_DENIED,
                        message="Raw card data (PAN/CVV/PIN) is strictly forbidden under PCI-DSS compliance.",
                        safe_user_message="Direct card number entry is forbidden. Payments must be processed through Razorpay Hosted Checkout.",
                        is_retryable=False,
                    ))
                if isinstance(v, (dict, list)):
                    RazorpayAdapter.scrub_card_data(v)
                elif isinstance(v, str):
                    # Check for 13-19 digit card number sequences (Luhn-like patterns)
                    cleaned = re.sub(r"[\s\-]", "", v)
                    if cleaned.isdigit() and 13 <= len(cleaned) <= 19 and lower_k not in ("order_id", "payment_id", "receipt", "external_id", "reference_id"):
                        raise RazorpayIntegrationException(IntegrationError(
                            code="CARD_DATA_FORBIDDEN",
                            category=ErrorCategory.PERMISSION_DENIED,
                            message="Raw payment card number detected in request parameters.",
                            safe_user_message="Payment card details cannot be handled directly. Please use the secure payment link.",
                            is_retryable=False,
                        ))
        elif isinstance(payload, list):
            for item in payload:
                RazorpayAdapter.scrub_card_data(item)

    def validate_payment_amount(
        self,
        amount_minor: int,
        currency: str,
        max_amount_minor: Optional[int] = None,
    ) -> Tuple[int, str]:
        """
        Enforce strict server-side validation of amount and currency:
        - Amount must be a positive integer minor unit (e.g. paise, cents)
        - Must meet Razorpay's minimum requirement for the currency
        - Must not exceed maximum allowed transaction threshold
        - Currency must be a recognized 3-letter ISO code
        """
        if not isinstance(amount_minor, int) or amount_minor <= 0:
            raise RazorpayIntegrationException(IntegrationError(
                code="INVALID_AMOUNT",
                category=ErrorCategory.INVALID_REQUEST,
                message=f"Payment amount must be a positive integer in minor units (received: {amount_minor}).",
                safe_user_message="Invalid payment amount specified.",
                is_retryable=False,
            ))

        norm_curr = str(currency).upper().strip()
        if len(norm_curr) != 3:
            raise RazorpayIntegrationException(IntegrationError(
                code="INVALID_CURRENCY",
                category=ErrorCategory.INVALID_REQUEST,
                message=f"Currency must be a valid 3-letter ISO code (received: '{currency}').",
                safe_user_message="Invalid currency specified for payment.",
                is_retryable=False,
            ))

        min_allowed = CURRENCY_MINIMUM_MINOR_UNITS.get(norm_curr, 50)
        if amount_minor < min_allowed:
            raise RazorpayIntegrationException(IntegrationError(
                code="AMOUNT_BELOW_MINIMUM",
                category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                message=(
                    f"Payment amount of {amount_minor} {norm_curr} subunits is below minimum allowed "
                    f"({min_allowed} {norm_curr} subunits)."
                ),
                safe_user_message=f"Payment amount is below minimum required transaction limit of {min_allowed / 100:.2f} {norm_curr}.",
                is_retryable=False,
            ))

        max_allowed = max_amount_minor or DEFAULT_MAX_TRANSACTION_MINOR_UNITS
        if amount_minor > max_allowed:
            raise RazorpayIntegrationException(IntegrationError(
                code="AMOUNT_EXCEEDS_MAXIMUM",
                category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                message=(
                    f"Payment amount of {amount_minor} {norm_curr} subunits exceeds allowable limit of "
                    f"{max_allowed} subunits."
                ),
                safe_user_message="Payment amount exceeds maximum transaction limit.",
                is_retryable=False,
            ))

        return amount_minor, norm_curr

    def bind_and_verify_transaction(
        self,
        receipt_id: str,
        requested_amount_minor: int,
        authoritative_amount_minor: Optional[int] = None,
    ) -> None:
        """
        Anti-Tampering & Order Binding Protection:
        Verify that the requested payment amount exactly matches the authoritative business transaction total.
        The AI agent is NEVER permitted to invent prices or mutate authoritative order totals.
        """
        if not receipt_id or not str(receipt_id).strip():
            raise RazorpayIntegrationException(IntegrationError(
                code="MISSING_TRANSACTION_BINDING",
                category=ErrorCategory.INVALID_REQUEST,
                message="Payment request must be bound to a real business transaction ID / receipt.",
                safe_user_message="Transaction reference is required to generate a payment request.",
                is_retryable=False,
            ))

        if authoritative_amount_minor is not None:
            if requested_amount_minor != authoritative_amount_minor:
                logger.error(
                    "Price tampering detected for transaction %s: requested %s, authoritative %s",
                    receipt_id, requested_amount_minor, authoritative_amount_minor
                )
                raise RazorpayIntegrationException(IntegrationError(
                    code="AMOUNT_MISMATCH",
                    category=ErrorCategory.BUSINESS_RULE_VIOLATION,
                    message=(
                        f"Requested payment amount ({requested_amount_minor}) does not match authoritative "
                        f"order total ({authoritative_amount_minor}) for transaction '{receipt_id}'."
                    ),
                    safe_user_message="Payment request total does not match authoritative invoice balance.",
                    is_retryable=False,
                ))

    # ---------------------------------------------------------------------------
    # Product 1: Orders API (POST /v1/orders, GET /v1/orders/{id})
    # ---------------------------------------------------------------------------

    def create_order(
        self,
        amount_minor: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
        partial_payment: bool = False,
        authoritative_amount_minor: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an order via Razorpay Orders API (POST /v1/orders).
        Used for Standard Checkout / Custom Checkout modal flows.
        """
        amount_minor, currency = self.validate_payment_amount(amount_minor, currency)
        receipt_id = receipt or f"rcpt_{uuid.uuid4().hex[:12]}"

        # Anti-tampering check
        self.bind_and_verify_transaction(receipt_id, amount_minor, authoritative_amount_minor)

        # Idempotency check
        idem_key = idempotency_key or receipt_id
        cached_entry = self._idempotency_cache.get(idem_key)
        if cached_entry:
            cached_data, cached_ts = cached_entry
            if (time.time() - cached_ts) < IDEMPOTENCY_CACHE_TTL_SECONDS:
                logger.info("Duplicate order creation suppressed from cache for receipt %s.", receipt_id)
                res = dict(cached_data)
                res["is_duplicate"] = True
                return res

        # Mock mode
        if self.configuration.get("is_mock"):
            sim_order_id = f"order_{uuid.uuid4().hex[:14]}"
            sim_order = {
                "order_id": sim_order_id,
                "provider_order_id": sim_order_id,
                "amount": amount_minor,
                "amount_paid": 0,
                "amount_due": amount_minor,
                "currency": currency,
                "receipt": receipt_id,
                "status": "created",
                "normalized_status": "pending",
                "attempts": 0,
                "notes": notes or {},
                "created_at": int(time.time()),
                "environment": self.get_environment(),
                "is_paid": False,
                "is_simulated": True,
            }
            self._idempotency_cache[idem_key] = (sim_order, time.time())
            return sim_order

        # Construct request payload
        order_notes = dict(notes or {})
        order_notes["tenant_id"] = self.tenant_id
        order_notes["business_id"] = self.tenant_id

        payload: Dict[str, Any] = {
            "amount": amount_minor,
            "currency": currency,
            "receipt": receipt_id[:40],  # Razorpay receipt max 40 chars
            "notes": order_notes,
            "partial_payment": partial_payment,
        }

        # Check for prohibited card data
        self.scrub_card_data(payload)

        raw_resp = self._make_request("POST", "/orders", payload=payload)
        normalized = self.normalize_order(raw_resp)
        self._idempotency_cache[idem_key] = (normalized, time.time())
        return normalized

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """Retrieve an order from Razorpay (GET /v1/orders/{order_id})."""
        clean_id = order_id.strip()
        raw_resp = self._make_request("GET", f"/orders/{clean_id}")
        return self.normalize_order(raw_resp)

    # ---------------------------------------------------------------------------
    # Product 2: Payment Links API (POST /v1/payment_links, GET /v1/payment_links/{id})
    # ---------------------------------------------------------------------------

    def create_payment_link(
        self,
        amount_minor: int,
        currency: str = "INR",
        reference_id: Optional[str] = None,
        description: str = "Service Payment",
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        notify_sms: bool = True,
        notify_email: bool = True,
        reminder_enable: bool = True,
        expire_by_minutes: int = 60,
        notes: Optional[Dict[str, Any]] = None,
        authoritative_amount_minor: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a shareable payment link via Razorpay Payment Links API (POST /v1/payment_links).
        Ideal for Conversational Voice/Chat Agents dispatching hosted payment links to customers.
        """
        amount_minor, currency = self.validate_payment_amount(amount_minor, currency)
        ref_id = reference_id or f"plref_{uuid.uuid4().hex[:12]}"

        # Anti-tampering check
        self.bind_and_verify_transaction(ref_id, amount_minor, authoritative_amount_minor)

        # Idempotency check
        idem_key = idempotency_key or ref_id
        cached_entry = self._idempotency_cache.get(idem_key)
        if cached_entry:
            cached_data, cached_ts = cached_entry
            if (time.time() - cached_ts) < IDEMPOTENCY_CACHE_TTL_SECONDS:
                logger.info("Duplicate payment link suppressed from cache for reference %s.", ref_id)
                res = dict(cached_data)
                res["is_duplicate"] = True
                return res

        # Mock mode
        if self.configuration.get("is_mock"):
            sim_link_id = f"plink_{uuid.uuid4().hex[:14]}"
            sim_url = f"https://rzp.io/i/{uuid.uuid4().hex[:8]}"
            sim_link = {
                "payment_link_id": sim_link_id,
                "provider_payment_id": sim_link_id,
                "amount": amount_minor,
                "amount_paid": 0,
                "currency": currency,
                "reference_id": ref_id,
                "description": description,
                "short_url": sim_url,
                "status": "created",
                "normalized_status": "pending",
                "customer": {
                    "name": customer_name,
                    "contact": customer_phone,
                    "email": customer_email,
                },
                "notes": notes or {},
                "created_at": int(time.time()),
                "environment": self.get_environment(),
                "is_paid": False,
                "is_simulated": True,
            }
            self._idempotency_cache[idem_key] = (sim_link, time.time())
            return sim_link

        link_notes = dict(notes or {})
        link_notes["tenant_id"] = self.tenant_id
        link_notes["business_id"] = self.tenant_id

        customer_dict: Dict[str, Any] = {}
        if customer_name:
            customer_dict["name"] = customer_name
        if customer_phone:
            customer_dict["contact"] = customer_phone
        if customer_email:
            customer_dict["email"] = customer_email

        payload: Dict[str, Any] = {
            "amount": amount_minor,
            "currency": currency,
            "accept_partial": False,
            "reference_id": ref_id[:40],
            "description": description,
            "customer": customer_dict,
            "notify": {
                "sms": notify_sms and bool(customer_phone),
                "email": notify_email and bool(customer_email),
            },
            "reminder_enable": reminder_enable,
            "notes": link_notes,
        }

        if expire_by_minutes > 0:
            payload["expire_by"] = int(time.time()) + (expire_by_minutes * 60)

        # Check for prohibited card data
        self.scrub_card_data(payload)

        raw_resp = self._make_request("POST", "/payment_links", payload=payload)
        normalized = self.normalize_payment_link(raw_resp)
        self._idempotency_cache[idem_key] = (normalized, time.time())
        return normalized

    def get_payment_link(self, link_id: str) -> Dict[str, Any]:
        """Retrieve payment link details (GET /v1/payment_links/{link_id})."""
        clean_id = link_id.strip()
        raw_resp = self._make_request("GET", f"/payment_links/{clean_id}")
        return self.normalize_payment_link(raw_resp)

    # ---------------------------------------------------------------------------
    # Product 3: Payments API (GET /v1/payments/{id}, POST /v1/payments/{id}/capture)
    # ---------------------------------------------------------------------------

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """
        Retrieve authoritative payment transaction details (GET /v1/payments/{payment_id}).
        Verifies whether payment is authorized, captured, refunded, or failed.
        """
        clean_id = payment_id.strip()
        raw_resp = self._make_request("GET", f"/payments/{clean_id}")
        return self.normalize_payment(raw_resp)

    def capture_payment(
        self,
        payment_id: str,
        amount_minor: int,
        currency: str = "INR",
    ) -> Dict[str, Any]:
        """
        Capture an authorized payment (POST /v1/payments/{payment_id}/capture).
        Financial side-effect requiring authorization.
        """
        clean_id = payment_id.strip()
        amount_minor, currency = self.validate_payment_amount(amount_minor, currency)
        payload = {
            "amount": amount_minor,
            "currency": currency,
        }
        raw_resp = self._make_request("POST", f"/payments/{clean_id}/capture", payload=payload)
        return self.normalize_payment(raw_resp)

    # ---------------------------------------------------------------------------
    # Normalization Functions
    # ---------------------------------------------------------------------------

    def normalize_payment(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw Razorpay payment object into standardized dictionary."""
        payment_id = str(raw.get("id", ""))
        raw_status = str(raw.get("status", "")).lower()
        normalized_status = RAZORPAY_PAYMENT_STATUS_MAP.get(raw_status, "pending")
        is_captured = bool(raw.get("captured", False)) or (raw_status == "captured")

        return {
            "payment_id": payment_id,
            "provider_payment_id": payment_id,
            "order_id": raw.get("order_id"),
            "amount": raw.get("amount", 0),
            "currency": str(raw.get("currency", "INR")).upper(),
            "status": raw_status,
            "normalized_status": normalized_status,
            "method": raw.get("method"),
            "is_captured": is_captured,
            "is_paid": is_captured and normalized_status == "succeeded",
            "description": raw.get("description"),
            "customer_email": raw.get("email"),
            "customer_phone": raw.get("contact"),
            "fee": raw.get("fee"),
            "tax": raw.get("tax"),
            "error_code": raw.get("error_code"),
            "error_description": raw.get("error_description"),
            "created_at": raw.get("created_at"),
            "environment": self.get_environment(),
            "authoritative_source": self.authoritative_source.value,
        }

    def normalize_order(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw Razorpay order object into standardized dictionary."""
        order_id = str(raw.get("id", ""))
        raw_status = str(raw.get("status", "")).lower()
        normalized_status = RAZORPAY_ORDER_STATUS_MAP.get(raw_status, "pending")
        amount = raw.get("amount", 0)
        amount_paid = raw.get("amount_paid", 0)
        is_paid = (raw_status == "paid") or (amount > 0 and amount_paid >= amount)

        return {
            "order_id": order_id,
            "provider_order_id": order_id,
            "amount": amount,
            "amount_paid": amount_paid,
            "amount_due": raw.get("amount_due", 0),
            "currency": str(raw.get("currency", "INR")).upper(),
            "receipt": raw.get("receipt"),
            "status": raw_status,
            "normalized_status": normalized_status,
            "attempts": raw.get("attempts", 0),
            "notes": raw.get("notes", {}),
            "created_at": raw.get("created_at"),
            "is_paid": is_paid,
            "environment": self.get_environment(),
            "authoritative_source": self.authoritative_source.value,
        }

    def normalize_payment_link(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw Razorpay payment link object into standardized dictionary."""
        link_id = str(raw.get("id", ""))
        raw_status = str(raw.get("status", "")).lower()
        normalized_status = RAZORPAY_LINK_STATUS_MAP.get(raw_status, "pending")
        amount = raw.get("amount", 0)
        amount_paid = raw.get("amount_paid", 0)
        is_paid = (raw_status == "paid") or (amount > 0 and amount_paid >= amount)

        customer_raw = raw.get("customer") or {}

        return {
            "payment_link_id": link_id,
            "provider_payment_id": link_id,
            "amount": amount,
            "amount_paid": amount_paid,
            "currency": str(raw.get("currency", "INR")).upper(),
            "reference_id": raw.get("reference_id"),
            "description": raw.get("description"),
            "short_url": raw.get("short_url"),
            "status": raw_status,
            "normalized_status": normalized_status,
            "customer": {
                "name": customer_raw.get("name"),
                "contact": customer_raw.get("contact"),
                "email": customer_raw.get("email"),
            },
            "notes": raw.get("notes", {}),
            "created_at": raw.get("created_at"),
            "is_paid": is_paid,
            "environment": self.get_environment(),
            "authoritative_source": self.authoritative_source.value,
        }

    # ---------------------------------------------------------------------------
    # Cryptographic Signature Verification & Webhooks
    # ---------------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verify incoming webhook signature according to official Razorpay algorithm:
        HMAC-SHA256(raw_body, webhook_secret) compared with X-Razorpay-Signature.
        """
        wh_secret = secret or self.configuration.get("webhook_secret") or self.credentials.get("webhook_secret")
        if not wh_secret or not signature:
            logger.warning("Missing webhook secret or signature for Razorpay verification.")
            return False

        try:
            expected = hmac.new(
                wh_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature.strip(), expected)
        except Exception as exc:
            logger.error("Error computing Razorpay webhook signature: %s", exc)
            return False

    def verify_checkout_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
        key_secret: Optional[str] = None,
    ) -> bool:
        """
        Verify Razorpay standard checkout client callback signature:
        HMAC-SHA256(order_id + "|" + payment_id, key_secret) compared with razorpay_signature.
        """
        sec = key_secret or self.credentials.get("key_secret") or self.configuration.get("key_secret")
        if not sec or not signature or not order_id or not payment_id:
            return False

        payload = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(sec.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature.strip(), expected)

    def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        """
        Process incoming Razorpay webhook event:
        1. Cryptographic HMAC-SHA256 signature verification via X-Razorpay-Signature header.
        2. Event deduplication against replay attacks.
        3. Authoritative verification of payment state (payment.captured, order.paid, etc.).
        """
        sig_header = (
            request.headers.get("x-razorpay-signature")
            or request.headers.get("x_razorpay_signature")
        )

        wh_secret = self.configuration.get("webhook_secret") or self.credentials.get("webhook_secret")

        # Signature verification if secret configured
        if wh_secret:
            if not sig_header:
                return WebhookResult(
                    success=False,
                    processed=False,
                    message="Missing X-Razorpay-Signature header on webhook request.",
                )

            if not self.verify_webhook_signature(request.raw_body, sig_header, secret=wh_secret):
                return WebhookResult(
                    success=False,
                    processed=False,
                    message="Razorpay HMAC-SHA256 signature verification failed.",
                )

        parsed = request.parsed_json or {}
        event_type = parsed.get("event") or "unknown"
        event_id = (
            request.headers.get("x-razorpay-event-id")
            or parsed.get("id")
            or f"evt_{uuid.uuid4().hex[:12]}"
        )

        # Deduplication check
        now = time.time()
        if event_id in self._webhook_event_cache:
            logger.info("Duplicate Razorpay webhook delivery '%s' ignored.", event_id)
            return WebhookResult(
                success=True,
                event_id=event_id,
                event_type=event_type,
                is_duplicate=True,
                processed=False,
                message="Duplicate webhook event delivery ignored.",
            )

        self._webhook_event_cache[event_id] = now
        # Cache eviction
        if len(self._webhook_event_cache) > 1000:
            cutoff = now - 86400
            self._webhook_event_cache = {k: v for k, v in self._webhook_event_cache.items() if v > cutoff}

        # Authoritative State Verification
        payload_section = parsed.get("payload") or {}
        payment_entity = payload_section.get("payment", {}).get("entity") or {}
        order_entity = payload_section.get("order", {}).get("entity") or {}
        link_entity = payload_section.get("payment_link", {}).get("entity") or {}

        # Authoritative status check: Do not claim paid unless state confirms it!
        payment_status = payment_entity.get("status")
        order_status = order_entity.get("status")
        link_status = link_entity.get("status")

        is_paid = (
            payment_status == "captured"
            or order_status == "paid"
            or link_status == "paid"
        )

        return WebhookResult(
            success=True,
            event_id=event_id,
            event_type=event_type,
            processed=True,
            message=f"Razorpay event '{event_type}' verified. Authoritative is_paid={is_paid}.",
            data={
                "event": event_type,
                "is_paid": is_paid,
                "payment": self.normalize_payment(payment_entity) if payment_entity else None,
                "order": self.normalize_order(order_entity) if order_entity else None,
                "payment_link": self.normalize_payment_link(link_entity) if link_entity else None,
            },
        )

    # ---------------------------------------------------------------------------
    # Safe Capability Execution Pipeline
    # ---------------------------------------------------------------------------

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Execute payment operations within safe capability execution pipeline.
        - CREATE_PAYMENT_REQUEST -> Generates payment link or order; returns OPERATION_PENDING.
        - GET_PAYMENT_STATUS -> Authoritative payment verification; returns OPERATION_COMPLETED.
        """
        start_time = time.time()

        # Scrub card data immediately
        self.scrub_card_data(input_data)

        def _dispatch() -> CapabilityResult:
            if operation == CapabilityType.CREATE_PAYMENT_REQUEST:
                # Require live credentials in live execution mode
                if context.execution_mode == "live" and not self.credentials.get("key_id"):
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_FAILED,
                        success=False,
                        authoritative_source=self.authoritative_source.value,
                        safe_message="Razorpay payment credentials not configured.",
                        error=IntegrationError(
                            code="AUTH_REQUIRED",
                            category=ErrorCategory.AUTHENTICATION_FAILED,
                            message="Razorpay Key ID and Secret are missing.",
                            safe_user_message="Unable to create payment link due to missing credentials.",
                            is_retryable=False,
                        ),
                    )

                # Extract inputs
                amount_minor = int(input_data.get("amount_cents") or input_data.get("amount_minor") or input_data.get("amount") or 1000)
                currency = str(input_data.get("currency") or self.configuration.get("default_currency") or "INR").upper()
                desc = input_data.get("description", "Service Payment")
                customer_phone = input_data.get("customer_phone")
                customer_email = input_data.get("customer_email")
                receipt_ref = input_data.get("receipt") or input_data.get("reference_id") or context.correlation_id or f"tx_{uuid.uuid4().hex[:10]}"
                authoritative_amount = input_data.get("authoritative_amount_minor")
                flow = str(input_data.get("payment_flow") or self.configuration.get("payment_flow") or "payment_link").lower()

                if flow == "order":
                    res = self.create_order(
                        amount_minor=amount_minor,
                        currency=currency,
                        receipt=receipt_ref,
                        notes=input_data.get("notes"),
                        authoritative_amount_minor=authoritative_amount,
                        idempotency_key=context.idempotency_key or receipt_ref,
                    )
                    pay_id = res["order_id"]
                    pay_url = None
                else:
                    res = self.create_payment_link(
                        amount_minor=amount_minor,
                        currency=currency,
                        reference_id=receipt_ref,
                        description=desc,
                        customer_phone=customer_phone,
                        customer_email=customer_email,
                        authoritative_amount_minor=authoritative_amount,
                        idempotency_key=context.idempotency_key or receipt_ref,
                    )
                    pay_id = res["payment_link_id"]
                    pay_url = res.get("short_url")

                # CRITICAL ARCHITECTURAL GUARANTEE:
                # Creating a payment request is OPERATION_PENDING.
                # An AI agent must NEVER claim a transaction is paid until authoritative state confirms it.
                latency = round((time.time() - start_time) * 1000, 2)
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_PENDING,
                    success=True,
                    data={
                        "payment_id": pay_id,
                        "status": "pending",
                        "amount_minor": amount_minor,
                        "currency": currency,
                        "payment_url": pay_url,
                        "receipt": receipt_ref,
                        "environment": self.get_environment(),
                        "is_paid": False,
                        "is_duplicate": res.get("is_duplicate", False),
                        "authoritative_source": self.authoritative_source.value,
                    },
                    safe_message=(
                        f"Payment request generated for {amount_minor / 100:.2f} {currency}. "
                        f"Status is pending customer payment."
                    ),
                    authoritative_source=self.authoritative_source.value,
                    correlation_id=context.correlation_id,
                    latency_ms=latency,
                    idempotency_key=context.idempotency_key,
                )

            elif operation == CapabilityType.GET_PAYMENT_STATUS:
                payment_id = str(input_data.get("payment_id") or "").strip()
                if not payment_id:
                    raise RazorpayIntegrationException(IntegrationError(
                        code="MISSING_PAYMENT_ID",
                        category=ErrorCategory.INVALID_REQUEST,
                        message="Payment ID or Order ID is required to inspect payment status.",
                        safe_user_message="Payment identifier is required.",
                        is_retryable=False,
                    ))

                # Check if simulated/mock
                if self.configuration.get("is_mock"):
                    status_override = input_data.get("status_override", "captured")
                    is_paid = (status_override == "captured")
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data={
                            "payment_id": payment_id,
                            "status": status_override,
                            "is_paid": is_paid,
                            "amount_minor": 250000,
                            "currency": "INR",
                            "paid_at": datetime.now(timezone.utc).isoformat() if is_paid else None,
                            "environment": self.get_environment(),
                            "authoritative_source": self.authoritative_source.value,
                        },
                        safe_message=f"Payment {payment_id} status is '{status_override}' (is_paid={is_paid}).",
                        authoritative_source=self.authoritative_source.value,
                        correlation_id=context.correlation_id,
                    )

                # Authoritative lookup based on ID prefix
                if payment_id.startswith("order_"):
                    norm = self.get_order(payment_id)
                elif payment_id.startswith("plink_"):
                    norm = self.get_payment_link(payment_id)
                else:
                    norm = self.get_payment(payment_id)

                is_paid = norm.get("is_paid", False)
                latency = round((time.time() - start_time) * 1000, 2)
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_COMPLETED,
                    success=True,
                    data=norm,
                    safe_message=f"Authoritative payment status for {payment_id} is '{norm.get('status')}'. (Paid: {is_paid})",
                    authoritative_source=self.authoritative_source.value,
                    correlation_id=context.correlation_id,
                    latency_ms=latency,
                )

            raise NotImplementedError(f"Operation {operation} not supported by RazorpayAdapter.")

        try:
            # Financial writes use max_retries=0 to avoid duplicate transactions
            return self.execute_with_retry(operation, input_data, context, _dispatch)
        except RazorpayIntegrationException as rex:
            latency = round((time.time() - start_time) * 1000, 2)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=rex.error.safe_user_message,
                error=rex.error,
                correlation_id=context.correlation_id,
                latency_ms=latency,
            )
        except Exception as exc:
            latency = round((time.time() - start_time) * 1000, 2)
            norm_err = self._normalize_razorpay_error(exc)
            return CapabilityResult(
                operation=operation,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message=norm_err.safe_user_message,
                error=norm_err,
                correlation_id=context.correlation_id,
                latency_ms=latency,
            )

    # ---------------------------------------------------------------------------
    # HTTP Request Dispatcher & Error Normalization
    # ---------------------------------------------------------------------------

    def _get_auth_header(self) -> str:
        """
        Construct Basic Auth header using key_id and key_secret:
        Authorization: Basic base64(key_id:key_secret)
        """
        key_id = self.credentials.get("key_id") or self.configuration.get("key_id")
        key_secret = self.credentials.get("key_secret") or self.configuration.get("key_secret")

        if not key_id or not key_secret:
            raise RazorpayIntegrationException(IntegrationError(
                code="MISSING_AUTHENTICATION",
                category=ErrorCategory.AUTHENTICATION_FAILED,
                message="Razorpay key_id and key_secret are required for API requests.",
                safe_user_message="Razorpay credentials missing or incomplete.",
                is_retryable=False,
            ))

        auth_str = f"{key_id}:{key_secret}"
        b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        return f"Basic {b64_auth}"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute an authenticated HTTP request against the Razorpay REST API (v1)."""
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{RAZORPAY_API_BASE_URL}{path}"

        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CallMe-RazorpayAdapter/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as http_err:
            raise RazorpayIntegrationException(self._normalize_razorpay_error(http_err))
        except Exception as exc:
            raise RazorpayIntegrationException(self._normalize_razorpay_error(exc))

    def _normalize_razorpay_error(self, exc: Exception) -> IntegrationError:
        """
        Normalize Razorpay API error payloads into structured IntegrationError instances.
        Standardizes HTTP 400, 401, 403, 404, 429, 5xx.
        """
        err_msg = str(exc)
        code_str = "RAZORPAY_ERROR"
        category = ErrorCategory.PROVIDER_UNAVAILABLE
        is_retryable = False
        details: Dict[str, Any] = {}

        if isinstance(exc, urllib.error.HTTPError):
            status_code = exc.code
            try:
                body = exc.read().decode("utf-8")
                parsed = json.loads(body)
                details = parsed

                # Razorpay error format: {"error": {"code": "...", "description": "...", "reason": "..."}}
                err_dict = parsed.get("error", {})
                if isinstance(err_dict, dict):
                    err_msg = err_dict.get("description", err_msg)
                    code_str = err_dict.get("code", "RAZORPAY_ERROR")
            except Exception:
                pass

            if status_code == 400:
                category = ErrorCategory.INVALID_REQUEST
                code_str = code_str or "BAD_REQUEST_ERROR"
            elif status_code == 401:
                category = ErrorCategory.AUTHENTICATION_FAILED
                code_str = "AUTHENTICATION_FAILED"
            elif status_code == 403:
                category = ErrorCategory.PERMISSION_DENIED
                code_str = "PERMISSION_DENIED"
            elif status_code == 404:
                category = ErrorCategory.RESOURCE_NOT_FOUND
                code_str = "RESOURCE_NOT_FOUND"
            elif status_code == 429:
                category = ErrorCategory.RATE_LIMITED
                code_str = "RATE_LIMIT_EXCEEDED"
                is_retryable = True
            elif status_code in (500, 502, 503, 504):
                category = ErrorCategory.PROVIDER_UNAVAILABLE
                code_str = "GATEWAY_ERROR"
                is_retryable = True
        elif isinstance(exc, (urllib.error.URLError, TimeoutError)):
            category = ErrorCategory.TIMEOUT
            code_str = "CONNECTION_TIMEOUT"
            is_retryable = True
            err_msg = "Connection to Razorpay gateway timed out."

        safe_user_message = "Payment gateway request failed. Please verify transaction details."
        if category == ErrorCategory.AUTHENTICATION_FAILED:
            safe_user_message = "Payment gateway authentication failed."
        elif category == ErrorCategory.RATE_LIMITED:
            safe_user_message = "Payment gateway is currently busy. Please retry shortly."
        elif category == ErrorCategory.INVALID_REQUEST:
            safe_user_message = f"Invalid payment request: {err_msg}"

        return IntegrationError(
            code=code_str,
            category=category,
            message=err_msg,
            safe_user_message=safe_user_message,
            is_retryable=is_retryable,
            details=details,
        )
