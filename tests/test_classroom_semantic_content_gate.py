"""Reject checkable meaning failures and expose a review hook for the rest."""

from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, LearningTask, TeachingUnavailable,
    validate_semantic_content,
)
from tests.adaptive_fixtures import ScriptedTeacher, context, plan, probe, task
from tests.export_guided_fixtures import visuals


@pytest.mark.parametrize("bad_label", ["ONE-HALF!!!", "one half"])
def test_equivalent_visible_options_are_rejected(bad_label):
    choice = task("choose").model_dump()
    choice["options"][1]["label"] = bad_label
    with pytest.raises(ValueError, match="distinct visible answers"):
        LearningTask.model_validate(choice)


def test_two_distractors_cannot_claim_the_same_misconception_under_different_punctuation():
    diagnostic = probe().model_dump()
    diagnostic["options"][2]["misconception"] = "More pieces means MORE each"
    with pytest.raises(ValueError, match="distinct misconceptions"):
        LearningTask.model_validate(diagnostic)


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["board_content", "question", "speech"])
async def test_visible_answer_is_repaired_before_the_probe_is_shown(location):
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    valid = ScriptedTeacher()._turn(ctx, state, "diagnose")
    invalid = valid.model_dump()
    answer = valid.task.options[0].label
    if location == "question":
        invalid["task"]["question"] = f"{answer} is bigger. Which piece is bigger?"
    else:
        invalid[location] = f"{answer} is bigger. Which piece is bigger?"
    generate = AsyncMock(side_effect=[
        type(valid).model_validate(invalid), valid,
    ])
    result = await AdaptiveTeacher(generate).turn(ctx, state, "diagnose")
    assert result.task.question == valid.task.question
    assert generate.await_count == 2
    repair = generate.await_args.args[1]["repair"]
    assert "reveals the answer" in repair and answer not in repair


@pytest.mark.parametrize("location", ["board", "visual"])
def test_visual_description_and_open_answer_are_subject_to_the_same_gate(location):
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "transfer")
    if location == "board":
        turn.board_content = turn.task.example_answer
    else:
        turn.visual = visuals()[1].model_copy(update={"description": turn.task.example_answer})
    with pytest.raises(ValueError, match="reveals the answer"):
        validate_semantic_content(turn)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["filler distractor", "mislabelled gap", "fluent wrong teaching"])
async def test_optional_second_judge_can_reject_meaning_the_schema_cannot_prove(failure):
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    move = "orient" if failure == "fluent wrong teaching" else "diagnose"
    candidate = ScriptedTeacher()._turn(ctx, state, move)
    if failure == "filler distractor":
        candidate.task.options[1].label = "The magical pizza is an elephant"
    elif failure == "mislabelled gap":
        candidate.task.options[1].gap = "near_miss"
    else:
        candidate.demonstration[0].speech = "More equal cuts always produce a larger piece."
    generate = AsyncMock(return_value=candidate)
    judge = AsyncMock(return_value=False)
    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher(generate, semantic_judge=judge).turn(ctx, state, move)
    assert generate.await_count == judge.await_count == 2
    assert judge.await_args.args[0] == move
    assert judge.await_args.args[1].title == state.unit.title
    assert state.completed == [] and state.outbox == []


def test_a_short_numeric_answer_in_the_scenario_is_data_not_answer_leakage():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "faded")
    turn.task.example_answer = "4"
    turn.board_content = "Four equal cuts in the first bar and eight in the second."
    validate_semantic_content(turn)
