"""
Domain models, enums, manifests, and execution envelopes for the
Multi-Tenant Integration Adapter Platform.
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field, ConfigDict

from backend.capabilities.models import SetupField, AuthoritativeSource, CapabilityStatus


class IntegrationCategory(str, Enum):
    """Broad functional categories for third-party and built-in integration adapters."""
    TELEPHONY = "telephony"
    CALENDAR = "calendar"
    RESERVATION = "reservation"
    APPOINTMENT = "appointment"
    CRM = "crm"
    MESSAGING = "messaging"
    SUPPORT = "support"
    PAYMENTS = "payments"


class CapabilityType(str, Enum):
    """Provider-independent stable capability operations."""
    CHECK_AVAILABILITY = "check_availability"
    CREATE_BOOKING = "create_booking"
    GET_BOOKING = "get_booking"
    RESCHEDULE_BOOKING = "reschedule_booking"
    CANCEL_BOOKING = "cancel_booking"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    GET_CUSTOMER = "get_customer"
    CREATE_OR_UPDATE_CUSTOMER = "create_or_update_customer"
    SEND_MESSAGE = "send_message"
    SEND_EMAIL = "send_email"
    INITIATE_CALL = "initiate_call"
    TRANSFER_CALL = "transfer_call"
    GET_CALL_STATUS = "get_call_status"
    CREATE_SUPPORT_TICKET = "create_support_ticket"
    GET_PAYMENT_STATUS = "get_payment_status"
    CREATE_PAYMENT_REQUEST = "create_payment_request"


class SideEffectClassification(str, Enum):
    """Declared side-effect classification governing retry safety and confirmation."""
    READ_ONLY = "read_only"
    IDEMPOTENT_WRITE = "idempotent_write"
    NON_IDEMPOTENT_WRITE = "non_idempotent_write"
    FINANCIAL = "financial"
    ESCALATION = "escalation"


class IntegrationLifecycleStatus(str, Enum):
    """Lifecycle state machine for a tenant's integration instance."""
    NOT_CONFIGURED = "not_configured"
    NEEDS_INPUT = "needs_input"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    VALIDATING = "validating"
    READY = "ready"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    PENDING_PROVIDER_APPROVAL = "pending_provider_approval"


class AuthMethod(str, Enum):
    """Authentication mechanism required to connect with provider."""
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    OAUTH2 = "oauth2"
    SERVICE_ACCOUNT = "service_account"
    WEBHOOK_SECRET = "webhook_secret"
    INTERNAL = "internal"


class ExecutionOutcome(str, Enum):
    """Truthful outcome classification distinguishing asynchronous, pending, and completed states."""
    REQUEST_ACCEPTED = "request_accepted"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_PENDING = "operation_pending"
    OPERATION_FAILED = "operation_failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    BUSINESS_REJECTION = "business_rejection"


class ErrorCategory(str, Enum):
    """Normalized category of integration failure."""
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT = "conflict"
    AMBIGUOUS_OUTCOME = "ambiguous_outcome"
    INVALID_REQUEST = "invalid_request"
    PERMISSION_DENIED = "permission_denied"
    BUSINESS_RULE_VIOLATION = "business_rule_violation"


class DiscoveredResource(BaseModel):
    """An external or internal resource discovered during setup."""
    resource_id: str
    name: str
    resource_type: str  # e.g., "calendar", "phone_number", "table", "location", "staff"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class ProviderManifest(BaseModel):
    """Declarative specification for an integration provider."""
    provider_id: str
    display_name: str
    category: IntegrationCategory
    supported_capabilities: List[CapabilityType]
    auth_method: AuthMethod
    authoritative_source: AuthoritativeSource
    required_setup_fields: List[SetupField] = Field(default_factory=list)
    optional_setup_fields: List[SetupField] = Field(default_factory=list)
    required_oauth_scopes: List[str] = Field(default_factory=list)
    partner_approval_required: bool = False
    required_resources: List[str] = Field(default_factory=list)
    webhook_events: List[str] = Field(default_factory=list)
    webhook_signature_method: Optional[str] = None
    test_connection_procedure: str = "Pings provider endpoint or validates credentials"
    known_limitations: List[str] = Field(default_factory=list)
    is_mock: bool = False

    model_config = ConfigDict(extra="ignore")


class ExecutionContext(BaseModel):
    """Tenant and invocation context passed to capability execution."""
    tenant_id: str
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}")
    caller_number: Optional[str] = None
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    execution_mode: str = "live"  # "live" or "mock"
    timeout_override: Optional[float] = None
    actor: str = "agent"

    model_config = ConfigDict(extra="ignore")


class IntegrationError(BaseModel):
    """Structured, safe normalized error returned when an operation fails."""
    code: str
    category: ErrorCategory
    message: str
    safe_user_message: str
    retry_after_seconds: Optional[float] = None
    is_retryable: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class CapabilityResult(BaseModel):
    """Normalized, provider-independent execution outcome returned to tool handlers and agent."""
    operation: CapabilityType
    outcome: ExecutionOutcome
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    safe_message: str = ""
    is_simulated: bool = False
    authoritative_source: str = ""
    error: Optional[IntegrationError] = None
    correlation_id: Optional[str] = None
    latency_ms: float = 0.0
    idempotency_key: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class WebhookRequest(BaseModel):
    """Standardized representation of an incoming provider webhook HTTP request."""
    provider_id: str
    headers: Dict[str, str] = Field(default_factory=dict)
    raw_body: bytes = b""
    parsed_json: Optional[Dict[str, Any]] = None
    url: Optional[str] = None

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)


class WebhookResult(BaseModel):
    """Outcome of processing an incoming provider webhook."""
    success: bool
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    is_duplicate: bool = False
    processed: bool = True
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class TenantIntegrationRecord(BaseModel):
    """Tenant's persisted configuration and status for an integration."""
    tenant_id: str
    provider_id: str
    category: IntegrationCategory
    status: IntegrationLifecycleStatus
    granted_scopes: List[str] = Field(default_factory=list)
    selected_resources: Dict[str, Any] = Field(default_factory=dict)
    configuration_version: str = "1.0.0"
    last_health_check: Optional[str] = None
    last_error_category: Optional[str] = None
    audit_metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class IntegrationDiagnosticReport(BaseModel):
    """Redacted operational diagnosis for admin/dashboard consumption."""
    tenant_id: str
    provider_id: str
    category: IntegrationCategory
    status: IntegrationLifecycleStatus
    authoritative_source: str
    last_health_check: Optional[str] = None
    last_error_category: Optional[str] = None
    granted_scopes: List[str] = Field(default_factory=list)
    selected_resources: Dict[str, Any] = Field(default_factory=dict)
    recent_audit_events: List[Dict[str, Any]] = Field(default_factory=list)
    is_ready_for_agent: bool = False

    model_config = ConfigDict(extra="ignore")
