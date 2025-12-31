"""
API routes for Ambient Presence System
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

from .schemas import (
    PresenceUpdateRequest,
    InlineHelpRequest,
    InlineHelpResponse,
    LogInlineHelpRequest,
    RecordHelpResponseRequest,
    QuickActionsRequest,
    QuickActionsResponse,
    QuickActionResponse
)
from .presence_manager import presence_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ambient", tags=["Ambient Presence"])


@router.post("/presence/update")
async def update_presence(
    request: PresenceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update user's current presence state.
    Called when user navigates or interacts with content.
    """
    try:
        context = {
            'page': request.page,
            'topic': request.topic,
            'content_id': request.content_id,
            'time_on_page': request.time_on_page,
            'scroll_count': request.scroll_count,
            'mouse_hesitations': request.mouse_hesitations,
            'organization_id': current_user.organization_id if hasattr(current_user, 'organization_id') else None,
            **(request.context or {})
        }

        state = await presence_manager.update_presence(
            db,
            current_user.id,
            context
        )

        return {
            "success": True,
            "message": "Presence updated",
            "last_seen_at": state.last_seen_at.isoformat()
        }

    except Exception as e:
        logger.error(f"Error updating presence for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update presence"
        )


@router.post("/inline-help/check", response_model=InlineHelpResponse)
async def check_inline_help(
    request: InlineHelpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if inline help should be shown based on user behavior.
    """
    try:
        should_show, help_message = await presence_manager.should_show_inline_help(
            db,
            current_user.id,
            request.current_context,
            request.user_behavior
        )

        return InlineHelpResponse(
            should_show=should_show,
            help_message=help_message,
            help_type="contextual" if should_show else None
        )

    except Exception as e:
        logger.error(f"Error checking inline help for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check inline help"
        )


@router.post("/inline-help/log")
async def log_inline_help(
    request: LogInlineHelpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Log when inline help is shown to user.
    """
    try:
        organization_id = current_user.organization_id if hasattr(current_user, 'organization_id') else None

        log = await presence_manager.log_inline_help(
            db,
            current_user.id,
            request.help_type,
            request.help_text,
            request.page,
            request.topic,
            request.content_id,
            organization_id
        )

        return {
            "success": True,
            "log_id": log.id,
            "shown_at": log.shown_at.isoformat()
        }

    except Exception as e:
        logger.error(f"Error logging inline help for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to log inline help"
        )


@router.post("/inline-help/response")
async def record_help_response(
    request: RecordHelpResponseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Record user's response to inline help (accepted, dismissed, ignored).
    """
    try:
        await presence_manager.record_help_response(
            db,
            request.help_log_id,
            request.user_response
        )

        return {
            "success": True,
            "message": "Response recorded"
        }

    except Exception as e:
        logger.error(f"Error recording help response: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record response"
        )


@router.post("/quick-actions", response_model=QuickActionsResponse)
async def get_quick_actions(
    request: QuickActionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get contextual quick actions for Cmd+K palette or floating widget.
    """
    try:
        actions = await presence_manager.get_contextual_quick_actions(
            db,
            current_user.id,
            request.current_page,
            request.current_content
        )

        return QuickActionsResponse(
            actions=[
                QuickActionResponse(
                    id=action.id,
                    label=action.label,
                    action_type=action.action_type,
                    icon=action.icon,
                    context=action.context
                )
                for action in actions
            ]
        )

    except Exception as e:
        logger.error(f"Error getting quick actions for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get quick actions"
        )
