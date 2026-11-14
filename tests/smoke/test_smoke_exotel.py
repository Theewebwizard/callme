import pytest
from tests.smoke.smoke_test_exotel import run_exotel_smoke_test

def test_exotel_smoke_verification():
    """Verify Exotel telephony configuration, Basic Auth, HMAC signatures, and tenant routing."""
    res = run_exotel_smoke_test()
    assert res == 0

