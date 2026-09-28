"""A reusable unit must be complete, safe, scoped and learner independent."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, LearningPlan, TeachingUnavailable, UnitPackage,
    UnitTargetPackage, model_json, select_package_turn, validate_unit_package,
)
from lyo_app.ai_classroom.models import (
    ClassroomQuestionExposure, ClassroomUnitPackage, Concept, ConceptPrerequisite, MasteryState,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
from lyo_app.ai_classroom.sdui_models import ActionIntent, QuizCard
from lyo_app.ai_classroom.skill_identity import resolve_skill_plan
from lyo_app.ai_classroom.teaching_prompt import unit_package_prompt
from lyo_app.ai_classroom.unit_package_cache import DatabaseUnitPackageCache, package_key
from lyo_app.core.database import Base
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, context, engine as classroom_engine, evaluation, plan, tap_probe,
)


def scripted_package(ctx, unit):
    """Author every slot deterministically, as one provider response would."""
    teacher = ScriptedTeacher()
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]))
    diagnostic = teacher._turn(ctx, state, "diagnose")
    orient = teacher._turn(ctx, state, "orient")
    targets = []
    for index in range(len(unit.targets)):
        state.target_index = index
        targets.append(UnitTargetPackage(**{
            move: teacher._turn(ctx, state, move).model_dump()
            for move in ("guided", "faded", "independent", "explain", "transfer")
        }))
    state.target_index = 0
    package = UnitPackage(diagnostic=diagnostic.model_dump(), orient=orient.model_dump(), targets=targets,
                          interleave=teacher._turn(ctx, state, "interleave").model_dump())
    validate_unit_package(package, unit)
    return package


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            Concept.__table__, ConceptPrerequisite.__table__,
            ClassroomUnitPackage.__table__, ClassroomQuestionExposure.__table__,
            MasteryState.__table__,
        ])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def make_teacher(db, ctx, unit):
    generated = AsyncMock(side_effect=lambda _prompt, _payload, _schema: scripted_package(ctx, unit))
    return AdaptiveTeacher(generate=generated, package_cache=DatabaseUnitPackageCache(db)), generated


@pytest.mark.asyncio
async def test_package_is_generated_once_then_reused_across_turns_and_reconnects(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    teacher, generated = make_teacher(db, ctx, unit)
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True, record_scope="unit")

    diagnostic = await teacher.turn(ctx, state, "diagnose")
    guided = await teacher.turn(ctx, state, "guided")
    assert diagnostic.task.kind == "diagnose" and guided.task.target_index == 0
    assert generated.await_count == 1
    assert generated.await_args.args[2] is UnitPackage
    assert len((await db.execute(select(ClassroomUnitPackage))).scalars().all()) == 1

    await db.commit()
    restored = GuidedState.model_validate_json(state.model_dump_json())
    replacement = AdaptiveTeacher(generate=AsyncMock(side_effect=AssertionError("re-authored")),
                                  package_cache=DatabaseUnitPackageCache(db))
    independent = await replacement.turn(ctx, restored, "independent")
    assert independent.task.kind == "apply" and independent.task.response_format != "choice"
    assert replacement.generate.await_count == 0
    assert restored.outbox == []  # Having a key and a rubric earns nothing.


@pytest.mark.asyncio
async def test_interleave_selects_the_earlier_skills_package(db):
    ctx = context(target_duration_minutes=24)
    units = plan(2)
    identities = await resolve_skill_plan(db, ctx, units)
    teacher, generated = make_teacher(db, ctx, units.units[0])
    state = GuidedState(owner=ctx.user_id, plan=units, unit_index=0,
                        skill_ids=identities.unit_ids, identity_required=True)
    await teacher.turn(ctx, state, "diagnose")
    state.unit_index, state.active_review_index = 1, 0
    revisit = await teacher.turn(ctx, state, "interleave")
    assert revisit.task.kind == "apply" and revisit.task.response_format != "choice"
    assert generated.await_count == 1
    assert len((await db.execute(select(ClassroomUnitPackage))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_key_separates_skill_level_language_and_changed_material(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    other = (await resolve_skill_plan(db, context(topic="Marketing"),
                                     LearningPlan(units=[unit]))).unit_ids[0]
    base = package_key(ctx, unit, skill)
    assert base != package_key(ctx, unit, other)
    assert base != package_key(ctx.model_copy(update={"language_code": "es-ES"}), unit, skill)
    assert base != package_key(ctx.model_copy(update={"preferred_difficulty": 0.9}), unit, skill)
    assert base != package_key(ctx, unit.model_copy(update={
        "material": unit.material + " Now check the whole before dividing."}), skill)

    teacher, generated = make_teacher(db, ctx, unit)
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    for i, variant in enumerate((ctx, ctx.model_copy(update={"language_code": "es-ES"}),
                                 ctx.model_copy(update={"preferred_difficulty": 0.9}))):
        learner = variant.model_copy(update={"user_id": str(i + 40)})
        await teacher.turn(learner, state.model_copy(update={"owner": learner.user_id}), "diagnose")
    assert generated.await_count == 3
    assert len((await db.execute(select(ClassroomUnitPackage))).scalars().all()) == 3


@pytest.mark.asyncio
async def test_invalid_unit_is_never_cached_or_shown(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    valid = scripted_package(ctx, unit)
    invalid = valid.model_copy(deep=True)
    invalid.targets[0].independent.board_content = invalid.targets[0].independent.task.example_answer
    generated = AsyncMock(return_value=invalid)
    teacher = AdaptiveTeacher(generate=generated, package_cache=DatabaseUnitPackageCache(db))
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    with pytest.raises(TeachingUnavailable):
        await teacher.turn(ctx, state, "diagnose")
    assert generated.await_count == 4  # Two package repairs and two live repairs.
    assert (await db.execute(select(ClassroomUnitPackage))).scalars().all() == []
    assert state.pending is None and state.outbox == [] and state.completed == []


@pytest.mark.asyncio
async def test_package_failure_falls_back_to_one_validated_live_move(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    invalid = scripted_package(ctx, unit)
    invalid.targets[0].faded.board_content = invalid.targets[0].faded.task.example_answer

    async def generate(_prompt, payload, schema):
        if schema is UnitPackage:
            return invalid
        return ScriptedTeacher()._turn(ctx, state, payload["move"])

    teacher = AdaptiveTeacher(generate=AsyncMock(side_effect=generate),
                              package_cache=DatabaseUnitPackageCache(db))
    turn = await teacher.turn(ctx, state, "diagnose")
    assert turn.task.kind == "diagnose" and teacher.generate.await_count == 3
    assert (await db.execute(select(ClassroomUnitPackage))).scalars().all() == []
    assert state.outbox == []  # The returned question is still only a question.


@pytest.mark.asyncio
async def test_second_semantic_judge_covers_every_package_move_before_cache(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    reviewed_moves = []

    async def judge(move, _unit, _turn):
        reviewed_moves.append(move)
        return move != "transfer"

    async def generate(_prompt, payload, schema):
        if schema is UnitPackage:
            return scripted_package(ctx, unit)
        return ScriptedTeacher()._turn(ctx, state, payload["move"])

    teacher = AdaptiveTeacher(generate=generate, semantic_judge=judge,
                              package_cache=DatabaseUnitPackageCache(db))
    assert (await teacher.turn(ctx, state, "diagnose")).task.kind == "diagnose"
    assert reviewed_moves.count("transfer") == 2
    assert (await db.execute(select(ClassroomUnitPackage))).scalars().all() == []
    assert state.outbox == []


@pytest.mark.asyncio
async def test_corrupt_saved_package_is_revalidated_and_rebuilt(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    key = package_key(ctx, unit, skill)
    db.add(ClassroomUnitPackage(
        cache_key=key.cache_key, skill_id=skill, level_band=key.level_band,
        language_code=key.language_code, content_hash=key.content_hash, version=1,
        content={"diagnostic": {"not_a_question": True}},
    ))
    await db.flush()
    teacher, generated = make_teacher(db, ctx, unit)
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    assert (await teacher.turn(ctx, state, "diagnose")).task.kind == "diagnose"
    assert generated.await_count == 1
    assert (await db.get(ClassroomUnitPackage, key.cache_key)).content["diagnostic"]["task"]["kind"] == "diagnose"


@pytest.mark.asyncio
async def test_cache_row_with_another_skill_identity_is_never_served(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    other = (await resolve_skill_plan(db, context(topic="Marketing"),
                                     LearningPlan(units=[unit]))).unit_ids[0]
    key = package_key(ctx, unit, skill)
    db.add(ClassroomUnitPackage(
        cache_key=key.cache_key, skill_id=other, level_band=key.level_band,
        language_code=key.language_code, content_hash=key.content_hash, version=1,
        content=scripted_package(ctx, unit).model_dump(mode="json"),
    ))
    await db.flush()
    teacher, generated = make_teacher(db, ctx, unit)
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        identity_required=True, skill_ids=[skill])
    assert (await teacher.turn(ctx, state, "diagnose")).task.kind == "diagnose"
    assert generated.await_count == 1
    assert (await db.get(ClassroomUnitPackage, key.cache_key)).skill_id == skill


@pytest.mark.asyncio
async def test_repeated_question_uses_live_generation_instead_of_recycling_answer(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    teacher, generated = make_teacher(db, ctx, unit)
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    first = await teacher.turn(ctx, state, "guided")
    from lyo_app.ai_classroom.adaptive_teaching import normalize_text
    state.recent_questions.append(normalize_text(first.task.scenario + " " + first.task.question))
    # A live writer proposes a new situation on the next call.
    live = ScriptedTeacher()._turn(ctx, state, "guided")
    live.task.scenario = "In a fresh setting, two identical fruit loaves are cut into halves and thirds."
    generated.side_effect = lambda _prompt, _payload, _schema: live
    second = await teacher.turn(ctx, state, "guided")
    assert second.task.scenario != first.task.scenario
    assert generated.await_count == 2  # package, then one live detour


@pytest.mark.asyncio
async def test_shared_transfer_is_fresh_for_each_learner_and_new_on_a_return_visit(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    teacher, generated = make_teacher(db, ctx, unit)

    def state_for(user_id):
        return GuidedState(owner=user_id, plan=LearningPlan(units=[unit]),
                           identity_required=True, skill_ids=[skill], record_scope="unit")

    first = await teacher.turn(ctx, state_for("42"), "transfer")
    assert generated.await_count == 1
    other = await teacher.turn(ctx.model_copy(update={"user_id": "43"}), state_for("43"), "transfer")
    assert first.task.question == other.task.question and generated.await_count == 1

    live = ScriptedTeacher()._turn(ctx, state_for("42"), "transfer")
    live.task.scenario = "On a fresh hiking trail, two equal ropes are cut into 4 or 8 equal lengths."
    generated.side_effect = lambda _prompt, _payload, _schema: live
    return_visit = await teacher.turn(ctx, state_for("42"), "transfer")
    assert return_visit.task.scenario != first.task.scenario
    assert generated.await_count == 2
    exposures = (await db.execute(select(ClassroomQuestionExposure))).scalars().all()
    assert len(exposures) == 3 and len({e.learner_hash for e in exposures}) == 2
    assert all(len(e.question_hash) == 64 for e in exposures)


@pytest.mark.asyncio
async def test_previous_question_cannot_be_reauthored_as_new_transfer_evidence(db):
    ctx, unit = context(target_duration_minutes=8), plan(1).units[0]
    skill = (await resolve_skill_plan(db, ctx, LearningPlan(units=[unit]))).unit_ids[0]
    state = GuidedState(owner=ctx.user_id, plan=LearningPlan(units=[unit]),
                        skill_ids=[skill], identity_required=True)
    teacher, generated = make_teacher(db, ctx, unit)
    original = await teacher.turn(ctx, state, "transfer")
    generated.side_effect = lambda _prompt, _payload, _schema: original
    with pytest.raises(TeachingUnavailable):
        await teacher.turn(ctx, GuidedState.model_validate_json(state.model_dump_json()), "transfer")
    assert generated.await_count == 3  # First package; two rejected live repeats.
    assert state.outbox == [] and state.completed == []


@pytest.mark.asyncio
async def test_package_uses_one_structured_provider_call_with_room_for_all_targets(monkeypatch):
    ctx, unit = context(), plan(1).units[0]
    package = scripted_package(ctx, unit)
    completion = AsyncMock(return_value={
        "content": package.model_dump_json(), "model_used": "gpt-4o-mini",
    })
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    response = await model_json(unit_package_prompt(), {"unit": unit.model_dump()}, UnitPackage)
    assert response == package
    assert completion.await_count == 1
    request = completion.await_args.kwargs
    assert request["max_tokens"] == 16000
    schema = json.loads(request["messages"][0]["content"].split(
        "Return only JSON matching this schema:\n")[1])
    assert set(schema["properties"]) == {"diagnostic", "orient", "targets", "interleave"}


@pytest.mark.asyncio
async def test_scripted_session_selects_package_but_grades_only_real_work(db):
    ctx = context(target_duration_minutes=8)
    unit_plan = plan(1)
    calls = []

    async def generate(_prompt, payload, schema):
        calls.append(schema.__name__)
        if schema is LearningPlan:
            return unit_plan
        if schema is UnitPackage:
            return scripted_package(ctx, unit_plan.units[0])
        return ScriptedTeacher()._turn(ctx, GuidedState(owner=ctx.user_id, plan=unit_plan),
                                      payload["move"])

    teacher = AdaptiveTeacher(generate=generate, package_cache=DatabaseUnitPackageCache(db))
    teacher.evaluate = AsyncMock(return_value=evaluation())
    runner = AdaptiveSession(teacher, skill_resolver=lambda c, p: resolve_skill_plan(db, c, p))
    progress = {}
    scene = await runner.run(ctx, progress, action(welcome=True))
    state = GuidedState.model_validate(progress["guided_state"])
    assert calls == ["LearningPlan", "UnitPackage"]
    assert state.outbox == [] and state.completed == []
    assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]

    progress["guided_state"] = json.loads(json.dumps(progress["guided_state"]))
    await tap_probe(runner, progress, ctx)
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.phase == "guided" and calls == ["LearningPlan", "UnitPackage"]
    assert state.outbox == [] and state.completed == []  # A correct tap is a ceiling only.
    await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, message="How do these cuts compare?"))
    assert calls[-1] == "ExplanationTurn"  # A real question still gets a live response.


@pytest.mark.asyncio
async def test_production_engine_installs_database_cache_for_its_default_teacher(db, monkeypatch):
    from lyo_app.ai_classroom import adaptive_teaching

    ctx, unit_plan = context(target_duration_minutes=8), plan(1)
    original_teacher = adaptive_teaching.AdaptiveTeacher
    installed = []

    async def generate(_prompt, _payload, schema):
        if schema is LearningPlan:
            return unit_plan
        if schema is UnitPackage:
            return scripted_package(ctx, unit_plan.units[0])
        raise AssertionError("The opening does not need another generated screen")

    def teacher_factory(*, package_cache):
        installed.append(package_cache)
        return original_teacher(generate=generate, package_cache=package_cache)

    monkeypatch.setattr(adaptive_teaching, "AdaptiveTeacher", teacher_factory)
    instance = classroom_engine(ctx)
    del instance.adaptive_teacher, instance.skill_resolver
    instance.db = instance.context_assembler.db = db
    key = session_progress_key(ctx.user_id, ctx.session_id)
    _SESSION_PROGRESS.pop(key, None)
    try:
        scene = await instance.process_trigger(action(welcome=True))
        state = GuidedState.model_validate(_SESSION_PROGRESS[key]["guided_state"])
        assert len(installed) == 1 and isinstance(installed[0], DatabaseUnitPackageCache)
        assert next(c for c in scene.components if isinstance(c, QuizCard)).concept_id == state.skill_ids[0]
        assert len((await db.execute(select(ClassroomUnitPackage))).scalars().all()) == 1
        assert len((await db.execute(select(ClassroomQuestionExposure))).scalars().all()) == 1
    finally:
        _SESSION_PROGRESS.pop(key, None)


def test_package_rejects_repeated_questions_and_wrong_target():
    ctx, unit = context(), plan(1).units[0]
    package = scripted_package(ctx, unit)
    package.targets[0].faded.task.scenario = package.targets[0].guided.task.scenario
    package.targets[0].faded.task.question = package.targets[0].guided.task.question
    with pytest.raises(ValueError, match="repeats a question"):
        validate_unit_package(package, unit)
    package = scripted_package(ctx, unit)
    package.targets[0].guided.task.target_index = 1
    with pytest.raises(ValueError, match="wrong component"):
        validate_unit_package(package, unit)


def test_prompt_and_slot_contract_cover_the_full_unit():
    ctx, unit = context(), plan(3).units[0].model_copy(update={
        "practice_targets": ["Compare halves with thirds", "Compare thirds with fifths",
                             "Compare shares of the same whole"],
    })
    prompts = unit_package_prompt()
    for move in ("diagnostic", "orient", "guided", "faded", "independent",
                 "explain", "transfer", "interleave"):
        assert move in prompts
    package = scripted_package(ctx, unit)
    assert len(package.targets) == 3
    for index in range(3):
        for move in ("guided", "faded", "independent", "explain", "transfer"):
            assert select_package_turn(package, move, index).task.target_index == index


def test_migration_adds_cache_without_changing_existing_concepts():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/classroom_packages_001_validated_unit_packages.py"
    spec = importlib.util.spec_from_file_location("classroom_packages_001", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE concepts (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO concepts VALUES ('old-id')"))
        original = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
        finally:
            migration.op = original
        assert inspect(connection).has_table("classroom_unit_packages")
        assert inspect(connection).has_table("classroom_question_exposures")
        assert connection.execute(text("SELECT id FROM concepts")).one() == ("old-id",)
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.downgrade()
        finally:
            migration.op = original
        assert not inspect(connection).has_table("classroom_unit_packages")
        assert not inspect(connection).has_table("classroom_question_exposures")
        assert connection.execute(text("SELECT id FROM concepts")).one() == ("old-id",)
    engine.dispose()
