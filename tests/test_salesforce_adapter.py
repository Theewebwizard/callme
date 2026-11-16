"""
Unit and integration tests for the Salesforce CRM Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.CRM_SYSTEM)
- Registry lookup and option aliases ('salesforce', 'salesforce_crm')
- Multi-environment routing (Production vs Sandbox vs custom My Domain)
- External Client App (ECA) configuration & admin approval policies
- OAuth 2.0 authorization URL, code exchange, token refresh, and token revocation
- Organization-specific authorization and strict cross-organization/cross-environment prevention
- Metadata discovery (SObjects, fields, custom fields, organization)
- Configurable deduplication matching policies
- Strict duplicate safeguard: never merge two people solely because names match
- Records APIs (SOQL search with pagination, record retrieval, create, update, upsert)
- Truthful confirmation: do not claim a record was saved until Salesforce confirms the write
- Validation rules and field-level permissions treated as business-visible failures, not successful writes
- Custom field mappings and resilience against unknown custom fields (retry after stripping)
- Progressive capability gating (Accounts, Cases, Opportunities, Tasks) based on enabled objects
- Sforce-Limit-Info header inspection & rate-limiting (HTTP 429)
- Configuration validation and readiness assessment
- Multi-tenant isolation and cryptographic webhook signature verification
- Capability contract execution via execute()
"""

from typing import Any, Dict, List, Optional
import pytest
from unittest.mock import MagicMock, patch
import json
import time
import hmac
import hashlib
import urllib.error
from datetime import datetime, timezone
import io

from backend.integrations.adapters.salesforce_adapter import (
    SalesforceAdapter,
    SalesforceIntegrationException,
    SalesforceEnvironment,
    SalesforceAppType,
    AdminApprovalPolicy,
    MatchingStrategy,
    LOGIN_URLS,
    DEFAULT_API_VERSION,
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


def make_mock_http_error(code: int, body_data: Any, headers: dict = None):
    body_bytes = json.dumps(body_data).encode("utf-8") if not isinstance(body_data, bytes) else body_data
    fp = io.BytesIO(body_bytes)
    return urllib.error.HTTPError(
        url="https://instance.salesforce.com/test",
        code=code,
        msg="HTTP Error",
        hdrs=headers or {},
        fp=fp,
    )


# ==============================================================================
# 1. Manifest, Registry & Authoritative Source
# ==============================================================================

def test_salesforce_manifest_and_authoritative_source():
    """Verify Salesforce CRM adapter manifest declarations and CRM_SYSTEM authoritative source."""
    adapter = SalesforceAdapter(business_id="tenant_dental")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "salesforce"
    assert manifest.display_name == "Salesforce CRM"
    assert manifest.category == IntegrationCategory.CRM
    assert manifest.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert adapter.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert manifest.auth_method == AuthMethod.OAUTH2

    # Scopes
    assert "api" in manifest.required_oauth_scopes
    assert "refresh_token" in manifest.required_oauth_scopes
    assert "offline_access" in manifest.required_oauth_scopes
    assert "id" in manifest.required_oauth_scopes

    # Capabilities
    caps = adapter.get_supported_capabilities()
    assert CapabilityType.GET_CUSTOMER in caps
    assert CapabilityType.CREATE_OR_UPDATE_CUSTOMER in caps


def test_salesforce_registered_in_registry():
    """Verify registry catalogs Salesforce under 'salesforce' and 'salesforce_crm' alias."""
    registry = get_integration_registry()
    manifest_primary = registry.get_manifest("salesforce")
    assert manifest_primary is not None
    assert manifest_primary.provider_id == "salesforce"

    # Alias check
    adapter_cls = registry.get_adapter_class("salesforce_crm")
    assert adapter_cls is SalesforceAdapter


# ==============================================================================
# 2. Sandbox vs Production Environment & Login URL Resolution
# ==============================================================================

def test_salesforce_environment_login_url_resolution():
    """Verify production, sandbox, and custom My Domain environments resolve to correct login URLs."""
    # Production
    prod_adapter = SalesforceAdapter(
        business_id="tenant_prod",
        configuration={"environment": "production"},
    )
    assert prod_adapter.get_login_url() == "https://login.salesforce.com"

    # Sandbox
    sandbox_adapter = SalesforceAdapter(
        business_id="tenant_sandbox",
        configuration={"environment": "sandbox"},
    )
    assert sandbox_adapter.get_login_url() == "https://test.salesforce.com"

    # Custom My Domain
    custom_adapter = SalesforceAdapter(
        business_id="tenant_custom",
        configuration={"login_url": "https://myhealthcare.my.salesforce.com"},
    )
    assert custom_adapter.get_login_url() == "https://myhealthcare.my.salesforce.com"


def test_salesforce_instance_url_resolution():
    """Verify dynamic instance_url captured during OAuth token exchange overrides login URL."""
    adapter = SalesforceAdapter(
        business_id="tenant_instance",
        configuration={"environment": "production"},
        credentials={"instance_url": "https://na139.salesforce.com"},
    )
    assert adapter.get_instance_url() == "https://na139.salesforce.com"


# ==============================================================================
# 3. External Client App vs Connected App & Admin Policies
# ==============================================================================

def test_salesforce_app_type_and_admin_policies():
    """Verify External Client App (ECA) is evaluated as default/recommended with admin approval policies."""
    adapter = SalesforceAdapter(business_id="tenant_eca")
    assert adapter._get_app_type() == SalesforceAppType.EXTERNAL_CLIENT_APP.value
    assert adapter._get_admin_approval_policy() == AdminApprovalPolicy.ADMIN_APPROVED_PREAUTHORIZED.value

    # Validate configuration checks
    res = adapter.validate_configuration({
        "client_id": "3MVG9_CLIENT_ID",
        "client_secret": "CLIENT_SECRET",
        "environment": "production",
        "app_type": "external_client_app",
    })
    assert res.passed is True

    # Readiness assessment includes ECA policy info
    report = adapter.assess_readiness()
    eca_check = next((c for c in report.checks if c.check_id == "sf_eca_policy"), None)
    assert eca_check is not None
    assert eca_check.passed is True


# ==============================================================================
# 4. OAuth 2.0 Flow: Authorization URL, Code Exchange, Refresh & Revoke
# ==============================================================================

def test_salesforce_authorization_url_generation():
    """Verify OAuth authorization URL formatting with scopes, client_id, and state."""
    adapter = SalesforceAdapter(
        business_id="tenant_auth",
        configuration={"client_id": "3MVG9_TEST_CLIENT_ID", "environment": "production"},
    )

    url = adapter.get_authorization_url(
        redirect_uri="https://callme.example.com/oauth/callback",
        state="state_xyz_123",
    )

    assert url.startswith("https://login.salesforce.com/services/oauth2/authorize?")
    assert "client_id=3MVG9_TEST_CLIENT_ID" in url
    assert "response_type=code" in url
    assert "prompt=consent" in url
    assert "state=state_xyz_123" in url
    assert "scope=api+refresh_token+offline_access+id" in url or "scope=api" in url


def test_salesforce_authorization_url_missing_client_id():
    """Verify ValueError is raised if client_id is missing when generating authorization URL."""
    adapter = SalesforceAdapter(business_id="tenant_no_id")
    with pytest.raises(ValueError, match="client_id"):
        adapter.get_authorization_url(redirect_uri="https://example.com", state="xyz")


@patch("urllib.request.urlopen")
def test_salesforce_exchange_authorization_code(mock_urlopen):
    """Verify code exchange captures tokens, instance_url, and parses 15/18-char organization_id."""
    token_response_payload = {
        "access_token": "00D000000000001!AQcAQ_access_token_val",
        "refresh_token": "5Aep861_refresh_token_val",
        "instance_url": "https://myclinic.my.salesforce.com",
        "id": "https://login.salesforce.com/id/00D5e000000ABCDEAA/0055e000000XYZ123",
        "token_type": "Bearer",
        "issued_at": "1710000000000",
        "signature": "sig_val",
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(token_response_payload).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_exchange",
        configuration={"client_id": "3MVG9_CLIENT", "client_secret": "SECRET", "environment": "production"},
    )

    tokens = adapter.exchange_authorization_code(code="auth_code_123", redirect_uri="https://example.com/cb")

    assert tokens["access_token"] == "00D000000000001!AQcAQ_access_token_val"
    assert tokens["refresh_token"] == "5Aep861_refresh_token_val"
    assert adapter.credentials["instance_url"] == "https://myclinic.my.salesforce.com"
    assert adapter.configuration["instance_url"] == "https://myclinic.my.salesforce.com"
    assert adapter.credentials["organization_id"] == "00D5e000000ABCDEAA"
    assert adapter.configuration["organization_id"] == "00D5e000000ABCDEAA"


@patch("urllib.request.urlopen")
def test_salesforce_refresh_access_token(mock_urlopen):
    """Verify refreshing expired access token against login URL using refresh_token."""
    token_response = {
        "access_token": "00D000000000001!NEW_REFRESHED_TOKEN",
        "instance_url": "https://myclinic.my.salesforce.com",
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(token_response).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_refresh",
        configuration={"client_id": "3MVG9_CLIENT", "client_secret": "SECRET", "environment": "sandbox"},
        credentials={"refresh_token": "5Aep861_REFRESH"},
    )

    result = adapter.refresh_access_token()
    assert result["access_token"] == "00D000000000001!NEW_REFRESHED_TOKEN"
    assert adapter.credentials["access_token"] == "00D000000000001!NEW_REFRESHED_TOKEN"


@patch("urllib.request.urlopen")
def test_salesforce_revoke_token(mock_urlopen):
    """Verify revoking an access token clears it locally."""
    mock_urlopen.return_value = MockHttpResponse(b"")

    adapter = SalesforceAdapter(
        business_id="tenant_revoke",
        configuration={"environment": "production"},
        credentials={"access_token": "token_to_revoke"},
    )

    success = adapter.revoke_token()
    assert success is True
    assert "access_token" not in adapter.credentials


# ==============================================================================
# 5. Strict Organization and Environment Isolation
# ==============================================================================

@patch("urllib.request.urlopen")
def test_salesforce_organization_verification_success(mock_urlopen):
    """Verify organization match passes when token org matches configured org."""
    org_resp = {
        "records": [
            {
                "Id": "00D5e000000ABCDEAA",
                "Name": "Apex Health Care",
                "OrganizationType": "Enterprise Edition",
                "IsSandbox": False,
            }
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(org_resp).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_org_ok",
        configuration={"organization_id": "00D5e000000ABCDEAA", "environment": "production"},
        credentials={"access_token": "live_token_123"},
    )

    assert adapter.verify_organization("00D5e000000ABCDEAA") is True


@patch("urllib.request.urlopen")
def test_salesforce_cross_organization_rejection(mock_urlopen):
    """
    CRITICAL: Never use an access token generated for one Salesforce organization against another!
    Verify verification strictly rejects when token belongs to another organization.
    """
    org_resp = {
        "records": [
            {
                "Id": "00D999999999999ZZZ",  # Different organization
                "Name": "Other Org",
                "IsSandbox": False,
            }
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(org_resp).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_cross_org",
        configuration={"organization_id": "00D5e000000ABCDEAA", "environment": "production"},
        credentials={"access_token": "token_from_other_org"},
    )

    is_valid = adapter.verify_organization("00D5e000000ABCDEAA")
    assert is_valid is False


@patch("urllib.request.urlopen")
def test_salesforce_cross_environment_rejection_sandbox_against_prod(mock_urlopen):
    """
    CRITICAL: Never use an access token generated for Salesforce Sandbox against Production or vice versa!
    """
    org_resp = {
        "records": [
            {
                "Id": "00D5e000000ABCDEAA",
                "Name": "Apex Health Care (Sandbox)",
                "IsSandbox": True,  # Token org is a Sandbox
            }
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(org_resp).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_env_mismatch",
        configuration={"organization_id": "00D5e000000ABCDEAA", "environment": "production"},  # Configured for Production!
        credentials={"access_token": "sandbox_token"},
    )

    is_valid = adapter.verify_organization("00D5e000000ABCDEAA")
    assert is_valid is False, "Sandbox token must be strictly rejected against production configuration!"


# ==============================================================================
# 6. Dynamic Resource & Metadata Discovery (SObjects, Fields, Org)
# ==============================================================================

@patch("urllib.request.urlopen")
def test_salesforce_discover_sobjects(mock_urlopen):
    """Verify dynamic discovery of available standard and custom SObjects."""
    sobjects_payload = {
        "sobjects": [
            {"name": "Contact", "label": "Contact", "custom": False, "createable": True},
            {"name": "Lead", "label": "Lead", "custom": False, "createable": True},
            {"name": "Patient__c", "label": "Patient", "custom": True, "createable": True},
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(sobjects_payload).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_meta",
        credentials={"access_token": "live_token_meta"},
    )

    resources = adapter.discover_resources("sobjects")
    assert len(resources) == 3
    names = [r.resource_id for r in resources]
    assert "Contact" in names
    assert "Lead" in names
    assert "Patient__c" in names
    assert resources[2].metadata["custom"] is True


@patch("urllib.request.urlopen")
def test_salesforce_discover_fields_with_custom_fields(mock_urlopen):
    """Verify dynamic discovery of contact and lead field metadata including custom fields."""
    fields_payload = {
        "fields": [
            {"name": "FirstName", "label": "First Name", "type": "string", "custom": False},
            {"name": "LastName", "label": "Last Name", "type": "string", "custom": False, "nillable": False},
            {"name": "Email", "label": "Email", "type": "email", "custom": False},
            {"name": "VIP_Status__c", "label": "VIP Status", "type": "string", "custom": True},
        ]
    }
    mock_urlopen.return_value = MockHttpResponse(json.dumps(fields_payload).encode("utf-8"))

    adapter = SalesforceAdapter(
        business_id="tenant_fields",
        credentials={"access_token": "live_token_fields"},
    )

    resources = adapter.discover_resources("contact_fields")
    assert len(resources) == 4
    f_names = [r.resource_id for r in resources]
    assert "FirstName" in f_names
    assert "VIP_Status__c" in f_names
    assert resources[1].metadata["nillable"] is False
    assert resources[3].metadata["custom"] is True


def test_salesforce_discover_resources_mock_mode():
    """Verify discover_resources returns representative metadata in mock/sandbox mode."""
    adapter = SalesforceAdapter(business_id="tenant_mock", credentials={"access_token": "mock_token"})
    objects = adapter.discover_resources("objects")
    assert len(objects) >= 4
    fields = adapter.discover_resources("fields")
    assert any(f.resource_id == "Email" for f in fields)
    org = adapter.discover_resources("org")
    assert len(org) == 1


# ==============================================================================
# 7. Deduplication Matching Policy & Strict Name-Only Safeguard
# ==============================================================================

def test_salesforce_matching_strategy_name_alone_never_merges():
    """
    CRITICAL SAFEGUARD:
    Contacts and leads are NEVER merged solely based on matching names!
    If only a name is provided, find_existing_record returns None.
    """
    adapter = SalesforceAdapter(business_id="tenant_dedup")
    input_data = {"name": "Alex Mercer"}

    match = adapter.find_existing_record("Contact", input_data)
    assert match is None, "Name alone must NEVER match or merge existing CRM records!"


@patch("urllib.request.urlopen")
def test_salesforce_matching_strategy_email_then_phone(mock_urlopen):
    """Verify email_then_phone queries email first, then falls back to phone."""
    adapter = SalesforceAdapter(
        business_id="tenant_dedup",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_THEN_PHONE},
        credentials={"access_token": "live_token_dedup"},
    )

    call_count = 0

    def side_effect(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = req.full_url
        if "Email+%3D+%27unknown%40example.com%27" in url or "unknown@example.com" in urllib.parse.unquote(url):
            # No email match
            return MockHttpResponse(b'{"totalSize": 0, "done": true, "records": []}')
        elif "+14155552671" in urllib.parse.unquote(url):
            # Phone match
            return MockHttpResponse(
                json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [
                        {"Id": "003000000000001AAA", "FirstName": "Jane", "LastName": "Doe", "Phone": "+14155552671"}
                    ],
                }).encode("utf-8")
            )
        return MockHttpResponse(b'{"records": []}')

    mock_urlopen.side_effect = side_effect

    match = adapter.find_existing_record(
        "Contact",
        {"name": "Jane Doe", "email": "unknown@example.com", "phone": "+14155552671"},
    )

    assert match is not None
    assert match["Id"] == "003000000000001AAA"
    assert call_count == 2


@patch("urllib.request.urlopen")
def test_salesforce_matching_strategy_email_only(mock_urlopen):
    """Verify email_only ignores phone even if provided."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "totalSize": 1,
            "done": True,
            "records": [
                {"Id": "003000000000002AAA", "FirstName": "Bob", "LastName": "Smith", "Email": "bob@example.com"}
            ],
        }).encode("utf-8")
    )

    adapter = SalesforceAdapter(
        business_id="tenant_dedup",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_ONLY},
        credentials={"access_token": "live_token_dedup"},
    )

    match = adapter.find_existing_record(
        "Contact",
        {"name": "Bob Smith", "email": "bob@example.com", "phone": "+14155550000"},
    )

    assert match is not None
    assert match["Id"] == "003000000000002AAA"
    req = mock_urlopen.call_args[0][0]
    unquoted = urllib.parse.unquote(req.full_url)
    assert "Email = 'bob@example.com'" in unquoted
    assert "Phone = " not in unquoted and "+14155550000" not in unquoted


# ==============================================================================
# 8. Records APIs: SOQL Query with Pagination, Get, Create, Update, Upsert
# ==============================================================================

@patch("urllib.request.urlopen")
def test_salesforce_query_soql_with_pagination(mock_urlopen):
    """Verify SOQL query follows nextRecordsUrl pagination."""
    call_count = 0

    def side_effect(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockHttpResponse(
                json.dumps({
                    "totalSize": 2,
                    "done": False,
                    "nextRecordsUrl": "/services/data/v61.0/query/01gD00000022Oz-2000",
                    "records": [{"Id": "003000000000001AAA", "LastName": "FirstBatch"}],
                }).encode("utf-8")
            )
        else:
            return MockHttpResponse(
                json.dumps({
                    "totalSize": 2,
                    "done": True,
                    "records": [{"Id": "003000000000002AAA", "LastName": "SecondBatch"}],
                }).encode("utf-8")
            )

    mock_urlopen.side_effect = side_effect

    adapter = SalesforceAdapter(business_id="tenant_query", credentials={"access_token": "live_token"})
    res = adapter.query_soql("SELECT Id, LastName FROM Contact", max_records=10)

    assert call_count == 2
    assert len(res["records"]) == 2
    assert res["records"][0]["Id"] == "003000000000001AAA"
    assert res["records"][1]["Id"] == "003000000000002AAA"


@patch("urllib.request.urlopen")
def test_salesforce_get_record_and_id_normalization(mock_urlopen):
    """Verify record retrieval normalizes provider IDs (e.g. sf_contact_003... -> 003...)."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({
            "Id": "sf_contact_0035e000000ABCDEAA",
            "FirstName": "Samantha",
            "LastName": "Ray",
            "Email": "samantha@example.com",
        }).encode("utf-8")
    )

    adapter = SalesforceAdapter(business_id="tenant_get", credentials={"access_token": "live_token_get"})
    record = adapter.get_record("Contact", "sf_contact_0035e000000ABCDEAA")

    assert record["Id"] == "0035e000000ABCDEAA"
    assert record["FirstName"] == "Samantha"


@patch("urllib.request.urlopen")
def test_salesforce_create_record_confirmed(mock_urlopen):
    """Verify record creation verifies confirmed write (success: true and id)."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({"id": "0035e000000CONFIRMED", "success": True, "errors": []}).encode("utf-8")
    )

    adapter = SalesforceAdapter(business_id="tenant_create", credentials={"access_token": "live_token_create"})
    res = adapter.create_record(
        "Contact",
        {"name": "Arthur Dent", "email": "arthur@galaxy.org", "phone": "+14155559999"},
    )

    assert res["id"] == "0035e000000CONFIRMED"
    assert res["created"] is True
    assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


@patch("urllib.request.urlopen")
def test_salesforce_update_record(mock_urlopen):
    """Verify record update sends PATCH request and handles HTTP 204 No Content."""
    mock_urlopen.return_value = MockHttpResponse(b"", code=204)

    adapter = SalesforceAdapter(business_id="tenant_update", credentials={"access_token": "live_token_update"})
    res = adapter.update_record(
        "Contact",
        "0035e000000CONFIRMED",
        {"name": "Arthur Dent", "notes": "Prefers morning tea."},
    )

    assert res["id"] == "0035e000000CONFIRMED"
    assert res["created"] is False
    assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


@patch("urllib.request.urlopen")
def test_salesforce_upsert_record(mock_urlopen):
    """Verify upsert via PATCH with external ID field and value."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({"id": "0035e000000UPSERTED", "success": True, "created": True}).encode("utf-8")
    )

    adapter = SalesforceAdapter(business_id="tenant_upsert", credentials={"access_token": "live_token_upsert"})
    res = adapter.upsert_record(
        "Contact",
        "External_Patient_Id__c",
        "PATIENT-1001",
        {"name": "Ford Prefect", "email": "ford@galaxy.org"},
    )

    assert res["id"] == "0035e000000UPSERTED"
    assert res["created"] is True


# ==============================================================================
# 9. Truthful Confirmation: Do Not Claim Saved Until Confirmed
# ==============================================================================

@patch("urllib.request.urlopen")
def test_salesforce_unconfirmed_write_rejected(mock_urlopen):
    """
    CRITICAL: Do not claim a record was saved until Salesforce confirms the write!
    If success is false or ID is missing, raises SalesforceIntegrationException.
    """
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({"id": "", "success": False, "errors": [{"message": "Unconfirmed write"}]}).encode("utf-8")
    )

    adapter = SalesforceAdapter(business_id="tenant_unconfirmed", credentials={"access_token": "live_token"})

    with pytest.raises(SalesforceIntegrationException) as exc_info:
        adapter.create_record("Contact", {"name": "Unconfirmed User", "email": "user@example.com"})

    assert exc_info.value.error.code == "SALESFORCE_WRITE_UNCONFIRMED"
    assert exc_info.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION


# ==============================================================================
# 10. Validation Rules & Permission Errors as Business-Visible Failures
# ==============================================================================

@patch("urllib.request.urlopen")
def test_salesforce_validation_rule_failure_treated_as_business_rejection(mock_urlopen):
    """
    Treat validation-rule failures (FIELD_CUSTOM_VALIDATION_EXCEPTION) as business-visible failures,
    never successful writes.
    """
    mock_urlopen.side_effect = make_mock_http_error(
        400,
        [
            {
                "message": "Custom Validation: Patient must have an emergency contact phone number.",
                "errorCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION",
                "fields": ["Emergency_Contact_Phone__c"],
            }
        ],
    )

    adapter = SalesforceAdapter(business_id="tenant_val_rule", credentials={"access_token": "live_token"})

    with pytest.raises(SalesforceIntegrationException) as exc_info:
        adapter.create_record("Contact", {"name": "Test Patient", "email": "patient@example.com"})

    assert exc_info.value.error.category == ErrorCategory.BUSINESS_RULE_VIOLATION
    assert exc_info.value.error.code == "FIELD_CUSTOM_VALIDATION_EXCEPTION"
    assert "Emergency_Contact_Phone__c" in exc_info.value.error.details.get("fields", [])


@patch("urllib.request.urlopen")
def test_salesforce_field_level_permission_error_treated_as_permission_denied(mock_urlopen):
    """
    Treat field-level permission errors (INVALID_FIELD_FOR_INSERT_UPDATE) as permission-denied failures,
    never successful writes.
    """
    mock_urlopen.side_effect = make_mock_http_error(
        400,
        [
            {
                "message": "Unable to create/update fields: SSN__c. Please check the security settings of this field.",
                "errorCode": "INVALID_FIELD_FOR_INSERT_UPDATE",
                "fields": ["SSN__c"],
            }
        ],
    )

    adapter = SalesforceAdapter(business_id="tenant_fls", credentials={"access_token": "live_token"})

    with pytest.raises(SalesforceIntegrationException) as exc_info:
        adapter.create_record("Contact", {"name": "Secure Patient", "properties": {"SSN__c": "123-45-6789"}})

    assert exc_info.value.error.category == ErrorCategory.PERMISSION_DENIED
    assert exc_info.value.error.code == "INVALID_FIELD_FOR_INSERT_UPDATE"


# ==============================================================================
# 11. Custom Field Resilience
# ==============================================================================

def test_salesforce_field_mapping_name_splitting():
    """Verify caller full name is split into FirstName and LastName."""
    adapter = SalesforceAdapter(business_id="tenant_split")
    fields = adapter._map_input_to_salesforce_fields({"name": "Dr. Clara Oswald", "email": "clara@tardis.org"})

    assert fields["FirstName"] == "Dr."
    assert fields["LastName"] == "Clara Oswald"
    assert fields["Email"] == "clara@tardis.org"


def test_salesforce_custom_field_mappings_json_parsing():
    """Verify custom field mappings JSON maps caller data to CustomField__c API names."""
    adapter = SalesforceAdapter(
        business_id="tenant_custom_fields",
        configuration={
            "field_mappings": json.dumps({
                "preferred_language": "Preferred_Language__c",
                "vip_tier": "VIP_Tier__c",
            })
        },
    )
    fields = adapter._map_input_to_salesforce_fields({
        "name": "Bruce Wayne",
        "email": "bruce@wayne.com",
        "preferred_language": "English",
        "vip_tier": "Platinum",
    })

    assert fields["Preferred_Language__c"] == "English"
    assert fields["VIP_Tier__c"] == "Platinum"


@patch("urllib.request.urlopen")
def test_salesforce_missing_custom_field_resilience_drops_field_and_retries(mock_urlopen):
    """
    Verify resilience when customer passes an unknown custom field:
    Adapter catches HTTP 400 invalid field error, strips unknown field, and retries.
    """
    call_count = 0

    def side_effect(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        body_dict = json.loads(req.data.decode("utf-8"))

        if "Unknown_Custom__c" in body_dict:
            # First attempt fails with 400 INVALID_FIELD
            raise make_mock_http_error(
                400,
                [
                    {
                        "message": "No such column 'Unknown_Custom__c' on sobject of type Contact",
                        "errorCode": "INVALID_FIELD",
                    }
                ],
            )
        else:
            # Second attempt succeeds!
            return MockHttpResponse(
                json.dumps({"id": "0035e000000RETRY_OK", "success": True, "errors": []}).encode("utf-8")
            )

    mock_urlopen.side_effect = side_effect

    adapter = SalesforceAdapter(
        business_id="tenant_resilience",
        configuration={"ignore_unknown_fields": True},
        credentials={"access_token": "live_token_resilience"},
    )

    res = adapter.create_record(
        "Contact",
        {
            "name": "Sarah Jane",
            "email": "sarah@unit.org",
            "properties": {"Unknown_Custom__c": "Some Value"},
        },
    )

    assert call_count == 2
    assert res["id"] == "0035e000000RETRY_OK"
    assert res["created"] is True


# ==============================================================================
# 12. Progressive Capability Gating for Extended Objects
# ==============================================================================

def test_salesforce_progressive_gating_account_disabled():
    """Verify Account creation is rejected when Account is not enabled in tenant config."""
    adapter = SalesforceAdapter(
        business_id="tenant_gating",
        configuration={"enabled_objects": "Contact,Lead"},  # Account NOT enabled
        credentials={"access_token": "live_token"},
    )

    with pytest.raises(SalesforceIntegrationException) as exc_info:
        adapter.create_account(name="Acme Corp")

    assert exc_info.value.error.code == "SALESFORCE_OBJECT_DISABLED"
    assert exc_info.value.error.category == ErrorCategory.INVALID_REQUEST


@patch("urllib.request.urlopen")
def test_salesforce_progressive_gating_account_success(mock_urlopen):
    """Verify Account creation succeeds when Account is configured in enabled_objects."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({"id": "0015e000000ACCOUNT", "success": True, "errors": []}).encode("utf-8")
    )

    adapter = SalesforceAdapter(
        business_id="tenant_gating_ok",
        configuration={"enabled_objects": "Contact,Lead,Account"},
        credentials={"access_token": "live_token"},
    )

    res = adapter.create_account(name="Acme Corp", phone="+14155551234", website="https://acme.com")
    assert res["id"] == "0015e000000ACCOUNT"


@patch("urllib.request.urlopen")
def test_salesforce_progressive_gating_case_success(mock_urlopen):
    """Verify Case creation succeeds when Case is configured in enabled_objects."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({"id": "5005e000000CASE", "success": True, "errors": []}).encode("utf-8")
    )

    adapter = SalesforceAdapter(
        business_id="tenant_case",
        configuration={"enabled_objects": "Contact,Case"},
        credentials={"access_token": "live_token"},
    )

    res = adapter.create_case(
        contact_id="0035e000000CONFIRMED",
        subject="Prescription Refill Request",
        description="Caller requested refill for medication.",
        priority="High",
    )
    assert res["id"] == "5005e000000CASE"


@patch("urllib.request.urlopen")
def test_salesforce_progressive_gating_task_success(mock_urlopen):
    """Verify Task creation succeeds when Task is configured in enabled_objects."""
    mock_urlopen.return_value = MockHttpResponse(
        json.dumps({"id": "00T5e000000TASK", "success": True, "errors": []}).encode("utf-8")
    )

    adapter = SalesforceAdapter(
        business_id="tenant_task",
        configuration={"enabled_objects": "Contact,Task"},
        credentials={"access_token": "live_token"},
    )

    res = adapter.create_task(
        who_id="0035e000000CONFIRMED",
        subject="Follow up on consultation notes",
        due_date="2026-11-01",
    )
    assert res["id"] == "00T5e000000TASK"


# ==============================================================================
# 13. Sforce-Limit-Info Header Monitoring & Rate Limiting
# ==============================================================================

@patch("urllib.request.urlopen")
def test_salesforce_limit_info_monitoring(mock_urlopen):
    """Verify Sforce-Limit-Info header is parsed and updates adapter api_usage."""
    mock_urlopen.return_value = MockHttpResponse(
        b'{"records": []}',
        headers={"Sforce-Limit-Info": "api-usage=320/15000"},
    )

    adapter = SalesforceAdapter(business_id="tenant_limits", credentials={"access_token": "live_token"})
    adapter.query_soql("SELECT Id FROM Contact LIMIT 1")

    assert adapter.api_usage["used"] == 320
    assert adapter.api_usage["limit"] == 15000


@pytest.mark.parametrize(
    "status_code, error_code, headers, expected_category, expected_retryable",
    [
        (429, "REQUEST_LIMIT_EXCEEDED", {"Retry-After": "4"}, ErrorCategory.RATE_LIMITED, True),
        (401, "INVALID_SESSION_ID", {}, ErrorCategory.AUTHENTICATION_FAILED, False),
        (403, "INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY", {}, ErrorCategory.PERMISSION_DENIED, False),
        (404, "NOT_FOUND", {}, ErrorCategory.RESOURCE_NOT_FOUND, False),
        (409, "DUPLICATES_DETECTED", {}, ErrorCategory.CONFLICT, False),
        (400, "FIELD_CUSTOM_VALIDATION_EXCEPTION", {}, ErrorCategory.BUSINESS_RULE_VIOLATION, False),
        (500, "SERVER_UNAVAILABLE", {}, ErrorCategory.PROVIDER_UNAVAILABLE, True),
    ],
)
def test_salesforce_error_normalization(status_code, error_code, headers, expected_category, expected_retryable):
    """Verify documented Salesforce error codes map to appropriate ErrorCategory."""
    adapter = SalesforceAdapter(business_id="tenant_err")
    http_err = make_mock_http_error(
        status_code,
        [{"message": f"Error {error_code}", "errorCode": error_code}],
        headers=headers,
    )

    norm_err = adapter._normalize_salesforce_error(http_err)
    assert norm_err.category == expected_category
    assert norm_err.is_retryable == expected_retryable


# ==============================================================================
# 14. Multi-Tenant Isolation & Webhooks
# ==============================================================================

def test_salesforce_multi_tenant_isolation():
    """Verify distinct tenant adapter instances maintain separate configurations, tokens, and orgs."""
    tenant_a = SalesforceAdapter(
        business_id="tenant_a",
        configuration={"organization_id": "00D111111111111AAA", "environment": "production"},
        credentials={"access_token": "token_tenant_a", "instance_url": "https://na1.salesforce.com"},
    )
    tenant_b = SalesforceAdapter(
        business_id="tenant_b",
        configuration={"organization_id": "00D222222222222BBB", "environment": "sandbox"},
        credentials={"access_token": "token_tenant_b", "instance_url": "https://cs1.salesforce.com"},
    )

    assert tenant_a.get_login_url() == "https://login.salesforce.com"
    assert tenant_b.get_login_url() == "https://test.salesforce.com"
    assert tenant_a._get_organization_id() == "00D111111111111AAA"
    assert tenant_b._get_organization_id() == "00D222222222222BBB"
    assert tenant_a.get_instance_url() != tenant_b.get_instance_url()


def test_salesforce_webhook_signature_verification():
    """Verify HMAC-SHA256 signature verification for Salesforce notification payloads."""
    secret = "my_sf_webhook_secret_key"
    payload_bytes = b'{"sobject": "Contact", "changeType": "UPDATE", "id": "0035e000000CONFIRMED"}'
    valid_sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    adapter = SalesforceAdapter(
        business_id="tenant_webhook",
        credentials={"webhook_secret": secret},
    )

    assert adapter.verify_webhook_signature(payload_bytes, {"x-salesforce-signature": valid_sig}) is True
    assert adapter.verify_webhook_signature(payload_bytes, {"x-salesforce-signature": "forged_sig"}) is False


def test_salesforce_handle_webhook_success():
    """Verify handle_webhook processes valid Change Data Capture / Outbound notification."""
    secret = "wh_secret"
    payload = {"sobject": "Contact", "changeType": "UPDATE", "event_id": "sf_evt_101"}
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    adapter = SalesforceAdapter(business_id="tenant_wh", credentials={"webhook_secret": secret})
    req = WebhookRequest(
        provider_id="salesforce",
        headers={"x-salesforce-signature": sig},
        raw_body=raw_body,
        parsed_json=payload,
    )

    res = adapter.handle_webhook(req)
    assert res.success is True
    assert res.event_type == "Contact.update"
    assert res.event_id == "sf_evt_101"


# ==============================================================================
# 15. Capability Contract Execution via execute()
# ==============================================================================

def test_salesforce_execute_get_customer():
    """Verify CapabilityType.GET_CUSTOMER execution returns normalized customer data."""
    adapter = SalesforceAdapter(
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
    assert result.data["customer_id"] == "003000000000001AAA"
    assert result.data["name"] == "Alex Mercer"
    assert result.data["email"] == "alex@example.com"


def test_salesforce_execute_create_or_update_customer():
    """Verify CapabilityType.CREATE_OR_UPDATE_CUSTOMER execution creates customer record."""
    adapter = SalesforceAdapter(
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
