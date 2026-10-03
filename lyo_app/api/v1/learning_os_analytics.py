"""Authenticated reporting endpoints for empirical Learning OS metrics."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.rbac import PermissionType
from lyo_app.auth.security_middleware import PermissionChecker
from lyo_app.teaching_runtime.analytics import load_learning_os_analytics


router = APIRouter()


@router.get("/analytics/me")
async def my_learning_os_analytics(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Outcome analytics for the authenticated learner only."""
    return await load_learning_os_analytics(
        db,
        days=days,
        user_id=int(current_user.id),
    )


@router.get("/analytics/system")
async def system_learning_os_analytics(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Anonymous aggregate Learning OS outcomes for analytics administrators."""
    if not await PermissionChecker.check_permission(
        current_user, PermissionType.VIEW_ANALYTICS
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return await load_learning_os_analytics(db, days=days)
