import pytest
from tests.smoke.smoke_test_deepgram import run_smoke_test

def test_deepgram_smoke_verification():
    """Verify Deepgram STT/TTS connectivity when configured or graceful skip when unconfigured."""
    res = run_smoke_test()
    assert res == 0

