"""Once per unit, the learner says why it works.

Whether a learner ever explained anything used to depend on which response
format the generator happened to pick. A unit could be finished having only
chosen between prepared candidates and filled in a final step — and putting the
reason into your own words is the part that makes a skill portable, so leaving
it to chance left the most valuable question in the lesson unasked.

It is asked after their first success, when they have something to explain and
have just been shown they can do it. These tests hold three things about it: it
happens, it is not a gate, and it does not quietly become a rung on the
scaffolding ladder.
"""

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    ExplanationPracticeTurn, GuidedState, TeachingBeat, turn_schema)
from lyo_app.ai_classroom.sdui_models import ActionIntent, ClassroomMode, InputField
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, evaluation, explanation, probe, tap_probe)


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


async def open_session(teacher=None, minutes=8, **overrides):
    teacher = teacher or ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(target_duration_minutes=minutes, **overrides)
    await runner.run(ctx, progress, action(welcome=True))
    return teacher, runner, progress, ctx


async def answer(runner, progress, ctx, option="a", response="The whole stays the same size, so more pieces means less on each."):
    await advance_to_task(runner, progress, ctx)
    pending = state(progress).pending
    if pending.task.response_format == "choice":
        return await runner.run(ctx, progress, action(
            ActionIntent.SUBMIT_ANSWER, pending.id, answer_data={"selected_option_id": option}))
    return await runner.run(ctx, progress, action(
        ActionIntent.SUBMIT_TRANSFER, pending.id, answer_data={"response": response}))


@pytest.mark.asyncio
async def test_a_first_success_earns_the_question_that_makes_the_skill_portable():
    teacher, runner, progress, ctx = await open_session()
    await tap_probe(runner, progress, ctx)
    assert not state(progress).explained

    scene = await answer(runner, progress, ctx)          # first success
    assert teacher.turn.await_args.args[2] == "explain"
    current = state(progress)
    assert current.pending.task.kind == "explain"
    assert current.pending.task.response_format == "short_answer"
    # Asked in their own words, on the board they were just working on.
    field = next(c for c in scene.components if isinstance(c, InputField))
    assert "own words" in field.question
    assert not current.pending.task.options


@pytest.mark.asyncio
async def test_the_explanation_is_filed_as_an_explanation():
    _, runner, progress, ctx = await open_session()
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)
    await answer(runner, progress, ctx)
    current = state(progress)
    assert current.explained
    # The ladder has an `explanation` rung and it used to be filled by
    # accident, if at all. This is the question that earns it on purpose.
    assert any(event["evidence_type"] == "explanation" for event in current.outbox)


@pytest.mark.asyncio
async def test_it_moves_the_learner_neither_up_nor_down_the_ladder():
    _, runner, progress, ctx = await open_session()
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)
    before = state(progress)
    assert before.pending.task.kind == "explain"
    ladder = (before.phase, before.guided_targets, before.faded_targets, before.successes)

    await answer(runner, progress, ctx)
    after = state(progress)
    assert (after.phase, after.guided_targets, after.faded_targets) == ladder[:3]
    # Practice resumes exactly where it was, at the rung the explanation was
    # asked at.
    assert after.pending.task.kind != "explain"
    assert after.pending.phase == before.pending.phase


@pytest.mark.asyncio
async def test_a_shaky_explanation_is_taught_into_rather_than_failed():
    teacher, runner, progress, ctx = await open_session()
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)
    teacher.evaluate.return_value = evaluation(
        "incorrect", feedback="More equal cuts make each piece smaller, not bigger.",
        misconception="more_pieces_means_more_each")
    await answer(runner, progress, ctx, response="Because three is more than two.")
    current = state(progress)
    # Reteaching, not a verdict on the learner: nothing is marked for review
    # yet and the unit is not over.
    assert teacher.turn.await_args.args[2] == "reteach"
    assert current.skipped == [] and not current.unit_done
    assert current.presentation is not None


@pytest.mark.asyncio
async def test_it_is_asked_once_per_unit_and_again_in_the_next_unit():
    # Three units, so there is a next one to ask again in.
    teacher, runner, progress, ctx = await open_session(minutes=24)
    await tap_probe(runner, progress, ctx)
    for _ in range(5):
        if state(progress).unit_done or state(progress).path_done:
            break
        await answer(runner, progress, ctx)
    assert state(progress).unit_done
    first_unit = [call.args[2] for call in teacher.turn.await_args_list]
    assert first_unit.count("explain") == 1, first_unit

    # A new unit is a new skill, so it asks for its own explanation. Carrying
    # the flag across units would silently retire the question after unit one.
    await runner.run(ctx, progress, action(component_id=state(progress).step_id))
    assert state(progress).unit_index == 1 and not state(progress).explained
    await tap_probe(runner, progress, ctx)
    await answer(runner, progress, ctx)
    assert teacher.turn.await_args.args[2] == "explain"
    assert [c.args[2] for c in teacher.turn.await_args_list].count("explain") == 2


@pytest.mark.asyncio
async def test_a_learner_who_asked_for_a_challenge_is_not_stopped_to_explain():
    # Challenge and review modes are a request to be tested, not taught.
    for mode in (ClassroomMode.CHALLENGE, ClassroomMode.REVIEW):
        teacher, runner, progress, ctx = await open_session(classroom_mode=mode)
        await answer(runner, progress, ctx)
        assert "explain" not in [call.args[2] for call in teacher.turn.await_args_list]


def test_the_contract_refuses_anything_that_is_not_the_learners_own_words():
    beat = dict(speech="You've got it. Now tell me why that works.",
                board_title="Say why it works", board_content="Same whole, more pieces, less on each.")
    assert turn_schema("explain") is ExplanationPracticeTurn
    good = explanation()
    assert ExplanationPracticeTurn(**beat, task=good).task.kind == "explain"

    # A tap cannot be an explanation, and neither can a checkpoint that is
    # really an application problem wearing the move's name.
    with pytest.raises(ValueError):
        ExplanationPracticeTurn(**beat, task=good.model_copy(update={"kind": "apply"}))
    with pytest.raises(ValueError):
        ExplanationPracticeTurn(**beat, task=probe())
    with pytest.raises(ValueError):
        ExplanationPracticeTurn(**beat, task=good.model_copy(update={"response_format": "completion"}))
    # And it is a question, not a lecture with a question attached.
    with pytest.raises(ValueError):
        ExplanationPracticeTurn(**beat, task=good, demonstration=[TeachingBeat(**beat)])


def test_the_question_may_not_be_a_request_to_explain_the_concept_in_general():
    # `LearningTask` already refuses this shape, and an explanation is exactly
    # where a generator is most tempted by it.
    with pytest.raises(ValueError):
        explanation().model_copy(update={}, deep=True).__class__(
            kind="explain", response_format="short_answer",
            scenario="Fractions describe equal parts of one whole, which matters here.",
            question="Explain this concept in your own words.",
            response_hint="Two or three sentences.",
            criteria=["Explains it"], example_answer="It is about equal parts.")
