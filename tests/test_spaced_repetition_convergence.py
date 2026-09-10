"""One spaced-repetition schedule, one SM-2.

There were two systems doing this job. `personalization.SpacedRepetitionSchedule`
is written every time a learner answers a check and read by Chat's due-review
nudge. `ai_classroom.ReviewSchedule` had its own SM-2 inside `playback_routes`
— and its only two writers, `spaced_repetition_service` and
`interaction_service`, have no callers anywhere.

So the classroom's `/review/today` served every learner an empty queue while
that same learner had items genuinely due in the other table, and
`/review/submit` answered 404 for anyone who tried. One surface said "nothing
to review"; the other offered five things. Same shape as the mastery split:
a real, learner-visible failure hiding behind two tables nobody reconciled.
"""

import unittest
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.core.database import Base
from lyo_app.personalization.models import LearnerMastery, SpacedRepetitionSchedule
from lyo_app.personalization.service import PersonalizationEngine
from lyo_app.personalization.spaced_repetition import (
    MINIMUM_EASINESS,
    QUALITY_FOR_CORRECT,
    QUALITY_FOR_INCORRECT,
    Schedule,
    clamp_quality,
    next_schedule,
)

FRESH = Schedule(easiness_factor=2.5, interval_days=1, repetitions=0)


# ─── The algorithm ───────────────────────────────────────────────────────────

class SM2Tests(unittest.TestCase):
    def test_the_interval_ladder_is_one_then_six_then_earned(self):
        first = next_schedule(FRESH, 5)
        self.assertEqual(first.interval_days, 1)
        second = next_schedule(first, 5)
        self.assertEqual(second.interval_days, 6)
        third = next_schedule(second, 5)
        self.assertGreater(third.interval_days, 6)

    def test_a_failed_recall_restarts_the_ladder(self):
        practised = next_schedule(next_schedule(next_schedule(FRESH, 5), 5), 5)
        self.assertGreater(practised.repetitions, 2)

        forgotten = next_schedule(practised, 1)
        self.assertEqual(forgotten.repetitions, 0)
        self.assertEqual(forgotten.interval_days, 1)

    def test_forgetting_once_does_not_erase_what_the_item_earned(self):
        """SM-2 keeps the easiness factor across a failure, minus a penalty.
        Forgetting says the spacing was too aggressive, not that the learner
        has to re-earn everything they knew about it."""
        practised = next_schedule(next_schedule(FRESH, 5), 5)
        forgotten = next_schedule(practised, 1)
        self.assertLess(forgotten.easiness_factor, practised.easiness_factor)
        self.assertGreater(forgotten.easiness_factor, MINIMUM_EASINESS)

    def test_easiness_never_falls_below_the_floor(self):
        schedule = FRESH
        for _ in range(20):
            schedule = next_schedule(schedule, 0)
        # The literal, not the imported constant: asserting against
        # MINIMUM_EASINESS would move with the bug and pass at any floor,
        # including none.
        self.assertGreaterEqual(schedule.easiness_factor, 1.3)
        self.assertEqual(MINIMUM_EASINESS, 1.3)

    def test_a_quality_of_three_still_counts_as_recall(self):
        """SM-2 draws the line at 3: "correct, with serious difficulty"."""
        self.assertEqual(next_schedule(FRESH, 3).repetitions, 1)
        self.assertEqual(next_schedule(FRESH, 2).repetitions, 0)

    def test_a_bad_grade_from_a_client_does_not_cost_the_review(self):
        self.assertEqual(clamp_quality(99), 5)
        self.assertEqual(clamp_quality(-4), 0)
        self.assertEqual(clamp_quality("three"), 0)
        self.assertEqual(clamp_quality(None), 0)
        self.assertIsInstance(next_schedule(FRESH, "nonsense"), Schedule)

    def test_a_corrupt_easiness_factor_is_recovered_from(self):
        self.assertGreaterEqual(
            next_schedule(Schedule(None, 1, 0), 5).easiness_factor, MINIMUM_EASINESS
        )

    def test_an_interval_never_collapses_to_zero(self):
        """An interval of 0 would make the item due the instant it is
        answered: a loop, not a schedule.

        Swept rather than spot-checked. No single input reaches the outer
        clamp — the easiness floor of 1.3 already keeps the product above 1 —
        so a one-case test here proves nothing about the guard.
        """
        for repetitions in range(0, 8):
            # A negative stored interval is the case the clamps actually
            # exist for: `or 1` already rescues 0, and the easiness floor
            # keeps the product above 1 for anything positive.
            for interval in (-5, 0, 1, 6, 30):
                for quality in range(0, 6):
                    result = next_schedule(
                        Schedule(1.3, interval, repetitions), quality
                    )
                    self.assertGreaterEqual(result.interval_days, 1)


class BooleanPathIsPreservedTests(unittest.TestCase):
    """Folding two schedulers together is not licence to re-tune every
    existing learner's intervals."""

    def test_a_correct_check_behaves_exactly_as_before(self):
        # Previously: interval ladder 1/6/interval*ef, easiness +0.1.
        after = next_schedule(FRESH, QUALITY_FOR_CORRECT)
        self.assertAlmostEqual(after.easiness_factor, 2.6, places=6)
        self.assertEqual(after.interval_days, 1)
        self.assertEqual(after.repetitions, 1)

    def test_a_wrong_check_still_resets_interval_and_repetitions(self):
        practised = next_schedule(next_schedule(FRESH, QUALITY_FOR_CORRECT), QUALITY_FOR_CORRECT)
        after = next_schedule(practised, QUALITY_FOR_INCORRECT)
        self.assertEqual(after.interval_days, 1)
        self.assertEqual(after.repetitions, 0)


# ─── Against a real database ─────────────────────────────────────────────────

@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SpacedRepetitionSchedule.__table__, LearnerMastery.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_a_review_creates_a_schedule_when_there_is_none(db):
    engine = PersonalizationEngine()

    schedule = await engine.record_review(db, 1, "fractions", "block-1", 5)

    assert schedule.skill_id == "fractions"
    assert schedule.repetitions == 1
    assert schedule.next_review > datetime.utcnow()


async def test_a_second_review_advances_the_same_row(db):
    engine = PersonalizationEngine()
    await engine.record_review(db, 1, "fractions", "block-1", 5)
    await engine.record_review(db, 1, "fractions", "block-1", 5)

    rows = (
        await db.execute(
            select(SpacedRepetitionSchedule).where(
                SpacedRepetitionSchedule.item_id == "block-1"
            )
        )
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].repetitions == 2
    assert rows[0].interval == 6


async def test_the_pass_fail_path_writes_the_same_table(db):
    """Chat's check and the classroom's review must not end up in different
    schedules — that is the whole bug."""
    engine = PersonalizationEngine()

    await engine._update_repetition_schedule(db, 1, "fractions", "block-1", True)
    await engine.record_review(db, 1, "fractions", "block-1", 5)

    rows = (
        await db.execute(select(SpacedRepetitionSchedule))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].repetitions == 2


async def test_the_grade_the_learner_gave_is_recorded(db):
    engine = PersonalizationEngine()
    schedule = await engine.record_review(db, 1, "fractions", "block-1", 4)
    assert schedule.last_grade == 4


async def test_the_classroom_queue_reads_what_chat_scheduled(db):
    """The convergence, end to end: something scheduled by a chat check turns
    up in the review queue the classroom serves."""
    engine = PersonalizationEngine()
    await engine._update_repetition_schedule(db, 1, "fractions", "block-1", True)

    # Make it due.
    row = (await db.execute(select(SpacedRepetitionSchedule))).scalar_one()
    row.next_review = datetime.utcnow() - timedelta(days=2)
    await db.commit()

    due = await engine.get_due_reviews(db, 1)

    assert len(due) == 1
    assert due[0]["skill_id"] == "fractions"
    # The fields the classroom's ReviewItem renders.
    assert due[0]["interval_days"] >= 1
    assert due[0]["repetitions"] == 1
    assert due[0]["last_review"] is not None


# ─── The dead scheduler is no longer serving learners ────────────────────────

async def test_the_review_endpoint_serves_what_chat_scheduled(db):
    """The endpoint itself, not its source text. It previously read a table
    nothing wrote, so it returned an empty queue no matter what the learner
    had due — which source assertions cannot detect."""
    from types import SimpleNamespace

    from lyo_app.ai_classroom.playback_routes import get_review_queue

    engine = PersonalizationEngine()
    await engine._update_repetition_schedule(db, 1, "fractions", "block-1", True)
    row = (await db.execute(select(SpacedRepetitionSchedule))).scalar_one()
    row.next_review = datetime.utcnow() - timedelta(days=3)
    await db.commit()

    response = await get_review_queue(
        current_user=SimpleNamespace(id=1), limit=20, db=db
    )

    assert response.total_items == 1
    item = response.items[0]
    assert item.concept_name == "fractions"
    assert item.node_id == "block-1"
    assert item.priority > 1.0  # overdue raises it


async def test_submitting_a_review_reschedules_the_live_row(db):
    from types import SimpleNamespace

    from lyo_app.ai_classroom.playback_routes import submit_review

    engine = PersonalizationEngine()
    await engine._update_repetition_schedule(db, 1, "fractions", "block-1", True)

    response = await submit_review(
        request=SimpleNamespace(node_id="block-1", quality=5),
        current_user=SimpleNamespace(id=1),
        db=db,
    )

    assert response.new_interval_days == 6
    assert response.streak == 2
    assert response.next_review_date > datetime.utcnow()


class DeadSchedulerIsUnwiredTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path

        self.routes = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "ai_classroom" / "playback_routes.py"
        ).read_text()
        start = self.routes.index('@router.get("/review/today")')
        end = self.routes.index("# MASTERY ROUTES")
        self.review = self.routes[start:end]

    def test_the_queue_no_longer_reads_the_unfed_table(self):
        self.assertNotIn("select(ReviewSchedule)", self.review)

    def test_the_queue_reads_the_live_schedule(self):
        self.assertIn("get_due_reviews(", self.review)

    def test_submitting_a_review_writes_the_live_schedule(self):
        self.assertIn("record_review(", self.review)

    def test_there_is_no_second_sm2_in_the_route(self):
        """The route carried its own copy of the algorithm."""
        self.assertNotIn("0.08 + (5 - q) * 0.02", self.review)

    def test_the_hardcoded_concept_placeholder_is_gone(self):
        """The route returned a fixed string as every concept's name, with a
        comment saying a real lookup would happen in production."""
        self.assertNotIn("concept_name=sched.concept_id or", self.review)
        self.assertIn("skill_id", self.review)


if __name__ == "__main__":
    unittest.main()
