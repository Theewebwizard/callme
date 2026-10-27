"""
Domain models for the declarative capability setup wizard, integration architecture,
and tenant readiness state machine.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class CapabilityStatus(str, Enum):
    """Lifecycle state machine for a tenant's configured capability."""
    NOT_CONFIGURED = "not_configured"
    NEEDS_INPUT = "needs_input"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    VALIDATING = "validating"
    READY = "ready"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    PENDING_PROVIDER_APPROVAL = "pending_provider_approval"


class AuthoritativeSource(str, Enum):
    """Authoritative source of truth declaring system of record for the capability."""
    BUILTIN_DATABASE = "builtin_database"
    EXTERNAL_CALENDAR = "external_calendar"
    EXTERNAL_RESERVATION = "external_reservation"
    EXTERNAL_RESERVATION_SYSTEM = "external_reservation"
    TELEPHONY_PROVIDER = "telephony_provider"
    COMMUNICATION_SERVICE = "communication_service"
    PAYMENT_GATEWAY = "payment_gateway"
    CRM_SYSTEM = "crm_system"
    SUPPORT_DESK = "support_desk"



class FailureBehavior(str, Enum):
    """Policy declaring how the tool boundary behaves when the capability is unavailable."""
    FAIL_CLOSED = "fail_closed"
    DEGRADED_RESPONSE = "degraded_response"
    FALLBACK_OPERATOR = "fallback_operator"


class FieldType(str, Enum):
    """Data type of a setup wizard configuration input."""
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    SELECT = "select"
    PASSWORD = "password"
    TEXT = "text"


class SetupField(BaseModel):
    """Declarative specification for a configuration field required during setup."""
    key: str
    label: str
    type: FieldType = FieldType.STRING
    required: bool = True
    secret: bool = False
    description: str = ""
    default_value: Optional[Any] = None
    options: Optional[List[Dict[str, str]]] = None  # [{"value": "val", "label": "Label"}]
    validation_regex: Optional[str] = None
    placeholder: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ReadinessCheckResult(BaseModel):
    """Result of an individual readiness verification check."""
    check_id: str
    name: str
    passed: bool
    details: str
    severity: str = "critical"  # "critical", "warning"

    model_config = ConfigDict(extra="ignore")


class ReadinessReport(BaseModel):
    """Comprehensive readiness assessment report for a tenant capability."""
    is_ready: bool
    status: CapabilityStatus
    checks: List[ReadinessCheckResult] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    checked_at: str

    model_config = ConfigDict(extra="ignore")


class IntegrationOption(BaseModel):
    """
    A concrete deployment choice for a tool (e.g. Built-in Table Manager vs External SevenRooms).
    Declares whether it is built-in or external, credentials needed, and authoritative source.
    """
    option_id: str
    name: str
    description: str
    is_built_in: bool
    requires_external_connection: bool
    authoritative_source: AuthoritativeSource
    setup_fields: List[SetupField] = Field(default_factory=list)
    required_scopes: List[str] = Field(default_factory=list)
    instructions_markdown: str = ""

    model_config = ConfigDict(extra="ignore")


class ToolCapabilityRequirement(BaseModel):
    """
    Canonical specification declaring what a tool requires, its supported options,
    setup questions, authoritative system, and failure policy.
    """
    tool_id: str
    version: str = "1.0.0"
    name: str
    description: str
    category: str
    allowed_canonical_industries: List[str] = Field(default_factory=lambda: ["*"])
    supported_options: List[IntegrationOption] = Field(default_factory=list)
    failure_behavior: FailureBehavior = FailureBehavior.FAIL_CLOSED
    requires_confirmation: bool = False
    input_schema_summary: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class CapabilityStateSummary(BaseModel):
    """Tenant-scoped summary of a tool's capability status and readiness."""
    tool_id: str
    tool_name: str
    is_enabled: bool
    status: CapabilityStatus
    selected_option_id: Optional[str] = None
    selected_option_name: Optional[str] = None
    authoritative_source: Optional[str] = None
    is_ready: bool
    missing_requirements: List[str] = Field(default_factory=list)
    last_validated_at: Optional[str] = None
    readiness_report: Optional[ReadinessReport] = None

    model_config = ConfigDict(extra="ignore")
