"""
Provider Webhook Ingestion Router.
Receives incoming HTTP callbacks from telephony, messaging, payments, and calendar providers.
Enforces cryptographic signature verification, replay deduplication, and tenant routing.
"""

from fastapi import APIRouter, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import logging

from backend.integrations.models import WebhookRequest, WebhookResult
from backend.integrations.manager import get_integration_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Integrations Webhooks"])


@router.post("/{provider_id}", status_code=status.HTTP_200_OK)
async def ingest_provider_webhook(
    provider_id: str,
    request: Request,
):
    """
    Ingest and process incoming third-party webhook event.
    Verifies cryptographic signatures, deduplicates replay deliveries,
    and dispatches to provider adapter.
    """
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    url = str(request.url)

    # Attempt to parse json payload safely
    parsed_json: Optional[Dict[str, Any]] = None
    if "application/json" in headers.get("content-type", ""):
        try:
            parsed_json = await request.json()
        except Exception:
            parsed_json = None
    elif "application/x-www-form-urlencoded" in headers.get("content-type", ""):
        try:
            form_data = await request.form()
            parsed_json = dict(form_data)
        except Exception:
            parsed_json = None

    wh_request = WebhookRequest(
        provider_id=provider_id,
        headers=headers,
        raw_body=raw_body,
        parsed_json=parsed_json,
        url=url,
    )

    tenant_id = (
        request.query_params.get("business_id")
        or request.query_params.get("tenant_id")
        or headers.get("x-business-id")
        or headers.get("x-tenant-id")
    )
    if not tenant_id and parsed_json and isinstance(parsed_json, dict):
        tenant_id = parsed_json.get("business_id") or parsed_json.get("tenant_id")

    manager = get_integration_manager()
    result: WebhookResult = manager.handle_provider_webhook(provider_id, wh_request, tenant_id=tenant_id)

    if not result.success:
        logger.warning("Rejected webhook for provider %s: %s", provider_id, result.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message or "Webhook signature or validation failed.",
        )

    if result.is_duplicate:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "received": True,
                "status": "duplicate_ignored",
                "event_id": result.event_id,
            },
        )

    return {
        "received": True,
        "status": "processed",
        "event_id": result.event_id,
        "event_type": result.event_type,
    }
