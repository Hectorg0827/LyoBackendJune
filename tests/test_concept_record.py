"""Reading a learner their own record.

Every line this view produces is a claim about a person, made back to that
person. The failure mode is not a crash — it is a screen that tells someone
they can *apply* something they have only ever *recognised*, or that they did
it unaided when they were walked through it. Those are the tests here.

`test_concept_summary.py` covers the counting rules; this covers the detail
the counts throw away.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.core.database import Base
from lyo_app.events.concept_record import (
    RECORD_CAP,
    build_records,
    learner_record,
    next_rung_after,
)
from lyo_app.events.models import EventType, LearningEvent

STRONG = 0.95
WEAK = 0.4
DAY = datetime(2026, 9, 21, 12, 0, 0)


def _rung(concept, kind, confidence, hints=0, seen=DAY):
    return (concept, kind, confidence, hints, seen)


def _by_id(records):
    return {record.concept_id: record for record in records}


# ─── What the record may and may not claim ───────────────────────────────────

def test_recognising_something_is_never_reported_as_applying_it():
    """The whole reason this view exists. A learner who has only picked the
    right option out of four has shown recognition, and no number of
    repetitions turns that into application."""
    record = _by_id(build_records([
        _rung("fractions", "recognition", STRONG),
        _rung("fractions", "recognition", STRONG),
        _rung("fractions", "recognition", STRONG),
    ]))["fractions"]

    assert record.best_rung == "recognition"
    assert record.state == "RECOGNIZED"
    assert [rung.kind for rung in record.rungs] == ["recognition"]


def test_a_rung_never_demonstrated_does_not_appear():
    record = _by_id(build_records([_rung("fractions", "application", STRONG)]))["fractions"]
    kinds = {rung.kind for rung in record.rungs}
    assert "transfer" not in kinds
    assert "retention" not in kinds


def test_being_helped_there_is_not_the_same_as_getting_there_alone():
    helped = _by_id(build_records([
        _rung("fractions", "application", STRONG, hints=2),
    ]))["fractions"]
    assert helped.rungs[0].unaided is False

    alone = _by_id(build_records([
        _rung("fractions", "application", STRONG, hints=0),
    ]))["fractions"]
    assert alone.rungs[0].unaided is True


def test_one_unaided_demonstration_is_enough_to_claim_it():
    """Having once done it without help is the claim `unaided` makes, so a
    later hinted attempt must not retract it."""
    record = _by_id(build_records([
        _rung("fractions", "application", WEAK, hints=0),
        _rung("fractions", "application", STRONG, hints=3),
    ]))["fractions"]

    # The strongest demonstration is reported...
    assert record.rungs[0].confidence == pytest.approx(STRONG)
    # ...and so is the fact that they have managed it alone.
    assert record.rungs[0].unaided is True


def test_rungs_are_ordered_weakest_first():
    record = _by_id(build_records([
        _rung("fractions", "transfer", STRONG),
        _rung("fractions", "recognition", STRONG),
        _rung("fractions", "application", STRONG),
    ]))["fractions"]
    assert [rung.kind for rung in record.rungs] == ["recognition", "application", "transfer"]


def test_the_state_agrees_with_the_mastery_projection():
    """`derive_mastery_state` is imported rather than reimplemented so this
    view and the projection cannot disagree about the same evidence."""
    mastered = _by_id(build_records([
        _rung("fractions", "application", STRONG),
        _rung("fractions", "transfer", STRONG),
        _rung("fractions", "retrieval", STRONG),
    ]))["fractions"]
    assert mastered.state == "MASTERED"

    # The wire says "retrieval"; the ladder says "retention". Adapted, not renamed.
    assert any(rung.kind == "retention" for rung in mastered.rungs)


def test_unrecognised_evidence_advances_nothing():
    """A new server-side evidence type must not be silently scored."""
    records = build_records([_rung("fractions", "vibes", STRONG)])
    assert records == []


def test_a_row_naming_no_concept_is_skipped_not_guessed_at():
    assert build_records([_rung(None, "application", STRONG)]) == []


# ─── What to do next ─────────────────────────────────────────────────────────

def test_the_next_step_is_the_next_rung_up():
    assert next_rung_after("recognition") == "explanation"
    assert next_rung_after("application") == "transfer"


def test_there_is_nothing_after_the_top_of_the_ladder():
    assert next_rung_after("retention") is None


def test_a_learner_who_has_shown_nothing_is_pointed_at_recognition():
    assert next_rung_after(None) == "recognition"


# ─── The misconception ───────────────────────────────────────────────────────

def test_the_named_error_survives_a_later_correct_answer():
    """Remediation targets the misconception, so getting the next one right
    does not mean the misunderstanding is gone."""
    record = _by_id(build_records(
        [_rung("fractions", "application", STRONG)],
        [("fractions", "inverts the denominator", DAY)],
    ))["fractions"]
    assert record.misconception == "inverts the denominator"


def test_the_most_recent_error_is_the_one_shown():
    record = _by_id(build_records(
        [_rung("fractions", "application", STRONG)],
        # Rows arrive most recent first.
        [("fractions", "newest", DAY), ("fractions", "older", DAY - timedelta(days=2))],
    ))["fractions"]
    assert record.misconception == "newest"


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


def _event(user_id, concept_id, evidence_type, confidence, hints=0, when=DAY, misconception=None):
    return LearningEvent(
        user_id=user_id,
        event_type=EventType.CLASSROOM_DEMONSTRATION,
        concept_id=concept_id,
        evidence_type=evidence_type,
        evidence_confidence=confidence,
        hints_used=hints,
        misconception=misconception,
        measurable_outcome=1.0,
        source_surface="classroom",
        timestamp=when,
    )


async def test_a_learner_reads_their_own_record_and_nobody_elses(db):
    db.add_all([
        _event(1, "fractions", "application", STRONG),
        _event(2, "fractions", "transfer", STRONG),
    ])
    await db.flush()

    record = await learner_record(db, 1)
    concepts = _by_id(record.concepts)

    assert set(concepts) == {"fractions"}
    assert [rung.kind for rung in concepts["fractions"].rungs] == ["application"]


async def test_a_learner_with_no_history_has_an_empty_record_not_an_error(db):
    record = await learner_record(db, 99)
    assert record.concepts == []
    assert record.unavailable is False


async def test_a_failed_read_says_so_rather_than_claiming_they_did_nothing():
    """An empty record means "you have not shown anything yet", which is a
    claim about the learner. A query failure is not evidence for it."""
    class BrokenSession:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("the database is having a day")

    record = await learner_record(BrokenSession(), 1)

    assert record.unavailable is True
    assert record.concepts == []


async def test_the_most_recently_worked_on_concept_comes_first(db):
    db.add_all([
        _event(1, "old-topic", "recognition", STRONG, when=DAY - timedelta(days=9)),
        _event(1, "todays-topic", "recognition", STRONG, when=DAY),
        _event(1, "middle-topic", "recognition", STRONG, when=DAY - timedelta(days=3)),
    ])
    await db.flush()

    record = await learner_record(db, 1)

    assert [c.concept_id for c in record.concepts] == [
        "todays-topic", "middle-topic", "old-topic",
    ]


async def test_hints_and_misconceptions_survive_the_round_trip(db):
    db.add_all([
        _event(1, "fractions", "application", STRONG, hints=2,
               misconception="inverts the denominator"),
    ])
    await db.flush()

    record = _by_id((await learner_record(db, 1)).concepts)["fractions"]

    assert record.rungs[0].unaided is False
    assert record.misconception == "inverts the denominator"


async def test_only_evidence_bearing_rows_are_read(db):
    db.add_all([
        LearningEvent(
            user_id=1, event_type=EventType.REFLECTION,
            concept_id="fractions", evidence_type=None, evidence_confidence=None,
        ),
        LearningEvent(
            user_id=1, event_type=EventType.QUIZ_ANSWER,
            concept_id=None, evidence_type="application", evidence_confidence=STRONG,
        ),
    ])
    await db.flush()

    record = await learner_record(db, 1)
    assert record.concepts == []


async def test_the_read_is_bounded(db):
    db.add_all([
        _event(1, f"concept-{index}", "recognition", STRONG, when=DAY - timedelta(minutes=index))
        for index in range(RECORD_CAP + 25)
    ])
    await db.flush()

    record = await learner_record(db, 1)
    assert len(record.concepts) == RECORD_CAP


async def test_the_cap_never_cuts_through_a_concept(db):
    """A record showing some of a concept's rungs and not others would
    understate what the learner did — worse than omitting the concept."""
    db.add_all([
        _event(1, "fractions", "application", STRONG, when=DAY),
        _event(1, "fractions", "transfer", STRONG, when=DAY),
        _event(1, "fractions", "retrieval", STRONG, when=DAY),
    ])
    await db.flush()

    record = await learner_record(db, 1, limit=1)
    concepts = _by_id(record.concepts)

    assert set(concepts) == {"fractions"}
    assert len(concepts["fractions"].rungs) == 3
    assert concepts["fractions"].state == "MASTERED"
