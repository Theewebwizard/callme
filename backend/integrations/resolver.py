"""
Integration Adapter Resolver.
Resolves authoritative provider adapter based on trusted tenant configuration at runtime.
Guarantees LLM never chooses arbitrary providers, credentials, or connection IDs.
"""

from typing import Optional, Dict, Any, List
import logging

from backend.integrations.base import BaseIntegrationAdapter
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
)
from backend.capabilities.credentials import decrypt_credentials
from backend.capabilities.models import AuthoritativeSource, CapabilityStatus, ReadinessReport, ReadinessCheckResult
from backend.database.service import get_database_service
from backend.integrations.registry import get_integration_registry

logger = logging.getLogger(__name__)


class UnconfiguredAdapter(BaseIntegrationAdapter):
    """Fallback adapter representing an unconfigured or uninitialized capability."""

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.COMMUNICATION_SERVICE

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="unconfigured",
            display_name="Unconfigured Provider",
            category=IntegrationCategory.SUPPORT,
            supported_capabilities=[],
            auth_method=AuthMethod.INTERNAL,
            authoritative_source=AuthoritativeSource.COMMUNICATION_SERVICE,
        )

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        return ReadinessCheckResult(
            check_id="unconfigured_check",
            name="Unconfigured",
            passed=False,
            details="Capability is not configured.",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        return ReadinessCheckResult(
            check_id="unconfigured_connect",
            name="Unconfigured",
            passed=False,
            details="Cannot connect unconfigured capability.",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        return ReadinessCheckResult(
            check_id="unconfigured_test",
            name="Unconfigured",
            passed=False,
            details="Capability is not configured.",
            severity="critical",
        )

    def discover_resources(self, resource_type: str) -> List[DiscoveredResource]:
        return []

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return []

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        return CapabilityResult(
            operation=operation,
            outcome=ExecutionOutcome.OPERATION_FAILED,
            success=False,
            safe_message="Capability is not configured.",
            authoritative_source=self.authoritative_source.value,
            error=IntegrationError(
                code="NOT_CONFIGURED",
                category=ErrorCategory.PROVIDER_UNAVAILABLE,
                message="Integration is not configured",
                safe_user_message="Capability not configured.",
                is_retryable=False,
            ),
        )

    def check_connection(self) -> Dict[str, Any]:
        return {"connected": False, "status": "not_configured"}

    def validate_permissions(self) -> Dict[str, Any]:
        return {"valid": False, "error": "Capability is not configured."}

    def assess_readiness(self, db_service: Any) -> ReadinessReport:
        from datetime import datetime, timezone
        return ReadinessReport(
            is_ready=False,
            status=CapabilityStatus.NOT_CONFIGURED,
            checks=[],
            missing_requirements=["Capability has not been configured in Setup Wizard."],
            checked_at=datetime.now(timezone.utc).isoformat(),
        )


def resolve_tool_adapter(
    business_id: str,
    tool_id: str,
    db_service: Optional[Any] = None,
) -> BaseIntegrationAdapter:
    """
    Resolve and instantiate the authoritative integration adapter for a tenant tool.
    Strictly tenant-scoped; decrypts stored credentials and injects configuration.
    """
    if db_service is None:
        db_service = get_database_service()

    cfg = db_service.get_tool_config(business_id, tool_id)
    selected_option = cfg.get("selected_option_id") if cfg else None
    configuration = cfg.get("configuration", {}) if cfg else {}

    # 1. Retrieve decrypted credentials if credential record exists
    credentials: Dict[str, Any] = {}
    cred_rec = db_service.get_credential_raw(business_id, tool_id)
    if cred_rec and cred_rec.get("encrypted_secrets"):
        try:
            credentials = decrypt_credentials(cred_rec["encrypted_secrets"])
        except Exception as exc:
            logger.error("Failed decrypting credentials for tenant %s tool %s: %s", business_id, tool_id, exc)

    # 2. Try registry lookup
    registry = get_integration_registry()
    if selected_option and registry.get_adapter_class(selected_option):
        return registry.create_adapter(
            provider_id=selected_option,
            business_id=business_id,
            tool_id=tool_id,
            configuration=configuration,
            credentials=credentials,
        )

    # 3. Default fallbacks by tool type
    if tool_id in ("check_table_availability", "create_table_booking"):
        return registry.create_adapter(
            provider_id="builtin_dining",
            business_id=business_id,
            tool_id=tool_id,
            configuration=configuration,
            credentials=credentials,
        )

    if tool_id in ("check_appointment_availability", "create_appointment"):
        return registry.create_adapter(
            provider_id="builtin_clinic",
            business_id=business_id,
            tool_id=tool_id,
            configuration=configuration,
            credentials=credentials,
        )

    if tool_id in ("manage_bookings", "book_resource", "book_room", "schedule_service"):
        return registry.create_adapter(
            provider_id="builtin_booking",
            business_id=business_id,
            tool_id=tool_id,
            configuration=configuration,
            credentials=credentials,
        )

    if tool_id == "transfer_call":
        return registry.create_adapter(
            provider_id="exotel",
            business_id=business_id,
            tool_id=tool_id,
            configuration=configuration,
            credentials=credentials,
        )

    if tool_id == "take_message":
        return registry.create_adapter(
            provider_id="twilio",
            business_id=business_id,
            tool_id=tool_id,
            configuration=configuration,
            credentials=credentials,
        )

    return UnconfiguredAdapter(
        business_id=business_id,
        tool_id=tool_id,
        option_id=selected_option or "unconfigured",
        configuration=configuration,
        credentials=credentials,
    )
