"""
Built-in Clinical Appointment Integration Adapter.
Provides authoritative first-party patient appointment scheduling using internal clinical suites.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import logging

from backend.integrations.base import ReservationAdapterInterface
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
)
from backend.database.engine import check_database_connection
from backend.database.repositories.reservation_repo import ReservationConflictError
import backend.database.service as db_service_mod


def get_database_service():
    return db_service_mod.get_database_service()


logger = logging.getLogger(__name__)


class BuiltinClinicAdapter(ReservationAdapterInterface):
    """First-party clinical scheduler managing patient appointment slots."""

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.BUILTIN_DATABASE

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="builtin_clinic",
            display_name="Built-in Clinical Scheduler",
            category=IntegrationCategory.APPOINTMENT,
            supported_capabilities=[
                CapabilityType.CHECK_AVAILABILITY,
                CapabilityType.CREATE_BOOKING,
                CapabilityType.GET_BOOKING,
                CapabilityType.CANCEL_BOOKING,
            ],
            auth_method=AuthMethod.INTERNAL,
            authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
            required_setup_fields=[
                SetupField(
                    key="slot_duration_minutes",
                    label="Appointment Slot Duration (Minutes)",
                    type=FieldType.INTEGER,
                    required=True,
                    default_value=30,
                    description="Standard clinical consultation length",
                ),
            ],
            required_resources=["rooms", "practitioners"],
            webhook_events=[],
            test_connection_procedure="Validates clinical database connectivity and registered consultation suites",
            known_limitations=[
                "Does not sync automatically with external hospital EHR / Epic systems.",
            ],
            is_mock=False,
        )

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        duration = config.get("slot_duration_minutes", 30)
        try:
            dur_int = int(duration)
            if dur_int < 10 or dur_int > 180:
                return ReadinessCheckResult(
                    check_id="config_slot_duration",
                    name="Consultation Length Validation",
                    passed=False,
                    details="Appointment duration must be between 10 and 180 minutes.",
                    severity="warning",
                )
        except (ValueError, TypeError):
            return ReadinessCheckResult(
                check_id="config_slot_duration",
                name="Consultation Length Validation",
                passed=False,
                details="Invalid consultation length format.",
                severity="critical",
            )
        return ReadinessCheckResult(
            check_id="config_slot_duration",
            name="Consultation Length Validation",
            passed=True,
            details=f"Consultation duration set to {duration} minutes",
            severity="warning",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        return ReadinessCheckResult(
            check_id="internal_auth",
            name="Clinical Engine Connection",
            passed=True,
            details="Connected to internal clinical database store.",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        try:
            svc = get_database_service()
            if hasattr(svc, "is_available"):
                db_ok = svc.is_available()
            elif hasattr(svc, "_engine") and svc._engine is not None:
                from sqlalchemy import text
                with svc._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                db_ok = True
            else:
                conn = check_database_connection(engine=getattr(svc, "_engine", None))
                db_ok = conn.get("connected", False)
        except Exception:
            db_ok = False

        return ReadinessCheckResult(
            check_id="db_connection",
            name="Clinical Database Connection",
            passed=db_ok,
            details="Connected to clinical database" if db_ok else "Database connection is offline",
            severity="critical",
        )

    def assess_readiness(self, db_service: Any = None) -> ReadinessReport:
        checks: List[ReadinessCheckResult] = []
        manifest = self.get_manifest()

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

        config_check = self.validate_configuration(self.configuration)
        checks.append(config_check)

        svc = db_service or get_database_service()
        try:
            if hasattr(svc, "is_available"):
                db_ok = svc.is_available()
            elif hasattr(svc, "_engine") and svc._engine is not None:
                from sqlalchemy import text
                with svc._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                db_ok = True
            else:
                conn = check_database_connection(engine=getattr(svc, "_engine", None))
                db_ok = conn.get("connected", False)
        except Exception:
            db_ok = False

        conn_check = ReadinessCheckResult(
            check_id="db_connection",
            name="Clinical Database Connection",
            passed=db_ok,
            details="Connected to clinical database" if db_ok else "Database connection is offline",
            severity="critical",
        )
        checks.append(conn_check)

        svc = db_service or get_database_service()
        practitioners = svc.list_resources(self.business_id, is_active=True)
        has_inventory = len(practitioners) > 0
        checks.append(
            ReadinessCheckResult(
                check_id="resource_inventory",
                name="Doctor / Practitioner Inventory",
                passed=has_inventory,
                details=f"Found {len(practitioners)} active doctor(s) / practitioner(s) taking appointments" if has_inventory else "No doctors configured for appointment scheduling",
                severity="critical",
            )
        )

        all_critical_passed = all(c.passed for c in checks if c.severity == "critical")
        if not has_inventory:
            status = CapabilityStatus.NEEDS_INPUT
        elif manifest.partner_approval_required and not self.configuration.get("partner_approved", False):
            status = CapabilityStatus.PENDING_PROVIDER_APPROVAL
        elif all_critical_passed:
            status = CapabilityStatus.READY
        else:
            status = CapabilityStatus.FAILED

        missing_reqs = [c.name for c in checks if not c.passed]
        return ReadinessReport(
            is_ready=all_critical_passed and status == CapabilityStatus.READY,
            status=status,
            checks=checks,
            missing_requirements=missing_reqs,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def discover_resources(self, resource_type: str = "practitioner") -> List[DiscoveredResource]:
        db_service = get_database_service()
        resources = db_service.list_resources(self.business_id, is_active=True)
        return [
            DiscoveredResource(
                resource_id=r["id"],
                name=r["name"],
                resource_type=r["resource_type"],
                metadata={
                    "capacity": r.get("capacity", 1),
                    "section": r.get("section", "Consultant"),
                    "available_days": (r.get("metadata") or {}).get("available_days", []),
                },
            )
            for r in resources
        ]

    def get_supported_capabilities(self) -> List[CapabilityType]:
        return [
            CapabilityType.CHECK_AVAILABILITY,
            CapabilityType.CREATE_BOOKING,
            CapabilityType.GET_BOOKING,
            CapabilityType.CANCEL_BOOKING,
        ]

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        def _dispatch() -> CapabilityResult:
            if operation == CapabilityType.CHECK_AVAILABILITY:
                start_iso = input_data.get("start_time")
                start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if "T" in str(start_iso) else datetime.strptime(str(start_iso), "%Y-%m-%d %H:%M")
                dur = int(self.configuration.get("slot_duration_minutes", 30))
                end_iso = input_data.get("end_time")
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else (start_dt + timedelta(minutes=dur))

                avail_res = self.check_availability(
                    start_time=start_dt,
                    end_time=end_dt,
                    party_size=1,
                    resource_type=input_data.get("resource_type", "room"),
                )
                if avail_res.get("available"):
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=avail_res,
                        safe_message="Clinical consultation slots are available for the requested time.",
                        authoritative_source=self.authoritative_source.value,
                    )
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.BUSINESS_REJECTION,
                    success=True,
                    data=avail_res,
                    safe_message="Doctor is not available at the requested time (weekly off or already booked).",
                    authoritative_source=self.authoritative_source.value,
                )

            elif operation == CapabilityType.CREATE_BOOKING:
                start_iso = input_data.get("start_time")
                start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if "T" in str(start_iso) else datetime.strptime(str(start_iso), "%Y-%m-%d %H:%M")
                dur = int(self.configuration.get("slot_duration_minutes", 30))
                end_iso = input_data.get("end_time")
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else (start_dt + timedelta(minutes=dur))

                try:
                    booking = self.create_reservation(
                        customer_name=input_data["customer_name"],
                        customer_phone=input_data["customer_phone"],
                        party_size=1,
                        start_time=start_dt,
                        end_time=end_dt,
                        special_requests=input_data.get("special_requests"),
                        idempotency_key=context.idempotency_key,
                    )
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=booking,
                        safe_message=f"Appointment confirmed for {input_data['customer_name']} (Ref: {booking['booking_reference']}).",
                        authoritative_source=self.authoritative_source.value,
                    )
                except ReservationConflictError as rce:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        data={"reason": "room_conflict", "details": str(rce)},
                        safe_message="The requested appointment slot is no longer open.",
                        authoritative_source=self.authoritative_source.value,
                        error=IntegrationError(
                            code="APPOINTMENT_CONFLICT",
                            category=ErrorCategory.CONFLICT,
                            message=str(rce),
                            safe_user_message="Appointment slot was just reserved by another patient.",
                            is_retryable=False,
                        ),
                    )

            elif operation == CapabilityType.GET_BOOKING:
                db_service = get_database_service()
                booking_id = input_data.get("booking_id", "")
                booking = db_service.get_reservation(self.business_id, booking_id)
                if booking:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=booking,
                        safe_message=f"Found appointment {booking_id}.",
                        authoritative_source=self.authoritative_source.value,
                    )
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_FAILED,
                    success=False,
                    safe_message=f"No appointment found with ID {booking_id}.",
                    authoritative_source=self.authoritative_source.value,
                    error=IntegrationError(
                        code="APPOINTMENT_NOT_FOUND",
                        category=ErrorCategory.RESOURCE_NOT_FOUND,
                        message=f"Appointment {booking_id} not found",
                        safe_user_message="Appointment not found.",
                        is_retryable=False,
                    ),
                )

            elif operation == CapabilityType.CANCEL_BOOKING:
                booking_id = input_data.get("booking_id", "")
                phone = input_data.get("customer_phone")
                cancelled = self.cancel_reservation(booking_id, phone)
                if cancelled:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data={"booking_id": booking_id, "status": "cancelled"},
                        safe_message=f"Appointment {booking_id} cancelled.",
                        authoritative_source=self.authoritative_source.value,
                    )
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_FAILED,
                    success=False,
                    safe_message=f"Unable to cancel appointment {booking_id}.",
                    authoritative_source=self.authoritative_source.value,
                    error=IntegrationError(
                        code="CANCELLATION_FAILED",
                        category=ErrorCategory.RESOURCE_NOT_FOUND,
                        message=f"Appointment {booking_id} could not be cancelled",
                        safe_user_message="Unable to cancel appointment.",
                        is_retryable=False,
                    ),
                )

            raise NotImplementedError(f"Operation {operation} not supported by BuiltinClinicAdapter")

        return self.execute_with_retry(operation, input_data, context, _dispatch)

    # ---------------------------------------------------------------------------
    # Concrete ReservationAdapterInterface implementation
    # ---------------------------------------------------------------------------

    def check_availability(
        self,
        start_time: datetime,
        end_time: datetime,
        party_size: int = 1,
        resource_type: str = "practitioner",
    ) -> Dict[str, Any]:
        """Query available clinical doctors/practitioners from database inventory."""
        db_service = get_database_service()
        # Look for practitioner first, fall back to any active resource
        available_rooms = db_service.find_available_resources(
            business_id=self.business_id,
            start_time=start_time,
            end_time=end_time,
            party_size=party_size,
            resource_type=resource_type or "practitioner",
        )
        if not available_rooms and resource_type == "practitioner":
            available_rooms = db_service.find_available_resources(
                business_id=self.business_id,
                start_time=start_time,
                end_time=end_time,
                party_size=party_size,
                resource_type="clinic_room",
            )

        return {
            "available": len(available_rooms) > 0,
            "party_size": party_size,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "available_resources": available_rooms,
            "count": len(available_rooms),
            "authoritative_source": self.authoritative_source.value,
        }

    def create_reservation(
        self,
        customer_name: str,
        customer_phone: str,
        party_size: int = 1,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resource_type: str = "practitioner",
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Commit clinical appointment to database."""
        db_service = get_database_service()
        booking = db_service.create_reservation_atomic(
            business_id=self.business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            party_size=party_size,
            start_time=start_time,
            end_time=end_dt if (end_dt := end_time) else None,
            resource_type=resource_type or "practitioner",
            special_requests=special_requests,
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "status": "confirmed",
            "booking_reference": booking["id"],
            "appointment_reference": booking["id"],
            "doctor_name": booking.get("resource_name"),
            "practitioner_name": booking.get("resource_name"),
            "room_name": booking.get("resource_name"),
            "table_name": booking.get("resource_name"),
            "customer_name": booking["customer_name"],
            "customer_phone": booking["customer_phone"],
            "party_size": booking["party_size"],
            "start_time": booking["start_time"],
            "end_time": booking["end_time"],
            "authoritative_source": self.authoritative_source.value,
            "is_simulated": False,
        }

    def cancel_reservation(
        self,
        reservation_id: str,
        customer_phone: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Cancel clinical appointment in database."""
        db_service = get_database_service()
        return db_service.cancel_reservation(
            business_id=self.business_id,
            reservation_id=reservation_id,
            customer_phone=customer_phone,
        )
