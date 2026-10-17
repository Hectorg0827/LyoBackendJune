"""Real SQL persistence and authorization checks for Lyo's unified journey.

This API stores navigation continuity; it must never award mastery or grades.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.coach.journey_models import LearningJourney, JourneyHandoff
from lyo_app.coach.journey_schemas import JourneyContext, JourneyHandoffRequest, JourneyStart
from lyo_app.coach.journeys import (
    get_journey,
    handoff,
    list_handoffs,
    list_journeys,
    start_journey,
)
from lyo_app.coach.models import LearningGoal


def _user(id):
    return SimpleNamespace(id=id)


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(LearningGoal.__table__.create)
        await conn.run_sync(LearningJourney.__table__.create)
        await conn.run_sync(JourneyHandoff.__table__.create)
    return engine


def _goal(user=7, goal_id="goal-a", *, exam=None):
    return LearningGoal(
        id=goal_id,
        user_id=user,
        goal_type="test" if exam else "mastery",
        title="Chemistry" if exam else "Learn anything",
        subject="Chemistry" if exam else None,
        status="active",
        desired_outcome={},
        constraints={},
        source_ref_type="test_profile" if exam else None,
        source_ref_id=exam,
    )


async def _new(db, *, user=7, goal_id="goal-a", key="start-request-a", context=None):
    return await start_journey(
        JourneyStart(
            request_id=key,
            goal_id=goal_id,
            origin_surface="chat",
            origin_ref="chat-42",
            context=context or JourneyContext(chat_session_id="chat-42"),
        ),
        current_user=_user(user),
        db=db,
    )


@pytest.mark.asyncio
async def test_create_and_reopen_survive_a_new_db_session():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal())
            await db.commit()
            created = await _new(db)
            assert created.revision == 0
            assert created.active_surface == "chat"

        async with AsyncSession(engine, expire_on_commit=False) as db:
            reopened = await get_journey(created.id, current_user=_user(7), db=db)
            assert reopened.id == created.id
            assert reopened.goal_id == "goal-a"
            assert reopened.context.chat_session_id == "chat-42"
            records = await list_journeys(goal_id=None, limit=20, current_user=_user(7), db=db)
            assert [r.id for r in records] == [created.id]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unchanged_retry_reuses_journey_but_conflicting_key_is_rejected():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal())
            await db.commit()
            one = await _new(db)
            replay = await _new(db)
            assert replay.id == one.id
            with pytest.raises(HTTPException) as exc:
                await _new(db, goal_id="other-goal")
            assert exc.value.status_code == 409
            assert (await db.execute(select(LearningJourney))).scalars().all().__len__() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_exact_exam_profile_is_bound_to_its_owned_goal():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal(exam="exam-A"))
            await db.commit()
            with pytest.raises(HTTPException) as exc:
                await _new(db, context=JourneyContext(test_profile_id="exam-B"))
            assert exc.value.status_code == 422
            valid = await _new(db, context=JourneyContext(test_profile_id="exam-A"))
            assert valid.context.test_profile_id == "exam-A"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_user_reads_and_handoffs_fail_closed():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal())
            await db.commit()
            journey = await _new(db)
            with pytest.raises(HTTPException) as exc:
                await get_journey(journey.id, current_user=_user(8), db=db)
            assert exc.value.status_code == 404
            with pytest.raises(HTTPException) as exc:
                await handoff(
                    journey.id,
                    JourneyHandoffRequest(request_id="handoff-a1", expected_revision=0, target_surface="classroom"),
                    current_user=_user(8),
                    db=db,
                )
            assert exc.value.status_code == 404
            assert await list_journeys(goal_id=None, limit=20, current_user=_user(8), db=db) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_chat_to_classroom_to_test_prep_retains_question_and_durable_history():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal(exam="exam-A"))
            await db.commit()
            started = await _new(db, context=JourneyContext(chat_session_id="chat-42", test_profile_id="exam-A"))
            first = await handoff(
                started.id,
                JourneyHandoffRequest(
                    request_id="handoff-classroom",
                    expected_revision=0,
                    target_surface="classroom",
                    target_ref="lesson-5",
                    context=JourneyContext(question_id="question-4", concept_id="bonding"),
                ),
                current_user=_user(7), db=db,
            )
            assert first.revision == 1
            assert first.from_surface == "chat"
            assert first.context.test_profile_id == "exam-A"
            assert first.context.question_id == "question-4"
            second = await handoff(
                started.id,
                JourneyHandoffRequest(
                    request_id="handoff-back-to-exam",
                    expected_revision=1,
                    target_surface="test_prep",
                    target_ref="question-4",
                ),
                current_user=_user(7), db=db,
            )
            assert second.revision == 2
            assert second.context.question_id == "question-4"

        async with AsyncSession(engine, expire_on_commit=False) as db:
            reopened = await get_journey(started.id, current_user=_user(7), db=db)
            assert reopened.revision == 2
            assert reopened.active_surface == "test_prep"
            assert reopened.active_ref == "question-4"
            assert reopened.context.chat_session_id == "chat-42"
            events = await list_handoffs(started.id, current_user=_user(7), db=db)
            assert [event.to_surface for event in events] == ["classroom", "test_prep"]
            assert [event.revision for event in events] == [1, 2]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retry_returns_exact_original_event_after_subsequent_transition():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal())
            await db.commit()
            j = await _new(db)
            request = JourneyHandoffRequest(
                request_id="handoff-classroom",
                expected_revision=0,
                target_surface="classroom",
                target_ref="course-1",
            )
            first = await handoff(j.id, request, current_user=_user(7), db=db)
            await handoff(
                j.id,
                JourneyHandoffRequest(request_id="handoff-chat", expected_revision=1, target_surface="chat"),
                current_user=_user(7), db=db,
            )
            replay = await handoff(j.id, request, current_user=_user(7), db=db)
            initial_replay = await _new(db)
            assert initial_replay.id == j.id
            assert initial_replay.revision == 2
            assert replay.id == first.id
            assert replay.revision == 1
            assert (await get_journey(j.id, current_user=_user(7), db=db)).revision == 2
            with pytest.raises(HTTPException) as exc:
                await handoff(
                    j.id,
                    JourneyHandoffRequest(request_id="handoff-classroom", expected_revision=0, target_surface="coach"),
                    current_user=_user(7), db=db,
                )
            assert exc.value.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_revision_cannot_rewrite_another_tab_and_same_surface_is_rejected():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(_goal())
            await db.commit()
            j = await _new(db)
            with pytest.raises(HTTPException) as exc:
                await handoff(
                    j.id,
                    JourneyHandoffRequest(request_id="handoff-invalid", expected_revision=0, target_surface="chat", target_ref="chat-42"),
                    current_user=_user(7), db=db,
                )
            assert exc.value.status_code == 422
            await handoff(
                j.id,
                JourneyHandoffRequest(request_id="handoff-classroom", expected_revision=0, target_surface="classroom"),
                current_user=_user(7), db=db,
            )
            with pytest.raises(HTTPException) as exc:
                await handoff(
                    j.id,
                    JourneyHandoffRequest(request_id="handoff-old-tab", expected_revision=0, target_surface="test_prep"),
                    current_user=_user(7), db=db,
                )
            assert exc.value.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owned_journey_rejects_missing_or_inactive_goal():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(HTTPException) as exc:
                await _new(db)
            assert exc.value.status_code == 404
            inactive = _goal()
            inactive.status = "archived"
            db.add(inactive)
            await db.commit()
            with pytest.raises(HTTPException) as exc:
                await _new(db)
            assert exc.value.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_archived_goal_cannot_be_reused_for_a_new_handoff():
    engine = await _database()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            goal = _goal()
            db.add(goal)
            await db.commit()
            j = await _new(db)
            goal.status = "archived"
            await db.commit()
            with pytest.raises(HTTPException) as exc:
                await handoff(
                    j.id,
                    JourneyHandoffRequest(
                        request_id="handoff-after-archive",
                        expected_revision=0,
                        target_surface="classroom",
                    ),
                    current_user=_user(7),
                    db=db,
                )
            assert exc.value.status_code == 409
            assert (await get_journey(j.id, current_user=_user(7), db=db)).revision == 0
    finally:
        await engine.dispose()


def test_untrusted_extra_state_and_invalid_surface_do_not_enter_navigation_contract():
    with pytest.raises(ValidationError):
        JourneyContext(secret="never store arbitrary memory")
    with pytest.raises(ValidationError):
        JourneyStart(goal_id="goal-a", request_id="token-a123", origin_surface="grade")
    with pytest.raises(ValidationError):
        JourneyHandoffRequest(
            request_id="handoff-anything", expected_revision=0,
            target_surface="classroom", unearned_mastery=1.0,
        )
