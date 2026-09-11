"""The mastery projection, run against a real database.

WHY THIS FILE EXISTS SEPARATELY

`test_evidence_ladder.py` covers the ladder as pure logic and pins the parts
that must agree with the client. It passed for the entire life of a bug that
made the projection unable to write a single row: chat identifies concepts by
slug, `MasteryState.concept_id` is foreign-keyed to `concepts.id`, and the
projection swallows its own failures by design — so every chat check would
have been silently dropped, forever, with a green test suite.

Logic tests cannot catch that. Only a database can. So this file stands up
the real ORM tables and asserts that evidence actually lands in a row.

Foreign keys are enforced (SQLite leaves them off by default), because the
foreign key *is* the thing under test in `test_a_slug_is_rejected_by_the_
concept_foreign_key`.

The `LearningEvent` is constructed but never persisted. The projection only
reads attributes off it, and persisting one would drag in `users` and most of
the model graph for no added coverage — but building the real class still
proves the evidence columns exist on it.
"""

import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.ai_classroom.models import Concept, MasteryState
from lyo_app.core.database import Base
from lyo_app.events.models import LearningEvent
from lyo_app.events.mastery_projection import (
    ProjectionOutcome,
    project_event_to_mastery_state,
)

LEARNER = "learner-1"
SLUG = "quadratic_functions"


@pytest.fixture
async def db():
    """A session over just the tables the projection touches."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [Concept.__table__, MasteryState.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


def _event(**overrides):
    """A LearningEvent shaped like one chat's check emits."""
    fields = {
        "user_id": LEARNER,
        "concept_id": SLUG,
        "evidence_type": "application",
        "evidence_confidence": 0.9,
        "measurable_outcome": 1.0,
        "hints_used": 0,
        "misconception": None,
        "source_surface": "chat",
    }
    fields.update(overrides)
    return LearningEvent(**fields)


async def _row(db, **where):
    return (await db.execute(select(MasteryState).filter_by(**where))).scalar_one_or_none()


# ─── The projection actually writes ──────────────────────────────────────────

async def test_a_chat_check_lands_a_mastery_row(db):
    outcome = await project_event_to_mastery_state(db, _event())
    assert outcome is ProjectionOutcome.PROJECTED

    row = await _row(db, user_id=LEARNER, objective_id=SLUG)
    assert row is not None, "the classroom's table stayed empty after a chat check"
    # The slug went to the column that can hold it, not the foreign-keyed one.
    assert row.concept_id is None
    assert row.attempts == 1
    assert row.correct_count == 1
    assert row.mastery_score > 0.0
    assert row.trend == "improving"


async def test_a_graph_concept_lands_on_concept_id(db):
    concept = Concept(id=str(uuid.uuid4()), name="Quadratic Functions", subject="math")
    db.add(concept)
    await db.flush()

    outcome = await project_event_to_mastery_state(db, _event(concept_id=concept.id))
    assert outcome is ProjectionOutcome.PROJECTED

    row = await _row(db, user_id=LEARNER, concept_id=concept.id)
    assert row is not None
    assert row.objective_id is None


async def test_a_slug_is_rejected_by_the_concept_foreign_key(db):
    """The bug this routing exists to avoid, demonstrated.

    If the projection wrote slugs to `concept_id`, this is the error it would
    hit on every chat check — and, being defensive, would swallow.
    """
    db.add(MasteryState(user_id=LEARNER, concept_id=SLUG, mastery_score=0.0, confidence=0.5))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


# ─── Evidence folds rather than piling up rows ───────────────────────────────

async def test_a_second_check_folds_into_the_same_row(db):
    await project_event_to_mastery_state(db, _event())
    first = await _row(db, user_id=LEARNER, objective_id=SLUG)
    score_after_one = first.mastery_score

    await project_event_to_mastery_state(db, _event())
    rows = (
        await db.execute(
            select(MasteryState).where(MasteryState.objective_id == SLUG)
        )
    ).scalars().all()

    assert len(rows) == 1, "a second check created a second row instead of folding"
    assert rows[0].attempts == 2
    assert rows[0].mastery_score > score_after_one


async def test_being_taught_records_the_encounter_without_scoring_it(db):
    """Instruction is not a failed attempt.

    An event with no `measurable_outcome` is delivery, not demonstration. It
    must leave a row saying the learner has now met the concept, and must not
    touch attempts, counts, score or trend — being taught something can never
    make a learner look worse at it.
    """
    outcome = await project_event_to_mastery_state(
        db,
        _event(evidence_type="exposure", evidence_confidence=0.0, measurable_outcome=None),
    )
    assert outcome is ProjectionOutcome.PROJECTED

    row = await _row(db, user_id=LEARNER, objective_id=SLUG)
    assert row.last_seen is not None
    assert row.attempts == 0
    assert row.incorrect_count == 0
    assert row.mastery_score == 0.0
    assert row.trend == "stable"


async def test_a_wrong_answer_lowers_the_score_without_erasing_history(db):
    await project_event_to_mastery_state(db, _event())
    after_correct = (await _row(db, user_id=LEARNER, objective_id=SLUG)).mastery_score

    await project_event_to_mastery_state(
        db,
        _event(
            evidence_type="exposure",
            evidence_confidence=0.0,
            measurable_outcome=0.0,
            misconception="sign error when completing the square",
        ),
    )
    row = await _row(db, user_id=LEARNER, objective_id=SLUG)

    assert 0.0 < row.mastery_score < after_correct
    assert row.incorrect_count == 1
    assert row.correct_count == 1
    assert "sign error when completing the square" in (row.misconception_tags or [])


# ─── The database refuses the duplicate the retry depends on ─────────────────

async def test_the_database_refuses_a_duplicate_slug_row(db):
    """`uq_mastery_user_objective` has to be real, not just declared.

    The projection's recovery from a concurrent insert is an IntegrityError
    handler. If the index is missing from the created schema, no error is
    raised, two rows land, and the next lookup raises MultipleResultsFound —
    after which every projection for that learner and concept fails.
    """
    await project_event_to_mastery_state(db, _event())
    await db.flush()

    db.add(MasteryState(user_id=LEARNER, objective_id=SLUG, mastery_score=0.0, confidence=0.5))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_two_learners_may_share_a_concept(db):
    await project_event_to_mastery_state(db, _event())
    await project_event_to_mastery_state(db, _event(user_id="learner-2"))
    await db.flush()

    rows = (
        await db.execute(select(MasteryState).where(MasteryState.objective_id == SLUG))
    ).scalars().all()
    assert len(rows) == 2


# ─── Failure never reaches the learner's turn ────────────────────────────────

async def test_a_failed_projection_leaves_the_caller_s_session_usable(db, monkeypatch):
    """The savepoint has to contain the damage.

    Without it a failed flush poisons the AsyncSession, and the processor's
    own commit — the one recording how the event was handled — goes down with
    it. A projection failure would then cost the learner their turn.
    """
    import lyo_app.events.mastery_projection as projection

    def _explode(*_args, **_kwargs):
        raise RuntimeError("projection blew up")

    monkeypatch.setattr(projection, "_fold_evidence", _explode)

    outcome = await project_event_to_mastery_state(db, _event())
    assert outcome is ProjectionOutcome.FAILED

    # The session still works, and the half-built row did not survive.
    assert await _row(db, user_id=LEARNER, objective_id=SLUG) is None
    db.add(MasteryState(user_id="learner-3", objective_id="other", mastery_score=0.0, confidence=0.5))
    await db.flush()
    assert await _row(db, user_id="learner-3", objective_id="other") is not None


async def test_an_event_with_nothing_to_prove_writes_nothing(db):
    outcome = await project_event_to_mastery_state(db, _event(evidence_type=None))
    assert outcome is ProjectionOutcome.NOTHING_TO_PROJECT
    assert await _row(db, user_id=LEARNER, objective_id=SLUG) is None
