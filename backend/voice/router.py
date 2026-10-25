"""
Inbound Call Router and Tenant Resolution Engine.
Resolves tenant identity from dialled phone number, validates status, prevents webhook spoofing,
and instantiates isolated voice sessions.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
import logging
from pydantic import BaseModel

from backend.voice.events import InboundCallEvent, CallSession, CallControlResult
from backend.voice.interfaces import VoiceSessionManager, TelephonyProvider
from backend.voice.session_manager import DatabaseVoiceSessionManager
from backend.voice.providers import get_telephony_provider
from backend.voice.utils import mask_phone_number

if TYPE_CHECKING:
    from backend.database.service import DatabaseService

logger = logging.getLogger(__name__)


class CallRoutingError(Exception):
    """Base exception for call routing failures."""
    pass


class UnknownTenantError(CallRoutingError):
    """Raised when called phone number is not assigned to any business."""
    pass


class InactiveTenantError(CallRoutingError):
    """Raised when phone number assignment is inactive, suspended, or disconnected."""
    pass


class AmbiguousTenantError(CallRoutingError):
    """Raised when multiple businesses are mapped to the same phone number."""
    pass


class TenantMismatchError(CallRoutingError):
    """Raised when an external webhook business_id claim conflicts with the registered phone owner."""
    pass


class CallRoutingResult(BaseModel):
    """Result of successfully routing and accepting an inbound call."""
    session: CallSession
    control_result: CallControlResult
    business: Dict[str, Any]
    greeting: str


class InboundCallRouter:
    """
    Validates and routes inbound telephony calls to the correct tenant business.
    """

    def __init__(
        self,
        db_service: Optional["DatabaseService"] = None,
        session_manager: Optional[VoiceSessionManager] = None,
        telephony_provider: Optional[TelephonyProvider] = None,
    ) -> None:
        if db_service is None:
            from backend.database.service import get_database_service
            self.db = get_database_service()
        else:
            self.db = db_service
        self.session_manager = session_manager or DatabaseVoiceSessionManager(self.db)
        from backend.config import get_settings
        settings = get_settings()
        default_provider = "exotel" if settings.ENVIRONMENT == "production" else "mock"
        self.telephony_provider = telephony_provider or get_telephony_provider(default_provider)

    def route_inbound_call(
        self,
        event: InboundCallEvent,
        claimed_business_id: Optional[str] = None,
    ) -> CallRoutingResult:
        """
        Validate dialled number, resolve tenant, verify claims, and instantiate voice session.
        """
        logger.info(
            "Routing inbound call provider_id=%s from=%s to=%s (claimed_tenant=%s)",
            event.provider_call_id,
            event.masked_caller_number,
            event.masked_called_number,
            claimed_business_id,
        )

        # 1. Resolve business from called number
        try:
            biz = self.db.get_business_by_phone_number(event.called_number)
        except ValueError as e:
            logger.warning(
                "Call routing rejected: Ambiguous number %s: %s",
                event.masked_called_number,
                str(e),
            )
            self.telephony_provider.reject_call(event, reason="Ambiguous phone number assignment")
            raise AmbiguousTenantError(
                f"Called number {event.masked_called_number} is ambiguously assigned to multiple businesses."
            ) from e

        if not biz:
            logger.warning("Call routing rejected: Unknown called number %s", event.masked_called_number)
            self.telephony_provider.reject_call(event, reason="Unassigned phone number")
            raise UnknownTenantError(
                f"Called number {event.masked_called_number} is not assigned to any business tenant."
            )

        # 2. Verify external claimed_business_id against resolved business
        if claimed_business_id and claimed_business_id != biz["id"]:
            logger.warning(
                "Call routing rejected: Claimed tenant '%s' does not match owner '%s' for %s",
                claimed_business_id,
                biz["id"],
                event.masked_called_number,
            )
            self.telephony_provider.reject_call(event, reason="Tenant verification failed")
            raise TenantMismatchError(
                f"Claimed business '{claimed_business_id}' does not match registered owner for dialled number."
            )

        # 3. Verify tenant phone number status
        status = biz.get("assigned_number_status", "Active & Connected")
        if status != "Active & Connected":
            logger.warning(
                "Call routing rejected: Number %s for tenant '%s' has inactive status '%s'",
                event.masked_called_number,
                biz["id"],
                status,
            )
            self.telephony_provider.reject_call(event, reason=f"Phone number status is {status}")
            raise InactiveTenantError(
                f"Phone number for tenant '{biz['id']}' is not active (current status: '{status}')."
            )

        # 4. Accept call via provider
        greeting = (
            biz.get("greeting_message")
            or f"Hello, thank you for calling {biz['name']}! How can I assist you today?"
        )
        control_result = self.telephony_provider.accept_call(event, greeting_text=greeting)

        # 5. Create durable voice session
        session = self.session_manager.create_session(
            inbound_event=event,
            business_id=biz["id"],
        )
        control_result.session_id = session.session_id

        # 6. Record greeting turn in persistent history
        self.session_manager.record_message(
            business_id=biz["id"],
            session_id=session.session_id,
            role="assistant",
            content=greeting,
        )

        logger.info(
            "Inbound call accepted: session_id=%s assigned to tenant=%s",
            session.session_id,
            biz["id"],
        )

        return CallRoutingResult(
            session=session,
            control_result=control_result,
            business=biz,
            greeting=greeting,
        )
