"""Behavioral contracts for the production guided-classroom pathway."""

import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, CriterionResult, Evaluation, GuidedState, LearningPlan,
    LearningTask, LearningTurn, PendingTask, TeachingUnavailable,
    requests_help, unit_count, validate_evaluation,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
from lyo_app.ai_classroom.sdui_models import ActionIntent, InputField, QuizCard, Scene, TeacherMessage
from tests.adaptive_fixtures import ScriptedTeacher, action, context, engine, evaluation, plan, task


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch):
    _SESSION_PROGRESS.clear()
    # An accidentally un-injected test must fail closed, never hit a provider.
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion",
                        AsyncMock(side_effect=AssertionError("Live model calls are forbidden in these tests")))
    yield
    _SESSION_PROGRESS.clear()


async def start():
    teacher = ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context()
    scene = await runner.run(ctx, progress, action(welcome=True))
    return teacher, runner, progress, ctx, scene


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


async def answer(runner, progress, ctx, response="One half: fewer cuts make larger pieces.", option="a"):
    pending = state(progress).pending
    intent = ActionIntent.SUBMIT_ANSWER if pending.task.kind == "choose" else ActionIntent.SUBMIT_TRANSFER
    return await runner.run(ctx, progress, action(intent, pending.id,
        answer_data={"selected_option_id": option, "response": response}))


@pytest.mark.asyncio
async def test_topic_session_is_not_completed_by_one_quiz_and_one_written_answer():
    teacher, runner, progress, ctx, scene = await start()
    assert len(state(progress).plan.units) == 3
    assert ctx.total_lessons == 0
    await answer(runner, progress, ctx)
    await answer(runner, progress, ctx)
    current = state(progress)
    assert current.completed == [0]
    assert current.unit_done and not current.path_done
    await runner.run(ctx, progress, action())
    assert state(progress).unit_index == 1
    assert teacher.turn.await_args.args[1].unit.title == "Fraction skill 2"


@pytest.mark.asyncio
async def test_full_path_requires_evidence_for_each_unit_and_ends_with_review():
    _, runner, progress, ctx, _ = await start()
    for index in range(3):
        await answer(runner, progress, ctx)
        scene = await answer(runner, progress, ctx)
        if index < 2:
            await runner.run(ctx, progress, action())
    assert state(progress).completed == [0, 1, 2]
    assert state(progress).path_done
    assert any(getattr(c, "action_intent", None) == ActionIntent.REQUEST_REVIEW for c in scene.components)
    assert "not a mastery claim" in " ".join(c.text for c in scene.components if isinstance(c, TeacherMessage))


@pytest.mark.asyncio
async def test_partial_answer_gets_one_targeted_follow_up_and_keeps_previous_reasoning():
    teacher, runner, progress, ctx, _ = await start()
    await answer(runner, progress, ctx)
    teacher.evaluate.return_value = evaluation("partial", feedback="One half is the larger piece.",
                                              follow_up="Why does cutting the same pizza fewer times make a bigger piece?")
    scene = await answer(runner, progress, ctx, "One half")
    partial = state(progress)
    assert partial.pending.answers == ["One half"]
    assert len(partial.outbox) == 1  # Only the earlier choice, not a partial failure.
    assert "Why does cutting" in next(c.question for c in scene.components if isinstance(c, InputField))
    assert any("One half" in getattr(c, "content", "") for c in scene.components)
    unchanged = await runner.run(ctx, progress, action())
    assert "Why does cutting" in next(c.question for c in unchanged.components if isinstance(c, InputField))
    teacher.evaluate.return_value = evaluation()
    await answer(runner, progress, ctx, "Fewer cuts make bigger pieces")
    assert teacher.evaluate.await_args.args[1].answers == ["One half", "Fewer cuts make bigger pieces"]
    assert not state(progress).unit_done  # Supported success still needs an independent check.
    assert teacher.turn.await_args.args[2] == "independent"


@pytest.mark.asyncio
async def test_incorrect_answer_gets_different_example_then_a_fresh_check():
    teacher, runner, progress, ctx, first = await start()
    original = state(progress).pending.id
    scene = await answer(runner, progress, ctx, option="b")
    assert teacher.turn.await_args.args[2] == "reteach"
    assert state(progress).pending.id != original
    assert state(progress).outbox[0]["correct"] is False
    assert state(progress).pending.assisted
    assert state(progress).pending.hint_level == "full_example"
    assert not any(isinstance(c, QuizCard) for c in scene.components)


@pytest.mark.asyncio
async def test_help_and_skip_are_not_wrong_answers_and_skip_can_be_revisited():
    _, runner, progress, ctx, _ = await start()
    await runner.run(ctx, progress, action(ActionIntent.REQUEST_HINT, state(progress).pending.id))
    assert not state(progress).outbox
    for _ in range(3):
        await runner.run(ctx, progress, action(ActionIntent.SKIP_QUESTION, state(progress).pending.id))
        if not state(progress).path_done:
            await runner.run(ctx, progress, action())
    assert state(progress).completed == [] and state(progress).skipped == [0, 1, 2]
    await runner.run(ctx, progress, action(ActionIntent.REQUEST_REVIEW))
    assert state(progress).unit_index == 0 and not state(progress).path_done
    await answer(runner, progress, ctx)
    await answer(runner, progress, ctx)
    assert state(progress).skipped == [1, 2]


@pytest.mark.asyncio
async def test_resume_restores_identical_scene_and_question_without_new_generation():
    teacher, runner, progress, ctx, _ = await start()
    await answer(runner, progress, ctx)
    teacher.evaluate.return_value = evaluation("partial", follow_up="What makes the equal piece larger?")
    before = await answer(runner, progress, ctx, "One half")
    restored_progress = json.loads(json.dumps(progress))
    offline_teacher = ScriptedTeacher()
    after = await AdaptiveSession(offline_teacher).run(ctx, restored_progress, action(welcome=True))
    assert after.model_dump(mode="json") == before.model_dump(mode="json")
    assert state(restored_progress).pending.answers == ["One half"]
    offline_teacher.plan.assert_not_awaited()
    offline_teacher.turn.assert_not_awaited()
    offline_teacher.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_or_stale_answer_cannot_grade_another_checkpoint():
    teacher, runner, progress, ctx, _ = await start()
    old_id = state(progress).pending.id
    next_scene = await answer(runner, progress, ctx)
    duplicate = await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, old_id,
        answer_data={"selected_option_id": "b", "is_correct": True}))
    assert duplicate.scene_id == next_scene.scene_id
    assert len(state(progress).outbox) == 1
    teacher.evaluate.assert_not_awaited()
    await runner.run(ctx, progress, action(ActionIntent.SUBMIT_TRANSFER, "someone-elses-question",
                                        answer_data={"response": "2"}))
    teacher.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluator_outage_keeps_answer_ungraded_and_retry_reuses_it():
    teacher, runner, progress, ctx, _ = await start()
    await answer(runner, progress, ctx)
    teacher.evaluate.return_value = evaluation("unavailable", confidence=0)
    scene = await answer(runner, progress, ctx, "One half")
    assert state(progress).pending.retry_response == "One half"
    assert len(state(progress).outbox) == 1
    assert "not graded" in json.dumps(scene.model_dump(mode="json"))
    teacher.evaluate.return_value = evaluation()
    await runner.run(ctx, progress, action(ActionIntent.RETRY))
    assert teacher.evaluate.await_args.args[-1] == "One half"
    assert len(state(progress).outbox) == 2


@pytest.mark.asyncio
async def test_generation_outage_after_grading_never_regrades_the_answer():
    teacher, runner, progress, ctx, _ = await start()
    teacher.turn.side_effect = TeachingUnavailable("offline")
    await answer(runner, progress, ctx)
    assert state(progress).next_move == "independent"
    assert len(state(progress).outbox) == 1
    teacher.turn.side_effect = teacher._turn
    await runner.run(ctx, progress, action(ActionIntent.RETRY))
    assert teacher.turn.await_args.args[2] == "independent"
    assert len(state(progress).outbox) == 1


@pytest.mark.asyncio
async def test_provider_outage_does_not_invent_a_generic_quiz():
    teacher = ScriptedTeacher()
    teacher.plan.side_effect = TeachingUnavailable("offline")
    scene = await AdaptiveSession(teacher).run(context(), {}, action())
    assert not any(isinstance(c, (QuizCard, InputField)) for c in scene.components)
    assert any(getattr(c, "action_intent", None) == ActionIntent.RETRY for c in scene.components)


@pytest.mark.asyncio
async def test_questions_keep_existing_client_types_and_allow_short_answers():
    _, runner, progress, ctx, _ = await start()
    scene = await answer(runner, progress, ctx)
    wire = json.dumps(scene.model_dump(mode="json"))
    assert "example_answer" not in wire and '"criteria"' not in wire
    field = next(c for c in scene.components if isinstance(c, InputField))
    assert field.min_words == 1 and field.expected_keywords == []
    assert "give one reason" in field.question  # Expectations remain visible while typing.
    assert Scene.model_validate_json(wire).scene_id == scene.scene_id


@pytest.mark.parametrize("minutes,authored,expected", [(3,0,3),(10,0,3),(20,0,4),(60,0,6),(10,5,2),(60,1,4)])
def test_time_budget_shapes_scope_not_forced_pacing(minutes, authored, expected):
    assert unit_count(minutes, authored) == expected


@pytest.mark.parametrize("response", ["idk", "I don't know", "No sé", "Can you help me?"])
@pytest.mark.asyncio
async def test_uncertainty_is_a_request_for_teaching(response):
    generate = AsyncMock()
    teacher = AdaptiveTeacher(generate)
    pending = PendingTask(task=task(), speech="Equal parts of the same whole.", board_title="Equal parts", board_content="Compare 1/2 and 1/3.")
    result = await teacher.evaluate(context(), pending, response)
    assert result.verdict == "clarify"
    generate.assert_not_awaited()


def test_substantive_reasoning_containing_uncertainty_is_not_discarded():
    assert not requests_help("I was confused but half is larger because there are fewer pieces.")


@pytest.mark.asyncio
async def test_semantic_evaluator_uses_question_prior_answers_and_accepts_paraphrase():
    pending = PendingTask(task=task(), speech="Fewer cuts make each equal part bigger.", board_title="Equal parts",
                          board_content="Halves versus thirds.", answers=["One half"], follow_up="Why is that piece larger?")
    generate = AsyncMock(return_value=evaluation(criteria=[
        CriterionResult(index=0, met=True, quote="One half"),
        CriterionResult(index=1, met=True, quote="fewer slices"),
    ]))
    result = await AdaptiveTeacher(generate).evaluate(context(), pending, "There are fewer slices of the same pizza.")
    assert result.verdict == "correct"
    payload = generate.await_args.args[1]
    assert payload["previous_answers"] == ["One half"]
    assert payload["follow_up_asked"] == "Why is that piece larger?"
    assert "expected_keywords" not in payload["task"]


@pytest.mark.asyncio
async def test_a_correct_number_is_not_rejected_for_word_count():
    numeric = task().model_copy(update={"criteria": ["Gives the result 2"], "question": "How many halves make one pizza?"})
    pending = PendingTask(task=numeric, speech="Two halves make one whole.", board_title="Halves", board_content="1/2 + 1/2 = 1")
    generate = AsyncMock(return_value=evaluation(criteria=[CriterionResult(index=0, met=True, quote="2")]))
    result = await AdaptiveTeacher(generate).evaluate(context(), pending, "2")
    assert result.verdict == "correct"


@pytest.mark.parametrize("invalid", [
    evaluation(criteria=[CriterionResult(index=0, met=True, quote="invented"), CriterionResult(index=1, met=True, quote="invented")]),
    evaluation(criteria=[CriterionResult(index=0, met=True, quote="half")]),
    evaluation(confidence=0.3),
    evaluation(criteria=[CriterionResult(index=0, met=True, quote="half"), CriterionResult(index=1, met=False, quote="")]),
])
@pytest.mark.asyncio
async def test_unreliable_grading_never_becomes_a_wrong_answer(invalid):
    generate = AsyncMock(return_value=invalid)
    pending = PendingTask(task=task(), speech="Equal parts of one whole.", board_title="Halves", board_content="Compare pieces.")
    result = await AdaptiveTeacher(generate).evaluate(context(), pending, "half")
    assert result.verdict == "unavailable"


@pytest.mark.asyncio
async def test_unclear_task_or_hidden_expectation_is_rephrased_not_failed():
    generate = AsyncMock(return_value=evaluation("incorrect", question_clear=False,
                                                feedback="The question did not ask you to explain the reason."))
    pending = PendingTask(task=task(), speech="Equal pieces make one whole.", board_title="Equal pieces", board_content="Compare two pieces.")
    result = await AdaptiveTeacher(generate).evaluate(context(), pending, "half")
    assert result.verdict == "clarify"


@pytest.mark.parametrize("vague", ["Explain the concept in your own words.", "Apply fractions to a new situation.", "Explica el concepto con tus palabras."])
def test_broad_explain_the_concept_templates_are_rejected(vague):
    with pytest.raises(ValueError):
        LearningTask.model_validate({**task().model_dump(), "question": vague})


@pytest.mark.asyncio
async def test_planner_uses_authored_material_time_goal_level_and_language():
    generate = AsyncMock(return_value=plan(2))
    ctx = context(total_lessons=4, lesson_title="Fracciones", lesson_content="Dos mitades forman una unidad.",
                  language_code="es-ES", target_duration_minutes=20)
    await AdaptiveTeacher(generate).plan(ctx)
    payload = generate.await_args.args[1]
    assert payload["material"] == ctx.lesson_content
    assert payload["language"] == "es-ES" and payload["unit_count"] == 2
    assert payload["target_minutes"] == 20


@pytest.mark.asyncio
async def test_engine_serializes_duplicate_submissions_and_saves_before_evidence():
    instance = engine()
    events = []
    async def persisted(*args, **kwargs):
        events.append("saved")
        return True
    async def recorded(**kwargs):
        assert events[-1] == "saved"
        events.append("evidence")
        return True
    instance._persist_session_progress.side_effect = persisted
    instance._record_adaptive_evidence = AsyncMock(side_effect=recorded)
    await instance.process_trigger(action(welcome=True))
    pending_id = state(_SESSION_PROGRESS[session_progress_key("42", "fractions")]).pending.id
    await asyncio.gather(*[instance.handle_quiz_submission("42", "fractions", pending_id, "a") for _ in range(2)])
    instance._record_adaptive_evidence.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_failure_never_emits_evidence_or_promises_resume():
    instance = engine()
    instance._record_adaptive_evidence = AsyncMock(return_value=True)
    await instance.process_trigger(action(welcome=True))
    pending_id = state(_SESSION_PROGRESS[session_progress_key("42", "fractions")]).pending.id
    instance._persist_session_progress.return_value = False
    scene = await instance.handle_quiz_submission("42", "fractions", pending_id, "a")
    instance._record_adaptive_evidence.assert_not_awaited()
    assert "has not synced" in " ".join(c.text for c in scene.components if isinstance(c, TeacherMessage))
    assert any("has not synced" in getattr(c, "content", "") for c in scene.components)
    assert any(getattr(c, "action_intent", None) == ActionIntent.RETRY for c in scene.components)
    instance._persist_session_progress.return_value = True
    await instance.process_trigger(action(welcome=True))
    instance._record_adaptive_evidence.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_topic_is_isolated_by_authenticated_learner():
    first, second = engine(), engine(context(user_id="43"))
    await first.process_trigger(action(welcome=True))
    other = action(welcome=True).model_copy(update={"user_id": "43"})
    await second.process_trigger(other)
    key1, key2 = session_progress_key("42", "fractions"), session_progress_key("43", "fractions")
    assert state(_SESSION_PROGRESS[key1]).pending.id != state(_SESSION_PROGRESS[key2]).pending.id
    assert first.get_session_context("fractions", "43") is None


@pytest.mark.asyncio
async def test_owner_mismatch_cannot_restore_another_learners_answer():
    _, runner, progress, ctx, _ = await start()
    with pytest.raises(ValueError, match="owner mismatch"):
        await runner.run(context(user_id="99"), progress, action(welcome=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["message", "text", "question"])
async def test_learner_questions_from_each_client_reach_the_teacher(field):
    teacher, runner, progress, ctx, _ = await start()
    await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, **{field: "Why must the pizzas be identical?"}))
    assert teacher.turn.await_args.args[2:] == ("answer_question", "Why must the pizzas be identical?")
    assert state(progress).completed == []
    assert not state(progress).outbox


@pytest.mark.asyncio
async def test_a_finished_step_still_answers_the_learners_question():
    teacher, runner, progress, ctx, _ = await start()
    await answer(runner, progress, ctx)
    await answer(runner, progress, ctx)
    assert state(progress).unit_done
    await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, message="What if the pizzas are different sizes?"))
    assert teacher.turn.await_args.args[2:] == ("answer_question", "What if the pizzas are different sizes?")
    assert state(progress).completed == [0]
