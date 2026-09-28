"""Operational counters compare opening predictions to the learner's work."""

import pytest
from prometheus_client import generate_latest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    GuidedState, classroom_ceiling_comparisons, classroom_diagnostics,
    classroom_teaching_turns, classroom_unit_outcomes,
)
from lyo_app.ai_classroom.sdui_models import ActionIntent
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, tap_probe,
)


async def answer(runner, progress, ctx, option="a"):
    pending = GuidedState.model_validate(progress["guided_state"]).pending
    intent = (ActionIntent.SUBMIT_ANSWER if pending.task.response_format == "choice"
              else ActionIntent.SUBMIT_TRANSFER)
    return await runner.run(ctx, progress, action(intent, pending.id,
        answer_data={"selected_option_id": option, "response": "The smaller share comes from more equal cuts."}))


def value(counter, *labels):
    return counter.labels(*labels)._value.get()


@pytest.mark.asyncio
async def test_ceiling_is_confirmed_per_skill_once_then_completion_is_counted_once():
    runner, ctx, progress = AdaptiveSession(ScriptedTeacher()), context(target_duration_minutes=8), {}
    before = value(classroom_ceiling_comparisons, "independent", "independent", "confirmed", "tap")
    done = value(classroom_unit_outcomes, "completed")
    probes = value(classroom_diagnostics, "correct")
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx)
    for _ in range(5):
        await answer(runner, progress, ctx)
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.path_done and state.ceiling_assessed
    comparisons = [e for e in state.practice_events if e["kind"] == "ceiling_accuracy"]
    assert len(comparisons) == 1
    assert {k: v for k, v in comparisons[0].items() if k != "at"} == dict(
        kind="ceiling_accuracy", unit=0, predicted="independent",
        observed="independent", result="confirmed", source="tap")
    assert value(classroom_ceiling_comparisons, "independent", "independent", "confirmed", "tap") == before + 1
    assert value(classroom_unit_outcomes, "completed") == done + 1
    assert value(classroom_diagnostics, "correct") == probes + 1
    await runner.run(ctx, progress, action(welcome=True))
    assert value(classroom_unit_outcomes, "completed") == done + 1


@pytest.mark.asyncio
async def test_a_near_miss_ceiling_is_contradicted_by_later_work_without_text_labels():
    runner, ctx, progress = AdaptiveSession(ScriptedTeacher()), context(), {}
    before = value(classroom_ceiling_comparisons, "faded", "none", "contradicted", "tap")
    reteach = value(classroom_teaching_turns, "reteach")
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx, option="c")
    await advance_to_task(runner, progress, ctx)
    await answer(runner, progress, ctx, option="b")
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.diagnostic_ceiling is None and state.ceiling_prediction == "faded"
    assert [e["result"] for e in state.practice_events if e["kind"] == "ceiling_accuracy"] == ["contradicted"]
    assert value(classroom_ceiling_comparisons, "faded", "none", "contradicted", "tap") == before + 1
    assert value(classroom_teaching_turns, "reteach") == reteach + 1
    assert b"more_pieces_means_more_each" not in generate_latest(classroom_ceiling_comparisons)
    assert b"Fraction skill" not in generate_latest(classroom_ceiling_comparisons)


@pytest.mark.asyncio
async def test_abstention_and_unfinished_unit_have_separate_denominators():
    runner, ctx, progress = AdaptiveSession(ScriptedTeacher()), context(), {}
    abstained = value(classroom_diagnostics, "abstained")
    unfinished = value(classroom_unit_outcomes, "needs_practice")
    await runner.run(ctx, progress, action(welcome=True))
    await tap_probe(runner, progress, ctx, option="d")
    assert value(classroom_diagnostics, "abstained") == abstained + 1
    await advance_to_task(runner, progress, ctx)
    pending = GuidedState.model_validate(progress["guided_state"]).pending
    await runner.run(ctx, progress, action(ActionIntent.SKIP_QUESTION, pending.id))
    assert value(classroom_unit_outcomes, "needs_practice") == unfinished + 1
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.completed == [] and not any(e["kind"] == "ceiling_accuracy" for e in state.practice_events)
