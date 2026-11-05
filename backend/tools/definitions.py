"""
Pydantic input models and schema definitions for the receptionist tool catalogue.
Enforces strict type safety, boundary validation, and rejection of dangerous inputs.
"""

from datetime import datetime
import re
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


def _validate_calendar_date(v: str, field_name: str = "date") -> str:
    """Validate that the string is a genuine calendar-valid date in YYYY-MM-DD format."""
    clean = v.strip() if isinstance(v, str) else v
    if isinstance(clean, str):
        from backend.tools.base import normalize_booking_date
        clean = normalize_booking_date(clean)
    if not isinstance(clean, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format.")
    try:
        datetime.strptime(clean, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid calendar date '{clean}'. Day or month does not exist on the calendar.") from e
    return clean


def _validate_clock_time(v: Optional[str], field_name: str = "time") -> Optional[str]:
    """Validate that the string is a genuine 24-hour clock time in HH:MM format."""
    if v is None:
        return None
    clean = v.strip() if isinstance(v, str) else v
    if not isinstance(clean, str) or not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", clean):
        raise ValueError(f"{field_name} must be in 24-hour HH:MM format (00:00 - 23:59).")
    try:
        datetime.strptime(clean, "%H:%M")
    except ValueError as e:
        raise ValueError(f"Invalid clock time '{clean}'.") from e
    return clean


def _validate_phone_number(v: str, field_name: str = "phone") -> str:
    """Validate phone number format and standard digit length."""
    clean = v.strip() if isinstance(v, str) else v
    if not isinstance(clean, str) or not re.match(r"^[\d\+\s\-\(\)]+$", clean):
        raise ValueError(f"{field_name} contains invalid characters. Use digits and standard separators.")
    digits = re.sub(r"\D", "", clean)
    if len(digits) < 7:
        raise ValueError(f"{field_name} must contain at least 7 digits.")
    if len(digits) > 15:
        raise ValueError(f"{field_name} cannot exceed 15 digits (ITU-T E.164).")
    return clean


class AnswerFAQInput(BaseModel):
    """Input payload for looking up business FAQs."""
    question: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Customer question or inquiry keyword to match against configured FAQs.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def clean_question(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    model_config = ConfigDict(extra="forbid")


class CheckTableAvailabilityInput(BaseModel):
    """Input payload for inspecting dining table availability."""
    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Target dining date in YYYY-MM-DD format.",
    )
    time: str = Field(
        ...,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Requested dining time in 24-hour HH:MM format.",
    )
    party_size: int = Field(
        ...,
        ge=1,
        le=20,
        description="Number of dining guests (1 to 20).",
    )

    @field_validator("date", mode="before")
    @classmethod
    def check_date(cls, v: str) -> str:
        return _validate_calendar_date(v, "date")

    @field_validator("time")
    @classmethod
    def check_time(cls, v: str) -> str:
        return _validate_clock_time(v, "time")

    model_config = ConfigDict(extra="forbid")


class CreateTableBookingInput(BaseModel):
    """Input payload for reserving a table."""
    customer_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full name of primary dining contact.",
    )
    customer_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Contact telephone number for SMS/call confirmation.",
    )
    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Reservation date in YYYY-MM-DD format.",
    )
    time: str = Field(
        ...,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Reservation time in 24-hour HH:MM format.",
    )
    party_size: int = Field(
        ...,
        ge=1,
        le=20,
        description="Number of dining guests (1 to 20).",
    )
    special_requests: Optional[str] = Field(
        None,
        max_length=300,
        description="Dietary requirements or seating preferences (e.g. outdoor, high chair).",
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional client idempotency key to prevent duplicate booking on network retry.",
    )

    @field_validator("customer_name", mode="before")
    @classmethod
    def clean_name(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("customer_phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        return _validate_phone_number(v, "customer_phone")

    @field_validator("date", mode="before")
    @classmethod
    def check_date(cls, v: str) -> str:
        return _validate_calendar_date(v, "date")

    @field_validator("time")
    @classmethod
    def check_time(cls, v: str) -> str:
        return _validate_clock_time(v, "time")

    @field_validator("special_requests", mode="before")
    @classmethod
    def clean_requests(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip()
            return clean if clean else None
        return v

    model_config = ConfigDict(extra="forbid")


class CheckAppointmentAvailabilityInput(BaseModel):
    """Input payload for checking medical, dental, or clinical consultation slots."""
    service_or_department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Medical/dental specialty or practitioner requested.",
    )
    preferred_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Requested appointment date in YYYY-MM-DD format.",
    )
    preferred_time: Optional[str] = Field(
        None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Preferred consultation time in 24-hour HH:MM format.",
    )

    @field_validator("service_or_department", mode="before")
    @classmethod
    def clean_dept(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("preferred_date", mode="before")
    @classmethod
    def check_date(cls, v: str) -> str:
        return _validate_calendar_date(v, "preferred_date")

    @field_validator("preferred_time")
    @classmethod
    def check_time(cls, v: Optional[str]) -> Optional[str]:
        return _validate_clock_time(v, "preferred_time")

    model_config = ConfigDict(extra="forbid")


class CreateAppointmentInput(BaseModel):
    """Input payload for creating a patient or client appointment."""
    patient_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full legal name of the patient.",
    )
    patient_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Patient contact telephone number.",
    )
    service_or_department: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Clinical department, treatment, or practitioner.",
    )
    appointment_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Confirmed appointment date in YYYY-MM-DD format.",
    )
    appointment_time: str = Field(
        ...,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Confirmed appointment time in 24-hour HH:MM format.",
    )
    notes: Optional[str] = Field(
        None,
        max_length=300,
        description="Clinical symptoms or visit background.",
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional client idempotency key to prevent duplicate booking on network retry.",
    )

    @field_validator("patient_name", "service_or_department", mode="before")
    @classmethod
    def clean_strings(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("patient_phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        return _validate_phone_number(v, "patient_phone")

    @field_validator("appointment_date", mode="before")
    @classmethod
    def check_date(cls, v: str) -> str:
        return _validate_calendar_date(v, "appointment_date")

    @field_validator("appointment_time")
    @classmethod
    def check_time(cls, v: str) -> str:
        return _validate_clock_time(v, "appointment_time")

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip()
            return clean if clean else None
        return v

    model_config = ConfigDict(extra="forbid")


class TakeMessageInput(BaseModel):
    """Input payload for capturing caller callback details and messages."""
    caller_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full name of caller.",
    )
    caller_phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        pattern=r"^[\d\+\s\-\(\)]+$",
        description="Callback contact telephone number.",
    )
    message: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Detailed message content to deliver to business staff.",
    )
    urgency: str = Field(
        "normal",
        pattern=r"^(low|normal|urgent)$",
        description="Callback priority: 'low', 'normal', or 'urgent'.",
    )

    @field_validator("caller_name", "message", mode="before")
    @classmethod
    def clean_strings(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("caller_phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        return _validate_phone_number(v, "caller_phone")

    model_config = ConfigDict(extra="forbid")


class TransferCallInput(BaseModel):
    """Input payload for requesting a human operator or line transfer."""
    reason: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Reason caller is requesting human escalation.",
    )
    department_or_target: Optional[str] = Field(
        None,
        max_length=100,
        description="Specific staff member, department, or desk requested.",
    )

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("department_or_target", mode="before")
    @classmethod
    def clean_target(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip()
            return clean if clean else None
        return v

    model_config = ConfigDict(extra="forbid")


class CheckRoomAvailabilityInput(BaseModel):
    """Input payload for inspecting hotel room availability."""
    check_in_date: str = Field(
        ...,
        description="Guest check-in date in YYYY-MM-DD format (e.g., '2026-11-01').",
    )
    check_out_date: str = Field(
        ...,
        description="Guest check-out date in YYYY-MM-DD format (e.g., '2026-11-03').",
    )
    room_type: str = Field(
        "any",
        max_length=50,
        description="Preferred room category (e.g., 'deluxe', 'suite', 'standard', 'villa', or 'any').",
    )
    guests_count: int = Field(
        1,
        ge=1,
        le=20,
        description="Total number of adult/child guests staying in the room.",
    )

    @field_validator("check_in_date", mode="before")
    @classmethod
    def check_in(cls, v: str) -> str:
        return _validate_calendar_date(v, "check_in_date")

    @field_validator("check_out_date", mode="before")
    @classmethod
    def check_out(cls, v: str) -> str:
        return _validate_calendar_date(v, "check_out_date")

    @field_validator("room_type", mode="before")
    @classmethod
    def clean_room(cls, v: Any) -> str:
        return v.strip().lower() if isinstance(v, str) else "any"

    model_config = ConfigDict(extra="forbid")


class CreateRoomBookingInput(BaseModel):
    """Input payload for creating a verified hotel room reservation."""
    check_in_date: str = Field(
        ...,
        description="Guest check-in date in YYYY-MM-DD format.",
    )
    check_out_date: str = Field(
        ...,
        description="Guest check-out date in YYYY-MM-DD format.",
    )
    guest_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full legal name of the primary staying guest.",
    )
    guest_phone: str = Field(
        ...,
        description="Direct telephone number of the primary guest for booking confirmation.",
    )
    guest_email: Optional[str] = Field(
        "",
        max_length=150,
        description="Optional contact email for digital confirmation and stay folio.",
    )
    room_type: str = Field(
        "standard",
        max_length=50,
        description="Room tier/category selected for the reservation.",
    )
    guests_count: int = Field(
        1,
        ge=1,
        le=20,
        description="Total number of guests staying.",
    )
    special_requests: Optional[str] = Field(
        "",
        max_length=500,
        description="Special requirements such as early check-in, high floor, quiet room, or extra bed.",
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=64,
        description="Idempotency key to prevent accidental duplicate booking submissions.",
    )

    @field_validator("check_in_date", mode="before")
    @classmethod
    def check_in(cls, v: str) -> str:
        return _validate_calendar_date(v, "check_in_date")

    @field_validator("check_out_date", mode="before")
    @classmethod
    def check_out(cls, v: str) -> str:
        return _validate_calendar_date(v, "check_out_date")

    @field_validator("guest_name", mode="before")
    @classmethod
    def clean_name(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("guest_phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        return _validate_phone_number(v, "guest_phone")

    model_config = ConfigDict(extra="forbid")



class QueryMenuPricingInput(BaseModel):
    """Input payload for searching dishes, ingredients, dietary options, and prices on a restaurant menu."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Dish name, ingredient, flavor note, or category keyword to search (e.g., 'paneer butter masala', 'something sweet', 'spicy starters', 'vegan options', 'rotis').",
    )
    category: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional category filter (e.g., Starters, Mains, Breads, Desserts, Beverages).",
    )
    dietary_preference: Optional[str] = Field(
        None,
        max_length=50,
        description="Optional dietary constraint (e.g., vegetarian, vegan, gluten-free, jain).",
    )
    max_budget: Optional[float] = Field(
        None,
        ge=0,
        description="Optional maximum budget per dish in local currency (e.g. 350.0).",
    )

    @field_validator("query", mode="before")
    @classmethod
    def clean_query(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    model_config = ConfigDict(extra="forbid")


class QueryRoomPricingInput(BaseModel):
    """Input payload for searching hotel room types, nightly rates, amenities, bed types, and inclusions."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Room tier, amenity, or feature keyword to search (e.g. 'ocean view suite', 'deluxe king room', 'private pool villa', 'breakfast included', 'rooms with bathtub').",
    )
    category: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional room category filter (e.g. Rooms, Suites, Villas, Penthouses).",
    )
    amenity_preference: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional amenity filter (e.g. ocean view, balcony, bathtub, private pool, high speed wifi).",
    )
    guests_count: Optional[int] = Field(
        None,
        ge=1,
        le=20,
        description="Optional party size / number of guests to ensure adequate room capacity.",
    )
    max_budget_per_night: Optional[float] = Field(
        None,
        ge=0,
        description="Optional maximum budget per night in local currency.",
    )
    check_in_date: Optional[str] = Field(
        None,
        description="Optional check-in date in YYYY-MM-DD format to compute total estimated stay cost.",
    )
    check_out_date: Optional[str] = Field(
        None,
        description="Optional check-out date in YYYY-MM-DD format to compute total estimated stay cost.",
    )

    @field_validator("query", mode="before")
    @classmethod
    def clean_query(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    model_config = ConfigDict(extra="forbid")

class QueryTreatmentPricingInput(BaseModel):
    """Input payload for searching clinic medical treatments, doctor consultation fees, procedure durations, and preparation guidelines."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Clinical treatment, procedure name, doctor specialty, or symptom keyword (e.g. 'root canal', 'teeth whitening', 'braces cost', 'consultation fee', 'wisdom tooth removal').",
    )
    category: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional category filter (e.g. 'Consultation', 'Preventive', 'Restoration', 'Orthodontics', 'Prosthodontics', 'Cosmetic', 'Surgery').",
    )
    practitioner_type: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional specialist / practitioner type filter (e.g. 'General Dentist', 'Orthodontist', 'Endodontist', 'Oral Surgeon', 'Physician').",
    )
    max_budget: Optional[float] = Field(
        None,
        ge=0,
        description="Optional maximum budget or fee ceiling in local currency.",
    )

    @field_validator("query", mode="before")
    @classmethod
    def clean_query(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    model_config = ConfigDict(extra="forbid")

