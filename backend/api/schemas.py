"""
Pydantic v2 request and response validation schemas for the REST API.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class BusinessSummaryResponse(BaseModel):
    """Concise business summary for tenant listing."""
    id: str
    name: str
    industry: str
    phone_number: Optional[str] = ""
    assigned_number_status: Optional[str] = "Active & Connected"
    opening_time: str
    closing_time: str
    timezone: str
    owner_email: Optional[str] = ""
    owner_name: Optional[str] = ""

    model_config = ConfigDict(from_attributes=True)


class FAQItem(BaseModel):
    """Knowledge base question and answer item."""
    id: Optional[str] = None
    question: str = Field(..., min_length=2, max_length=500, description="Customer question")
    answer: str = Field(..., min_length=2, max_length=2000, description="Authoritative answer")
    category: str = Field(default="General", max_length=100)

    model_config = ConfigDict(from_attributes=True)


class FAQListUpdateRequest(BaseModel):
    """Payload to atomically update or replace business FAQs."""
    faqs: List[FAQItem]


class BusinessDetailResponse(BaseModel):
    """Complete tenant configuration profile."""
    id: str
    name: str
    industry: str
    description: str
    phone_number: str
    assigned_number_status: str
    opening_time: str
    closing_time: str
    timezone: str
    greeting_message: str
    languages: List[str]
    transfer_instructions: str
    owner_email: Optional[str] = ""
    owner_name: Optional[str] = ""
    faqs: List[FAQItem]
    enabled_tools: Dict[str, bool]
    stats: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class BusinessCreateRequest(BaseModel):
    """Payload to register a new business tenant."""
    id: Optional[str] = Field(None, max_length=100, description="Optional custom slug/ID")
    name: str = Field(..., min_length=1, max_length=255, description="Official business name")
    industry: str = Field("Other", min_length=1, max_length=100)
    description: Optional[str] = Field("", max_length=2000)
    phone_number: Optional[str] = Field("", max_length=100)
    assigned_number_status: Optional[str] = Field("Active & Connected", max_length=50)
    opening_time: Optional[str] = Field("09:00", max_length=10)
    closing_time: Optional[str] = Field("21:00", max_length=10)
    timezone: Optional[str] = Field("Asia/Kolkata", max_length=50)
    greeting_message: Optional[str] = Field("", max_length=2000)
    languages: Optional[List[str]] = Field(default_factory=lambda: ["English", "Hindi"])
    transfer_instructions: Optional[str] = Field("", max_length=2000)
    owner_email: Optional[str] = Field("", max_length=255)
    owner_name: Optional[str] = Field("", max_length=255)
    password: Optional[str] = Field(None, max_length=128, description="Account password")
    faqs: Optional[List[FAQItem]] = Field(default_factory=list)
    enabled_tools: Optional[Dict[str, bool]] = Field(default_factory=dict)


class BusinessLoginRequest(BaseModel):
    """Payload to log in with Gmail ID and password."""
    email: str = Field(..., min_length=3, max_length=255, description="Gmail or registered email ID")
    password: str = Field(..., min_length=1, max_length=128, description="Account password")


class BusinessUpdateRequest(BaseModel):
    """Mutable profile fields for a business tenant."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    industry: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    phone_number: Optional[str] = Field(None, max_length=50)
    opening_time: Optional[str] = Field(None, max_length=10)
    closing_time: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=50)
    greeting_message: Optional[str] = Field(None, max_length=2000)
    languages: Optional[List[str]] = None
    transfer_instructions: Optional[str] = Field(None, max_length=2000)
    owner_email: Optional[str] = Field(None, max_length=255)
    owner_name: Optional[str] = Field(None, max_length=255)
    faqs: Optional[List[FAQItem]] = None


class GoogleAuthRequest(BaseModel):
    """Payload for Google OAuth / Gmail sign in and sign up."""
    email: str = Field(..., description="Google account email address")
    name: Optional[str] = Field("", description="Google account display name")
    picture: Optional[str] = Field("", description="Google avatar image URL")
    google_id: Optional[str] = Field(None, description="Google user identifier")
    create_if_missing: Optional[bool] = Field(False, description="Whether to auto-register receptionist agent if not yet registered")
    business_name: Optional[str] = Field(None, description="Custom business name if registering")
    industry: Optional[str] = Field("Restaurant", description="Industry category")
    phone_number: Optional[str] = Field(None, description="Inbound line number")
    greeting_message: Optional[str] = Field(None, description="Custom greeting")
    enabled_tools: Optional[Dict[str, bool]] = Field(None, description="Initial tools map")


class ToolItemResponse(BaseModel):
    """Metadata and enabled status for a canonical tool."""
    id: str
    name: str
    description: str
    category: str
    icon: str
    is_enabled: bool
    allowed_industries: List[str] = Field(default_factory=lambda: ["*"])
    is_industry_compatible: bool = True


class BusinessToolsResponse(BaseModel):
    """Listing of all available tools and active statuses for a tenant."""
    business_id: str
    industry: Optional[str] = None
    tools: List[ToolItemResponse]
    enabled_tools: Dict[str, bool]
    total_available: int = 0


class ToolStatusUpdateRequest(BaseModel):
    """Payload for updating enabled/disabled tool statuses."""
    tool_statuses: Dict[str, bool] = Field(..., description="Map of {tool_id: is_enabled}")


class ToolDemandCreateRequest(BaseModel):
    """Payload to demand/request a custom tool feature for a receptionist."""
    tool_name: str = Field(..., min_length=2, max_length=100, description="Name of requested tool/integration")
    description: str = Field(..., min_length=5, max_length=2000, description="Detailed behavior requirements")
    category: Optional[str] = Field("Custom Integration", max_length=50)
    integration_target: Optional[str] = Field("Custom API", max_length=100, description="Target software/API")
    priority: Optional[str] = Field("Important", max_length=30)


class ToolDemandResponse(BaseModel):
    """Audited custom tool feature demand entry."""
    id: str
    business_id: str
    tool_name: str
    description: str
    category: str
    integration_target: str
    priority: str
    status: str
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CallRecordResponse(BaseModel):
    """Audited call history entry."""
    id: str
    business_id: str
    datetime: str
    caller_number: str
    duration: str
    duration_seconds: int
    outcome: str
    summary: str
    tools_used: List[str]
    is_simulated: bool

    model_config = ConfigDict(from_attributes=True)


class CallHistoryResponse(BaseModel):
    """Paginated call history records."""
    business_id: str
    total: int
    limit: int
    offset: int
    calls: List[CallRecordResponse]


class PlaygroundMessageRequest(BaseModel):
    """Inbound customer message to playground receptionist."""
    message: str = Field(..., min_length=1, max_length=2000, description="Caller utterance")


class PlaygroundMessageResponse(BaseModel):
    """Assistant dialogue response from LangGraph workflow."""
    business_id: str
    role: str = "assistant"
    content: str
    success: bool
    pending_action: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ActionConfirmResponse(BaseModel):
    """Result of Phase B human confirmation or cancellation."""
    success: bool
    action_id: str
    status: str
    reference_id: Optional[str] = None
    message: str
    error: Optional[str] = None
