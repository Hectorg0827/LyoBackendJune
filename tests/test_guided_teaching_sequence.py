"""Learner journeys through modelling, support, exploration and safe resumption."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import AdaptiveTeacher, GuidedState, LearningUnit, PendingTask, TeachingUnavailable
from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
from lyo_app.ai_classroom.sdui_models import ActionIntent, CTAButton, InputField, QuizCard
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual
from tests.adaptive_fixtures import ScriptedTeacher, action, advance_to_task, context, engine, evaluation, plan


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


def fraction_visual():
    return TeachingVisual(kind="fraction_bar", title="Equal parts of one bar",
        caption="Move the slider to shade parts. The size of the whole stays the same.",
        description="One 12 cm bar has four equal parts. Each part is 3 cm long.",
        parts=4, whole=12, unit="cm", value=1)


async def begin(teacher=None):
    teacher = teacher or ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(target_duration_minutes=8)
    scene = await runner.run(ctx, progress, action(welcome=True))
    return teacher, runner, progress, ctx, scene


async def respond(runner, progress, ctx, option="a"):
    pending = state(progress).pending
    if pending.task.response_format == "choice":
        return await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending.id,
            answer_data={"selected_option_id": option}))
    return await runner.run(ctx, progress, action(ActionIntent.SUBMIT_TRANSFER, pending.id,
        answer_data={"response": "Half. Equal cuts of the same whole make larger pieces when there are fewer cuts."}))


@pytest.mark.asyncio
async def test_first_visit_models_a_complete_example_before_any_question_and_double_taps_do_not_skip():
    teacher, runner, progress, ctx, opening = await begin()
    assert not any(isinstance(c, (InputField, QuizCard)) for c in opening.components)
    assert state(progress).phase == "orient" and state(progress).pending is None
    for index in range(2):
        tap = action(component_id=state(progress).step_id)
        scene = await runner.run(ctx, progress, tap)
        assert state(progress).beat_index == index
        assert state(progress).phase == "model" and state(progress).pending is None
        assert not any(isinstance(c, (InputField, QuizCard)) for c in scene.components)
        replay = await runner.run(ctx, progress, tap)
        assert replay == scene and state(progress).beat_index == index
    assert teacher.turn.await_count == 1  # No new content generation is needed for each prepared beat.
    scene = await runner.run(ctx, progress, action(component_id=state(progress).step_id))
    assert state(progress).phase == "guided"
    assert any(isinstance(c, QuizCard) for c in scene.components)
    assert not any(isinstance(c, InputField) for c in scene.components)
    teacher.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_mid_example_retains_pacing_without_generating_or_grading():
    _, runner, progress, ctx, _ = await begin()
    expected = await runner.run(ctx, progress, action(component_id=state(progress).step_id))
    restored = json.loads(json.dumps(progress))
    unavailable_teacher = ScriptedTeacher()
    unavailable_teacher.turn.side_effect = TeachingUnavailable("offline")
    actual = await AdaptiveSession(unavailable_teacher).run(ctx, restored, action(welcome=True))
    assert actual == expected and state(restored).beat_index == 0
    unavailable_teacher.plan.assert_not_awaited()
    unavailable_teacher.turn.assert_not_awaited()
    unavailable_teacher.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_questions_can_interrupt_and_return_to_the_exact_worked_step():
    _, runner, progress, ctx, _ = await begin()
    await runner.run(ctx, progress, action(component_id=state(progress).step_id))
    before = state(progress)
    await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, "ask", message="Why must the wholes match?"))
    await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, "ask", message="Can the shapes differ?"))
    detour = state(progress)
    assert detour.pending is None and detour.paused_presentation
    await runner.run(ctx, progress, action(component_id=detour.step_id))
    after = state(progress)
    assert after.phase == before.phase and after.beat_index == before.beat_index
    assert after.presentation == before.presentation
    assert not after.paused_presentation and not after.outbox


@pytest.mark.asyncio
async def test_readiness_covers_each_component_skill_with_faded_support_before_independence():
    teacher = ScriptedTeacher()
    curriculum = plan(1)
    curriculum.units[0].practice_targets = ["Compare equal-sized wholes", "Relate number of equal cuts to piece size"]
    teacher.plan.side_effect = None
    teacher.plan.return_value = curriculum
    _, runner, progress, ctx, _ = await begin(teacher)
    await advance_to_task(runner, progress, ctx)
    for phase, target in [("guided", 0), ("faded", 0), ("guided", 1), ("faded", 1), ("independent", 1)]:
        pending = state(progress).pending
        assert (pending.phase, pending.task.target_index) == (phase, target)
        assert state(progress).completed == []
        await respond(runner, progress, ctx)
    # What this pins is the phase and target sequence, above. It used to also
    # assert the exact response_format at each step — but format is no longer
    # decided by the phase, so that list only ever reflected what the scripted
    # teacher happened to return, not anything the production code enforced.
    # The demand is still fixed where it matters: independent practice is an
    # application problem, which `test_independent_practice_demands_application`
    # holds separately.
    assert state(progress).completed == [0] and state(progress).path_done
    assert len(state(progress).practice_events) == 5


@pytest.mark.asyncio
async def test_extra_help_keeps_question_but_requires_a_fresh_faded_attempt():
    _, runner, progress, ctx, _ = await begin()
    await advance_to_task(runner, progress, ctx)
    await respond(runner, progress, ctx)
    before = state(progress).pending
    await runner.run(ctx, progress, action(ActionIntent.REQUEST_HINT, "hint"))
    await advance_to_task(runner, progress, ctx)
    assisted = state(progress).pending
    assert assisted.id == before.id and assisted.task == before.task
    assert assisted.extra_help_used
    await respond(runner, progress, ctx)
    assert state(progress).phase == "faded" and state(progress).faded_targets == []
    assert state(progress).pending.id != before.id
    await respond(runner, progress, ctx)
    assert state(progress).phase == "independent" and state(progress).completed == []


@pytest.mark.asyncio
async def test_struggle_reteaches_then_checks_a_prerequisite_without_a_peer_or_difficulty_jump():
    teacher, runner, progress, ctx, _ = await begin()
    await advance_to_task(runner, progress, ctx)
    for move in ("reteach", "prerequisite"):
        old_question = state(progress).pending.task.scenario
        scene = await respond(runner, progress, ctx, option="b")
        assert teacher.turn.await_args.args[2] == move
        assert state(progress).pending is None
        assert not any(isinstance(c, (InputField, QuizCard)) for c in scene.components)
        await advance_to_task(runner, progress, ctx)
        assert state(progress).pending.task.scenario != old_question
        assert state(progress).phase == "guided"
    assert state(progress).completed == []
    assert state(progress).unit.objective == "Compare equal parts of the same whole."


@pytest.mark.asyncio
async def test_visual_manipulation_persists_with_same_scene_and_creates_no_evidence():
    teacher = ScriptedTeacher()
    def visual_turn(*args):
        return teacher._turn(*args).model_copy(update={"visual": fraction_visual()})
    teacher.turn.side_effect = visual_turn
    _, runner, progress, ctx, opening = await begin(teacher)
    before = state(progress)
    visual_id = "visual:" + before.step_id
    updated = await runner.run(ctx, progress, action(ActionIntent.UPDATE_ACTIVITY, visual_id, answer_data={"value": 3}))
    assert updated.scene_id == opening.scene_id
    assert state(progress).presentation.visual.value == 3
    assert state(progress).step_id == before.step_id and state(progress).beat_index == -1
    assert state(progress).pending is None and state(progress).outbox == [] and state(progress).practice_events == []
    assert [c.component_id for c in updated.components] == [c.component_id for c in opening.components]
    restored = json.loads(json.dumps(progress))
    replay = await AdaptiveSession(ScriptedTeacher()).run(ctx, restored, action(welcome=True))
    assert replay == updated
    teacher.evaluate.assert_not_awaited()
    # Stale controls from a previous beat cannot change the current activity.
    await runner.run(ctx, progress, action(component_id=state(progress).step_id))
    snapshot = deepcopy(progress)
    await runner.run(ctx, progress, action(ActionIntent.UPDATE_ACTIVITY, visual_id, answer_data={"value": 2}))
    assert progress == snapshot


@pytest.mark.asyncio
async def test_visual_save_uses_existing_persistence_without_replaying_audio_or_recording_an_attempt():
    _SESSION_PROGRESS.clear()
    instance = engine(context(target_duration_minutes=8))
    teacher = instance.adaptive_teacher
    teacher.turn.side_effect = lambda *args: teacher._turn(*args).model_copy(update={"visual": fraction_visual()})
    instance.websocket_manager = SimpleNamespace(stream_scene_to_session=AsyncMock())
    await instance.process_trigger(action(welcome=True))
    instance.websocket_manager.stream_scene_to_session.reset_mock()
    progress = _SESSION_PROGRESS[session_progress_key("42", "fractions")]
    await instance.process_trigger(action(ActionIntent.UPDATE_ACTIVITY, "visual:" + state(progress).step_id, answer_data={"value": 2}))
    assert state(progress).presentation.visual.value == 2
    instance.websocket_manager.stream_scene_to_session.assert_not_awaited()
    assert instance._persist_session_progress.await_args.kwargs["record_interaction"] is False
    _SESSION_PROGRESS.clear()


@pytest.mark.parametrize("payload", [{"value": -1}, {"value": 5}, {"value": True}, {"value": 1.5}, {"value": "2"}, [], {"params": {}}])
def test_visual_rejects_invalid_updates_without_changing_current_value(payload):
    visual = fraction_visual()
    assert not visual.update(payload) and visual.value == 1


def graph(**updates):
    return TeachingVisual(kind="graph", title="See how slope changes", caption="Increase a and observe the steepness.",
        description="The line y = a times x passes through the origin. Increasing a makes it steeper.",
        params=[{"name": "a", "min": -3, "max": 3, "initial": 1}], **{"expression": "a*x", **updates})


def test_graph_keeps_axes_fixed_and_resumes_parameters_without_a_grade():
    visual = graph()
    assert visual.update({"params": {"a": 2}})
    restored = TeachingVisual.model_validate_json(visual.model_dump_json())
    assert restored.params[0].initial == 2
    assert (restored.y_min, restored.y_max) == (-10, 10)
    for params in ({"a": 4}, {"a": True}, {"a": float("nan")}, {"b": 1}, {"a": 1, "b": 2}):
        assert not restored.update({"params": params})
    assert restored.params[0].initial == 2


@pytest.mark.parametrize("expression", ["a*", "unknown*x", "a(x)", "sin(x, a)", "x.__class__", "x // a"])
def test_malformed_graphs_are_rejected_before_delivery(expression):
    with pytest.raises(ValidationError):
        graph(expression=expression)


@pytest.mark.parametrize("targets", [[" "], ["Same skill", "same skill"], ["x" * 301]])
def test_practice_targets_must_represent_distinct_real_skills(targets):
    with pytest.raises(ValidationError):
        LearningUnit(title="Equal wholes", objective="Compare pieces from identical wholes.",
            material="Halves and thirds can be compared when the original pizzas have the same size.", practice_targets=targets)


@pytest.mark.asyncio
async def test_authored_orientation_cannot_sneak_in_a_question_or_skip_the_modelled_example():
    teacher = ScriptedTeacher()
    _, _, progress, ctx, _ = await begin(teacher)
    current = state(progress)
    premature_task = teacher._turn(ctx, current, "guided")
    generate = AsyncMock(return_value=premature_task)
    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher(generate).turn(ctx, current, "orient")
    assert generate.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("weaker_kind", ["choose", "predict", "explain", "diagnose"])
async def test_independent_practice_demands_application(weaker_kind):
    """Independence is about what the question asks, not how it is answered.

    The phase used to also fix the response format — choice while guided,
    typed once faded — which made every checkpoint's shape guessable from the
    phase alone. That is gone, so this is now the whole of what protects the
    bar: whatever format it wears, the last checkpoint before a unit closes
    has to be a fresh application problem, because `kind` is what the
    completion gate reads.
    """
    teacher = ScriptedTeacher()
    _, _, progress, ctx, _ = await begin(teacher)
    current = state(progress)
    turn = teacher._turn(ctx, current, "independent")
    turn.task.kind = weaker_kind
    if weaker_kind != "choose":
        turn.task.options = []
        turn.task.response_format = "short_answer"
    generate = AsyncMock(return_value=turn)
    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher(generate).turn(ctx, current, "independent")


@pytest.mark.asyncio
async def test_an_application_problem_may_be_answered_by_choosing():
    """The format is free even at the bar: a real application problem answered
    from genuine competing candidates is still application."""
    teacher = ScriptedTeacher()
    _, _, progress, ctx, _ = await begin(teacher)
    current = state(progress)
    turn = teacher._turn(ctx, current, "independent")
    assert turn.task.kind == "apply"
    choice = teacher._turn(ctx, current, "guided")
    turn.task.response_format = "choice"
    turn.task.options = choice.task.options
    generate = AsyncMock(return_value=turn)
    accepted = await AdaptiveTeacher(generate).turn(ctx, current, "independent")
    assert accepted.task.kind == "apply"
    assert accepted.task.response_format == "choice"


@pytest.mark.asyncio
async def test_the_closing_question_does_not_ship_its_own_answer():
    """The one checkpoint that decides what the product believes a learner
    can do must not arrive with the answer attached.

    Clients colour a tap instantly from the option's own correctness instead
    of waiting for the server, which is a fair trade during practice. It is
    not a fair trade for the checkpoint whose correct answer banks
    application evidence and closes a unit: anyone who opens the page can
    read the answer, and the record stops meaning anything.

    All three fields have to go together. Android reads a missing
    `is_correct` as a neutral selection, but its feedback lookup falls back
    to `feedback_incorrect`, so leaving the text behind would tell a correct
    learner they were wrong.
    """
    teacher = ScriptedTeacher()
    _, runner, progress, ctx, _ = await begin(teacher)
    state_now = state(progress)
    applied = teacher._turn(ctx, state_now, "independent").task
    choice = teacher._turn(ctx, state_now, "guided").task
    applied.response_format, applied.options = "choice", choice.options
    assert applied.kind == "apply"

    state_now.pending = PendingTask(task=applied, speech="Try this one yourself.",
                                    board_title="Your turn", board_content="A fresh problem.")
    scene = runner.checkpoint(ctx, state_now)
    card = next(c for c in scene.components if isinstance(c, QuizCard))
    assert card.options, "the learner still gets something to choose between"
    for option in card.options:
        assert option.is_correct is None, "the answer key rode along with the question"
        assert option.feedback_correct is None and option.feedback_incorrect is None, (
            "feedback text names the answer just as plainly as the flag does"
        )


def test_a_card_cannot_declare_the_key_for_only_some_of_its_options():
    """Half a key is worse than either whole.

    It leaves the client colouring some taps locally and not others, and on
    the checkpoint that exists to be answered unaided it narrows the answer
    by elimination. Proven load-bearing by deleting the check and watching a
    half-declared card sail through.
    """
    from lyo_app.ai_classroom.sdui_models import QuizOption
    with pytest.raises(ValidationError, match="all declare correctness or all withhold"):
        QuizCard(component_id="q", question="Which piece is larger?", options=[
            QuizOption(id="a", label="One half", is_correct=True),
            QuizOption(id="b", label="One third", is_correct=None),
        ])


@pytest.mark.asyncio
async def test_practice_questions_still_answer_instantly():
    """Withholding the key is scoped to the checkpoint that closes a unit.

    Recognition practice keeps its local colouring: the round-trip it saves
    is worth more there than the answer is worth hiding, and a `choose` task
    never banks application evidence however fluently it is answered.
    """
    teacher = ScriptedTeacher()
    _, runner, progress, ctx, _ = await begin(teacher)
    state_now = state(progress)
    recognition = teacher._turn(ctx, state_now, "guided").task
    assert recognition.response_format == "choice" and recognition.kind != "apply"

    state_now.pending = PendingTask(task=recognition, speech="Which one is larger?",
                                    board_title="Compare", board_content="Same whole, fewer cuts.")
    scene = runner.checkpoint(ctx, state_now)
    card = next(c for c in scene.components if isinstance(c, QuizCard))
    assert any(o.is_correct for o in card.options), "practice still colours a tap locally"
    assert any(o.feedback_correct or o.feedback_incorrect for o in card.options)


@pytest.mark.asyncio
async def test_legacy_pending_question_is_restored_verbatim_but_old_successes_do_not_unlock_independence():
    _, runner, progress, ctx, _ = await begin()
    await advance_to_task(runner, progress, ctx)
    raw = progress["guided_state"]
    raw["version"] = 1
    raw["successes"] = 99
    for name in ("phase", "guided_targets", "faded_targets", "presentation"):
        raw.pop(name, None)
    raw["pending"].pop("phase", None)
    raw["pending"]["task"].pop("response_format", None)
    old_scene = deepcopy(raw["scene"])
    restored = await runner.run(ctx, progress, action(welcome=True))
    assert restored.model_dump(mode="json") == old_scene
    await respond(runner, progress, ctx)
    assert state(progress).phase == "faded" and not state(progress).completed
