import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, LearningPlan, LearningUnit, PendingTask,
)
from lyo_app.ai_classroom.equation_practice import recovery_turn, grade_recovery
from lyo_app.ai_classroom.sdui_models import ActionIntent
from lyo_app.ai_classroom.trial_budget import ClassroomTrialBudgetExceeded


def fixture():
    unit = LearningUnit(title="Isolating Variables on One Side of an Equation",
                        objective="Solve and check two-sided equations.",
                        material="Subtract equal terms from both sides before isolating the variable.")
    state = GuidedState(owner="qa", plan=LearningPlan(units=[unit]), phase="faded", next_move="faded",
                        explained=True, guided_targets=[0], unresolved_misconceptions=["target 1: addition"])
    context = SimpleNamespace(user_id="qa", session_id="test", classroom_mode=SimpleNamespace(value="solo"),
                              language_code="en", topic=unit.title, lesson_title="", lesson_content="",
                              learning_objective=unit.objective, preferred_difficulty="intermediate",
                              source_attributions=[], total_lessons=1, lesson_index=0,
                              scheduled_due_items=[], knowledge_states=[])
    teacher = AdaptiveTeacher(generate=AsyncMock(side_effect=ClassroomTrialBudgetExceeded("test limit")))
    return teacher, context, state


def solve(task):
    numbers = list(map(int, re.findall(r"\d+", task.scenario)))
    if task.scenario.startswith("Plan A"):
        constant, a, right, b = numbers
    else:
        a, constant, b, right = numbers
    x, remainder = divmod(right - constant, a - b)
    assert remainder == 0
    return f"{x}, {a * x + constant}"


@pytest.mark.asyncio
async def test_paused_lesson_resumes_grades_and_completes_under_budget_guard():
    teacher, context, state = fixture()
    runner = AdaptiveSession(teacher)
    progress = {}
    runner.save(progress, state, runner.unavailable(context, state))

    async def act(intent=None, component=None, **data):
        # Rehydrate the saved state on every action, as on a reconnect.
        return await runner.run(context, progress, SimpleNamespace(
            component_id=component, action_data=dict(action_intent=intent, **data)))

    scene = await act(welcome=True)
    ids = set()
    for phase in ("faded", "independent", "transfer"):
        pending = PendingTask.model_validate(progress["guided_state"]["pending"])
        assert pending.phase == phase and pending.id not in ids
        ids.add(pending.id)
        assert scene.metadata.scene_source == "template"
        assert solve(pending.task) == pending.task.example_answer
        assert pending.task.example_answer not in scene.model_dump_json()
        if phase == "independent":
            await act(ActionIntent.SUBMIT_TRANSFER, pending.id, answer_data={"response": "my result is written in prose"})
            pending = PendingTask.model_validate(progress["guided_state"]["pending"])
            assert not pending.assisted and pending.retry_response is None
            assert pending.id not in ids and not progress["guided_state"]["completed"]
            scene = await act(welcome=True)
        restored = await act(welcome=True)
        assert restored.scene_id == scene.scene_id
        data = dict(answer_data={"response": solve(pending.task)})
        scene = await act(ActionIntent.SUBMIT_TRANSFER, pending.id, **data)
        saved = json.dumps(progress["guided_state"])
        await act(ActionIntent.SUBMIT_TRANSFER, pending.id, **data)
        assert json.dumps(progress["guided_state"]) == saved
    assert progress["guided_state"]["completed"] == [0]
    assert progress["guided_state"]["path_done"]
    assert not progress["guided_state"]["unresolved_misconceptions"]


@pytest.mark.asyncio
async def test_partial_and_wrong_answers_and_unrelated_units():
    teacher, context, state = fixture()
    turn = await recovery_turn(teacher, context, state, "independent")
    pending = PendingTask(task=turn.task, speech=turn.speech, board_title=turn.board_title,
                          board_content=turn.board_content)
    x = solve(turn.task).split(",")[0]
    assert grade_recovery(pending, f"{x}, -1").verdict == "partial"
    assert grade_recovery(pending, "-1, -1").verdict == "incorrect"
    assert grade_recovery(pending, "I need help") is None
    state.unit.title = "Cell division"
    assert await recovery_turn(teacher, context, state, "independent") is None


@pytest.mark.asyncio
async def test_try_fresh_example_from_skipped_summary_reaches_editable_question():
    teacher, context, state = fixture()
    state.path_done, state.skipped = True, [0]
    runner, progress = AdaptiveSession(teacher), {}
    runner.save(progress, state, runner.summary(context, state))
    intent = ActionIntent.REQUEST_REVIEW
    component_id = state.step_id
    for _ in range(5):
        scene = await runner.run(context, progress, SimpleNamespace(
            component_id=component_id, action_data={"action_intent": intent}))
        saved = progress["guided_state"]
        assert scene.metadata.scene_source == "template"
        assert not saved["completed"]
        if saved["pending"]:
            assert saved["pending"]["phase"] == "guided"
            return
        component_id = saved["step_id"]
        intent = ActionIntent.CONTINUE
    pytest.fail("Fresh example never reached an editable question")


@pytest.mark.asyncio
async def test_equivalent_saved_unit_restores_opening_diagnostic():
    teacher, context, state = fixture()
    state.unit.title = "Collecting Variable Terms in Linear Equations"
    state.next_move = state.phase = "diagnose"
    runner, progress = AdaptiveSession(teacher), {}
    runner.save(progress, state, runner.unavailable(context, state))
    scene = await runner.run(context, progress, SimpleNamespace(component_id=None, action_data={"welcome": True}))
    assert scene.metadata.scene_source == "template"
    pending = PendingTask.model_validate(progress["guided_state"]["pending"])
    assert pending.phase == "diagnose"
    assert len(pending.task.options) == 4 and sum(item.correct for item in pending.task.options) == 1
