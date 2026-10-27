"""
Capability Setup Wizard and Readiness State Machine.
Guides businesses through declarative tool onboarding, validates connectivity,
isolates secrets, and activates verified operational capabilities.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging
import uuid
import re

from backend.capabilities.models import (
    CapabilityStatus,
    CapabilityStateSummary,
    ReadinessReport,
    ReadinessCheckResult,
    ToolCapabilityRequirement,
    IntegrationOption,
    FieldType,
)
from backend.capabilities.specs import (
    get_capability_spec,
    list_all_capability_specs,
    TOOL_CAPABILITY_SPECS,
)
from backend.capabilities.credentials import (
    encrypt_credentials,
    redact_credential_dict,
)
from backend.database.service import DatabaseService, get_database_service

logger = logging.getLogger(__name__)


class CapabilitySetupWizard:
    """Server-side state machine orchestrating guided capability onboarding."""

    def __init__(self, db_service: Optional[DatabaseService] = None) -> None:
        self.db = db_service or get_database_service()

    def _resolve_adapter(self, business_id: str, tool_id: str):
        from backend.integrations.resolver import resolve_tool_adapter
        return resolve_tool_adapter(business_id, tool_id, self.db)

    def get_capability_summary(self, business_id: str, tool_id: str) -> Optional[CapabilityStateSummary]:
        """Fetch real-time capability status and readiness for a tenant."""
        spec = get_capability_spec(tool_id)
        if not spec:
            return None

        cfg = self.db.get_tool_config(business_id, tool_id)
        is_enabled = cfg.get("is_enabled", False) if cfg else False
        stored_status = cfg.get("status", CapabilityStatus.NOT_CONFIGURED.value) if cfg else CapabilityStatus.NOT_CONFIGURED.value
        selected_option = cfg.get("selected_option_id") if cfg else None

        # Resolve authoritative adapter and evaluate live readiness
        adapter = self._resolve_adapter(business_id, tool_id)
        readiness = adapter.assess_readiness(self.db)

        # Selected option name
        opt_name = None
        for opt in spec.supported_options:
            if opt.option_id == selected_option:
                opt_name = opt.name
                break

        return CapabilityStateSummary(
            tool_id=tool_id,
            tool_name=spec.name,
            is_enabled=is_enabled,
            status=CapabilityStatus(readiness.status.value) if is_enabled else CapabilityStatus(stored_status),
            selected_option_id=selected_option,
            selected_option_name=opt_name,
            authoritative_source=adapter.authoritative_source.value,
            is_ready=readiness.is_ready,
            missing_requirements=readiness.missing_requirements,
            last_validated_at=readiness.checked_at,
            readiness_report=readiness,
        )

    def list_capabilities(self, business_id: str) -> List[CapabilityStateSummary]:
        """List all capabilities available for the tenant's industry with readiness states."""
        profile = self.db.get_business_profile(business_id)
        biz_industry = profile.get("industry") if profile else None

        from backend.tools.base import normalize_industry_name
        canonical_ind = normalize_industry_name(biz_industry)

        summaries = []
        for tool_id, spec in TOOL_CAPABILITY_SPECS.items():
            # Check industry compatibility
            is_compatible = (
                "*" in spec.allowed_canonical_industries
                or canonical_ind in spec.allowed_canonical_industries
            )
            if not is_compatible:
                continue

            summary = self.get_capability_summary(business_id, tool_id)
            if summary:
                summaries.append(summary)

        return summaries

    def start_setup_session(
        self,
        business_id: str,
        tool_id: str,
        option_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate or resume a guided capability onboarding session."""
        spec = get_capability_spec(tool_id)
        if not spec:
            raise ValueError(f"Tool '{tool_id}' is not registered in capability catalog.")

        # If option_id not provided, check if existing session or config has one
        if not option_id:
            cfg = self.db.get_tool_config(business_id, tool_id)
            if cfg and cfg.get("selected_option_id"):
                option_id = cfg["selected_option_id"]
            elif spec.supported_options:
                option_id = spec.supported_options[0].option_id

        # Validate option_id belongs to spec
        valid_options = {opt.option_id: opt for opt in spec.supported_options}
        if option_id and option_id not in valid_options:
            raise ValueError(f"Integration option '{option_id}' is not supported for tool '{tool_id}'.")

        sess = self.db.save_setup_session(
            business_id=business_id,
            tool_id=tool_id,
            selected_option_id=option_id,
            current_step="configure_parameters",
            status="needs_input",
        )

        self.db.record_capability_audit(
            business_id=business_id,
            tool_id=tool_id,
            event_type="setup_session_started",
            details={"option_id": option_id, "session_id": sess["id"]},
        )

        selected_opt_obj = valid_options.get(option_id)
        return {
            "id": sess["id"],
            "session_id": sess["id"],
            "tool_id": tool_id,
            "tool_name": spec.name,
            "selected_option_id": option_id,
            "selected_option": selected_opt_obj.model_dump() if selected_opt_obj else None,
            "supported_options": [opt.model_dump() for opt in spec.supported_options],
            "current_step": sess["current_step"],
            "step_data": redact_credential_dict(sess.get("step_data", {})),
            "status": sess["status"],
            "instructions": selected_opt_obj.instructions_markdown if selected_opt_obj else "",
        }

    def save_step(
        self,
        business_id: str,
        session_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        step_id: str = "configure_parameters",
        step_name: Optional[str] = None,
        is_completed: bool = False,
    ) -> Dict[str, Any]:
        """Validate and persist step inputs, isolating secrets into encrypted vault."""
        if not session_id and tool_id:
            s = self.db.get_setup_session_by_tool(business_id, tool_id)
            if s:
                session_id = s["id"]
        if not session_id:
            raise ValueError("session_id or valid tool_id required.")

        sess = self.db.get_setup_session(session_id, business_id=business_id)
        if not sess:
            raise ValueError(f"Setup session '{session_id}' not found for tenant.")

        tool_id = sess["tool_id"]
        option_id = sess.get("selected_option_id")
        effective_data = input_data if input_data is not None else (data or {})
        effective_step = step_name or step_id

        spec = get_capability_spec(tool_id)
        if not spec:
            raise ValueError(f"Tool specification '{tool_id}' not found.")

        target_opt = next((o for o in spec.supported_options if o.option_id == option_id), None)
        if not target_opt:
            raise ValueError(f"Invalid option '{option_id}' for tool '{tool_id}'.")

        # 1. Validate fields against declared schema
        validation_errors = []
        non_secret_data: Dict[str, Any] = {}
        secret_data: Dict[str, Any] = {}

        for field in target_opt.setup_fields:
            val = effective_data.get(field.key)
            if val is None or val == "":
                # Check if already present in session or existing credentials
                existing_val = sess.get("step_data", {}).get(field.key)
                if existing_val is not None:
                    val = existing_val
                elif field.default_value is not None:
                    val = field.default_value
                elif field.required:
                    validation_errors.append({
                        "field": field.key,
                        "error": f"Field '{field.label}' is required.",
                    })
                    continue
                else:
                    val = field.default_value

            # Type validation & regex
            if val is not None:
                if field.type == FieldType.INTEGER:
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        validation_errors.append({"field": field.key, "error": f"'{field.label}' must be an integer."})
                        continue
                elif field.type == FieldType.BOOLEAN:
                    val = bool(val)
                elif field.type == FieldType.STRING and field.validation_regex:
                    if not re.match(field.validation_regex, str(val)):
                        validation_errors.append({"field": field.key, "error": f"'{field.label}' has invalid format."})
                        continue

            if field.secret:
                if val:
                    secret_data[field.key] = val
            else:
                non_secret_data[field.key] = val

        if validation_errors:
            self.db.save_setup_session(
                business_id=business_id,
                tool_id=tool_id,
                session_id=session_id,
                status="needs_input",
                validation_errors=validation_errors,
            )
            return {
                "success": False,
                "session_id": session_id,
                "status": "needs_input",
                "validation_errors": validation_errors,
            }

        # 2. Encrypt and store secrets separately
        if secret_data:
            encrypted_payload, fingerprint = encrypt_credentials(secret_data)
            self.db.save_credential(
                business_id=business_id,
                tool_id=tool_id,
                option_id=option_id,
                encrypted_secrets=encrypted_payload,
                key_fingerprint=fingerprint,
                scopes=target_opt.required_scopes,
            )
            logger.info("Encrypted and stored credentials for tenant %s tool %s (Fingerprint: %s)", business_id, tool_id, fingerprint)

        # 3. Save non-secret parameters to session
        updated_sess = self.db.save_setup_session(
            business_id=business_id,
            tool_id=tool_id,
            session_id=session_id,
            current_step=step_id,
            step_data=non_secret_data,
            status="validating",
            validation_errors=[],
        )

        self.db.record_capability_audit(
            business_id=business_id,
            tool_id=tool_id,
            event_type="setup_step_saved",
            details={"step_id": step_id, "fields_saved": list(non_secret_data.keys())},
        )

        return {
            "success": True,
            "session_id": session_id,
            "status": updated_sess["status"],
            "current_step": updated_sess["current_step"],
            "step_data": redact_credential_dict(updated_sess["step_data"]),
        }

    def validate_session(
        self,
        business_id: str,
        session_id: Optional[str] = None,
        tool_id: Optional[str] = None,
    ) -> ReadinessReport:
        """Execute connectivity and operational readiness checks on the configured setup."""
        if not session_id and tool_id:
            s = self.db.get_setup_session_by_tool(business_id, tool_id)
            if s:
                session_id = s["id"]
        if not session_id:
            raise ValueError("session_id or valid tool_id required.")

        sess = None
        if session_id:
            sess = self.db.get_setup_session(session_id, business_id=business_id)
            if not sess:
                # Fallback: check if caller passed tool_id into session_id positionally
                sess = self.db.get_setup_session_by_tool(business_id, session_id)
        if not sess and tool_id:
            sess = self.db.get_setup_session_by_tool(business_id, tool_id)

        if not sess:
            raise ValueError(f"Setup session '{session_id or tool_id}' not found.")

        tool_id = sess["tool_id"]
        option_id = sess["selected_option_id"]
        step_data = sess.get("step_data", {})

        # Temporarily stage configuration for testing
        self.db.set_tool_capability(
            business_id=business_id,
            tool_id=tool_id,
            selected_option_id=option_id,
            configuration=step_data,
        )

        adapter = self._resolve_adapter(business_id, tool_id)
        report = adapter.assess_readiness(self.db)

        new_status = "ready" if report.is_ready else "failed"
        self.db.save_setup_session(
            business_id=business_id,
            tool_id=tool_id,
            session_id=session_id,
            status=new_status,
            validation_errors=[{"error": m} for m in report.missing_requirements],
        )

        self.db.set_tool_capability(
            business_id=business_id,
            tool_id=tool_id,
            status=report.status.value,
            readiness_details=report.model_dump(),
        )

        self.db.record_capability_audit(
            business_id=business_id,
            tool_id=tool_id,
            event_type="readiness_validated",
            details={"is_ready": report.is_ready, "status": report.status.value, "missing": report.missing_requirements},
        )

        return report

    def activate_capability(self, business_id: str, tool_id: str) -> Dict[str, Any]:
        """
        Activate a tool capability after strictly verifying that all mandatory readiness checks pass.
        Never activates an incomplete or unverified capability.
        """
        adapter = self._resolve_adapter(business_id, tool_id)
        report = adapter.assess_readiness(self.db)

        if not report.is_ready:
            missing_str = "; ".join(report.missing_requirements)
            logger.warning("Activation rejected for tenant %s tool %s: %s", business_id, tool_id, missing_str)
            raise ValueError(f"Cannot activate capability '{tool_id}'. Missing requirements: {missing_str}")

        cfg = self.db.set_tool_capability(
            business_id=business_id,
            tool_id=tool_id,
            is_enabled=True,
            status=CapabilityStatus.READY.value,
            readiness_details=report.model_dump(),
        )

        self.db.record_capability_audit(
            business_id=business_id,
            tool_id=tool_id,
            event_type="capability_activated",
            details={"tool_id": tool_id, "option_id": cfg.get("selected_option_id")},
        )

        return {
            "success": True,
            "tool_id": tool_id,
            "is_enabled": True,
            "status": CapabilityStatus.READY.value,
            "message": f"Capability '{tool_id}' successfully activated and verified ready for live calls.",
        }

    def deactivate_capability(self, business_id: str, tool_id: str) -> Dict[str, Any]:
        """Deactivate a tool capability."""
        cfg = self.db.set_tool_capability(
            business_id=business_id,
            tool_id=tool_id,
            is_enabled=False,
            status=CapabilityStatus.NOT_CONFIGURED.value,
        )

        self.db.record_capability_audit(
            business_id=business_id,
            tool_id=tool_id,
            event_type="capability_deactivated",
            details={"tool_id": tool_id},
        )

        return {
            "success": True,
            "tool_id": tool_id,
            "is_enabled": False,
            "status": cfg.get("status"),
        }

    def disconnect_integration(self, business_id: str, tool_id: str) -> Dict[str, Any]:
        """Disconnect external provider, purge credentials, and mark disconnected."""
        # 1. Purge credentials
        self.db.delete_credential(business_id, tool_id)

        # 2. Deactivate and mark disconnected
        cfg = self.db.set_tool_capability(
            business_id=business_id,
            tool_id=tool_id,
            is_enabled=False,
            status=CapabilityStatus.DISCONNECTED.value,
            configuration={},
            readiness_details={},
        )

        # 3. Clean up active setup session
        sess = self.db.get_setup_session_by_tool(business_id, tool_id)
        if sess:
            self.db.delete_setup_session(sess["id"], business_id=business_id)

        self.db.record_capability_audit(
            business_id=business_id,
            tool_id=tool_id,
            event_type="integration_disconnected",
            details={"tool_id": tool_id},
        )

        return {
            "success": True,
            "tool_id": tool_id,
            "status": CapabilityStatus.DISCONNECTED.value,
            "message": f"Integration for '{tool_id}' disconnected and credentials securely purged.",
        }

    def discover_resources(
        self,
        business_id: str,
        tool_id: str,
        resource_type: str = "",
    ) -> List[Dict[str, Any]]:
        """Discover available external or internal resources through adapter."""
        adapter = self._resolve_adapter(business_id, tool_id)
        resources = adapter.discover_resources(resource_type)
        return [r.model_dump() for r in resources]

    def test_connection(
        self,
        business_id: str,
        tool_id: str,
    ) -> Dict[str, Any]:
        """Safely test connection without creating real bookings or charges."""
        adapter = self._resolve_adapter(business_id, tool_id)
        res = adapter.test_connection()
        return {
            "passed": res.passed,
            "details": res.details,
            "check_id": res.check_id,
        }


_default_wizard: Optional[CapabilitySetupWizard] = None


def get_setup_wizard() -> CapabilitySetupWizard:
    """Return singleton CapabilitySetupWizard instance."""
    global _default_wizard
    if _default_wizard is None:
        _default_wizard = CapabilitySetupWizard()
    return _default_wizard
