"""HTTP routes for the per-user learning profile (Stage B1).

Endpoints:
  GET   /me/learning_profile              — fetch or auto-create
  PATCH /me/learning_profile              — partial update (subjects/topics
                                            /last-classroom pointer)

Authentication: Lyo JWT (Bearer). Guests get a 401 — there's no
user_id to attach a profile to.
"""
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.learning_profile.models import LearningProfile
from lyo_app.learning_profile.schemas import (
    LearningProfileRead,
    LearningProfileUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["learning-profile"])


async def _fetch_or_create(
    db: AsyncSession, user_id: int
) -> LearningProfile:
    """Return the user's profile, creating an empty row on first access."""
    stmt = select(LearningProfile).where(LearningProfile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is not None:
        return profile

    profile = LearningProfile(
        user_id=user_id,
        known_subjects=[],
        struggle_topics=[],
        total_classroom_sessions=0,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get(
    "/learning_profile",
    response_model=LearningProfileRead,
    summary="Fetch the current user's learning profile (auto-creates on first call).",
)
async def get_my_learning_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LearningProfileRead:
    profile = await _fetch_or_create(db, user_id=current_user.id)
    return LearningProfileRead.model_validate(profile)


@router.patch(
    "/learning_profile",
    response_model=LearningProfileRead,
    summary="Partial update of the user's learning profile.",
)
async def update_my_learning_profile(
    payload: LearningProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LearningProfileRead:
    profile = await _fetch_or_create(db, user_id=current_user.id)

    # Field-by-field application. None means "leave alone."
    if payload.known_subjects is not None:
        profile.known_subjects = _clean_list(payload.known_subjects, max_items=20)
    if payload.struggle_topics is not None:
        profile.struggle_topics = _clean_list(payload.struggle_topics, max_items=20)

    if payload.last_classroom_topic is not None:
        profile.last_classroom_topic = payload.last_classroom_topic[:200]
    if payload.last_classroom_session_id is not None:
        profile.last_classroom_session_id = payload.last_classroom_session_id[:100]

    if payload.record_classroom_session:
        profile.last_classroom_at = datetime.utcnow()
        profile.total_classroom_sessions += 1

    profile.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(profile)
    return LearningProfileRead.model_validate(profile)


@router.get(
    "/identity",
    summary="The learner's persistent 'learning identity': mastery heatmap, "
            "strengths/gaps, long-term memory, active goals, and a learning arc.",
)
async def get_learning_identity(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Aggregate the durable learner identity from existing subsystems.

    This is what makes Lyo a 'learning identity, not a chat session': it composes
    the DKT mastery profile (personalization), long-term memory (memory
    synthesis), and active goals (evolution) into one persistent view. Each
    source degrades independently so a missing subsystem never 500s the call.
    """
    uid = current_user.id
    identity: dict = {"user_id": uid}

    # 1. Mastery heatmap + strengths/weaknesses (DKT)
    try:
        from lyo_app.personalization.service import personalization_engine
        mp = await personalization_engine.get_mastery_profile(db, str(uid))
        identity["mastery_heatmap"] = mp.skills            # skill_id -> level
        identity["strengths"] = mp.strengths
        identity["weaknesses"] = mp.weaknesses
        identity["recommended_focus"] = mp.recommended_focus
        identity["learning_velocity"] = mp.learning_velocity
        identity["optimal_difficulty"] = mp.optimal_difficulty
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning(f"identity: mastery unavailable for {uid}: {e}")
        identity["mastery_heatmap"] = {}
        identity["strengths"] = []
        identity["weaknesses"] = []

    # 2. Long-term memory blob (memory synthesis)
    try:
        from lyo_app.services.memory_synthesis import memory_synthesis_service
        identity["memory"] = await memory_synthesis_service.get_memory_for_prompt(uid, db)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning(f"identity: memory unavailable for {uid}: {e}")
        identity["memory"] = None

    # 3. Active goals (evolution)
    try:
        from lyo_app.evolution.goals_service import get_user_goals
        from lyo_app.evolution.goals_models import GoalStatus
        goals = await get_user_goals(db, uid, status=GoalStatus.ACTIVE)
        identity["active_goals"] = [
            {"id": g.id, "target": g.target, "description": g.description,
             "status": g.status.value if hasattr(g.status, "value") else g.status}
            for g in goals
        ]
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning(f"identity: goals unavailable for {uid}: {e}")
        identity["active_goals"] = []

    # 4. Lightweight learning arc summary (no LLM needed; deterministic)
    mastered = len(identity.get("strengths", []))
    focus = identity.get("weaknesses", [])
    identity["learning_arc"] = {
        "skills_mastered": mastered,
        "next_frontier": focus[:3],
        "summary": (
            f"You've mastered {mastered} skill(s); "
            + (f"your current frontier is {', '.join(focus[:3])}."
               if focus else "ready for new challenges.")
        ),
    }
    return identity


def _clean_list(items: list[str], *, max_items: int) -> list[str]:
    """Lowercase, trim, dedupe, cap. Keeps the table small + free-form."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        s = raw.strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        result.append(s)
        if len(result) >= max_items:
            break
    return result
