"""
Exotel Telephony Adapter & AgentStream WebSocket Protocol Implementation.
Implements the official Exotel AgentStream / Voicebot Applet bidirectional protocol:
- Event schemas: connected, start, media, dtmf, mark, clear, stop
- Linear PCM (16-bit mono) audio validation (8000, 16000, 24000 Hz)
- Outbound media/mark/clear frame builders
- X-Exotel-Signature (HMAC-SHA256) and HTTP Basic Auth handshake verification
"""

from typing import Optional, Dict, Any, List, Union, Tuple
import base64
import hashlib
import hmac
import json
import logging
import uuid
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.database.models import utcnow
from backend.voice.events import (
    InboundCallEvent,
    CallControlResult,
    ProviderCapabilities,
    CallStatus,
)
from backend.voice.providers.base import BaseTelephonyProvider

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Audio Constraints & Encodings (Official Exotel Spec)
# ------------------------------------------------------------------------------

SUPPORTED_ENCODINGS = {
    "audio/x-raw",
    "audio/x-l16",
    "linear16",
    "slin",
    "pcm",
    "l16",
}

SUPPORTED_SAMPLE_RATES = {8000, 16000, 24000}
EXOTEL_CHUNK_MULTIPLE_BYTES = 320  # Multiple of 320 bytes (20ms at 8kHz, 16-bit mono)
MIN_CHUNK_BYTES = 3200             # 3.2 KB minimum documented chunk
MAX_CHUNK_BYTES = 102400           # 100 KB maximum documented chunk


# ------------------------------------------------------------------------------
# Typed Exotel WebSocket Event Schemas
# ------------------------------------------------------------------------------

class ExotelMediaFormat(BaseModel):
    """Audio format specification sent in Exotel 'start' event."""
    encoding: str = Field("audio/x-raw", description="Audio encoding (e.g. audio/x-raw, audio/x-l16)")
    sample_rate: Union[str, int] = Field("8000", description="Sample rate in Hz (8000, 16000, 24000)")
    bit_rate: Optional[Union[str, int]] = Field("16", description="Bit rate (16-bit)")
    channels: Optional[int] = Field(1, description="Number of channels (1 for mono)")

    @property
    def sample_rate_int(self) -> int:
        try:
            return int(self.sample_rate)
        except (ValueError, TypeError):
            return 8000


class ExotelStartData(BaseModel):
    """Metadata block delivered in Exotel 'start' event."""
    stream_sid: str = Field(..., description="Unique media stream identifier (prefixed with MZ)")
    call_sid: str = Field(..., description="Unique telephony call identifier (prefixed with CA)")
    account_sid: Optional[str] = Field(None, description="Exotel Account SID")
    from_: Optional[str] = Field(None, alias="from", description="Caller phone number")
    to: str = Field(..., description="Called virtual phone number (Exophone)")
    custom_parameters: Dict[str, Any] = Field(default_factory=dict, description="Custom parameters passed from flow")
    media_format: Optional[ExotelMediaFormat] = Field(None, description="Audio format configuration")

    model_config = {
        "populate_by_name": True,
    }


class ExotelMediaData(BaseModel):
    """Audio data packet payload sent in Exotel 'media' event."""
    chunk: Optional[Union[str, int]] = Field(None, description="Incremental audio chunk sequence")
    timestamp: Optional[Union[str, int]] = Field(None, description="Stream timestamp in milliseconds")
    payload: str = Field(..., description="Base64-encoded raw 16-bit Linear PCM audio")


class ExotelStopData(BaseModel):
    """Metadata delivered in Exotel 'stop' event."""
    call_sid: Optional[str] = Field(None, description="Call SID")
    account_sid: Optional[str] = Field(None, description="Account SID")


class ExotelMarkData(BaseModel):
    """Marker label delivered in Exotel 'mark' event."""
    name: str = Field(..., description="Playback marker identifier")


class ExotelDtmfData(BaseModel):
    """Keypad digit delivered in Exotel 'dtmf' event."""
    digit: str = Field(..., description="DTMF digit pressed (0-9, *, #)")


class ExotelWebSocketMessage(BaseModel):
    """
    Normalized representation of any incoming or outgoing Exotel AgentStream WebSocket message.
    Supported events: connected, start, media, dtmf, mark, clear, stop.
    """
    event: str = Field(..., description="Event type: connected, start, media, dtmf, mark, clear, stop")
    sequence_number: Optional[Union[str, int]] = Field(None, description="Message sequence counter")
    stream_sid: Optional[str] = Field(None, description="Active stream SID")
    start: Optional[ExotelStartData] = None
    media: Optional[ExotelMediaData] = None
    stop: Optional[ExotelStopData] = None
    mark: Optional[ExotelMarkData] = None
    dtmf: Optional[ExotelDtmfData] = None


# ------------------------------------------------------------------------------
# Outbound Message Builders (Server -> Exotel)
# ------------------------------------------------------------------------------

def build_exotel_media_message(stream_sid: str, payload_base64: str) -> str:
    """
    Construct outgoing audio media JSON frame for Exotel.
    Payload must be Base64-encoded 16-bit Linear PCM mono matching negotiated sample rate.
    """
    return json.dumps({
        "event": "media",
        "stream_sid": stream_sid,
        "media": {
            "payload": payload_base64
        }
    })


def build_exotel_mark_message(stream_sid: str, name: str, sequence_number: Optional[int] = None) -> str:
    """
    Construct outgoing mark JSON frame to track audio playback milestones.
    """
    msg = {
        "event": "mark",
        "stream_sid": stream_sid,
        "mark": {
            "name": name
        }
    }
    if sequence_number is not None:
        msg["sequence_number"] = sequence_number
    return json.dumps(msg)


def build_exotel_clear_message(stream_sid: str) -> str:
    """
    Construct outgoing clear JSON frame to flush Exotel's playback buffer on caller barge-in.
    """
    return json.dumps({
        "event": "clear",
        "stream_sid": stream_sid
    })


# ------------------------------------------------------------------------------
# Audio Format Validator
# ------------------------------------------------------------------------------

def validate_exotel_audio_format(media_format: Optional[ExotelMediaFormat]) -> Tuple[bool, Optional[str]]:
    """
    Validate that incoming Exotel media_format matches expected Linear PCM specifications.
    Returns (True, None) if valid, or (False, error_reason) if unsupported.
    """
    if not media_format:
        # Default to 8000 Hz raw PCM if unspecified
        return True, None

    encoding = media_format.encoding.lower().strip()
    if encoding not in SUPPORTED_ENCODINGS:
        return False, f"Unsupported audio encoding: '{media_format.encoding}'. Expected raw Linear PCM (e.g., audio/x-raw, audio/x-l16)."

    sample_rate = media_format.sample_rate_int
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        return False, f"Unsupported sample rate: {sample_rate} Hz. Exotel AgentStream supports 8000, 16000, or 24000 Hz."

    return True, None


# ------------------------------------------------------------------------------
# Exotel Telephony Provider Implementation
# ------------------------------------------------------------------------------

class ExotelTelephonyProvider(BaseTelephonyProvider):
    """
    Official Exotel Telephony Adapter supporting:
    - Passthru HTTP webhooks with X-Exotel-Signature verification (HMAC-SHA256)
    - AgentStream WebSocket protocol handshakes with HTTP Basic Auth verification
    - Inbound call event normalization
    - Bidirectional audio streaming lifecycle
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        api_key: Optional[str] = None,
        api_token: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.account_sid = account_sid or settings.EXOTEL_ACCOUNT_SID
        self.api_key = api_key or settings.EXOTEL_API_KEY
        self.api_token = api_token or settings.EXOTEL_API_TOKEN
        self._explicit_webhook_secret = webhook_secret
        self.webhook_secret = webhook_secret or settings.EXOTEL_WEBHOOK_SECRET

    @property
    def provider_name(self) -> str:
        return "exotel"

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Exotel AgentStream telephony capabilities."""
        return ProviderCapabilities(
            name="exotel",
            supports_streaming_stt=True,
            supports_streaming_tts=True,
            supports_barge_in=True,
            supports_dtmf=True,
            supports_call_recording=True,
            supported_audio_codecs=["audio/x-raw", "audio/x-l16", "linear16", "slin"],
        )

    def parse_inbound_webhook(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> InboundCallEvent:
        """
        Normalize Exotel inbound webhook payload (Passthru applet or WebSocket start event)
        into a standardized InboundCallEvent.
        """
        # 1. Handle WebSocket 'start' event if wrapped or passed directly
        if "start" in payload and isinstance(payload["start"], dict):
            start_data = payload["start"]
            call_sid = start_data.get("call_sid") or payload.get("stream_sid", "exotel_stream")
            stream_sid = start_data.get("stream_sid")
            called_number = start_data.get("to") or ""
            caller_number = start_data.get("from")
            metadata = {
                "account_sid": start_data.get("account_sid"),
                "stream_sid": stream_sid,
                "custom_parameters": start_data.get("custom_parameters", {}),
                "media_format": start_data.get("media_format", {}),
            }
            return InboundCallEvent(
                provider_call_id=str(call_sid),
                provider_name=self.provider_name,
                called_number=str(called_number),
                caller_number=str(caller_number) if caller_number else None,
                call_status=CallStatus.INITIATED.value,
                correlation_id=stream_sid,
                timestamp=utcnow(),
                metadata=metadata,
            )

        # 2. Handle HTTP Passthru applet query or form payload
        call_sid = (
            payload.get("CallSid")
            or payload.get("call_sid")
            or payload.get("Sid")
            or payload.get("provider_call_id")
            or f"exotel_{utcnow().timestamp()}"
        )
        called_number = (
            payload.get("To")
            or payload.get("CallTo")
            or payload.get("DialWhomNumber")
            or payload.get("called_number")
            or ""
        )
        caller_number = (
            payload.get("From")
            or payload.get("CallFrom")
            or payload.get("caller_number")
        )
        stream_sid = payload.get("stream_sid") or payload.get("StreamSid")

        metadata = {
            "account_sid": payload.get("AccountSid") or self.account_sid,
            "stream_sid": stream_sid,
            "call_type": payload.get("CallType", "inbound"),
            "digits": payload.get("Digits"),
            "custom_field": payload.get("CustomField"),
        }

        return InboundCallEvent(
            provider_call_id=str(call_sid),
            provider_name=self.provider_name,
            called_number=str(called_number),
            caller_number=str(caller_number) if caller_number else None,
            call_status=CallStatus.INITIATED.value,
            correlation_id=stream_sid or f"exo_corr_{uuid.uuid4().hex[:12]}",
            timestamp=utcnow(),
            metadata=metadata,
        )

    def verify_webhook_signature(
        self,
        payload: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verify incoming Exotel webhook signature using HMAC-SHA256.
        Exotel signs webhooks with header: 'X-Exotel-Signature: sha256=<signature>' or '<signature>'.
        """
        settings = get_settings()
        check_secret = secret or getattr(self, "_explicit_webhook_secret", None) or settings.EXOTEL_WEBHOOK_SECRET or self.webhook_secret
        if not check_secret:
            logger.warning("Exotel webhook signature check failed: No secret configured.")
            return False

        # Extract signature header case-insensitively
        sig_header = None
        for k, v in headers.items():
            if k.lower() in ("x-exotel-signature", "x-signature"):
                sig_header = v.strip()
                break

        if not sig_header:
            logger.warning("Exotel webhook signature missing: No 'X-Exotel-Signature' header provided.")
            return False

        # Support 'sha256=<hash>' prefix as well as raw hex
        provided_hash = sig_header
        if "=" in sig_header:
            parts = sig_header.split("=", 1)
            if parts[0].lower() != "sha256":
                logger.warning("Unsupported signature algorithm in X-Exotel-Signature: %s", parts[0])
                return False
            provided_hash = parts[1]

        computed = hmac.new(
            check_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed.lower(), provided_hash.lower())

    def verify_handshake_auth(
        self,
        headers: Dict[str, str],
        expected_key: Optional[str] = None,
        expected_token: Optional[str] = None,
    ) -> bool:
        """
        Verify WebSocket connection handshake using HTTP Basic Authentication:
        'Authorization: Basic base64(api_key:api_token)'
        Matches Exotel's documented wss://<key>:<token>@host/path connection behavior.
        """
        settings = get_settings()
        auth_key = expected_key or self.api_key or settings.EXOTEL_API_KEY
        auth_token = expected_token or self.api_token or settings.EXOTEL_API_TOKEN

        # If no credentials are configured, reject in production
        if not auth_key or not auth_token:
            logger.warning("Exotel handshake auth failed: Server has no API credentials configured.")
            return False

        auth_header = None
        for k, v in headers.items():
            if k.lower() == "authorization":
                auth_header = v.strip()
                break

        if not auth_header or not auth_header.lower().startswith("basic "):
            logger.warning("Exotel handshake auth failed: Missing or invalid 'Authorization: Basic' header.")
            return False

        encoded_creds = auth_header.split(" ", 1)[1].strip()
        try:
            decoded = base64.b64decode(encoded_creds).decode("utf-8")
            if ":" not in decoded:
                return False
            provided_key, provided_token = decoded.split(":", 1)
        except Exception:
            logger.warning("Failed to decode HTTP Basic Auth credentials (format error).")
            return False

        key_valid = hmac.compare_digest(auth_key, provided_key)
        token_valid = hmac.compare_digest(auth_token, provided_token)
        return key_valid and token_valid

    def accept_call(
        self,
        event: InboundCallEvent,
        greeting_text: Optional[str] = None,
    ) -> CallControlResult:
        """
        Signal acceptance of inbound call.
        For Exotel, returns HTTP 200 with optional custom instructions or queued greeting.
        """
        return CallControlResult(
            session_id=None,
            action="accept",
            message=greeting_text,
            status="accepted",
            metadata={
                "provider_call_id": event.provider_call_id,
                "provider_name": self.provider_name,
                "correlation_id": event.correlation_id,
            },
        )

    def reject_call(
        self,
        event: InboundCallEvent,
        reason: str = "busy",
    ) -> CallControlResult:
        """Signal rejection of inbound call."""
        return CallControlResult(
            session_id=None,
            action="reject",
            message=reason,
            status="rejected",
            metadata={
                "provider_call_id": event.provider_call_id,
                "provider_name": self.provider_name,
            },
        )

    def hangup_call(
        self,
        session_id: str,
        reason: str = "completed",
    ) -> CallControlResult:
        """Terminate call session."""
        return CallControlResult(
            session_id=session_id,
            action="hangup",
            message=reason,
            status="completed",
        )
