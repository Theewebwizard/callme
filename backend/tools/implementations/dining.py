"""
Backward-compatibility proxy re-exporting from standalone tools packages.
"""

from tools.check_table_availability import (
    CheckTableAvailabilityInput,
    handle_check_table_availability,
)
from tools.create_table_booking import (
    CreateTableBookingInput,
    handle_create_table_booking,
)

__all__ = [
    "CheckTableAvailabilityInput",
    "CreateTableBookingInput",
    "handle_check_table_availability",
    "handle_create_table_booking",
]
