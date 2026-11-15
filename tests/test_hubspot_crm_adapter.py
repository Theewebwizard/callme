"""
Unit and integration tests for the HubSpot CRM Integration Adapter.
Tests:
- Manifest & Authoritative Source (AuthoritativeSource.CRM_SYSTEM)
- Registry lookup and option aliases
- OAuth 2.0 authorization URL, code exchange, token refresh, introspection & scope verification
- Configuration validation and readiness assessment
- Resource discovery (properties, custom fields, objects, pipelines)
- Configurable deduplication matching strategies
- Strict duplicate safeguard: never merge two people solely because names match
- Custom field mappings and resilience against missing/unknown custom properties
- Contact search, filtering, and forward pagination
- Contact retrieval and provider ID normalization (e.g. hs_101 -> 101)
- Associations to other CRM records (companies, deals, notes, tasks)
- Engagements (notes, tasks, deals) with scope and configuration gating
- Rate limiting (HTTP 429) and Retry-After backoff calculation
- Error normalization (400, 401, 403, 404, 409, 500)
- Truthful outcome envelopes (OPERATION_COMPLETED vs OPERATION_PENDING)
- Multi-tenant isolation (Tenant A credentials & portal cannot leak to Tenant B)
- Cryptographic webhook signature verification (v3 HMAC-SHA256 & replay prevention)
- Capability contract execution via execute()
"""

import pytest
from unittest.mock import MagicMock, patch
import time
import base64
import hmac
import hashlib
from datetime import datetime, timezone

from backend.integrations.adapters.hubspot_crm_adapter import (
    HubspotCrmAdapter,
    HubspotIntegrationException,
    MatchingStrategy,
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
# 1. Manifest, Registry & Authoritative Source
# ==============================================================================

def test_hubspot_manifest_and_authoritative_source():
    """Verify HubSpot CRM adapter manifest declarations and CRM_SYSTEM authoritative source."""
    adapter = HubspotCrmAdapter(business_id="tenant_dental")
    manifest = adapter.get_manifest()

    assert manifest.provider_id == "hubspot"
    assert manifest.display_name == "HubSpot CRM"
    assert manifest.category == IntegrationCategory.CRM
    assert manifest.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert adapter.authoritative_source == AuthoritativeSource.CRM_SYSTEM
    assert manifest.auth_method == AuthMethod.OAUTH2

    # Scopes
    assert "crm.objects.contacts.read" in manifest.required_oauth_scopes
    assert "crm.objects.contacts.write" in manifest.required_oauth_scopes

    # Capabilities
    caps = adapter.get_supported_capabilities()
    assert CapabilityType.GET_CUSTOMER in caps
    assert CapabilityType.CREATE_OR_UPDATE_CUSTOMER in caps


def test_hubspot_registered_in_registry():
    """Verify registry catalogs HubSpot under 'hubspot' and 'hubspot_crm' alias."""
    registry = get_integration_registry()
    manifest_primary = registry.get_manifest("hubspot")
    assert manifest_primary is not None
    assert manifest_primary.provider_id == "hubspot"

    # Alias check
    adapter_cls = registry.get_adapter_class("hubspot_crm")
    assert adapter_cls is HubspotCrmAdapter


# ==============================================================================
# 2. OAuth 2.0 Authorization Flow & Token Introspection
# ==============================================================================

def test_hubspot_oauth_authorization_url_generation():
    """Verify OAuth authorization URL formatting with scopes, client_id, and state."""
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        configuration={
            "client_id": "client_abc_123",
            "redirect_uri": "https://answerly.ai/oauth/callback",
            "enabled_objects": ["contacts", "notes", "tasks"],
        },
    )

    url = adapter.get_authorization_url(
        redirect_uri="https://answerly.ai/oauth/callback",
        state="csrf_state_999",
    )

    assert "https://app.hubspot.com/oauth/authorize" in url
    assert "client_id=client_abc_123" in url
    assert "state=csrf_state_999" in url
    assert "crm.objects.contacts.read" in url
    assert "crm.objects.notes.read" in url
    assert "crm.objects.tasks.read" in url


def test_hubspot_oauth_token_exchange():
    """Verify exchanging authorization code for access & refresh tokens."""
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        configuration={
            "client_id": "client_abc_123",
            "redirect_uri": "https://answerly.ai/oauth/callback",
        },
        credentials={
            "client_secret": "secret_xyz_888",
        },
    )

    mock_token_resp = {
        "access_token": "act_new_token_777",
        "refresh_token": "ref_new_token_444",
        "expires_in": 1800,
        "token_type": "bearer",
    }

    mock_info_resp = {
        "token": "act_new_token_777",
        "hub_id": "14298102",
        "scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write"],
        "user": "admin@clinic.com",
    }

    with patch.object(adapter, "_post_form_request", return_value=mock_token_resp) as mock_post, \
         patch.object(adapter, "introspect_token", return_value=mock_info_resp):

        result = adapter.exchange_authorization_code(code="auth_code_123")
        assert result["access_token"] == "act_new_token_777"
        assert adapter.credentials["access_token"] == "act_new_token_777"
        assert adapter.credentials["refresh_token"] == "ref_new_token_444"
        assert adapter.configuration["portal_id"] == "14298102"
        assert adapter.credentials["scopes"] == ["crm.objects.contacts.read", "crm.objects.contacts.write"]
        mock_post.assert_called_once()


def test_hubspot_oauth_token_refresh():
    """Verify refreshing expired access token using refresh_token."""
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        configuration={
            "client_id": "client_abc_123",
        },
        credentials={
            "client_secret": "secret_xyz_888",
            "refresh_token": "ref_existing_token",
            "access_token": "act_old_token",
        },
    )

    mock_refresh_resp = {
        "access_token": "act_refreshed_999",
        "refresh_token": "ref_existing_token",
        "expires_in": 1800,
        "token_type": "bearer",
    }

    with patch.object(adapter, "_post_form_request", return_value=mock_refresh_resp):
        result = adapter.refresh_access_token()
        assert result["access_token"] == "act_refreshed_999"
        assert adapter.credentials["access_token"] == "act_refreshed_999"


def test_hubspot_scope_verification():
    """Verify scope inspection detects missing required OAuth scopes."""
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        credentials={
            "access_token": "act_test",
            "scopes": ["crm.objects.contacts.read"],  # Missing contacts.write
        },
    )

    is_valid, missing = adapter.verify_scopes(["crm.objects.contacts.read", "crm.objects.contacts.write"])
    assert is_valid is False
    assert missing == ["crm.objects.contacts.write"]

    # Now grant write scope
    adapter.credentials["scopes"].append("crm.objects.contacts.write")
    is_valid2, missing2 = adapter.verify_scopes(["crm.objects.contacts.read", "crm.objects.contacts.write"])
    assert is_valid2 is True
    assert len(missing2) == 0


# ==============================================================================
# 3. Configuration Validation & Readiness Assessment
# ==============================================================================

def test_hubspot_configuration_validation():
    """Verify configuration validation checks credentials and matching strategy."""
    # 1. Missing credentials fails
    adapter = HubspotCrmAdapter("tenant_dental", configuration={})
    res_fail = adapter.validate_configuration({})
    assert res_fail.passed is False
    assert "required" in res_fail.details

    # 2. Invalid matching strategy fails
    adapter_invalid = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": "invalid_strategy"},
        credentials={"access_token": "pat-na1-valid"},
    )
    res_strat_fail = adapter_invalid.validate_configuration({"matching_strategy": "invalid_strategy"})
    assert res_strat_fail.passed is False
    assert "Invalid matching strategy" in res_strat_fail.details

    # 3. Valid config passes
    adapter_valid = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": "email_then_phone"},
        credentials={"access_token": "pat-na1-valid"},
    )
    res_pass = adapter_valid.validate_configuration({"access_token": "pat-na1-valid"})
    assert res_pass.passed is True


def test_hubspot_readiness_assessment():
    """Verify assess_readiness compiles report checking token and scopes."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": "email_then_phone"},
        credentials={
            "access_token": "test_token_mock",
            "scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write"],
        },
    )

    report = adapter.assess_readiness()
    assert report.is_ready is True
    assert report.status == CapabilityStatus.READY
    assert len(report.missing_requirements) == 0


# ==============================================================================
# 4. Resource Discovery (Properties, Objects, Pipelines)
# ==============================================================================

def test_hubspot_resource_discovery_properties_and_objects():
    """Verify discovering standard & custom properties and CRM objects."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        credentials={"access_token": "live_token"},
    )

    mock_client = MagicMock()
    mock_p1 = MagicMock()
    mock_p1.name = "firstname"
    mock_p1.label = "First Name"
    mock_p1.type = "string"
    mock_p1.field_type = "text"
    mock_p1.hubspot_defined = True
    mock_p1.group_name = "contactinformation"

    mock_p2 = MagicMock()
    mock_p2.name = "dietary_preference_custom"
    mock_p2.label = "Dietary Preferences"
    mock_p2.type = "string"
    mock_p2.field_type = "text"
    mock_p2.hubspot_defined = False  # Custom property!
    mock_p2.group_name = "custom_fields"

    mock_client.crm.properties.core_api.get_all.return_value = MagicMock(results=[mock_p1, mock_p2])

    with patch.object(adapter, "_get_client", return_value=mock_client):
        # 1. Properties
        props = adapter.discover_resources("properties")
        assert len(props) == 2
        assert props[0].resource_id == "firstname"
        assert props[0].metadata["isCustom"] is False
        assert props[1].resource_id == "dietary_preference_custom"
        assert props[1].metadata["isCustom"] is True

        # 2. Objects
        objects = adapter.discover_resources("objects")
        obj_ids = [o.resource_id for o in objects]
        assert "contacts" in obj_ids
        assert "deals" in obj_ids
        assert "notes" in obj_ids
        assert "tasks" in obj_ids


# ==============================================================================
# 5. Configurable Deduplication & Strict Name-Only Safeguard
# ==============================================================================

def test_hubspot_duplicate_detection_email_then_phone():
    """Verify email_then_phone strategy checks email first, then phone."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_THEN_PHONE},
        credentials={"access_token": "live_token"},
    )

    # 1. Email matches -> returns contact immediately
    with patch.object(adapter, "search_contacts") as mock_search:
        mock_search.return_value = {"contacts": [{"id": "101", "properties": {"email": "alex@example.com"}}]}
        match = adapter.find_existing_contact({"email": "alex@example.com", "phone": "+14155552671"})
        assert match is not None
        assert match["id"] == "101"
        mock_search.assert_called_once_with(email="alex@example.com", limit=1)

    # 2. Email not found, phone matches -> checks phone and returns contact
    with patch.object(adapter, "search_contacts") as mock_search:
        # First call by email returns empty, second call by phone returns match
        mock_search.side_effect = [
            {"contacts": []},
            {"contacts": [{"id": "202", "properties": {"phone": "+14155552671"}}]},
        ]
        match = adapter.find_existing_contact({"email": "unknown@example.com", "phone": "+14155552671"})
        assert match is not None
        assert match["id"] == "202"
        assert mock_search.call_count == 2


def test_hubspot_duplicate_detection_name_alone_never_merges():
    """
    CRITICAL REQUIREMENT:
    'never merge two people solely because their names match.'
    If input only has name without verified email or phone, find_existing_contact MUST return None.
    """
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_THEN_PHONE},
        credentials={"access_token": "live_token"},
    )

    with patch.object(adapter, "search_contacts") as mock_search:
        # Caller supplies only name "John Smith"
        match = adapter.find_existing_contact({"name": "John Smith", "phone": "", "email": ""})
        assert match is None
        # Must not search or merge purely by name
        mock_search.assert_not_called()


def test_hubspot_duplicate_strategies_email_only_and_phone_only():
    """Verify EMAIL_ONLY and PHONE_ONLY matching strategies."""
    # 1. EMAIL_ONLY
    adapter_email = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": MatchingStrategy.EMAIL_ONLY},
        credentials={"access_token": "live_token"},
    )
    with patch.object(adapter_email, "search_contacts", return_value={"contacts": [{"id": "555"}]}) as mock_search:
        match = adapter_email.find_existing_contact({"email": "test@demo.com", "phone": "+14155550000"})
        assert match["id"] == "555"
        mock_search.assert_called_once_with(email="test@demo.com", limit=1)

    # 2. PHONE_ONLY
    adapter_phone = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"matching_strategy": MatchingStrategy.PHONE_ONLY},
        credentials={"access_token": "live_token"},
    )
    with patch.object(adapter_phone, "search_contacts", return_value={"contacts": [{"id": "777"}]}) as mock_search:
        match = adapter_phone.find_existing_contact({"email": "test@demo.com", "phone": "+14155550000"})
        assert match["id"] == "777"
        mock_search.assert_called_once_with(phone="+14155550000", limit=1)


# ==============================================================================
# 6. Custom Field Mapping & Missing Properties Resilience
# ==============================================================================

def test_hubspot_custom_field_mapping():
    """Verify custom field mappings translate receptionist caller attributes to HubSpot properties."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        configuration={
            "field_mappings": {
                "dietary_preference": "custom_dietary_needs",
                "patient_notes": "clinical_notes_custom",
            }
        },
        credentials={"access_token": "live_token"},
    )

    mapped = adapter._map_input_to_hubspot_properties({
        "first_name": "Eleanor",
        "last_name": "Vance",
        "phone": "+14155551234",
        "dietary_preference": "Gluten Free",
        "patient_notes": "Allergic to penicillin",
    })

    assert mapped["firstname"] == "Eleanor"
    assert mapped["lastname"] == "Vance"
    assert mapped["phone"] == "+14155551234"
    assert mapped["custom_dietary_needs"] == "Gluten Free"
    assert mapped["clinical_notes_custom"] == "Allergic to penicillin"


def test_hubspot_missing_properties_resilience():
    """
    Verify that if a custom property does not exist on the portal (HubSpot returns 400 INVALID_PROPERTY),
    the adapter catches the error, omits the invalid property, and retries successfully.
    """
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"ignore_unknown_properties": True},
        credentials={"access_token": "live_token"},
    )

    mock_client = MagicMock()
    # First call fails with INVALID_PROPERTY
    first_err = Exception('{"message": "Property \\"non_existent_field\\" does not exist"}')
    first_err.status = 400

    mock_resp = MagicMock()
    mock_resp.id = "99441"
    mock_resp.properties = {"firstname": "Sarah", "lastname": "Connor"}

    mock_client.crm.contacts.basic_api.create.side_effect = [first_err, mock_resp]

    with patch.object(adapter, "_get_client", return_value=mock_client):
        res = adapter.create_contact({
            "name": "Sarah Connor",
            "properties": {"non_existent_field": "some_value"},
        })

        assert res["contact_id"] == "99441"
        assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED
        # Verified that create was called twice (first with bad property, then omitted)
        assert mock_client.crm.contacts.basic_api.create.call_count == 2


# ==============================================================================
# 7. Contact Search, Pagination & Provider ID Normalization
# ==============================================================================

def test_hubspot_contact_search_and_pagination():
    """Verify search API formats filter groups, sorts, and handles cursor pagination."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        credentials={"access_token": "live_token"},
    )

    mock_client = MagicMock()
    item1 = MagicMock(id="hs_contact_101", properties={"email": "user1@demo.com"})
    item2 = MagicMock(id="hs_contact_102", properties={"email": "user2@demo.com"})
    paging_mock = MagicMock()
    paging_mock.next.after = "cursor_token_page_2"

    mock_resp = MagicMock(results=[item1, item2], total=50, paging=paging_mock)
    mock_client.crm.contacts.search_api.do_search.return_value = mock_resp

    with patch.object(adapter, "_get_client", return_value=mock_client):
        res = adapter.search_contacts(query="demo", limit=10, after="cursor_token_page_1")

        assert res["total"] == 50
        assert res["has_more"] is True
        assert res["next_cursor"] == "cursor_token_page_2"
        assert len(res["contacts"]) == 2
        # Normalization check: hs_contact_101 -> 101
        assert res["contacts"][0]["id"] == "101"
        assert res["contacts"][1]["id"] == "102"


def test_hubspot_contact_retrieval_and_id_normalization():
    """Verify contact retrieval normalizes provider IDs (e.g. hs_contact_33 -> 33)."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        credentials={"access_token": "live_token"},
    )

    mock_client = MagicMock()
    mock_resp = MagicMock(
        id="33",
        properties={"firstname": "Marcus", "lastname": "Aurelius", "email": "marcus@rome.org"},
        associations={},
    )
    mock_client.crm.contacts.basic_api.get_by_id.return_value = mock_resp

    with patch.object(adapter, "_get_client", return_value=mock_client):
        contact = adapter.get_contact("hs_contact_33")
        assert contact["id"] == "33"
        assert contact["properties"]["firstname"] == "Marcus"
        mock_client.crm.contacts.basic_api.get_by_id.assert_called_once_with(
            contact_id="33",
            properties=["firstname", "lastname", "email", "phone", "mobilephone", "company", "lifecyclestage"],
            associations=None,
        )


# ==============================================================================
# 8. Associations & Engagements (Notes, Tasks, Deals)
# ==============================================================================

def test_hubspot_associations_contacts_to_deals_and_notes():
    """Verify associating contact to deals or notes using CRM v4 basic_api.create_default."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        credentials={"access_token": "live_token"},
    )

    mock_client = MagicMock()
    with patch.object(adapter, "_get_client", return_value=mock_client):
        success = adapter.associate_records(
            from_object_type="contacts",
            from_object_id="hs_contact_101",
            to_object_type="deals",
            to_object_id="hs_deal_505",
        )

        assert success is True
        mock_client.crm.associations.v4.basic_api.create_default.assert_called_once_with(
            from_object_type="contacts",
            from_object_id="101",
            to_object_type="deals",
            to_object_id="505",
        )


def test_hubspot_engagements_scope_and_config_guards():
    """Verify notes, tasks, and deals require explicit object enablement and OAuth scopes."""
    adapter = HubspotCrmAdapter(
        "tenant_dental",
        configuration={"enabled_objects": ["contacts"]},  # Notes NOT enabled
        credentials={"access_token": "live_token", "scopes": ["crm.objects.contacts.read"]},
    )

    # 1. Fails when object is not enabled in configuration
    with pytest.raises(HubspotIntegrationException) as exc_info:
        adapter.create_note(contact_id="101", note_body="Caller requested callback.")
    assert exc_info.value.error.code == "HUBSPOT_OBJECT_DISABLED"

    # 2. Enable object, but missing OAuth scope fails
    adapter.configuration["enabled_objects"] = ["contacts", "notes"]
    with pytest.raises(HubspotIntegrationException) as exc_info2:
        adapter.create_note(contact_id="101", note_body="Caller requested callback.")
    assert exc_info2.value.error.category == ErrorCategory.PERMISSION_DENIED

    # 3. Grant scope -> succeeds!
    adapter.credentials["scopes"].append("crm.objects.notes.write")
    mock_client = MagicMock()
    mock_note_resp = MagicMock(id="note_9999")
    mock_client.crm.objects.basic_api.create.return_value = mock_note_resp

    with patch.object(adapter, "_get_client", return_value=mock_client), \
         patch.object(adapter, "associate_records", return_value=True):
        res = adapter.create_note(contact_id="101", note_body="Caller requested callback.")
        assert res["note_id"] == "9999"
        assert res["outcome"] == ExecutionOutcome.OPERATION_COMPLETED


# ==============================================================================
# 9. Rate Limiting & Error Normalization
# ==============================================================================

def test_hubspot_rate_limiting_and_retry_after():
    """Verify HTTP 429 maps to RATE_LIMITED with retry_after_seconds."""
    adapter = HubspotCrmAdapter("tenant_dental")

    mock_exc = Exception("Rate limit exceeded")
    mock_exc.status = 429
    mock_exc.headers = {"Retry-After": "3.5"}

    norm_err = adapter._normalize_hubspot_error(mock_exc)
    assert norm_err.category == ErrorCategory.RATE_LIMITED
    assert norm_err.is_retryable is True
    assert norm_err.retry_after_seconds == 3.5


def test_hubspot_error_normalization():
    """Verify standard HubSpot error status codes are normalized correctly."""
    adapter = HubspotCrmAdapter("tenant_dental")

    # 401 Unauthorized
    e401 = Exception("Expired token")
    e401.status = 401
    assert adapter._normalize_hubspot_error(e401).category == ErrorCategory.AUTHENTICATION_FAILED

    # 403 Forbidden / Scopes
    e403 = Exception("Missing scopes")
    e403.status = 403
    assert adapter._normalize_hubspot_error(e403).category == ErrorCategory.PERMISSION_DENIED

    # 404 Not Found
    e404 = Exception("Contact not found")
    e404.status = 404
    assert adapter._normalize_hubspot_error(e404).category == ErrorCategory.RESOURCE_NOT_FOUND

    # 409 Conflict
    e409 = Exception("Contact already exists")
    e409.status = 409
    assert adapter._normalize_hubspot_error(e409).category == ErrorCategory.CONFLICT

    # 500 Server Error
    e500 = Exception("HubSpot internal error")
    e500.status = 500
    norm_500 = adapter._normalize_hubspot_error(e500)
    assert norm_500.category == ErrorCategory.PROVIDER_UNAVAILABLE
    assert norm_500.is_retryable is True


# ==============================================================================
# 10. Multi-Tenant Isolation
# ==============================================================================

def test_hubspot_multi_tenant_isolation():
    """Verify complete isolation between Tenant A and Tenant B."""
    tenant_a = HubspotCrmAdapter(
        business_id="tenant_alpha",
        configuration={"portal_id": "11111", "matching_strategy": "email_only"},
        credentials={"access_token": "token_tenant_a", "client_secret": "secret_a"},
    )

    tenant_b = HubspotCrmAdapter(
        business_id="tenant_beta",
        configuration={"portal_id": "22222", "matching_strategy": "phone_only"},
        credentials={"access_token": "token_tenant_b", "client_secret": "secret_b"},
    )

    assert tenant_a.tenant_id == "tenant_alpha"
    assert tenant_b.tenant_id == "tenant_beta"
    assert tenant_a._get_access_token() != tenant_b._get_access_token()
    assert tenant_a._get_matching_strategy() == "email_only"
    assert tenant_b._get_matching_strategy() == "phone_only"
    assert tenant_a.configuration["portal_id"] == "11111"
    assert tenant_b.configuration["portal_id"] == "22222"


# ==============================================================================
# 11. Webhook Signature Verification (v3 HMAC-SHA256 & Replay Protection)
# ==============================================================================

def test_hubspot_webhook_signature_v3_verification():
    """Verify v3 HMAC-SHA256 signature verification over method + url + body + timestamp."""
    client_secret = "hs_client_sec_test_99"
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        credentials={"client_secret": client_secret},
    )

    raw_body = b'[{"eventId": 12345, "subscriptionType": "contact.creation", "objectId": 101}]'
    notification_url = "https://api.answerly.ai/api/v1/integrations/webhooks/hubspot"
    http_method = "POST"
    now_ms = str(int(time.time() * 1000))

    source_bytes = (
        http_method.encode("utf-8")
        + notification_url.encode("utf-8")
        + raw_body
        + now_ms.encode("utf-8")
    )
    expected_sig = base64.b64encode(
        hmac.new(client_secret.encode("utf-8"), source_bytes, hashlib.sha256).digest()
    ).decode("utf-8")

    headers = {
        "x-hubspot-signature-v3": expected_sig,
        "x-hubspot-request-timestamp": now_ms,
    }

    # 1. Valid signature passes
    assert adapter.verify_webhook_signature(raw_body, headers, notification_url, http_method) is True

    # 2. Tampered body fails
    assert adapter.verify_webhook_signature(b"tampered", headers, notification_url, http_method) is False

    # 3. Old timestamp (> 5 minutes) fails replay check
    old_headers = dict(headers)
    old_headers["x-hubspot-request-timestamp"] = str(int(time.time() * 1000) - 400000)
    assert adapter.verify_webhook_signature(raw_body, old_headers, notification_url, http_method) is False


def test_hubspot_webhook_handling():
    """Verify handling HubSpot webhook delivers deduplication event ID."""
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        credentials={"client_secret": "test_sec"},
    )

    wh_req = WebhookRequest(
        provider_id="hubspot",
        headers={},
        raw_body=b'[{"eventId": 987654, "subscriptionType": "contact.creation", "objectId": 101}]',
        parsed_json={"events": [{"eventId": 987654, "subscriptionType": "contact.creation", "objectId": 101}]},
        url="https://api.answerly.ai/api/v1/integrations/webhooks/hubspot",
    )

    result = adapter.handle_webhook(wh_req)
    assert result.success is True
    assert result.event_id == "987654"
    assert result.event_type == "contact.creation"


# ==============================================================================
# 12. Capability Execution via execute() Contract
# ==============================================================================

def test_hubspot_capability_execution_get_and_create():
    """Verify execute() dispatches GET_CUSTOMER and CREATE_OR_UPDATE_CUSTOMER."""
    adapter = HubspotCrmAdapter(
        business_id="tenant_dental",
        credentials={"access_token": "test_token_mock"},
    )
    ctx = ExecutionContext(
        tenant_id="tenant_dental",
        business_id="tenant_dental",
        tool_id="crm_tool",
        provider_id="hubspot",
        correlation_id="corr_hs_001",
    )

    # 1. GET_CUSTOMER
    get_res = adapter.execute(
        CapabilityType.GET_CUSTOMER,
        {"email": "alex@example.com"},
        ctx,
    )
    assert get_res.success is True
    assert get_res.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert get_res.data["email"] == "alex@example.com"
    assert get_res.data["provider_id"] == "hubspot"

    # 2. CREATE_OR_UPDATE_CUSTOMER
    create_res = adapter.execute(
        CapabilityType.CREATE_OR_UPDATE_CUSTOMER,
        {"name": "Clara Oswald", "phone": "+14155558822", "email": "clara@tardis.org"},
        ctx,
    )
    assert create_res.success is True
    assert create_res.outcome == ExecutionOutcome.OPERATION_COMPLETED
    assert create_res.data["name"] == "Clara Oswald"
    assert create_res.data["hubspot_id"] is not None
