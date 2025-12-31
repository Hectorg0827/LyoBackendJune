"""
Calendar Integration Service - External Calendar Sync for Learning Events

This module integrates with external calendars (Google, Apple) to:
1. Detect learning-related events (exams, interviews, presentations)
2. Proactively queue preparation sessions before events
3. Sync study schedules to user calendars

The goal: If you have "Math Exam" on your calendar, Lyo will reach out
1-2 days before with a personalized review session.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode
import httpx

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class CalendarProvider(str, Enum):
    """Supported calendar providers."""
    GOOGLE = "google"
    APPLE = "apple"
    OUTLOOK = "outlook"
    ICAL = "ical"  # Generic iCal URL


class EventCategory(str, Enum):
    """Categories of learning-related events we detect."""
    EXAM = "exam"
    QUIZ = "quiz"
    TEST = "test"
    INTERVIEW = "interview"
    PRESENTATION = "presentation"
    DEADLINE = "deadline"
    CLASS = "class"
    STUDY_SESSION = "study_session"
    MEETING = "meeting"
    OTHER = "other"


@dataclass
class CalendarEvent:
    """A calendar event with learning relevance analysis."""
    id: str
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    location: Optional[str]
    category: EventCategory
    learning_keywords: List[str]
    preparation_needed: bool
    prep_days_before: int  # How many days before to start prep
    confidence: float  # Confidence in category detection
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class CalendarConnection:
    """User's calendar connection details."""
    user_id: int
    provider: CalendarProvider
    access_token: str
    refresh_token: Optional[str]
    token_expires_at: Optional[datetime]
    calendar_id: str  # Primary calendar ID
    sync_enabled: bool
    last_sync: Optional[datetime]
    created_at: datetime


class CalendarIntegrationService:
    """
    Manages calendar integrations and event analysis.

    Key capabilities:
    - OAuth flow for Google/Apple calendars
    - Event fetching and caching
    - Learning event detection (exams, interviews, etc.)
    - Preparation reminder scheduling
    """

    # Keywords that indicate learning-related events
    LEARNING_KEYWORDS = {
        EventCategory.EXAM: [
            "exam", "final", "midterm", "test", "examination",
            "examen", "prueba", "prüfung", "考试"
        ],
        EventCategory.QUIZ: [
            "quiz", "pop quiz", "assessment", "evaluation"
        ],
        EventCategory.TEST: [
            "test", "testing", "certification", "cert exam"
        ],
        EventCategory.INTERVIEW: [
            "interview", "technical interview", "phone screen",
            "onsite", "coding interview", "behavioral interview"
        ],
        EventCategory.PRESENTATION: [
            "presentation", "present", "demo", "pitch",
            "speech", "talk", "keynote", "defense", "thesis"
        ],
        EventCategory.DEADLINE: [
            "due", "deadline", "submit", "submission",
            "turn in", "hand in", "assignment due"
        ],
        EventCategory.CLASS: [
            "class", "lecture", "seminar", "workshop",
            "tutorial", "lab", "recitation"
        ],
        EventCategory.STUDY_SESSION: [
            "study", "review", "practice", "prep",
            "study group", "tutoring", "office hours"
        ]
    }

    # Days of preparation needed by category
    PREP_DAYS = {
        EventCategory.EXAM: 3,
        EventCategory.QUIZ: 1,
        EventCategory.TEST: 2,
        EventCategory.INTERVIEW: 2,
        EventCategory.PRESENTATION: 2,
        EventCategory.DEADLINE: 1,
        EventCategory.CLASS: 0,
        EventCategory.STUDY_SESSION: 0,
        EventCategory.MEETING: 0,
        EventCategory.OTHER: 0
    }

    def __init__(self):
        self.google_client_id = getattr(settings, "GOOGLE_CLIENT_ID", None)
        self.google_client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", None)
        self.google_redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", None)

    # ==================== OAuth Flows ====================

    def get_google_auth_url(self, user_id: int, state: Optional[str] = None) -> str:
        """
        Generate Google OAuth URL for calendar access.
        """
        if not self.google_client_id:
            raise ValueError("Google OAuth not configured")

        scopes = [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events.readonly"
        ]

        params = {
            "client_id": self.google_client_id,
            "redirect_uri": self.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state or str(user_id)
        }

        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        query_string = urlencode(params)
        return f"{base_url}?{query_string}"

    async def exchange_google_code(
        self,
        code: str,
        user_id: int
    ) -> CalendarConnection:
        """
        Exchange OAuth code for access tokens.
        """
        if not self.google_client_id or not self.google_client_secret:
            raise ValueError("Google OAuth not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.google_client_id,
                    "client_secret": self.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.google_redirect_uri
                }
            )

            if response.status_code != 200:
                logger.error(f"Google OAuth error: {response.text}")
                raise ValueError("Failed to exchange OAuth code")

            tokens = response.json()

            return CalendarConnection(
                user_id=user_id,
                provider=CalendarProvider.GOOGLE,
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                token_expires_at=datetime.utcnow() + timedelta(seconds=tokens["expires_in"]),
                calendar_id="primary",
                sync_enabled=True,
                last_sync=None,
                created_at=datetime.utcnow()
            )

    async def refresh_google_token(
        self,
        connection: CalendarConnection
    ) -> CalendarConnection:
        """
        Refresh expired Google access token.
        """
        if not connection.refresh_token:
            raise ValueError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.google_client_id,
                    "client_secret": self.google_client_secret,
                    "refresh_token": connection.refresh_token,
                    "grant_type": "refresh_token"
                }
            )

            if response.status_code != 200:
                logger.error(f"Token refresh error: {response.text}")
                raise ValueError("Failed to refresh token")

            tokens = response.json()
            connection.access_token = tokens["access_token"]
            connection.token_expires_at = datetime.utcnow() + timedelta(seconds=tokens["expires_in"])

            return connection

    # ==================== Event Fetching ====================

    async def fetch_google_events(
        self,
        connection: CalendarConnection,
        days_ahead: int = 14
    ) -> List[CalendarEvent]:
        """
        Fetch upcoming events from Google Calendar.
        """
        # Refresh token if needed
        if connection.token_expires_at and connection.token_expires_at <= datetime.utcnow():
            connection = await self.refresh_google_token(connection)

        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{connection.calendar_id}/events",
                headers={"Authorization": f"Bearer {connection.access_token}"},
                params={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "singleEvents": "true",
                    "orderBy": "startTime"
                }
            )

            if response.status_code != 200:
                logger.error(f"Google Calendar API error: {response.text}")
                raise ValueError("Failed to fetch calendar events")

            data = response.json()
            events = []

            for item in data.get("items", []):
                event = self._parse_google_event(item)
                if event:
                    events.append(event)

            return events

    def _parse_google_event(self, item: Dict[str, Any]) -> Optional[CalendarEvent]:
        """
        Parse a Google Calendar event into our format.
        """
        try:
            # Parse start/end times
            start = item.get("start", {})
            end = item.get("end", {})

            if "dateTime" in start:
                start_time = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))
            elif "date" in start:
                # All-day event
                start_time = datetime.fromisoformat(start["date"])
                end_time = datetime.fromisoformat(end["date"])
            else:
                return None

            title = item.get("summary", "")
            description = item.get("description", "")

            # Analyze the event
            category, keywords, confidence = self._categorize_event(title, description)
            prep_needed = category in [
                EventCategory.EXAM, EventCategory.QUIZ, EventCategory.TEST,
                EventCategory.INTERVIEW, EventCategory.PRESENTATION, EventCategory.DEADLINE
            ]

            return CalendarEvent(
                id=item.get("id", ""),
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                location=item.get("location"),
                category=category,
                learning_keywords=keywords,
                preparation_needed=prep_needed,
                prep_days_before=self.PREP_DAYS.get(category, 0),
                confidence=confidence,
                raw_data=item
            )

        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            return None

    # ==================== Event Analysis ====================

    def _categorize_event(
        self,
        title: str,
        description: str
    ) -> Tuple[EventCategory, List[str], float]:
        """
        Categorize an event based on title and description.
        Returns (category, matched_keywords, confidence).
        """
        text = f"{title} {description}".lower()
        matches: Dict[EventCategory, List[str]] = {}

        for category, keywords in self.LEARNING_KEYWORDS.items():
            matched = [kw for kw in keywords if kw.lower() in text]
            if matched:
                matches[category] = matched

        if not matches:
            return EventCategory.OTHER, [], 0.0

        # Find best match (most keywords, with priority for specific categories)
        priority_order = [
            EventCategory.EXAM, EventCategory.INTERVIEW, EventCategory.TEST,
            EventCategory.PRESENTATION, EventCategory.QUIZ, EventCategory.DEADLINE,
            EventCategory.CLASS, EventCategory.STUDY_SESSION
        ]

        best_category = EventCategory.OTHER
        best_keywords: List[str] = []
        best_score = 0

        for category in priority_order:
            if category in matches:
                score = len(matches[category])
                if score > best_score:
                    best_score = score
                    best_category = category
                    best_keywords = matches[category]

        # Calculate confidence based on matches
        confidence = min(0.5 + (best_score * 0.2), 1.0)

        return best_category, best_keywords, confidence

    def get_events_needing_prep(
        self,
        events: List[CalendarEvent],
        max_days_ahead: int = 7
    ) -> List[CalendarEvent]:
        """
        Filter events that need preparation within the specified window.
        """
        now = datetime.utcnow()
        cutoff = now + timedelta(days=max_days_ahead)

        prep_events = []
        for event in events:
            if not event.preparation_needed:
                continue

            # Check if prep should start soon
            prep_start = event.start_time - timedelta(days=event.prep_days_before)
            if now <= prep_start <= cutoff:
                prep_events.append(event)

        return sorted(prep_events, key=lambda e: e.start_time)

    async def generate_prep_plan(
        self,
        event: CalendarEvent,
        user_memory: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a preparation plan for an event.
        """
        days_until = (event.start_time - datetime.utcnow()).days

        plan = {
            "event_id": event.id,
            "event_title": event.title,
            "event_category": event.category.value,
            "event_time": event.start_time.isoformat(),
            "days_until": days_until,
            "prep_days": event.prep_days_before,
            "keywords": event.learning_keywords,
            "suggested_sessions": [],
            "topics_to_review": [],
            "personalized": bool(user_memory)
        }

        # Generate session plan based on category
        if event.category == EventCategory.EXAM:
            plan["suggested_sessions"] = [
                {"day": -3, "focus": "Concept review", "duration_min": 45},
                {"day": -2, "focus": "Practice problems", "duration_min": 60},
                {"day": -1, "focus": "Quick review & weak areas", "duration_min": 30}
            ]
        elif event.category == EventCategory.INTERVIEW:
            plan["suggested_sessions"] = [
                {"day": -2, "focus": "Common questions practice", "duration_min": 45},
                {"day": -1, "focus": "Mock interview", "duration_min": 60}
            ]
        elif event.category == EventCategory.PRESENTATION:
            plan["suggested_sessions"] = [
                {"day": -2, "focus": "Content review", "duration_min": 30},
                {"day": -1, "focus": "Practice run-through", "duration_min": 45}
            ]
        else:
            plan["suggested_sessions"] = [
                {"day": -1, "focus": "Quick review", "duration_min": 20}
            ]

        # Extract topics from event
        if event.learning_keywords:
            plan["topics_to_review"] = event.learning_keywords[:5]

        return plan


# Global service instance
calendar_service = CalendarIntegrationService()
