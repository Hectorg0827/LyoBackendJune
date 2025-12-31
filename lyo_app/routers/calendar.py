"""
Calendar Integration API Routes

Endpoints for connecting external calendars and managing
event-based learning preparation.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db as get_async_db
from lyo_app.auth.models import User
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.integrations.calendar_integration import (
    calendar_service,
    CalendarProvider,
    EventCategory
)
from lyo_app.tasks.calendar_sync import (
    sync_user_calendar_task,
    generate_prep_session_task
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["Calendar"])


# ==================== Schemas ====================

class CalendarEventResponse(BaseModel):
    """A calendar event with learning analysis."""
    id: str
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    location: Optional[str]
    category: str
    learning_keywords: List[str]
    preparation_needed: bool
    prep_days_before: int
    days_until: int
    confidence: float


class PrepPlanResponse(BaseModel):
    """Preparation plan for a learning event."""
    event_id: str
    event_title: str
    event_category: str
    event_time: datetime
    days_until: int
    prep_days: int
    keywords: List[str]
    suggested_sessions: List[dict]
    topics_to_review: List[str]
    personalized: bool


class CalendarConnectionResponse(BaseModel):
    """Status of calendar connection."""
    connected: bool
    provider: Optional[str]
    last_sync: Optional[datetime]
    events_synced: int
    upcoming_prep_events: int


class ConnectCalendarRequest(BaseModel):
    """Request to initiate calendar connection."""
    provider: str = Field(..., description="Calendar provider: google, apple, outlook")
    redirect_url: Optional[str] = Field(None, description="Custom redirect URL after OAuth")


class OAuthCallbackRequest(BaseModel):
    """OAuth callback data."""
    code: str
    state: Optional[str]
    provider: str = "google"


# ==================== Endpoints ====================

@router.get("/connect/google")
async def get_google_auth_url(
    current_user: User = Depends(get_current_user)
):
    """
    Get the Google OAuth URL to connect your calendar.

    After authorization, Google will redirect back with a code
    that you'll send to the callback endpoint.
    """
    try:
        auth_url = calendar_service.get_google_auth_url(
            user_id=current_user.id,
            state=str(current_user.id)
        )

        return {
            "auth_url": auth_url,
            "provider": "google",
            "instructions": "Redirect user to this URL to authorize calendar access"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar integration not configured"
        )


@router.post("/connect/callback")
async def handle_oauth_callback(
    request: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle OAuth callback after user authorizes calendar access.

    Exchange the authorization code for access tokens and
    store the calendar connection.
    """
    try:
        if request.provider == "google":
            connection = await calendar_service.exchange_google_code(
                code=request.code,
                user_id=current_user.id
            )

            # In production, save connection to database
            # For now, trigger initial sync
            sync_user_calendar_task.delay(
                user_id=current_user.id,
                connection_data={
                    "provider": connection.provider.value,
                    "access_token": connection.access_token,
                    "refresh_token": connection.refresh_token,
                    "token_expires_at": connection.token_expires_at.isoformat() if connection.token_expires_at else None,
                    "calendar_id": connection.calendar_id
                }
            )

            return {
                "status": "connected",
                "provider": request.provider,
                "message": "Calendar connected successfully! Syncing events...",
                "sync_status": "in_progress"
            }

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported provider: {request.provider}"
            )

    except ValueError as e:
        logger.exception(f"OAuth callback failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/status", response_model=CalendarConnectionResponse)
async def get_calendar_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the status of your calendar connection.
    """
    # In production, query CalendarConnection table
    # For now, return placeholder
    return CalendarConnectionResponse(
        connected=False,
        provider=None,
        last_sync=None,
        events_synced=0,
        upcoming_prep_events=0
    )


@router.post("/sync")
async def trigger_calendar_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Manually trigger a calendar sync.

    This fetches the latest events from your connected calendar
    and identifies any upcoming learning events that need preparation.
    """
    # In production, get connection from database
    # For now, return placeholder
    return {
        "status": "sync_queued",
        "message": "Calendar sync has been queued. You'll be notified when complete."
    }


@router.get("/events/upcoming", response_model=List[CalendarEventResponse])
async def get_upcoming_events(
    days: int = Query(default=14, ge=1, le=30, description="Days to look ahead"),
    prep_only: bool = Query(default=False, description="Only show events needing prep"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get upcoming events from your connected calendar.

    Events are analyzed for learning relevance and preparation needs.
    """
    # In production, fetch from stored calendar data
    # For now, return empty list
    return []


@router.get("/events/{event_id}/prep-plan", response_model=PrepPlanResponse)
async def get_event_prep_plan(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a personalized preparation plan for a specific event.

    The plan includes:
    - Suggested study sessions with timing
    - Topics to review based on your history
    - Personalized recommendations from your memory
    """
    # In production, fetch event and generate plan
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Event not found or no calendar connected"
    )


@router.post("/events/{event_id}/start-prep")
async def start_event_prep(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Start a preparation session for an event.

    This creates a guided study session based on:
    - The event type (exam, interview, presentation)
    - Topics detected from the event
    - Your learning history and memory
    """
    # Queue prep session generation
    generate_prep_session_task.delay(
        user_id=current_user.id,
        event_id=event_id,
        event_title="Event",  # Would come from stored data
        event_category="exam",
        keywords=[]
    )

    return {
        "status": "session_starting",
        "event_id": event_id,
        "message": "Preparing your personalized study session..."
    }


@router.delete("/disconnect")
async def disconnect_calendar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Disconnect your calendar from Lyo.

    This removes all stored calendar data and stops event syncing.
    Your calendar itself is not affected.
    """
    # In production, delete CalendarConnection and related data
    return {
        "status": "disconnected",
        "message": "Calendar disconnected. Your calendar data has been removed from Lyo."
    }


@router.get("/settings")
async def get_calendar_settings(
    current_user: User = Depends(get_current_user)
):
    """
    Get calendar integration settings.
    """
    return {
        "sync_frequency_hours": 6,
        "prep_reminder_days": [3, 1],  # Days before event to remind
        "event_categories_enabled": [
            EventCategory.EXAM.value,
            EventCategory.INTERVIEW.value,
            EventCategory.PRESENTATION.value,
            EventCategory.QUIZ.value,
            EventCategory.TEST.value,
            EventCategory.DEADLINE.value
        ],
        "auto_create_study_sessions": True,
        "quiet_hours_respected": True
    }


@router.put("/settings")
async def update_calendar_settings(
    settings: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update calendar integration settings.
    """
    # In production, save settings to user preferences
    return {
        "status": "updated",
        "message": "Calendar settings updated"
    }
