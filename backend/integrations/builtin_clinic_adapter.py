"""
Built-in Clinical Appointment Integration Adapter re-export.
Maintains backwards compatibility for direct module imports.
"""

from backend.integrations.adapters.builtin_clinic_adapter import BuiltinClinicAdapter

__all__ = ["BuiltinClinicAdapter"]
