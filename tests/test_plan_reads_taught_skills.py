"""A study plan can see what the Classroom taught, now that it teaches by id.

The Classroom used to file evidence under the same slug Chat uses, so a plan
topic and a taught skill met at a shared string. It now files against
persistent `Concept` rows, and the units it teaches are finer than a plan's
topics — so the string is gone and nothing joined the two. A learner could
finish a whole lesson on long division and have their plan still report the
topic as never attempted.

The join is the scope: every skill taught under a free topic shares a scope
derived from that topic's own name. These tests pin that a plan reaches its
taught skills through it, that it still reads the slug evidence Chat writes,
that the two fold together rather than replacing each other, and that the
scope does not hand a learner credit from a different subject.
"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.ai_classroom.models import Concept, MasteryState
from lyo_app.ai_classroom.skill_identity import topic_scope
from lyo_app.study_plans.topic_standing import (
    _merge_mastery,
    load_taught_skill_mastery,
    standings_for_profile,
)

LEARNER = 7


async def _database():
    database = create_async_engine("sqlite+aiosqlite://")
    async with database.begin() as connection:
        await connection.run_sync(Concept.__table__.create)
        await connection.run_sync(MasteryState.__table__.create)
    return database


def _skill(scope: str, name: str, key: str) -> Concept:
    return Concept(id=f"id-{key}", name=name, display_name=name,
                   subject=scope, identity_key=key)


def _state(concept_id: str | None, score: float, attempts: int,
           objective_id: str | None = None) -> MasteryState:
    return MasteryState(
        id=f"m-{concept_id or objective_id}", user_id=str(LEARNER),
        concept_id=concept_id, objective_id=objective_id,
        mastery_score=score, attempts=attempts, last_seen=datetime.utcnow(),
    )


async def _taught(db, topics):
    return await load_taught_skill_mastery(db, LEARNER, topics)


# ─── The join itself ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_plan_topic_reaches_the_units_the_classroom_taught_under_it():
    database = await _database()
    try:
        scope = topic_scope("Long division")
        async with AsyncSession(database) as db:
            db.add_all([
                _skill(scope, "Divide by a two-digit number", "a"),
                _skill(scope, "Interpret a remainder", "b"),
                _state("id-a", 0.4, 2),
                _state("id-b", 0.6, 2),
            ])
            await db.commit()
            found = await _taught(db, [("Long division", "long_division", 1.0)])
        # Neither unit is called "Long division" and neither carries the slug.
        assert found == {"long_division": (0.5, 4)}
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_a_unit_the_lesson_has_not_reached_is_silence_not_a_zero():
    """An untaught unit must not drag the topic's score down.

    Leaving it out is the same judgement `build_standings` already makes for
    a topic with no attempts: nothing shown is not nothing achieved.
    """
    database = await _database()
    try:
        scope = topic_scope("Long division")
        async with AsyncSession(database) as db:
            db.add_all([
                _skill(scope, "Divide by a two-digit number", "a"),
                _skill(scope, "Interpret a remainder", "b"),
                _state("id-a", 0.8, 3),
                # Taught, never answered: a row exists with no attempt behind it.
                _state("id-b", 0.0, 0),
            ])
            await db.commit()
            found = await _taught(db, [("Long division", "long_division", 1.0)])
        assert found == {"long_division": (0.8, 3)}
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_one_heavily_drilled_unit_does_not_speak_for_the_whole_topic():
    database = await _database()
    try:
        scope = topic_scope("Long division")
        async with AsyncSession(database) as db:
            db.add_all([
                _skill(scope, "Divide by a two-digit number", "a"),
                _skill(scope, "Interpret a remainder", "b"),
                _state("id-a", 0.9, 40),
                _state("id-b", 0.1, 1),
            ])
            await db.commit()
            found = await _taught(db, [("Long division", "long_division", 1.0)])
        score, attempts = found["long_division"]
        # Attempt-weighted this would read 0.88 and call a learner who cannot
        # interpret a remainder nearly done with long division.
        assert score == pytest.approx(0.5)
        assert attempts == 41
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_nothing_taught_yet_leaves_the_topic_untouched():
    database = await _database()
    try:
        async with AsyncSession(database) as db:
            found = await _taught(db, [("Long division", "long_division", 1.0)])
        assert found == {}
    finally:
        await database.dispose()


# ─── What the scope must refuse ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_same_title_in_another_subject_confers_no_credit():
    """The property the identity model exists for, read from this side.

    "Division" in a music course is not "Division" in an arithmetic one, and
    a plan asking about one must not be handed the other's evidence.
    """
    database = await _database()
    try:
        async with AsyncSession(database) as db:
            db.add_all([
                # A skill taught inside an authored lesson, scoped to it.
                _skill("lesson:deadbeef", "Divide by a two-digit number", "a"),
                _state("id-a", 0.9, 5),
            ])
            await db.commit()
            found = await _taught(db, [("Long division", "long_division", 1.0)])
        assert found == {}
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_a_legacy_taxonomy_row_in_the_scope_is_not_evidence():
    """Only rows the Classroom gave an identity to count.

    A taxonomy concept predating skill identities carries no identity key. It
    can share a subject string by coincidence; it is not something a learner
    was taught here.
    """
    database = await _database()
    try:
        scope = topic_scope("Long division")
        async with AsyncSession(database) as db:
            db.add_all([
                Concept(id="id-legacy", name="Long division", subject=scope,
                        identity_key=None),
                _state("id-legacy", 0.9, 9),
            ])
            await db.commit()
            found = await _taught(db, [("Long division", "long_division", 1.0)])
        assert found == {}
    finally:
        await database.dispose()


# ─── Folding the two halves ─────────────────────────────────────────────────

def test_chat_and_classroom_evidence_add_up_rather_than_replacing():
    merged = _merge_mastery(
        {"long_division": (0.2, 1)},   # a chat answer, under the slug
        {"long_division": (0.8, 3)},   # a taught unit, under a skill id
    )
    score, attempts = merged["long_division"]
    assert attempts == 4
    # Weighted by the work behind each, not an unweighted average of 0.5.
    assert score == pytest.approx((0.2 * 1 + 0.8 * 3) / 4)


def test_folding_two_rows_of_pure_exposure_invents_no_score():
    merged = _merge_mastery({"a": (0.0, 0)}, {"a": (0.0, 0)})
    assert merged == {"a": (0.0, 0)}


def test_a_topic_with_only_one_kind_of_evidence_is_left_alone():
    assert _merge_mastery({"a": (0.3, 2)}, {}) == {"a": (0.3, 2)}
    assert _merge_mastery({}, {"b": (0.4, 5)}) == {"b": (0.4, 5)}


# ─── End of the reader ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_readiness_reports_a_topic_the_classroom_just_taught():
    """The failure this change exists for, at the reader's own front door."""
    database = await _database()
    try:
        scope = topic_scope("Long division")
        async with AsyncSession(database) as db:
            db.add_all([
                _skill(scope, "Divide by a two-digit number", "a"),
                _state("id-a", 0.35, 1),
            ])
            await db.commit()
            standings = await standings_for_profile(
                db, LEARNER, [{"name": "Long division", "weight": 2.0}],
            )
        assert len(standings) == 1
        standing = standings[0]
        # The public identifier does not change: a plan still names its topic
        # the way every other surface names it.
        assert standing.concept_id == "long_division"
        assert standing.assessed and standing.mastery == pytest.approx(0.35)
        assert standing.attempts == 1
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_a_topic_nobody_has_taught_still_reports_nothing_shown():
    database = await _database()
    try:
        async with AsyncSession(database) as db:
            standings = await standings_for_profile(
                db, LEARNER, [{"name": "Mitosis"}],
            )
        assert len(standings) == 1
        # Not zero. Zero is a result; this is the absence of one.
        assert standings[0].mastery is None and standings[0].attempts == 0
    finally:
        await database.dispose()
