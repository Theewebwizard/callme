"""
Idempotent database seeder for initial sample tenants.
Seeds 'biz_spice_garden' and 'biz_apex_dental' with profile data, FAQs, tool configurations,
and representative call records without duplicating records or destroying existing user edits.
"""

from typing import Optional, Dict, Any
import logging
from sqlalchemy.orm import Session
from sqlalchemy import Engine

from backend.database.engine import (
    get_engine,
    get_session_factory,
    session_scope,
    init_db_schema,
    DatabaseConfigurationError,
)
from backend.database.repositories import (
    BusinessRepository,
    FAQRepository,
    ToolConfigRepository,
    CallRepository,
    ConversationRepository,
)
from ui.mock_data import INITIAL_BUSINESSES, INITIAL_TOOLS, MOCK_CALL_HISTORY

logger = logging.getLogger(__name__)


def seed_database(
    engine: Optional[Engine] = None,
    session: Optional[Session] = None,
    force_update_profile: bool = False,
) -> Dict[str, Any]:
    """
    Idempotent seeding operation for initial platform businesses.
    Ensures 'biz_spice_garden' and 'biz_apex_dental' exist with complete profiles,
    canonical tool enablement, FAQs, and simulated call audit logs.
    """
    stats = {
        "businesses_created": 0,
        "businesses_existing": 0,
        "faqs_created": 0,
        "tools_configured": 0,
        "calls_seeded": 0,
    }

    def _execute_seed(sess: Session) -> None:
        biz_repo = BusinessRepository(sess)
        faq_repo = FAQRepository(sess)
        tool_repo = ToolConfigRepository(sess)
        call_repo = CallRepository(sess)
        conv_repo = ConversationRepository(sess)

        for b_id, b_data in INITIAL_BUSINESSES.items():
            biz = biz_repo.get(b_id)
            if not biz:
                # 1. Create Business
                biz = biz_repo.create(b_data)
                stats["businesses_created"] += 1
                logger.info(f"Seeded new business: {b_id} ({b_data['name']})")

                # 2. Seed FAQs
                for faq_item in b_data.get("faqs", []):
                    faq_repo.create(
                        business_id=b_id,
                        question=faq_item["question"],
                        answer=faq_item["answer"],
                        category="General",
                    )
                    stats["faqs_created"] += 1

                # 3. Seed Tool Statuses
                for t_id, enabled in b_data.get("enabled_tools", {}).items():
                    tool_repo.set_tool_status(b_id, t_id, enabled)
                    stats["tools_configured"] += 1

                # 4. Seed Mock Call Records
                calls = MOCK_CALL_HISTORY.get(b_id, [])
                for c in calls:
                    call_repo.log_call(
                        business_id=b_id,
                        caller_number=c["caller_number"],
                        duration_seconds=120,
                        duration_formatted=c.get("duration", "2m 00s"),
                        outcome=c["outcome"],
                        summary=c["summary"],
                        tools_used=c.get("tools_used", []),
                        is_simulated=True,
                        call_id=c["id"],
                    )
                    stats["calls_seeded"] += 1

                # 5. Seed Initial Greeting Message in Conversation
                conv_repo.add_message(
                    business_id=b_id,
                    role="assistant",
                    content=b_data["greeting_message"],
                    is_simulated=True,
                )
            else:
                stats["businesses_existing"] += 1
                logger.info(f"Business already exists, preserving user edits: {b_id}")

                if force_update_profile:
                    biz_repo.update(b_id, b_data)

                # Ensure any newly introduced canonical tools are configured if missing
                current_tools = tool_repo.get_tool_statuses(b_id)
                for t_id in INITIAL_TOOLS:
                    if t_id not in current_tools:
                        default_enabled = b_data.get("enabled_tools", {}).get(t_id, False)
                        tool_repo.set_tool_status(b_id, t_id, default_enabled)
                        stats["tools_configured"] += 1

                # If no call history records exist for this business, seed initial calls
                existing_calls = call_repo.list_for_business(b_id, limit=1)
                if not existing_calls:
                    calls = MOCK_CALL_HISTORY.get(b_id, [])
                    for c in calls:
                        call_repo.log_call(
                            business_id=b_id,
                            caller_number=c["caller_number"],
                            duration_seconds=120,
                            duration_formatted=c.get("duration", "2m 00s"),
                            outcome=c["outcome"],
                            summary=c["summary"],
                            tools_used=c.get("tools_used", []),
                            is_simulated=True,
                            call_id=c["id"],
                        )
                        stats["calls_seeded"] += 1

    if session is not None:
        _execute_seed(session)
    else:
        eng = engine or get_engine()
        # Ensure schema tables exist before seeding
        init_db_schema(eng)
        with session_scope(engine=eng) as sess:
            _execute_seed(sess)

    return stats


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("Connecting to database and running seed operation...")
    try:
        results = seed_database()
        print(f"Seed operation completed successfully:\n{results}")
    except DatabaseConfigurationError as err:
        print(f"Configuration Error: {err}")
        sys.exit(1)
    except Exception as exc:
        print(f"Seed Error: {type(exc).__name__}: {exc}")
        sys.exit(1)
