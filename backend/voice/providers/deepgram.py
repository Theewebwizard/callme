"""
Deepgram Speech-to-Text and Text-to-Speech streaming and batch providers.
Connects real-time audio streams between Exotel telephony and Deepgram speech APIs.
"""

from typing import Optional, Dict, Any, AsyncIterator, List
import asyncio
import json
import logging
import uuid
import httpx
import websockets

from backend.config import get_settings
from backend.database.models import utcnow
from backend.voice.audio import resample_pcm16, validate_pcm16_chunk, pad_pcm16_to_multiple
from backend.voice.events import TranscriptEvent

logger = logging.getLogger(__name__)

DEEPGRAM_LISTEN_WS_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_LISTEN_REST_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_SPEAK_WS_URL = "wss://api.deepgram.com/v1/speak"
DEEPGRAM_SPEAK_REST_URL = "https://api.deepgram.com/v1/speak"


class DeepgramSTTStream:
    """
    Asynchronous streaming session for Deepgram live Speech-to-Text via WebSockets.
    Transmits continuous Linear PCM audio chunks and streams back interim and final transcripts.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        sample_rate: Optional[int] = None,
        endpointing_ms: Optional[int] = None,
        session_id: Optional[str] = None,
        ws_client: Any = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.DEEPGRAM_API_KEY or ""
        self.model = model or settings.DEEPGRAM_STT_MODEL
        self.language = language or settings.DEEPGRAM_STT_LANGUAGE
        self.sample_rate = sample_rate or settings.DEEPGRAM_STT_SAMPLE_RATE
        self.endpointing_ms = endpointing_ms or settings.DEEPGRAM_STT_ENDPOINTING_MS
        self.session_id = session_id or "voice_stream"

        self._ws = ws_client
        self._is_closed = False
        self._connected = False
        self._accumulated_text = ""

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._is_closed

    async def connect(self) -> None:
        """Establish WebSocket connection to Deepgram streaming STT API."""
        if self._ws is not None:
            self._connected = True
            return

        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY is not configured.")

        params = (
            f"?model={self.model}"
            f"&language={self.language}"
            f"&encoding=linear16"
            f"&sample_rate={self.sample_rate}"
            f"&channels=1"
            f"&endpointing={self.endpointing_ms}"
            f"&interim_results=true"
            f"&smart_format=true"
            f"&vad_events=true"
        )
        url = f"{DEEPGRAM_LISTEN_WS_URL}{params}"
        headers = {
            "Authorization": f"Token {self.api_key}",
        }

        try:
            self._ws = await websockets.connect(url, extra_headers=headers)
            self._connected = True
            self._is_closed = False
            logger.info("Deepgram STT streaming session connected (model=%s, rate=%d)", self.model, self.sample_rate)
        except Exception as e:
            logger.error("Failed to connect to Deepgram STT streaming endpoint: %s", type(e).__name__)
            self._connected = False
            raise

    async def send_audio(self, audio_chunk: bytes) -> None:
        """
        Send raw 16-bit Linear PCM audio bytes to Deepgram.
        """
        if self._is_closed or not self._ws:
            return

        is_valid, err = validate_pcm16_chunk(audio_chunk)
        if not is_valid:
            logger.debug("Skipping invalid audio chunk for STT: %s", err)
            return

        try:
            await self._ws.send(audio_chunk)
        except Exception as err:
            logger.warning("Error transmitting audio frame to Deepgram STT: %s", str(err))
            self._is_closed = True

    async def receive_event(self, timeout: Optional[float] = None) -> Optional[TranscriptEvent]:
        """
        Receive and parse the next message from Deepgram.
        Returns TranscriptEvent if speech is detected; None for keepalive/metadata/silence.
        """
        if self._is_closed or not self._ws:
            return None

        try:
            if timeout is not None:
                message = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            else:
                message = await self._ws.recv()
        except asyncio.TimeoutError:
            return None
        except Exception as err:
            logger.info("Deepgram STT connection closed or ended: %s", str(err))
            self._is_closed = True
            return None

        if isinstance(message, bytes):
            return None

        try:
            data = json.loads(message)
        except Exception:
            return None

        msg_type = data.get("type", "")

        if msg_type == "Results":
            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                return None

            primary = alternatives[0]
            transcript_text = primary.get("transcript", "").strip()
            confidence = float(primary.get("confidence", 1.0))
            is_final = bool(data.get("is_final", False))
            speech_final = bool(data.get("speech_final", False))

            if not transcript_text:
                return None

            if is_final:
                if speech_final:
                    # Utterance complete: merge any prior partial segments with this final segment
                    if self._accumulated_text:
                        full_text = f"{self._accumulated_text} {transcript_text}".strip()
                        self._accumulated_text = ""
                    else:
                        full_text = transcript_text

                    return TranscriptEvent(
                        session_id=self.session_id,
                        turn_id=str(uuid.uuid4()),
                        text=full_text,
                        is_final=True,
                        speech_final=True,
                        confidence=confidence,
                        language=self.language,
                        speaker="customer",
                        timestamp=utcnow(),
                    )
                else:
                    # Partial finalized segment: accumulate and yield with speech_final=False
                    if self._accumulated_text:
                        self._accumulated_text = f"{self._accumulated_text} {transcript_text}".strip()
                    else:
                        self._accumulated_text = transcript_text

                    return TranscriptEvent(
                        session_id=self.session_id,
                        turn_id=str(uuid.uuid4()),
                        text=self._accumulated_text,
                        is_final=True,
                        speech_final=False,
                        confidence=confidence,
                        language=self.language,
                        speaker="customer",
                        timestamp=utcnow(),
                    )
            else:
                # Interim hypothesis for real-time barge-in detection
                interim_display = f"{self._accumulated_text} {transcript_text}".strip() if self._accumulated_text else transcript_text
                return TranscriptEvent(
                    session_id=self.session_id,
                    turn_id=str(uuid.uuid4()),
                    text=interim_display,
                    is_final=False,
                    speech_final=False,
                    confidence=confidence,
                    language=self.language,
                    speaker="customer",
                    timestamp=utcnow(),
                )

        elif msg_type == "UtteranceEnd":
            # UtteranceEnd signals speaker finished speaking
            if self._accumulated_text.strip():
                full_text = self._accumulated_text.strip()
                self._accumulated_text = ""
                return TranscriptEvent(
                    session_id=self.session_id,
                    turn_id=str(uuid.uuid4()),
                    text=full_text,
                    is_final=True,
                    speech_final=True,
                    confidence=1.0,
                    language=self.language,
                    speaker="customer",
                    timestamp=utcnow(),
                )
            return None

        return None

    async def close(self) -> None:
        """Gracefully close the Deepgram streaming STT connection."""
        if self._is_closed:
            return
        self._is_closed = True
        self._connected = False
        if self._ws:
            try:
                # Send CloseStream control frame
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass


class DeepgramSTTProvider:
    """
    Deepgram Speech-to-Text provider implementing SpeechToTextProvider protocol.
    Supports one-off batch transcription via REST and real-time streaming via WebSocket.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.DEEPGRAM_API_KEY or ""

    @property
    def provider_name(self) -> str:
        return "deepgram_stt"

    def create_stream(
        self,
        session_id: str,
        sample_rate: Optional[int] = None,
        language: Optional[str] = None,
        ws_client: Any = None,
    ) -> DeepgramSTTStream:
        """Create a new streaming STT session."""
        return DeepgramSTTStream(
            api_key=self.api_key,
            sample_rate=sample_rate,
            language=language,
            session_id=session_id,
            ws_client=ws_client,
        )

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en",
    ) -> TranscriptEvent:
        """
        Synchronous / batch transcription of audio bytes via Deepgram Listen REST API.
        Fails safely if provider is not configured or network request fails.
        """
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured.")

        settings = get_settings()
        sample_rate = settings.DEEPGRAM_STT_SAMPLE_RATE

        # Validate PCM audio buffer
        is_valid, err = validate_pcm16_chunk(audio_bytes)
        if not is_valid:
            logger.warning("Invalid audio chunk provided for Deepgram STT transcribe: %s", err)
            return TranscriptEvent(
                session_id="transcribe_error",
                text="",
                is_final=True,
                confidence=0.0,
                language=language,
                speaker="customer",
            )

        params = {
            "model": settings.DEEPGRAM_STT_MODEL,
            "language": language or settings.DEEPGRAM_STT_LANGUAGE,
            "encoding": "linear16",
            "sample_rate": sample_rate,
            "channels": 1,
            "smart_format": "true",
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/raw",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    DEEPGRAM_LISTEN_REST_URL,
                    params=params,
                    headers=headers,
                    content=audio_bytes,
                )
                if resp.status_code != 200:
                    logger.error("Deepgram STT REST returned status %d", resp.status_code)
                    return TranscriptEvent(
                        session_id="transcribe_failed",
                        text="",
                        is_final=True,
                        confidence=0.0,
                        language=language,
                        speaker="customer",
                    )

                data = resp.json()
                channel = data.get("results", {}).get("channels", [{}])[0]
                alts = channel.get("alternatives", [{}])
                transcript_text = alts[0].get("transcript", "").strip() if alts else ""
                confidence = float(alts[0].get("confidence", 1.0)) if alts else 0.0

                return TranscriptEvent(
                    session_id="batch_stt",
                    text=transcript_text,
                    is_final=True,
                    confidence=confidence,
                    language=language,
                    speaker="customer",
                )
        except Exception as e:
            logger.error("Deepgram STT REST request failed: %s", str(e))
            return TranscriptEvent(
                session_id="transcribe_error",
                text="",
                is_final=True,
                confidence=0.0,
                language=language,
                speaker="customer",
            )


class DeepgramTTSProvider:
    """
    Deepgram Text-to-Speech provider implementing TextToSpeechProvider protocol.
    Supports both batch synthesis and real-time chunked streaming over WebSockets.
    Outputs Linear PCM 16-bit mono audio at the configured sample rate (8000 Hz / 16000 Hz).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.DEEPGRAM_API_KEY or ""
        self.model = settings.DEEPGRAM_TTS_MODEL
        self.sample_rate = settings.DEEPGRAM_TTS_SAMPLE_RATE

    @property
    def provider_name(self) -> str:
        return "deepgram_tts"

    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        language: str = "en",
    ) -> bytes:
        """
        Synthesize speech from text via Deepgram Speak REST API.
        Returns raw Linear PCM 16-bit mono audio bytes.
        """
        if not text or not text.strip():
            return b""

        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured.")

        model = voice_id or self.model
        params = {
            "model": model,
            "encoding": "linear16",
            "sample_rate": self.sample_rate,
            "container": "none",
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    DEEPGRAM_SPEAK_REST_URL,
                    params=params,
                    headers=headers,
                    json={"text": text},
                )
                if resp.status_code != 200:
                    logger.error("Deepgram TTS REST failed with status %d", resp.status_code)
                    return b""

                audio_bytes = resp.content
                # Ensure 16-bit byte alignment
                if len(audio_bytes) % 2 != 0:
                    audio_bytes = audio_bytes[:-(len(audio_bytes) % 2)]
                return audio_bytes
        except Exception as e:
            logger.error("Deepgram TTS REST synthesis exception: %s", str(e))
            return b""

    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        sample_rate: Optional[int] = None,
        cancellation_token: Optional[asyncio.Event] = None,
        ws_client: Any = None,
    ) -> AsyncIterator[bytes]:
        """
        Synthesize speech streamingly via Deepgram Speak WebSocket API.
        Yields raw 16-bit Linear PCM audio chunks.
        Honors cancellation_token for immediate barge-in interruption.
        """
        if not text or not text.strip():
            return

        model = voice_id or self.model
        rate = sample_rate or self.sample_rate

        ws = ws_client
        should_close_ws = False

        if ws is None:
            if not self.api_key:
                raise RuntimeError("DEEPGRAM_API_KEY is not configured.")

            url = f"{DEEPGRAM_SPEAK_WS_URL}?model={model}&encoding=linear16&sample_rate={rate}&container=none"
            headers = {"Authorization": f"Token {self.api_key}"}
            try:
                ws = await websockets.connect(url, extra_headers=headers)
                should_close_ws = True
            except Exception as e:
                logger.error("Failed to connect to Deepgram TTS streaming WebSocket: %s", type(e).__name__)
                # Fallback to batch REST synthesis
                batch_audio = self.synthesize(text, voice_id=model)
                if batch_audio:
                    yield batch_audio
                return

        try:
            # Send text to speak and flush instruction
            await ws.send(json.dumps({"type": "Speak", "text": text}))
            await ws.send(json.dumps({"type": "Flush"}))

            while True:
                # Check for caller barge-in cancellation
                if cancellation_token and cancellation_token.is_set():
                    logger.info("Deepgram TTS stream cancelled due to barge-in.")
                    try:
                        await ws.send(json.dumps({"type": "Clear"}))
                    except Exception:
                        pass
                    break

                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    break
                except Exception:
                    break

                if isinstance(message, bytes):
                    # Raw PCM audio chunk
                    if len(message) > 0:
                        yield message
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")
                        if msg_type in ["Flushed", "Cleared"]:
                            break
                    except Exception:
                        pass
        finally:
            if should_close_ws and ws:
                try:
                    await ws.send(json.dumps({"type": "Close"}))
                    await ws.close()
                except Exception:
                    pass
