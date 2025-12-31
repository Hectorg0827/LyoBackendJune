"""
External integrations module.

Contains integrations with third-party services:
- Calendar (Google, Apple, Outlook)
- Firebase (Push notifications)
- GCP Secrets Manager
- Vertex AI
"""

from .calendar_integration import calendar_service, CalendarProvider, EventCategory

__all__ = [
    "calendar_service",
    "CalendarProvider",
    "EventCategory",
]
