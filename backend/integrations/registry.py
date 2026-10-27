"""
Provider Manifest and Adapter Registry.
Provides declarative catalog of all supported integration providers,
factories for creating adapter instances, and capability-to-provider mappings.
"""

from typing import Dict, Any, Optional, List, Type
import logging

from backend.integrations.base import IntegrationAdapter
from backend.integrations.models import (
    ProviderManifest,
    IntegrationCategory,
    CapabilityType,
)
from backend.integrations.adapters import (
    BuiltinDiningAdapter,
    BuiltinClinicAdapter,
    GoogleCalendarAdapter,
    OutlookCalendarAdapter,
    ExotelTelephonyAdapter,
    TwilioMessagingAdapter,
    StripePaymentsAdapter,
    HubspotCrmAdapter,
    ZendeskSupportAdapter,
    OpenTableAdapter,
    SevenRoomsAdapter,
    AcuityAdapter,
    SquareBookingsAdapter,
    ZohoCrmAdapter,
    SalesforceAdapter,
    WhatsAppCloudAdapter,
    GmailAdapter,
    FreshdeskSupportAdapter,
    RazorpayAdapter,
    BuiltinBookingAdapter,
    BuiltinKnowledgeBaseAdapter,
    BuiltinMessagingAdapter,
    SimulatedEscalationAdapter,
)

logger = logging.getLogger(__name__)


class IntegrationRegistry:
    """Central registry of provider manifests and adapter implementations."""

    def __init__(self) -> None:
        self._manifests: Dict[str, ProviderManifest] = {}
        self._adapter_classes: Dict[str, Type[IntegrationAdapter]] = {}
        self._default_providers: Dict[CapabilityType, str] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        adapters: List[Type[IntegrationAdapter]] = [
            BuiltinDiningAdapter,
            BuiltinClinicAdapter,
            GoogleCalendarAdapter,
            OutlookCalendarAdapter,
            OpenTableAdapter,
            SevenRoomsAdapter,
            AcuityAdapter,
            SquareBookingsAdapter,
            ExotelTelephonyAdapter,
            TwilioMessagingAdapter,
            StripePaymentsAdapter,
            RazorpayAdapter,
            HubspotCrmAdapter,
            ZendeskSupportAdapter,
            ZohoCrmAdapter,
            SalesforceAdapter,
            WhatsAppCloudAdapter,
            GmailAdapter,
            FreshdeskSupportAdapter,
            BuiltinBookingAdapter,
            BuiltinKnowledgeBaseAdapter,
            BuiltinMessagingAdapter,
            SimulatedEscalationAdapter,
        ]

        for adapter_cls in adapters:
            temp_instance = adapter_cls(business_id="registry_init")
            manifest = temp_instance.get_manifest()
            self.register_provider(manifest, adapter_cls)

        # Register alias for external_sevenrooms option_id used in capabilities catalog
        if "sevenrooms" in self._adapter_classes:
            self._adapter_classes["external_sevenrooms"] = self._adapter_classes["sevenrooms"]
            self._manifests["external_sevenrooms"] = self._manifests["sevenrooms"]

        # Register alias for acuity_scheduling option_id
        if "acuity" in self._adapter_classes:
            self._adapter_classes["acuity_scheduling"] = self._adapter_classes["acuity"]
            self._manifests["acuity_scheduling"] = self._manifests["acuity"]

        # Register alias for square_bookings option_id
        if "square" in self._adapter_classes:
            self._adapter_classes["square_bookings"] = self._adapter_classes["square"]
            self._manifests["square_bookings"] = self._manifests["square"]

        # Register alias for hubspot_crm option_id
        if "hubspot" in self._adapter_classes:
            self._adapter_classes["hubspot_crm"] = self._adapter_classes["hubspot"]
            self._manifests["hubspot_crm"] = self._manifests["hubspot"]

        # Register alias for zoho_crm option_id
        if "zoho" in self._adapter_classes:
            self._adapter_classes["zoho_crm"] = self._adapter_classes["zoho"]
            self._manifests["zoho_crm"] = self._manifests["zoho"]

        # Register alias for salesforce_crm option_id
        if "salesforce" in self._adapter_classes:
            self._adapter_classes["salesforce_crm"] = self._adapter_classes["salesforce"]
            self._manifests["salesforce_crm"] = self._manifests["salesforce"]

        # Register aliases for whatsapp option_id
        if "whatsapp" in self._adapter_classes:
            self._adapter_classes["whatsapp_cloud"] = self._adapter_classes["whatsapp"]
            self._manifests["whatsapp_cloud"] = self._manifests["whatsapp"]
            self._adapter_classes["whatsapp_business"] = self._adapter_classes["whatsapp"]
            self._manifests["whatsapp_business"] = self._manifests["whatsapp"]

        # Register alias for gmail option_id
        if "gmail" in self._adapter_classes:
            self._adapter_classes["google_mail"] = self._adapter_classes["gmail"]
            self._manifests["google_mail"] = self._manifests["gmail"]

        # Register alias for freshdesk option_id
        if "freshdesk" in self._adapter_classes:
            self._adapter_classes["freshdesk_support"] = self._adapter_classes["freshdesk"]
            self._manifests["freshdesk_support"] = self._manifests["freshdesk"]

        # Register alias for zendesk option_id
        if "zendesk" in self._adapter_classes:
            self._adapter_classes["zendesk_support"] = self._adapter_classes["zendesk"]
            self._manifests["zendesk_support"] = self._manifests["zendesk"]

        # Register alias for razorpay option_id
        if "razorpay" in self._adapter_classes:
            self._adapter_classes["razorpay_payments"] = self._adapter_classes["razorpay"]
            self._manifests["razorpay_payments"] = self._manifests["razorpay"]

        # Register aliases for builtin_booking option_id
        if "builtin_booking" in self._adapter_classes:
            for alias in ("builtin_resource_manager", "builtin_reservation", "builtin_hotel", "builtin_service"):
                self._adapter_classes[alias] = self._adapter_classes["builtin_booking"]
                self._manifests[alias] = self._manifests["builtin_booking"]



        # Default capability-to-provider mappings
        self._default_providers = {
            CapabilityType.CHECK_AVAILABILITY: "builtin_dining",
            CapabilityType.CREATE_BOOKING: "builtin_dining",
            CapabilityType.GET_BOOKING: "builtin_dining",
            CapabilityType.RESCHEDULE_BOOKING: "builtin_dining",
            CapabilityType.CANCEL_BOOKING: "builtin_dining",
            CapabilityType.CREATE_CALENDAR_EVENT: "google_calendar",
            CapabilityType.GET_CUSTOMER: "hubspot",
            CapabilityType.CREATE_OR_UPDATE_CUSTOMER: "hubspot",
            CapabilityType.SEND_MESSAGE: "twilio",
            CapabilityType.SEND_EMAIL: "twilio",
            CapabilityType.INITIATE_CALL: "exotel",
            CapabilityType.TRANSFER_CALL: "exotel",
            CapabilityType.GET_CALL_STATUS: "exotel",
            CapabilityType.CREATE_SUPPORT_TICKET: "zendesk",
            CapabilityType.GET_PAYMENT_STATUS: "stripe",
            CapabilityType.CREATE_PAYMENT_REQUEST: "stripe",
        }

    def register_provider(
        self,
        manifest: ProviderManifest,
        adapter_class: Type[IntegrationAdapter],
    ) -> None:
        """Register a provider manifest and corresponding adapter class."""
        self._manifests[manifest.provider_id] = manifest
        self._adapter_classes[manifest.provider_id] = adapter_class
        logger.debug("Registered integration provider: %s (%s)", manifest.provider_id, manifest.category.value)

    def get_manifest(self, provider_id: str) -> Optional[ProviderManifest]:
        """Fetch declarative manifest for provider."""
        return self._manifests.get(provider_id)

    def list_manifests(
        self,
        category: Optional[IntegrationCategory] = None,
    ) -> List[ProviderManifest]:
        """List registered provider manifests, optionally filtered by category."""
        manifests = list(self._manifests.values())
        if category:
            manifests = [m for m in manifests if m.category == category]
        return manifests

    def get_adapter_class(self, provider_id: str) -> Optional[Type[IntegrationAdapter]]:
        """Fetch adapter class for provider ID."""
        return self._adapter_classes.get(provider_id)

    def create_adapter(
        self,
        provider_id: str,
        business_id: str,
        tool_id: str = "",
        configuration: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> IntegrationAdapter:
        """Factory creating instantiated adapter for tenant."""
        cls = self.get_adapter_class(provider_id)
        if not cls:
            raise ValueError(f"Unknown provider_id '{provider_id}'")
        return cls(
            business_id=business_id,
            tool_id=tool_id,
            option_id=provider_id,
            configuration=configuration,
            credentials=credentials,
        )

    def get_default_provider(self, capability: CapabilityType) -> str:
        """Get default provider ID for a capability."""
        return self._default_providers.get(capability, "builtin_dining")


_GLOBAL_REGISTRY: Optional[IntegrationRegistry] = None


def get_integration_registry() -> IntegrationRegistry:
    """Retrieve global singleton IntegrationRegistry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = IntegrationRegistry()
    return _GLOBAL_REGISTRY
