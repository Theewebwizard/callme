"""
Base interfaces and domain contracts for tenant integration adapters.
Defines common lifecycle operations, retry policies, webhook handling,
and provider-independent capability execution.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
import time
import random
import logging

from backend.capabilities.models import (
    ReadinessReport,
    ReadinessCheckResult,
    CapabilityStatus,
    AuthoritativeSource,
)
from backend.integrations.models import (
    ProviderManifest,
    DiscoveredResource,
    CapabilityType,
    ExecutionContext,
    CapabilityResult,
    WebhookRequest,
    WebhookResult,
    ExecutionOutcome,
    IntegrationError,
    ErrorCategory,
    SideEffectClassification,
)
from backend.integrations.contracts import CAPABILITY_CONTRACTS

logger = logging.getLogger(__name__)


class IntegrationAdapter(ABC):
    """
    Common lifecycle and capability execution interface for all integration providers.
    Each adapter encapsulates connectivity, credentials, resource discovery,
    safe capability execution, and webhook verification for a provider.
    """

    def __init__(
        self,
        business_id: str,
        tool_id: str = "",
        option_id: str = "",
        configuration: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.business_id = business_id
        self.tool_id = tool_id
        self.option_id = option_id
        self.configuration = configuration or {}
        self.credentials = credentials or {}

    @property
    def tenant_id(self) -> str:
        """Alias for multi-tenant business identifier."""
        return self.business_id

    @property
    def provider_id(self) -> str:
        """Alias for integration provider identifier."""
        return self.option_id or self.get_manifest().provider_id

    # ---------------------------------------------------------------------------
    # Core Adapter Lifecycle Interface
    # ---------------------------------------------------------------------------

    @abstractmethod
    def get_manifest(self) -> ProviderManifest:
        """Return static declarative manifest defining capabilities, auth, and setup fields."""
        pass

    @abstractmethod
    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate non-secret configuration fields against provider rules."""
        pass

    @abstractmethod
    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate credentials and establish authenticated session or client."""
        pass

    @abstractmethod
    def test_connection(self) -> ReadinessCheckResult:
        """Safely probe connectivity without creating side effects (e.g. ping/profile check)."""
        pass

    @abstractmethod
    def discover_resources(self, resource_type: str) -> List[DiscoveredResource]:
        """Query and list available provider resources (calendars, phone numbers, tables, staff)."""
        pass

    @abstractmethod
    def get_supported_capabilities(self) -> List[CapabilityType]:
        """Return list of capabilities currently supported and ready for this adapter."""
        pass

    @abstractmethod
    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """Execute a validated capability contract through the provider."""
        pass

    def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        """Process incoming provider webhook; default base verifies not supported."""
        return WebhookResult(
            success=False,
            processed=False,
            message=f"Webhooks not supported for provider '{self.provider_id}'",
        )

    def refresh_credentials(self) -> Optional[Dict[str, Any]]:
        """Refresh expired OAuth access token or bearer credential if supported."""
        return None

    def disconnect(self) -> bool:
        """Tear down client connections and clean up local adapter state."""
        return True

    # ---------------------------------------------------------------------------
    # Reliable Execution Helper with Retry, Backoff, and Idempotency Guard
    # ---------------------------------------------------------------------------

    def execute_with_retry(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
        dispatch_fn: Callable[[], CapabilityResult],
    ) -> CapabilityResult:
        """
        Execute an operation with bounded timeout, rate-limit adherence, exponential backoff,
        and protection against ambiguous outcomes on non-idempotent operations.
        """
        contract = CAPABILITY_CONTRACTS.get(operation)
        timeout_sec = context.timeout_override or (contract.default_timeout_seconds if contract else 8.0)
        max_retries = contract.max_retries if contract else 0
        side_effect = contract.side_effect if contract else SideEffectClassification.NON_IDEMPOTENT_WRITE

        start_time = time.time()
        attempt = 0

        while True:
            attempt += 1
            try:
                result = dispatch_fn()
                result.latency_ms = round((time.time() - start_time) * 1000, 2)
                result.correlation_id = context.correlation_id
                result.idempotency_key = context.idempotency_key

                # If successful or non-retryable business rejection, return immediately
                if result.success or result.outcome in (ExecutionOutcome.BUSINESS_REJECTION, ExecutionOutcome.REQUEST_ACCEPTED):
                    return result

                # Check if error is retryable
                is_retryable = False
                retry_after = 0.0
                if result.error:
                    is_retryable = result.error.is_retryable
                    if result.error.retry_after_seconds:
                        retry_after = result.error.retry_after_seconds

                # NEVER automatically retry non-idempotent operations without idempotency guarantee
                if side_effect in (SideEffectClassification.NON_IDEMPOTENT_WRITE, SideEffectClassification.FINANCIAL):
                    if not context.idempotency_key:
                        logger.warning(
                            "Suppressing automatic retry for non-idempotent operation %s on provider %s (attempt %d)",
                            operation.value, self.provider_id, attempt
                        )
                        return result

                if attempt > max_retries or not is_retryable:
                    return result

                # Compute backoff with jitter
                backoff_time = retry_after if retry_after > 0 else min(10.0, (0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.25))
                logger.info(
                    "Retrying operation %s on provider %s (attempt %d/%d) after %.2fs backoff",
                    operation.value, self.provider_id, attempt, max_retries, backoff_time
                )
                time.sleep(backoff_time)

            except TimeoutError as timeout_exc:
                latency_ms = round((time.time() - start_time) * 1000, 2)
                # If timeout occurs on a non-idempotent operation, return OUTCOME_UNKNOWN
                if side_effect in (SideEffectClassification.NON_IDEMPOTENT_WRITE, SideEffectClassification.FINANCIAL):
                    logger.error(
                        "Timeout on non-idempotent operation %s for tenant %s. Ambiguous outcome detected.",
                        operation.value, self.tenant_id
                    )
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OUTCOME_UNKNOWN,
                        success=False,
                        authoritative_source=self.authoritative_source.value,
                        safe_message=(
                            "The operation timed out while waiting for the external system; "
                            "outcome is currently ambiguous. Please check status before attempting again to avoid duplicate actions."
                        ),
                        error=IntegrationError(
                            code="AMBIGUOUS_TIMEOUT",
                            category=ErrorCategory.AMBIGUOUS_OUTCOME,
                            message=f"Timeout after {timeout_sec}s; external state unknown.",
                            safe_user_message="Request timed out. Outcome is currently ambiguous.",
                            is_retryable=False,
                        ),
                        correlation_id=context.correlation_id,
                        latency_ms=latency_ms,
                    )
                if attempt > max_retries:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_FAILED,
                        success=False,
                        authoritative_source=self.authoritative_source.value,
                        safe_message="Operation timed out while contacting integration provider.",
                        error=IntegrationError(
                            code="REQUEST_TIMEOUT",
                            category=ErrorCategory.TIMEOUT,
                            message=str(timeout_exc),
                            safe_user_message="Connection to provider timed out.",
                            is_retryable=True,
                        ),
                        correlation_id=context.correlation_id,
                        latency_ms=latency_ms,
                    )
                time.sleep(min(5.0, 0.5 * (2 ** (attempt - 1)) + random.uniform(0.05, 0.2)))

            except Exception as exc:
                latency_ms = round((time.time() - start_time) * 1000, 2)
                logger.error("Unhandled error executing %s on %s: %s", operation.value, self.provider_id, exc)
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_FAILED,
                    success=False,
                    authoritative_source=self.authoritative_source.value,
                    safe_message="An unexpected integration error occurred.",
                    error=IntegrationError(
                        code="INTERNAL_ADAPTER_ERROR",
                        category=ErrorCategory.PROVIDER_UNAVAILABLE,
                        message=f"{type(exc).__name__}: {str(exc)}",
                        safe_user_message="Service encountered an internal provider error.",
                        is_retryable=False,
                    ),
                    correlation_id=context.correlation_id,
                    latency_ms=latency_ms,
                )

    # ---------------------------------------------------------------------------
    # Backwards Compatibility Methods for Existing Tool Callers & Readiness Checks
    # ---------------------------------------------------------------------------

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        """Declare authoritative system of record."""
        return self.get_manifest().authoritative_source

    def check_connection(self) -> Dict[str, Any]:
        """Backwards compatible probe method."""
        check = self.test_connection()
        return {
            "connected": check.passed,
            "details": check.details,
            "status": "connected" if check.passed else "failed",
        }

    def validate_permissions(self) -> Dict[str, Any]:
        """Backwards compatible permission verification."""
        manifest = self.get_manifest()
        required_scopes = manifest.required_oauth_scopes
        granted_scopes = self.credentials.get("scopes", [])
        missing = [s for s in required_scopes if s not in granted_scopes]
        return {
            "valid": len(missing) == 0,
            "missing_scopes": missing,
            "error": f"Missing required scopes: {missing}" if missing else None,
        }

    def assess_readiness(self, db_service: Any) -> ReadinessReport:
        """Run all mandatory readiness checks and compile report."""
        checks: List[ReadinessCheckResult] = []
        manifest = self.get_manifest()

        # 1. Partner Approval Check
        if manifest.partner_approval_required:
            is_approved = self.configuration.get("partner_approved", False)
            checks.append(
                ReadinessCheckResult(
                    check_id="partner_approval",
                    name="Partner Access Approval",
                    passed=bool(is_approved),
                    details="Partner production approval granted" if is_approved else "Pending provider partner approval",
                    severity="critical",
                )
            )

        # 2. Configuration Validation
        config_check = self.validate_configuration(self.configuration)
        checks.append(config_check)

        # 3. Connectivity Probe
        conn_check = self.test_connection()
        checks.append(conn_check)

        # 4. Permissions Check
        perm_res = self.validate_permissions()
        perm_passed = perm_res.get("valid", False)
        checks.append(
            ReadinessCheckResult(
                check_id="permissions_valid",
                name="API Scope & Permissions Check",
                passed=perm_passed,
                details="All required scopes granted" if perm_passed else str(perm_res.get("error", "Missing scopes")),
                severity="critical",
            )
        )

        all_critical_passed = all(c.passed for c in checks if c.severity == "critical")
        status = CapabilityStatus.READY if all_critical_passed else CapabilityStatus.FAILED

        if manifest.partner_approval_required and not self.configuration.get("partner_approved", False):
            status = CapabilityStatus.PENDING_PROVIDER_APPROVAL

        missing_reqs = [c.name for c in checks if not c.passed]

        return ReadinessReport(
            is_ready=all_critical_passed and status == CapabilityStatus.READY,
            status=status,
            checks=checks,
            missing_requirements=missing_reqs,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )


# Backward-compatible alias for existing codebase
BaseIntegrationAdapter = IntegrationAdapter


class ReservationAdapterInterface(IntegrationAdapter):
    """Domain interface for dining table reservation and clinical appointment adapters."""

    @abstractmethod
    def check_availability(
        self,
        start_time: datetime,
        end_time: datetime,
        party_size: int,
        resource_type: str = "table",
    ) -> Dict[str, Any]:
        """Inspect available slots for party size and time window."""
        pass

    @abstractmethod
    def create_reservation(
        self,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: datetime,
        end_time: datetime,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a confirmed reservation or appointment."""
        pass

    @abstractmethod
    def cancel_reservation(
        self,
        reservation_id: str,
        customer_phone: Optional[str] = None,
    ) -> bool:
        """Cancel an existing reservation."""
        pass
