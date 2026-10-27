"""
Built-in Booking and Resource Management Integration Adapter.
Provides authoritative first-class inventory, capacity, and scheduling management
for restaurants, hotels, healthcare clinics, and service businesses.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta, time, date
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import uuid
import zoneinfo

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
from backend.database.repositories.reservation_repo import (
    ReservationConflictError,
    CancellationPolicyViolation,
)
import backend.database.service as db_service_mod

logger = logging.getLogger(__name__)


def get_database_service():
    """Retrieve database service instance."""
    return db_service_mod.get_database_service()


# ============================================================================
# Domain-Specific Resource Configuration Models & Validation
# ============================================================================

@dataclass
class DiningTableConfig:
    """Configurable restaurant table resource."""
    name: str
    seating_area: str = "Main Dining Room"
    min_party_size: int = 1
    max_party_size: int = 4
    capacity: int = 4
    is_combinable: bool = False
    turnover_buffer_minutes: int = 15

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Table name cannot be empty.")
        if self.min_party_size < 1:
            raise ValueError(f"min_party_size must be at least 1 (got {self.min_party_size}).")
        if self.max_party_size < self.min_party_size:
            raise ValueError(
                f"max_party_size ({self.max_party_size}) cannot be less than min_party_size ({self.min_party_size})."
            )
        if self.capacity < self.max_party_size:
            raise ValueError(
                f"Table capacity ({self.capacity}) cannot be less than max_party_size ({self.max_party_size})."
            )


@dataclass
class HotelRoomConfig:
    """Configurable hotel room inventory resource."""
    room_number: str
    room_type: str = "standard"  # standard, deluxe, suite, penthouse
    bed_type: str = "king"  # king, queen, double_twin
    floor: int = 1
    max_occupancy: int = 2
    base_nightly_rate_minor: int = 0
    amenities: List[str] = field(default_factory=list)
    housekeeping_buffer_minutes: int = 120

    def validate(self) -> None:
        if not self.room_number or not self.room_number.strip():
            raise ValueError("Room number cannot be empty.")
        valid_room_types = {"standard", "deluxe", "suite", "penthouse", "accessible"}
        if self.room_type.lower() not in valid_room_types:
            raise ValueError(
                f"Invalid room_type '{self.room_type}'. Must be one of {sorted(valid_room_types)}."
            )
        if self.max_occupancy < 1:
            raise ValueError(f"max_occupancy must be at least 1 (got {self.max_occupancy}).")


@dataclass
class ClinicRoomConfig:
    """Configurable healthcare consultation or exam room resource."""
    name: str
    room_number: str
    specialties: List[str] = field(default_factory=lambda: ["general_practice"])
    sanitization_buffer_minutes: int = 10

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Clinic room name cannot be empty.")
        if not self.room_number or not self.room_number.strip():
            raise ValueError("Room number cannot be empty.")
        if self.sanitization_buffer_minutes < 0:
            raise ValueError("Sanitization buffer cannot be negative.")


@dataclass
class PractitionerConfig:
    """Healthcare practitioner resource."""
    name: str
    license_number: str
    specialties: List[str] = field(default_factory=list)
    slot_duration_minutes: int = 30

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Practitioner name cannot be empty.")
        if not self.license_number or not self.license_number.strip():
            raise ValueError("License number cannot be empty.")
        if self.slot_duration_minutes < 5:
            raise ValueError("Slot duration must be at least 5 minutes.")


@dataclass
class ServiceStaffConfig:
    """Service staff resource for salons, spas, and professional services."""
    staff_name: str
    services_offered: List[str] = field(default_factory=list)
    shift_start: str = "09:00"
    shift_end: str = "17:00"
    buffer_after_minutes: int = 15

    def validate(self) -> None:
        if not self.staff_name or not self.staff_name.strip():
            raise ValueError("Staff name cannot be empty.")
        if self.buffer_after_minutes < 0:
            raise ValueError("Buffer minutes cannot be negative.")


@dataclass
class ServiceItemConfig:
    """Service catalog item with duration and pricing."""
    name: str
    duration_minutes: int = 45
    price_minor: int = 0

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Service name cannot be empty.")
        if self.duration_minutes < 5:
            raise ValueError("Service duration must be at least 5 minutes.")
        if self.price_minor < 0:
            raise ValueError("Service price cannot be negative.")


# ============================================================================
# Main Built-in Booking Adapter Implementation
# ============================================================================

class BuiltinBookingAdapter(ReservationAdapterInterface):
    """
    First-class Built-in Booking and Resource Management Adapter.
    Provides authoritative inventory, capacity, and scheduling management for:
    - Restaurants (tables, seating sections, dining duration, turn buffers).
    - Hotels (rooms, room types, bed configurations, check-in turnover).
    - Healthcare Clinics (practitioners, rooms, slots, sanitization buffers).
    - Services (staff members, service catalog, durations, shift breaks).
    """

    def __init__(
        self,
        business_id: str = "",
        tool_id: str = "manage_bookings",
        option_id: str = "builtin_booking",
        configuration: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        cfg = configuration or kwargs.get("config") or {}
        creds = credentials or {}
        super().__init__(
            business_id=business_id,
            tool_id=tool_id,
            option_id=option_id,
            configuration=cfg,
            credentials=creds,
        )

    @property
    def authoritative_source(self) -> AuthoritativeSource:
        """The authoritative source is strictly the internal transactional database."""
        return AuthoritativeSource.BUILTIN_DATABASE

    def get_manifest(self) -> ProviderManifest:
        """Declarative manifest advertising provider capabilities and configuration."""
        return ProviderManifest(
            provider_id="builtin_booking",
            display_name="Built-in Booking & Resource Management",
            category=IntegrationCategory.RESERVATION,
            supported_capabilities=[
                CapabilityType.CHECK_AVAILABILITY,
                CapabilityType.CREATE_BOOKING,
                CapabilityType.GET_BOOKING,
                CapabilityType.RESCHEDULE_BOOKING,
                CapabilityType.CANCEL_BOOKING,
            ],
            auth_method=AuthMethod.INTERNAL,
            authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
            required_setup_fields=[
                SetupField(
                    key="business_type",
                    label="Business Type",
                    type=FieldType.STRING,
                    required=True,
                    default_value="restaurant",
                    description="Industry model: restaurant, hotel, clinic, or service",
                ),
                SetupField(
                    key="timezone",
                    label="Business Timezone",
                    type=FieldType.STRING,
                    required=True,
                    default_value="UTC",
                    description="IANA timezone identifier (e.g. America/New_York, Europe/London, UTC)",
                ),
            ],
            optional_setup_fields=[
                SetupField(
                    key="opening_time",
                    label="Daily Opening Time",
                    type=FieldType.STRING,
                    required=False,
                    default_value="09:00",
                    description="Opening time in HH:MM format",
                ),
                SetupField(
                    key="closing_time",
                    label="Daily Closing Time",
                    type=FieldType.STRING,
                    required=False,
                    default_value="22:00",
                    description="Closing time in HH:MM format",
                ),
                SetupField(
                    key="operating_days",
                    label="Operating Days",
                    type=FieldType.STRING,
                    required=False,
                    default_value="[0, 1, 2, 3, 4, 5, 6]",
                    description="Days open: 0=Monday through 6=Sunday",
                ),
                SetupField(
                    key="slot_duration_minutes",
                    label="Default Booking Duration (Minutes)",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=60,
                    description="Standard slot or reservation length in minutes",
                ),
                SetupField(
                    key="turnover_buffer_minutes",
                    label="Turnover Buffer (Minutes)",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=15,
                    description="Buffer required between back-to-back bookings (e.g. cleaning, sanitization)",
                ),
                SetupField(
                    key="min_lead_time_minutes",
                    label="Minimum Lead Time (Minutes)",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=0,
                    description="Minimum advance notice required before a booking start time",
                ),
                SetupField(
                    key="max_booking_window_days",
                    label="Maximum Booking Window (Days)",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=90,
                    description="How far in advance customers can make bookings",
                ),
                SetupField(
                    key="cancellation_deadline_hours",
                    label="Cancellation Deadline (Hours)",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=24,
                    description="Hours before booking when cancellation is free or allowed",
                ),
                SetupField(
                    key="strict_cancellation",
                    label="Strict Cancellation Policy",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=False,
                    description="If true, cancellations attempted past the deadline are rejected",
                ),
                SetupField(
                    key="hold_duration_minutes",
                    label="Temporary Hold Expiration (Minutes)",
                    type=FieldType.INTEGER,
                    required=False,
                    default_value=15,
                    description="Minutes temporary holds remain reserved before expiring",
                ),
                SetupField(
                    key="allow_waitlist",
                    label="Enable Waitlist",
                    type=FieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                    description="Allow customers to join waitlist when slots are fully booked",
                ),
            ],
            required_resources=["resources"],
            webhook_events=[],
            test_connection_procedure="Verifies transactional database connectivity and active tenant inventory",
            known_limitations=[
                "Operates directly on the platform database inventory.",
                "External calendar sync requires secondary sync adapter if desired.",
            ],
            is_mock=False,
        )

    # ---------------------------------------------------------------------------
    # Configuration and Connection Validation
    # ---------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> ReadinessCheckResult:
        """Validate business type, timezone, operating hours, and booking constraints."""
        b_type = config.get("business_type", "restaurant").lower()
        valid_types = {"restaurant", "hotel", "clinic", "service", "custom"}
        if b_type not in valid_types:
            return ReadinessCheckResult(
                check_id="config_business_type",
                name="Business Type Validation",
                passed=False,
                details=f"Invalid business type '{b_type}'. Must be one of {sorted(valid_types)}.",
                severity="critical",
            )

        # Timezone validation
        tz_name = config.get("timezone", "UTC")
        try:
            zoneinfo.ZoneInfo(tz_name)
        except Exception:
            return ReadinessCheckResult(
                check_id="config_timezone",
                name="Timezone Validation",
                passed=False,
                details=f"Invalid IANA timezone identifier: '{tz_name}'.",
                severity="critical",
            )

        # Hours format validation
        for field_name in ("opening_time", "closing_time"):
            time_str = config.get(field_name)
            if time_str:
                try:
                    parts = str(time_str).split(":")
                    h, m = int(parts[0]), int(parts[1])
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        raise ValueError()
                except Exception:
                    return ReadinessCheckResult(
                        check_id=f"config_{field_name}",
                        name=f"{field_name.replace('_', ' ').title()} Validation",
                        passed=False,
                        details=f"{field_name} must be a valid 24-hour time string in HH:MM format.",
                        severity="critical",
                    )

        # Durations & buffers
        for dur_key in ("slot_duration_minutes", "turnover_buffer_minutes", "min_lead_time_minutes"):
            val = config.get(dur_key)
            if val is not None:
                try:
                    ival = int(val)
                    if ival < 0:
                        raise ValueError()
                except Exception:
                    return ReadinessCheckResult(
                        check_id=f"config_{dur_key}",
                        name=f"{dur_key} Validation",
                        passed=False,
                        details=f"{dur_key} must be a non-negative integer.",
                        severity="critical",
                    )

        return ReadinessCheckResult(
            check_id="config_valid",
            name="Booking Rules & Configuration Validation",
            passed=True,
            details=f"Configuration valid for business type '{b_type}' in timezone '{tz_name}'.",
            severity="critical",
        )

    def connect(self, credentials: Dict[str, Any]) -> ReadinessCheckResult:
        """Built-in adapter uses local transactional database. Verifies DB connectivity."""
        conn_res = check_database_connection()
        db_ok = bool(conn_res.get("connected", False)) if isinstance(conn_res, dict) else bool(conn_res)
        return ReadinessCheckResult(
            check_id="builtin_database_connection",
            name="Database Connection",
            passed=db_ok,
            details="Transactional database connected and ready" if db_ok else "Database connection failure",
            severity="critical",
        )

    def test_connection(self) -> ReadinessCheckResult:
        """Probe local database and verify tenant has registered reservable resources."""
        conn_res = check_database_connection()
        db_ok = bool(conn_res.get("connected", False)) if isinstance(conn_res, dict) else bool(conn_res)
        if not db_ok:
            return ReadinessCheckResult(
                check_id="builtin_test_probe",
                name="Authoritative Inventory Probe",
                passed=False,
                details="Database connection unavailable.",
                severity="critical",
            )

        db_service = get_database_service()
        resources = db_service.get_resources(self.business_id, active_only=True)
        count = len(resources)
        return ReadinessCheckResult(
            check_id="builtin_test_probe",
            name="Authoritative Inventory Probe",
            passed=True,
            details=f"Database operational. Tenant has {count} active reservable resource(s).",
            severity="critical",
        )

    def assess_readiness(self, db_service: Any = None) -> ReadinessReport:
        """Run all mandatory readiness checks for built-in booking engine."""
        checks: List[ReadinessCheckResult] = []
        svc = db_service or get_database_service()

        # 1. DB connection check
        conn_res = check_database_connection()
        db_ok = bool(conn_res.get("connected", False)) if isinstance(conn_res, dict) else bool(conn_res)
        checks.append(
            ReadinessCheckResult(
                check_id="db_connection",
                name="Database Connection",
                passed=db_ok,
                details="Connected to transactional reservation store" if db_ok else "Database connection is offline",
                severity="critical",
            )
        )

        # 2. Config validation
        checks.append(self.validate_configuration(self.configuration))

        # 3. Reservable resources inventory check
        try:
            resources = svc.get_resources(self.business_id, active_only=True)
            has_resources = len(resources) > 0
        except Exception:
            resources = []
            has_resources = False

        checks.append(
            ReadinessCheckResult(
                check_id="resource_inventory",
                name="Authoritative Resource Inventory",
                passed=has_resources,
                details=f"Found {len(resources)} active reservable resource(s) configured" if has_resources else "No reservable resources configured for this business",
                severity="critical",
            )
        )

        all_critical_passed = all(c.passed for c in checks if c.severity == "critical")
        status = CapabilityStatus.READY if all_critical_passed else (CapabilityStatus.NEEDS_INPUT if not has_resources else CapabilityStatus.FAILED)
        missing_reqs = [c.name for c in checks if not c.passed]

        return ReadinessReport(
            is_ready=all_critical_passed,
            status=status,
            checks=checks,
            missing_requirements=missing_reqs,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def discover_resources(self, resource_type: str = "") -> List[DiscoveredResource]:
        """Query and list authoritative reservable resources configured for this tenant."""
        db_service = get_database_service()
        r_type = resource_type if resource_type else None
        res_list = db_service.get_resources(self.business_id, resource_type=r_type, active_only=True)

        discovered: List[DiscoveredResource] = []
        for r in res_list:
            discovered.append(
                DiscoveredResource(
                    resource_id=r["id"],
                    name=r["name"],
                    resource_type=r.get("resource_type", "resource"),
                    is_default=False,
                    metadata={
                        "capacity": r.get("capacity"),
                        "min_party_size": r.get("min_party_size"),
                        "max_party_size": r.get("max_party_size"),
                        "section": r.get("section"),
                        "extra": r.get("metadata", {}),
                    },
                )
            )
        return discovered

    def get_supported_capabilities(self) -> List[CapabilityType]:
        """Return supported booking lifecycle operations."""
        return [
            CapabilityType.CHECK_AVAILABILITY,
            CapabilityType.CREATE_BOOKING,
            CapabilityType.GET_BOOKING,
            CapabilityType.RESCHEDULE_BOOKING,
            CapabilityType.CANCEL_BOOKING,
        ]

    # ---------------------------------------------------------------------------
    # Timezone, Daylight-Saving Transitions, and Operating Rules
    # ---------------------------------------------------------------------------

    def get_timezone(self) -> zoneinfo.ZoneInfo:
        """Resolve business timezone object."""
        tz_name = self.configuration.get("timezone", "UTC")
        try:
            return zoneinfo.ZoneInfo(tz_name)
        except Exception:
            return zoneinfo.ZoneInfo("UTC")

    def parse_to_utc(
        self,
        dt_val: Union[datetime, str],
        source_tz: Optional[zoneinfo.ZoneInfo] = None,
    ) -> datetime:
        """
        Parse datetime string or naive/aware datetime object into UTC-aware datetime.
        Guarantees all database storage and conflict checking use timezone-aware UTC.
        """
        if isinstance(dt_val, str):
            clean_str = dt_val.replace("Z", "+00:00")
            if "T" in clean_str:
                dt_obj = datetime.fromisoformat(clean_str)
            else:
                dt_obj = datetime.strptime(clean_str, "%Y-%m-%d %H:%M")
        else:
            dt_obj = dt_val

        if dt_obj.tzinfo is None:
            tz = source_tz or self.get_timezone()
            dt_obj = dt_obj.replace(tzinfo=tz)

        return dt_obj.astimezone(timezone.utc)

    def handle_dst_transitions(
        self,
        local_wall_clock: datetime,
        tz_name: Optional[str] = None,
    ) -> Tuple[datetime, Dict[str, Any]]:
        """
        Define clear rules for daylight-saving transitions:
        1. Ambiguous time during 'fall back' (e.g. 01:30 AM occurs twice):
           Default to fold=0 (earlier occurrence / daylight time) and log resolution.
        2. Nonexistent time during 'spring forward' (e.g. 02:30 AM gap when 02:00 -> 03:00):
           Detect the gap and shift forward to the post-transition wall clock time (e.g. 03:00 AM).
        Returns localized UTC datetime and transition audit metadata.
        """
        tz = zoneinfo.ZoneInfo(tz_name or self.configuration.get("timezone", "UTC"))
        meta: Dict[str, Any] = {}

        # 1. Fall back check (ambiguity / fold)
        # Attempt fold=0 and fold=1 to see if offset differs
        naive = local_wall_clock.replace(tzinfo=None)
        dt_fold0 = naive.replace(tzinfo=tz, fold=0)
        dt_fold1 = naive.replace(tzinfo=tz, fold=1)
        offset0 = dt_fold0.utcoffset()
        offset1 = dt_fold1.utcoffset()

        if offset0 is not None and offset1 is not None and offset0 != offset1:
            if offset0 > offset1:
                # 1. Fall back (ambiguous / overlap):
                # Standard wall clock hour repeats.
                # Rule: default to fold=0 (earlier occurrence / daylight saving time)
                meta["dst_transition"] = "fall_back_overlap"
                meta["resolution"] = "standard_fold_0_selected"
                logger.info("Daylight-saving fall back ambiguity detected at %s. Selected fold=0.", naive)
                return dt_fold0.astimezone(timezone.utc), meta
            else:
                # 2. Spring forward (gap / nonexistent time):
                # Wall clock hour is skipped.
                # Rule: detect gap and shift forward past transition to valid wall-clock time
                gap_delta = offset1 - offset0
                gap_minutes = int(gap_delta.total_seconds() / 60)
                adjusted_naive = naive + gap_delta
                adjusted_dt = adjusted_naive.replace(tzinfo=tz)
                meta["dst_transition"] = "spring_forward_gap"
                meta["gap_minutes"] = gap_minutes
                meta["adjusted_wall_clock"] = adjusted_naive.isoformat()
                logger.warning(
                    "Nonexistent wall-clock time %s in spring forward gap. Shifted to %s (+%d mins).",
                    naive, adjusted_naive, gap_minutes
                )
                return adjusted_dt.astimezone(timezone.utc), meta

        return dt_fold0.astimezone(timezone.utc), meta

    def is_within_operating_rules(
        self,
        start_dt_utc: datetime,
        end_dt_utc: datetime,
        party_size: int = 1,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate booking against opening hours, operating days, lead times,
        booking windows, and capacity constraints.
        """
        tz = self.get_timezone()
        start_local = start_dt_utc.astimezone(tz)
        end_local = end_dt_utc.astimezone(tz)

        # 1. Operating days check (0=Mon, ..., 6=Sun)
        operating_days = self.configuration.get("operating_days", [0, 1, 2, 3, 4, 5, 6])
        if start_local.weekday() not in operating_days:
            day_name = start_local.strftime("%A")
            return False, f"Business is closed on {day_name}s."

        # 2. Operating hours check
        open_str = self.configuration.get("opening_time", "09:00")
        close_str = self.configuration.get("closing_time", "22:00")
        try:
            oh, om = map(int, open_str.split(":"))
            ch, cm = map(int, close_str.split(":"))
            open_time = time(oh, om)
            close_time = time(ch, cm)

            if start_local.time() < open_time or start_local.time() > close_time:
                return (
                    False,
                    f"Requested time ({start_local.strftime('%H:%M')}) is outside operating hours ({open_str} – {close_str}).",
                )
            if end_local.time() > close_time and end_local.date() == start_local.date():
                return (
                    False,
                    f"Booking ends at {end_local.strftime('%H:%M')}, which exceeds closing time ({close_str}).",
                )
        except Exception as exc:
            logger.warning("Could not evaluate operating hours rule: %s", exc)

        # 3. Minimum lead time check
        now_utc = datetime.now(timezone.utc)
        min_lead_minutes = int(self.configuration.get("min_lead_time_minutes", 0))
        if min_lead_minutes > 0:
            lead_seconds = (start_dt_utc - now_utc).total_seconds()
            if lead_seconds < (min_lead_minutes * 60):
                return (
                    False,
                    f"Bookings require at least {min_lead_minutes} minutes advance notice.",
                )

        # 4. Maximum booking window check
        max_window_days = int(self.configuration.get("max_booking_window_days", 90))
        if max_window_days > 0:
            days_ahead = (start_dt_utc - now_utc).days
            if days_ahead > max_window_days:
                return (
                    False,
                    f"Bookings cannot be scheduled more than {max_window_days} days in advance.",
                )

        # 5. Party size automated limit
        max_party = int(self.configuration.get("max_party_size", 50))
        min_party = int(self.configuration.get("min_party_size", 1))
        if party_size < min_party or party_size > max_party:
            return (
                False,
                f"Party size ({party_size}) must be between {min_party} and {max_party}.",
            )

        return True, None

    # ---------------------------------------------------------------------------
    # Authoritative Availability and Capacity Check
    # ---------------------------------------------------------------------------

    def check_availability(
        self,
        start_time: Union[datetime, str],
        end_time: Optional[Union[datetime, str]] = None,
        party_size: int = 1,
        resource_type: Optional[str] = None,
        section: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check availability against authoritative internal inventory and database.
        NEVER infers availability from FAQs, messages, or calendar events.
        """
        start_utc = self.parse_to_utc(start_time)
        r_type = resource_type or self._default_resource_type()

        # Compute end time if omitted
        if end_time is None:
            dur_mins = int(self.configuration.get("slot_duration_minutes", 60))
            end_utc = start_utc + timedelta(minutes=dur_mins)
        else:
            end_utc = self.parse_to_utc(end_time)

        # Validate operating rules
        is_allowed, decline_reason = self.is_within_operating_rules(
            start_dt_utc=start_utc,
            end_dt_utc=end_utc,
            party_size=party_size,
        )
        if not is_allowed:
            return {
                "available": False,
                "reason": decline_reason,
                "party_size": party_size,
                "start_time": start_utc.isoformat(),
                "end_time": end_utc.isoformat(),
                "available_resources": [],
                "count": 0,
                "authoritative_source": self.authoritative_source.value,
            }

        buffer_mins = int(self.configuration.get("turnover_buffer_minutes", 15))
        db_service = get_database_service()
        available_resources = db_service.find_available_resources(
            business_id=self.business_id,
            start_time=start_utc,
            end_time=end_utc,
            party_size=party_size,
            resource_type=r_type,
            section=section,
            buffer_minutes=buffer_mins,
        )

        # If a specific location is filtered, refine by metadata location
        if location:
            available_resources = [
                r for r in available_resources
                if (r.get("metadata", {}).get("location") == location)
            ]

        is_avail = len(available_resources) > 0
        return {
            "available": is_avail,
            "party_size": party_size,
            "start_time": start_utc.isoformat(),
            "end_time": end_utc.isoformat(),
            "available_resources": available_resources,
            "count": len(available_resources),
            "resource_type": r_type,
            "section": section,
            "reason": None if is_avail else "all_resources_booked",
            "authoritative_source": self.authoritative_source.value,
        }

    # ---------------------------------------------------------------------------
    # Authoritative Booking Lifecycle Interface
    # ---------------------------------------------------------------------------

    def create_reservation(
        self,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: Union[datetime, str],
        end_time: Optional[Union[datetime, str]] = None,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        section: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a confirmed reservation or appointment.
        Prevents overlapping reservations and overselling under concurrent requests
        via database transactional conflict checking and rollback.
        """
        start_utc = self.parse_to_utc(start_time)
        r_type = resource_type or self._default_resource_type()

        if end_time is None:
            dur_mins = int(self.configuration.get("slot_duration_minutes", 60))
            end_utc = start_utc + timedelta(minutes=dur_mins)
        else:
            end_utc = self.parse_to_utc(end_time)

        # Operating rules check
        is_allowed, decline_reason = self.is_within_operating_rules(
            start_dt_utc=start_utc,
            end_dt_utc=end_utc,
            party_size=party_size,
        )
        if not is_allowed:
            raise ReservationConflictError(decline_reason or "Booking violates business operating rules.")

        buffer_mins = int(self.configuration.get("turnover_buffer_minutes", 15))
        db_service = get_database_service()

        booking = db_service.create_reservation_atomic(
            business_id=self.business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            party_size=party_size,
            start_time=start_utc,
            end_time=end_utc,
            resource_id=resource_id,
            resource_type=r_type,
            section=section,
            special_requests=special_requests,
            idempotency_key=idempotency_key,
            status="confirmed",
            metadata=metadata,
            buffer_minutes=buffer_mins,
        )

        return {
            "booking_id": booking["id"],
            "booking_reference": booking["id"],
            "status": booking["status"],
            "resource_id": booking.get("resource_id"),
            "resource_name": booking.get("resource_name"),
            "customer_name": booking["customer_name"],
            "customer_phone": booking["customer_phone"],
            "party_size": booking["party_size"],
            "start_time": booking["start_time"],
            "end_time": booking["end_time"],
            "special_requests": booking.get("special_requests"),
            "authoritative_source": self.authoritative_source.value,
        }

    def create_hold(
        self,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        start_time: Union[datetime, str],
        end_time: Optional[Union[datetime, str]] = None,
        hold_minutes: Optional[int] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        section: Optional[str] = None,
        special_requests: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Atomically place a temporary hold on a resource with an expiration timestamp.
        Inventory is reserved until expiration.
        """
        start_utc = self.parse_to_utc(start_time)
        r_type = resource_type or self._default_resource_type()

        if end_time is None:
            dur_mins = int(self.configuration.get("slot_duration_minutes", 60))
            end_utc = start_utc + timedelta(minutes=dur_mins)
        else:
            end_utc = self.parse_to_utc(end_time)

        h_mins = hold_minutes or int(self.configuration.get("hold_duration_minutes", 15))
        buffer_mins = int(self.configuration.get("turnover_buffer_minutes", 15))

        db_service = get_database_service()
        hold = db_service.create_hold_atomic(
            business_id=self.business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            party_size=party_size,
            start_time=start_utc,
            end_time=end_utc,
            hold_minutes=h_mins,
            resource_id=resource_id,
            resource_type=r_type,
            section=section,
            special_requests=special_requests,
            idempotency_key=idempotency_key,
            metadata=metadata,
            buffer_minutes=buffer_mins,
        )
        return hold

    def confirm_hold(
        self,
        reservation_id: str,
        customer_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert an active hold into a confirmed booking.
        Rejects if the hold timestamp has expired.
        """
        db_service = get_database_service()
        return db_service.confirm_hold_atomic(
            business_id=self.business_id,
            reservation_id=reservation_id,
            customer_phone=customer_phone,
        )

    def get_reservation(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve booking record with strict tenant isolation."""
        db_service = get_database_service()
        return db_service.get_reservation(self.business_id, reservation_id)

    def reschedule_reservation(
        self,
        reservation_id: str,
        new_start_time: Union[datetime, str],
        new_end_time: Optional[Union[datetime, str]] = None,
        new_resource_id: Optional[str] = None,
        customer_phone: Optional[str] = None,
        party_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Atomically reschedule a reservation with audit history and conflict prevention.
        Excludes the reservation's current slot during availability check.
        """
        new_start_utc = self.parse_to_utc(new_start_time)
        if new_end_time is None:
            dur_mins = int(self.configuration.get("slot_duration_minutes", 60))
            new_end_utc = new_start_utc + timedelta(minutes=dur_mins)
        else:
            new_end_utc = self.parse_to_utc(new_end_time)

        # Operating rules check
        is_allowed, decline_reason = self.is_within_operating_rules(
            start_dt_utc=new_start_utc,
            end_dt_utc=new_end_utc,
            party_size=party_size or 1,
        )
        if not is_allowed:
            raise ReservationConflictError(decline_reason or "Rescheduled slot violates operating rules.")

        buffer_mins = int(self.configuration.get("turnover_buffer_minutes", 15))
        db_service = get_database_service()

        rescheduled = db_service.reschedule_reservation_atomic(
            business_id=self.business_id,
            reservation_id=reservation_id,
            new_start_time=new_start_utc,
            new_end_time=new_end_utc,
            new_resource_id=new_resource_id,
            customer_phone=customer_phone,
            party_size=party_size,
            buffer_minutes=buffer_mins,
        )
        return rescheduled

    def cancel_reservation(
        self,
        reservation_id: str,
        customer_phone: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Cancel a reservation, enforcing business cancellation deadline policy.
        """
        deadline_hours = self.configuration.get("cancellation_deadline_hours")
        strict_policy = bool(self.configuration.get("strict_cancellation", False))

        db_service = get_database_service()
        return db_service.cancel_reservation(
            business_id=self.business_id,
            reservation_id=reservation_id,
            customer_phone=customer_phone,
            cancellation_deadline_hours=deadline_hours,
            strict_cancellation=strict_policy,
            reason=reason,
        )

    # ---------------------------------------------------------------------------
    # Waiting List Support
    # ---------------------------------------------------------------------------

    def add_to_waitlist(
        self,
        customer_name: str,
        customer_phone: str,
        requested_time: Union[datetime, str],
        party_size: int = 1,
        resource_type: Optional[str] = None,
        section: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add customer to the waiting list when resources are fully booked.
        Maintains customer reference and queue order.
        """
        if not self.configuration.get("allow_waitlist", True):
            raise ValueError("Waitlists are disabled for this business.")

        req_utc = self.parse_to_utc(requested_time)
        r_type = resource_type or self._default_resource_type()

        db_service = get_database_service()
        return db_service.add_to_waitlist(
            business_id=self.business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            requested_time=req_utc,
            party_size=party_size,
            resource_type=r_type,
            section=section,
            notes=notes,
        )

    def get_waitlist(self, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch active waitlist entries for this tenant."""
        db_service = get_database_service()
        return db_service.get_waitlist(self.business_id, resource_type=resource_type)

    # ---------------------------------------------------------------------------
    # Domain-Specific Resource Registration Helpers
    # ---------------------------------------------------------------------------

    def register_dining_table(
        self,
        name: str,
        seating_area: str = "Main Dining Room",
        min_party_size: int = 1,
        max_party_size: int = 4,
        capacity: int = 4,
        is_combinable: bool = False,
        turnover_buffer_minutes: int = 15,
    ) -> Dict[str, Any]:
        """Register a dining table with section and capacity constraints."""
        cfg = DiningTableConfig(
            name=name,
            seating_area=seating_area,
            min_party_size=min_party_size,
            max_party_size=max_party_size,
            capacity=capacity,
            is_combinable=is_combinable,
            turnover_buffer_minutes=turnover_buffer_minutes,
        )
        cfg.validate()

        db_service = get_database_service()
        return db_service.create_resource(
            business_id=self.business_id,
            name=name,
            capacity=capacity,
            min_party_size=min_party_size,
            max_party_size=max_party_size,
            resource_type="table",
            section=seating_area,
            metadata_json={
                "is_combinable": is_combinable,
                "turnover_buffer_minutes": turnover_buffer_minutes,
            },
        )

    def register_hotel_room(
        self,
        room_number: str,
        room_type: str = "standard",
        bed_type: str = "king",
        floor: int = 1,
        max_occupancy: int = 2,
        base_nightly_rate_minor: int = 0,
        amenities: Optional[List[str]] = None,
        housekeeping_buffer_minutes: int = 120,
    ) -> Dict[str, Any]:
        """Register a hotel room inventory resource."""
        cfg = HotelRoomConfig(
            room_number=room_number,
            room_type=room_type,
            bed_type=bed_type,
            floor=floor,
            max_occupancy=max_occupancy,
            base_nightly_rate_minor=base_nightly_rate_minor,
            amenities=amenities or [],
            housekeeping_buffer_minutes=housekeeping_buffer_minutes,
        )
        cfg.validate()

        name = f"Room {room_number} ({room_type.title()})"
        db_service = get_database_service()
        return db_service.create_resource(
            business_id=self.business_id,
            name=name,
            capacity=max_occupancy,
            min_party_size=1,
            max_party_size=max_occupancy,
            resource_type="room",
            section=f"Floor {floor}",
            metadata_json={
                "room_number": room_number,
                "room_type": room_type,
                "bed_type": bed_type,
                "floor": floor,
                "base_nightly_rate_minor": base_nightly_rate_minor,
                "amenities": amenities or [],
                "housekeeping_buffer_minutes": housekeeping_buffer_minutes,
            },
        )

    def register_clinic_room(
        self,
        name: str,
        room_number: str,
        specialties: Optional[List[str]] = None,
        sanitization_buffer_minutes: int = 10,
    ) -> Dict[str, Any]:
        """Register a clinical consultation room."""
        cfg = ClinicRoomConfig(
            name=name,
            room_number=room_number,
            specialties=specialties or ["general_practice"],
            sanitization_buffer_minutes=sanitization_buffer_minutes,
        )
        cfg.validate()

        db_service = get_database_service()
        return db_service.create_resource(
            business_id=self.business_id,
            name=name,
            capacity=2,
            min_party_size=1,
            max_party_size=2,
            resource_type="clinic_room",
            section="Clinical Suite",
            metadata_json={
                "room_number": room_number,
                "specialties": specialties or ["general_practice"],
                "sanitization_buffer_minutes": sanitization_buffer_minutes,
            },
        )

    def register_practitioner(
        self,
        name: str,
        license_number: str,
        specialties: Optional[List[str]] = None,
        slot_duration_minutes: int = 30,
    ) -> Dict[str, Any]:
        """Register a clinical practitioner / doctor resource."""
        cfg = PractitionerConfig(
            name=name,
            license_number=license_number,
            specialties=specialties or [],
            slot_duration_minutes=slot_duration_minutes,
        )
        cfg.validate()

        db_service = get_database_service()
        return db_service.create_resource(
            business_id=self.business_id,
            name=name,
            capacity=1,
            min_party_size=1,
            max_party_size=1,
            resource_type="practitioner",
            section="Staff",
            metadata_json={
                "license_number": license_number,
                "specialties": specialties or [],
                "slot_duration_minutes": slot_duration_minutes,
            },
        )

    def register_service_staff(
        self,
        staff_name: str,
        services_offered: Optional[List[str]] = None,
        shift_start: str = "09:00",
        shift_end: str = "17:00",
        buffer_after_minutes: int = 15,
    ) -> Dict[str, Any]:
        """Register service staff member (e.g. hair stylist, massage therapist)."""
        cfg = ServiceStaffConfig(
            staff_name=staff_name,
            services_offered=services_offered or [],
            shift_start=shift_start,
            shift_end=shift_end,
            buffer_after_minutes=buffer_after_minutes,
        )
        cfg.validate()

        db_service = get_database_service()
        return db_service.create_resource(
            business_id=self.business_id,
            name=staff_name,
            capacity=1,
            min_party_size=1,
            max_party_size=1,
            resource_type="service_staff",
            section="Service Team",
            metadata_json={
                "services_offered": services_offered or [],
                "shift_start": shift_start,
                "shift_end": shift_end,
                "buffer_after_minutes": buffer_after_minutes,
            },
        )

    # ---------------------------------------------------------------------------
    # Setup Wizard and Safe Demo Seeding
    # ---------------------------------------------------------------------------

    def get_setup_wizard_steps(self, business_type: str = "restaurant") -> List[Dict[str, Any]]:
        """
        Return dynamic setup wizard steps tailored strictly to the business type.
        Owners configure relevant resources, hours, and booking rules.
        """
        b_type = business_type.lower()
        base_step_general = {
            "step_id": "general_hours",
            "title": "Operating Hours & Timezone",
            "fields": [
                {"key": "timezone", "label": "Timezone", "type": "string", "default": "UTC"},
                {"key": "opening_time", "label": "Opening Time", "type": "string", "default": "09:00"},
                {"key": "closing_time", "label": "Closing Time", "type": "string", "default": "22:00"},
            ],
        }
        base_step_policies = {
            "step_id": "policies",
            "title": "Booking & Cancellation Policies",
            "fields": [
                {"key": "cancellation_deadline_hours", "label": "Cancellation Deadline (Hours)", "type": "integer", "default": 24},
                {"key": "strict_cancellation", "label": "Strict Cancellation", "type": "boolean", "default": False},
                {"key": "min_lead_time_minutes", "label": "Min Lead Time (Minutes)", "type": "integer", "default": 60},
                {"key": "max_booking_window_days", "label": "Max Booking Window (Days)", "type": "integer", "default": 90},
            ],
        }

        if b_type == "restaurant":
            return [
                base_step_general,
                {
                    "step_id": "dining_rules",
                    "title": "Dining & Table Configuration",
                    "fields": [
                        {"key": "slot_duration_minutes", "label": "Dining Duration (Minutes)", "type": "integer", "default": 90},
                        {"key": "turnover_buffer_minutes", "label": "Table Turn Buffer (Minutes)", "type": "integer", "default": 15},
                        {"key": "max_party_size", "label": "Max Automated Party Size", "type": "integer", "default": 10},
                    ],
                },
                base_step_policies,
            ]
        elif b_type == "hotel":
            return [
                base_step_general,
                {
                    "step_id": "hotel_rules",
                    "title": "Hotel Room & Check-In Rules",
                    "fields": [
                        {"key": "check_in_time", "label": "Check-in Time", "type": "string", "default": "15:00"},
                        {"key": "check_out_time", "label": "Check-out Time", "type": "string", "default": "11:00"},
                        {"key": "turnover_buffer_minutes", "label": "Housekeeping Turn Buffer (Minutes)", "type": "integer", "default": 120},
                    ],
                },
                base_step_policies,
            ]
        elif b_type == "clinic":
            return [
                base_step_general,
                {
                    "step_id": "clinical_rules",
                    "title": "Clinical Consultation Rules",
                    "fields": [
                        {"key": "slot_duration_minutes", "label": "Consultation Duration (Minutes)", "type": "integer", "default": 30},
                        {"key": "turnover_buffer_minutes", "label": "Sanitization Buffer (Minutes)", "type": "integer", "default": 10},
                    ],
                },
                base_step_policies,
            ]
        elif b_type == "service":
            return [
                base_step_general,
                {
                    "step_id": "service_rules",
                    "title": "Service Staff & Appointment Rules",
                    "fields": [
                        {"key": "slot_duration_minutes", "label": "Default Service Duration (Minutes)", "type": "integer", "default": 45},
                        {"key": "turnover_buffer_minutes", "label": "Staff Buffer / Break (Minutes)", "type": "integer", "default": 15},
                    ],
                },
                base_step_policies,
            ]
        return [base_step_general, base_step_policies]

    def seed_demo_data(
        self,
        business_type: str = "restaurant",
        is_demo: bool = False,
        environment: str = "production",
    ) -> Dict[str, Any]:
        """
        Safely seed realistic demo inventory strictly when explicitly in a demo environment.
        Raises SecurityError if invoked in production or when is_demo=False.
        """
        if not is_demo or environment.lower() != "demo":
            raise PermissionError(
                "Demo data can only be seeded in an explicitly designated demo environment "
                "(is_demo=True and environment='demo'). Never mutate production inventory."
            )

        b_type = business_type.lower()
        seeded_resources: List[Dict[str, Any]] = []

        if b_type == "restaurant":
            t1 = self.register_dining_table("Table 1 (Patio)", seating_area="Patio", min_party_size=1, max_party_size=2, capacity=2)
            t2 = self.register_dining_table("Table 2 (Patio)", seating_area="Patio", min_party_size=2, max_party_size=4, capacity=4)
            t3 = self.register_dining_table("Table 3 (Main Hall)", seating_area="Main Hall", min_party_size=2, max_party_size=4, capacity=4)
            t4 = self.register_dining_table("Table 4 (Main Hall)", seating_area="Main Hall", min_party_size=4, max_party_size=6, capacity=6)
            t5 = self.register_dining_table("Private Dining Room", seating_area="Private Dining", min_party_size=8, max_party_size=12, capacity=12)
            seeded_resources.extend([t1, t2, t3, t4, t5])

        elif b_type == "hotel":
            r1 = self.register_hotel_room("101", room_type="standard", bed_type="king", floor=1, max_occupancy=2)
            r2 = self.register_hotel_room("102", room_type="standard", bed_type="double_twin", floor=1, max_occupancy=2)
            r3 = self.register_hotel_room("201", room_type="deluxe", bed_type="king", floor=2, max_occupancy=3, amenities=["ocean_view", "balcony"])
            r4 = self.register_hotel_room("301", room_type="suite", bed_type="king", floor=3, max_occupancy=4, amenities=["penthouse_terrace", "jacuzzi"])
            seeded_resources.extend([r1, r2, r3, r4])

        elif b_type == "clinic":
            c1 = self.register_clinic_room("Consultation Room 1", room_number="101", specialties=["general_practice"])
            c2 = self.register_clinic_room("Dental Suite A", room_number="102", specialties=["dentistry"])
            p1 = self.register_practitioner("Dr. Sarah Jenkins", license_number="MED-98124", specialties=["general_practice"], slot_duration_minutes=30)
            p2 = self.register_practitioner("Dr. David Wong", license_number="DEN-44021", specialties=["dentistry"], slot_duration_minutes=45)
            seeded_resources.extend([c1, c2, p1, p2])

        elif b_type == "service":
            s1 = self.register_service_staff("Alice Stylist", services_offered=["Haircut", "Color"], shift_start="09:00", shift_end="17:00")
            s2 = self.register_service_staff("Bob Massage Therapist", services_offered=["Deep Tissue", "Swedish Massage"], shift_start="10:00", shift_end="18:00")
            seeded_resources.extend([s1, s2])

        return {
            "status": "seeded",
            "business_type": b_type,
            "environment": environment,
            "resources_created": len(seeded_resources),
            "resource_ids": [r["id"] for r in seeded_resources],
        }

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
        Execute validated capability operations with transaction guarantees,
        concurrency rollback, and truthful outcomes.
        """
        def _dispatch() -> CapabilityResult:
            if operation == CapabilityType.CHECK_AVAILABILITY:
                start_raw = input_data.get("start_time")
                end_raw = input_data.get("end_time")
                party_size = int(input_data.get("party_size", 1))
                res_type = input_data.get("resource_type") or self._default_resource_type()
                section = input_data.get("section")
                location = input_data.get("location")

                avail_res = self.check_availability(
                    start_time=start_raw,
                    end_time=end_raw,
                    party_size=party_size,
                    resource_type=res_type,
                    section=section,
                    location=location,
                )

                if avail_res.get("available"):
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=avail_res,
                        safe_message=(
                            f"Slots are available for party size {party_size} on "
                            f"{avail_res['start_time']}."
                        ),
                        authoritative_source=self.authoritative_source.value,
                    )
                else:
                    reason = avail_res.get("reason", "No slots available")
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=True,
                        data=avail_res,
                        safe_message=f"No availability: {reason}",
                        authoritative_source=self.authoritative_source.value,
                    )

            elif operation == CapabilityType.CREATE_BOOKING:
                party_size = int(input_data.get("party_size", 1))
                start_raw = input_data.get("start_time")
                end_raw = input_data.get("end_time")
                cust_name = input_data.get("customer_name", "").strip()
                cust_phone = input_data.get("customer_phone", "").strip()
                res_id = input_data.get("resource_id")
                res_type = input_data.get("resource_type") or self._default_resource_type()
                section = input_data.get("section")
                special_requests = input_data.get("special_requests")
                meta = input_data.get("metadata", {})

                try:
                    booking = self.create_reservation(
                        customer_name=cust_name,
                        customer_phone=cust_phone,
                        party_size=party_size,
                        start_time=start_raw,
                        end_time=end_raw,
                        special_requests=special_requests,
                        idempotency_key=context.idempotency_key,
                        resource_id=res_id,
                        resource_type=res_type,
                        section=section,
                        metadata=meta,
                    )
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=booking,
                        safe_message=f"Booking confirmed for {cust_name} (Ref: {booking['booking_reference']}).",
                        authoritative_source=self.authoritative_source.value,
                    )
                except ReservationConflictError as rce:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        data={"reason": "resource_conflict", "details": str(rce)},
                        safe_message="Selected resource or time window is no longer available.",
                        authoritative_source=self.authoritative_source.value,
                        error=IntegrationError(
                            code="RESERVATION_CONFLICT",
                            category=ErrorCategory.CONFLICT,
                            message=str(rce),
                            safe_user_message="The requested time slot is no longer available.",
                            is_retryable=False,
                        ),
                    )

            elif operation == CapabilityType.GET_BOOKING:
                booking_id = input_data.get("booking_id", "")
                booking = self.get_reservation(booking_id)
                if booking:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=booking,
                        safe_message=f"Booking {booking_id} retrieved successfully.",
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

            elif operation == CapabilityType.RESCHEDULE_BOOKING:
                booking_id = input_data.get("booking_id", "")
                new_start = input_data.get("new_start_time")
                new_end = input_data.get("new_end_time")
                phone = input_data.get("customer_phone")
                res_id = input_data.get("resource_id")
                party_size = input_data.get("party_size")

                try:
                    rescheduled = self.reschedule_reservation(
                        reservation_id=booking_id,
                        new_start_time=new_start,
                        new_end_time=new_end,
                        new_resource_id=res_id,
                        customer_phone=phone,
                        party_size=party_size,
                    )
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_COMPLETED,
                        success=True,
                        data=rescheduled,
                        safe_message=f"Booking {booking_id} successfully rescheduled.",
                        authoritative_source=self.authoritative_source.value,
                    )
                except ReservationConflictError as rce:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        data={"reason": "reschedule_conflict", "details": str(rce)},
                        safe_message="Cannot reschedule: requested new time slot is unavailable.",
                        authoritative_source=self.authoritative_source.value,
                        error=IntegrationError(
                            code="RESCHEDULE_CONFLICT",
                            category=ErrorCategory.CONFLICT,
                            message=str(rce),
                            safe_user_message="Requested new time slot is unavailable.",
                            is_retryable=False,
                        ),
                    )

            elif operation == CapabilityType.CANCEL_BOOKING:
                booking_id = input_data.get("booking_id", "")
                phone = input_data.get("customer_phone")
                reason = input_data.get("reason")

                try:
                    cancelled = self.cancel_reservation(
                        reservation_id=booking_id,
                        customer_phone=phone,
                        reason=reason,
                    )
                    if cancelled:
                        return CapabilityResult(
                            operation=operation,
                            outcome=ExecutionOutcome.OPERATION_COMPLETED,
                            success=True,
                            data={"booking_id": booking_id, "status": "cancelled", "reason": reason},
                            safe_message=f"Booking {booking_id} successfully cancelled.",
                            authoritative_source=self.authoritative_source.value,
                        )
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.OPERATION_FAILED,
                        success=False,
                        safe_message=f"Unable to cancel booking {booking_id}. Record not found.",
                        authoritative_source=self.authoritative_source.value,
                        error=IntegrationError(
                            code="CANCELLATION_FAILED",
                            category=ErrorCategory.RESOURCE_NOT_FOUND,
                            message=f"Reservation {booking_id} does not exist or customer phone verification failed.",
                            safe_user_message="Reservation could not be found or cancelled.",
                            is_retryable=False,
                        ),
                    )
                except CancellationPolicyViolation as cpv:
                    return CapabilityResult(
                        operation=operation,
                        outcome=ExecutionOutcome.BUSINESS_REJECTION,
                        success=False,
                        data={"reason": "cancellation_policy_violation", "details": str(cpv)},
                        safe_message=str(cpv),
                        authoritative_source=self.authoritative_source.value,
                        error=IntegrationError(
                            code="CANCELLATION_DEADLINE_EXPIRED",
                            category=ErrorCategory.POLICY_VIOLATION,
                            message=str(cpv),
                            safe_user_message="Cancellation deadline has passed.",
                            is_retryable=False,
                        ),
                    )

            raise NotImplementedError(f"Operation {operation} not supported by BuiltinBookingAdapter")

        return self.execute_with_retry(operation, input_data, context, _dispatch)

    # ---------------------------------------------------------------------------
    # Internal Helpers
    # ---------------------------------------------------------------------------

    def _default_resource_type(self) -> str:
        """Derive default resource type from configured business type."""
        b_type = self.configuration.get("business_type", "restaurant").lower()
        mapping = {
            "restaurant": "table",
            "hotel": "room",
            "clinic": "clinic_room",
            "service": "service_staff",
        }
        return mapping.get(b_type, "table")
