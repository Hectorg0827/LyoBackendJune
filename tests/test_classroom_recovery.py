"""Production authoring limits and recovery at the first guided checkpoint."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningTurn, TeachingUnavailable
from lyo_app.ai_classroom.scene_lifecycle_engine import ContextAssembler, SceneLifecycleEngine
from lyo_app.ai_classroom.sdui_models import ActionIntent, CTAButton, ExampleBlock, QuizCard, Scene, TeacherMessage
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual
from lyo_app.classroom.models import ClassroomInteraction, ClassroomSession
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, decline_probe, evaluation, plan,
)


def current(progress):
    return GuidedState.model_validate(progress["guided_state"])


def retry(scene):
    button = next(c for c in scene.components if isinstance(c, CTAButton) and c.action_intent == ActionIntent.RETRY)
    return action(ActionIntent.RETRY, button.component_id)


async def final_example(teacher):
    """Open a session, pass on its diagnostic, and walk the modelled example to its end.

    Recovery is about what happens to work already done, so every test here
    starts from a learner who has been taught something. Declining the opening
    probe is the route that reaches the teaching.
    """
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(target_duration_minutes=8)
    await runner.run(ctx, progress, action(welcome=True))
    await decline_probe(runner, progress, ctx)
    scene = Scene.model_validate(current(progress).scene)
    while current(progress).beat_index + 1 < len(current(progress).presentation.demonstration):
        scene = await runner.run(ctx, progress, action(component_id=current(progress).step_id))
    return runner, progress, ctx, scene


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["feedback", "title", "visual_description"])
@pytest.mark.parametrize("language", ["en-US", "es-ES"])
async def test_valid_authored_guided_question_always_reaches_the_learner(boundary, language):
    teacher = ScriptedTeacher()
    authored = []

    def bounded_turn(ctx, state, move, learner_input=""):
        turn = teacher._turn(ctx, state, move, learner_input)
        if move == "guided":
            if boundary == "feedback":
                turn.task.options[0].feedback = ("Compare the equal parts of the same whole carefully. " * 5)[:250]
                turn.task.options[1].feedback = ("More equal cuts produce smaller pieces of the same whole. " * 5)[:250]
            elif boundary == "title":
                turn.board_title = "Compare equal parts and explain how their size depends on the number of cuts".ljust(100, ".")
            else:
                turn.board_content = ("Compare the equal pieces of the same whole. " * 25)[:1000]
                turn.visual = TeachingVisual(kind="fraction_bar", title="Equal pieces", parts=4, value=1,
                    caption="Shade a piece and compare it with the remaining pieces.",
                    description=("Four equal pieces make one whole. " * 20)[:600])
            # These must be genuinely valid authoring objects, not unchecked
            # model_copy updates that would never survive production decoding.
            turn = LearningTurn.model_validate_json(turn.model_dump_json())
            authored.append(turn)
        return turn

    teacher.turn.side_effect = bounded_turn
    runner, progress, ctx, _ = await final_example(teacher)
    ctx.language_code = language
    scene = await runner.run(ctx, progress, action(component_id=current(progress).step_id))
    card = next(c for c in scene.components if isinstance(c, QuizCard))
    assert current(progress).pending.id == card.component_id
    assert current(progress).phase == "guided"
    assert current(progress).outbox == [] and current(progress).completed == []
    assert Scene.model_validate_json(scene.model_dump_json()) == scene
    if boundary == "feedback":
        assert card.options[0].feedback_correct == authored[0].task.options[0].feedback
        assert card.options[1].feedback_incorrect == authored[0].task.options[1].feedback
    elif boundary == "title":
        examples = [c for c in scene.components if isinstance(c, ExampleBlock)]
        assert all(len(c.title) <= 100 for c in examples)
        assert examples[0].title.startswith("Hagámoslo juntos" if language.startswith("es") else "Let's do it together")
    else:
        content = "\n".join(c.content for c in scene.components if isinstance(c, ExampleBlock))
        assert authored[0].board_content in content and authored[0].visual.description in content


@pytest.mark.asyncio
async def test_failed_guided_transition_survives_database_restart_and_retry():
    teacher = ScriptedTeacher()
    runner, progress, ctx, before = await final_example(teacher)
    worked_example = next(c.content for c in before.components if isinstance(c, ExampleBlock))
    teacher.turn.side_effect = TeachingUnavailable("provider temporarily unavailable")
    failed = await runner.run(ctx, progress, action(component_id=current(progress).step_id))
    assert worked_example in "\n".join(c.content for c in failed.components if isinstance(c, ExampleBlock))
    assert current(progress).next_move == "guided"
    assert current(progress).pending is None and not current(progress).completed
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(ClassroomSession.__table__.create)
            await connection.run_sync(ClassroomInteraction.__table__.create)
        async with AsyncSession(database) as db:
            persistence = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
            persistence.db = db
            assert await persistence._persist_session_progress(retry(failed), ctx, progress, record_interaction=False)
        async with AsyncSession(database) as db:
            restored = await ContextAssembler(db)._load_persisted_session_progress(action(welcome=True))
        recovered_teacher = ScriptedTeacher()
        recovered = AdaptiveSession(recovered_teacher)
        assert await recovered.run(ctx, restored, action(welcome=True)) == failed
        recovered_teacher.turn.assert_not_awaited()
        question = await recovered.run(ctx, restored, retry(failed))
        assert any(isinstance(c, QuizCard) for c in question.components)
        assert recovered_teacher.turn.await_args.args[2] == "guided"
        assert not current(restored).outbox and not current(restored).completed
        # A delayed duplicate retry must not replace the recovered question.
        assert await recovered.run(ctx, restored, retry(failed)) == question
        assert recovered_teacher.turn.await_count == 1
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_scene_validation_failure_keeps_accepted_evidence_and_retries_the_next_move(monkeypatch):
    teacher = ScriptedTeacher()
    runner, progress, ctx, _ = await final_example(teacher)
    await advance_to_task(runner, progress, ctx)
    pending = current(progress).pending

    def rendering_failure(*args, **kwargs):
        # Inject an unforeseen wire validation error after a real answer has
        # been accepted. The new question must not replace the recovery state.
        raise ValidationError.from_exception_data("Scene", [{
            "type": "string_too_long", "loc": ("components", 2, "content"),
            "input": "private teaching content", "ctx": {"max_length": 1500},
        }])

    monkeypatch.setattr(runner, "checkpoint", rendering_failure)
    failed = await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending.id,
        answer_data={"selected_option_id": "a"}))
    assert current(progress).next_move == "faded"
    assert [event["event_id"] for event in current(progress).outbox] == [pending.id]
    restored = json.loads(json.dumps(progress))
    recovered_teacher = ScriptedTeacher()
    recovered = AdaptiveSession(recovered_teacher)
    scene = await recovered.run(ctx, restored, retry(failed))
    assert current(restored).pending.phase == "faded"
    assert recovered_teacher.turn.await_args.args[2] == "faded"
    assert [event["event_id"] for event in current(restored).outbox] == [pending.id]
    duplicate = await recovered.run(ctx, restored, action(ActionIntent.SUBMIT_ANSWER, pending.id,
        answer_data={"selected_option_id": "a"}))
    assert duplicate == scene
    recovered_teacher.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_of_interrupted_question_keeps_the_question_and_returns_to_the_example():
    teacher = ScriptedTeacher()
    runner, progress, ctx, _ = await final_example(teacher)
    before = current(progress)
    teacher.turn.side_effect = TeachingUnavailable("temporary failure")
    question = "Why do both pizzas need to be the same size?"
    failed = await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, "ask", message=question))
    restored = json.loads(json.dumps(progress))
    recovered_teacher = ScriptedTeacher()
    recovered = AdaptiveSession(recovered_teacher)
    scene = await recovered.run(ctx, restored, retry(failed))
    assert recovered_teacher.turn.await_args.args[2:] == ("answer_question", question)
    assert current(restored).paused_presentation
    await recovered.run(ctx, restored, action(component_id=current(restored).step_id))
    assert current(restored).presentation == before.presentation
    assert current(restored).beat_index == before.beat_index
    assert current(restored).outbox == []
    assert scene.scene_id != failed.scene_id


@pytest.mark.asyncio
@pytest.mark.parametrize("response_format", ["choice", "completion"])
@pytest.mark.parametrize("language", ["en-US", "es-ES"])
async def test_wrong_answer_is_visible_and_explained_before_another_supported_attempt(response_format, language):
    teacher = ScriptedTeacher()
    teaching_inputs = []
    response = "One third" if language == "en-US" else "Un tercio"
    feedback = ("More equal cuts make smaller pieces, not bigger ones." if language == "en-US" else
                "Al hacer más cortes iguales, cada trozo es más pequeño, no más grande.")

    def authored(*args):
        if args[2] == "reteach":
            teaching_inputs.append((args[1].model_copy(deep=True), *args[2:]))
        turn = teacher._turn(*args)
        if turn.task and turn.task.response_format == "choice":
            turn.task.options[1].label = response
            turn.task.options[1].feedback = feedback
            turn.task.options[1].misconception = "More pieces means bigger pieces"
            if response_format == "completion":
                turn.task.options = []
                turn.task.response_format = response_format
        return turn

    teacher.turn.side_effect = authored
    teacher.evaluate.return_value = evaluation("incorrect", feedback=feedback,
                                              misconception="More pieces means bigger pieces")
    runner, progress, ctx, _ = await final_example(teacher)
    ctx.language_code = language
    await advance_to_task(runner, progress, ctx)
    pending = current(progress).pending
    submit = action(ActionIntent.SUBMIT_ANSWER, pending.id, answer_data={"selected_option_id": "b"}) if response_format == "choice" else action(
        ActionIntent.SUBMIT_TRANSFER, pending.id, answer_data={"response": response})
    scene = await runner.run(ctx, progress, submit)
    visible = "\n".join(c.content for c in scene.components if isinstance(c, ExampleBlock))
    assert response in visible and feedback in visible  # Available with sound off.
    assert not any(isinstance(c, QuizCard) for c in scene.components)
    assert current(progress).pending is None
    teaching_state, move, learner_input = teaching_inputs[-1]
    assert move == "reteach" and learner_input == response
    assert teaching_state.pending.answers == [response]
    assert teaching_state.pending.task == pending.task and teaching_state.last_feedback == feedback
    # Reload and a duplicate submission must keep the same explanation.
    restored = json.loads(json.dumps(progress))
    assert await runner.run(ctx, restored, action(welcome=True)) == scene
    assert await runner.run(ctx, restored, submit) == scene
    await advance_to_task(runner, restored, ctx)
    assert current(restored).pending.phase == "guided"
    assert current(restored).pending.id != pending.id
    assert len(current(restored).outbox) == 1 and not current(restored).outbox[0]["correct"]
    assert not current(restored).completed


@pytest.mark.asyncio
async def test_repeated_difficulty_allows_progress_and_returns_to_teaching_on_review():
    teacher = ScriptedTeacher()
    teacher.plan.side_effect = None
    teacher.plan.return_value = plan(2)
    runner, progress, ctx, _ = await final_example(teacher)
    await advance_to_task(runner, progress, ctx)
    for _ in range(2):
        pending = current(progress).pending
        await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending.id,
                                             answer_data={"selected_option_id": "b"}))
        await advance_to_task(runner, progress, ctx)
    assert current(progress).unit_done and current(progress).skipped == [0]
    assert current(progress).completed == [] and not current(progress).independent_application
    # Continuing goes to the next teaching goal without inventing success, and
    # that goal opens by finding out where the learner is rather than lecturing.
    await runner.run(ctx, progress, action(component_id=current(progress).step_id))
    assert current(progress).unit_index == 1 and current(progress).phase == "diagnose"
    assert not current(progress).diagnosed
    await decline_probe(runner, progress, ctx)
    await advance_to_task(runner, progress, ctx)
    pending = current(progress).pending
    await runner.run(ctx, progress, action(ActionIntent.SKIP_QUESTION, pending.id))
    assert current(progress).path_done and current(progress).skipped == [0, 1]
    reviewed = await runner.run(ctx, progress, action(ActionIntent.REQUEST_REVIEW, current(progress).step_id))
    assert current(progress).unit_index == 0 and current(progress).phase == "orient"
    assert current(progress).presentation and not current(progress).pending
    assert not current(progress).challenge_requested and not current(progress).completed
    assert not any(isinstance(c, QuizCard) for c in reviewed.components)
    assert all(not event["correct"] for event in current(progress).outbox)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en-US", "es-ES"])
async def test_a_generation_failure_is_shown_to_the_learner_but_never_spoken_by_the_teacher(language):
    """The teacher keeps teaching; the screen carries the failure and the retry.

    A learner on a bad connection used to hear "I couldn't prepare the next
    step" from their teacher, repeatedly — the most-heard line in the product,
    and an apology for the backend in the voice of the person teaching them.

    The failure still has to be visible: it is what the Retry control is for,
    and hiding it would leave a learner pressing Continue at a screen that has
    stopped moving. So it goes where product notices go, on the board next to
    the control, while the teacher goes on teaching from the material the
    session already holds.
    """
    teacher = ScriptedTeacher()
    runner, progress, ctx, _ = await final_example(teacher)
    ctx.language_code = language
    teacher.turn.side_effect = TeachingUnavailable("providers down")

    scene = await runner.run(ctx, progress, action(component_id=current(progress).step_id))

    spoken = " ".join(c.text for c in scene.components if isinstance(c, TeacherMessage))
    board = " ".join(getattr(c, "content", "") for c in scene.components)
    notice = "no se cargó" if language.startswith("es") else "didn't load"
    paused = "pausa" if language.startswith("es") else "paused"

    # Visible, actionable, and on the board.
    assert notice in board and paused in board
    assert any(getattr(c, "action_intent", None) == ActionIntent.RETRY for c in scene.components)

    # Not in the teacher's voice, in either language.
    assert notice not in spoken and paused not in spoken
    for apology in ("couldn't prepare", "No pude preparar", "doesn't count as a wrong answer"):
        assert apology not in spoken

    # The teacher is still teaching: the unit, and the material already taught.
    assert spoken.strip()
    assert current(progress).unit.title in spoken or "idea" in spoken.lower()

    # Nothing was graded, lost, or claimed by the failure.
    assert current(progress).outbox == [] and not current(progress).completed
