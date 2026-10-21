"""Malformed optional diagrams must not discard a valid authored checkpoint."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, TeachingUnavailable,
)
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual
from tests.adaptive_fixtures import ScriptedTeacher, context, plan


VISUAL = {
    "kind": "process_flow",
    "title": "Follow the process",
    "caption": "Follow the two steps already described on the board.",
    "description": "First observe the system, then compare what changed.",
    "entries": [
        {"label": "Observe", "detail": "Observe the starting system."},
        {"label": "Compare", "detail": "Compare the system after the change."},
    ],
}
PRIVATE = "private-learner-answer-not-for-logs"
MALFORMED_VISUALS = [
    pytest.param({k: v for k, v in VISUAL.items() if k != "title"}, id="missing-title"),
    pytest.param({**VISUAL, "entries": []}, id="invalid-process"),
    pytest.param({**VISUAL, "kind": "fraction_pie", "parts": 2, "value": 3}, id="invalid-fraction"),
    pytest.param({**VISUAL, "kind": "graph", "expression": "__import__('os')"}, id="invalid-graph"),
    pytest.param({**VISUAL, "kind": "annotated_image", "image_query": "a leaf",
                  "image_url": "https://untrusted.example/leaf.jpg"}, id="untrusted-image"),
    pytest.param(PRIVATE, id="wrong-type"),
    pytest.param({**VISUAL, PRIVATE: PRIVATE}, id="private-extra-key"),
]


def provider(monkeypatch, payload):
    completion = AsyncMock(return_value={
        "content": json.dumps(payload), "model_used": "gpt-4o-mini",
    })
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    return completion


def teaching_content(turn):
    return turn.model_dump(exclude={
        "visual": True, "demonstration": {"__all__": {"visual": True}},
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en-US", "es-ES"])
@pytest.mark.parametrize("visual", MALFORMED_VISUALS)
async def test_bad_visual_preserves_the_real_guided_task_without_a_model_retry(monkeypatch, caplog,
                                                                             language, visual):
    ctx = context(language_code=language, target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    authored = ScriptedTeacher()._turn(ctx, state, "guided")
    payload = authored.model_dump()
    payload["visual"] = deepcopy(visual)
    completion = provider(monkeypatch, payload)

    actual = await AdaptiveTeacher().turn(ctx, state, "guided")

    assert teaching_content(actual) == teaching_content(authored)
    assert actual.visual is None
    assert completion.await_count == 1
    assert not state.pending and not state.completed and not state.outbox
    assert PRIVATE not in caplog.text
    assert "untrusted.example" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("visual", MALFORMED_VISUALS[:2])
async def test_nested_bad_visual_keeps_every_paced_beat_and_valid_sibling_visual(monkeypatch, visual):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    authored = ScriptedTeacher()._turn(ctx, state, "orient")
    payload = authored.model_dump()
    valid = TeachingVisual.model_validate(VISUAL)
    payload["visual"] = valid.model_dump()
    payload["demonstration"][0]["visual"] = deepcopy(visual)
    payload["demonstration"][1]["visual"] = valid.model_dump()
    completion = provider(monkeypatch, payload)

    actual = await AdaptiveTeacher().turn(ctx, state, "orient")

    assert teaching_content(actual) == teaching_content(authored)
    assert actual.visual == actual.demonstration[1].visual == valid
    # The existing fallback is grounded in the authored 1/2, not the bad visual.
    fallback = actual.demonstration[0].visual
    assert fallback.kind == "fraction_pie"
    assert (fallback.value, fallback.parts) == (1, 2)
    state.presentation = actual
    restored = GuidedState.model_validate_json(state.model_dump_json())
    # Saved sessions intentionally use the compatible base LearningTurn type.
    assert restored.presentation.model_dump() == actual.model_dump()
    assert completion.await_count == 1


@pytest.mark.asyncio
async def test_bad_visual_uses_only_the_existing_authored_numbered_step_fallback(monkeypatch):
    ctx = context(topic="Observe a system", target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    authored = ScriptedTeacher()._turn(ctx, state, "guided")
    authored.board_content = "1. Observe the starting system\n2. Compare the system after the change"
    payload = authored.model_dump()
    payload["visual"] = {**VISUAL, "entries": []}
    completion = provider(monkeypatch, payload)

    actual = await AdaptiveTeacher().turn(ctx, state, "guided")

    assert teaching_content(actual) == teaching_content(authored)
    assert actual.visual.kind == "process_flow"
    assert [item.detail for item in actual.visual.entries] == [
        "Observe the starting system", "Compare the system after the change",
    ]
    assert completion.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["missing-task", "criteria", "answer-key", "speech", "extra-mastery"])
async def test_optional_visual_recovery_never_accepts_invalid_teaching_or_grading(monkeypatch, defect):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    payload = ScriptedTeacher()._turn(ctx, state, "guided").model_dump()
    payload["visual"] = {**VISUAL, "entries": []}
    if defect == "missing-task":
        del payload["task"]
    elif defect == "criteria":
        payload["task"]["criteria"] = []
    elif defect == "answer-key":
        payload["task"]["options"][1]["correct"] = True
    elif defect == "speech":
        payload["speech"] = ""
    else:
        payload["mastered"] = True
    completion = provider(monkeypatch, payload)

    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher().turn(ctx, state, "guided")

    assert completion.await_count == 2
    assert not state.pending and not state.completed and not state.outbox


@pytest.mark.asyncio
async def test_visual_recovery_still_requires_independent_semantic_acceptance(monkeypatch):
    ctx = context(target_duration_minutes=8)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    payload = ScriptedTeacher()._turn(ctx, state, "guided").model_dump()
    payload["visual"] = {**VISUAL, "entries": []}
    completion = provider(monkeypatch, payload)
    judge = AsyncMock(return_value=False)

    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher(semantic_judge=judge).turn(ctx, state, "guided")

    assert completion.await_count == judge.await_count == 2
    assert not state.pending and not state.completed and not state.outbox


def test_the_visual_contract_itself_still_rejects_untrusted_or_invalid_diagrams():
    with pytest.raises(ValidationError):
        TeachingVisual.model_validate({**VISUAL, "entries": []})
    with pytest.raises(ValidationError):
        TeachingVisual.model_validate({**VISUAL, "kind": "annotated_image", "image_query": "leaf",
                                       "image_url": "https://untrusted.example/leaf.jpg"})
