"""
API routes for the Self-Evolution OS — Goals, Reflections & Recommendations.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

from .goals_service import (
    create_user_goal,
    get_user_goals,
    update_goal_status,
    add_goal_skill_mapping,
    record_progress_snapshot,
)
from .goals_schemas import (
    UserGoalCreate,
    UserGoalRead,
    GoalSkillMappingCreate,
    GoalProgressSnapshotCreate,
    GoalProgressSnapshotRead,
)
from .goals_models import GoalStatus
from .reflection_service import process_reflection, ReflectionPayload
from .recommendation_engine import get_next_upgrade

from lyo_app.events.processor import log_learning_event
from lyo_app.events.schemas import LearningEventCreate, LearningEventRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evolution", tags=["Self-Evolution OS"])


# ── Goals CRUD ────────────────────────────────────────────────

@router.post("/goals", response_model=UserGoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    target: str,
    description: Optional[str] = None,
    target_date: Optional[str] = None,
    skill_ids: Optional[List[int]] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new learning goal for the authenticated user."""
    from datetime import datetime

    parsed_date = None
    if target_date:
        try:
            parsed_date = datetime.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid target_date format. Use ISO-8601.")

    mappings = None
    if skill_ids:
        mappings = [GoalSkillMappingCreate(skill_id=sid) for sid in skill_ids]

    goal_in = UserGoalCreate(
        user_id=user.id,
        target=target,
        description=description,
        target_date=parsed_date,
        skill_mappings=mappings,
    )
    goal = await create_user_goal(db, goal_in)
    return goal


@router.get("/goals", response_model=List[UserGoalRead])
async def list_goals(
    status_filter: Optional[GoalStatus] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all goals for the authenticated user, optionally filtered by status."""
    goals = await get_user_goals(db, user.id, status=status_filter)
    return goals


@router.patch("/goals/{goal_id}/status", response_model=UserGoalRead)
async def update_goal(
    goal_id: int,
    new_status: GoalStatus,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the status of an existing goal."""
    goal = await update_goal_status(db, goal_id, new_status)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your goal")
    return goal


@router.post("/goals/{goal_id}/skills", status_code=status.HTTP_201_CREATED)
async def map_skill_to_goal(
    goal_id: int,
    mapping: GoalSkillMappingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Map an additional skill to an existing goal."""
    result = await add_goal_skill_mapping(db, goal_id, mapping)
    return {"id": result.id, "goal_id": result.goal_id, "skill_id": result.skill_id}


@router.post("/goals/{goal_id}/progress", response_model=GoalProgressSnapshotRead)
async def record_goal_progress(
    goal_id: int,
    snapshot: GoalProgressSnapshotCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a progress snapshot for a goal."""
    result = await record_progress_snapshot(db, goal_id, snapshot)
    return result


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a goal by setting its status to ABANDONED."""
    goal = await update_goal_status(db, goal_id, GoalStatus.ABANDONED)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your goal")
    return None


# ── Reflections ───────────────────────────────────────────────

@router.post("/reflections")
async def submit_reflection(
    payload: ReflectionPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a learning reflection, feeding into DKT, Goals & Memory Synthesis."""
    # Override user_id with the authenticated user
    payload.user_id = user.id
    event = await process_reflection(db, payload)
    return {
        "status": "reflected",
        "event_id": event.id,
        "confidence_normalized": event.measurable_outcome,
    }


# ── Learning Events ──────────────────────────────────────────

@router.post("/events", response_model=LearningEventRead, status_code=status.HTTP_201_CREATED)
async def log_event(
    event: LearningEventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log an explicit learning event (quiz answer, lesson completion, etc.)."""
    # Override user_id with authenticated user
    event.user_id = user.id
    result = await log_learning_event(db, event)
    return result


# ── Recommendations ──────────────────────────────────────────

@router.get("/next-upgrade")
async def next_upgrade(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the Next Best Upgrade recommendation for the authenticated user."""
    suggestion = await get_next_upgrade(db, user.id)
    if not suggestion:
        return {"suggestion": None, "message": "No upgrade suggestions available right now."}
    return {"suggestion": suggestion.to_dict()}
