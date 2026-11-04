import logging
import uuid
from typing import Dict, Any, List, Optional, Set
from pydantic import ValidationError

from backend.tools.base import (
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
    ToolCategory,
)
from backend.tools.definitions import (
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
    CheckRoomAvailabilityInput,
    CreateRoomBookingInput,
    QueryMenuPricingInput,
    QueryRoomPricingInput,
    QueryTreatmentPricingInput,
)
from backend.tools.implementations.information import handle_answer_faq
from backend.tools.implementations.dining import (
    handle_check_table_availability,
    handle_create_table_booking,
    handle_query_menu_pricing,
    format_dining_reservation_summary,
)
from backend.tools.implementations.healthcare import (
    handle_check_appointment_availability,
    handle_create_appointment,
    format_appointment_summary,
    handle_query_treatment_pricing,
)
from backend.tools.implementations.communication import (
    handle_take_message,
    handle_transfer_call,
)
from backend.tools.implementations.hospitality import (
    handle_check_room_availability,
    handle_create_room_booking,
    format_hotel_reservation_summary,
    handle_query_room_pricing,
)

logger = logging.getLogger(__name__)

# Explicit execution modes allowlist
VALID_EXECUTION_MODES: Set[str] = {"mock", "live", "unavailable"}

# Tools that possess verified live integrations in this repository
LIVE_VERIFIED_TOOLS: Set[str] = {
    "answer_faq",
    "take_message",
    "transfer_call",
    "query_menu_pricing",
    "query_room_pricing",
    "query_treatment_pricing",
    "check_appointment_availability",
    "create_appointment",
    "check_table_availability",
    "create_table_booking",
    "check_room_availability",
    "create_room_booking",
}


class ToolRegistry:
    """
    Central repository for receptionist tools.
    Provides lookup, listing, tenant permission enforcement, and safe execution.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """
        Register a new tool definition.
        Rejects duplicate tool IDs to ensure deterministic lookup.
        """
        if tool.id in self._tools:
            raise ValueError(
                f"Duplicate tool registration: Tool ID '{tool.id}' is already registered."
            )
        self._tools[tool.id] = tool

    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        """Look up a tool definition by ID."""
        return self._tools.get(tool_id)

    def has_tool(self, tool_id: str) -> bool:
        """Check if a tool ID is registered."""
        return tool_id in self._tools

    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        industry: Optional[str] = None,
    ) -> List[ToolDefinition]:
        """Return list of registered tools, optionally filtered by category and industry."""
        tools = list(self._tools.values())
        if category is not None:
            tools = [t for t in tools if t.category == category]
        if industry is not None:
            tools = [t for t in tools if t.is_allowed_for_industry(industry)]
        return tools

    def get_tools_for_industry(self, industry: Optional[str]) -> List[ToolDefinition]:
        """Return all tools permitted for a specific business industry type."""
        return [t for t in self._tools.values() if t.is_allowed_for_industry(industry)]

    def get_enabled_tools_for_business(
        self, business_config: Dict[str, Any]
    ) -> List[ToolDefinition]:
        """
        Return only the tools that are:
        1. Explicitly enabled in the business configuration
        2. Authorized for the business's industry category
        """
        enabled_map = business_config.get("enabled_tools", {})
        biz_industry = business_config.get("industry")
        return [
            tool
            for tool in self._tools.values()
            if enabled_map.get(tool.id) is True and tool.is_allowed_for_industry(biz_industry)
        ]

    def execute_tool(
        self,
        business_id: str,
        business_config: Dict[str, Any],
        tool_id: str,
        input_data: Dict[str, Any],
        confirmed: bool = False,
    ) -> ToolExecutionResult:
        """
        Primary execution boundary for all tool actions.
        Enforces tenant permissions, schema validation, industry eligibility,
        execution mode policies, and two-phase confirmation.
        """
        # 1. Validate trusted business context
        if not business_config or not isinstance(business_config, dict):
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="INVALID_BUSINESS_CONTEXT",
                message="Invalid or missing trusted business context.",
            )

        if business_id and business_config.get("id") and business_config.get("id") != business_id:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.PERMISSION_DENIED,
                success=False,
                is_business_accepted=False,
                error_code="BUSINESS_IDENTITY_MISMATCH",
                message=f"Context authorization mismatch: requested business '{business_id}' does not match configuration.",
            )

        # 2. Validate execution mode against explicit allowlist
        raw_mode = business_config.get("execution_mode", "mock")
        if not isinstance(raw_mode, str) or raw_mode.lower() not in VALID_EXECUTION_MODES:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="INVALID_EXECUTION_MODE",
                message=f"Invalid execution mode '{raw_mode}'. Valid modes are: {sorted(list(VALID_EXECUTION_MODES))}.",
            )
        exec_mode = raw_mode.lower()

        # 3. Look up tool in registry
        tool = self.get_tool(tool_id)
        if not tool:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="TOOL_NOT_FOUND",
                message=f"Tool '{tool_id}' is not registered in the system catalogue.",
            )

        # 4. Enforce industry eligibility
        biz_industry = business_config.get("industry")
        if not tool.is_allowed_for_industry(biz_industry):
            allowed_desc = ", ".join(tool.allowed_industries)
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.DISABLED,
                success=False,
                is_business_accepted=False,
                error_code="INDUSTRY_NOT_PERMITTED",
                message=(
                    f"Tool '{tool.name}' is only available for businesses in: {allowed_desc}. "
                    f"Business '{business_id}' is in the '{biz_industry}' industry."
                ),
            )

        # 5. Enforce tenant tool permissions
        enabled_tools = business_config.get("enabled_tools", {})
        if not enabled_tools.get(tool_id, False):
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.DISABLED,
                success=False,
                is_business_accepted=False,
                error_code="TOOL_DISABLED_FOR_TENANT",
                message=f"Tool '{tool_id}' is not enabled for business '{business_id}'.",
            )

        # 6. Check implementation readiness and execution mode compliance
        if not tool.is_implemented or tool.handler is None:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.UNAVAILABLE,
                success=False,
                is_business_accepted=False,
                mode=ToolExecutionMode.UNAVAILABLE,
                error_code="TOOL_UNIMPLEMENTED",
                message=f"Tool '{tool_id}' is registered but its execution handler is currently unavailable.",
            )

        if exec_mode == "live":
            tool_cfg = business_config.get("tool_configs", {}).get(tool.id, {})
            is_capability_ready = (
                isinstance(tool_cfg, dict)
                and tool_cfg.get("status") == "ready"
                and tool_cfg.get("is_enabled") is True
            )
            if tool.id not in LIVE_VERIFIED_TOOLS and not is_capability_ready:
                return ToolExecutionResult(
                    tool_id=tool_id,
                    status=ToolExecutionStatus.UNAVAILABLE,
                    success=False,
                    is_business_accepted=False,
                    mode=ToolExecutionMode.UNAVAILABLE,
                    error_code="LIVE_INTEGRATION_NOT_CONFIGURED",
                    message=f"Tool '{tool_id}' is simulated (mock) and no verified live integration is configured.",
                )

        # 7. Validate input payload against tool schema
        try:
            validated_input = tool.input_schema.model_validate(input_data)
        except ValidationError as val_err:
            first_err = val_err.errors()[0]
            field_name = ".".join(str(loc) for loc in first_err["loc"])
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.VALIDATION_ERROR,
                success=False,
                is_business_accepted=False,
                error_code="INPUT_VALIDATION_ERROR",
                message=f"Validation failed for field '{field_name}': {first_err['msg']}",
            )

        # 8. Two-phase confirmation boundary
        if tool.requires_confirmation and not confirmed:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.CONFIRMATION_REQUIRED,
                success=False,
                is_business_accepted=False,
                requires_confirmation=True,
                message=(
                    f"Action '{tool.name}' requires explicit confirmation before execution. "
                    "Please confirm the details to complete."
                ),
            )

        # 9. Execute permitted handler with validated input & trusted context
        try:
            return tool.handler(validated_input, business_config)
        except Exception as exc:
            error_id = uuid.uuid4().hex[:8]
            logger.error(
                "Handler exception in tool '%s' for business '%s' [Error ID %s]: %s",
                tool_id, business_id, error_id, exc, exc_info=True
            )
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                is_business_accepted=False,
                error_code="HANDLER_EXCEPTION",
                internal_diagnostics=f"Exception [{error_id}] in {tool_id}: {type(exc).__name__}: {str(exc)}",
                message=f"An unexpected error occurred while executing the action (Error ID: {error_id}). Please try again later or contact our team.",
            )


def build_default_tool_registry() -> ToolRegistry:
    """
    Construct and populate the default tool registry with canonical tools.
    """
    registry = ToolRegistry()

    # 1. Answer FAQ (Universal)
    registry.register(
        ToolDefinition(
            id="answer_faq",
            name="Answer Business FAQs",
            description="Answers caller questions regarding business hours, location, services, and amenities using configured business FAQs.",
            category=ToolCategory.INFORMATION,
            icon="ℹ️",
            allowed_industries=["*"],
            allowed_canonical_industries=["*"],
            input_schema=AnswerFAQInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_answer_faq,
        )
    )

    # 2. Check Table Availability (Restaurant & Dining only)
    registry.register(
        ToolDefinition(
            id="check_table_availability",
            name="Check Table Availability",
            description="Inspects real-time table inventory for requested date, time, and party size.",
            category=ToolCategory.DINING,
            icon="🍽️",
            allowed_industries=["Restaurant", "Dining & Hospitality", "Cafe", "Bistro", "Food & Beverage", "Bar & Lounge"],
            allowed_canonical_industries=["restaurant"],
            input_schema=CheckTableAvailabilityInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_check_table_availability,
        )
    )

    # 2b. Query Menu & Pricing (Restaurant & Dining only)
    registry.register(
        ToolDefinition(
            id="query_menu_pricing",
            name="Query Menu & Pricing",
            description="Searches restaurant menu dishes, current prices, descriptions, ingredients, and dietary options (vegetarian, vegan, gluten-free, jain, spicy, mild, sweet desserts).",
            category=ToolCategory.DINING,
            icon="📜",
            allowed_industries=["Restaurant", "Dining & Hospitality", "Cafe", "Bistro", "Food & Beverage", "Bar & Lounge"],
            allowed_canonical_industries=["restaurant"],
            input_schema=QueryMenuPricingInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_query_menu_pricing,
        )
    )

    # 3. Create Table Booking (Restaurant & Dining only)
    registry.register(
        ToolDefinition(
            id="create_table_booking",
            name="Create Table Booking",
            description="Reserves a dining table after guest details and party size are confirmed.",
            category=ToolCategory.DINING,
            icon="📅",
            allowed_industries=["Restaurant", "Dining & Hospitality", "Cafe", "Bistro", "Food & Beverage", "Bar & Lounge"],
            allowed_canonical_industries=["restaurant"],
            input_schema=CreateTableBookingInput,
            requires_confirmation=True,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_create_table_booking,
            friendly_name="dining reservation",
            confirmation_formatter=format_dining_reservation_summary,
        )
    )

    # 4. Check Room Availability (Hotel & Hospitality only)
    registry.register(
        ToolDefinition(
            id="check_room_availability",
            name="Check Room Availability",
            description="Inspects real-time hotel room availability for requested check-in and check-out dates and room type.",
            category=ToolCategory.HOSPITALITY,
            icon="🏨",
            allowed_industries=["Hotel", "Resort", "Hotel & Resort", "Hospitality & Lodging", "Hospitality", "Lodging", "Bed & Breakfast", "Inn"],
            allowed_canonical_industries=["hotel"],
            input_schema=CheckRoomAvailabilityInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_check_room_availability,
        )
    )

    # 5. Create Room Booking (Hotel & Hospitality only)
    registry.register(
        ToolDefinition(
            id="create_room_booking",
            name="Create Room Booking",
            description="Reserves a hotel room for a guest after confirming stay dates, room type, and guest contact details.",
            category=ToolCategory.HOSPITALITY,
            icon="🛏️",
            allowed_industries=["Hotel", "Resort", "Hotel & Resort", "Hospitality & Lodging", "Hospitality", "Lodging", "Bed & Breakfast", "Inn"],
            allowed_canonical_industries=["hotel"],
            input_schema=CreateRoomBookingInput,
            requires_confirmation=True,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_create_room_booking,
            friendly_name="hotel room reservation",
            confirmation_formatter=format_hotel_reservation_summary,
        )
    )

    # 6. Query Room & Suite Pricing (Hotel & Hospitality only)
    registry.register(
        ToolDefinition(
            id="query_room_pricing",
            name="Query Room & Suite Pricing",
            description="Answers caller inquiries regarding hotel room types, nightly tariffs, suite amenities (ocean view, balcony, bathtub), bed configurations, breakfast inclusions, and stay policies.",
            category=ToolCategory.HOSPITALITY,
            icon="🏨",
            allowed_industries=["Hotel", "Resort", "Hotel & Resort", "Hospitality & Lodging", "Hospitality", "Lodging", "Bed & Breakfast", "Inn"],
            allowed_canonical_industries=["hotel"],
            input_schema=QueryRoomPricingInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_query_room_pricing,
        )
    )



    # 4b. Query Treatment & Consultation Pricing (Clinic & Medical only)
    registry.register(
        ToolDefinition(
            id="query_treatment_pricing",
            name="Query Treatment & Consultation Pricing",
            description="Answers caller inquiries regarding clinical treatment procedures, consultation fees, specialist doctors, procedure durations, and patient preparation guidelines.",
            category=ToolCategory.HEALTHCARE,
            icon="🩺",
            allowed_industries=["Clinic", "Doctor", "Healthcare & Services", "Hospital", "Dental", "Medical"],
            allowed_canonical_industries=["clinic"],
            input_schema=QueryTreatmentPricingInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_query_treatment_pricing,
        )
    )

    # 4. Check Appointment Availability (Doctor, Clinic, Salon, Consulting only)
    registry.register(
        ToolDefinition(
            id="check_appointment_availability",
            name="Check Appointment Availability",
            description="Inspects open consultation slots across clinic doctors, specialists, and departments.",
            category=ToolCategory.HEALTHCARE,
            icon="🩺",
            allowed_industries=["Clinic", "Doctor", "Healthcare & Services", "Hospital", "Dental", "Medical", "Salon", "Spa", "Consulting / Services", "Astrology / Spiritual", "Legal"],
            allowed_canonical_industries=["clinic", "services"],
            input_schema=CheckAppointmentAvailabilityInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_check_appointment_availability,
        )
    )

    # 5. Create Appointment (Doctor, Clinic, Salon, Consulting only)
    registry.register(
        ToolDefinition(
            id="create_appointment",
            name="Create Appointment",
            description="Schedules a patient or client consultation after date, time, and department are confirmed.",
            category=ToolCategory.HEALTHCARE,
            icon="📋",
            allowed_industries=["Clinic", "Doctor", "Healthcare & Services", "Hospital", "Dental", "Medical", "Salon", "Spa", "Consulting / Services", "Astrology / Spiritual", "Legal"],
            allowed_canonical_industries=["clinic", "services"],
            input_schema=CreateAppointmentInput,
            requires_confirmation=True,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_create_appointment,
            friendly_name="appointment",
            confirmation_formatter=format_appointment_summary,
        )
    )

    # 6. Take Message (Universal)
    registry.register(
        ToolDefinition(
            id="take_message",
            name="Take a Message",
            description="Captures caller message notes, priority, and callback details when staff are unavailable.",
            category=ToolCategory.COMMUNICATION,
            icon="📝",
            allowed_industries=["*"],
            allowed_canonical_industries=["*"],
            input_schema=TakeMessageInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_take_message,
        )
    )

    # 7. Transfer Call (Universal)
    registry.register(
        ToolDefinition(
            id="transfer_call",
            name="Transfer Call",
            description="Transfers the caller to a designated human desk or emergency line according to business escalation rules.",
            category=ToolCategory.COMMUNICATION,
            icon="📞",
            allowed_industries=["*"],
            allowed_canonical_industries=["*"],
            input_schema=TransferCallInput,
            requires_confirmation=False,
            is_implemented=True,
            execution_mode=ToolExecutionMode.MOCK,
            handler=handle_transfer_call,
        )
    )

    return registry


# Singleton cache for default registry
_default_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Return the application's singleton ToolRegistry instance."""
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_tool_registry()
    return _default_registry
