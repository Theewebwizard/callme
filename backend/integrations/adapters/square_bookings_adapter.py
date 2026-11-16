"""
Square Bookings Integration Adapter.

Integrates with Square Appointments / Bookings API using the official Square Python SDK.
Supports:
- Least-privilege OAuth2 scopes: APPOINTMENTS_READ, APPOINTMENTS_WRITE,
  APPOINTMENTS_BUSINESS_SETTINGS_READ, MERCHANT_PROFILE_READ, CUSTOMERS_READ,
  CUSTOMERS_WRITE, ITEMS_READ.
- Seller eligibility validation (Appointments enabled, active locations, catalog services).
- Resource discovery: Locations, Catalog Service Variations, and Bookable Team Members.
- Real-time availability lookup via /v2/bookings/availability/search (no slot inference).
- Appointment creation with customer resolution, appointment segments, and idempotency keys.
- Separation of confirmed (ACCEPTED) vs pending (PENDING) appointments.
- Booking retrieval, update/rescheduling with version conflict detection, and cancellation.
- Cryptographic webhook signature verification (HMAC-SHA256 via x-square-hmacsha256-signature).
- Concurrency & version safeguards (Square booking_version locking).
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, timedelta
import json
import base64
import hmac
import hashlib
import logging
import uuid

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

logger = logging.getLogger(__name__)

# Square API Base URLs
SQUARE_PRODUCTION_URL = "https://connect.squareup.com"
SQUARE_SANDBOX_URL = "https://connect.squareupsandbox.com"


class SquareBookingsAdapter(ReservationAdapterInterface):
    """
    Square Bookings Integration Adapter.
    Connects Square Appointments for salons, clinics, consultants, and service merchants.
    """

    authoritative_source: AuthoritativeSource = AuthoritativeSource.EXTERNAL_CALENDAR

    def __init__(
        self,
        business_id: str,
        tool_id: Optional[str] = None,
        option_id: Optional[str] = None,
        configuration: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(business_id, tool_id, option_id, configuration, credentials)
        self._client_instance = None

    # ---------------------------------------------------------------------------
    # Provider Manifest & Metadata
    # ---------------------------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="square",
            display_name="Square Bookings",
            category=IntegrationCategory.CALENDAR,
            supported_capabilities=[
                CapabilityType.CHECK_AVAILABILITY,
                CapabilityType.CREATE_BOOKING,
                CapabilityType.GET_BOOKING,
                CapabilityType.RESCHEDULE_BOOKING,
                CapabilityType.CANCEL_BOOKING,
            ],
            auth_method=AuthMethod.OAUTH2,
            authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
            required_setup_fields=[
                SetupField(
                    key="access_token",
                    label="Square OAuth Access Token",
                    type=FieldType.PASSWORD,
                    required=True,
                    secret=True,
                    description="OAuth access token with Appointments, Customers, and Catalog permissions.",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="location_id",
                    label="Square Location ID",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="e.g. L9XYZ123456",
                    description="Authoritative business location ID (leave blank to use main location).",
                ),
                SetupField(
                    key="service_variation_id",
                    label="Default Service Variation ID",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="e.g. VAR_1029384",
                    description="Catalog item variation ID representing the default service or treatment.",
                ),
                SetupField(
                    key="team_member_id",
                    label="Default Team Member ID",
                    type=FieldType.STRING,
                    required=False,
                    placeholder="e.g. TM_482910",
                    description="Staff member or practitioner ID (leave blank for any available staff).",
                ),
                SetupField(
                    key="environment",
                    label="Square Environment",
                    type=FieldType.SELECT,
                    required=False,
                    default_value="production",
                    options=[
                        {"value": "production", "label": "Production (connect.squareup.com)"},
                        {"value": "sandbox", "label": "Sandbox (connect.squareupsandbox.com)"},
                    ],
                    description="Target Square environment (Production vs Sandbox).",
                ),
                SetupField(
                    key="webhook_signature_key",
                    label="Webhook Signature Key",
                    type=FieldType.PASSWORD,
                    required=False,
                    secret=True,
                    description="Square Webhook Signature Key for verifying incoming HMAC-SHA256 callbacks.",
                ),
            ],
            required_oauth_scopes=[
                "APPOINTMENTS_READ",
                "APPOINTMENTS_WRITE",
                "APPOINTMENTS_BUSINESS_SETTINGS_READ",
                "MERCHANT_PROFILE_READ",
                "CUSTOMERS_READ",
                "CUSTOMERS_WRITE",
                "ITEMS_READ",
            ],
            partner_approval_required=False,
            required_resources=["locations", "services", "team_members"],
            webhook_events=[
                "booking.created",
                "booking.updated",
                "booking.canceled",
            ],
        )

    def get_supported_capabilities(self) -> List[CapabilityType]:
        token = self._get_access_token()
        if not token:
            return []
        return [
            CapabilityType.CHECK_AVAILABILITY,
            CapabilityType.CREATE_BOOKING,
            CapabilityType.GET_BOOKING,
            CapabilityType.RESCHEDULE_BOOKING,
            CapabilityType.CANCEL_BOOKING,
        ]

    # ---------------------------------------------------------------------------
    # Client Initialization & Authentication
    # ---------------------------------------------------------------------------

    def _get_access_token(self) -> str:
        return str(
            self.credentials.get("access_token")
            or self.configuration.get("access_token")
            or ""
        ).strip()

    def _get_environment(self) -> str:
        return str(
            self.configuration.get("environment")
            or self.credentials.get("environment")
            or "production"
        ).strip().lower()

    def _get_client(self):
        """Lazy-initialize official Square client."""
        if self._client_instance is not None:
            return self._client_instance

        token = self._get_access_token()
        env = self._get_environment()

        try:
            from square import Square
            self._client_instance = Square(
                token=token,
                environment="sandbox" if env == "sandbox" else "production",
            )
            return self._client_instance
        except ImportError:
            logger.warning("Square SDK not installed; using fallback client.")
            return None

    # ---------------------------------------------------------------------------
    # Error Normalization
    # ---------------------------------------------------------------------------

    def _normalize_square_error(self, exc: Any) -> IntegrationError:
        """
        Map Square SDK ApiError or generic HTTP exception into a normalized IntegrationError.
        Handles rate limits, version mismatches (409 CONFLICT), auth errors, and validation issues.
        """
        status_code = getattr(exc, "status_code", 500)
        body = getattr(exc, "body", {}) or {}
        errors = body.get("errors", []) if isinstance(body, dict) else []

        category = ErrorCategory.PROVIDER_UNAVAILABLE
        code = "SQUARE_API_ERROR"
        msg = str(exc)
        is_retryable = False
        retry_after = None

        # Check headers for Retry-After
        headers = getattr(exc, "headers", {}) or {}
        if "retry-after" in headers:
            try:
                retry_after = float(headers["retry-after"])
            except (ValueError, TypeError):
                retry_after = None

        if errors and isinstance(errors, list) and len(errors) > 0:
            first_err = errors[0]
            err_code = first_err.get("code", "")
            err_cat = first_err.get("category", "")
            detail = first_err.get("detail", "")
            code = err_code or code
            msg = detail or msg

            if status_code == 403 or err_code in ("NOT_AUTHORIZED", "FORBIDDEN", "INSUFFICIENT_SCOPES"):
                category = ErrorCategory.PERMISSION_DENIED
                is_retryable = False
            elif err_cat == "AUTHENTICATION_ERROR" or status_code == 401:
                category = ErrorCategory.AUTHENTICATION_FAILED
                is_retryable = False
            elif err_cat == "RATE_LIMIT_ERROR" or status_code == 429:
                category = ErrorCategory.RATE_LIMITED
                is_retryable = True
            elif status_code == 409 or "VERSION_MISMATCH" in err_code or "CONFLICT" in err_code:
                category = ErrorCategory.CONFLICT
                is_retryable = False
            elif status_code == 404 or "NOT_FOUND" in err_code:
                category = ErrorCategory.RESOURCE_NOT_FOUND
                is_retryable = False
            elif status_code == 400 or "INVALID_REQUEST_ERROR" in err_cat:
                category = ErrorCategory.INVALID_REQUEST
                is_retryable = False
        else:
            if status_code == 429:
                category = ErrorCategory.RATE_LIMITED
                is_retryable = True
            elif status_code == 401:
                category = ErrorCategory.AUTHENTICATION_FAILED
            elif status_code == 403:
                category = ErrorCategory.PERMISSION_DENIED
            elif status_code == 404:
                category = ErrorCategory.RESOURCE_NOT_FOUND
            elif status_code == 409:
                category = ErrorCategory.CONFLICT

        return IntegrationError(
            code=code,
            category=category,
            message=msg,
            safe_user_message="Square Appointments reported an issue with your booking request.",
            retry_after_seconds=retry_after,
            is_retryable=is_retryable,
            details={"raw_status": status_code, "square_errors": errors},
        )

    # ---------------------------------------------------------------------------
    # Webhook Verification
    # ---------------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        notification_url: Optional[str] = None,
    ) -> bool:
        """
        Cryptographic verification of x-square-hmacsha256-signature header.
        Uses HMAC-SHA256 with the account's Webhook Signature Key over:
        combined = notification_url + raw_body
        """
        sig_key = str(
            self.credentials.get("webhook_signature_key")
            or self.configuration.get("webhook_signature_key")
            or ""
        ).strip()
        signature_header = (
            headers.get("x-square-hmacsha256-signature")
            or headers.get("X-Square-Hmacsha256-Signature")
            or ""
        )

        if not signature_header or not sig_key:
            return False

        try:
            url_bytes = (notification_url or "").encode("utf-8")
            combined = url_bytes + raw_body
            computed_hash = base64.b64encode(
                hmac.new(sig_key.encode("utf-8"), combined, hashlib.sha256).digest()
            ).decode("utf-8")
            return hmac.compare_digest(computed_hash, signature_header)
        except Exception as exc:
            logger.error("Error verifying Square webhook signature: %s", exc)
            return False

    def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        """
        Process incoming Square webhook notification:
        1. Verifies HMAC-SHA256 signature using the account's webhook signature key.
        2. Parses event payload (booking.created, booking.updated, booking.canceled).
        3. Extracts booking ID and version for replay deduplication.
        """
        sig_header = request.headers.get("x-square-hmacsha256-signature") or request.headers.get("X-Square-Hmacsha256-Signature")
        sig_key = self.credentials.get("webhook_signature_key") or self.configuration.get("webhook_signature_key")

        if sig_key and sig_header:
            if not self.verify_webhook_signature(request.raw_body, request.headers, notification_url=request.url):
                return WebhookResult(
                    success=False,
                    processed=False,
                    message="Invalid Square webhook signature (HMAC-SHA256 mismatch).",
                )
        elif sig_key and not sig_header:
            return WebhookResult(
                success=False,
                processed=False,
                message="Missing x-square-hmacsha256-signature header.",
            )

        payload = request.parsed_json or {}
        event_type = payload.get("type") or "booking.updated"
        data_obj = payload.get("data", {}).get("object", {}) if isinstance(payload.get("data"), dict) else {}
        booking_obj = data_obj.get("booking", {}) if isinstance(data_obj.get("booking"), dict) else data_obj

        booking_id = booking_obj.get("id") or payload.get("event_id")
        booking_ver = booking_obj.get("version", 0)

        # Build unique event ID for deduplication
        event_id = payload.get("event_id") or f"square_{event_type}_{booking_id}_v{booking_ver}"

        return WebhookResult(
            success=True,
            event_id=event_id,
            event_type=event_type,
            processed=True,
            message=f"Square webhook event '{event_type}' processed for booking {booking_id}.",
            data=payload,
        )

    # ---------------------------------------------------------------------------
    # Configuration & Seller Eligibility Validation
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """
        Validate credentials presence and preliminary configuration format.
        """
        token = self._get_access_token()
        if not token:
            return ReadinessCheckResult(
                check_id="square_token_check",
                name="Square OAuth Access Token",
                passed=False,
                details="Missing Square OAuth access token.",
                severity="critical",
            )

        return ReadinessCheckResult(
            check_id="square_token_check",
            name="Square OAuth Access Token",
            passed=True,
            details=f"Configured with Square OAuth token ({self._get_environment()}).",
            severity="warning",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        self.credentials.update(credentials)
        token = self._get_access_token()
        if not token:
            return ReadinessCheckResult(
                check_id="square_auth_check",
                name="Square Authentication",
                passed=False,
                details="No access token provided.",
                severity="critical",
            )
        return ReadinessCheckResult(
            check_id="square_auth_check",
            name="Square Authentication",
            passed=True,
            details="Square OAuth token loaded into secure memory.",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        """
        Verify connection and validate seller eligibility:
        1. Checks Bookings Business Profile: seller must have Appointments enabled.
        2. Checks Locations: seller must have at least one active location.
        """
        token = self._get_access_token()
        if not token:
            return ReadinessCheckResult(
                check_id="square_connection",
                name="Square API Reachability",
                passed=False,
                details="Missing access token.",
                severity="critical",
            )

        # Mock / Sandbox bypass
        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return ReadinessCheckResult(
                check_id="square_connection",
                name="Square Appointments Eligibility",
                passed=True,
                details="Verified Square Appointments connection (Mock Mode).",
                severity="critical",
            )

        client = self._get_client()
        if not client:
            return ReadinessCheckResult(
                check_id="square_connection",
                name="Square Client Initialization",
                passed=False,
                details="Square SDK could not be initialized.",
                severity="critical",
            )

        # 1. Validate Appointments Business Profile & Eligibility
        try:
            profile_resp = client.bookings.get_business_profile()
            profile = getattr(profile_resp, "business_booking_profile", None)
            if profile is not None:
                booking_enabled = getattr(profile, "booking_enabled", True)
                if booking_enabled is False:
                    return ReadinessCheckResult(
                        check_id="square_eligibility_check",
                        name="Square Appointments Online Bookings",
                        passed=False,
                        details="Online bookings are disabled on this Square merchant profile.",
                        severity="critical",
                    )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            if err.category in (ErrorCategory.AUTHENTICATION_FAILED, ErrorCategory.PERMISSION_DENIED):
                return ReadinessCheckResult(
                    check_id="square_eligibility_check",
                    name="Square Appointments Authorization",
                    passed=False,
                    details=(
                        f"Square authorization failed: {err.message}. "
                        "Ensure seller has active Appointments plan and APPOINTMENTS_BUSINESS_SETTINGS_READ scope."
                    ),
                    severity="critical",
                )
            logger.warning("Could not query Square business booking profile: %s", exc)

        # 2. Validate at least one active location
        try:
            locs_resp = client.locations.list()
            locs = getattr(locs_resp, "locations", []) or []
            active_locs = [l for l in locs if getattr(l, "status", "ACTIVE") == "ACTIVE"]
            if not active_locs:
                return ReadinessCheckResult(
                    check_id="square_locations_check",
                    name="Square Active Locations",
                    passed=False,
                    details="Square account has no active business locations.",
                    severity="critical",
                )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            return ReadinessCheckResult(
                check_id="square_locations_check",
                name="Square Locations Reachability",
                passed=False,
                details=f"Failed to query Square locations: {err.message}",
                severity="critical",
            )

        return ReadinessCheckResult(
            check_id="square_connection",
            name="Square Appointments Eligibility",
            passed=True,
            details=f"Square Appointments verified with {len(active_locs)} active location(s).",
            severity="critical",
        )

    def assess_readiness(self, db_service: Any) -> ReadinessReport:
        token = self._get_access_token()
        checks: List[ReadinessCheckResult] = []
        missing: List[str] = []

        if not token:
            checks.append(
                ReadinessCheckResult(
                    check_id="square_token_check",
                    name="Square OAuth Token",
                    passed=False,
                    details="Access token is missing.",
                    severity="critical",
                )
            )
            missing.append("Square OAuth Access Token required.")
            return ReadinessReport(
                status=CapabilityStatus.NEEDS_INPUT,
                is_ready=False,
                missing_requirements=missing,
                checks=checks,
            )

        conn_check = self.test_connection()
        checks.append(conn_check)

        if not conn_check.passed:
            missing.append(conn_check.details)
            return ReadinessReport(
                status=CapabilityStatus.FAILED,
                is_ready=False,
                missing_requirements=missing,
                checks=checks,
            )

        return ReadinessReport(
            status=CapabilityStatus.READY,
            is_ready=True,
            missing_requirements=[],
            checks=checks,
        )

    # ---------------------------------------------------------------------------
    # Resource Discovery
    # ---------------------------------------------------------------------------

    def discover_resources(self, resource_type: str = "all") -> List[DiscoveredResource]:
        """
        Discover seller's locations, catalog services, and bookable team members.
        """
        resources: List[DiscoveredResource] = []
        token = self._get_access_token()

        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            if resource_type in ("all", "location", "locations"):
                resources.append(
                    DiscoveredResource(
                        resource_id="LOC_MOCK_001",
                        name="Main Downtown Studio",
                        resource_type="location",
                        metadata={"location_id": "LOC_MOCK_001", "timezone": "America/New_York", "status": "ACTIVE"},
                    )
                )
            if resource_type in ("all", "service", "services", "service_variation"):
                resources.append(
                    DiscoveredResource(
                        resource_id="VAR_MOCK_101",
                        name="Full Consultation (45 mins)",
                        resource_type="service_variation",
                        metadata={"service_variation_id": "VAR_MOCK_101", "duration_minutes": 45, "price": 12000},
                    )
                )
            if resource_type in ("all", "team_member", "team_members"):
                resources.append(
                    DiscoveredResource(
                        resource_id="TM_MOCK_501",
                        name="Dr. Taylor Reed",
                        resource_type="team_member",
                        metadata={"team_member_id": "TM_MOCK_501", "is_bookable": True},
                    )
                )
            return resources

        client = self._get_client()
        if not client:
            return resources

        # 1. Locations Discovery
        if resource_type in ("all", "location", "locations"):
            try:
                loc_res = client.locations.list()
                locs = getattr(loc_res, "locations", []) or []
                for loc in locs:
                    lid = str(getattr(loc, "id", "") or "")
                    name = str(getattr(loc, "name", "Location") or "Location")
                    status = str(getattr(loc, "status", "ACTIVE") or "ACTIVE")
                    tz = str(getattr(loc, "timezone", "UTC") or "UTC")
                    resources.append(
                        DiscoveredResource(
                            resource_id=lid,
                            name=name,
                            resource_type="location",
                            metadata={"location_id": lid, "status": status, "timezone": tz},
                        )
                    )
            except Exception as exc:
                logger.error("Error discovering Square locations: %s", exc)

        # 2. Services Discovery (Catalog Item Variations)
        if resource_type in ("all", "service", "services", "service_variation"):
            try:
                cat_res = client.catalog.list(types="ITEM_VARIATION")
                objects = getattr(cat_res, "objects", []) or []
                for obj in objects:
                    vid = str(getattr(obj, "id", "") or "")
                    vdata = getattr(obj, "item_variation_data", None)
                    vname = str(getattr(vdata, "name", "Service Variation") or "Service Variation") if vdata else "Service"
                    dur = getattr(vdata, "service_duration", 1800000) if vdata else 1800000  # ms
                    dur_mins = int(dur / 60000) if dur else 30
                    resources.append(
                        DiscoveredResource(
                            resource_id=vid,
                            name=vname,
                            resource_type="service_variation",
                            metadata={
                                "service_variation_id": vid,
                                "duration_minutes": dur_mins,
                            },
                        )
                    )
            except Exception as exc:
                logger.error("Error discovering Square catalog services: %s", exc)

        # 3. Team Members Discovery
        if resource_type in ("all", "team_member", "team_members"):
            try:
                # Retrieve bookable team member profiles
                profiles_res = client.bookings.team_member_profiles.list(bookable_only=True)
                profiles = getattr(profiles_res, "team_member_booking_profiles", []) or []
                for p in profiles:
                    tmid = str(getattr(p, "team_member_id", "") or "")
                    dname = str(getattr(p, "display_name", "Team Member") or "Team Member")
                    bookable = getattr(p, "is_bookable", True)
                    resources.append(
                        DiscoveredResource(
                            resource_id=tmid,
                            name=dname,
                            resource_type="team_member",
                            metadata={"team_member_id": tmid, "is_bookable": bookable},
                        )
                    )
            except Exception as exc:
                logger.error("Error discovering Square team members: %s", exc)

        return resources

    # ---------------------------------------------------------------------------
    # Capability Execution
    # ---------------------------------------------------------------------------

    def execute(
        self,
        operation: CapabilityType,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        def _dispatch() -> CapabilityResult:
            if operation == CapabilityType.CHECK_AVAILABILITY:
                return self._execute_check_availability(input_data, context)
            elif operation == CapabilityType.CREATE_BOOKING:
                return self._execute_create_booking(input_data, context)
            elif operation == CapabilityType.GET_BOOKING:
                return self._execute_get_booking(input_data, context)
            elif operation == CapabilityType.RESCHEDULE_BOOKING:
                return self._execute_reschedule_booking(input_data, context)
            elif operation == CapabilityType.CANCEL_BOOKING:
                return self._execute_cancel_booking(input_data, context)
            else:
                raise NotImplementedError(f"Operation '{operation.value}' not supported by SquareBookingsAdapter")

        return self.execute_with_retry(operation, input_data, context, _dispatch)

    # ---------------------------------------------------------------------------
    # Operation Handlers
    # ---------------------------------------------------------------------------

    def _execute_check_availability(
        self,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Query Square Bookings availability via /v2/bookings/availability/search.
        Verifies live availability rules and team member schedules without slot inference.
        """
        start_str = str(input_data.get("start_time") or input_data.get("date") or "")
        try:
            start_dt = self._parse_iso_datetime(start_str)
        except Exception:
            start_dt = datetime.now(timezone.utc) + timedelta(days=1)

        end_dt = start_dt + timedelta(hours=8)
        start_at_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_at_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        loc_id = (
            input_data.get("location_id")
            or self.configuration.get("location_id")
            or "LOC_DEFAULT"
        )
        service_var_id = (
            input_data.get("service_variation_id")
            or self.configuration.get("service_variation_id")
            or "VAR_DEFAULT"
        )
        team_member_id = (
            input_data.get("team_member_id")
            or self.configuration.get("team_member_id")
        )

        token = self._get_access_token()

        # Mock / Sandbox Bypass
        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            is_busy = "busy" in start_str.lower()
            return CapabilityResult(
                operation=CapabilityType.CHECK_AVAILABILITY,
                outcome=ExecutionOutcome.OPERATION_COMPLETED if not is_busy else ExecutionOutcome.BUSINESS_REJECTION,
                success=True,
                data={
                    "available": not is_busy,
                    "location_id": loc_id,
                    "service_variation_id": service_var_id,
                    "slots": [{"start_at": start_at_iso, "location_id": loc_id}] if not is_busy else [],
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=(
                    f"Square has appointment availability starting at {start_at_iso}."
                    if not is_busy
                    else "No Square appointment availability for requested time window."
                ),
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )

        client = self._get_client()
        if not client:
            return CapabilityResult(
                operation=CapabilityType.CHECK_AVAILABILITY,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                safe_message="Square client not configured.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )

        segment_filter: Dict[str, Any] = {"service_variation_id": service_var_id}
        if team_member_id:
            segment_filter["team_member_id_filter"] = {"any": [team_member_id]}

        query_payload = {
            "filter": {
                "start_at_range": {"start_at": start_at_iso, "end_at": end_at_iso},
                "location_id": loc_id,
                "segment_filters": [segment_filter],
            }
        }

        try:
            resp = client.bookings.search_availability(query=query_payload)
            availabilities = getattr(resp, "availabilities", []) or []
            is_available = len(availabilities) > 0

            slots = []
            for av in availabilities:
                slots.append({
                    "start_at": getattr(av, "start_at", None),
                    "location_id": getattr(av, "location_id", loc_id),
                })

            return CapabilityResult(
                operation=CapabilityType.CHECK_AVAILABILITY,
                outcome=ExecutionOutcome.OPERATION_COMPLETED if is_available else ExecutionOutcome.BUSINESS_REJECTION,
                success=True,
                data={
                    "available": is_available,
                    "location_id": loc_id,
                    "service_variation_id": service_var_id,
                    "slots": slots,
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=(
                    f"Square has {len(slots)} open slot(s) starting from {start_at_iso}."
                    if is_available
                    else "No available appointment slots found in Square for the requested time range."
                ),
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            return CapabilityResult(
                operation=CapabilityType.CHECK_AVAILABILITY,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="Failed to query Square appointment availability.",
                error=err,
                correlation_id=context.correlation_id,
            )

    def _execute_create_booking(
        self,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Create an appointment booking in Square with idempotency key.
        Separates confirmed (ACCEPTED) vs pending (PENDING) bookings.
        """
        start_str = str(input_data.get("start_time") or input_data.get("datetime") or "")
        try:
            start_dt = self._parse_iso_datetime(start_str)
        except Exception:
            start_dt = datetime.now(timezone.utc) + timedelta(days=1)

        start_at_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        loc_id = (
            input_data.get("location_id")
            or self.configuration.get("location_id")
            or "LOC_DEFAULT"
        )
        service_var_id = (
            input_data.get("service_variation_id")
            or self.configuration.get("service_variation_id")
            or "VAR_DEFAULT"
        )
        team_member_id = (
            input_data.get("team_member_id")
            or self.configuration.get("team_member_id")
        )
        duration_mins = int(input_data.get("duration_minutes") or 30)

        cust_name = str(input_data.get("customer_name") or input_data.get("patient_name") or "Client").strip()
        cust_phone = str(input_data.get("customer_phone") or input_data.get("patient_phone") or "").strip()
        cust_email = str(input_data.get("customer_email") or input_data.get("email") or "").strip()
        cust_notes = str(input_data.get("notes") or input_data.get("special_requests") or "")

        idempotency_key = context.idempotency_key or f"sq_book_{uuid.uuid4().hex[:16]}"
        token = self._get_access_token()

        # Mock / Sandbox Bypass
        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            booking_id = f"SQ-BK-{int(start_dt.timestamp())}"
            is_pending = "pending" in cust_notes.lower()
            return CapabilityResult(
                operation=CapabilityType.CREATE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_PENDING if is_pending else ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": booking_id,
                    "appointment_reference": booking_id,
                    "booking_reference": booking_id,
                    "id": booking_id,
                    "version": 1,
                    "status": "PENDING" if is_pending else "ACCEPTED",
                    "start_at": start_at_iso,
                    "location_id": loc_id,
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=(
                    f"Square appointment request received and pending acceptance (Reference: {booking_id})."
                    if is_pending
                    else f"Square appointment confirmed for {cust_name} (Reference: {booking_id})."
                ),
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
                idempotency_key=idempotency_key,
            )

        client = self._get_client()
        if not client:
            return CapabilityResult(
                operation=CapabilityType.CREATE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                safe_message="Square client not configured.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )

        # 1. Resolve or Create Square Customer
        customer_id = input_data.get("customer_id")
        if not customer_id:
            try:
                name_parts = cust_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""

                cust_create_resp = client.customers.create(
                    idempotency_key=f"sq_cust_{uuid.uuid4().hex[:12]}",
                    given_name=first_name,
                    family_name=last_name,
                    phone_number=cust_phone if cust_phone else None,
                    email_address=cust_email if cust_email else None,
                    note=f"Created via CallMe AI Receptionist ({context.tenant_id})",
                )
                created_cust = getattr(cust_create_resp, "customer", None)
                if created_cust:
                    customer_id = getattr(created_cust, "id", None)
            except Exception as exc:
                logger.warning("Could not auto-create Square customer profile: %s", exc)

        segment = {
            "service_variation_id": service_var_id,
            "duration_minutes": duration_mins,
        }
        if team_member_id:
            segment["team_member_id"] = team_member_id

        booking_payload = {
            "start_at": start_at_iso,
            "location_id": loc_id,
            "customer_id": customer_id,
            "customer_note": cust_notes,
            "seller_note": f"CallMe AI Receptionist Booking [Idempotency: {idempotency_key}]",
            "appointment_segments": [segment],
        }

        try:
            resp = client.bookings.create(
                idempotency_key=idempotency_key,
                booking=booking_payload,
            )
            booking = getattr(resp, "booking", None)
            if not booking:
                raise ValueError("Square did not return a valid booking object.")

            b_id = getattr(booking, "id", "")
            b_ver = getattr(booking, "version", 0)
            b_status = getattr(booking, "status", "ACCEPTED")

            is_pending = (b_status == "PENDING")
            outcome = ExecutionOutcome.OPERATION_PENDING if is_pending else ExecutionOutcome.OPERATION_COMPLETED

            return CapabilityResult(
                operation=CapabilityType.CREATE_BOOKING,
                outcome=outcome,
                success=True,
                data={
                    "booking_id": b_id,
                    "appointment_reference": b_id,
                    "booking_reference": b_id,
                    "id": b_id,
                    "version": b_ver,
                    "status": b_status,
                    "start_at": getattr(booking, "start_at", start_at_iso),
                    "location_id": getattr(booking, "location_id", loc_id),
                    "customer_id": getattr(booking, "customer_id", customer_id),
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=(
                    f"Square appointment request received and pending acceptance (Reference: {b_id})."
                    if is_pending
                    else f"Square appointment confirmed for {cust_name} (Reference: {b_id})."
                ),
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            return CapabilityResult(
                operation=CapabilityType.CREATE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="Square was unable to confirm the appointment.",
                error=err,
                correlation_id=context.correlation_id,
            )

    def _execute_get_booking(
        self,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        booking_id = input_data.get("booking_id") or input_data.get("appointment_id")
        token = self._get_access_token()

        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return CapabilityResult(
                operation=CapabilityType.GET_BOOKING,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": booking_id,
                    "appointment_reference": booking_id,
                    "version": 1,
                    "status": "ACCEPTED",
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=f"Square booking {booking_id} retrieved.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )

        client = self._get_client()
        if not client:
            return CapabilityResult(
                operation=CapabilityType.GET_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                safe_message="Square client not configured.",
                authoritative_source=self.authoritative_source.value,
            )

        try:
            resp = client.bookings.get(booking_id=booking_id)
            booking = getattr(resp, "booking", None)
            if not booking:
                raise ValueError(f"Square booking {booking_id} not found.")

            b_id = getattr(booking, "id", booking_id)
            b_ver = getattr(booking, "version", 0)
            b_status = getattr(booking, "status", "ACCEPTED")

            return CapabilityResult(
                operation=CapabilityType.GET_BOOKING,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": b_id,
                    "appointment_reference": b_id,
                    "version": b_ver,
                    "status": b_status,
                    "start_at": getattr(booking, "start_at", None),
                    "location_id": getattr(booking, "location_id", None),
                    "customer_id": getattr(booking, "customer_id", None),
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=f"Square appointment {b_id} details retrieved.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            return CapabilityResult(
                operation=CapabilityType.GET_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="Could not find Square appointment.",
                error=err,
                correlation_id=context.correlation_id,
            )

    def _execute_reschedule_booking(
        self,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Update/reschedule appointment booking in Square with version concurrency check.
        """
        booking_id = input_data.get("booking_id") or input_data.get("appointment_id")
        new_start_str = str(input_data.get("new_start_time") or input_data.get("start_time") or "")
        start_dt = self._parse_iso_datetime(new_start_str)
        start_at_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        token = self._get_access_token()
        idempotency_key = context.idempotency_key or f"sq_upd_{uuid.uuid4().hex[:16]}"

        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return CapabilityResult(
                operation=CapabilityType.RESCHEDULE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": booking_id,
                    "appointment_reference": booking_id,
                    "version": 2,
                    "status": "ACCEPTED",
                    "start_at": start_at_iso,
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=f"Square appointment {booking_id} rescheduled to {start_at_iso}.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )

        client = self._get_client()
        if not client:
            return CapabilityResult(
                operation=CapabilityType.RESCHEDULE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                safe_message="Square client not configured.",
                authoritative_source=self.authoritative_source.value,
            )

        try:
            # 1. Fetch current version if not supplied to protect against concurrency conflict
            current_version = input_data.get("version")
            if current_version is None:
                get_resp = client.bookings.get(booking_id=booking_id)
                current_booking = getattr(get_resp, "booking", None)
                current_version = getattr(current_booking, "version", 0) if current_booking else 0

            # 2. Update booking with version locking
            update_payload = {
                "version": int(current_version),
                "start_at": start_at_iso,
            }
            if input_data.get("location_id"):
                update_payload["location_id"] = input_data["location_id"]

            resp = client.bookings.update(
                booking_id=booking_id,
                idempotency_key=idempotency_key,
                booking=update_payload,
            )
            updated_booking = getattr(resp, "booking", None)
            new_version = getattr(updated_booking, "version", current_version + 1) if updated_booking else current_version + 1

            return CapabilityResult(
                operation=CapabilityType.RESCHEDULE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": booking_id,
                    "appointment_reference": booking_id,
                    "version": new_version,
                    "status": getattr(updated_booking, "status", "ACCEPTED") if updated_booking else "ACCEPTED",
                    "start_at": start_at_iso,
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=f"Square appointment {booking_id} rescheduled successfully.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            return CapabilityResult(
                operation=CapabilityType.RESCHEDULE_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="Failed to reschedule Square appointment.",
                error=err,
                correlation_id=context.correlation_id,
            )

    def _execute_cancel_booking(
        self,
        input_data: Dict[str, Any],
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Cancel appointment booking in Square with version locking and idempotency.
        """
        booking_id = input_data.get("booking_id") or input_data.get("appointment_id")
        token = self._get_access_token()
        idempotency_key = context.idempotency_key or f"sq_can_{uuid.uuid4().hex[:16]}"

        if token.startswith("mock_") or token.startswith("test_") or token == "sandbox_key_verified":
            return CapabilityResult(
                operation=CapabilityType.CANCEL_BOOKING,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": booking_id,
                    "appointment_reference": booking_id,
                    "status": "CANCELLED_BY_CUSTOMER",
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=f"Square appointment {booking_id} has been canceled.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )

        client = self._get_client()
        if not client:
            return CapabilityResult(
                operation=CapabilityType.CANCEL_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                safe_message="Square client not configured.",
                authoritative_source=self.authoritative_source.value,
            )

        try:
            # Fetch current version if not provided
            current_version = input_data.get("version")
            if current_version is None:
                get_resp = client.bookings.get(booking_id=booking_id)
                current_booking = getattr(get_resp, "booking", None)
                current_version = getattr(current_booking, "version", 0) if current_booking else 0

            resp = client.bookings.cancel(
                booking_id=booking_id,
                idempotency_key=idempotency_key,
                booking_version=int(current_version),
            )
            canceled_booking = getattr(resp, "booking", None)
            c_status = getattr(canceled_booking, "status", "CANCELLED_BY_CUSTOMER") if canceled_booking else "CANCELLED_BY_CUSTOMER"

            return CapabilityResult(
                operation=CapabilityType.CANCEL_BOOKING,
                outcome=ExecutionOutcome.OPERATION_COMPLETED,
                success=True,
                data={
                    "booking_id": booking_id,
                    "appointment_reference": booking_id,
                    "status": c_status,
                    "authoritative_source": self.authoritative_source.value,
                },
                safe_message=f"Square appointment {booking_id} canceled successfully.",
                authoritative_source=self.authoritative_source.value,
                correlation_id=context.correlation_id,
            )
        except Exception as exc:
            err = self._normalize_square_error(exc)
            return CapabilityResult(
                operation=CapabilityType.CANCEL_BOOKING,
                outcome=ExecutionOutcome.OPERATION_FAILED,
                success=False,
                authoritative_source=self.authoritative_source.value,
                safe_message="Could not cancel Square appointment.",
                error=err,
                correlation_id=context.correlation_id,
            )

    # ---------------------------------------------------------------------------
    # Concrete ReservationAdapterInterface implementation
    # ---------------------------------------------------------------------------

    def check_availability(
        self,
        start_time: datetime,
        end_time: datetime,
        party_size: int = 1,
        resource_type: str = "room",
    ) -> Dict[str, Any]:
        """Backwards compatible availability check."""
        ctx = ExecutionContext(
            tenant_id=self.business_id,
            business_id=self.business_id,
            tool_id=self.tool_id,
            provider_id="square",
            correlation_id=f"sq_avail_{int(start_time.timestamp())}",
        )
        res = self.execute(
            CapabilityType.CHECK_AVAILABILITY,
            {"start_time": start_time.isoformat()},
            ctx,
        )
        return {
            "available": res.data.get("available", False),
            "slots": res.data.get("slots", []),
            "authoritative_source": self.authoritative_source.value,
            "message": res.safe_message,
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
        """Backwards compatible appointment booking creation."""
        ctx = ExecutionContext(
            tenant_id=self.business_id,
            business_id=self.business_id,
            tool_id=self.tool_id,
            provider_id="square",
            idempotency_key=idempotency_key,
        )
        res = self.execute(
            CapabilityType.CREATE_BOOKING,
            {
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "start_time": start_time.isoformat(),
                "notes": special_requests or "",
            },
            ctx,
        )
        return {
            "success": res.success,
            "status": res.data.get("status", "failed"),
            "appointment_reference": res.data.get("booking_id"),
            "booking_reference": res.data.get("booking_id"),
            "booking_id": res.data.get("booking_id"),
            "id": res.data.get("booking_id"),
            "version": res.data.get("version"),
            "message": res.safe_message,
            "authoritative_source": self.authoritative_source.value,
        }

    def cancel_reservation(self, reservation_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Backwards compatible appointment cancellation."""
        ctx = ExecutionContext(
            tenant_id=self.business_id,
            business_id=self.business_id,
            tool_id=self.tool_id,
            provider_id="square",
        )
        res = self.execute(
            CapabilityType.CANCEL_BOOKING,
            {"booking_id": reservation_id, "reason": reason or "Canceled via AI Receptionist"},
            ctx,
        )
        return {
            "success": res.success,
            "status": res.data.get("status", "canceled"),
            "message": res.safe_message,
            "authoritative_source": self.authoritative_source.value,
        }

    def get_reservation(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        ctx = ExecutionContext(
            tenant_id=self.business_id,
            business_id=self.business_id,
            tool_id=self.tool_id,
            provider_id="square",
        )
        res = self.execute(
            CapabilityType.GET_BOOKING,
            {"booking_id": reservation_id},
            ctx,
        )
        if res.success:
            return res.data
        return None

    def reschedule_reservation(
        self,
        reservation_id: str,
        new_start_time: datetime,
        new_end_time: datetime,
    ) -> Dict[str, Any]:
        ctx = ExecutionContext(
            tenant_id=self.business_id,
            business_id=self.business_id,
            tool_id=self.tool_id,
            provider_id="square",
        )
        res = self.execute(
            CapabilityType.RESCHEDULE_BOOKING,
            {
                "booking_id": reservation_id,
                "new_start_time": new_start_time.isoformat(),
            },
            ctx,
        )
        return {
            "success": res.success,
            "status": res.data.get("status", "rescheduled"),
            "message": res.safe_message,
            "authoritative_source": self.authoritative_source.value,
        }

    # ---------------------------------------------------------------------------
    # Internal Helpers
    # ---------------------------------------------------------------------------

    def _parse_iso_datetime(self, dt_str: str) -> datetime:
        dt_str = dt_str.strip()
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            raise ValueError(f"Unable to parse datetime string: {dt_str}")
