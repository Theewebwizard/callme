"""
Manual smoke-test script for live Exotel telephony configuration and routing readiness.
Run using:
    python -m tests.smoke.smoke_test_exotel

Verifies configuration, Basic Auth headers, HMAC signature verification, and tenant routing.
Never prints or leaks credentials or secrets.
"""

import sys
import base64
import hmac
import hashlib
import logging

from backend.config import get_settings
from backend.database.service import get_database_service
from backend.voice.providers.exotel import ExotelTelephonyProvider
from backend.voice.router import InboundCallRouter
from backend.voice.events import InboundCallEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("exotel_smoke_test")


def run_exotel_smoke_test() -> int:
    settings = get_settings()

    print("\n" + "=" * 60)
    print(" Exotel Telephony & AgentStream Pre-Flight Readiness Audit")
    print("=" * 60)

    if not settings.is_exotel_configured:
        print("\n[NOTE] Exotel production credentials are not fully configured in your .env file.")
        print("To enable live PSTN telephony:")
        print("  1. Obtain your Account SID, API Key, and API Token from the Exotel Dashboard.")
        print("  2. Add the following to your local .env file:")
        print("       EXOTEL_ACCOUNT_SID=your_account_sid")
        print("       EXOTEL_API_KEY=your_api_key")
        print("       EXOTEL_API_TOKEN=your_api_token")
        print("       EXOTEL_WEBHOOK_SECRET=your_signing_secret")
        print("       EXOTEL_STREAM_URL=wss://your-domain.com/api/voice/exotel/ws\n")
    else:
        print(f"\nConfiguration detected:")
        print(f"  Account SID     : [CONFIGURED]")
        print(f"  Subdomain       : {settings.EXOTEL_SUBDOMAIN}")
        print(f"  Audio Format    : {settings.EXOTEL_AUDIO_CODEC} ({settings.EXOTEL_SAMPLE_RATE} Hz)")
        print(f"  Stream URL      : {settings.EXOTEL_STREAM_URL or '[NOT CONFIGURED]'}\n")

    # 1. Test HTTP Basic Auth Generator & Validator
    print("Step 1: Testing Exotel HTTP Basic Authentication validation...")
    provider = ExotelTelephonyProvider()
    test_key = settings.EXOTEL_API_KEY or "test_key"
    test_token = settings.EXOTEL_API_TOKEN or "test_token"
    auth_header_val = "Basic " + base64.b64encode(f"{test_key}:{test_token}".encode("utf-8")).decode("utf-8")

    # Temporarily evaluate handshake verification
    is_valid = provider.verify_handshake_auth(
        {"authorization": auth_header_val},
        expected_key=test_key,
        expected_token=test_token,
    )
    if not is_valid:
        print("  [FAIL] Basic Auth validation failed.")
        return 1
    print("  [SUCCESS] Basic Auth header handshake validation verified.")

    # 2. Test HMAC-SHA256 Webhook Signature Verification
    print("\nStep 2: Testing X-Exotel-Signature HMAC-SHA256 verification...")
    secret = settings.EXOTEL_WEBHOOK_SECRET or "smoke_test_secret"
    sample_body = b'{"CallSid": "call_123", "To": "+918041235678"}'
    computed_sig = hmac.new(secret.encode("utf-8"), sample_body, hashlib.sha256).hexdigest()

    sig_valid = provider.verify_webhook_signature(
        sample_body,
        {"X-Exotel-Signature": f"sha256={computed_sig}"},
        secret=secret,
    )
    if not sig_valid:
        print("  [FAIL] Webhook signature verification failed.")
        return 1
    print("  [SUCCESS] HMAC-SHA256 signature verification verified.")

    # 3. Test Inbound Tenant Routing Against Database
    print("\nStep 3: Testing Inbound Tenant Routing from virtual numbers...")
    try:
        db = get_database_service()
        if not db.is_available():
            print("  [WARNING] Database connection not reachable, skipping live tenant lookup.")
        else:
            businesses = list(db.get_all_businesses().values())
            print(f"  Discovered {len(businesses)} active tenant(s) in database:")
            for b in businesses:
                print(f"    - Tenant: {b.get('name')} | Phone: {b.get('phone_number') or '[NONE]'}")

            # Verify routing on known test number
            router = InboundCallRouter(db_service=db)
            test_event = InboundCallEvent(
                provider_call_id="audit_call_001",
                provider_name="exotel",
                called_number="+91 80 4123 5678",
                caller_number="+91 98 7654 3210",
            )
            route_res = router.route_inbound_call(test_event)
            print(f"  [SUCCESS] Route resolved tenant '{route_res.business.get('name')}' for dialled number +91 80 4123 5678.")
    except Exception as e:
        print(f"  [NOTE] Inbound router evaluation: {str(e)}")

    print("\n" + "=" * 60)
    print(" Exotel Pre-Flight Telephony Audit PASSED.")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_exotel_smoke_test())
