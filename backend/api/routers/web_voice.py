"""
Web Voice Router for Browser-Based Direct AI Receptionist Calling.
Enables real-time voice conversations through web microphone without PSTN telephony.
"""

from typing import Optional, Dict, Any, List
import io
import time
import uuid
import base64
import logging
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from pydantic import BaseModel

from backend.config import get_settings
from backend.services.groq_service import get_groq_service
from backend.database.service import get_database_service, DatabaseService
from backend.voice.session_manager import DatabaseVoiceSessionManager
from backend.voice.orchestrator import VoiceTurnOrchestrator
from backend.voice.events import InboundCallEvent, TranscriptEvent
from backend.api.routers.voice import get_session_manager, get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice/web", tags=["Web Voice Phone"])


class WebCallStartRequest(BaseModel):
    business_id: str = "biz_spice_garden"


class WebCallHangupRequest(BaseModel):
    session_id: str


def detect_voice_for_text(text: str) -> str:
    """
    Detect appropriate neural voice based on language and script.
    Uses SwaraNeural for Hindi/Hinglish, and NeerjaNeural for Indian English.
    """
    if not text:
        return "en-IN-NeerjaNeural"

    # 1. Check for Devanagari script Unicode block (\u0900 to \u097F)
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "hi-IN-SwaraNeural"

    # 2. Check for common Roman Hindi / Hinglish keywords
    lower_words = set(text.lower().replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ").split())
    hindi_keywords = {
        "namaste", "dhanyavad", "shukriya", "aap", "aapka", "aapki", "aapke",
        "hum", "humare", "humari", "hai", "hain", "kya", "nahi", "nahin",
        "chahiye", "karunga", "karenge", "kijiye", "bataiye", "samay", "din",
        "kaise", "madad", "swagat", "shubh", "shukrawar", "somwar", "shanivar",
        "ravivar", "mangalwar", "budhwar", "guruwar", "bhaiya", "didi", "sahab",
        "sirji", "ji", "bilkul", "thik", "theek", "shyam", "dopahar", "subah",
        "raat", "log", "logo", "khana", "booking", "table"
    }
    matches = lower_words.intersection(hindi_keywords)
    if len(matches) >= 2 or ("namaste" in lower_words) or ("dhanyavad" in lower_words):
        return "hi-IN-SwaraNeural"

    return "en-IN-NeerjaNeural"


async def synthesize_speech_base64(text: str) -> tuple[str, str]:
    """
    Synthesize speech using high-quality Edge-TTS (unlimited, zero rate limits)
    with dynamic Indian Hindi (hi-IN-SwaraNeural) / Indian English (en-IN-NeerjaNeural) voice selection.
    Returns (base64_audio, mime_type).
    """
    clean_text = text.strip()
    if not clean_text:
        return "", ""

    # 1. Primary: Edge-TTS (unlimited, natural neural voice, zero daily rate limits)
    try:
        import edge_tts
        voice_to_use = detect_voice_for_text(clean_text)
        communicate = edge_tts.Communicate(clean_text, voice=voice_to_use)
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        if chunks:
            mp3_bytes = b"".join(chunks)
            return base64.b64encode(mp3_bytes).decode("utf-8"), "audio/mp3"
    except Exception as e:
        logger.warning("edge-tts synthesis failed: %s", str(e))

    # 2. Secondary fallback: Groq Orpheus
    try:
        groq = get_groq_service()
        settings = get_settings()
        if settings.GROQ_API_KEY:
            resp = groq.client.audio.speech.create(
                input=clean_text,
                model=getattr(settings, "GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english"),
                voice=getattr(settings, "GROQ_TTS_VOICE", "diana"),
                response_format="wav",
                sample_rate=24000,
            )
            wav_bytes = resp.read() if hasattr(resp, "read") and callable(resp.read) else resp
            if isinstance(wav_bytes, (bytes, bytearray)):
                return base64.b64encode(wav_bytes).decode("utf-8"), "audio/wav"
    except Exception as e:
        logger.warning("Groq TTS synthesis failed: %s", str(e))

    return "", ""


@router.post("/start")
async def start_web_call(
    req: WebCallStartRequest,
    db: DatabaseService = Depends(get_database_service),
    session_manager: DatabaseVoiceSessionManager = Depends(get_session_manager),
) -> Dict[str, Any]:
    """
    Start a live browser voice call session.
    Returns session metadata and synthesized opening greeting audio.
    """
    target_biz_id = req.business_id
    biz = db.get_business_profile(target_biz_id) if target_biz_id else None
    if not biz:
        all_bizs = db.get_all_businesses()
        if all_bizs:
            target_biz_id = next(iter(all_bizs.keys()))
            biz = db.get_business_profile(target_biz_id)
    if not biz:
        raise HTTPException(status_code=404, detail="No registered business tenant found in database.")

    session_id = f"web_{uuid.uuid4().hex[:12]}"
    provider_call_id = f"call_{session_id}"
    phone_number = biz.get("phone_number") or "+919513886363"
    primary_phone = phone_number.split(",")[0].strip()

    # 1. Instantiate inbound call event
    inbound_event = InboundCallEvent(
        provider_call_id=provider_call_id,
        provider_name="web_browser",
        called_number=primary_phone,
        caller_number="+91 99999 00000 (Browser)",
        metadata={"client": "web_phone", "business_id": target_biz_id},
    )

    # 2. Persist voice session in database
    session = session_manager.create_session(inbound_event, business_id=target_biz_id)

    # 3. Formulate and synthesize greeting
    greeting_text = (
        biz.get("greeting_message")
        or f"Namaste and welcome to {biz.get('name', 'our business')}! How can I assist you today?"
    )

    # Record greeting in session transcript
    session_manager.record_message(
        business_id=target_biz_id,
        session_id=session.session_id,
        role="assistant",
        content=greeting_text,
    )

    # Synthesize opening greeting
    audio_b64, audio_mime = await synthesize_speech_base64(greeting_text)

    return {
        "session_id": session.session_id,
        "business_id": target_biz_id,
        "business_name": biz.get("name"),
        "greeting_text": greeting_text,
        "audio_base64": audio_b64,
        "audio_mime": audio_mime or "audio/mp3",
    }


@router.post("/turn")
async def process_web_turn(
    session_id: str = Form(...),
    text: Optional[str] = Form(None),
    text_fallback: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    audio_file: Optional[UploadFile] = File(None),
    session_manager: DatabaseVoiceSessionManager = Depends(get_session_manager),
    orchestrator: VoiceTurnOrchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Process one conversational turn from the web browser phone.
    Accepts either recorded audio (WebM/WAV) or transcribed text.
    Returns the agent's spoken reply, synthesized audio, and tool calls.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    caller_text = ""
    groq = get_groq_service()
    settings = get_settings()

    active_audio = audio or audio_file

    # 1. Transcribe audio if provided
    if active_audio is not None:
        try:
            audio_bytes = await active_audio.read()
            if audio_bytes and len(audio_bytes) > 500:
                audio_buf = io.BytesIO(audio_bytes)
                audio_buf.name = active_audio.filename or "recording.webm"
                stt_res = groq.client.audio.transcriptions.create(
                    model=getattr(settings, "GROQ_STT_MODEL", "whisper-large-v3-turbo"),
                    file=audio_buf,
                )
                if stt_res and hasattr(stt_res, "text") and stt_res.text:
                    caller_text = stt_res.text.strip()
        except Exception as e:
            logger.warning("Web voice transcription failed: %s", str(e))

    # 2. Fallback to passed text (e.g. from browser SpeechRecognition)
    if not caller_text:
        caller_text = (text or text_fallback or "").strip()

    if not caller_text or caller_text == "Thank you.":
        fallback_msg = "I didn't quite catch that. Could you please repeat?"
        fb_b64, fb_mime = await synthesize_speech_base64(fallback_msg)
        return {
            "session_id": session_id,
            "user_text": "",
            "assistant_text": fallback_msg,
            "response_text": fallback_msg,
            "audio_base64": fb_b64,
            "audio_mime": fb_mime,
            "tool_calls": [],
            "tool_used": None,
            "should_terminate": False,
        }

    # 3. Create typed TranscriptEvent
    transcript_event = TranscriptEvent(
        session_id=session_id,
        text=caller_text,
        is_final=True,
        speech_final=True,
        confidence=0.98,
        speaker="customer",
    )

    # 4. Execute LangGraph receptionist turn (skipping internal telephony PCM TTS)
    turn_result = orchestrator.process_turn(session_id, transcript_event, synthesize_audio=False)
    assistant_text = turn_result.assistant_text or ""

    # 5. Synthesize assistant voice reply for browser playback
    audio_b64, audio_mime = await synthesize_speech_base64(assistant_text) if assistant_text else ("", "")

    # 6. Check termination
    if turn_result.should_terminate:
        session_manager.terminate_session(session_id, reason="completed")

    tool_used = turn_result.tool_calls_executed[0] if turn_result.tool_calls_executed else None

    return {
        "session_id": session_id,
        "user_text": caller_text,
        "assistant_text": assistant_text,
        "response_text": assistant_text,
        "audio_base64": audio_b64,
        "audio_mime": audio_mime or "audio/wav",
        "tool_calls": turn_result.tool_calls_executed,
        "tool_used": tool_used,
        "filler_phrase": getattr(turn_result, "filler_phrase", None),
        "should_terminate": turn_result.should_terminate,
    }


@router.post("/hangup")
async def hangup_web_call(
    req: WebCallHangupRequest,
    session_manager: DatabaseVoiceSessionManager = Depends(get_session_manager),
) -> Dict[str, Any]:
    """Hangup and finalize the web voice session."""
    session = session_manager.terminate_session(req.session_id, reason="caller_hangup")
    return {
        "status": "terminated",
        "session_id": req.session_id,
        "persisted": bool(session),
    }
