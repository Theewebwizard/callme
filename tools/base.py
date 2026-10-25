"""
Base models, enums, and execution result schemas for the modular AI receptionist tool registry.
Decoupled into the standalone tools package.
"""

from enum import Enum
from typing import Dict, Any, Optional, Type, Callable, List
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


class ToolExecutionStatus(str, Enum):
    """Status returned by the tool execution boundary."""
    SUCCESS = "success"
    ERROR = "error"
    DISABLED = "disabled"
    CONFIRMATION_REQUIRED = "confirmation_required"
    VALIDATION_ERROR = "validation_error"
    UNAVAILABLE = "unavailable"


class ToolExecutionResult(BaseModel):
    """
    Standardized result payload returned from tool execution.
    Maintains strict separation between successful operations, validation failures,
    and missing confirmation states.
    """
    tool_id: str
    status: ToolExecutionStatus
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str
    mode: ToolExecutionMode = ToolExecutionMode.MOCK
    requires_confirmation: bool = False

    @property
    def reference_id(self) -> Optional[str]:
        """Extract reference identifier from data dictionary if present."""
        if isinstance(self.data, dict):
            return (
                self.data.get("booking_reference")
                or self.data.get("appointment_reference")
                or self.data.get("reference_id")
                or self.data.get("message_id")
            )
        return None

    model_config = ConfigDict(extra="ignore")


class ToolDefinition(BaseModel):
    """
    Canonical metadata and execution handler contract for a modular tool.
    Keeps tool catalog definition separate from runtime execution logic.
    """
    id: str
    name: str
    description: str
    category: ToolCategory
    allowed_industries: List[str] = Field(default_factory=lambda: ["*"])
    input_schema: Type[BaseModel]
    requires_confirmation: bool = False
    is_implemented: bool = True
    execution_mode: ToolExecutionMode = ToolExecutionMode.MOCK
    handler: Optional[Callable[[BaseModel, Dict[str, Any]], ToolExecutionResult]] = None

    def is_allowed_for_industry(self, industry: Optional[str]) -> bool:
        """
        Evaluate if tool is authorized for a business industry.
        "*" indicates a universal tool available for all business types.
        """
        if not self.allowed_industries or "*" in self.allowed_industries:
            return True
        if not industry:
            return False

        clean_ind = industry.strip().lower()
        for allowed in self.allowed_industries:
            clean_allowed = allowed.strip().lower()
            if clean_allowed == "*" or clean_allowed in clean_ind or clean_ind in clean_allowed:
                return True
        return False

    model_config = ConfigDict(arbitrary_types_allowed=True)
