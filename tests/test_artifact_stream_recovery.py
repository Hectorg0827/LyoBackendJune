"""Consume the real Chat SSE path with real executor/mutator behavior.

Only provider and storage boundaries are stubbed. HTTP 200 alone is not a pass:
the production regression returned 200 followed by an error event.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest

from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import ActionType, Intent, LyoPlan, PlannedAction
from lyo_app.services.mutator import FollowUpMutator
from tests.test_voice_turn_lifecycle import event_payload, harness  # noqa: F401


@pytest.fixture
def artifact_stream(harness, monkeypatch):
    from lyo_app.api.v1 import stream_lyo2 as stream

    content = {"title": "Photosynthesis", "cards": [
        {"front": "What captures light?", "back": "Chlorophyll"},
    ]}
    artifact = {"artifact_id": "saved-deck", "user_id": "42", "type": "FLASHCARDS",
                "version": 1, "content": content, "metadata": {}}
    storage = SimpleNamespace(
        get_artifact=AsyncMock(return_value=artifact),
        update_artifact=AsyncMock(return_value={**artifact, "version": 2}),
        create_artifact=AsyncMock(return_value=artifact),
    )
    mutator = FollowUpMutator.__new__(FollowUpMutator)
    mutator.artifacts = storage
    mutator.model_manager = SimpleNamespace(
        generate_with_retry=AsyncMock(return_value='{"title":"Photosynthesis","cards":[{"front":"What captures light?","back":"Chlorophyll"}]}'),
    )
    executor = LyoExecutor.__new__(LyoExecutor)
    executor.artifacts = storage
    executor.mutator = mutator
    executor._generate_text = AsyncMock(return_value="Your deck is ready.")
    plan = LyoPlan(steps=[
        PlannedAction(action_type=ActionType.UPDATE_ARTIFACT, description="Update deck",
                      parameters={"artifact_id": "saved-deck", "instruction": "Add detail"}),
        PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Confirm update"),
    ])
    monkeypatch.setattr(stream, "LyoExecutor", lambda db: executor)
    monkeypatch.setattr(stream.planner_agent, "plan", AsyncMock(return_value=plan))

    async def consume(**overrides):
        params = dict(text="Create detailed photosynthesis flashcards",
                      forced_intent=Intent.FLASHCARDS, state_summary={})
        params.update(overrides)
        response = await harness.response(
            **params,
        )
        assert response.status_code == 200
        events = [event_payload(chunk) async for chunk in response.body_iterator]
        return events

    return SimpleNamespace(consume=consume, storage=storage, mutator=mutator,
                           executor=executor, plan=plan, harness=harness)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["missing_id", "stale", "other_learner", "unowned"])
async def test_unavailable_artifact_finishes_sse_with_honest_recovery(artifact_stream, target):
    control = artifact_stream
    if target == "missing_id":
        control.plan.steps[0].parameters.clear()
    elif target == "stale":
        control.plan.steps[0].parameters["artifact_id"] = "flashcard_photosynthesis_1"
        control.storage.get_artifact.return_value = None
    elif target == "other_learner":
        control.storage.get_artifact.return_value["user_id"] = "99"
    else:
        control.storage.get_artifact.return_value.pop("user_id")

    events = await control.consume()
    assert not [event for event in events if event["type"] == "error"], events
    assert events[-1]["type"] == "DONE"
    assert not [event for event in events if event.get("generation_status") == "incomplete"
                or event["type"] == "voice_incomplete"]
    assert next(event for event in events if event["type"] == "answer")["generation_status"] == "completed"
    assert not [event for event in events if event["type"] == "artifact"]
    answer = next(event for event in events if event["type"] == "answer")["block"]["content"]["text"]
    assert "reopen" in answer.lower()
    assert "new" in answer.lower()
    assert "saved-deck" not in answer and "flashcard_photosynthesis_1" not in answer
    assert "ready" not in answer.lower()
    control.mutator.model_manager.generate_with_retry.assert_not_awaited()
    control.storage.update_artifact.assert_not_awaited()
    control.storage.create_artifact.assert_not_awaited()
    control.executor._generate_text.assert_not_awaited()
    assert [w["content"] for w in control.harness.writes if w["role"] == "assistant"] == [answer]


@pytest.mark.asyncio
async def test_owned_artifact_still_emits_updated_deck_and_finishes_sse(artifact_stream):
    events = await artifact_stream.consume()
    assert not [event for event in events if event["type"] == "error"], events
    assert events[-1]["type"] == "DONE"
    block = next(event for event in events if event["type"] == "artifact")["block"]
    assert block["version_id"] == "saved-deck_v2"
    assert block["content"]["cards"][0]["back"] == "Chlorophyll"
    artifact_stream.storage.update_artifact.assert_awaited_once()
    artifact_stream.mutator.model_manager.generate_with_retry.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_deck_is_created_without_attempting_a_mutation(artifact_stream):
    artifact_stream.plan.steps[0] = PlannedAction(
        action_type=ActionType.CREATE_ARTIFACT, description="Create deck",
        parameters={"type": "FLASHCARDS", "content": {"cards": [
            {"front": "What captures light?", "back": "Chlorophyll"},
        ]}},
    )
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    assert not [event for event in events if event["type"] == "error"], events
    assert next(event for event in events if event["type"] == "artifact")["block"]["version_id"] == "saved-deck_v1"
    artifact_stream.storage.create_artifact.assert_awaited_once()
    artifact_stream.storage.update_artifact.assert_not_awaited()
    artifact_stream.storage.get_artifact.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_outage_is_not_misreported_as_a_missing_artifact(artifact_stream):
    artifact_stream.storage.get_artifact.side_effect = RuntimeError("storage unavailable")
    events = await artifact_stream.consume()
    assert any(event["type"] == "error" for event in events)
    artifact_stream.storage.update_artifact.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [None, {}, {"user_id": "0"}])
async def test_mutation_without_authenticated_identity_never_reads_saved_content(artifact_stream, identity):
    from lyo_app.services.mutator import ArtifactUnavailable

    with pytest.raises(ArtifactUnavailable):
        await artifact_stream.mutator.mutate("saved-deck", "Add detail", user_context=identity)
    artifact_stream.storage.get_artifact.assert_not_awaited()
    artifact_stream.mutator.model_manager.generate_with_retry.assert_not_awaited()
    artifact_stream.storage.update_artifact.assert_not_awaited()


def creation_plan(control, parameters):
    control.plan.steps[0] = PlannedAction(
        action_type=ActionType.CREATE_ARTIFACT, description="Create requested flashcards",
        parameters=parameters,
    )
    control.storage.create_artifact.side_effect = lambda user_id, art_type, content: {
        "artifact_id": "generated-deck", "user_id": user_id, "type": art_type.value,
        "version": 1, "content": content,
    }


DECK = {"title": "Photosynthesis", "cards": [
    {"front": "What captures light?", "back": "Chlorophyll"},
    {"front": "What gas is consumed?", "back": "Carbon dioxide"},
    {"front": "What gas is released?", "back": "Oxygen"},
]}


@pytest.mark.asyncio
@pytest.mark.parametrize("parameters", [{}, {"artifact_type": "FLASHCARDS"},
                                      {"type": "QUIZ", "content": {"title": "New Quiz", "questions": []}}])
async def test_incomplete_plan_authors_the_requested_deck_instead_of_an_empty_quiz(
    artifact_stream, monkeypatch, parameters,
):
    from lyo_app.ai.schemas.lyo2 import UIBlockType, ArtifactType

    creation_plan(artifact_stream, parameters)
    completion = AsyncMock(return_value={"content": json.dumps(DECK), "model_used": "gemini-fixture"})
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    assert not [e for e in events if e["type"] == "error"], events
    block = next(e for e in events if e["type"] == "artifact")["block"]
    assert block["type"] == UIBlockType.FLASHCARDS
    assert block["content"]["cards"] == DECK["cards"]
    assert artifact_stream.storage.create_artifact.await_args.args[1] == ArtifactType.FLASHCARDS
    completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_artifact_step_still_creates_the_requested_flashcards(artifact_stream, monkeypatch):
    creation_plan(artifact_stream, {})
    artifact_stream.plan.steps.pop(0)
    completion = AsyncMock(return_value={"content": json.dumps(DECK)})
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    assert next(e for e in events if e["type"] == "artifact")["block"]["content"]["cards"] == DECK["cards"]
    completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_question_answer_cards_are_normalized_without_an_extra_model_call(artifact_stream, monkeypatch):
    creation_plan(artifact_stream, {"type": "FLASHCARDS", "content": {
        "title": "Photosynthesis", "flashcards": [{"question": " Light pigment? ", "answer": " Chlorophyll "}],
    }})
    completion = AsyncMock()
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    assert next(e for e in events if e["type"] == "artifact")["block"]["content"]["cards"] == [
        {"front": "Light pigment?", "back": "Chlorophyll"},
    ]
    completion.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    {"is_fallback": True, "content": "provider unavailable"},
    {"content": "not JSON"},
    {"content": '{"cards":[{"front":" ","back":""}]}'},
])
async def test_unavailable_or_invalid_authoring_never_saves_an_empty_deck(artifact_stream, monkeypatch, result):
    creation_plan(artifact_stream, {})
    completion = AsyncMock(return_value=result)
    monkeypatch.setattr("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", completion)
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    assert not [e for e in events if e["type"] in {"error", "artifact"}], events
    answer = next(e for e in events if e["type"] == "answer")["block"]["content"]["text"]
    assert "couldn't create" in answer
    artifact_stream.storage.create_artifact.assert_not_awaited()
    artifact_stream.executor._generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_disabled_real_storage_never_emits_a_saved_artifact(artifact_stream, operation):
    from lyo_app.services.artifact_service import ArtifactService

    storage = ArtifactService.__new__(ArtifactService)
    storage.fb = SimpleNamespace(enabled=False, db=None)
    artifact_stream.executor.artifacts = storage
    artifact_stream.mutator.artifacts = storage
    if operation == "create":
        creation_plan(artifact_stream, {"type": "FLASHCARDS", "content": DECK})

    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    assert not [e for e in events if e["type"] in {"artifact", "error", "voice_incomplete"}]
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["generation_status"] == "completed"
    assert "couldn't save" in answer["block"]["content"]["text"].lower()
    artifact_stream.mutator.model_manager.generate_with_retry.assert_not_awaited()
    artifact_stream.executor._generate_text.assert_not_awaited()
    assert [w["content"] for w in artifact_stream.harness.writes if w["role"] == "assistant"] == [
        answer["block"]["content"]["text"],
    ]


@pytest.mark.asyncio
async def test_planner_cannot_generate_confirmation_before_unavailable_update(artifact_stream):
    artifact_stream.plan.steps.reverse()
    artifact_stream.storage.get_artifact.return_value = None
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    artifact_stream.executor._generate_text.assert_not_awaited()
    assert not [e for e in events if e["type"] == "artifact"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read", "write", "provider"])
async def test_failed_update_never_emits_a_success_confirmation(artifact_stream, failure):
    if failure == "provider":
        artifact_stream.mutator.model_manager.generate_with_retry.side_effect = RuntimeError("provider unavailable")
    else:
        operation = "get_artifact" if failure == "read" else "update_artifact"
        getattr(artifact_stream.storage, operation).side_effect = RuntimeError("storage unavailable")
    events = await artifact_stream.consume()
    assert any(e["type"] == "error" for e in events)
    assert not [e for e in events if e["type"] in {"artifact", "answer", "voice_ready"}]
    artifact_stream.executor._generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [{}, {"cards": []}, {"cards": [{"front": "Q", "back": " "}]}])
async def test_invalid_mutated_flashcards_are_not_saved(artifact_stream, content):
    artifact_stream.mutator.model_manager.generate_with_retry.return_value = json.dumps(content)
    events = await artifact_stream.consume()
    assert any(e["type"] == "error" for e in events)
    assert not [e for e in events if e["type"] in {"artifact", "answer", "voice_ready"}]
    artifact_stream.storage.update_artifact.assert_not_awaited()
    artifact_stream.executor._generate_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_interrupted_confirmation_is_not_a_completed_artifact_turn(artifact_stream):
    from lyo_app.core.ai_resilience import StreamingIncompleteError

    artifact_stream.executor._generate_text.side_effect = StreamingIncompleteError(
        partial_text="Your saved deck contains", model="fixture",
    )
    events = await artifact_stream.consume()
    assert events[-1]["type"] == "DONE"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["generation_status"] == "incomplete"
    assert any(e["type"] == "voice_incomplete" for e in events)
    assert not [e for e in events if e["type"] in {"artifact", "voice_ready"}]
