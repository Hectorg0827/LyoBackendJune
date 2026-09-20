"""Exercise the real JSON/provider boundary, not a pre-validated mock turn."""

import json
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, TeachingUnavailable, turn_schema,
)
from tests.adaptive_fixtures import ScriptedTeacher, context, plan


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
        {"content": expected.model_dump_json(), "model_used": "gemini-2.5-flash"},
    ])
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    actual = await AdaptiveTeacher().turn(ctx, state, move)
    assert actual.model_dump() == expected.model_dump()
    assert completion.await_count == 2
    initial, repair = [call.kwargs for call in completion.await_args_list]
    assert initial["provider_order"] == ["gpt-4o-mini", "gemini-2.5-flash"]
    assert repair["provider_order"] == ["gemini-2.5-flash", "gpt-4o-mini"]
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
        {"content": '{"goal":"echoed input"}', "model_used": "gemini-2.5-flash"},
        {"content": valid.model_dump_json(), "model": "gpt-4o-mini"},
    ])
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    turn = await AdaptiveTeacher().turn(ctx, state, "orient")
    assert turn.model_dump() == valid.model_dump()
    initial, repair = [call.kwargs for call in completion.await_args_list]
    assert initial["provider_order"] == ["gpt-4o-mini", "gemini-2.5-flash"]
    assert repair["provider_order"] == ["gpt-4o-mini", "gemini-2.5-flash"]
    sent = json.loads(repair["messages"][1]["content"])
    assert "_rejected_provider" not in sent


@pytest.mark.asyncio
async def test_empty_demonstration_is_repaired_before_the_turn_can_reach_the_student(monkeypatch):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    valid = ScriptedTeacher()._turn(ctx, state, "orient")
    missing_steps = valid.model_dump()
    missing_steps["demonstration"] = []
    completion = AsyncMock(side_effect=[
        {"content": json.dumps(missing_steps), "model": "gpt-4o-mini"},
        {"content": valid.model_dump_json(), "model_used": "gemini-2.5-flash"},
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
