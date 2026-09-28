"""An open transfer rung and one earlier-skill revisit within later practice."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    GuidedState, LearningTurn, TransferPracticeTurn,
)
from lyo_app.ai_classroom.sdui_models import ActionIntent, InputField
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, evaluation, tap_probe,
)


def current(progress):
    return GuidedState.model_validate(progress["guided_state"])


async def answer(runner, progress, ctx):
    pending = current(progress).pending
    intent = (ActionIntent.SUBMIT_ANSWER if pending.task.response_format == "choice"
              else ActionIntent.SUBMIT_TRANSFER)
    return await runner.run(ctx, progress, action(intent, pending.id, answer_data={
        "selected_option_id": "a", "response": "The shorter cut makes a bigger piece.",
    }))


async def first_unit(runner, progress, ctx):
    await runner.run(ctx, progress, action(welcome=True, record_scope="unit"))
    await tap_probe(runner, progress, ctx)
    for _ in range(8):
        if current(progress).unit_done:
            break
        await advance_to_task(runner, progress, ctx)
        await answer(runner, progress, ctx)
    assert current(progress).unit_done


def test_transfer_and_revisit_contract_demand_an_open_application():
    teacher, ctx = ScriptedTeacher(), context()
    state = GuidedState(owner="42", plan=teacher.plan.side_effect(ctx))
    for move in ("transfer", "interleave"):
        turn = teacher._turn(ctx, state, move)
        assert TransferPracticeTurn.model_validate(turn.model_dump()).task.kind == "apply"
        with pytest.raises(ValidationError):
            TransferPracticeTurn.model_validate(
                turn.model_copy(update={"task": teacher._turn(ctx, state, "guided").task}).model_dump())


@pytest.mark.asyncio
async def test_transfer_is_earned_only_after_open_correct_answer_and_does_not_gate_completion():
    teacher, runner, progress, ctx = ScriptedTeacher(), None, {}, context(target_duration_minutes=8)
    runner = AdaptiveSession(teacher)
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    for _ in range(4):
        await answer(runner, progress, ctx)
    state = current(progress)
    assert state.phase == "transfer" and state.completed == [0] and not state.path_done
    assert [e["evidence_type"] for e in state.outbox if e["correct"]] == [None, "explanation", "explanation", "application"]
    scene = await answer(runner, progress, ctx)
    assert current(progress).path_done
    assert current(progress).outbox[-1]["evidence_type"] == "transfer"
    assert current(progress).review_outbox[0]["passed"] is True

    # A fresh unit can close on the independent success even when the novel
    # setting is missed; the original application still belongs to the learner.
    teacher, runner, progress = ScriptedTeacher(), None, {}
    runner = AdaptiveSession(teacher)
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    for _ in range(4):
        await answer(runner, progress, ctx)
    teacher.evaluate.return_value = evaluation("incorrect", misconception="Transfer gap")
    await answer(runner, progress, ctx)
    state = current(progress)
    assert state.path_done and state.completed == [0]
    assert state.outbox[-1]["correct"] is False
    assert not any(e["evidence_type"] == "transfer" and e["correct"] for e in state.outbox)
    assert state.review_outbox[0]["passed"] is True


@pytest.mark.asyncio
async def test_interleave_keeps_earlier_identity_and_resumes_current_ladder_after_reconnect():
    teacher, ctx, progress = ScriptedTeacher(), context(), {}
    runner = AdaptiveSession(teacher)
    await first_unit(runner, progress, ctx)
    await runner.run(ctx, progress, action())
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)  # guided, then explain
    scene = await answer(runner, progress, ctx)  # explain, then earlier skill
    state = current(progress)
    assert state.phase == "interleave" and state.active_review_index == 0
    assert state.review_return_phase == "faded" and state.unit_index == 1
    assert next(c for c in scene.components if isinstance(c, InputField)).concept_id == "Fraction skill 1"
    assert not state.review_is_due

    progress["guided_state"] = json.loads(json.dumps(progress["guided_state"]))
    restored = current(progress)
    teacher.evaluate.return_value = evaluation("incorrect", misconception="Revisit gap")
    await answer(runner, progress, ctx)
    state = current(progress)
    assert state.phase == "faded" and state.unit_index == 1
    assert state.completed == [0] and state.interleaved_units == [0]
    assert state.outbox[-1]["concept_id"] == "Fraction skill 1"
    assert state.outbox[-1]["correct"] is False
    assert state.active_review_index is None
    assert restored.pending.id in state.handled


@pytest.mark.asyncio
async def test_only_a_spaced_due_revisit_can_file_retention():
    teacher, ctx, progress = ScriptedTeacher(), context(scheduled_due_items=["fraction_skill_1"]), {}
    runner = AdaptiveSession(teacher)
    await first_unit(runner, progress, ctx)
    await runner.run(ctx, progress, action())
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)
    await answer(runner, progress, ctx)
    assert current(progress).phase == "interleave"
    assert not current(progress).review_is_due  # due at entry, taught again today
    await answer(runner, progress, ctx)
    assert current(progress).outbox[-1]["evidence_type"] == "application"

    teacher, ctx, progress = ScriptedTeacher(), context(), {}
    runner = AdaptiveSession(teacher)
    await first_unit(runner, progress, ctx)
    progress["guided_state"]["review_history"][0]["decided_at"] = (
        datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    ctx.scheduled_due_items = ["fraction_skill_1"]
    await runner.run(ctx, progress, action())
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)
    await answer(runner, progress, ctx)
    assert current(progress).review_is_due
    await answer(runner, progress, ctx)
    assert current(progress).outbox[-1]["evidence_type"] == "retrieval"
