"""
Utility script to purge mock tenants (biz_spice_garden, biz_apex_dental) and their cascading data.
Usage:
    python -m backend.database.cleanup_mock_data
"""

import sys
import logging
from typing import List
from backend.database.service import get_database_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MOCK_TENANT_IDS = ["biz_spice_garden", "biz_apex_dental"]


def purge_mock_data(mock_ids: List[str] = MOCK_TENANT_IDS) -> int:
    """Purge mock tenant records from the database."""
    db = get_database_service()
    if not db.is_available():
        logger.error("Database service is unavailable. Aborting cleanup.")
        return 1

    all_businesses = db.get_all_businesses()
    logger.info("Found %d total business(es) in database: %s", len(all_businesses), list(all_businesses.keys()))

    deleted_count = 0
    for mock_id in mock_ids:
        if mock_id in all_businesses:
            biz_name = all_businesses[mock_id].get("name", mock_id)
            logger.info("Deleting mock business '%s' (%s)...", biz_name, mock_id)
            try:
                success = db.delete_business(mock_id)
                if success:
                    logger.info("Successfully deleted '%s' (%s) and all cascading child records.", biz_name, mock_id)
                    deleted_count += 1
                else:
                    logger.warning("Failed to delete '%s' (%s).", biz_name, mock_id)
            except Exception as e:
                logger.error("Error deleting '%s' (%s): %s", biz_name, mock_id, str(e))
        else:
            logger.info("Mock tenant '%s' is not present in the database (already clean).", mock_id)

    remaining = db.get_all_businesses()
    logger.info(
        "Purge complete. %d mock tenant(s) removed. %d business(es) remain: %s",
        deleted_count,
        len(remaining),
        list(remaining.keys()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(purge_mock_data())
