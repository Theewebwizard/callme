"""
Backward-compatibility proxy re-exporting from standalone tools packages.
"""

from tools.check_appointment_availability import (
    CheckAppointmentAvailabilityInput,
    handle_check_appointment_availability,
)
from tools.create_appointment import (
    CreateAppointmentInput,
    handle_create_appointment,
)

__all__ = [
    "CheckAppointmentAvailabilityInput",
    "CreateAppointmentInput",
    "handle_check_appointment_availability",
    "handle_create_appointment",
]
