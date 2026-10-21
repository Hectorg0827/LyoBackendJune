"""Exercise the real JSON/provider boundary, not a pre-validated mock turn."""

import json
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, CriterionResult, Evaluation, GuidedState, PendingTask,
    TeachingUnavailable, turn_schema,
    validate_authored_turn_with_optional_visual_fallback,
)
from tests.adaptive_fixtures import ScriptedTeacher, context, plan, task


def assert_teaching_content_preserved(actual, authored):
    # The server may supplement a missing visual after repairing the provider
    # response. It must still preserve every authored word, task and beat.
    exclude = {"visual": True, "demonstration": {"__all__": {"visual": True}}}
    assert actual.model_dump(exclude=exclude) == authored.model_dump(exclude=exclude)
    for rendered, original in zip([actual, *actual.demonstration], [authored, *authored.demonstration]):
        if original.visual is not None:
            assert rendered.visual == original.visual
        elif rendered.visual is not None:
            assert rendered.visual.kind == "fraction_pie"
            assert (rendered.visual.value, rendered.visual.parts) == (1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("move", ["orient", "guided", "reteach"])
async def test_wrong_root_object_repairs_with_exact_phase_contract_and_alternate_provider(monkeypatch, move):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    expected = ScriptedTeacher()._turn(ctx, state, move)
    # Production returned input-context keys instead of authored teaching.
    invalid = {"goal": "private learner objective", "target_index": 0}
    completion = AsyncMock(side_effect=[
        {"content": json.dumps(invalid), "model": "gpt-4o-mini"},
        {"content": expected.model_dump_json(), "model_used": "gemini-3.6-flash"},
    ])
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    actual = await AdaptiveTeacher().turn(ctx, state, move)
    assert_teaching_content_preserved(actual, expected)
    if move != "guided":
        assert all(beat.visual is not None for beat in actual.demonstration)
    assert completion.await_count == 2
    initial, repair = [call.kwargs for call in completion.await_args_list]
    assert initial["provider_order"] == ["gpt-4o-mini", "gemini-3.6-flash"]
    assert repair["provider_order"] == ["gemini-3.6-flash", "gpt-4o-mini"]
    assert initial["max_tokens"] == repair["max_tokens"] == 4500
    contract = json.loads(initial["messages"][0]["content"].split("Return only JSON matching this schema:\n")[1])
    assert set(contract["properties"]) == {"speech", "board_title", "board_content", "visual", "task", "demonstration"}
    if move == "guided":
        assert "task" in contract["required"]
        assert contract["properties"]["demonstration"]["maxItems"] == 0
    else:
        assert contract["properties"]["task"]["type"] == "null"
        assert "LearningTask" not in contract.get("$defs", {})
        assert contract["properties"]["demonstration"]["minItems"] == (2 if move == "orient" else 1)
    repair_message = json.loads(repair["messages"][1]["content"])["repair"]
    assert "speech: missing" in repair_message and "board_title: missing" in repair_message
    assert "private learner objective" not in repair_message


@pytest.mark.asyncio
async def test_repair_uses_the_provider_that_did_not_return_the_malformed_content(monkeypatch):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    valid = ScriptedTeacher()._turn(ctx, state, "orient")
    # The resilience layer may skip an unavailable first provider and return
    # malformed content from the second. Routing must follow the actual result,
    # not assume the first name in the requested order answered.
    completion = AsyncMock(side_effect=[
        {"content": '{"goal":"echoed input"}', "model_used": "gemini-3.6-flash"},
        {"content": valid.model_dump_json(), "model": "gpt-4o-mini"},
    ])
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    turn = await AdaptiveTeacher().turn(ctx, state, "orient")
    assert_teaching_content_preserved(turn, valid)
    assert all(beat.visual is not None for beat in turn.demonstration)
    initial, repair = [call.kwargs for call in completion.await_args_list]
    assert initial["provider_order"] == ["gpt-4o-mini", "gemini-3.6-flash"]
    assert repair["provider_order"] == ["gpt-4o-mini", "gemini-3.6-flash"]
    sent = json.loads(repair["messages"][1]["content"])
    assert "_rejected_provider" not in sent


@pytest.mark.asyncio
async def test_rejected_evaluation_tries_stronger_model_before_pausing_class(monkeypatch):
    pending = PendingTask(task=task(), speech="Compare equal wholes.",
                          board_title="Fractions", board_content="Half is larger than a third.")
    invalid = Evaluation(
        verdict="partial", confidence=0.95, question_clear=True,
        feedback="You have identified the first part.", follow_up="Why is it bigger?",
        criteria=[CriterionResult(index=0, met=True, quote="invented"),
                  CriterionResult(index=1, met=False, quote="")],
    )
    repaired = invalid.model_copy(update={
        "criteria": [CriterionResult(index=0, met=True, quote="half"),
                     CriterionResult(index=1, met=False, quote="")]
    })
    completion = AsyncMock(side_effect=[
        {"content": invalid.model_dump_json(), "model_used": "gpt-4o-mini"},
        {"content": repaired.model_dump_json(), "model_used": "gpt-4o"},
    ])
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    result = await AdaptiveTeacher().evaluate(context(), pending, "half")
    assert result.verdict == "partial"
    assert completion.await_count == 2
    assert completion.await_args_list[0].kwargs["provider_order"][0] == "gpt-4o-mini"
    assert completion.await_args_list[1].kwargs["provider_order"][0] == "gpt-4o"


@pytest.mark.asyncio
async def test_empty_demonstration_is_repaired_before_the_turn_can_reach_the_student(monkeypatch):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    valid = ScriptedTeacher()._turn(ctx, state, "orient")
    missing_steps = valid.model_dump()
    missing_steps["demonstration"] = []
    completion = AsyncMock(side_effect=[
        {"content": json.dumps(missing_steps), "model": "gpt-4o-mini"},
        {"content": valid.model_dump_json(), "model_used": "gemini-3.6-flash"},
    ])
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    turn = await AdaptiveTeacher().turn(ctx, state, "orient")
    assert turn.task is None and len(turn.demonstration) >= 2
    repair_message = json.loads(completion.await_args.kwargs["messages"][1]["content"])["repair"]
    assert "demonstration: too_short" in repair_message


@pytest.mark.asyncio
async def test_two_invalid_provider_responses_still_fail_honestly_without_an_invented_question(monkeypatch):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    completion = AsyncMock(return_value={"content": '{"goal":"echoed input"}'})
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher().turn(ctx, state, "guided")
    assert completion.await_count == 2
    assert not state.pending and not state.completed and not state.outbox


def test_saved_sessions_keep_their_existing_contract():
    # Phase-specific constraints are only for newly authored turns. An older
    # saved presentation can still be resumed through the compatible base type.
    ctx = context()
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    saved = ScriptedTeacher()._turn(ctx, state, "help").model_dump()
    assert saved["demonstration"] == []
    state.presentation = saved
    restored = GuidedState.model_validate_json(state.model_dump_json())
    assert restored.presentation.demonstration == []
    assert turn_schema("answer_question").model_validate(saved).task is None


def test_optional_root_visual_missing_title_keeps_assessment_and_learner_text_unchanged():
    ctx = context()
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    authored = ScriptedTeacher()._turn(ctx, state, "guided")
    data = authored.model_dump()
    data["visual"] = {
        "kind": "comparison",
        "caption": "A comparison of the relevant quantities.",
        "description": "Two quantities can be compared side by side.",
        "entries": [],
    }
    result = validate_authored_turn_with_optional_visual_fallback(
        turn_schema("guided"), json.dumps(data),
    )
    assert result.visual is None
    assert result.task == authored.task
    assert result.speech == authored.speech
    assert result.board_title == authored.board_title
    assert result.board_content == authored.board_content
    assert result.demonstration == authored.demonstration


def test_invalid_demonstration_visual_does_not_remove_required_worked_steps():
    ctx = context()
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    authored = ScriptedTeacher()._turn(ctx, state, "orient")
    data = authored.model_dump()
    data["demonstration"][0]["visual"] = {
        "kind": "fraction_pie", "title": "Half and whole",
        "caption": "Two halves make up a complete whole.",
        "description": "A pie with two sections has one section shaded.",
        "parts": 2, "value": 9,
    }
    result = validate_authored_turn_with_optional_visual_fallback(
        turn_schema("orient"), json.dumps(data),
    )
    assert result.demonstration[0].visual is None
    assert len(result.demonstration) == len(authored.demonstration)
    for original, actual in zip(authored.demonstration, result.demonstration):
        assert original.speech == actual.speech
        assert original.board_title == actual.board_title
        assert original.board_content == actual.board_content
    assert result.task is None


def test_mixed_invalid_visual_and_invalid_grading_task_still_fails_closed():
    from pydantic import ValidationError
    ctx = context()
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    data = ScriptedTeacher()._turn(ctx, state, "guided").model_dump()
    data["visual"] = {"kind": "fraction_pie"}
    # An absent task cannot be repaired by removing its optional visual.
    data.pop("task")
    with pytest.raises(ValidationError):
        validate_authored_turn_with_optional_visual_fallback(
            turn_schema("guided"), json.dumps(data),
        )


def test_invalid_required_demonstration_never_passes_as_optional_visual_error():
    from pydantic import ValidationError
    ctx = context()
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    data = ScriptedTeacher()._turn(ctx, state, "orient").model_dump()
    data["demonstration"] = []
    data["visual"] = {"kind": "fraction_pie"}
    with pytest.raises(ValidationError):
        validate_authored_turn_with_optional_visual_fallback(
            turn_schema("orient"), json.dumps(data),
        )


@pytest.mark.asyncio
async def test_provider_invalid_optional_visual_does_not_retry_paid_generation(monkeypatch):
    ctx = context()
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    authored = ScriptedTeacher()._turn(ctx, state, "guided")
    data = authored.model_dump()
    data["visual"] = {
        "kind": "comparison",
        "caption": "A comparison of the quantities.",
        "description": "Two values compared side by side.",
        "entries": [],
    }
    completion = AsyncMock(return_value={
        "content": json.dumps(data),
        "model_used": "gemini-3.8-flash",
        "tokens_used": 1200,
    })
    monkeypatch.setattr(
        "lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion",
        completion,
    )
    turn = await AdaptiveTeacher().turn(ctx, state, "guided")
    assert turn.visual is None
    assert turn.task == authored.task
    assert completion.await_count == 1
