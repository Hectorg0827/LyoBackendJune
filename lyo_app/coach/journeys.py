"""Authenticated, idempotent navigation handoffs across existing learning engines.

A journey is NOT a course, lesson, transcript or Test Prep plan. It stores
only what a client needs to return to the existing engine with intact IDs.
No grade, mastery, readiness or evidence is created by this router.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from .journey_models import JourneyHandoff, LearningJourney
from .journey_schemas import (
    JourneyContext,
    JourneyHandoffRead,
    JourneyHandoffRequest,
    JourneyRead,
    JourneyStart,
)
from .service import owned_goal

router = APIRouter(tags=["Lyo Journey Continuity"])


def _snapshot(journey: LearningJourney) -> JourneyRead:
    return JourneyRead(
        id=journey.id,
        goal_id=journey.goal_id,
        origin_surface=journey.origin_surface,
        origin_ref=journey.origin_ref,
        active_surface=journey.active_surface,
        active_ref=journey.active_ref,
        status=journey.status,
        revision=journey.revision,
        context=JourneyContext.model_validate(journey.context_json or {}),
        updated_at=journey.updated_at,
    )


def _handoff_read(handoff: JourneyHandoff) -> JourneyHandoffRead:
    return JourneyHandoffRead(
        id=handoff.id,
        revision=handoff.revision,
        from_surface=handoff.from_surface,
        from_ref=handoff.from_ref,
        to_surface=handoff.to_surface,
        to_ref=handoff.to_ref,
        context=JourneyContext.model_validate(handoff.context_json or {}),
        created_at=handoff.created_at,
    )


def _validate_test_link(goal, context: dict) -> None:
    """Prevent navigation state from impersonating another exam profile.

    The destination endpoint must STILL enforce object ownership: the journey
    is a navigation reference, never an access-grant token.
    """
    profile_id = context.get("test_profile_id")
    if profile_id and not (
        goal.source_ref_type == "test_profile" and goal.source_ref_id == profile_id
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Test profile does not belong to this learning goal",
        )


async def _owned_journey(db: AsyncSession, user_id: int, journey_id: str, *, lock=False):
    query = select(LearningJourney).where(
        LearningJourney.id == journey_id,
        LearningJourney.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    journey = (await db.execute(query)).scalar_one_or_none()
    if journey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning journey not found")
    return journey


def _start_matches(existing: LearningJourney, body: JourneyStart, context: dict) -> None:
    if (
        existing.goal_id != body.goal_id
        or existing.origin_surface != body.origin_surface
        or existing.origin_ref != body.origin_ref
        or dict(existing.initial_context_json or {}) != context
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Request ID already used for another journey")


@router.post("", response_model=JourneyRead, status_code=status.HTTP_201_CREATED)
async def start_journey(
    body: JourneyStart,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user.id
    context = body.context.model_dump(exclude_none=True)

    # Replays return the exact same journey, even after further transitions.
    existing = (
        await db.execute(select(LearningJourney).where(
            LearningJourney.user_id == user_id,
            LearningJourney.start_request_id == body.request_id,
        ))
    ).scalar_one_or_none()
    if existing is not None:
        _start_matches(existing, body, context)
        return _snapshot(existing)

    goal = await owned_goal(db, user_id, body.goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning goal not found")
    if goal.status not in ("active", "paused"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Learning goal is not active")
    _validate_test_link(goal, context)

    journey = LearningJourney(
        user_id=user_id,
        goal_id=goal.id,
        start_request_id=body.request_id,
        origin_surface=body.origin_surface,
        origin_ref=body.origin_ref,
        active_surface=body.origin_surface,
        active_ref=body.origin_ref,
        initial_context_json=context,
        context_json=context,
        revision=0,
        status="active",
    )
    # Savepoint keeps the surrounding request/session healthy if another
    # concurrent request commits the same idempotency key first.
    try:
        async with db.begin_nested():
            db.add(journey)
            await db.flush()
    except IntegrityError:
        existing = (
            await db.execute(select(LearningJourney).where(
                LearningJourney.user_id == user_id,
                LearningJourney.start_request_id == body.request_id,
            ))
        ).scalar_one_or_none()
        if existing is None:
            raise
        _start_matches(existing, body, context)
        return _snapshot(existing)

    await db.commit()
    return _snapshot(journey)


@router.get("", response_model=List[JourneyRead])
async def list_journeys(
    goal_id: Optional[str] = Query(default=None, max_length=36),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(LearningJourney).where(LearningJourney.user_id == current_user.id)
    if goal_id is not None:
        query = query.where(LearningJourney.goal_id == goal_id)
    rows = (await db.execute(
        query.order_by(LearningJourney.updated_at.desc()).limit(limit)
    )).scalars().all()
    return [_snapshot(row) for row in rows]


@router.get("/{journey_id}", response_model=JourneyRead)
async def get_journey(
    journey_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _snapshot(await _owned_journey(db, current_user.id, journey_id))


@router.get("/{journey_id}/handoffs", response_model=List[JourneyHandoffRead])
async def list_handoffs(
    journey_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_journey(db, current_user.id, journey_id)
    rows = (await db.execute(
        select(JourneyHandoff).where(
            JourneyHandoff.journey_id == journey_id,
            JourneyHandoff.user_id == current_user.id,
        ).order_by(JourneyHandoff.revision.asc())
    )).scalars().all()
    return [_handoff_read(row) for row in rows]


@router.post("/{journey_id}/handoffs", response_model=JourneyHandoffRead, status_code=status.HTTP_201_CREATED)
async def handoff(
    journey_id: str,
    body: JourneyHandoffRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user.id
    requested_context = body.context.model_dump(exclude_none=True)
    journey = await _owned_journey(db, user_id, journey_id, lock=True)

    # Replay validation precedes revision checks; a legitimate retry still
    # returns its original event after other work has advanced the journey.
    existing = (await db.execute(
        select(JourneyHandoff).where(
            JourneyHandoff.journey_id == journey.id,
            JourneyHandoff.request_id == body.request_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        if (
            existing.to_surface != body.target_surface
            or existing.to_ref != body.target_ref
            or existing.revision != body.expected_revision + 1
            or dict(existing.requested_context or {}) != requested_context
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Request ID already used for another handoff")
        return _handoff_read(existing)

    if journey.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Learning journey is not active")
    if journey.revision != body.expected_revision:
        raise HTTPException(status.HTTP_409_CONFLICT, "Journey changed; reload before switching")
    if journey.active_surface == body.target_surface and journey.active_ref == body.target_ref:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Already on requested surface")

    context = {**dict(journey.context_json or {}), **requested_context}
    goal = await owned_goal(db, user_id, journey.goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning goal not found")
    if goal.status not in ("active", "paused"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Learning goal is not active")
    _validate_test_link(goal, context)

    event = JourneyHandoff(
        journey_id=journey.id,
        user_id=user_id,
        request_id=body.request_id,
        revision=journey.revision + 1,
        from_surface=journey.active_surface,
        from_ref=journey.active_ref,
        to_surface=body.target_surface,
        to_ref=body.target_ref,
        requested_context=requested_context,
        context_json=context,
    )
    db.add(event)
    journey.revision += 1
    journey.active_surface = body.target_surface
    journey.active_ref = body.target_ref
    journey.context_json = context

    await db.flush()
    await db.commit()
    return _handoff_read(event)
