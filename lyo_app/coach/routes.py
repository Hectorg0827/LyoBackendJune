"""Authenticated API for the Lyo Coach control plane."""

from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User

from .schemas import (
    GoalCoachView,
    LearningGoalCreate,
    LearningGoalPatch,
    LearningGoalRead,
    TodayCoachView,
)
from .service import (
    CoachEvidenceUnavailable,
    _as_utc_naive,
    _goal_read,
    _skills_for_goal,
    active_goals,
    build_goal_view,
    build_today_view,
    create_goal,
    owned_goal,
)

router = APIRouter(prefix="/me/coach", tags=["Lyo Coach"])


async def _require_evidence(awaitable):
    try:
        return await awaitable
    except CoachEvidenceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Learner evidence is temporarily unavailable; the last valid coach state remains authoritative.",
        ) from exc


@router.get("/goals", response_model=List[LearningGoalRead])
async def list_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All active goals, including lazily adapted existing Test Prep goals."""

    goals = await active_goals(db, current_user.id)
    result = [
        _goal_read(goal, await _skills_for_goal(db, current_user.id, goal.id))
        for goal in goals
    ]
    # Lazy Test Prep adaptation is a write; make it durable on a read so the
    # next surface sees the same goal identity.
    await db.commit()
    return result


@router.post("/goals", response_model=GoalCoachView, status_code=status.HTTP_201_CREATED)
async def add_goal(
    body: LearningGoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await create_goal(db, current_user.id, body, source_surface="coach")
    view = await _require_evidence(
        build_goal_view(db, current_user.id, goal, use_cache=False)
    )
    await db.commit()
    return view


@router.get("/goals/{goal_id}", response_model=GoalCoachView)
async def get_goal(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await owned_goal(db, current_user.id, goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning goal not found")
    view = await _require_evidence(build_goal_view(db, current_user.id, goal))
    await db.commit()
    return view


@router.patch("/goals/{goal_id}", response_model=GoalCoachView)
async def update_goal(
    goal_id: str,
    body: LearningGoalPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await owned_goal(db, current_user.id, goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning goal not found")

    updates = body.model_dump(exclude_unset=True)
    if "deadline" in updates:
        updates["deadline"] = _as_utc_naive(updates["deadline"])
    for key, value in updates.items():
        setattr(goal, key, value)
    goal.updated_at = datetime.utcnow()

    await db.flush()
    view = await _require_evidence(
        build_goal_view(db, current_user.id, goal, use_cache=False)
    )
    await db.commit()
    return view


@router.post("/goals/{goal_id}/refresh", response_model=GoalCoachView)
async def refresh_goal(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force a fresh projection from evidence; useful after a client completes work."""

    goal = await owned_goal(db, current_user.id, goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning goal not found")
    view = await build_goal_view(db, current_user.id, goal, use_cache=False)
    await db.commit()
    return view


@router.get("/today", response_model=TodayCoachView)
async def today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The receding-horizon mission across every active learning goal."""

    view = await _require_evidence(build_today_view(db, current_user.id))
    await db.commit()
    return view
