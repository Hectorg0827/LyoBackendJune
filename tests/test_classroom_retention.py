"""What the classroom leaves behind: a skill that comes back.

A lesson can show that a learner could do something today. Only a schedule can
tell you whether they still can next week, and spaced retrieval is the
best-evidenced way of making sure they do.

The classroom had no way into the scheduler. Every writer of
`SpacedRepetitionSchedule` was somewhere else — Chat's answer check, and review
endpoints that can update a schedule but not create one — so a learner taught
here finished units, earned evidence, and never had a single thing come due.
The summary screen's "try a fresh example in a later session to see what
sticks" was an invitation with nothing behind it.

These tests are about that write: that it happens once per unit rather than
once per question, that a skill the learner could not do comes back soonest,
and that replaying the durable queue cannot push a review further out than the
learner's work earned.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState
from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine
from lyo_app.ai_classroom.sdui_models import ActionIntent
from lyo_app.personalization.models import SpacedRepetitionSchedule
from lyo_app.personalization.spaced_repetition import (
    FIRST_INTERVAL_DAYS, QUALITY_FOR_CORRECT, QUALITY_FOR_INCORRECT)
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, evaluation, tap_probe)


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


async def answer(runner, progress, ctx, option="a"):
    await advance_to_task(runner, progress, ctx)
    pending = state(progress).pending
    if pending.task.response_format == "choice":
        return await runner.run(ctx, progress, action(
            ActionIntent.SUBMIT_ANSWER, pending.id, answer_data={"selected_option_id": option}))
    return await runner.run(ctx, progress, action(
        ActionIntent.SUBMIT_TRANSFER, pending.id,
        answer_data={"response": "One half: fewer equal cuts of the same whole leave more on each piece."}))


async def finish_a_unit(teacher=None):
    """Walk one unit to a completed independent application."""
    runner, progress, ctx = AdaptiveSession(teacher or ScriptedTeacher()), {}, context(target_duration_minutes=8)
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    for _ in range(5):
        if state(progress).unit_done or state(progress).path_done:
            break
        await answer(runner, progress, ctx)
    return runner, progress, ctx


# ── One write per unit ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finishing_a_unit_queues_one_review_not_one_per_question():
    _, progress, _ = await finish_a_unit()
    current = state(progress)
    assert current.completed == [0] and current.independent_application
    # Four graded answers, one review. SM-2 counts each write as a separate
    # sitting, so a write per checkpoint would stretch the interval as though
    # four days had passed inside one lesson.
    assert len(current.outbox) >= 3
    assert len(current.review_outbox) == 1
    queued = current.review_outbox[0]
    assert queued["passed"] is True
    assert queued["concept_id"] == "Fractions"  # canonicalised on the way out
    assert queued["decided_at"]


@pytest.mark.asyncio
async def test_a_unit_the_learner_could_not_do_comes_back_as_a_failed_recall():
    teacher = ScriptedTeacher()
    teacher.evaluate.return_value = evaluation(
        "incorrect", feedback="More equal cuts make each piece smaller, not bigger.",
        misconception="more_pieces_means_more_each")
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(target_duration_minutes=8)
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx, "b")
    for _ in range(8):
        await advance_to_task(runner, progress, ctx)
        current = state(progress)
        if current.unit_done or current.path_done or current.pending is None:
            break
        await answer(runner, progress, ctx, option="b")
    current = state(progress)
    assert current.skipped == [0] and current.completed == []
    # The skill they could not do is the one most worth bringing back soonest,
    # so it is scheduled as a failed recall rather than left out entirely.
    assert len(current.review_outbox) == 1 and current.review_outbox[0]["passed"] is False


@pytest.mark.asyncio
async def test_skipping_a_practice_question_still_schedules_the_revisit():
    runner, progress, ctx = AdaptiveSession(ScriptedTeacher()), {}, context(target_duration_minutes=8)
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    await advance_to_task(runner, progress, ctx)
    await runner.run(ctx, progress, action(ActionIntent.SKIP_QUESTION, state(progress).pending.id))
    current = state(progress)
    assert current.skipped == [0]
    assert len(current.review_outbox) == 1 and current.review_outbox[0]["passed"] is False


@pytest.mark.asyncio
async def test_the_opening_probe_alone_schedules_nothing():
    # Nothing has been taught and nothing demonstrated, so there is nothing to
    # bring back — the probe is the starting line, not a review item.
    runner, progress, ctx = AdaptiveSession(ScriptedTeacher()), {}, context(target_duration_minutes=8)
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    assert state(progress).review_outbox == []


# ── The write lands in the one schedule the product reads ────────────────────

async def drain(db, progress):
    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = db
    snapshot = progress["guided_state"]
    remaining = []
    for review in snapshot["review_outbox"]:
        if not await engine._schedule_adaptive_review(**review):
            remaining.append(review)
    snapshot["review_outbox"] = remaining
    return snapshot


@pytest.mark.asyncio
async def test_the_review_reaches_the_schedule_the_rest_of_the_product_reads():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(SpacedRepetitionSchedule.__table__.create)
        _, progress, _ = await finish_a_unit()
        async with AsyncSession(database) as db:
            snapshot = await drain(db, progress)
            assert snapshot["review_outbox"] == [], "a successful write leaves the queue empty"
            rows = (await db.execute(select(SpacedRepetitionSchedule))).scalars().all()
            assert len(rows) == 1
            row = rows[0]
            assert row.user_id == 42 and row.item_id == "fractions"
            assert row.last_grade == QUALITY_FOR_CORRECT
            assert row.repetitions == 1 and row.interval == FIRST_INTERVAL_DAYS
            # Due tomorrow, which is what makes it show up in a review queue at
            # all — the thing that never happened before.
            assert row.next_review is not None
            assert timedelta(hours=20) < (row.next_review - datetime.utcnow()) < timedelta(hours=28)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_replaying_the_queue_does_not_push_the_next_review_further_out():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(SpacedRepetitionSchedule.__table__.create)
        _, progress, _ = await finish_a_unit()
        queued = list(progress["guided_state"]["review_outbox"])
        async with AsyncSession(database) as db:
            await drain(db, progress)
            first = (await db.execute(select(SpacedRepetitionSchedule))).scalars().one()
            interval, repetitions = first.interval, first.repetitions
            # A crash between writing and persisting the drained queue replays
            # it. Applying it twice would count one lesson as two sittings.
            progress["guided_state"]["review_outbox"] = queued
            await drain(db, progress)
            again = (await db.execute(select(SpacedRepetitionSchedule))).scalars().one()
            assert (again.interval, again.repetitions) == (interval, repetitions)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_a_failed_unit_is_scheduled_as_a_failure_when_it_reaches_the_table():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(SpacedRepetitionSchedule.__table__.create)
        async with AsyncSession(database) as db:
            engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
            engine.db = db
            assert await engine._schedule_adaptive_review(
                user_id="42", concept_id="Fractions", passed=False,
                decided_at=datetime.utcnow().isoformat())
            row = (await db.execute(select(SpacedRepetitionSchedule))).scalars().one()
            assert row.last_grade == QUALITY_FOR_INCORRECT
            # A failed recall restarts the ladder: due again tomorrow.
            assert row.repetitions == 0 and row.interval == FIRST_INTERVAL_DAYS
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_a_guest_has_no_schedule_to_write_to_and_is_not_faked():
    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = None  # touching the database at all would raise
    assert await engine._schedule_adaptive_review(
        user_id="guest-7", concept_id="Fractions", passed=True,
        decided_at=datetime.utcnow().isoformat())
    assert await engine._schedule_adaptive_review(
        user_id="42", concept_id=None, passed=True, decided_at=None)


# ── A demonstration is not lost to a secondary update ────────────────────────

@pytest.mark.asyncio
async def test_a_failing_mastery_update_cannot_erase_the_demonstration():
    """The learner answered. Nothing downstream gets to undo that.

    `log_learning_event` commits the event and then writes the MasteryState
    projection that readiness and the next lesson actually read. That
    projection is still uncommitted when the optional DKT update runs, so a
    failure there used to fall through to a shared handler whose `rollback()`
    discarded it — the learner answered, the event was stored, and every
    surface still reported the skill as never attempted.

    The update it protects is a derived score the projection already covers. It
    is not worth a demonstration.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = MagicMock()
    engine.db.commit = AsyncMock()
    engine.db.rollback = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None          # no prior event
    engine.db.execute = AsyncMock(return_value=result)
    engine._log_classroom_evidence = AsyncMock(return_value=True)

    # Exactly what the end-to-end run does to hold the DKT back, and what any
    # real outage looks like from here.
    broken = MagicMock()
    broken.return_value.dkt.update_mastery = AsyncMock(side_effect=AttributeError("dkt is unavailable"))
    with patch("lyo_app.personalization.service.PersonalizationEngine", broken):
        recorded = await engine._record_adaptive_evidence(
            event_id="checkpoint-1", user_id="42", concept_id="long_division",
            correct=True, evidence_type=None, hints_used=0, hint_level=None,
            misconception=None, response_time_ms=5000,
        )

    assert recorded is True, "the answer is recorded even when the mastery update fails"
    engine._log_classroom_evidence.assert_awaited_once()
    # What the projection already wrote is kept, not thrown away.
    engine.db.commit.assert_awaited()
    engine.db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_real_failure_recording_the_evidence_is_still_reported():
    """The protection above is for the optional update, not for everything."""
    from unittest.mock import AsyncMock, MagicMock

    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = MagicMock()
    engine.db.rollback = AsyncMock()
    engine.db.execute = AsyncMock(side_effect=RuntimeError("the database is gone"))
    engine._log_classroom_evidence = AsyncMock(return_value=True)

    recorded = await engine._record_adaptive_evidence(
        event_id="checkpoint-2", user_id="42", concept_id="long_division",
        correct=True, evidence_type=None, hints_used=0, hint_level=None,
        misconception=None, response_time_ms=5000,
    )
    assert recorded is False, "a genuine failure keeps the evidence queued for retry"
    engine.db.rollback.assert_awaited()
