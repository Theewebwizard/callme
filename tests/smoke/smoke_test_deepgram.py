"""
Manual smoke-test script for live Deepgram STT and TTS connectivity.
Run using:
    python -m tests.smoke.smoke_test_deepgram
"""

import sys
import time
import logging

from backend.config import get_settings
from backend.voice.providers.deepgram import DeepgramSTTProvider, DeepgramTTSProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deepgram_smoke_test")


def run_smoke_test() -> int:
    settings = get_settings()

    print("\n" + "=" * 60)
    print(" Deepgram Speech-to-Text & Text-to-Speech Smoke Test")
    print("=" * 60)

    if not settings.is_deepgram_configured:
        print("\n[SKIPPED] DEEPGRAM_API_KEY is not configured in your environment or .env file.")
        print("To run live Deepgram verification:")
        print("  1. Create a free API key at https://console.deepgram.com")
        print("  2. Add 'DEEPGRAM_API_KEY=your_key_here' to your local .env file")
        print("  3. Re-run: python -m backend.voice.smoke_test\n")
        return 0

    print(f"\nConfiguration detected:")
    print(f"  STT Model       : {settings.DEEPGRAM_STT_MODEL}")
    print(f"  STT Sample Rate : {settings.DEEPGRAM_STT_SAMPLE_RATE} Hz")
    print(f"  TTS Model       : {settings.DEEPGRAM_TTS_MODEL}")
    print(f"  TTS Sample Rate : {settings.DEEPGRAM_TTS_SAMPLE_RATE} Hz")
    print(f"  API Key         : [CONFIGURED - {len(settings.DEEPGRAM_API_KEY)} chars]\n")

    # 1. Test TTS
    print("Step 1: Testing live Deepgram TTS synthesis...")
    test_phrase = "Hello! This is a real-time voice verification test for the AI receptionist."
    tts_provider = DeepgramTTSProvider(api_key=settings.DEEPGRAM_API_KEY)

    start_time = time.time()
    try:
        audio_bytes = tts_provider.synthesize(test_phrase)
        elapsed = (time.time() - start_time) * 1000
        if not audio_bytes or len(audio_bytes) < 1000:
            print(f"  [FAIL] TTS synthesis returned unexpected audio size: {len(audio_bytes)} bytes")
            return 1
        print(f"  [SUCCESS] Synthesized {len(audio_bytes)} bytes of Linear PCM audio in {elapsed:.1f}ms")
    except Exception as e:
        print(f"  [ERROR] TTS synthesis failed: {str(e)}")
        return 1

    # 2. Test STT
    print("\nStep 2: Testing live Deepgram STT transcription with synthesized audio...")
    stt_provider = DeepgramSTTProvider(api_key=settings.DEEPGRAM_API_KEY)

    start_time = time.time()
    try:
        transcript_event = stt_provider.transcribe(audio_bytes)
        elapsed = (time.time() - start_time) * 1000
        if not transcript_event.text:
            print(f"  [FAIL] STT transcription returned empty text")
            return 1
        print(f"  [SUCCESS] Recognized in {elapsed:.1f}ms:")
        print(f"    Transcript : \"{transcript_event.text}\"")
        print(f"    Confidence : {transcript_event.confidence:.2%}")
    except Exception as e:
        print(f"  [ERROR] STT transcription failed: {str(e)}")
        return 1

    print("\n" + "=" * 60)
    print(" Deepgram Smoke Test PASSED: Both STT and TTS are operational.")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
