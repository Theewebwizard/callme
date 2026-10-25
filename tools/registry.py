"""
Modular Tool Registry and execution boundary for the AI Receptionist Platform.
Enforces multi-tenant permissions, input validation, industry boundaries, and two-phase confirmation.
"""

from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from tools.base import (
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolExecutionMode,
    ToolCategory,
)
from tools.definitions import (
    AnswerFAQInput,
    CheckTableAvailabilityInput,
    CreateTableBookingInput,
    CheckAppointmentAvailabilityInput,
    CreateAppointmentInput,
    TakeMessageInput,
    TransferCallInput,
    CANONICAL_TOOLS,
)


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
        Enforces tenant permissions, schema validation, industry eligibility, and two-phase confirmation.
        """
        # 1. Validate trusted business context
        if not business_config or not isinstance(business_config, dict):
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                message="Invalid or missing trusted business context.",
            )

        # 2. Lookup tool
        tool = self.get_tool(tool_id)
        if not tool:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                message=f"Unknown tool '{tool_id}'. This tool is not registered in the system.",
            )

        # 3. Industry Authorization Guard
        biz_industry = business_config.get("industry")
        if not tool.is_allowed_for_industry(biz_industry):
            allowed_str = ", ".join(tool.allowed_industries)
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.DISABLED,
                success=False,
                message=(
                    f"Tool '{tool.name}' is not enabled for business '{business_id}'. "
                    f"It is only available for businesses in: {allowed_str}. "
                    f"Business '{business_id}' is in the '{biz_industry}' industry."
                ),
            )

        # 4. Check tenant permission
        enabled_map = business_config.get("enabled_tools", {})
        if not enabled_map.get(tool_id, False):
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.DISABLED,
                success=False,
                message=f"Tool '{tool.name}' is not enabled for business '{business_id}'.",
            )

        # 5. Check implementation availability
        if not tool.is_implemented or tool.handler is None:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.UNAVAILABLE,
                success=False,
                mode=ToolExecutionMode.UNAVAILABLE,
                message=(
                    f"Tool '{tool.name}' is registered but currently unavailable or not fully implemented. "
                    f"No simulated or live action was performed."
                ),
            )

        # 6. Two-phase confirmation interception
        if tool.requires_confirmation and not confirmed:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.CONFIRMATION_REQUIRED,
                success=False,
                requires_confirmation=True,
                data=input_data,
                message=(
                    f"Action '{tool.name}' requires explicit customer or staff confirmation before proceeding. "
                    f"Parameters prepared for review."
                ),
            )

        # 7. Validate schema with Pydantic
        try:
            validated_model = tool.input_schema.model_validate(input_data)
        except ValidationError as val_err:
            first_error = val_err.errors()[0]
            field_name = ".".join(str(loc) for loc in first_error["loc"])
            error_msg = f"Validation failed for field '{field_name}': {first_error['msg']}"
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.VALIDATION_ERROR,
                success=False,
                message=error_msg,
            )

        # 8. Execute verified tool handler
        try:
            return tool.handler(validated_model, business_config)
        except Exception as exc:
            return ToolExecutionResult(
                tool_id=tool_id,
                status=ToolExecutionStatus.ERROR,
                success=False,
                message=f"Error executing tool '{tool.name}': {str(exc)}",
            )


def build_default_tool_registry() -> ToolRegistry:
    """
    Construct the canonical pre-registered tool repository with all 7 tools.
    """
    registry = ToolRegistry()
    for tool_def in CANONICAL_TOOLS:
        registry.register(tool_def)
    return registry


_DEFAULT_REGISTRY: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Retrieve or initialize the global shared tool registry singleton."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_default_tool_registry()
    return _DEFAULT_REGISTRY
