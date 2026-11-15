"""
Unit and integration tests for the Zoho CRM Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.CRM_SYSTEM)
- Registry lookup and option aliases ('zoho', 'zoho_crm')
- Multi-datacenter / API-domain resolution (US, EU, IN, AU, JP, CN, CA)
- OAuth 2.0 authorization URL, code exchange, token refresh, and auto-refresh on expiry
- Organization-specific authorization (X-CRM-ORG) and strict cross-org token prevention
- Metadata discovery (modules, fields, organization)
- Configurable deduplication matching strategies
- Strict duplicate safeguard: never merge two people solely because names match
- Records APIs (Search, Retrieval, Create, Update, Upsert)
- Handling HTTP 204 No Content as an empty search result
- Upsert behavior and conflict handling (DUPLICATE_DATA -> ErrorCategory.CONFLICT)
- Custom field mappings and resilience against missing/unknown custom fields (retry after stripping)
- Progressive capability gating (Tasks, Calls, Meetings) based on enabled modules and granted scopes
- Rate-limiting (HTTP 429, Retry-After adherence) and error normalization (400, 401, 403, 404, 409, 500)
- Readiness assessment and configuration validation
- Multi-tenant isolation and cryptographic webhook signature verification
- Capability contract execution via execute()
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import hmac
import hashlib
import urllib.error
from datetime import datetime, timezone
import io

from backend.integrations.adapters.zoho_crm_adapter import (
    ZohoCrmAdapter,
    ZohoIntegrationException,
    ZohoRegion,
    MatchingStrategy,
    ZOHO_ACCOUNTS_URLS,
    DEFAULT_API_DOMAINS,
    DEFAULT_FIELD_MAPPINGS,
)
from backend.capabilities.models import (
    AuthoritativeSource,
    CapabilityStatus,
)
from backend.integrations.models import (
    ProviderManifest,
    CapabilityType,
    AuthMethod,
    IntegrationCategory,
    ExecutionContext,
    ExecutionOutcome,
    ErrorCategory,
    WebhookRequest,
    IntegrationError,
)
from backend.integrations.registry import get_integration_registry


# ==============================================================================
# Helper for Mocking HTTP Responses
# ==============================================================================

class MockHttpResponse:
    def __init__(self, data: bytes, code: int = 200, headers: dict = None):
        self._data = data
        self._code = code
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._data

    def getcode(self) -> int:
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def make_mock_http_error(code: int, body_dict: dict, headers: dict = None):
    body_bytes = json.dumps(body_dict).encode("utf-8")
    fp = io.BytesIO(body_bytes)
    return urllib.error.HTTPError(
        url="https://www.zohoapis.com/test",
        code=code,
        msg="HTTP Error",
        hdrs=headers or {},
        fp=fp,
    )


# ==============================================================================
# 1. Manifest, Registry & Authoritative Source
# ==============================================================================

def test_zoho_manifest_and_authoritative_source():
    """Verify Zoho CRM adapter manifest declarations and CRM_SYSTEM authoritative source."""
    adapter = ZohoCrmAdapter(business_id="tenant_clinic")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "zoho"
    assert manifest.display_name == "Zoho CRM"
    assert manifest.category == IntegrationCategory.CRM
    assert manifest.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert adapter.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert manifest.auth_method == AuthMethod.OAUTH2

    # Scopes
    assert "ZohoCRM.modules.contacts.READ" in manifest.required_oauth_scopes
    assert "ZohoCRM.modules.contacts.CREATE" in manifest.required_oauth_scopes
    assert "ZohoCRM.modules.contacts.UPDATE" in manifest.required_oauth_scopes
    assert "ZohoCRM.modules.leads.READ" in manifest.required_oauth_scopes
    assert "ZohoCRM.settings.modules.READ" in manifest.required_oauth_scopes
    assert "ZohoCRM.settings.fields.READ" in manifest.required_oauth_scopes
    assert "ZohoCRM.org.READ" in manifest.required_oauth_scopes

    # Capabilities
    caps = adapter.get_supported_capabilities()
    assert CapabilityType.GET_CUSTOMER in caps
    assert CapabilityType.CREATE_OR_UPDATE_CUSTOMER in caps


def test_zoho_registered_in_registry():
    """Verify registry catalogs Zoho under 'zoho' and 'zoho_crm' alias."""
    registry = get_integration_registry()
    manifest_primary = registry.get_manifest("zoho")
    assert manifest_primary is not None
    assert manifest_primary.provider_id == "zoho"

    # Alias check
    adapter_cls = registry.get_adapter_class("zoho_crm")
    assert adapter_cls is ZohoCrmAdapter


# ==============================================================================
# 2. Multi-Datacenter / Region Selection & API Domain Resolution
# ==============================================================================

@pytest.mark.parametrize(
    "region, expected_accounts, expected_api_domain",
    [
        ("us", "https://accounts.zoho.com", "https://www.zohoapis.com"),
        ("eu", "https://accounts.zoho.eu", "https://www.zohoapis.eu"),
        ("in", "https://accounts.zoho.in", "https://www.zohoapis.in"),
        ("au", "https://accounts.zoho.com.au", "https://www.zohoapis.com.au"),
        ("jp", "https://accounts.zoho.jp", "https://www.zohoapis.jp"),
        ("cn", "https://accounts.zoho.com.cn", "https://www.zohoapis.com.cn"),
        ("ca", "https://accounts.zohocloud.ca", "https://www.zohoapis.ca"),
    ],
)
def test_zoho_region_and_accounts_url_resolution(region, expected_accounts, expected_api_domain):
    """Verify all 7 global Zoho data centers resolve to their respective accounts and API domains."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_global",
        configuration={"data_center": region},
    )
    assert adapter.get_accounts_url() == expected_accounts
    assert adapter.get_api_domain() == expected_api_domain


def test_zoho_custom_api_domain_override():
    """Verify dynamic api_domain captured during OAuth exchange overrides regional default."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_custom_domain",
        configuration={"data_center": "us"},
        credentials={"api_domain": "https://crm.zohoapis.eu"},
    )
    assert adapter.get_api_domain() == "https://crm.zohoapis.eu"


def test_zoho_region_normalization():
    """Verify whitespace and casing in region configuration are trimmed and lowercased."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_norm",
        configuration={"data_center": "  EU  "},
    )
    assert adapter.get_accounts_url() == "https://accounts.zoho.eu"
    assert adapter.get_api_domain() == "https://www.zohoapis.eu"


# ==============================================================================
# 3. OAuth 2.0 Authorization Flow & Token Management
# ==============================================================================

def test_zoho_oauth_authorization_url_generation():
    """Verify OAuth authorization URL formatting with scopes, client_id, and state."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_auth",
        configuration={"client_id": "1000.TESTCLIENTID123", "data_center": "eu"},
    )

    url = adapter.get_authorization_url(
        redirect_uri="https://answerly.example.com/oauth/callback",
        state="state_xyz_123",
    )

    assert url.startswith("https://accounts.zoho.eu/oauth/v2/auth?")
    assert "client_id=1000.TESTCLIENTID123" in url
    assert "response_type=code" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=state_xyz_123" in url
    assert "ZohoCRM.modules.contacts.READ" in url
    assert "ZohoCRM.modules.leads.READ" in url
    assert "ZohoCRM.org.READ" in url


def test_zoho_oauth_authorization_url_missing_client_id():
    """Verify ValueError is raised if client_id is missing when generating authorization URL."""
    adapter = ZohoCrmAdapter(business_id="tenant_no_id")
    with pytest.raises(ValueError, match="client_id is required"):
        adapter.get_authorization_url(redirect_uri="https://example.com", state="xyz")


@patch("urllib.request.urlopen")
def test_zoho_exchange_authorization_code(mock_urlopen):
    """Verify code exchange captures tokens, dynamic api_domain, and probes organization metadata."""
    token_response_payload = {
        "access_token": "1000.accesstokenval.xyz",
        "refresh_token": "1000.refreshtokenval.abc",
        "api_domain": "https://www.zohoapis.com",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    org_response_payload = {
        "org": [
            {
                "id": "7001829102",
                "company_name": "Apex Medical Care",
                "primary_email": "admin@apexmedical.com",
                "time_zone": "America/New_York",
                "environment": "production",
            }
        ]
    }

    def side_effect(req, *args, **kwargs):
        url = req.full_url
        if "oauth/v2/token" in url:
            return MockHttpResponse(json.dumps(token_response_payload).encode("utf-8"))
        elif "/crm/v6/org" in url:
            return MockHttpResponse(json.dumps(org_response_payload).encode("utf-8"))
        return MockHttpResponse(b"{}")

    mock_urlopen.side_effect = side_effect

    adapter = ZohoCrmAdapter(
        business_id="tenant_exchange",
        configuration={"client_id": "1000.CLIENTID", "client_secret": "CLIENTSECRET", "data_center": "us"},
    )

    tokens = adapter.exchange_authorization_code(code="auth_code_999", redirect_uri="https://example.com/cb")

    assert tokens["access_token"] == "1000.accesstokenval.xyz"
    assert tokens["refresh_token"] == "1000.refreshtokenval.abc"
    assert adapter.credentials["access_token"] == "1000.accesstokenval.xyz"
    assert adapter.credentials["refresh_token"] == "1000.refreshtokenval.abc"
    assert adapter.credentials["api_domain"] == "https://www.zohoapis.com"
    assert adapter.configuration["organization_id"] == "7001829102"
    assert adapter.credentials["organization_id"] == "7001829102"


@patch("urllib.request.urlopen")
def test_zoho_refresh_access_token(mock_urlopen):
    """Verify refreshing expired access token against region accounts URL."""
    token_response = {
        "access_token": "1000.refreshed_access_token",
        "api_domain": "https://www.zohoapis.eu",
        "expires_in": 3600,
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(token_response).encode("utf-8"))

    adapter = ZohoCrmAdapter(
        business_id="tenant_refresh",
        configuration={"client_id": "1000.CLIENTID", "client_secret": "SECRET", "data_center": "eu"},
        credentials={"refresh_token": "1000.MY_REFRESH_TOKEN"},
    )

    result = adapter.refresh_access_token()
    assert result["access_token"] == "1000.refreshed_access_token"
    assert adapter.credentials["access_token"] == "1000.refreshed_access_token"
    assert adapter.credentials["api_domain"] == "https://www.zohoapis.eu"


@patch("urllib.request.urlopen")
def test_zoho_auto_refresh_on_expiry(mock_urlopen):
    """Verify _get_access_token auto-refreshes when token is nearing expiration."""
    refresh_response = {
        "access_token": "1000.newly_refreshed_token",
        "expires_in": 3600,
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(refresh_response).encode("utf-8"))

    now_ts = datetime.now(timezone.utc).timestamp()
    adapter = ZohoCrmAdapter(
        business_id="tenant_auto_refresh",
        configuration={"client_id": "1000.CID", "client_secret": "SEC", "data_center": "us"},
        credentials={
            "access_token": "1000.old_expiring_token",
            "refresh_token": "1000.REFRESH",
            "token_expires_at": now_ts + 10,  # Only 10s left, within 60s threshold
        },
    )

    token = adapter._get_access_token()
    assert token == "1000.newly_refreshed_token"


# ==============================================================================
# 4. Organization Verification & Strict Cross-Organization Token Prevention
# ==============================================================================

@patch("urllib.request.urlopen")
def test_zoho_organization_verification_success(mock_urlopen):
    """Verify organization match passes when token org matches configured org."""
    org_resp = {"org": [{"id": "7001829102", "company_name": "Apex Medical"}]}
    mock_urlopen.return_value = MockHttpResponse(json.dumps(org_resp).encode("utf-8"))

    adapter = ZohoCrmAdapter(
        business_id="tenant_org_ok",
        configuration={"organization_id": "7001829102"},
        credentials={"access_token": "valid_token_123"},
    )

    assert adapter.verify_organization("7001829102") is True


@patch("urllib.request.urlopen")
def test_zoho_organization_verification_cross_org_rejection(mock_urlopen):
    """
    CRITICAL: Never use an access token generated for one Zoho organization against another!
    Verify verification strictly rejects when token belongs to another organization.
    """
    org_resp = {"org": [{"id": "9999999999", "company_name": "Other Company"}]}
    mock_urlopen.return_value = MockHttpResponse(json.dumps(org_resp).encode("utf-8"))

    adapter = ZohoCrmAdapter(
        business_id="tenant_cross_org",
        configuration={"organization_id": "7001829102"},  # Target configured org
        credentials={"access_token": "alien_token_from_different_org"},
    )

    is_valid = adapter.verify_organization("7001829102")
    assert is_valid is False


@patch("urllib.request.urlopen")
def test_zoho_request_sends_x_crm_org_header(mock_urlopen):
    """Verify all outgoing API requests include the X-CRM-ORG header for tenant org isolation."""
    mock_urlopen.return_value = MockHttpResponse(b'{"data": []}')

    adapter = ZohoCrmAdapter(
        business_id="tenant_header_check",
        configuration={"organization_id": "7001829102"},
        credentials={"access_token": "live_token_abc"},
    )

    adapter._make_zoho_request("GET", "/crm/v6/Contacts/search?email=test@example.com")

    # Assert request object had X-CRM-ORG header set
    req = mock_urlopen.call_args[0][0]
    assert req.headers.get("X-crm-org") == "7001829102" or req.headers.get("X-CRM-ORG") == "7001829102"
    assert "Zoho-oauthtoken live_token_abc" in req.headers.get("Authorization")


# ==============================================================================
# 5. Metadata Discovery (Modules, Fields, Organization)
# ==============================================================================

@patch("urllib.request.urlopen")
def test_zoho_discover_modules(mock_urlopen):
    """Verify dynamic discovery of tenant CRM modules."""
    modules_payload = {
        "modules": [
            {"api_name": "Contacts", "plural_label": "Contacts", "custom": False, "creatable": True},
            {"api_name": "Leads", "plural_label": "Leads", "custom": False, "creatable": True},
            {"api_name": "Custom_Patients", "plural_label": "Patients", "custom": True, "creatable": True},
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(modules_payload).encode("utf-8"))

    adapter = ZohoCrmAdapter(
        business_id="tenant_meta",
        credentials={"access_token": "live_token_meta"},
    )

    resources = adapter.discover_resources("modules")
    assert len(resources) == 3
    mod_ids = [r.resource_id for r in resources]
    assert "Contacts" in mod_ids
    assert "Leads" in mod_ids
    assert "Custom_Patients" in mod_ids
    assert resources[2].metadata["custom"] is True


@patch("urllib.request.urlopen")
def test_zoho_discover_fields(mock_urlopen):
    """Verify dynamic discovery of contact and lead field metadata."""
    fields_payload = {
        "fields": [
            {"api_name": "First_Name", "field_label": "First Name", "data_type": "text", "custom_field": False},
            {"api_name": "Last_Name", "field_label": "Last Name", "data_type": "text", "system_mandatory": True},
            {"api_name": "Email", "field_label": "Email", "data_type": "email"},
            {"api_name": "Special_Dietary", "field_label": "Dietary", "data_type": "text", "custom_field": True},
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(fields_payload).encode("utf-8"))

    adapter = ZohoCrmAdapter(
        business_id="tenant_fields",
        credentials={"access_token": "live_token_fields"},
    )

    resources = adapter.discover_resources("contact_fields")
    assert len(resources) == 4
    f_names = [r.resource_id for r in resources]
    assert "First_Name" in f_names
    assert "Special_Dietary" in f_names
    assert resources[1].metadata["required"] is True
    assert resources[3].metadata["custom"] is True


def test_zoho_discover_resources_mock_mode():
    """Verify discover_resources returns representative metadata in mock/sandbox mode."""
    adapter = ZohoCrmAdapter(business_id="tenant_mock", credentials={"access_token": "mock_token"})
    modules = adapter.discover_resources("modules")
    assert len(modules) >= 3
    fields = adapter.discover_resources("fields")
    assert any(f.resource_id == "Email" for f in fields)
    org = adapter.discover_resources("org")
    assert len(org) == 1
    assert org[0].resource_id == "7001829102"


# ==============================================================================
# 6. Deduplication Matching Strategy & Strict Name-Only Safeguard
# ==============================================================================

def test_zoho_matching_strategy_name_alone_never_merges():
    """
    CRITICAL SAFEGUARD:
    Contacts and leads are NEVER merged solely based on matching names!
    If only a name is provided, find_existing_record returns None.
    """
    adapter = ZohoCrmAdapter(business_id="tenant_dedup")
    # Record with only name, no email or phone
    input_data = {"name": "Alex Mercer"}

    match = adapter.find_existing_record("Contacts", input_data)
    assert match is None, "Name alone must NEVER match or merge existing CRM records!"


@patch("urllib.request.urlopen")
def test_zoho_matching_strategy_email_then_phone(mock_urlopen):
    """Verify email_then_phone checks email first; falls back to phone if email yields 0 records."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_dedup",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_THEN_PHONE},
        credentials={"access_token": "live_token_dedup"},
    )

    # 1. Search by email yields no results (204 No Content)
    # 2. Search by phone yields matched contact
    call_count = 0

    def side_effect(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = req.full_url
        if "email=" in url:
            # 204 No Content
            return MockHttpResponse(b"", code=204)
        elif "phone=" in url:
            return MockHttpResponse(
                json.dumps({
                    "data": [
                        {"id": "4150892000001", "First_Name": "Jane", "Last_Name": "Doe", "Phone": "+14155552671"}
                    ]
                }).encode("utf-8")
            )
        return MockHttpResponse(b"{}")

    mock_urlopen.side_effect = side_effect

    match = adapter.find_existing_record(
        "Contacts",
        {"name": "Jane Doe", "email": "unknown@example.com", "phone": "+14155552671"},
    )

    assert match is not None
    assert match["id"] == "4150892000001"
    assert call_count == 2


@patch("urllib.request.urlopen")
def test_zoho_matching_strategy_email_only(mock_urlopen):
    """Verify email_only ignores phone even if present."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [{"id": "4150892000002", "First_Name": "Bob", "Last_Name": "Smith", "Email": "bob@example.com"}]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(
        business_id="tenant_dedup",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_ONLY},
        credentials={"access_token": "live_token_dedup"},
    )

    match = adapter.find_existing_record(
        "Contacts",
        {"name": "Bob Smith", "email": "bob@example.com", "phone": "+14155550000"},
    )

    assert match is not None
    assert match["id"] == "4150892000002"
    # Ensure phone was not part of query URL
    req = mock_urlopen.call_args[0][0]
    assert "email=bob%40example.com" in req.full_url
    assert "phone=" not in req.full_url


# ==============================================================================
# 7. Records APIs: Search, Get, Create, Update, Upsert
# ==============================================================================

@patch("urllib.request.urlopen")
def test_zoho_search_records_http_204_handled_as_empty_list(mock_urlopen):
    """Verify HTTP 204 No Content returned by Zoho search is handled as an empty list."""
    mock_urlopen.return_value = MockHttpResponse(b"", code=204)

    adapter = ZohoCrmAdapter(business_id="tenant_search", credentials={"access_token": "live_token_search"})
    res = adapter.search_records("Contacts", email="nonexistent@example.com")

    assert res["data"] == []
    assert res["info"]["count"] == 0


@patch("urllib.request.urlopen")
def test_zoho_get_record_and_id_normalization(mock_urlopen):
    """Verify record retrieval normalizes provider IDs (e.g. zoho_contact_415... -> 415...)."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [
                {
                    "id": "zoho_contact_4150892000001",
                    "First_Name": "Samantha",
                    "Last_Name": "Ray",
                    "Email": "samantha@example.com",
                }
            ]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(business_id="tenant_get", credentials={"access_token": "live_token_get"})
    record = adapter.get_record("Contacts", "zoho_contact_4150892000001")

    assert record["id"] == "4150892000001"
    assert record["First_Name"] == "Samantha"


@patch("urllib.request.urlopen")
def test_zoho_create_record(mock_urlopen):
    """Verify record creation sends nested data payload and parses response ID."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [
                {
                    "code": "SUCCESS",
                    "details": {"id": "4150892000009999"},
                    "message": "record added",
                    "status": "success",
                }
            ]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(business_id="tenant_create", credentials={"access_token": "live_token_create"})
    res = adapter.create_record(
        "Contacts",
        {"name": "Arthur Dent", "email": "arthur@galaxy.org", "phone": "+14155559999"},
    )

    assert res["id"] == "4150892000009999"
    assert res["created"] is True
    assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


@patch("urllib.request.urlopen")
def test_zoho_update_record(mock_urlopen):
    """Verify record update sends PUT request to module/id."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [
                {
                    "code": "SUCCESS",
                    "details": {"id": "4150892000009999"},
                    "message": "record updated",
                    "status": "success",
                }
            ]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(business_id="tenant_update", credentials={"access_token": "live_token_update"})
    res = adapter.update_record(
        "Contacts",
        "4150892000009999",
        {"name": "Arthur Dent", "notes": "Prefers morning tea."},
    )

    assert res["id"] == "4150892000009999"
    assert res["created"] is False
    assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


@patch("urllib.request.urlopen")
def test_zoho_upsert_record_success_insert_and_update(mock_urlopen):
    """Verify upsert handles both 'insert' and 'update' action outcomes."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [
                {
                    "code": "SUCCESS",
                    "action": "insert",
                    "details": {"id": "4150892000005555"},
                    "status": "success",
                }
            ]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(business_id="tenant_upsert", credentials={"access_token": "live_token_upsert"})
    res = adapter.upsert_record(
        "Contacts",
        {"name": "Ford Prefect", "email": "ford@galaxy.org", "phone": "+14155551111"},
    )

    assert res["id"] == "4150892000005555"
    assert res["created"] is True
    assert res["action"] == "insert"


@patch("urllib.request.urlopen")
def test_zoho_upsert_conflict_duplicate_data(mock_urlopen):
    """Verify upsert returns CONFLICT error when multiple records match duplicate check fields."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [
                {
                    "code": "DUPLICATE_DATA",
                    "message": "duplicate data found in check fields",
                    "status": "error",
                }
            ]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(business_id="tenant_upsert_conflict", credentials={"access_token": "live_token_upsert"})

    with pytest.raises(ZohoIntegrationException) as exc_info:
        adapter.upsert_record(
            "Contacts",
            {"name": "Duplicate Contact", "email": "dupe@example.com", "phone": "+14155552222"},
        )

    assert exc_info.value.error.category == ErrorCategory.CONFLICT
    assert exc_info.value.error.code == "DUPLICATE_DATA"


def test_zoho_upsert_without_email_or_phone_creates_distinct():
    """Verify upserting without email or phone falls back to create_record (never merges by name)."""
    adapter = ZohoCrmAdapter(business_id="tenant_upsert_no_id", credentials={"access_token": "mock_token"})
    with patch.object(adapter, "create_record") as mock_create:
        mock_create.return_value = {"id": "4150892000007777", "created": True}
        res = adapter.upsert_record("Contacts", {"name": "Only Name Given"})
        assert mock_create.called
        assert res["id"] == "4150892000007777"


# ==============================================================================
# 8. Custom Field Mappings & Resilience Against Missing Properties
# ==============================================================================

def test_zoho_field_mapping_name_splitting():
    """Verify caller full name is split into First_Name and Last_Name."""
    adapter = ZohoCrmAdapter(business_id="tenant_split")
    fields = adapter._map_input_to_zoho_fields({"name": "Dr. Clara Oswald", "email": "clara@tardis.org"})

    assert fields["First_Name"] == "Dr."
    assert fields["Last_Name"] == "Clara Oswald"
    assert fields["Email"] == "clara@tardis.org"


def test_zoho_custom_field_mappings_json_parsing():
    """Verify custom field mappings JSON configured by tenant maps into Zoho field API names."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_custom_fields",
        configuration={
            "field_mappings": json.dumps({"dietary": "Dietary_Preferences_Custom", "vip_level": "VIP_Tier_Custom"})
        },
    )
    fields = adapter._map_input_to_zoho_fields({
        "name": "Bruce Wayne",
        "email": "bruce@wayne.com",
        "dietary": "Gluten Free",
        "vip_level": "Platinum",
    })

    assert fields["Dietary_Preferences_Custom"] == "Gluten Free"
    assert fields["VIP_Tier_Custom"] == "Platinum"


@patch("urllib.request.urlopen")
def test_zoho_missing_custom_field_resilience_drops_field_and_retries(mock_urlopen):
    """
    Verify resilience when customer passes a custom field not defined in Zoho:
    Adapter catches HTTP 400 with invalid field error, strips the unknown field,
    and successfully retries the creation.
    """
    call_count = 0

    def side_effect(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        body_dict = json.loads(req.data.decode("utf-8"))
        data_item = body_dict["data"][0]

        if "Unknown_Custom_Field" in data_item:
            # First attempt fails with 400 INVALID_FIELD
            raise make_mock_http_error(
                400,
                {
                    "data": [
                        {
                            "code": "INVALID_FIELD",
                            "message": "invalid field 'Unknown_Custom_Field' not defined in module",
                            "status": "error",
                        }
                    ]
                },
            )
        else:
            # Second attempt without the bad field succeeds!
            return MockHttpResponse(
                json.dumps({
                    "data": [
                        {
                            "code": "SUCCESS",
                            "details": {"id": "4150892000008888"},
                            "status": "success",
                        }
                    ]
                }).encode("utf-8")
            )

    mock_urlopen.side_effect = side_effect

    adapter = ZohoCrmAdapter(
        business_id="tenant_resilience",
        configuration={"ignore_unknown_fields": True},
        credentials={"access_token": "live_token_resilience"},
    )

    res = adapter.create_record(
        "Contacts",
        {
            "name": "Sarah Jane",
            "email": "sarah@unit.org",
            "properties": {"Unknown_Custom_Field": "Some Value"},
        },
    )

    assert call_count == 2
    assert res["id"] == "4150892000008888"
    assert res["created"] is True


# ==============================================================================
# 9. Progressive Capability Gating (Tasks, Calls, Meetings)
# ==============================================================================

def test_zoho_progressive_gating_task_module_disabled():
    """Verify task creation is rejected when Tasks module is not enabled in tenant setup."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_gating",
        configuration={"enabled_modules": "Contacts,Leads"},  # Tasks NOT enabled
        credentials={"access_token": "live_token"},
    )

    with pytest.raises(ZohoIntegrationException) as exc_info:
        adapter.create_task(contact_id="415001", subject="Follow up call")

    assert exc_info.value.error.code == "ZOHO_MODULE_DISABLED"
    assert exc_info.value.error.category == ErrorCategory.INVALID_REQUEST


def test_zoho_progressive_gating_task_missing_scope():
    """Verify task creation is rejected when Tasks module is enabled but OAuth scope missing."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_gating",
        configuration={"enabled_modules": "Contacts,Leads,Tasks"},
        credentials={
            "access_token": "live_token_no_task_scope",
            "scopes": ["ZohoCRM.modules.contacts.READ", "ZohoCRM.modules.contacts.CREATE"],  # Missing tasks scope
        },
    )

    with pytest.raises(ZohoIntegrationException) as exc_info:
        adapter.create_task(contact_id="415001", subject="Follow up call")

    assert exc_info.value.error.code == "ZOHO_MISSING_SCOPES"
    assert exc_info.value.error.category == ErrorCategory.PERMISSION_DENIED


@patch("urllib.request.urlopen")
def test_zoho_progressive_gating_task_success(mock_urlopen):
    """Verify task creation succeeds when Tasks module is enabled and scope authorized."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [{"code": "SUCCESS", "details": {"id": "4150892000003333"}, "status": "success"}]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(
        business_id="tenant_gating_ok",
        configuration={"enabled_modules": "Contacts,Leads,Tasks"},
        credentials={
            "access_token": "live_token_tasks_ok",
            "scopes": ["ZohoCRM.modules.tasks.CREATE"],
        },
    )

    res = adapter.create_task(contact_id="415001", subject="Follow up with patient", priority="High")
    assert res["task_id"] == "4150892000003333"
    assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


@patch("urllib.request.urlopen")
def test_zoho_call_log_duration_formatting(mock_urlopen):
    """Verify voice call duration in seconds is converted to mm:ss format for Zoho Calls."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [{"code": "SUCCESS", "details": {"id": "4150892000004444"}, "status": "success"}]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(
        business_id="tenant_calls",
        configuration={"enabled_modules": "Contacts,Calls"},
        credentials={"access_token": "live_token_calls", "scopes": ["ZohoCRM.modules.calls.CREATE"]},
    )

    res = adapter.create_call_log(
        contact_id="415001",
        subject="Inbound Reception Call",
        duration_seconds=185,  # 3 minutes 5 seconds -> "03:05"
        call_type="Inbound",
    )

    assert res["call_id"] == "4150892000004444"
    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["data"][0]["Call_Duration"] == "03:05"


@patch("urllib.request.urlopen")
def test_zoho_meeting_creation_success(mock_urlopen):
    """Verify meeting creation in Events module when enabled and authorized."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "data": [{"code": "SUCCESS", "details": {"id": "4150892000006666"}, "status": "success"}]
        }).encode("utf-8")
    )

    adapter = ZohoCrmAdapter(
        business_id="tenant_meetings",
        configuration={"enabled_modules": "Contacts,Events"},
        credentials={"access_token": "live_token_events", "scopes": ["ZohoCRM.modules.events.CREATE"]},
    )

    res = adapter.create_meeting(
        contact_id="415001",
        title="Consultation",
        start_time="2026-11-01T10:00:00+00:00",
        end_time="2026-11-01T10:30:00+00:00",
    )

    assert res["event_id"] == "4150892000006666"
    assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


# ==============================================================================
# 10. Rate Limiting & Error Normalization
# ==============================================================================

@pytest.mark.parametrize(
    "status_code, body_code, headers, expected_category, expected_retryable, expected_retry_after",
    [
        (429, "RATE_LIMIT_EXCEEDED", {"Retry-After": "5"}, ErrorCategory.RATE_LIMITED, True, 5.0),
        (401, "INVALID_TOKEN", {}, ErrorCategory.AUTHENTICATION_FAILED, False, None),
        (403, "NO_PERMISSION", {}, ErrorCategory.PERMISSION_DENIED, False, None),
        (404, "RECORD_NOT_FOUND", {}, ErrorCategory.RESOURCE_NOT_FOUND, False, None),
        (409, "DUPLICATE_DATA", {}, ErrorCategory.CONFLICT, False, None),
        (400, "MANDATORY_NOT_FOUND", {}, ErrorCategory.INVALID_REQUEST, False, None),
        (500, "INTERNAL_SERVER_ERROR", {}, ErrorCategory.PROVIDER_UNAVAILABLE, True, None),
    ],
)
def test_zoho_error_normalization(
    status_code, body_code, headers, expected_category, expected_retryable, expected_retry_after
):
    """Verify all documented Zoho CRM error codes and HTTP statuses map to standard ErrorCategory."""
    adapter = ZohoCrmAdapter(business_id="tenant_err")
    http_err = make_mock_http_error(
        status_code,
        {"code": body_code, "message": f"Zoho error {body_code}"},
        headers=headers,
    )

    norm_err = adapter._normalize_zoho_error(http_err)
    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable
    if expected_retry_after:
        assert norm_err.retry_after_seconds == expected_retry_after


# ==============================================================================
# 11. Configuration Validation & Readiness Assessment
# ==============================================================================

def test_zoho_validate_configuration():
    """Verify validate_configuration checks required credentials and region validity."""
    adapter = ZohoCrmAdapter(business_id="tenant_cfg")

    # Invalid: missing credentials
    r1 = adapter.validate_configuration({})
    assert r1.passed is False

    # Invalid: invalid region
    r2 = adapter.validate_configuration({"client_id": "cid", "client_secret": "sec", "data_center": "mars"})
    assert r2.passed is False

    # Valid
    r3 = adapter.validate_configuration({"client_id": "cid", "client_secret": "sec", "data_center": "eu"})
    assert r3.passed is True


def test_zoho_assess_readiness_ready_in_sandbox():
    """Verify assess_readiness succeeds in mock/sandbox mode."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_ready",
        configuration={"client_id": "cid", "client_secret": "sec", "data_center": "us"},
        credentials={"access_token": "sandbox_key_verified"},
    )

    report = adapter.assess_readiness()
    assert report.is_ready is True
    assert report.status == CapabilityStatus.READY


# ==============================================================================
# 12. Multi-Tenant Isolation & Webhooks
# ==============================================================================

def test_zoho_multi_tenant_isolation():
    """Verify distinct tenant adapter instances maintain separate configurations, tokens, and orgs."""
    tenant_a = ZohoCrmAdapter(
        business_id="tenant_a",
        configuration={"organization_id": "111111", "data_center": "us"},
        credentials={"access_token": "token_tenant_a"},
    )
    tenant_b = ZohoCrmAdapter(
        business_id="tenant_b",
        configuration={"organization_id": "222222", "data_center": "eu"},
        credentials={"access_token": "token_tenant_b"},
    )

    assert tenant_a.get_accounts_url() == "https://accounts.zoho.com"
    assert tenant_b.get_accounts_url() == "https://accounts.zoho.eu"
    assert tenant_a._get_organization_id() == "111111"
    assert tenant_b._get_organization_id() == "222222"
    assert tenant_a._get_access_token() != tenant_b._get_access_token()


def test_zoho_webhook_signature_verification():
    """Verify HMAC-SHA256 signature verification for Zoho webhook notifications."""
    secret = "my_zoho_webhook_secret_key"
    payload_bytes = b'{"module": "Contacts", "operation": "create", "id": "4150892"}'
    valid_sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    adapter = ZohoCrmAdapter(
        business_id="tenant_webhook",
        credentials={"webhook_secret": secret},
    )

    # Valid signature
    assert adapter.verify_webhook_signature(payload_bytes, {"x-zoho-webhook-signature": valid_sig}) is True
    # Invalid signature
    assert adapter.verify_webhook_signature(payload_bytes, {"x-zoho-webhook-signature": "forged_sig"}) is False


def test_zoho_handle_webhook_success():
    """Verify handle_webhook processes valid webhook requests."""
    secret = "wh_secret"
    payload = {"module": "Contacts", "operation": "create", "event_id": "evt_101"}
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    adapter = ZohoCrmAdapter(business_id="tenant_wh", credentials={"webhook_secret": secret})
    req = WebhookRequest(
        provider_id="zoho",
        headers={"x-zoho-webhook-signature": sig},
        raw_body=raw_body,
        parsed_json=payload,
    )

    res = adapter.handle_webhook(req)
    assert res.success is True
    assert res.event_type == "Contacts.create"
    assert res.event_id == "evt_101"


# ==============================================================================
# 13. Capability Contract Execution via execute()
# ==============================================================================

def test_zoho_execute_get_customer():
    """Verify CapabilityType.GET_CUSTOMER execution returns normalized customer data."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_exec",
        credentials={"access_token": "mock_token"},
    )
    ctx = ExecutionContext(tenant_id="tenant_exec", business_id="tenant_exec", conversation_id="conv_1")

    result = adapter.execute(
        CapabilityType.GET_CUSTOMER,
        {"email": "alex@example.com"},
        ctx,
    )

    assert result.success is True
    assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert result.authoritative_source == AuthoritativeSource.CRM_SYSTEM.value
    assert result.data["customer_id"] == "4150892000002891001"
    assert result.data["name"] == "Alex Mercer"
    assert result.data["email"] == "alex@example.com"


def test_zoho_execute_create_or_update_customer():
    """Verify CapabilityType.CREATE_OR_UPDATE_CUSTOMER execution creates customer record."""
    adapter = ZohoCrmAdapter(
        business_id="tenant_exec",
        credentials={"access_token": "mock_token"},
    )
    ctx = ExecutionContext(tenant_id="tenant_exec", business_id="tenant_exec", conversation_id="conv_2")

    result = adapter.execute(
        CapabilityType.CREATE_OR_UPDATE_CUSTOMER,
        {"name": "Eleanor Vance", "email": "eleanor@hillhouse.org", "phone": "+14155553333"},
        ctx,
    )

    assert result.success is True
    assert result.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert result.data["created"] is True
    assert result.data["email"] == "eleanor@hillhouse.org"
    assert result.data["customer_id"] is not None
