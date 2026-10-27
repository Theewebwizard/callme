"""
Built-in Dining Table and Capacity Management Integration Adapter.
Provides authoritative first-party table booking using the transactional database.
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
    WebhookRequest,
    WebhookResult,
)
from backend.database.engine import check_database_connection
from backend.database.repositories.reservation_repo import ReservationConflictError
import backend.database.service as db_service_mod


def get_database_service():
    return db_service_mod.get_database_service()


logger = logging.getLogger(__name__)


class BuiltinDiningAdapter(ReservationAdapterInterface):
    """
    First-party table reservation adapter.
    Uses tenant's configured reservable tables and transactional database.
    """

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        return AuthoritativeSource.BUILTIN_DATABASE

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="builtin_dining",
            display_name="Built-in Restaurant Table Manager",
            category=IntegrationCategory.RESERVATION,
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
                    key="reservation_duration_minutes",
                    label="Reservation Duration (Minutes)",
                    type=FieldType.INTEGER,
                    required=True,
                    default_value=90,
                    description="Standard dining slot duration in minutes",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="max_party_size",
                    label="Maximum Automated Party Size",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=10,
                    description="Parties above this size require front-desk confirmation",
                ),
            ],
            required_oauth_scopes=[],
            partner_approval_required=False,
            required_resources=["tables"],
            webhook_events=[],
            test_connection_procedure="Checks local transactional database connectivity and active table inventory",
            known_limitations=[
                "Relies on tables registered in local resource inventory.",
                "Does not automatically sync with external POS or third-party reservation systems.",
            ],
            is_mock=False,
        )

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        duration = config.get("reservation_duration_minutes", 90)
        try:
            dur_int = int(duration)
            if dur_int < 15 or dur_int > 360:
                return ReadinessCheckResult(
                    check_id="config_duration",
                    name="Seating Duration Validation",
                    passed=False,
                    details="Reservation duration must be between 15 and 360 minutes.",
                    severity="warning",
                )
        except (ValueError, TypeError):
            return ReadinessCheckResult(
                check_id="config_duration",
                name="Seating Duration Validation",
                passed=False,
                details="Invalid seating duration format; must be an integer.",
                severity="critical",
            )
        return ReadinessCheckResult(
            check_id="config_duration",
            name="Seating Duration Validation",
            passed=True,
            details=f"Reservation duration set to {duration} minutes",
            severity="warning",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        return ReadinessCheckResult(
            check_id="internal_auth",
            name="Internal System Authentication",
            passed=True,
            details="Built-in database adapter authenticated via internal connection pool.",
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
            name="Database Connection",
            passed=db_ok,
            details="Connected to transactional reservation store" if db_ok else "Database connection is offline",
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
            name="Database Connection",
            passed=db_ok,
            details="Connected to transactional reservation store" if db_ok else "Database connection is offline",
            severity="critical",
        )
        checks.append(conn_check)

        svc = db_service or get_database_service()
        tables = svc.list_resources(self.business_id, resource_type="table", is_active=True)
        has_inventory = len(tables) > 0
        checks.append(
            ReadinessCheckResult(
                check_id="resource_inventory",
                name="Resource Inventory (Tables)",
                passed=has_inventory,
                details=f"Found {len(tables)} active table(s) configured" if has_inventory else "No reservable tables configured for this business",
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

    def discover_resources(self, resource_type: str = "table") -> List[DiscoveredResource]:
        db_service = get_database_service()
        resources = db_service.list_resources(self.business_id, resource_type=resource_type or "table", is_active=True)
        return [
            DiscoveredResource(
                resource_id=r["id"],
                name=r["name"],
                resource_type=r["resource_type"],
                metadata={
                    "capacity": r.get("capacity", 4),
                    "min_party_size": r.get("min_party_size", 1),
                    "max_party_size": r.get("max_party_size", 4),
                    "section": r.get("section", "Main Hall"),
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
                dur = int(self.configuration.get("reservation_duration_minutes", 90))
                end_iso = input_data.get("end_time")
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else (start_dt + timedelta(minutes=dur))
                party_size = int(input_data.get("party_size", 2))

                avail_res = self.check_availability(
                    start_time=start_dt,
                    end_time=end_dt,
                    party_size=party_size,
                    resource_type=input_data.get("resource_type", "table"),
                )
                if avail_res.get("available"):
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=avail_res,
                        safe_message=f"Tables available for a party of {party_size}.",
                        authoritative_source=self.authoritative_source.value,
                    )
                else:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=True,
                        data=avail_res,
                        safe_message=f"No tables currently available for a party of {party_size} at the requested time.",
                        authoritative_source=self.authoritative_source.value,
                    )

            elif operation == CapabilityType.CREATE_BOOKING:
                start_iso = input_data.get("start_time")
                start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if "T" in str(start_iso) else datetime.strptime(str(start_iso), "%Y-%m-%d %H:%M")
                dur = int(self.configuration.get("reservation_duration_minutes", 90))
                end_iso = input_data.get("end_time")
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else (start_dt + timedelta(minutes=dur))
                party_size = int(input_data.get("party_size", 2))

                try:
                    booking = self.create_reservation(
                        customer_name=input_data["customer_name"],
                        customer_phone=input_data["customer_phone"],
                        party_size=party_size,
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
                        safe_message=f"Booking confirmed for {input_data['customer_name']} (Ref: {booking['booking_reference']}).",
                        authoritative_source=self.authoritative_source.value,
                    )
                except ReservationConflictError as rce:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        data={"reason": "table_conflict", "details": str(rce)},
                        safe_message="Selected table is no longer available for this time window.",
                        authoritative_source=self.authoritative_source.value,
                        error=IntegrationError(
                            code="RESERVATION_CONFLICT",
                            category=ErrorCategory.CONFLICT,
                            message=str(rce),
                            safe_user_message="The requested time slot was just booked.",
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
                        safe_message=f"Found booking {booking_id}.",
                        authoritative_source=self.authoritative_source.value,
                    )
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_FAILED,
                    success=False,
                    safe_message=f"No reservation found with ID {booking_id}.",
                    authoritative_source=self.authoritative_source.value,
                    error=IntegrationError(
                        code="BOOKING_NOT_FOUND",
                        category=ErrorCategory.RESOURCE_NOT_FOUND,
                        message=f"Reservation {booking_id} not found",
                        safe_user_message="Reservation not found.",
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
                        safe_message=f"Reservation {booking_id} successfully cancelled.",
                        authoritative_source=self.authoritative_source.value,
                    )
                return CapabilityResult(
                    operation=operation,
                    outcome=ExecutionOutcome.OPERATION_FAILED,
                    success=False,
                    safe_message=f"Unable to cancel reservation {booking_id}.",
                    authoritative_source=self.authoritative_source.value,
                    error=IntegrationError(
                        code="CANCELLATION_FAILED",
                        category=ErrorCategory.RESOURCE_NOT_FOUND,
                        message=f"Reservation {booking_id} does not exist or cannot be cancelled",
                        safe_user_message="Reservation could not be found or cancelled.",
                        is_retryable=False,
                    ),
                )

            raise NotImplementedError(f"Operation {operation} not supported by BuiltinDiningAdapter")

        return self.execute_with_retry(operation, input_data, context, _dispatch)

    # ---------------------------------------------------------------------------
    # Concrete ReservationAdapterInterface implementation
    # ---------------------------------------------------------------------------

    def check_availability(
        self,
        start_time: datetime,
        end_time: datetime,
        party_size: int,
        resource_type: str = "table",
    ) -> Dict[str, Any]:
        """Query available tables from database inventory."""
        db_service = get_database_service()
        available_tables = db_service.find_available_resources(
            business_id=self.business_id,
            start_time=start_time,
            end_time=end_time,
            party_size=party_size,
            resource_type=resource_type,
        )

        return {
            "available": len(available_tables) > 0,
            "party_size": party_size,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "available_resources": available_tables,
            "count": len(available_tables),
            "authoritative_source": self.authoritative_source.value,
        }

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
        """Commit confirmed table reservation to database."""
        db_service = get_database_service()
        booking = db_service.create_reservation_atomic(
            business_id=self.business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            party_size=party_size,
            start_time=start_time,
            end_time=end_time,
            resource_type="table",
            special_requests=special_requests,
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "status": "confirmed",
            "booking_reference": booking["id"],
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
    ) -> bool:
        """Cancel reservation in database."""
        db_service = get_database_service()
        return db_service.cancel_reservation(
            business_id=self.business_id,
            reservation_id=reservation_id,
            customer_phone=customer_phone,
        )
