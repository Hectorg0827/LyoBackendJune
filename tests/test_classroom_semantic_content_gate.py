"""Reject checkable meaning failures and expose a review hook for the rest."""

from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, LearningTask, TeachingContractError,
    TeachingUnavailable, validate_semantic_content,
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


def test_a_short_numeric_answer_may_not_be_stated_by_the_teacher_before_answering():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "guided")
    turn.task.example_answer = "24"
    turn.task.scenario = "Compare 3/8 and 5/12 by using a common denominator."
    turn.board_content = "The least common denominator is 24."
    with pytest.raises(TeachingContractError, match="short answer"):
        validate_semantic_content(turn)


def test_a_short_fraction_answer_may_not_be_stated_by_the_teacher_before_answering():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "guided")
    turn.task.example_answer = "3/4"
    turn.task.scenario = "Compare 2/5 and 3/4."
    turn.board_content = "After conversion, 3/4 is larger."
    with pytest.raises(TeachingContractError, match="short answer"):
        validate_semantic_content(turn)


# ─── The hint is shown, so the hint is checked ───────────────────────────────

def test_the_response_hint_may_not_work_the_answer_out():
    """`response_hint` reaches the learner twice and was not being checked.

    `InputField` appends it to the question *and* uses it as the placeholder,
    so a hint that states the answer gives it away exactly as the board would.
    Every other visible field was already covered; this one was missed because
    it reads like internal guidance and is not.
    """
    open_task = task("apply").model_dump()
    open_task["response_hint"] = f"Say {open_task['example_answer']}"
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "guided")
    bad = turn.model_copy(update={"task": LearningTask.model_validate(open_task)})
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(bad)


def test_a_hint_that_only_says_how_to_answer_is_still_fine():
    """The check must not make hints useless — it targets the answer, not help."""
    open_task = task("apply").model_dump()
    open_task["response_hint"] = "Name the larger piece and say why."
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "guided")
    validate_semantic_content(turn.model_copy(
        update={"task": LearningTask.model_validate(open_task)}))


# ─── Filler options ─────────────────────────────────────────────────────────

def test_two_options_cannot_share_one_piece_of_feedback():
    """Identical feedback is the signature of an option nobody authored.

    A learner who taps a filler distractor is answered with text written about
    a different option — which reads as a teacher who did not look at what
    they chose, and teaches them nothing about their actual mistake.
    """
    choice = task("choose").model_dump()
    choice["options"][1]["feedback"] = choice["options"][0]["feedback"]
    with pytest.raises(ValueError, match="feedback about that option"):
        LearningTask.model_validate(choice)


def test_punctuation_does_not_disguise_duplicated_feedback():
    choice = task("choose").model_dump()
    choice["options"][1]["feedback"] = choice["options"][0]["feedback"].upper() + "!!"
    with pytest.raises(ValueError, match="feedback about that option"):
        LearningTask.model_validate(choice)


def test_a_misconception_that_only_restates_the_option_diagnoses_nothing():
    """The reteaching reads this field. Restating the wrong answer gives it nothing."""
    diagnostic = probe().model_dump()
    label = diagnostic["options"][2]["label"]
    diagnostic["options"][2]["misconception"] = f"They said {label}"
    with pytest.raises(ValueError, match="not repeat the option"):
        LearningTask.model_validate(diagnostic)


@pytest.mark.parametrize("restatement", [
    "They said {label}",
    "{label} is wrong",
    "The learner chose {label} instead",
    "{label}",
])
def test_every_shape_of_restatement_is_caught(restatement):
    diagnostic = probe().model_dump()
    label = diagnostic["options"][2]["label"]
    diagnostic["options"][2]["misconception"] = restatement.format(label=label)
    with pytest.raises(ValueError, match="not repeat the option"):
        LearningTask.model_validate(diagnostic)


@pytest.mark.parametrize("terse", [
    "Counts pieces, ignores size",
    "Inverts numerator and denominator",
    "Adds denominators",          # two words, and a complete diagnosis
    "Cuenta las piezas",          # and it must not be an English-only gate
])
def test_a_terse_but_real_diagnosis_is_accepted(terse):
    """The test is substance, not length, and it was length in the first cut.

    A word count would have rejected "Adds denominators" — a complete
    diagnosis — while accepting "They said 14 rolls", which is none. It would
    also have pushed the generator toward padding this field to clear a bar,
    which is the opposite of what the field is for.
    """
    diagnostic = probe().model_dump()
    diagnostic["options"][2]["misconception"] = terse
    assert LearningTask.model_validate(diagnostic).options[2].misconception == terse


def test_ordinary_practice_may_still_leave_a_misconception_unset():
    """Only probes are required to diagnose; practice options may not need to."""
    choice = task("choose").model_dump()
    for option in choice["options"]:
        option["misconception"] = None
        option["gap"] = None
    assert LearningTask.model_validate(choice).options
