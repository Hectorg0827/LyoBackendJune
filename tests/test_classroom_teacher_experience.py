from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher,
    GuidedState,
    LearningTurn,
    TeachingBeat,
)
from lyo_app.ai_classroom.sdui_models import ExampleBlock
from lyo_app.ai_classroom.unit_package_cache import package_key
from tests.adaptive_fixtures import ScriptedTeacher, context, plan


def state_for_class():
    return GuidedState(
        owner="42",
        plan=plan(2),
        remaining_units=[1],
        phase="guided",
        next_move="guided",
    )


def test_teacher_state_round_trips_with_strategy_signals_and_board_memory():
    state = state_for_class()
    state.active_strategy = "analogy"
    state.strategy_history = ["worked_example", "analogy"]
    state.misconceptions = ["more_pieces_means_more_each"]
    state.learner_signals = ["learner_question", "answer:partial:guided"]
    state.board_memory = [{"title": "Equal wholes", "content": "1/2 > 1/3"}]
    state.open_question = "Why does the denominator change the piece size?"

    restored = GuidedState.model_validate(state.model_dump(mode="json"))

    assert restored.active_strategy == "analogy"
    assert restored.strategy_history[-1] == "analogy"
    assert restored.misconceptions == ["more_pieces_means_more_each"]
    assert restored.learner_signals[-1] == "answer:partial:guided"
    assert restored.board_memory[-1]["title"] == "Equal wholes"
    assert restored.open_question.startswith("Why does")


def test_reteach_changes_representation_instead_of_repeating_the_last_strategy():
    state = state_for_class()
    state.strategy_history = ["analogy"]
    assert AdaptiveTeacher.strategy_for(state, "reteach") == "counterexample"

    state.strategy_history = ["analogy", "counterexample"]
    assert AdaptiveTeacher.strategy_for(state, "reteach") == "worked_example"


def test_board_memory_is_deduplicated_and_bounded():
    state = state_for_class()
    for number in range(8):
        AdaptiveSession.remember_beat(
            state,
            TeachingBeat(
                speech=f"Teaching beat number {number}.",
                board_title=f"Anchor {number}",
                board_content=f"Concrete board content number {number}.",
            ),
        )

    assert len(state.board_memory) == 6
    assert state.board_memory[0]["title"] == "Anchor 2"
    assert state.board_memory[-1]["title"] == "Anchor 7"

    duplicate = TeachingBeat(
        speech="Repeat the latest anchor with a useful explanation.",
        board_title="Anchor 7",
        board_content="Concrete board content number 7.",
    )
    AdaptiveSession.remember_beat(state, duplicate)
    assert len(state.board_memory) == 6
    assert state.board_memory[-1]["title"] == "Anchor 7"


def test_surface_re_emits_only_the_latest_prior_board_anchor_for_every_client():
    ctx = context()
    state = state_for_class()
    state.board_memory = [
        {"title": "Old anchor", "content": "This should no longer be replayed."},
        {"title": "First anchor", "content": "The same whole is divided into equal parts."},
        {"title": "Current anchor", "content": "A half is larger than a third of the same whole."},
    ]
    session = AdaptiveSession(ScriptedTeacher())

    components = session.surface(
        ctx,
        state,
        "Compare the two pieces using the same whole.",
        "Current anchor",
        "A half is larger than a third of the same whole.",
    )

    memory = next(
        component for component in components
        if isinstance(component, ExampleBlock)
        and component.component_id == "classroom-board-memory"
    )
    assert "First anchor" in memory.content
    assert "same whole" in memory.content
    assert "Old anchor" not in memory.content
    assert "Current anchor" not in memory.content
    assert len(memory.content) <= 320


def test_summary_names_key_ideas_and_the_next_skill_to_revisit():
    ctx = context()
    state = state_for_class()
    state.board_memory = [
        {"title": "Equal wholes", "content": "Compare fractions only after identifying the same whole."},
    ]
    state.skipped = [0]
    state.path_done = True
    state.remaining_units = []
    session = AdaptiveSession(ScriptedTeacher())

    scene = session.summary(ctx, state)

    key_ideas = next(
        component for component in scene.components
        if isinstance(component, ExampleBlock)
        and component.component_id == "classroom-summary/key-ideas"
    )
    next_class = next(
        component for component in scene.components
        if isinstance(component, ExampleBlock)
        and component.component_id == "classroom-summary/next-class"
    )
    assert "Equal wholes" in key_ideas.content
    assert state.plan.units[0].title in next_class.content


@pytest.mark.asyncio
async def test_answer_question_generation_receives_the_exact_open_question_and_teacher_state():
    captured = {}

    async def generate(_system, payload, _schema):
        captured.update(payload)
        return LearningTurn(
            speech="The denominator tells how many equal parts share the same whole.",
            board_title="Denominator",
            board_content="Same whole: more equal parts means each part is smaller.",
        )

    teacher = AdaptiveTeacher(generate=generate)
    state = state_for_class()
    state.open_question = "Why does a bigger denominator make each equal piece smaller?"
    state.learner_signals = ["learner_question"]
    state.board_memory = [{"title": "Equal wholes", "content": "Start by checking the wholes match."}]

    turn = await teacher.turn(context(), state, "answer_question", state.open_question)

    assert turn.task is None
    assert captured["open_question"] == state.open_question
    assert captured["teaching_strategy"] == "direct_answer"
    assert captured["learner_signals"] == ["learner_question"]
    assert captured["board_memory"][0]["title"] == "Equal wholes"


@pytest.mark.asyncio
async def test_fast_start_warms_the_validated_unit_only_after_the_immediate_move():
    ctx = context()
    state = state_for_class()
    state.skill_ids = [str(uuid4()), str(uuid4())]
    state.identity_required = True
    cache = object()
    teacher = AdaptiveTeacher(package_cache=cache, fast_start=True)
    key = package_key(ctx, state.unit, state.skill_ids[0])
    assert key is not None

    warmed_package = object()
    teacher.build_package = AsyncMock(return_value=warmed_package)
    teacher._fast_cache_misses.add(key.cache_key)

    teacher.schedule_package_prefetch(ctx, state, state.unit)
    task = teacher._package_prefetch_tasks[key.cache_key]
    await task

    assert teacher.build_package.await_count == 1
    assert teacher._prefetched_packages[key.cache_key] is warmed_package
    assert key.cache_key not in teacher._fast_cache_misses


@pytest.mark.asyncio
async def test_late_stage_practice_warms_exactly_one_next_unit():
    ctx = context()
    state = state_for_class()
    state.skill_ids = [str(uuid4()), str(uuid4())]
    state.identity_required = True
    teacher = AdaptiveTeacher(package_cache=object(), fast_start=True)

    next_unit = state.plan.units[1]
    next_key = package_key(ctx, next_unit, state.skill_ids[1])
    assert next_key is not None

    warmed = object()
    teacher.build_package = AsyncMock(return_value=warmed)
    teacher.schedule_next_unit_prefetch(ctx, state, "independent")

    assert list(teacher._package_prefetch_tasks) == [next_key.cache_key]
    await teacher._package_prefetch_tasks[next_key.cache_key]
    assert teacher.build_package.await_count == 1
    assert teacher.build_package.await_args.args[1] == next_unit
    assert teacher._prefetched_packages[next_key.cache_key] is warmed


@pytest.mark.asyncio
async def test_early_practice_does_not_spend_next_unit_generation():
    ctx = context()
    state = state_for_class()
    state.skill_ids = [str(uuid4()), str(uuid4())]
    state.identity_required = True
    teacher = AdaptiveTeacher(package_cache=object(), fast_start=True)
    teacher.build_package = AsyncMock()

    teacher.schedule_next_unit_prefetch(ctx, state, "guided")
    await __import__("asyncio").sleep(0)

    teacher.build_package.assert_not_awaited()
    assert teacher._package_prefetch_tasks == {}
