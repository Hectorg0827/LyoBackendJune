"""What a question demands and how its answer is collected are separate.

The classroom used to weld the two together: the only multiple-choice kind was
"choose", and only an unassisted "apply" could close a unit. Every unit
therefore ended in a typing task. On a phone that is a real tax — and it buys
nothing, because what makes an application problem rigorous is the thinking it
demands, not the keyboard it is answered on.

These tests hold the two apart in both directions: a demanding question stays
demanding when it is answered by choosing, and recognition stays recognition
however it is answered.
"""

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningTask, TaskOption
from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS
from lyo_app.ai_classroom.sdui_models import ActionIntent, InputField, QuizCard
from tests.adaptive_fixtures import ScriptedTeacher, action, context, evaluation, plan, task
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch):
    _SESSION_PROGRESS.clear()
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion",
                        AsyncMock(side_effect=AssertionError("Live model calls are forbidden in these tests")))
    yield
    _SESSION_PROGRESS.clear()


def choice_options():
    return [
        TaskOption(id="a", label="3/4 of the tank", correct=True,
                   feedback="Three of the four equal parts remain after one is used."),
        TaskOption(id="b", label="1/4 of the tank", correct=False, misconception="Reports the part used, not the part left.",
                   feedback="That is the quarter used up, not the amount still in the tank."),
        TaskOption(id="c", label="4/3 of the tank", correct=False, misconception="Inverts the fraction.",
                   feedback="A tank cannot hold more than all of itself."),
    ]


def applied_choice_task():
    """A genuine application problem whose answer is selected, not typed."""
    return LearningTask(
        kind="apply", response_format="choice",
        scenario="A fuel tank is divided into four equal parts and one part is used on a trip.",
        question="How much fuel is left in the tank?",
        response_hint="Pick the remaining amount.",
        criteria=["Identifies three of four equal parts remain"],
        example_answer="3/4 of the tank.",
        options=choice_options(),
    )


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


# --- the model keeps the two ideas apart -----------------------------------

def test_format_follows_kind_when_the_author_does_not_say():
    # Every task authored before this field existed must behave exactly as it did.
    assert task(kind="apply").response_format == "short_answer"
    assert task(kind="choose").response_format == "choice"
    assert task(kind="explain").response_format == "short_answer"


def test_a_recognition_task_cannot_be_turned_into_a_typing_task():
    # "choose" IS the recognition kind; typing it would change what it measures.
    with pytest.raises(ValueError, match="cannot be answered by typing"):
        LearningTask(**{**applied_choice_task().model_dump(), "kind": "choose",
                        "response_format": "short_answer"})


def test_a_choice_task_needs_options_whatever_its_kind():
    with pytest.raises(ValueError, match="2–4 options"):
        LearningTask(**{**applied_choice_task().model_dump(), "options": []})


def test_choice_options_must_be_genuinely_different():
    duplicated = choice_options()
    duplicated[1].label = "3/4 OF THE TANK"
    with pytest.raises(ValueError, match="genuinely different"):
        LearningTask(**{**applied_choice_task().model_dump(), "options": [o.model_dump() for o in duplicated]})


def test_an_open_task_still_cannot_smuggle_in_options():
    with pytest.raises(ValueError, match="cannot carry choice options"):
        LearningTask(**{**applied_choice_task().model_dump(), "response_format": "short_answer"})


# --- the session honours the format it rendered ----------------------------

@pytest.mark.asyncio
async def test_a_demanding_question_offered_as_choice_is_rendered_and_answerable():
    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context()
    await runner.run(ctx, progress, action(welcome=True))

    current = state(progress)
    current.pending.task = applied_choice_task()
    progress["guided_state"] = current.model_dump(mode="json")

    scene = runner.checkpoint(ctx, state(progress))
    # The learner is shown options, not a text box.
    assert any(isinstance(c, QuizCard) for c in scene.components)
    assert not any(isinstance(c, InputField) for c in scene.components)

    # And the selection they send back is accepted rather than bounced for
    # not having been typed.
    pending_id = state(progress).pending.id
    await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending_id,
                                           answer_data={"selected_option_id": "a"}))
    assert state(progress).successes == 1


@pytest.mark.asyncio
async def test_a_unit_can_be_completed_without_the_learner_typing_anything():
    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context()
    await runner.run(ctx, progress, action(welcome=True))

    for _ in range(4):
        current = state(progress)
        if current.unit_done or current.completed:
            break
        current.pending.task = applied_choice_task()
        progress["guided_state"] = current.model_dump(mode="json")
        await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, state(progress).pending.id,
                                               answer_data={"selected_option_id": "a"}))

    final = state(progress)
    assert final.independent_application, "An applied choice is still independent application"
    assert final.completed == [0], "The unit closed on selected answers alone"


@pytest.mark.asyncio
async def test_recognition_never_closes_a_unit_however_fluently_it_is_answered():
    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context()
    await runner.run(ctx, progress, action(welcome=True))

    for _ in range(4):
        current = state(progress)
        if current.completed:
            break
        current.pending.task = task(kind="choose")
        progress["guided_state"] = current.model_dump(mode="json")
        await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, state(progress).pending.id,
                                               answer_data={"selected_option_id": "a"}))

    final = state(progress)
    assert final.successes >= 2, "The learner answered correctly more than once"
    assert not final.independent_application, "Recognition is not application"
    assert final.completed == [], "Picking right answers repeatedly did not close the unit"


@pytest.mark.asyncio
async def test_help_on_an_applied_choice_still_withholds_independent_credit():
    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context()
    await runner.run(ctx, progress, action(welcome=True))

    current = state(progress)
    current.pending.task = applied_choice_task()
    progress["guided_state"] = current.model_dump(mode="json")

    await runner.run(ctx, progress, action(ActionIntent.REQUEST_HINT, state(progress).pending.id))
    helped = state(progress)
    helped.pending.task = applied_choice_task()
    helped.pending.assisted = True
    progress["guided_state"] = helped.model_dump(mode="json")

    await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, state(progress).pending.id,
                                           answer_data={"selected_option_id": "a"}))
    assert not state(progress).independent_application


@pytest.mark.asyncio
async def test_an_applied_choice_is_banked_as_application_evidence():
    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context()
    await runner.run(ctx, progress, action(welcome=True))

    current = state(progress)
    current.pending.task = applied_choice_task()
    progress["guided_state"] = current.model_dump(mode="json")
    await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, state(progress).pending.id,
                                           answer_data={"selected_option_id": "a"}))

    banked = [e for e in state(progress).outbox if e["evidence_type"]]
    assert banked, "The applied choice produced ladder evidence"
    assert banked[-1]["evidence_type"] == "application"
    assert banked[-1]["correct"] is True
