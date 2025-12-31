"""
API routes for Proactive Intervention System
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

from .schemas import (
    InterventionResponse,
    GetInterventionsResponse,
    LogInterventionRequest,
    RecordInterventionResponseRequest,
    UserNotificationPreferencesUpdate,
    UserNotificationPreferencesResponse
)
from .intervention_engine import intervention_engine
from .models import Intervention, UserNotificationPreferences, InterventionType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proactive", tags=["Proactive Interventions"])


@router.get("/interventions", response_model=GetInterventionsResponse)
async def get_interventions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get proactive interventions for current user.
    Called by frontend to check if Lyo should reach out.
    """
    try:
        interventions = await intervention_engine.evaluate_interventions(
            current_user.id,
            db
        )

        return GetInterventionsResponse(
            interventions=[
                InterventionResponse(
                    intervention_type=i.intervention_type,
                    priority=i.priority,
                    title=i.title,
                    message=i.message,
                    action=i.action,
                    timing=i.timing,
                    context=i.context
                )
                for i in interventions
            ],
            count=len(interventions)
        )

    except Exception as e:
        logger.error(f"Error getting interventions for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get interventions"
        )


@router.post("/interventions/log")
async def log_intervention(
    request: LogInterventionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Log an intervention that was delivered to user.
    """
    try:
        organization_id = current_user.organization_id if hasattr(current_user, 'organization_id') else None

        intervention = Intervention(
            intervention_type=InterventionType(request.intervention_type),
            priority=request.priority,
            title=request.title,
            message=request.message,
            action=request.action,
            context=request.context
        )

        log = await intervention_engine.log_intervention(
            current_user.id,
            intervention,
            db,
            organization_id
        )

        return {
            "success": True,
            "log_id": log.id,
            "triggered_at": log.triggered_at.isoformat()
        }

    except Exception as e:
        logger.error(f"Error logging intervention for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to log intervention"
        )


@router.post("/interventions/response")
async def record_intervention_response(
    request: RecordInterventionResponseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Record user's response to an intervention (engaged, dismissed, ignored, snoozed).
    """
    try:
        await intervention_engine.record_intervention_response(
            request.intervention_log_id,
            request.user_response,
            db
        )

        return {
            "success": True,
            "message": "Response recorded"
        }

    except Exception as e:
        logger.error(f"Error recording intervention response: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record response"
        )


@router.get("/preferences", response_model=UserNotificationPreferencesResponse)
async def get_notification_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user's notification preferences.
    """
    try:
        stmt = select(UserNotificationPreferences).where(
            UserNotificationPreferences.user_id == current_user.id
        )
        result = await db.execute(stmt)
        prefs = result.scalar_one_or_none()

        if not prefs:
            # Create default preferences
            organization_id = current_user.organization_id if hasattr(current_user, 'organization_id') else None
            prefs = UserNotificationPreferences(
                user_id=current_user.id,
                organization_id=organization_id,
                dnd_enabled=False,
                max_notifications_per_day=5
            )
            db.add(prefs)
            await db.commit()
            await db.refresh(prefs)

        return UserNotificationPreferencesResponse(
            user_id=prefs.user_id,
            dnd_enabled=prefs.dnd_enabled,
            quiet_hours_start=prefs.quiet_hours_start,
            quiet_hours_end=prefs.quiet_hours_end,
            max_notifications_per_day=prefs.max_notifications_per_day,
            enabled_intervention_types=prefs.enabled_intervention_types,
            disabled_intervention_types=prefs.disabled_intervention_types,
            preferred_study_times=prefs.preferred_study_times,
            updated_at=prefs.updated_at
        )

    except Exception as e:
        logger.error(f"Error getting notification preferences for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get preferences"
        )


@router.put("/preferences", response_model=UserNotificationPreferencesResponse)
async def update_notification_preferences(
    request: UserNotificationPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update user's notification preferences.
    """
    try:
        stmt = select(UserNotificationPreferences).where(
            UserNotificationPreferences.user_id == current_user.id
        )
        result = await db.execute(stmt)
        prefs = result.scalar_one_or_none()

        if not prefs:
            # Create new preferences
            organization_id = current_user.organization_id if hasattr(current_user, 'organization_id') else None
            prefs = UserNotificationPreferences(
                user_id=current_user.id,
                organization_id=organization_id
            )
            db.add(prefs)

        # Update fields
        if request.dnd_enabled is not None:
            prefs.dnd_enabled = request.dnd_enabled
        if request.quiet_hours_start is not None:
            prefs.quiet_hours_start = request.quiet_hours_start
        if request.quiet_hours_end is not None:
            prefs.quiet_hours_end = request.quiet_hours_end
        if request.max_notifications_per_day is not None:
            prefs.max_notifications_per_day = request.max_notifications_per_day
        if request.enabled_intervention_types is not None:
            prefs.enabled_intervention_types = request.enabled_intervention_types
        if request.disabled_intervention_types is not None:
            prefs.disabled_intervention_types = request.disabled_intervention_types
        if request.preferred_study_times is not None:
            prefs.preferred_study_times = request.preferred_study_times

        await db.commit()
        await db.refresh(prefs)

        return UserNotificationPreferencesResponse(
            user_id=prefs.user_id,
            dnd_enabled=prefs.dnd_enabled,
            quiet_hours_start=prefs.quiet_hours_start,
            quiet_hours_end=prefs.quiet_hours_end,
            max_notifications_per_day=prefs.max_notifications_per_day,
            enabled_intervention_types=prefs.enabled_intervention_types,
            disabled_intervention_types=prefs.disabled_intervention_types,
            preferred_study_times=prefs.preferred_study_times,
            updated_at=prefs.updated_at
        )

    except Exception as e:
        logger.error(f"Error updating notification preferences for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences"
        )
