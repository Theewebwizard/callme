"""
Integration Adapters Package.
Contains provider-specific implementations adhering to the common IntegrationAdapter interface.
"""

from backend.integrations.adapters.builtin_dining_adapter import BuiltinDiningAdapter
from backend.integrations.adapters.builtin_clinic_adapter import BuiltinClinicAdapter
from backend.integrations.adapters.google_calendar_adapter import GoogleCalendarAdapter
from backend.integrations.adapters.exotel_telephony_adapter import ExotelTelephonyAdapter
from backend.integrations.adapters.twilio_messaging_adapter import TwilioMessagingAdapter
from backend.integrations.adapters.stripe_payments_adapter import StripePaymentsAdapter
from backend.integrations.adapters.hubspot_crm_adapter import HubspotCrmAdapter
from backend.integrations.adapters.zendesk_support_adapter import ZendeskSupportAdapter
from backend.integrations.adapters.outlook_calendar_adapter import OutlookCalendarAdapter
from backend.integrations.adapters.opentable_adapter import OpenTableAdapter
from backend.integrations.adapters.sevenrooms_adapter import SevenRoomsAdapter
from backend.integrations.adapters.acuity_adapter import AcuityAdapter
from backend.integrations.adapters.square_bookings_adapter import SquareBookingsAdapter
from backend.integrations.adapters.zoho_crm_adapter import ZohoCrmAdapter
from backend.integrations.adapters.salesforce_adapter import SalesforceAdapter
from backend.integrations.adapters.whatsapp_cloud_adapter import WhatsAppCloudAdapter
from backend.integrations.adapters.gmail_adapter import GmailAdapter
from backend.integrations.adapters.builtin_booking_adapter import (
    BuiltinBookingAdapter,
    DiningTableConfig,
    HotelRoomConfig,
    ClinicRoomConfig,
    PractitionerConfig,
    ServiceStaffConfig,
    ServiceItemConfig,
)
from backend.integrations.adapters.freshdesk_support_adapter import FreshdeskSupportAdapter
from backend.integrations.adapters.razorpay_adapter import RazorpayAdapter
from backend.integrations.adapters.builtin_support_adapters import (
    BuiltinKnowledgeBaseAdapter,
    BuiltinMessagingAdapter,
    SimulatedEscalationAdapter,
    BuiltinRestaurantMenuAdapter,
    BuiltinHotelRoomsAdapter,
)

__all__ = [
    "BuiltinBookingAdapter",
    "DiningTableConfig",
    "HotelRoomConfig",
    "ClinicRoomConfig",
    "PractitionerConfig",
    "ServiceStaffConfig",
    "ServiceItemConfig",
    "BuiltinDiningAdapter",
    "BuiltinClinicAdapter",
    "BuiltinKnowledgeBaseAdapter",
    "BuiltinMessagingAdapter",
    "SimulatedEscalationAdapter",
    "BuiltinRestaurantMenuAdapter",
    "BuiltinHotelRoomsAdapter",
    "GoogleCalendarAdapter",
    "OutlookCalendarAdapter",
    "OpenTableAdapter",
    "SevenRoomsAdapter",
    "AcuityAdapter",
    "SquareBookingsAdapter",
    "ZohoCrmAdapter",
    "SalesforceAdapter",
    "WhatsAppCloudAdapter",
    "ExotelTelephonyAdapter",
    "TwilioMessagingAdapter",
    "StripePaymentsAdapter",
    "ZendeskSupportAdapter",
    "GmailAdapter",
    "FreshdeskSupportAdapter",
    "RazorpayAdapter",
]
