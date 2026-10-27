"""
External Google Calendar Scheduling Adapter re-export.
Maintains backwards compatibility for direct module imports.
"""

from backend.integrations.adapters.google_calendar_adapter import GoogleCalendarAdapter

__all__ = ["GoogleCalendarAdapter"]
