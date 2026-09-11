"""One key per skill, and no learner loses progress getting there.

`LearnerMastery.skill_id` was written two ways. Chat writes `slugify_skill`
output. The Classroom wrote the learning objective as authored. So one
learner accumulated two rows for one concept — "compare_fractions" and
"Compare fractions" — and neither surface could see the other's evidence.

The interesting half is the migration. A plain rename collides wherever the
learner already has a slug row, which is the common case since that is
precisely the duplication being fixed. And abandoning the classroom-keyed
rows would show a mid-course learner their progress resetting.
"""

import json
import unittest
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine
from lyo_app.core.database import Base
from lyo_app.personalization.models import LearnerMastery

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "skillkey_001",
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "skillkey_001_canonical_skill_ids.py",
)
skillkey = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skillkey)


# ─── The two surfaces now agree ──────────────────────────────────────────────

class OneKeyTests(unittest.TestCase):
    def test_the_classroom_keys_a_skill_the_way_chat_does(self):
        self.assertEqual(
            SceneLifecycleEngine._canonical_concept_id("Compare Fractions"),
            slugify_skill("Compare Fractions"),
        )

    def test_the_migration_slug_matches_the_application_slug(self):
        """The migration inlines its own copy so a later refactor cannot
        silently change what an already-applied migration meant. That copy
        still has to agree with the real one today."""
        for topic in ("Compare Fractions", "Square Roots!", "photosynthesis",
                      "  spaced   out  ", "Ünicode Things", "x" * 200):
            self.assertEqual(skillkey._slugify(topic), slugify_skill(topic))

    def test_both_dkt_call_sites_canonicalise(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "ai_classroom" / "scene_lifecycle_engine.py"
        ).read_text()
        self.assertEqual(source.count("dkt_skill_id = self._canonical_concept_id("), 2)
        self.assertNotIn('skill_id=validated_skill_id or "current_concept"', source)


# ─── The migration, against a real database ──────────────────────────────────

@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LearnerMastery.__table__])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _mastery(**overrides):
    fields = {
        "user_id": 1,
        "skill_id": "Compare fractions",
        "mastery_level": 0.4,
        "uncertainty": 0.3,
        "attempts": 4,
        "successes": 2,
        "hints_used": 1,
        "misconceptions": ["flipped_the_fraction"],
        "first_attempt": datetime(2026, 1, 1),
        "last_seen": datetime(2026, 2, 1),
        "mastery_achieved": None,
    }
    fields.update(overrides)
    return LearnerMastery(**fields)


async def _run_migration(db):
    """Drive the migration body against this session's connection."""
    conn = await db.connection()

    def _apply(sync_conn):
        class _Op:
            @staticmethod
            def get_bind():
                return sync_conn

        original = skillkey.op
        skillkey.op = _Op()
        try:
            skillkey.upgrade()
        finally:
            skillkey.op = original

    await conn.run_sync(_apply)


async def _rows(db, user_id=1):
    return (
        await db.execute(
            select(LearnerMastery).where(LearnerMastery.user_id == user_id)
        )
    ).scalars().all()


async def test_a_classroom_row_is_re_keyed_not_discarded(db):
    db.add(_mastery())
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    rows = await _rows(db)
    assert len(rows) == 1
    assert rows[0].skill_id == "compare_fractions"
    assert rows[0].attempts == 4  # the learner's history survives


async def test_two_rows_for_one_concept_become_one(db):
    db.add_all([
        _mastery(skill_id="Compare fractions", attempts=4, successes=2, hints_used=1),
        _mastery(skill_id="compare_fractions", attempts=6, successes=5, hints_used=2,
                 mastery_level=0.8, uncertainty=0.1),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    rows = await _rows(db)
    assert len(rows) == 1
    merged = rows[0]
    assert merged.skill_id == "compare_fractions"
    # Nothing the learner did is thrown away.
    assert merged.attempts == 10
    assert merged.successes == 7
    assert merged.hints_used == 3


async def test_the_estimate_with_more_evidence_behind_it_wins(db):
    db.add_all([
        _mastery(skill_id="Compare fractions", attempts=20, mastery_level=0.9, uncertainty=0.05),
        _mastery(skill_id="compare_fractions", attempts=2, mastery_level=0.1, uncertainty=0.6),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    merged = (await _rows(db))[0]
    assert merged.mastery_level == pytest.approx(0.9)
    assert merged.uncertainty == pytest.approx(0.05)


async def test_a_weaker_estimate_does_not_overwrite_a_stronger_one(db):
    """The mirror of the case above. With only one direction tested, an
    unconditional overwrite passes: the row being folded in happens to be the
    stronger one. Here it is the weaker one, so the guard has to hold."""
    db.add_all([
        _mastery(skill_id="compare_fractions", attempts=20, mastery_level=0.9, uncertainty=0.05),
        _mastery(skill_id="Compare fractions", attempts=2, mastery_level=0.1, uncertainty=0.6),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    merged = (await _rows(db))[0]
    assert merged.mastery_level == pytest.approx(0.9)
    assert merged.uncertainty == pytest.approx(0.05)


async def test_misconceptions_from_both_rows_survive(db):
    db.add_all([
        _mastery(skill_id="Compare fractions", misconceptions=["flipped_the_fraction"]),
        _mastery(skill_id="compare_fractions", misconceptions=["bigger_denominator_is_bigger"]),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    merged = (await _rows(db))[0]
    stored = merged.misconceptions
    if isinstance(stored, str):
        stored = json.loads(stored)
    assert "flipped_the_fraction" in stored
    assert "bigger_denominator_is_bigger" in stored


async def test_the_learning_history_keeps_its_true_span(db):
    db.add_all([
        _mastery(skill_id="Compare fractions",
                 first_attempt=datetime(2026, 1, 1), last_seen=datetime(2026, 1, 20)),
        _mastery(skill_id="compare_fractions",
                 first_attempt=datetime(2026, 2, 1), last_seen=datetime(2026, 3, 1)),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    merged = (await _rows(db))[0]
    assert merged.first_attempt == datetime(2026, 1, 1)
    assert merged.last_seen == datetime(2026, 3, 1)


async def test_other_learners_are_left_alone(db):
    db.add_all([
        _mastery(user_id=1, skill_id="Compare fractions"),
        _mastery(user_id=2, skill_id="Compare fractions"),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    assert len(await _rows(db, 1)) == 1
    assert len(await _rows(db, 2)) == 1


async def test_rows_already_correctly_keyed_are_untouched(db):
    db.add(_mastery(skill_id="compare_fractions", attempts=7))
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    rows = await _rows(db)
    assert len(rows) == 1
    assert rows[0].attempts == 7


async def test_running_it_twice_changes_nothing_the_second_time(db):
    db.add_all([
        _mastery(skill_id="Compare fractions", attempts=4),
        _mastery(skill_id="compare_fractions", attempts=6),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()
    first = (await _rows(db))[0].attempts

    await _run_migration(db)
    db.expire_all()
    rows = await _rows(db)

    assert len(rows) == 1
    assert rows[0].attempts == first  # not summed again


async def test_unrelated_skills_are_not_collapsed_together(db):
    db.add_all([
        _mastery(skill_id="Compare fractions"),
        _mastery(skill_id="Add fractions"),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    assert {r.skill_id for r in await _rows(db)} == {"compare_fractions", "add_fractions"}


class GraphIdsAreNotSlugifiedTests(unittest.TestCase):
    """A UUID is already the canonical key.

    The live path leaves graph ids alone — slugifying one turns its hyphens
    into underscores and produces a key nothing matches. The migration
    slugified everything, so historical graph-keyed rows were rewritten onto a
    key no future write would ever use: splitting exactly the mastery it
    exists to merge.
    """

    def test_a_uuid_is_left_exactly_as_it_is(self):
        graph_id = "8ec42eab-fa05-4455-afb8-56240ba48c91"
        self.assertEqual(skillkey._canonical_key(graph_id), graph_id)

    def test_human_text_is_still_slugified(self):
        self.assertEqual(skillkey._canonical_key("Compare Fractions"), "compare_fractions")

    def test_the_migration_agrees_with_the_live_path(self):
        for value in (
            "8ec42eab-fa05-4455-afb8-56240ba48c91",
            "Compare Fractions",
            "photosynthesis",
        ):
            self.assertEqual(
                skillkey._canonical_key(value),
                SceneLifecycleEngine._canonical_concept_id(value),
            )


async def test_a_graph_keyed_row_is_not_rewritten(db):
    graph_id = "8ec42eab-fa05-4455-afb8-56240ba48c91"
    db.add(_mastery(skill_id=graph_id, attempts=9))
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    rows = await _rows(db)
    assert len(rows) == 1
    assert rows[0].skill_id == graph_id
    assert rows[0].attempts == 9


async def test_a_merged_mastery_date_is_written_not_just_computed(db):
    """`_merge` picked the earliest `mastery_achieved` and the UPDATE never
    carried it, so a learner whose only mastery record was on the discarded
    row lost the fact that they had ever mastered the skill."""
    db.add_all([
        _mastery(skill_id="compare_fractions", attempts=2, mastery_achieved=None),
        _mastery(skill_id="Compare fractions", attempts=1,
                 mastery_achieved=datetime(2026, 1, 15)),
    ])
    await db.commit()

    await _run_migration(db)
    db.expire_all()

    merged = (await _rows(db))[0]
    assert merged.mastery_achieved == datetime(2026, 1, 15)
