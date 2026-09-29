"""Real database identities for classroom skills; no inferred learner credit."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningPlan, LearningUnit
from lyo_app.ai_classroom.models import Concept, ConceptPrerequisite, MasteryState
from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
from lyo_app.ai_classroom.sdui_models import ActionIntent, QuizCard
from lyo_app.ai_classroom.skill_identity import resolve_skill_plan
from lyo_app.core.database import Base
from lyo_app.events.mastery_projection import ProjectionOutcome, project_event_to_mastery_state
from lyo_app.events.models import LearningEvent
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, engine as classroom_engine, tap_probe,
)


@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[
            Concept.__table__, ConceptPrerequisite.__table__, MasteryState.__table__,
        ])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def plan(*titles, prerequisite=None):
    return LearningPlan(units=[LearningUnit(
        title=title, objective="Compare the size of equal parts.",
        material="From one equal whole, fewer cuts make each piece larger than more cuts.",
        prerequisite_titles=[titles[0]] if prerequisite == i else [],
    ) for i, title in enumerate(titles)])


@pytest.mark.asyncio
async def test_same_display_title_in_two_topics_never_shares_a_skill_id(db):
    unit = plan("Compare equal shares")
    fractions = await resolve_skill_plan(db, context(topic="Fractions"), unit)
    marketing = await resolve_skill_plan(db, context(topic="Marketing"), unit)
    again = await resolve_skill_plan(db, context(topic="fractions"), unit)
    assert fractions.unit_ids == again.unit_ids
    assert fractions.unit_ids != marketing.unit_ids
    assert UUID(fractions.unit_ids[0])
    assert (await db.get(Concept, fractions.unit_ids[0])).name == "Compare equal shares"


@pytest.mark.asyncio
async def test_slug_collisions_and_long_titles_do_not_merge_earned_work(db):
    ctx = context(topic="Marketing")
    a = await resolve_skill_plan(db, ctx, plan("Compare prices!"))
    b = await resolve_skill_plan(db, ctx, plan("Compare prices?"))
    prefix = "Important context " * 5
    c = await resolve_skill_plan(db, ctx, plan(prefix + " A"))
    d = await resolve_skill_plan(db, ctx, plan(prefix + " B"))
    assert len({a.unit_ids[0], b.unit_ids[0], c.unit_ids[0], d.unit_ids[0]}) == 4
    assert (await db.get(Concept, c.unit_ids[0])).name != (await db.get(Concept, d.unit_ids[0])).name


@pytest.mark.asyncio
async def test_authored_courses_with_same_lesson_name_remain_separate(db):
    units = plan("Estimate an outcome")
    left = await resolve_skill_plan(db, context(course_id="course-A", lesson_id="1",
                                                lesson_title="Estimate an outcome"), units)
    right = await resolve_skill_plan(db, context(course_id="course-B", lesson_id="1",
                                                 lesson_title="Estimate an outcome"), units)
    later = await resolve_skill_plan(db, context(course_id="course-A", lesson_id="2",
                                                 lesson_title="Estimate an outcome"), units)
    assert left.topic_id != right.topic_id
    assert left.topic_id != later.topic_id
    assert left.unit_ids[0] != left.topic_id  # A broad lesson name is not its unit's objective.


@pytest.mark.asyncio
async def test_authored_lesson_files_each_answer_under_its_actual_unit(db):
    ctx = context(course_id="course-A", lesson_id="1", lesson_title="Equal shares",
                  target_duration_minutes=24)
    progress = {}
    runner = AdaptiveSession(ScriptedTeacher(),
        skill_resolver=lambda context_, plan_: resolve_skill_plan(db, context_, plan_))
    scene = await runner.run(ctx, progress, action(welcome=True))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.record_scope == "unit"
    assert AdaptiveSession.record_concept(ctx, state) == state.skill_ids[0]
    assert state.skill_ids[0] != state.topic_skill_id
    assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]


@pytest.mark.asyncio
async def test_same_title_with_different_objective_is_not_one_skill(db):
    ctx = context(topic="Marketing")
    first = plan("Compare prices")
    second = LearningPlan(units=[first.units[0].model_copy(update={
        "objective": "Compare unit prices of two packages at a store.",
    })])
    a, b = await resolve_skill_plan(db, ctx, first), await resolve_skill_plan(db, ctx, second)
    assert a.unit_ids[0] != b.unit_ids[0]
    assert (await db.get(Concept, a.unit_ids[0])).display_name == "Compare prices"
    assert (await db.get(Concept, b.unit_ids[0])).display_name == "Compare prices"


@pytest.mark.asyncio
async def test_only_named_prerequisites_are_edges_and_never_grant_mastery(db):
    ctx = context()
    identities = await resolve_skill_plan(db, ctx, plan(
        "Compare equal shares", "Scale equal shares", "Check a recipe", prerequisite=1,
    ))
    rows = (await db.execute(select(ConceptPrerequisite))).scalars().all()
    assert [(row.concept_id, row.prerequisite_id) for row in rows] == [
        (identities.unit_ids[1], identities.unit_ids[0]),
    ]
    assert (await db.execute(select(MasteryState))).scalars().all() == []

    # A demonstrated later skill updates itself only. A dependency is not a
    # substitute for the learner's own answer on the earlier skill.
    answer = LearningEvent(user_id=42, concept_id=identities.unit_ids[1],
                           evidence_type="application", measurable_outcome=1.0,
                           evidence_confidence=0.9, hints_used=0)
    assert await project_event_to_mastery_state(db, answer) is ProjectionOutcome.PROJECTED
    rows = (await db.execute(select(MasteryState))).scalars().all()
    assert [row.concept_id for row in rows] == [identities.unit_ids[1]]


@pytest.mark.asyncio
async def test_reverse_dependency_in_a_later_plan_is_rejected(db):
    ctx = context()
    await resolve_skill_plan(db, ctx, plan("Compare equal shares", "Scale equal shares", prerequisite=1))
    with pytest.raises(ValueError, match="cycle"):
        await resolve_skill_plan(db, ctx, plan("Scale equal shares", "Compare equal shares", prerequisite=1))
    assert len((await db.execute(select(ConceptPrerequisite))).all()) == 1


@pytest.mark.asyncio
async def test_database_rejects_duplicate_identity_and_self_dependency(db):
    skill_id = (await resolve_skill_plan(db, context(), plan("Compare equal shares"))).unit_ids[0]
    skill = await db.get(Concept, skill_id)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Concept(id="another", name="Another label", subject=skill.subject,
                           identity_key=skill.identity_key))
            await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ConceptPrerequisite(concept_id=skill_id, prerequisite_id=skill_id))
            await db.flush()
    assert (await db.execute(select(ConceptPrerequisite))).all() == []


@pytest.mark.parametrize("requirement", ["Missing skill", "Scale equal shares"])
def test_model_rejects_unmet_or_self_prerequisites(requirement):
    with pytest.raises(ValueError, match="Prerequisites"):
        LearningPlan(units=[LearningUnit(title="Scale equal shares",
            objective="Compare the size of equal parts.",
            material="From one equal whole, fewer cuts make each piece larger than more cuts.",
            prerequisite_titles=[requirement])])


@pytest.mark.asyncio
async def test_live_scripted_session_uses_persisted_ids_after_reconnect(db):
    ctx, progress = context(target_duration_minutes=24), {}
    resolver = lambda context_, plan_: resolve_skill_plan(db, context_, plan_)
    teacher = ScriptedTeacher()
    runner = AdaptiveSession(teacher, skill_resolver=resolver)
    scene = await runner.run(ctx, progress, action(welcome=True, record_scope="unit"))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.identity_required and len(state.skill_ids) == 3
    assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]
    assert scene.metadata.target_concepts == [state.skill_ids[0]]
    assert state.outbox == []  # The opening question alone proves nothing.

    progress["guided_state"] = json.loads(json.dumps(progress["guided_state"]))
    runner = AdaptiveSession(teacher, skill_resolver=resolver)
    await tap_probe(runner, progress, ctx)
    pending = GuidedState.model_validate(progress["guided_state"]).pending
    await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending.id,
        answer_data={"selected_option_id": "a"}))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.outbox[-1]["concept_id"] == state.skill_ids[0]
    assert AdaptiveSession.record_concept(ctx, state) == state.skill_ids[0]
    assert (await resolve_skill_plan(db, ctx, state.plan)).unit_ids == state.skill_ids


@pytest.mark.asyncio
async def test_free_topic_records_the_actual_unit_without_an_extra_client_flag(db):
    ctx, progress = context(target_duration_minutes=8), {}
    runner = AdaptiveSession(ScriptedTeacher(),
        skill_resolver=lambda context_, plan_: resolve_skill_plan(db, context_, plan_))
    await runner.run(ctx, progress, action(welcome=True))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.record_scope == "unit"
    assert AdaptiveSession.record_concept(ctx, state) == state.skill_ids[0]
    assert AdaptiveSession.record_concept(ctx, state) != state.topic_skill_id


@pytest.mark.asyncio
async def test_missing_scope_cannot_fall_back_to_a_shared_placeholder(db):
    ctx, progress = context(topic=None, lesson_title=None, target_duration_minutes=8), {}
    runner = AdaptiveSession(ScriptedTeacher(),
        skill_resolver=lambda context_, plan_: resolve_skill_plan(db, context_, plan_))
    scene = await runner.run(ctx, progress, action(welcome=True))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.identity_required and state.skill_ids == []
    assert AdaptiveSession.record_concept(ctx, state) is None
    assert scene.metadata.target_concepts == []
    assert (await db.execute(select(Concept))).scalars().all() == []


@pytest.mark.asyncio
async def test_old_saved_question_rebinds_without_rewriting_past_evidence(db):
    ctx, progress = context(target_duration_minutes=24), {}
    old = AdaptiveSession(ScriptedTeacher())
    await old.run(ctx, progress, action(welcome=True, record_scope="unit"))
    await tap_probe(old, progress, ctx)
    prior = GuidedState.model_validate(progress["guided_state"])
    assert next(c for c in prior.scene["components"] if c["type"] == "QuizCard")["concept_id"] == "Fraction skill 1"
    # A previously queued demonstration retains its original legacy key.
    progress["guided_state"]["outbox"] = [{
        "event_id": "old-checkpoint", "user_id": "42", "concept_id": "Fraction skill 1",
        "correct": False, "evidence_type": None, "hints_used": 0,
    }]

    runner = AdaptiveSession(ScriptedTeacher(),
        skill_resolver=lambda context_, plan_: resolve_skill_plan(db, context_, plan_))
    scene = await runner.run(ctx, progress, action(welcome=True))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.identity_required
    assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]
    assert state.outbox[0]["concept_id"] == "Fraction skill 1"


@pytest.mark.asyncio
async def test_old_topic_scoped_session_switches_future_answers_to_its_unit(db):
    ctx, progress = context(lesson_title="Equal shares", target_duration_minutes=24), {}
    teacher = ScriptedTeacher()
    old = AdaptiveSession(teacher)
    await old.run(ctx, progress, action(welcome=True))
    await tap_probe(old, progress, ctx)
    assert GuidedState.model_validate(progress["guided_state"]).record_scope == "topic"
    progress["guided_state"]["outbox"] = [{
        "event_id": "earlier-answer", "concept_id": "Equal shares", "correct": True,
    }]

    runner = AdaptiveSession(teacher,
        skill_resolver=lambda context_, plan_: resolve_skill_plan(db, context_, plan_))
    scene = await runner.run(ctx, progress, action(welcome=True))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.record_scope == "unit"
    assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]
    assert state.outbox[0]["concept_id"] == "Equal shares"
    await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, state.pending.id,
        answer_data={"selected_option_id": "a"}))
    assert progress["guided_state"]["outbox"][-1]["concept_id"] == state.skill_ids[0]


@pytest.mark.asyncio
async def test_live_engine_installs_database_skill_resolution(db):
    ctx = context(target_duration_minutes=8)
    instance = classroom_engine(ctx)
    del instance.skill_resolver  # exercise the production resolver instead of simulated IDs
    instance.db = instance.context_assembler.db = db
    key = session_progress_key(ctx.user_id, ctx.session_id)
    _SESSION_PROGRESS.pop(key, None)
    try:
        scene = await instance.process_trigger(action(welcome=True))
        state = GuidedState.model_validate(_SESSION_PROGRESS[key]["guided_state"])
        assert state.identity_required
        assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]
        assert await db.get(Concept, state.skill_ids[0]) is not None
    finally:
        _SESSION_PROGRESS.pop(key, None)


@pytest.mark.asyncio
async def test_due_interleave_and_review_outbox_use_the_earlier_persisted_id(db):
    ctx, progress = context(target_duration_minutes=24), {}
    runner = AdaptiveSession(ScriptedTeacher(),
        skill_resolver=lambda context_, plan_: resolve_skill_plan(db, context_, plan_))

    async def answer():
        current = GuidedState.model_validate(progress["guided_state"])
        pending = current.pending
        intent = (ActionIntent.SUBMIT_ANSWER if pending.task.response_format == "choice"
                  else ActionIntent.SUBMIT_TRANSFER)
        await runner.run(ctx, progress, action(intent, pending.id, answer_data={
            "selected_option_id": "a", "response": "Fewer equal cuts leave larger pieces.",
        }))

    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    for _ in range(8):
        if GuidedState.model_validate(progress["guided_state"]).unit_done:
            break
        await advance_to_task(runner, progress, ctx)
        await answer()
    first = GuidedState.model_validate(progress["guided_state"])
    assert first.unit_done
    assert first.review_outbox[0]["concept_id"] == first.skill_ids[0]

    progress["guided_state"]["review_history"][0]["decided_at"] = (
        datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    ctx.scheduled_due_items = [first.skill_ids[0]]
    await runner.run(ctx, progress, action())
    await tap_probe(runner, progress, ctx)
    await answer()
    await answer()
    interleave = GuidedState.model_validate(progress["guided_state"])
    assert interleave.phase == "interleave" and interleave.review_is_due
    assert interleave.active_review_index == 0 and interleave.unit_index == 1
    await answer()
    resumed = GuidedState.model_validate(progress["guided_state"])
    assert resumed.outbox[-1]["concept_id"] == first.skill_ids[0]
    assert resumed.outbox[-1]["evidence_type"] == "retrieval"
    assert resumed.unit_index == 1


def test_old_topic_review_does_not_claim_retention_for_new_unit():
    ctx = context(topic="Fractions", target_duration_minutes=24)
    state = GuidedState(owner=ctx.user_id, plan=plan("Equal shares", "Scale shares"),
                        record_scope="unit", identity_required=True,
                        skill_ids=["11111111-1111-4111-8111-111111111111",
                                   "22222222-2222-4222-8222-222222222222"],
                        unit_index=1, review_history=[{
                            "concept_id": "Fractions", "unit_index": 0,
                            "decided_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                        }])
    ctx.scheduled_due_items = ["fractions"]
    runner = AdaptiveSession(ScriptedTeacher())
    assert runner.start_interleave(ctx, state)
    assert state.active_review_index == 0
    assert not state.review_is_due


def test_migration_adds_identity_without_rekeying_legacy_evidence():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/classroom_identity_001_persistent_skills.py"
    spec = importlib.util.spec_from_file_location("classroom_identity_001", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE concepts (id VARCHAR(36) PRIMARY KEY, name VARCHAR(200) NOT NULL, subject VARCHAR(100) NOT NULL)"))
        connection.execute(text("INSERT INTO concepts VALUES ('old-id', 'Existing lesson', 'math')"))
        operation = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
        finally:
            migration.op = operation
        assert {col["name"] for col in inspect(connection).get_columns("concepts")} >= {"identity_key"}
        assert inspect(connection).has_table("concept_prerequisites")
        assert connection.execute(text("SELECT id, identity_key FROM concepts")).one() == ("old-id", None)
    engine.dispose()
