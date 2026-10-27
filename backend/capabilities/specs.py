"""
Declarative capability requirements and integration option specifications for all canonical tools.
Declares required fields, permissions, authoritative source of truth, and failure policies.
"""

from typing import Dict, List, Optional
from backend.capabilities.models import (
    ToolCapabilityRequirement,
    IntegrationOption,
    SetupField,
    FieldType,
    AuthoritativeSource,
    FailureBehavior,
)


TOOL_CAPABILITY_SPECS: Dict[str, ToolCapabilityRequirement] = {
    # ---------------------------------------------------------------------------
    # 1. Dining Table Availability
    # ---------------------------------------------------------------------------
    "check_table_availability": ToolCapabilityRequirement(
        tool_id="check_table_availability",
        version="1.1.0",
        name="Check Table Availability",
        description="Inspect available dining tables for a given party size, calendar date, and clock time.",
        category="Dining & Hospitality",
        allowed_canonical_industries=["restaurant"],
        failure_behavior=FailureBehavior.FAIL_CLOSED,
        requires_confirmation=False,
        supported_options=[
            IntegrationOption(
                option_id="builtin_dining",
                name="Built-in Table & Capacity Manager",
                description="Transactional first-party table inventory manager built directly into CallMe.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="reservation_duration_minutes",
                        label="Reservation Seating Duration (Minutes)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=90,
                        description="Standard seating duration allocated per table reservation.",
                    ),
                    SetupField(
                        key="buffer_minutes",
                        label="Table Turnover Buffer (Minutes)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=15,
                        description="Cleaning and turnaround time required between consecutive reservations.",
                    ),
                    SetupField(
                        key="advance_booking_days",
                        label="Advance Booking Horizon (Days)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=30,
                        description="How many days into the future guests are permitted to reserve tables.",
                    ),
                ],
                instructions_markdown=(
                    "### Built-in Dining Table Manager\n"
                    "CallMe manages table inventory directly in your tenant database.\n\n"
                    "**Readiness Requirements:**\n"
                    "1. Configure seating duration and turnover buffer.\n"
                    "2. Add at least one active dining table under **Resource Inventory**."
                ),
            ),
            IntegrationOption(
                option_id="builtin_booking",
                name="Built-in Booking & Resource Manager",
                description="Unified multi-industry booking system supporting tables, rooms, appointment slots, and staff.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="business_type",
                        label="Business Type",
                        type=FieldType.STRING,
                        required=True,
                        default_value="restaurant",
                        description="Resource type: restaurant, hotel, clinic, service",
                    ),
                    SetupField(
                        key="timezone",
                        label="Timezone",
                        type=FieldType.STRING,
                        required=True,
                        default_value="UTC",
                        description="IANA timezone (e.g. America/New_York, UTC)",
                    ),
                ],
                instructions_markdown=(
                    "### Built-in Booking & Resource Manager\n"
                    "CallMe manages authoritative resource inventory directly in your tenant database."
                ),
            ),
            IntegrationOption(
                option_id="external_sevenrooms",
                name="SevenRooms Reservation Engine",
                description="Connect your live SevenRooms hospitality venue for real-time table inventory.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_RESERVATION,
                setup_fields=[
                    SetupField(
                        key="venue_id",
                        label="SevenRooms Venue ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. sr_venue_772910",
                        description="Unique SevenRooms Venue ID for your restaurant location.",
                    ),
                    SetupField(
                        key="api_key",
                        label="SevenRooms API Key / Access Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Bearer API token provisioned from SevenRooms Developer Portal.",
                    ),
                    SetupField(
                        key="partner_approved",
                        label="Integration Partner Program Approved",
                        type=FieldType.BOOLEAN,
                        required=False,
                        default_value=False,
                        description="Confirmation of approved SevenRooms partner or venue API agreement.",
                    ),
                    SetupField(
                        key="environment",
                        label="Regional Cluster Environment",
                        type=FieldType.SELECT,
                        required=False,
                        default_value="us_production",
                        options=[
                            {"value": "us_production", "label": "US Production (api.sevenrooms.com/2_4)"},
                            {"value": "eu_production", "label": "EU Production (api.eu.sevenrooms.com/2_4)"},
                        ],
                        description="Data residency cluster hosting the restaurant venue.",
                    ),
                ],
                required_scopes=["reservations:read", "availability:read"],
                instructions_markdown=(
                    "### SevenRooms Live Integration (REST API v2_4)\n"
                    "Connect your restaurant's SevenRooms account for real-time table availability.\n\n"
                    "**Partner Approval Prerequisite:**\n"
                    "- SevenRooms API access is partner-gated. Obtain provisioned credentials from SevenRooms Support (`api-integration-support@sevenrooms.com`).\n"
                    "- If partner access is pending, this capability displays `pending_provider_approval` and keeps live reservation execution disabled.\n"
                    "- **Built-in Alternative**: If SevenRooms external access is not available, select the **Built-in Table & Capacity Manager** (`builtin_dining`) to manage inventory directly in CallMe."
                ),
            ),
            IntegrationOption(
                option_id="opentable",
                name="OpenTable Partner Network",
                description="Live table inventory and reservations via official OpenTable Consumer API v2.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_RESERVATION_SYSTEM,
                setup_fields=[
                    SetupField(
                        key="restaurant_id",
                        label="OpenTable Restaurant ID (RID)",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. 104291",
                        description="Unique restaurant identifier in OpenTable GuestCenter.",
                    ),
                    SetupField(
                        key="partner_id",
                        label="OpenTable Partner ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. callme_reception_prod",
                        description="Approved integration partner ID provisioned by OpenTable.",
                    ),
                    SetupField(
                        key="partner_api_key",
                        label="Partner API Key / Bearer Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Consumer API v2 secret key provisioned for approved partner.",
                    ),
                    SetupField(
                        key="partner_approved",
                        label="Integration Partner Program Approved",
                        type=FieldType.BOOLEAN,
                        required=False,
                        default_value=False,
                        description="Flag confirmed upon formal OpenTable commercial agreement sign-off.",
                    ),
                    SetupField(
                        key="environment",
                        label="API Environment",
                        type=FieldType.SELECT,
                        required=False,
                        default_value="sandbox",
                        options=[
                            {"value": "sandbox", "label": "OpenTable Partner Sandbox (sandbox-api.opentable.com)"},
                            {"value": "production", "label": "Live Production Network (api.opentable.com)"},
                        ],
                        description="Sandbox certification environment vs live restaurant network.",
                    ),
                    SetupField(
                        key="default_seating_area",
                        label="Default Seating Area",
                        type=FieldType.SELECT,
                        required=False,
                        default_value="Default",
                        options=[
                            {"value": "Default", "label": "Standard Dining Room"},
                            {"value": "Outdoor", "label": "Outdoor / Patio"},
                            {"value": "Bar", "label": "Bar Seating"},
                            {"value": "Window", "label": "Window Table"},
                        ],
                        description="Default guest seating preference.",
                    ),
                ],
                required_scopes=["reservations:read"],
                instructions_markdown=(
                    "### OpenTable Partner Integration (Consumer API v2)\n"
                    "Requires an approved OpenTable Integration Partner Agreement and provisioned credentials.\n\n"
                    "**Partner Approval Prerequisite:**\n"
                    "- Our company must execute an approved commercial agreement with OpenTable Partner Network.\n"
                    "- OpenTable will provision a Partner ID and API credentials.\n"
                    "- The restaurant owner must authorize the integration in OpenTable GuestCenter.\n"
                    "- If partner access is pending, this capability displays `pending_provider_approval` and blocks live reservation operations."
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------------------
    # 2. Dining Table Booking
    # ---------------------------------------------------------------------------
    "create_table_booking": ToolCapabilityRequirement(
        tool_id="create_table_booking",
        version="1.1.0",
        name="Create Table Booking",
        description="Reserve a dining table for a guest party. Requires human-in-the-loop confirmation.",
        category="Dining & Hospitality",
        allowed_canonical_industries=["restaurant"],
        failure_behavior=FailureBehavior.FAIL_CLOSED,
        requires_confirmation=True,
        supported_options=[
            IntegrationOption(
                option_id="builtin_dining",
                name="Built-in Table & Capacity Manager",
                description="Transactional first-party reservation manager with double-booking prevention.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="auto_assign_tables",
                        label="Auto-Assign Matching Tables",
                        type=FieldType.BOOLEAN,
                        required=True,
                        default_value=True,
                        description="Automatically select best-fitting table matching party size.",
                    ),
                    SetupField(
                        key="max_party_size",
                        label="Maximum Online Party Size",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=8,
                        description="Parties exceeding this size must be escalated to staff.",
                    ),
                ],
                instructions_markdown=(
                    "### Built-in Table Booking\n"
                    "Books verified tables in your database. Employs atomic concurrency locks to prevent double-booking."
                ),
            ),
            IntegrationOption(
                option_id="builtin_booking",
                name="Built-in Booking & Resource Manager",
                description="Unified multi-industry booking system supporting tables, rooms, appointment slots, and staff.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="business_type",
                        label="Business Type",
                        type=FieldType.STRING,
                        required=True,
                        default_value="restaurant",
                        description="Resource type: restaurant, hotel, clinic, service",
                    ),
                    SetupField(
                        key="auto_assign_tables",
                        label="Auto-Assign Matching Resources",
                        type=FieldType.BOOLEAN,
                        required=False,
                        default_value=True,
                        description="Automatically select best-fitting resource matching party size.",
                    ),
                ],
                instructions_markdown=(
                    "### Built-in Booking & Resource Manager\n"
                    "Books verified resources in your database. Employs atomic concurrency locks to prevent double-booking."
                ),
            ),
            IntegrationOption(
                option_id="external_sevenrooms",
                name="SevenRooms Reservation Engine",
                description="Commit reservations directly to your SevenRooms restaurant book.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_RESERVATION,
                setup_fields=[
                    SetupField(
                        key="venue_id",
                        label="SevenRooms Venue ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. sr_venue_772910",
                        description="Unique SevenRooms Venue ID.",
                    ),
                    SetupField(
                        key="api_key",
                        label="SevenRooms API Key / Access Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Bearer API token from SevenRooms Developer Portal.",
                    ),
                    SetupField(
                        key="partner_approved",
                        label="Integration Partner Program Approved",
                        type=FieldType.BOOLEAN,
                        required=False,
                        default_value=False,
                        description="Confirmation of approved SevenRooms partner or venue API agreement.",
                    ),
                ],
                required_scopes=["reservations:write"],
                instructions_markdown=(
                    "### SevenRooms Live Booking (REST API v2_4)\n"
                    "Commits table reservations to your SevenRooms restaurant book.\n\n"
                    "**Partner Approval Prerequisite:**\n"
                    "- Live booking execution is blocked until `partner_approved` is confirmed.\n"
                    "- Employs `X-Request-Id` and `client_reference_id` idempotency tokens on every commit.\n"
                    "- **Built-in Alternative**: If SevenRooms credentials are not approved, select **Built-in Table & Capacity Manager** (`builtin_dining`) to reserve tables in CallMe."
                ),
            ),
            IntegrationOption(
                option_id="opentable",
                name="OpenTable Partner Network",
                description="Commit reservations directly to OpenTable using Consumer API v2 under partner approval.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_RESERVATION_SYSTEM,
                setup_fields=[
                    SetupField(
                        key="restaurant_id",
                        label="OpenTable Restaurant ID (RID)",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. 104291",
                        description="Unique restaurant identifier in OpenTable GuestCenter.",
                    ),
                    SetupField(
                        key="partner_id",
                        label="OpenTable Partner ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. callme_reception_prod",
                        description="Approved integration partner ID provisioned by OpenTable.",
                    ),
                    SetupField(
                        key="partner_api_key",
                        label="Partner API Key / Bearer Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Consumer API v2 secret key provisioned for approved partner.",
                    ),
                    SetupField(
                        key="partner_approved",
                        label="Integration Partner Program Approved",
                        type=FieldType.BOOLEAN,
                        required=False,
                        default_value=False,
                        description="Flag confirmed upon formal OpenTable commercial agreement sign-off.",
                    ),
                ],
                required_scopes=["reservations:write"],
                instructions_markdown=(
                    "### OpenTable Partner Booking (Consumer API v2)\n"
                    "Commits table reservations to OpenTable GuestCenter.\n\n"
                    "**Partner Approval Prerequisite:**\n"
                    "- Live booking execution is blocked until `partner_approved` is confirmed.\n"
                    "- Employs `X-OT-Request-Id` idempotency tokens on every commit."
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------------------
    # 3. Healthcare / Clinic Appointment Availability
    # ---------------------------------------------------------------------------
    "check_appointment_availability": ToolCapabilityRequirement(
        tool_id="check_appointment_availability",
        version="1.1.0",
        name="Check Appointment Availability",
        description="Inspect available practitioner or clinic consultation openings.",
        category="Healthcare & Services",
        allowed_canonical_industries=["clinic", "services"],
        failure_behavior=FailureBehavior.FAIL_CLOSED,
        requires_confirmation=False,
        supported_options=[
            IntegrationOption(
                option_id="builtin_clinic",
                name="Built-in Clinical Appointment Scheduler",
                description="Transactional appointment scheduling managing clinical rooms and practitioner slots.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="appointment_duration_minutes",
                        label="Consultation Duration (Minutes)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=30,
                        description="Standard appointment duration per patient consultation.",
                    ),
                    SetupField(
                        key="buffer_minutes",
                        label="Sanitization Buffer (Minutes)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=10,
                        description="Buffer between appointments for clinical disinfection.",
                    ),
                ],
                instructions_markdown=(
                    "### Built-in Clinical Scheduler\n"
                    "Manage appointments using CallMe's internal clinical scheduling engine."
                ),
            ),
            IntegrationOption(
                option_id="google_calendar",
                name="Google Calendar Clinical Scheduling",
                description="Sync appointment availability with your clinic's Google Calendar.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="calendar_id",
                        label="Google Calendar ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. primary or clinic@example.com",
                        description="The email address or identifier of the Google Calendar to manage.",
                    ),
                    SetupField(
                        key="service_account_json",
                        label="Google Service Account JSON Key",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="JSON credential file downloaded from Google Cloud Console.",
                    ),
                    SetupField(
                        key="slot_duration_minutes",
                        label="Appointment Slot Length (Minutes)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=30,
                        description="Length of each bookable appointment window.",
                    ),
                ],
                required_scopes=["https://www.googleapis.com/auth/calendar"],
                instructions_markdown=(
                    "### Google Calendar Integration\n"
                    "Connect Google Calendar for clinical appointments.\n\n"
                    "1. Create a Service Account in Google Cloud Console.\n"
                    "2. Share your target calendar with the service account client email.\n"
                    "3. Paste the Service Account JSON key below."
                ),
            ),
            IntegrationOption(
                option_id="outlook_calendar",
                name="Microsoft 365 / Outlook Calendar",
                description="Connect Microsoft Graph v1.0 for real-time Outlook calendar availability and event scheduling.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="access_token",
                        label="OAuth Access Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Microsoft Graph v1.0 access token.",
                    ),
                    SetupField(
                        key="calendar_id",
                        label="Authoritative Calendar ID",
                        type=FieldType.STRING,
                        required=False,
                        default_value="primary",
                        description="Target Outlook calendar ID (defaults to primary).",
                    ),
                    SetupField(
                        key="account_type",
                        label="Account Type",
                        type=FieldType.SELECT,
                        required=False,
                        default_value="work_school",
                        options=[
                            {"value": "work_school", "label": "Work or School Account (Microsoft 365)"},
                            {"value": "personal", "label": "Personal Account (Outlook.com)"},
                        ],
                        description="Select work_school (Entra ID) or personal (Outlook.com).",
                    ),

                ],
                required_scopes=["Calendars.Read", "Calendars.ReadWrite"],
                instructions_markdown=(
                    "### Microsoft 365 / Outlook Calendar Integration\n"
                    "Connect via Microsoft Entra ID and Microsoft Graph v1.0.\n\n"
                    "1. Register app in Microsoft Entra ID with least-privilege delegated `Calendars.Read` or `Calendars.ReadWrite` permissions.\n"
                    "2. Authenticate and provide access token.\n"
                    "3. Select target authoritative calendar."
                ),
            ),
            IntegrationOption(
                option_id="acuity",
                name="Acuity Scheduling",
                description="Live consultation availability from Acuity Scheduling API v1.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="user_id",
                        label="Acuity User ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. 19283746",
                        description="Numeric user identifier found in Acuity Integrations > API settings.",
                    ),
                    SetupField(
                        key="api_key",
                        label="Acuity API Key",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="API Key generated in Acuity Integrations > API settings.",
                    ),
                    SetupField(
                        key="calendar_id",
                        label="Authoritative Calendar ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. 482910",
                        description="Specific practitioner or room calendar to manage.",
                    ),
                    SetupField(
                        key="appointment_type_id",
                        label="Default Appointment Type ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. 1029384",
                        description="Default service or consultation appointment type.",
                    ),
                ],
                required_scopes=["api-v1"],
                instructions_markdown=(
                    "### Acuity Scheduling Integration\n"
                    "Connect your Acuity Scheduling account.\n\n"
                    "1. Navigate to **Integrations > API** in your Acuity dashboard.\n"
                    "2. Copy your numeric **User ID** and generate an **API Key**.\n"
                    "3. Configure your target calendar and appointment type."
                ),
            ),
            IntegrationOption(
                option_id="square",
                name="Square Bookings",
                description="Live appointment availability from Square Bookings & Appointments API.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="access_token",
                        label="Square OAuth Access Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="OAuth access token with Appointments, Customers, and Catalog permissions.",
                    ),
                    SetupField(
                        key="location_id",
                        label="Square Location ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. L9XYZ123456",
                        description="Authoritative business location ID.",
                    ),
                    SetupField(
                        key="service_variation_id",
                        label="Default Service Variation ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. VAR_1029384",
                        description="Catalog item variation ID representing the service.",
                    ),
                    SetupField(
                        key="team_member_id",
                        label="Default Team Member ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. TM_482910",
                        description="Preferred practitioner or staff member ID.",
                    ),
                    SetupField(
                        key="environment",
                        label="Square Environment",
                        type=FieldType.SELECT,
                        required=False,
                        default_value="production",
                        options=[
                            {"value": "production", "label": "Production (connect.squareup.com)"},
                            {"value": "sandbox", "label": "Sandbox (connect.squareupsandbox.com)"},
                        ],
                        description="Target Square environment (Production vs Sandbox).",
                    ),
                ],
                required_scopes=[
                    "APPOINTMENTS_READ",
                    "APPOINTMENTS_WRITE",
                    "APPOINTMENTS_BUSINESS_SETTINGS_READ",
                    "MERCHANT_PROFILE_READ",
                    "CUSTOMERS_READ",
                    "CUSTOMERS_WRITE",
                    "ITEMS_READ",
                ],
                instructions_markdown=(
                    "### Square Bookings Integration\n"
                    "Connect your Square Appointments account.\n\n"
                    "1. Connect via OAuth or provide your Square OAuth Access Token.\n"
                    "2. Select your business location, service variation, and team member.\n"
                    "3. Ensure your Appointments online booking settings are enabled."
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------------------
    # 4. Healthcare / Clinic Create Appointment
    # ---------------------------------------------------------------------------
    "create_appointment": ToolCapabilityRequirement(
        tool_id="create_appointment",
        version="1.1.0",
        name="Create Appointment",
        description="Book a verified clinic or consultation appointment. Requires confirmation.",
        category="Healthcare & Services",
        allowed_canonical_industries=["clinic", "services"],
        failure_behavior=FailureBehavior.FAIL_CLOSED,
        requires_confirmation=True,
        supported_options=[
            IntegrationOption(
                option_id="builtin_clinic",
                name="Built-in Clinical Appointment Scheduler",
                description="Commit verified appointments to local clinical calendar.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="confirmation_sms_template",
                        label="SMS Confirmation Notice",
                        type=FieldType.STRING,
                        required=False,
                        description="Text template sent to patient upon appointment confirmation.",
                    ),
                ],
                instructions_markdown="Commits patient appointments directly to the clinic's database calendar.",
            ),
            IntegrationOption(
                option_id="google_calendar",
                name="Google Calendar Clinical Scheduling",
                description="Create verified events on your clinic's Google Calendar.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="calendar_id",
                        label="Google Calendar ID",
                        type=FieldType.STRING,
                        required=True,
                        description="Calendar ID.",
                    ),
                    SetupField(
                        key="service_account_json",
                        label="Service Account JSON",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Service Account JSON credentials.",
                    ),
                ],
                required_scopes=["https://www.googleapis.com/auth/calendar.events"],
                instructions_markdown="Creates calendar events with patient details and phone number.",
            ),
            IntegrationOption(
                option_id="outlook_calendar",
                name="Microsoft 365 / Outlook Calendar",
                description="Create verified events on your clinic's Microsoft 365 / Outlook Calendar.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="access_token",
                        label="OAuth Access Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="Microsoft Graph v1.0 access token.",
                    ),
                    SetupField(
                        key="calendar_id",
                        label="Authoritative Calendar ID",
                        type=FieldType.STRING,
                        required=False,
                        default_value="primary",
                        description="Target Outlook calendar ID.",
                    ),
                ],
                required_scopes=["Calendars.ReadWrite"],
                instructions_markdown="Creates calendar events on Microsoft 365 with patient details.",
            ),
            IntegrationOption(
                option_id="acuity",
                name="Acuity Scheduling",
                description="Commit verified appointments directly to Acuity Scheduling.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="user_id",
                        label="Acuity User ID",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="e.g. 19283746",
                        description="Numeric user identifier from Acuity Integrations > API settings.",
                    ),
                    SetupField(
                        key="api_key",
                        label="Acuity API Key",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="API Key generated in Acuity Integrations > API settings.",
                    ),
                    SetupField(
                        key="calendar_id",
                        label="Calendar ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. 482910",
                        description="Target Acuity calendar ID.",
                    ),
                    SetupField(
                        key="appointment_type_id",
                        label="Appointment Type ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. 1029384",
                        description="Target service appointment type ID.",
                    ),
                ],
                required_scopes=["api-v1"],
                instructions_markdown="Commits verified appointments directly to your Acuity Scheduling account.",
            ),
            IntegrationOption(
                option_id="square",
                name="Square Bookings",
                description="Commit verified appointments directly to Square Appointments API.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.EXTERNAL_CALENDAR,
                setup_fields=[
                    SetupField(
                        key="access_token",
                        label="Square OAuth Access Token",
                        type=FieldType.PASSWORD,
                        required=True,
                        secret=True,
                        description="OAuth access token with Appointments, Customers, and Catalog write permissions.",
                    ),
                    SetupField(
                        key="location_id",
                        label="Location ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. L9XYZ123456",
                        description="Authoritative business location ID.",
                    ),
                    SetupField(
                        key="service_variation_id",
                        label="Service Variation ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. VAR_1029384",
                        description="Catalog item variation ID representing the service.",
                    ),
                    SetupField(
                        key="team_member_id",
                        label="Team Member ID",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="e.g. TM_482910",
                        description="Preferred practitioner or staff member ID.",
                    ),
                    SetupField(
                        key="environment",
                        label="Square Environment",
                        type=FieldType.SELECT,
                        required=False,
                        default_value="production",
                        options=[
                            {"value": "production", "label": "Production (connect.squareup.com)"},
                            {"value": "sandbox", "label": "Sandbox (connect.squareupsandbox.com)"},
                        ],
                        description="Target Square environment (Production vs Sandbox).",
                    ),
                ],
                required_scopes=[
                    "APPOINTMENTS_READ",
                    "APPOINTMENTS_WRITE",
                    "APPOINTMENTS_BUSINESS_SETTINGS_READ",
                    "MERCHANT_PROFILE_READ",
                    "CUSTOMERS_READ",
                    "CUSTOMERS_WRITE",
                    "ITEMS_READ",
                ],
                instructions_markdown="Commits verified appointments directly to your Square Appointments account with version conflict protection.",
            ),
        ],
    ),

    # ---------------------------------------------------------------------------
    # 5. Message Intake
    # ---------------------------------------------------------------------------
    "take_message": ToolCapabilityRequirement(
        tool_id="take_message",
        version="1.1.0",
        name="Take Caller Message",
        description="Record a caller's message and contact details for staff follow-up.",
        category="Communication",
        allowed_canonical_industries=["*"],
        failure_behavior=FailureBehavior.DEGRADED_RESPONSE,
        requires_confirmation=False,
        supported_options=[
            IntegrationOption(
                option_id="builtin_messaging",
                name="Transactional Message Store",
                description="Persist caller messages directly into CallMe's staff review store.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.COMMUNICATION_SERVICE,
                setup_fields=[
                    SetupField(
                        key="urgent_notification_email",
                        label="Urgent Notification Email",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="manager@example.com",
                        description="Email address notified when callers flag an urgent matter.",
                    ),
                    SetupField(
                        key="urgent_notification_phone",
                        label="Urgent Alert SMS / WhatsApp",
                        type=FieldType.STRING,
                        required=False,
                        placeholder="+91 98000 00000",
                        description="Mobile phone number for urgent SMS alerts.",
                    ),
                ],
                instructions_markdown=(
                    "### Message Intake\n"
                    "Captures caller messages and callback requests in database records."
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------------------
    # 6. Call Transfer & Human Escalation
    # ---------------------------------------------------------------------------
    "transfer_call": ToolCapabilityRequirement(
        tool_id="transfer_call",
        version="1.1.0",
        name="Transfer Call",
        description="Initiate live call transfer or escalation to a human staff member.",
        category="Communication",
        allowed_canonical_industries=["*"],
        failure_behavior=FailureBehavior.FAIL_CLOSED,
        requires_confirmation=False,
        supported_options=[
            IntegrationOption(
                option_id="exotel_telephony_transfer",
                name="Exotel Telephony Transfer Bridge",
                description="Live SIP telephony bridging to transfer callers to staff phones.",
                is_built_in=False,
                requires_external_connection=True,
                authoritative_source=AuthoritativeSource.TELEPHONY_PROVIDER,
                setup_fields=[
                    SetupField(
                        key="destination_number",
                        label="Destination Transfer Number",
                        type=FieldType.STRING,
                        required=True,
                        placeholder="+91 80 4123 5678",
                        description="E.164 phone number where calls will be bridged.",
                    ),
                    SetupField(
                        key="transfer_timeout_seconds",
                        label="Transfer Timeout (Seconds)",
                        type=FieldType.INTEGER,
                        required=True,
                        default_value=30,
                        description="Maximum seconds to ring staff line before fallback.",
                    ),
                ],
                instructions_markdown=(
                    "### Live Telephony Transfer\n"
                    "Routes callers over Exotel telephony bridges to your duty manager phone line."
                ),
            ),
            IntegrationOption(
                option_id="simulated_escalation",
                name="Development Simulation / Escalation Logging",
                description="Record escalation intent in development without placing live outbound phone calls.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.COMMUNICATION_SERVICE,
                setup_fields=[],
                instructions_markdown="Safe development mode that logs escalation requests truthfully.",
            ),
        ],
    ),

    # ---------------------------------------------------------------------------
    # 7. Answer Business FAQs
    # ---------------------------------------------------------------------------
    "answer_faq": ToolCapabilityRequirement(
        tool_id="answer_faq",
        version="1.1.0",
        name="Answer Business FAQs",
        description="Search business knowledge base and provide factual answers to customer questions.",
        category="Information",
        allowed_canonical_industries=["*"],
        failure_behavior=FailureBehavior.DEGRADED_RESPONSE,
        requires_confirmation=False,
        supported_options=[
            IntegrationOption(
                option_id="builtin_knowledge_base",
                name="Tenant Knowledge Base & FAQ Store",
                description="Lexical multi-candidate FAQ retrieval grounded in business settings.",
                is_built_in=True,
                requires_external_connection=False,
                authoritative_source=AuthoritativeSource.BUILTIN_DATABASE,
                setup_fields=[
                    SetupField(
                        key="strict_business_hours_only",
                        label="Strict Operating Hours Answering",
                        type=FieldType.BOOLEAN,
                        required=False,
                        default_value=False,
                        description="Only answer FAQs during tenant operating hours.",
                    ),
                ],
                instructions_markdown=(
                    "### Knowledge Base FAQs\n"
                    "Answers customer inquiries using verified FAQs configured under Knowledge Base."
                ),
            ),
        ],
    ),
}


def get_capability_spec(tool_id: str) -> Optional[ToolCapabilityRequirement]:
    """Retrieve capability requirements specification for a canonical tool."""
    return TOOL_CAPABILITY_SPECS.get(tool_id)


def list_all_capability_specs() -> List[ToolCapabilityRequirement]:
    """List all registered capability specifications."""
    return list(TOOL_CAPABILITY_SPECS.values())
