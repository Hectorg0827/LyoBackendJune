"""HTTP routes for the per-user study plans (Stage B2).

Endpoints (all under /me/study_plans, mounted at /api/v1):
  GET    /                  — list the user's active plans (most recent first)
  POST   /                  — create a new plan
  GET    /{plan_id}         — fetch one plan by id
  PATCH  /{plan_id}         — partial update (subject / topics / deadline / status)
  DELETE /{plan_id}         — soft-delete (sets status='abandoned')

Authentication: Lyo JWT only.
"""
from datetime import datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.study_plans.models import StudyPlan
from lyo_app.study_plans.schemas import (
    StudyPlanCreate,
    StudyPlanRead,
    StudyPlanUpdate,
)

router = APIRouter(prefix="/me/study_plans", tags=["study-plans"])


@router.get(
    "",
    response_model=List[StudyPlanRead],
    summary="List the current user's study plans (active first).",
)
async def list_plans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_completed: bool = Query(
        default=False,
        description="If true, also returns abandoned/completed plans.",
    ),
) -> List[StudyPlanRead]:
    stmt = select(StudyPlan).where(StudyPlan.user_id == current_user.id)
    if not include_completed:
        stmt = stmt.where(StudyPlan.status == "active")
    stmt = stmt.order_by(desc(StudyPlan.updated_at))

    result = await db.execute(stmt)
    plans = result.scalars().all()
    return [StudyPlanRead.model_validate(p) for p in plans]


@router.post(
    "",
    response_model=StudyPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new study plan from chat.",
)
async def create_plan(
    payload: StudyPlanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudyPlanRead:
    plan = StudyPlan(
        user_id=current_user.id,
        subject=payload.subject.strip(),
        topics=_clean_list(payload.topics, max_items=20),
        deadline=payload.deadline.strip() if payload.deadline else None,
        daily_breakdown=_clean_list(payload.daily_breakdown, max_items=14, lowercase=False),
        source_conversation_id=payload.source_conversation_id,
        status="active",
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return StudyPlanRead.model_validate(plan)


@router.get(
    "/{plan_id}",
    response_model=StudyPlanRead,
    summary="Fetch a single plan by id (must be owned by the current user).",
)
async def get_plan(
    plan_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudyPlanRead:
    plan = await _load_owned_plan(db, plan_id=plan_id, user_id=current_user.id)
    return StudyPlanRead.model_validate(plan)


@router.patch(
    "/{plan_id}",
    response_model=StudyPlanRead,
    summary="Partial update of a plan.",
)
async def update_plan(
    plan_id: int,
    payload: StudyPlanUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudyPlanRead:
    plan = await _load_owned_plan(db, plan_id=plan_id, user_id=current_user.id)

    if payload.subject is not None:
        plan.subject = payload.subject.strip()
    if payload.topics is not None:
        plan.topics = _clean_list(payload.topics, max_items=20)
    if payload.deadline is not None:
        plan.deadline = payload.deadline.strip() or None
    if payload.daily_breakdown is not None:
        plan.daily_breakdown = _clean_list(
            payload.daily_breakdown, max_items=14, lowercase=False
        )
    if payload.status is not None:
        plan.status = payload.status
        if payload.status == "completed":
            plan.completed_at = datetime.utcnow()

    plan.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(plan)
    return StudyPlanRead.model_validate(plan)


@router.delete(
    "/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete (mark abandoned).",
)
async def delete_plan(
    plan_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    plan = await _load_owned_plan(db, plan_id=plan_id, user_id=current_user.id)
    plan.status = "abandoned"
    plan.updated_at = datetime.utcnow()
    await db.commit()


# MARK: - Internals

async def _load_owned_plan(
    db: AsyncSession, *, plan_id: int, user_id: int
) -> StudyPlan:
    stmt = select(StudyPlan).where(
        StudyPlan.id == plan_id, StudyPlan.user_id == user_id
    )
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Study plan not found")
    return plan


def _clean_list(items: list[str], *, max_items: int, lowercase: bool = True) -> list[str]:
    """Trim, dedupe, cap. `lowercase=True` for free-form topics; False for
    `daily_breakdown` items where casing matters ('Tuesday: photosynthesis')."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s.lower() if lowercase else s)
        if len(out) >= max_items:
            break
    return out
