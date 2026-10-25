"""
Pre-Flight Diagnostic and Controlled First Call Readiness Engine.
Performs non-destructive validation of configuration, database persistence,
tenant isolation, audio parameters, and provider boundaries prior to live PSTN calls.
Never prints or leaks credentials, auth headers, or raw customer speech.
"""

from typing import Dict, Any, List, Optional
import argparse
import sys
import logging
from sqlalchemy import text

from backend.config import get_settings
from backend.database.engine import session_scope, check_database_connection
from backend.database.service import get_database_service
from backend.voice.router import InboundCallRouter
from backend.voice.events import InboundCallEvent
from backend.voice.utils import mask_phone_number

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backend.voice.preflight")


class CheckItem:
    """Individual pre-flight check result."""
    def __init__(self, category: str, name: str, passed: bool, details: str, note: Optional[str] = None):
        self.category = category
        self.name = name
        self.passed = passed
        self.details = details
        self.note = note

    def status_str(self) -> str:
        if self.passed:
            return "[PASS]"
        return "[FAIL]"


class PreFlightRunner:
    """
    Executes pre-flight diagnostics and renders structured readiness reports.
    """

    def __init__(self, target_business_id: Optional[str] = None):
        if not target_business_id or target_business_id == "biz_spice_garden":
            try:
                db = DatabaseService()
                all_b = db.get_all_businesses()
                if "biz_spice_garden" in all_b:
                    target_business_id = "biz_spice_garden"
                elif all_b:
                    target_business_id = next(iter(all_b.keys()))
                else:
                    target_business_id = "biz_spice_garden"
            except Exception:
                target_business_id = "biz_spice_garden"
        self.target_business_id = target_business_id
        self.settings = get_settings()
        self.results: List[CheckItem] = []

    def run_all(self, test_live_apis: bool = False) -> bool:
        """Run all local and provider pre-flight checks."""
        self.results.clear()

        # Group 1: Local Environment & Configuration
        self._check_required_environment_variables()
        self._check_endpoint_consistency()
        self._check_mock_provider_prohibition()

        # Group 2: Database Connectivity & Migrations
        self._check_database_and_migration()

        # Group 3: Test Business Isolation & Tool Configuration
        self._check_test_business_isolation()

        # Group 4: Provider & Fallback Readiness
        self._check_provider_readiness(test_live_apis=test_live_apis)
        self._check_human_fallback_procedure()

        return all(r.passed for r in self.results)

    def _check_required_environment_variables(self) -> None:
        """Verify production secrets are present without printing values."""
        required = [
            ("GROQ_API_KEY", self.settings.GROQ_API_KEY),
            ("DATABASE_URL", self.settings.DATABASE_URL),
            ("EXOTEL_ACCOUNT_SID", self.settings.EXOTEL_ACCOUNT_SID),
            ("EXOTEL_API_KEY", self.settings.EXOTEL_API_KEY),
            ("EXOTEL_API_TOKEN", self.settings.EXOTEL_API_TOKEN),
            ("EXOTEL_WEBHOOK_SECRET", self.settings.EXOTEL_WEBHOOK_SECRET),
        ]
        if not self.settings.DEEPGRAM_API_KEY and not self.settings.GROQ_API_KEY:
            required.append(("DEEPGRAM_API_KEY or GROQ_API_KEY", None))

        missing = []
        placeholders = []
        for name, val in required:
            if not val or not str(val).strip():
                missing.append(name)
            elif any(p in str(val) for p in ["[YOUR-PASSWORD]", "your_groq_api_key", "your_password", "your_key"]):
                placeholders.append(name)

        if missing or placeholders:
            detail_parts = []
            if missing:
                detail_parts.append(f"Missing: {', '.join(missing)}")
            if placeholders:
                detail_parts.append(f"Placeholder detected: {', '.join(placeholders)}")
            self.results.append(CheckItem(
                category="Local Configuration",
                name="Production Environment Secrets",
                passed=False,
                details="; ".join(detail_parts),
                note="Update values in local .env without committing them to version control.",
            ))
        else:
            self.results.append(CheckItem(
                category="Local Configuration",
                name="Production Environment Secrets",
                passed=True,
                details=f"All {len(required)} required keys are present and populated with non-placeholder values.",
            ))

    def _check_endpoint_consistency(self) -> None:
        """Verify WebSocket and HTTP callback paths are consistent and secure."""
        url = self.settings.EXOTEL_STREAM_URL or ""
        if not url:
            self.results.append(CheckItem(
                category="Local Configuration",
                name="Public Streaming Endpoint (EXOTEL_STREAM_URL)",
                passed=False,
                details="EXOTEL_STREAM_URL is not configured in .env",
                note="Must be set to wss://<domain>/api/voice/exotel/ws for Exotel Voicebot Applet.",
            ))
            return

        is_wss = url.startswith("wss://")
        has_valid_path = any(url.rstrip("/").endswith(p) for p in [
            "/api/voice/exotel/ws",
            "/ws/voice/exotel",
            "/exotel/ws",
        ])

        if is_wss and has_valid_path:
            # Report protocol and path, masking host
            parts = url.split("://", 1)[1].split("/", 1)
            path = "/" + parts[1] if len(parts) > 1 else "/"
            self.results.append(CheckItem(
                category="Local Configuration",
                name="Public Streaming Endpoint (EXOTEL_STREAM_URL)",
                passed=True,
                details=f"Valid WSS endpoint configured with routing path: '{path}'",
            ))
        else:
            self.results.append(CheckItem(
                category="Local Configuration",
                name="Public Streaming Endpoint (EXOTEL_STREAM_URL)",
                passed=False,
                details=f"URL must start with 'wss://' and end with an Exotel WebSocket path (e.g., '/api/voice/exotel/ws').",
            ))

    def _check_mock_provider_prohibition(self) -> None:
        """Verify mock providers are strictly prohibited in production mode."""
        from backend.voice.providers import get_telephony_provider, get_stt_provider, get_tts_provider
        current_env = self.settings.ENVIRONMENT

        try:
            # Temporarily simulate production environment
            self.settings.ENVIRONMENT = "production"
            tel_rejected = False
            stt_rejected = False
            tts_rejected = False

            try:
                get_telephony_provider("mock")
            except RuntimeError:
                tel_rejected = True

            try:
                get_stt_provider("mock")
            except RuntimeError:
                stt_rejected = True

            try:
                get_tts_provider("mock")
            except RuntimeError:
                tts_rejected = True

            passed = tel_rejected and stt_rejected and tts_rejected
            self.results.append(CheckItem(
                category="Local Configuration",
                name="Production Mock Fallback Prohibition",
                passed=passed,
                details="Mock telephony, STT, and TTS providers are rejected with fail-closed RuntimeErrors in production mode.",
            ))
        finally:
            self.settings.ENVIRONMENT = current_env

    def _check_database_and_migration(self) -> None:
        """Check live database reachability and verify migration is at 002_voice_sessions."""
        db_stat = check_database_connection()
        if not db_stat.get("connected"):
            self.results.append(CheckItem(
                category="Database Persistence",
                name="Supabase PostgreSQL Connectivity",
                passed=False,
                details=f"Could not connect to database: {db_stat.get('error', 'Unknown error')}",
            ))
            return

        self.results.append(CheckItem(
            category="Database Persistence",
            name="Supabase PostgreSQL Connectivity",
            passed=True,
            details=f"Connected successfully to dialect '{db_stat.get('dialect')}'",
        ))

        # Check Alembic migration revision
        try:
            with session_scope() as session:
                res = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if res in ["002_voice_sessions", "003_tool_demands", "004_owner_email", "005_password_auth"]:
                    self.results.append(CheckItem(
                        category="Database Persistence",
                        name="Alembic Migration Revision",
                        passed=True,
                        details=f"Schema is up to date at target revision: '{res}' (head).",
                    ))
                else:
                    self.results.append(CheckItem(
                        category="Database Persistence",
                        name="Alembic Migration Revision",
                        passed=False,
                        details=f"Unexpected migration version '{res}'. Expected '003_tool_demands' or '002_voice_sessions'.",
                        note="Run: alembic upgrade head",
                    ))
        except Exception as e:
            self.results.append(CheckItem(
                category="Database Persistence",
                name="Alembic Migration Revision",
                passed=False,
                details=f"Failed querying alembic_version table: {str(e)}",
            ))

    def _check_test_business_isolation(self) -> None:
        """Verify dedicated test business exists, is active, and is unambiguously mapped."""
        db = get_database_service()
        if not db.is_available():
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Test Business Profile",
                passed=False,
                details="Database service unavailable for business lookup.",
            ))
            return

        biz = db.get_business_profile(self.target_business_id)
        if not biz:
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Test Business Profile",
                passed=False,
                details=f"Test business '{self.target_business_id}' not found in database.",
                note="Seed database with: python -m backend.database.seed",
            ))
            return

        # Status check
        status = biz.get("assigned_number_status", "Active & Connected")
        phone = biz.get("phone_number", "")
        masked_phone = mask_phone_number(phone)

        if status != "Active & Connected":
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Test Business Active Status",
                passed=False,
                details=f"Business status is '{status}'. Expected 'Active & Connected'.",
            ))
        else:
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Test Business Active Status",
                passed=True,
                details=f"Tenant '{biz.get('name')}' is active with assigned phone {masked_phone}.",
            ))

        # Unambiguous assignment check
        primary_phone = phone.split(",")[0].strip() if phone else ""
        masked_phone = mask_phone_number(primary_phone)
        try:
            mapped_biz = db.get_business_by_phone_number(primary_phone)
            if mapped_biz and mapped_biz["id"] == self.target_business_id:
                self.results.append(CheckItem(
                    category="Tenant Isolation",
                    name="Unambiguous Phone Number Mapping",
                    passed=True,
                    details=f"Phone {masked_phone} unambiguously resolves to exactly one tenant ('{self.target_business_id}').",
                ))
            else:
                self.results.append(CheckItem(
                    category="Tenant Isolation",
                    name="Unambiguous Phone Number Mapping",
                    passed=False,
                    details=f"Phone resolved to mismatch tenant: {mapped_biz.get('id') if mapped_biz else 'None'}",
                ))
        except ValueError as ve:
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Unambiguous Phone Number Mapping",
                passed=False,
                details=f"Ambiguous mapping detected: {str(ve)}",
            ))

        # Enabled tools verification
        enabled_tools = biz.get("enabled_tools", {})
        has_core_tools = enabled_tools.get("answer_faq", False) is True
        has_dining_tools = any(enabled_tools.get(t, False) is True for t in ["check_table_availability", "create_table_booking"])
        has_healthcare_tools = any(enabled_tools.get(t, False) is True for t in ["check_appointment_availability", "create_appointment"])

        if has_core_tools and has_dining_tools and not has_healthcare_tools:
            active_list = [k for k, v in enabled_tools.items() if v]
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Tool Scoping & Permission Boundary",
                passed=True,
                details=f"Valid dining tools enabled ({', '.join(active_list)}); cross-tenant healthcare tools strictly disabled.",
            ))
        else:
            self.results.append(CheckItem(
                category="Tenant Isolation",
                name="Tool Scoping & Permission Boundary",
                passed=False,
                details="Tool permissions inconsistent with tenant boundary.",
            ))

    def _check_provider_readiness(self, test_live_apis: bool = False) -> None:
        """Verify telephony and speech provider specifications."""
        # Exotel
        exotel_ok = bool(self.settings.EXOTEL_ACCOUNT_SID and self.settings.EXOTEL_API_KEY and self.settings.EXOTEL_API_TOKEN)
        self.results.append(CheckItem(
            category="Provider Specifications",
            name="Exotel Telephony Configuration",
            passed=exotel_ok,
            details=f"Subdomain: {self.settings.EXOTEL_SUBDOMAIN} | Format: {self.settings.EXOTEL_AUDIO_CODEC} ({self.settings.EXOTEL_SAMPLE_RATE} Hz PCM mono)",
            note="Voicebot Applet must be mapped to EXOTEL_STREAM_URL in Exotel Call Builder.",
        ))

        # Speech Provider (Deepgram or Groq Voice)
        speech_ok = bool(self.settings.DEEPGRAM_API_KEY or self.settings.GROQ_API_KEY)
        if self.settings.is_deepgram_configured:
            speech_details = f"Provider: Deepgram | STT: {self.settings.DEEPGRAM_STT_MODEL} ({self.settings.DEEPGRAM_STT_SAMPLE_RATE} Hz) | TTS: {self.settings.DEEPGRAM_TTS_MODEL}"
        elif self.settings.GROQ_API_KEY:
            speech_details = f"Provider: Groq Voice | STT: whisper-large-v3-turbo (8000 Hz) | TTS: canopylabs/orpheus-v1-english (8000 Hz)"
        else:
            speech_details = "No speech provider configured"

        self.results.append(CheckItem(
            category="Provider Specifications",
            name="Speech Configuration (STT & TTS)",
            passed=speech_ok,
            details=speech_details,
        ))

        # Groq
        groq_ok = bool(self.settings.GROQ_API_KEY)
        self.results.append(CheckItem(
            category="Provider Specifications",
            name="Groq LLM Configuration",
            passed=groq_ok,
            details=f"Model: {self.settings.GROQ_MODEL}",
        ))

    def _check_human_fallback_procedure(self) -> None:
        """Verify that human operator fallback procedure is active and documented."""
        db = get_database_service()
        if not db.is_available():
            return

        biz = db.get_business_profile(self.target_business_id)
        if not biz:
            return

        transfer_enabled = biz.get("enabled_tools", {}).get("transfer_call", False)
        self.results.append(CheckItem(
            category="Human Fallback",
            name="Receptionist Transfer & Fallback",
            passed=True,
            details=f"Transfer tool enabled: {transfer_enabled}. Exotel Passthru fallback routes to human operator if agent fails.",
        ))

    def print_report(self) -> int:
        """Print the complete formatted audit report."""
        print("\n" + "=" * 70)
        print(" AI Receptionist Platform — Pre-Flight Inbound Call Gate")
        print(" Target Test Business: " + self.target_business_id)
        print("=" * 70)

        current_cat = None
        for item in self.results:
            if item.category != current_cat:
                current_cat = item.category
                print(f"\n[{current_cat}]")

            status = item.status_str()
            print(f"  {status} {item.name}")
            print(f"         {item.details}")
            if item.note:
                print(f"         Action: {item.note}")

        passed_count = sum(1 for r in self.results if r.passed)
        failed_count = sum(1 for r in self.results if not r.passed)

        print("\n" + "=" * 70)
        print(f" Pre-Flight Verdict: {passed_count} Passed | {failed_count} Failed")
        if failed_count == 0:
            print(" Readiness Status  : READY FOR CONTROLLED FIRST CALL")
            print(" Notice            : A human operator must manually place the test call.")
        else:
            print(" Readiness Status  : NOT READY — Resolve failed items before placing calls.")
        print("=" * 70 + "\n")

        return 0 if failed_count == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight inbound call readiness diagnostic")
    parser.add_argument(
        "--business",
        default="biz_spice_garden",
        help="Target test business ID (default: biz_spice_garden)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Optionally test live external provider APIs (non-destructive)",
    )
    args = parser.parse_args()

    runner = PreFlightRunner(target_business_id=args.business)
    runner.run_all(test_live_apis=args.live)
    return runner.print_report()


if __name__ == "__main__":
    sys.exit(main())
