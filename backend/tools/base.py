"""
Base models, enums, and execution result schemas for the modular tool registry.
"""

import re
import zoneinfo
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Dict, Any, Optional, Type, Callable, List, Set
import dateutil.parser
from pydantic import BaseModel, ConfigDict, Field


class ToolExecutionMode(str, Enum):
    """Execution mode of the tool handler."""
    MOCK = "mock"
    UNAVAILABLE = "unavailable"
    LIVE = "live"


class ToolCategory(str, Enum):
    """Categorical classification of business receptionist tools."""
    INFORMATION = "Information"
    DINING = "Dining & Hospitality"
    HEALTHCARE = "Healthcare & Services"
    COMMUNICATION = "Communication"
    HOSPITALITY = "Hospitality & Lodging"


class ToolExecutionStatus(str, Enum):
    """
    Status returned by the tool execution boundary.
    Distinguishes system execution outcome from business-level rejection and security blocks.
    """
    SUCCESS = "success"
    BUSINESS_DECLINED = "business_declined"
    ERROR = "error"
    DISABLED = "disabled"
    PERMISSION_DENIED = "permission_denied"
    CONFIRMATION_REQUIRED = "confirmation_required"
    VALIDATION_ERROR = "validation_error"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"


class ToolExecutionResult(BaseModel):
    """
    Standardized result payload returned from tool execution.
    Maintains strict separation between:
    - System execution success (success=True/False)
    - Business domain decision (is_business_accepted=True/False)
    - Simulation disclosure (is_simulated=True/False)
    - Security / validation failures
    - Pending confirmation requirements
    """
    tool_id: str
    status: ToolExecutionStatus
    success: bool
    is_business_accepted: bool = True
    is_simulated: bool = False
    data: Optional[Dict[str, Any]] = None
    message: str
    mode: ToolExecutionMode = ToolExecutionMode.MOCK
    requires_confirmation: bool = False
    error_code: Optional[str] = None
    internal_diagnostics: Optional[str] = None

    @property
    def reference_id(self) -> Optional[str]:
        """Extract reference identifier from data dictionary if present."""
        if isinstance(self.data, dict):
            return (
                self.data.get("booking_reference")
                or self.data.get("appointment_reference")
                or self.data.get("reference_id")
                or self.data.get("message_id")
                or self.data.get("message_reference")
                or self.data.get("transfer_reference")
            )
        return None

    model_config = ConfigDict(extra="forbid")


# Canonical industry taxonomy and deterministic normalization mapping
CANONICAL_INDUSTRIES: Set[str] = {"restaurant", "hotel", "clinic", "services", "universal"}

INDUSTRY_NORMALIZATION_MAP: Dict[str, str] = {
    # Lodging / Hotel sector -> "hotel"
    "hotel": "hotel",
    "resort": "hotel",
    "hotel & resort": "hotel",
    "hotel and resort": "hotel",
    "hotel / hospitality": "hotel",
    "hotel and hospitality": "hotel",
    "hotel & hospitality": "hotel",
    "hospitality": "hotel",
    "hospitality & lodging": "hotel",
    "hospitality and lodging": "hotel",
    "lodging": "hotel",
    "motel": "hotel",
    "inn": "hotel",
    "bed & breakfast": "hotel",
    "bed and breakfast": "hotel",
    "boutique hotel": "hotel",

    # Dining / Restaurant sector -> "restaurant"
    "restaurant": "restaurant",
    "dining": "restaurant",
    "dining & hospitality": "restaurant",
    "dining and hospitality": "restaurant",
    "cafe": "restaurant",
    "bistro": "restaurant",
    "cafe & bistro": "restaurant",
    "cafe and bistro": "restaurant",
    "food & beverage": "restaurant",
    "food and beverage": "restaurant",
    "bar & lounge": "restaurant",
    "bar and lounge": "restaurant",
    "food": "restaurant",
    "eatery": "restaurant",
    "pub": "restaurant",
    "catering": "restaurant",
    "bakery": "restaurant",

    # Healthcare / Clinic sector -> "clinic"
    "clinic": "clinic",
    "clinic / medical": "clinic",
    "clinic and medical": "clinic",
    "clinic & medical": "clinic",
    "doctor": "clinic",
    "healthcare": "clinic",
    "healthcare & services": "clinic",
    "healthcare and services": "clinic",
    "hospital": "clinic",
    "dental": "clinic",
    "dental clinic": "clinic",
    "medical": "clinic",
    "therapy": "clinic",
    "physiotherapy": "clinic",

    # Professional & Personal Services -> "services"
    "service": "services",
    "services": "services",
    "salon": "services",
    "spa": "services",
    "salon / spa": "services",
    "salon & spa": "services",
    "salon and spa": "services",
    "consulting": "services",
    "consulting / services": "services",
    "consulting and services": "services",
    "astrology / spiritual": "services",
    "astrology and spiritual": "services",
    "legal": "services",
}


def normalize_industry_name(industry: Optional[str]) -> Optional[str]:
    """
    Map raw business industry string to its canonical industry key.
    Returns None if the industry cannot be authoritatively mapped.
    """
    if not industry:
        return None
    clean = re.sub(r"[^\w\s&/]", " ", industry).strip().lower()
    clean = re.sub(r"\s+", " ", clean)
    return INDUSTRY_NORMALIZATION_MAP.get(clean)


def normalize_booking_date(date_str: str, tz_name: str = "Asia/Kolkata") -> str:
    """
    Deterministically normalize any user or LLM provided booking/appointment date string.
    - Anchors dates without explicit year (e.g. '29 November', '29 Nov', '11-29') to the current calendar year.
    - Corrects hallucinated past years (e.g. 2023, 2024, 2025) to the current calendar year.
    - If a date in the current year has already passed relative to today, advances to next year.
    - Resolves relative terms like 'today', 'tomorrow', 'day after tomorrow', 'aaj', 'kal', 'parson'.
    - Returns standardized 'YYYY-MM-DD' ISO date string.
    """
    if not date_str or not isinstance(date_str, str):
        return date_str

    clean = date_str.strip()
    if not clean:
        return clean

    try:
        try:
            local_tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            local_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        today = datetime.now(local_tz).date()

        lower = clean.lower()

        # Handle relative terms in English and Hindi
        if lower in {"today", "aaj", "आज"}:
            return today.isoformat()
        if lower in {"tomorrow", "kal", "कल"}:
            return (today + timedelta(days=1)).isoformat()
        if lower in {"day after tomorrow", "parson", "परसों"}:
            return (today + timedelta(days=2)).isoformat()

        # If already standard ISO YYYY-MM-DD format, parse strictly without dayfirst ambiguity
        if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
            dt = datetime.strptime(clean, "%Y-%m-%d")
            y, m, d = dt.year, dt.month, dt.day
            if y < today.year:
                target_year = today.year
                try:
                    candidate = date(target_year, m, d)
                except ValueError:
                    candidate = date(target_year, m, 28)
                if candidate < today:
                    target_year += 1
                return date(target_year, m, d).isoformat()
            return clean

        # Check if caller or model supplied an explicit 4-digit year
        has_explicit_year = bool(re.search(r"\b(19|20)\d{2}\b", clean))

        # Default anchor is current year
        default_dt = datetime(today.year, 1, 1)
        parsed_dt = dateutil.parser.parse(clean, default=default_dt, dayfirst=True)
        y, m, d = parsed_dt.year, parsed_dt.month, parsed_dt.day

        # If no explicit year was supplied, or if the year is in the past (e.g. LLM training cutoff hallucination):
        if not has_explicit_year or y < today.year:
            target_year = today.year
            try:
                candidate = date(target_year, m, d)
            except ValueError:
                candidate = date(target_year, m, 28)

            if candidate < today:
                target_year += 1
            return date(target_year, m, d).isoformat()

        return date(y, m, d).isoformat()
    except Exception:
        return clean



class ToolDefinition(BaseModel):
    """
    Canonical metadata and execution handler contract for a modular tool.
    Keeps tool catalog definition separate from runtime execution logic.
    """
    id: str
    name: str
    description: str
    category: ToolCategory
    icon: str = "🔧"
    allowed_industries: List[str] = Field(default_factory=lambda: ["*"])
    allowed_canonical_industries: List[str] = Field(default_factory=lambda: ["*"])
    input_schema: Type[BaseModel]
    requires_confirmation: bool = False
    is_implemented: bool = True
    execution_mode: ToolExecutionMode = ToolExecutionMode.MOCK
    handler: Optional[Callable[[BaseModel, Dict[str, Any]], ToolExecutionResult]] = None
    friendly_name: Optional[str] = None
    confirmation_formatter: Optional[Callable[[Dict[str, Any]], str]] = None

    def format_confirmation_summary(self, args: Dict[str, Any]) -> str:
        """Generate human-readable summary of action arguments for confirmation dialog."""
        if self.confirmation_formatter:
            try:
                return self.confirmation_formatter(args)
            except Exception:
                pass
        # Resilient default formatter using title-cased field names
        lines = []
        for k, v in args.items():
            if v is not None and v != "":
                label = k.replace("_", " ").title()
                lines.append(f"• {label}: {v}")
        return "\n".join(lines) if lines else "• Action details confirmed."

    def is_allowed_for_industry(self, industry: Optional[str]) -> bool:
        """
        Evaluate if tool is authorized for a business industry using canonical allowlists.
        Replaces ambiguous token-overlap matching with explicit canonical sector resolution.
        "*" indicates a universal tool available for all business types.
        """
        if not self.allowed_canonical_industries or "*" in self.allowed_canonical_industries:
            return True
        if not industry:
            return False

        canonical_ind = normalize_industry_name(industry)
        if not canonical_ind:
            return False

        return (
            canonical_ind in self.allowed_canonical_industries
            or "*" in self.allowed_canonical_industries
        )

    model_config = ConfigDict(arbitrary_types_allowed=True)
