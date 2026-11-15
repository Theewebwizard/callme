"""
Gnani.ai Vachana Voice Providers (Prisma STT & Timbre TTS).
Enables sovereign Indic speech recognition and high-fidelity neural voice synthesis.
"""

from typing import Optional, Dict, Any, List
import io
import json
import logging
import urllib.request
import urllib.error

from backend.config import get_settings
from backend.voice.events import TranscriptEvent
from backend.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider

logger = logging.getLogger(__name__)

GNANI_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Supported Indic Languages on Gnani Vachana Platform
GNANI_SUPPORTED_LANGUAGES = [
    {"code": "indic-auto", "name": "Auto-Detect / Code-Switching", "native": "स्वचालित / All Indic"},
    {"code": "hi-IN", "name": "Hindi", "native": "हिन्दी"},
    {"code": "en-IN", "name": "English (India)", "native": "Indian English"},
    {"code": "bn-IN", "name": "Bengali", "native": "বাংলা"},
    {"code": "gu-IN", "name": "Gujarati", "native": "ગુજરાતી"},
    {"code": "kn-IN", "name": "Kannada", "native": "ಕನ್ನಡ"},
    {"code": "ml-IN", "name": "Malayalam", "native": "മലയാളം"},
    {"code": "mr-IN", "name": "Marathi", "native": "मराठी"},
    {"code": "pa-IN", "name": "Punjabi", "native": "ਪੰਜਾਬੀ"},
    {"code": "ta-IN", "name": "Tamil", "native": "தமிழ்"},
    {"code": "te-IN", "name": "Telugu", "native": "తెలుగు"},
    {"code": "as-IN", "name": "Assamese", "native": "অসমীয়া"},
]

GNANI_LANGUAGE_CODES = [lang["code"] for lang in GNANI_SUPPORTED_LANGUAGES]

# Supported Neural Voices in Timbre v2.5
GNANI_VOICES = [
    "Nalini", "Bhavna", "Yashvi", "Urmila", "Jwala", "Chitra", "Ambuja",
    "Deepak", "Roopesh", "Vikrant", "Hemraj", "Jalaj", "Omkar", "Aarohi",
    "Bhavini", "Charvi", "Eishani", "Falguni", "Gauri", "Iravati", "Janaki",
    "Kamakshi", "Madhuri", "Radhika", "Shweta", "Tanvi", "Vidya", "Wamika",
    "Yamini", "Abhimanyu", "Chirag", "Deven", "Farhan", "Jatin", "Kartik",
    "Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish", "Asmita",
    "Trisha", "Brinda", "Vedika", "Noopur", "Oviya"
]


class GnaniSTTProvider:
    """
    Speech-to-Text provider backed by Gnani.ai's Prisma v3.0 / v2.5 models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or getattr(settings, "GNANI_API_KEY", "") or ""
        self.model = model or getattr(settings, "GNANI_STT_MODEL", "prisma-v3.0")
        self.api_base = (api_base or getattr(settings, "GNANI_API_BASE", "https://api.vachana.ai")).rstrip("/")

    @property
    def provider_name(self) -> str:
        return "gnani"

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "hi-IN",
        filename: str = "audio.wav",
    ) -> TranscriptEvent:
        """
        Transcribe audio buffer to text using Gnani Prisma ASR.
        """
        if not audio_bytes:
            return TranscriptEvent(session_id="", text="", is_final=True, confidence=0.0)

        if not self.api_key:
            logger.warning("Gnani API key missing; cannot transcribe audio.")
            return TranscriptEvent(session_id="", text="", is_final=True, confidence=0.0)

        # Normalize language code to supported set
        lang_code = language if language in GNANI_LANGUAGE_CODES else "hi-IN"

        url = f"{self.api_base}/stt/v3"
        boundary = "----GnaniMultipartBoundary" + "X" * 16

        body = io.BytesIO()
        # Audio file field
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(f'Content-Disposition: form-data; name="audio_file"; filename="{filename}"\r\n'.encode("utf-8"))
        body.write(b"Content-Type: audio/wav\r\n\r\n")
        body.write(audio_bytes)
        body.write(b"\r\n")

        # Language code
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="language_code"\r\n\r\n')
        body.write(f"{lang_code}\r\n".encode("utf-8"))

        # Model field
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.write(f"{self.model}\r\n".encode("utf-8"))

        body.write(f"--{boundary}--\r\n".encode("utf-8"))
        payload_data = body.getvalue()

        headers = {
            "X-API-Key-ID": self.api_key,
            "User-Agent": GNANI_USER_AGENT,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        req = urllib.request.Request(url, data=payload_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    transcript = data.get("transcript", "").strip()
                    detected_lang = data.get("detected_language_code") or lang_code
                    logger.info("Gnani STT success: '%s' (lang: %s)", transcript, detected_lang)
                    return TranscriptEvent(
                        session_id="",
                        text=transcript,
                        is_final=True,
                        confidence=0.98 if transcript else 0.0,
                    )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error("Gnani STT HTTP error %d: %s", e.code, err_body)
        except Exception as e:
            logger.error("Gnani STT exception: %s", str(e))

        return TranscriptEvent(session_id="", text="", is_final=True, confidence=0.0)


class GnaniTTSProvider:
    """
    Text-to-Speech provider backed by Gnani.ai's Timbre v2.5 models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or getattr(settings, "GNANI_API_KEY", "") or ""
        self.model = model or getattr(settings, "GNANI_TTS_MODEL", "timbre-v2.5")
        self.default_voice = voice or getattr(settings, "GNANI_TTS_VOICE", "Nalini")
        self.api_base = (api_base or getattr(settings, "GNANI_API_BASE", "https://api.vachana.ai")).rstrip("/")

    @property
    def provider_name(self) -> str:
        return "gnani"

    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        language: str = "hi-IN",
        sample_rate: int = 24000,
    ) -> bytes:
        """
        Synthesize text into WAV audio bytes using Gnani Timbre.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return b""

        if not self.api_key:
            logger.warning("Gnani API key missing; cannot synthesize audio.")
            return b""

        voice = voice_id or self.default_voice
        if voice not in GNANI_VOICES:
            voice = "Nalini"

        lang_code = language if language in GNANI_LANGUAGE_CODES else "hi-IN"

        url = f"{self.api_base}/api/v1/tts/inference"
        payload = {
            "text": clean_text,
            "model": self.model,
            "voice": voice,
            "language": lang_code,
            "speed": 1.0,
            "audio_config": {
                "encoding": "linear_pcm",
                "container": "wav",
                "sample_rate": sample_rate,
            },
        }

        headers = {
            "X-API-Key-ID": self.api_key,
            "User-Agent": GNANI_USER_AGENT,
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    audio_bytes = resp.read()
                    logger.info("Gnani TTS success: %d bytes synthesized for '%s'", len(audio_bytes), clean_text[:30])
                    return audio_bytes
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error("Gnani TTS HTTP error %d: %s", e.code, err_body)
        except Exception as e:
            logger.error("Gnani TTS exception: %s", str(e))

        return b""
