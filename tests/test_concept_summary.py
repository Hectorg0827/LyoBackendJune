"""Counting what a learner knows, strictly.

Home leads with XP, level and streak — real numbers that describe attendance,
not knowledge. The specification asks it to lead with concepts learned,
mastered and retained instead. Those are claims about a person, so a wrong
one is worse than no headline at all: a learner told they have "mastered" 12
concepts and then failing a test on them has been lied to by their own
progress screen.

So these tests are mostly about what does *not* count.
"""

import unittest

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.core.database import Base
from lyo_app.events.concept_summary import (
    ConceptSummary,
    concept_summary_for_user,
    summarize_concepts,
)
from lyo_app.events.models import EventType, LearningEvent

STRONG = 0.95
WEAK = 0.4


def _rows(*triples):
    return list(triples)


# ─── What counts as knowing something ────────────────────────────────────────

class WhatCountsTests(unittest.TestCase):
    def test_recognising_an_answer_is_not_knowing_it(self):
        """A multiple-choice hit is the weakest positive rung. Counting it as
        "learned" is how a progress screen starts lying."""
        summary = summarize_concepts(_rows(("fractions", "recognition", STRONG)))
        self.assertEqual(summary.exploring, 1)
        self.assertEqual(summary.learned, 0)
        self.assertEqual(summary.total, 1)

    def test_explaining_it_counts_as_learned(self):
        summary = summarize_concepts(_rows(("fractions", "explanation", STRONG)))
        self.assertEqual(summary.learned, 1)
        self.assertEqual(summary.exploring, 0)

    def test_being_taught_alone_is_not_learning(self):
        summary = summarize_concepts(_rows(("fractions", "exposure", 0.0)))
        self.assertEqual(summary.learned, 0)
        self.assertEqual(summary.exploring, 1)

    def test_mastery_needs_all_three_strong_forms(self):
        partial = summarize_concepts(
            _rows(("fractions", "application", STRONG), ("fractions", "transfer", STRONG))
        )
        self.assertEqual(partial.mastered, 0)

        complete = summarize_concepts(
            _rows(
                ("fractions", "application", STRONG),
                ("fractions", "transfer", STRONG),
                ("fractions", "retrieval", STRONG),
            )
        )
        self.assertEqual(complete.mastered, 1)

    def test_a_barely_scraped_demonstration_does_not_master_a_concept(self):
        summary = summarize_concepts(
            _rows(
                ("fractions", "application", WEAK),
                ("fractions", "transfer", WEAK),
                ("fractions", "retrieval", WEAK),
            )
        )
        self.assertEqual(summary.mastered, 0)

    def test_retention_is_what_separates_learning_from_remembering(self):
        without = summarize_concepts(_rows(("fractions", "application", STRONG)))
        self.assertEqual(without.retained, 0)

        with_recall = summarize_concepts(
            _rows(("fractions", "application", STRONG), ("fractions", "retrieval", STRONG))
        )
        self.assertEqual(with_recall.retained, 1)


# ─── The counts are a funnel, not a partition ────────────────────────────────

class FunnelTests(unittest.TestCase):
    def test_a_mastered_concept_is_also_learned_and_retained(self):
        """Otherwise the numbers move backwards at the moment a learner gets
        better at something."""
        summary = summarize_concepts(
            _rows(
                ("fractions", "application", STRONG),
                ("fractions", "transfer", STRONG),
                ("fractions", "retrieval", STRONG),
            )
        )
        self.assertEqual(summary.mastered, 1)
        self.assertEqual(summary.learned, 1)
        self.assertEqual(summary.retained, 1)
        self.assertEqual(summary.exploring, 0)
        self.assertEqual(summary.total, 1)

    def test_exploring_and_learned_do_not_double_count(self):
        summary = summarize_concepts(
            _rows(("a", "recognition", STRONG), ("b", "explanation", STRONG))
        )
        self.assertEqual(summary.exploring + summary.learned, summary.total)


# ─── What is refused ─────────────────────────────────────────────────────────

class RefusalTests(unittest.TestCase):
    def test_evidence_naming_no_concept_is_skipped(self):
        self.assertEqual(summarize_concepts(_rows((None, "explanation", STRONG))).total, 0)

    def test_an_unrecognised_rung_advances_nothing(self):
        """The same rule the projection follows, so the two cannot disagree
        about what counts as evidence."""
        self.assertEqual(summarize_concepts(_rows(("fractions", "vibes", STRONG))).total, 0)

    def test_a_malformed_confidence_is_treated_as_none_not_full(self):
        # Every value here raises on float(), so each one exercises the
        # malformed path. Mixing in None would coerce quietly to 0.0 and the
        # test would pass without the guard ever being reached.
        summary = summarize_concepts(
            _rows(
                ("fractions", "application", "not a number"),
                ("fractions", "transfer", "later"),
                ("fractions", "retrieval", "?"),
            )
        )
        self.assertEqual(summary.mastered, 0)
        # Still "learned": the rungs were reached. The ladder is explicit that
        # low confidence bars the concept from MASTERED without erasing the
        # demonstration underneath it.
        self.assertEqual(summary.learned, 1)

    def test_no_evidence_is_all_zeroes(self):
        self.assertEqual(summarize_concepts([]), ConceptSummary())
        self.assertEqual(summarize_concepts(None), ConceptSummary())

    def test_the_best_attempt_at_each_rung_is_what_counts(self):
        """A learner who fumbled a transfer and later nailed it has
        demonstrated the transfer."""
        summary = summarize_concepts(
            _rows(
                ("fractions", "application", STRONG),
                ("fractions", "transfer", WEAK),
                ("fractions", "transfer", STRONG),
                ("fractions", "retrieval", STRONG),
            )
        )
        self.assertEqual(summary.mastered, 1)


# ─── Against a real database ─────────────────────────────────────────────────

@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LearningEvent.__table__])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


def _event(user_id, concept_id, evidence_type, confidence):
    return LearningEvent(
        user_id=user_id,
        event_type=EventType.QUIZ_ANSWER,
        concept_id=concept_id,
        evidence_type=evidence_type,
        evidence_confidence=confidence,
        measurable_outcome=1.0,
        source_surface="chat",
    )


async def test_a_learners_own_evidence_is_what_is_counted(db):
    db.add_all([
        _event(1, "fractions", "application", STRONG),
        _event(1, "fractions", "transfer", STRONG),
        _event(1, "fractions", "retrieval", STRONG),
        _event(1, "algebra", "recognition", STRONG),
        # Another learner's work must not appear in this one's totals.
        _event(2, "geometry", "explanation", STRONG),
    ])
    await db.flush()

    summary = await concept_summary_for_user(db, 1)

    assert summary.total == 2
    assert summary.mastered == 1
    assert summary.learned == 1
    assert summary.exploring == 1


async def test_a_learner_with_no_history_gets_honest_zeroes(db):
    summary = await concept_summary_for_user(db, 99)
    assert summary == ConceptSummary()


async def test_a_guest_id_is_not_an_error(db):
    assert await concept_summary_for_user(db, "guest-abc") == ConceptSummary()
    assert await concept_summary_for_user(db, None) == ConceptSummary()


async def test_a_broken_query_costs_zeroes_not_the_front_page(db):
    """This feeds Home. A learner should not lose their front page because a
    summary query failed.

    The session is made to fail outright. Closing it would not do: SQLAlchemy
    reopens a closed session on next use, so that version of this test passed
    whether or not the guard existed.
    """
    from unittest.mock import AsyncMock

    db.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
    assert await concept_summary_for_user(db, 1) == ConceptSummary()


async def test_only_evidence_bearing_rows_are_read(db):
    """Events predating the evidence columns, and log-only events, say
    nothing about what a learner knows."""
    db.add_all([
        _event(1, None, "explanation", STRONG),
        _event(1, "fractions", None, STRONG),
        _event(1, "fractions", "explanation", STRONG),
    ])
    await db.flush()

    summary = await concept_summary_for_user(db, 1)
    assert summary.total == 1
    assert summary.learned == 1


async def test_the_read_is_bounded(db):
    """Still bounded — but by distinct concept-and-rung pairs, not by events,
    so a busy learner cannot push their own earlier work out of the count."""
    db.add_all([_event(1, f"concept_{i}", "explanation", STRONG) for i in range(20)])
    await db.flush()

    summary = await concept_summary_for_user(db, 1, limit=5)
    assert summary.total == 5


async def test_early_mastery_is_not_pushed_out_by_later_work(db):
    """Home's numbers must never move backwards while a learner keeps
    working. The first version of this read the most recent N events, so a
    concept mastered early dropped out as later answers on other topics
    filled the window."""
    db.add_all([
        _event(1, "fractions", "application", STRONG),
        _event(1, "fractions", "transfer", STRONG),
        _event(1, "fractions", "retrieval", STRONG),
    ])
    await db.flush()
    before = await concept_summary_for_user(db, 1)
    assert before.mastered == 1

    # A great deal of later work on entirely different concepts.
    db.add_all([
        _event(1, f"other_{i}", "recognition", STRONG) for i in range(200)
    ])
    await db.flush()

    after = await concept_summary_for_user(db, 1)
    assert after.mastered == 1, "the early mastery vanished"
    assert after.learned >= before.learned
    assert after.retained >= before.retained
