"""Actual route/save/replay regressions for completed and interrupted Chat."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_voice_turn_lifecycle import harness, event_payload
from lyo_app.chat.models import ChatMessage


@pytest.mark.asyncio
@pytest.mark.parametrize("incremental", [False, True])
async def test_comparison_and_dated_sources_saved_exactly_as_emitted(harness, monkeypatch, incremental):
    from lyo_app.api.v1 import stream_lyo2 as stream

    harness.result = "Mitosis produces two similar cells. Meiosis produces four genetically varied cells."
    sources = [{"title": "Cell research", "url": "https://example.com/cells",
                "kind": "web", "retrieved_at": "2026-10-08T15:00:00-04:00",
                "published_at": "2026-10-08"}]

    async def fake_stream(self, **kwargs):
        kwargs["metadata_sink"].update(sources=sources, search_status="complete")
        yield harness.result

    async def fake_execute(self, **kwargs):
        return SimpleNamespace(
            answer_block=SimpleNamespace(content={"text": harness.result}),
            artifact_block=None, open_classroom_payload=None, next_actions=[],
            metadata={"sources": sources, "search_status": "complete"},
        )

    monkeypatch.setattr(stream.LyoExecutor, "stream_text", fake_stream, raising=False)
    monkeypatch.setattr(stream.LyoExecutor, "execute", fake_execute)
    response = await harness.response(
        text="Compare mitosis and meiosis.",
        state_summary={"stream_capabilities": {"text_delta": incremental}},
    )
    events = [event_payload(chunk) async for chunk in response.body_iterator]
    emitted = [block for event in events if event.get("type") == "smart_blocks"
               for block in event.get("blocks", [])]
    assert any(block.get("subtype") == "comparison" for block in emitted)
    assert any(block.get("subtype") == "sourceNavigator" for block in emitted)
    saved = [write for write in harness.writes if write.get("role") == "assistant"]
    assert len(saved) == 1
    assert saved[0]["content"] == harness.result
    assert saved[0]["blocks"] == emitted

    # Retry loads the canonical stored row, not client-supplied blocks.
    row = ChatMessage(content=saved[0]["content"], blocks=saved[0]["blocks"],
                      action_triggered=saved[0].get("action_triggered"))
    monkeypatch.setattr(stream.conversation_store, "get_message_by_client_id",
                        AsyncMock(return_value=row))
    replay = await harness.response(state_summary={})
    replay_events = [event_payload(chunk) async for chunk in replay.body_iterator]
    restored = [block for event in replay_events if event.get("type") == "smart_blocks"
                for block in event.get("blocks", [])]
    assert restored == emitted
    assert next(event for event in replay_events if event.get("type") == "answer")["generation_status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", ["stream_incomplete", "voice_incomplete"])
async def test_partial_history_replays_incomplete_and_is_excluded_from_context(harness, monkeypatch, marker):
    from lyo_app.api.v1 import stream_lyo2 as stream

    partial = ChatMessage(content="This is only half an answer", role="assistant",
                          client_message_id="partial-turn", action_triggered=marker)
    assert partial.generation_status == "incomplete"
    monkeypatch.setattr(stream.conversation_store, "get_message_by_client_id",
                        AsyncMock(return_value=partial))
    response = await harness.response(state_summary={})
    events = [event_payload(chunk) async for chunk in response.body_iterator]
    assert next(event for event in events if event.get("type") == "answer")["generation_status"] == "incomplete"

    captured = {}
    async def fake_stream(self, **kwargs):
        captured.update(kwargs)
        yield "A fresh complete answer."

    async def fake_execute(self, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            answer_block=SimpleNamespace(content={"text": "A fresh complete answer."}),
            artifact_block=None, open_classroom_payload=None, next_actions=[], metadata={},
        )

    monkeypatch.setattr(stream.conversation_store, "get_message_by_client_id",
                        AsyncMock(return_value=None))
    monkeypatch.setattr(stream.conversation_store, "get_messages", AsyncMock(return_value=[partial]))
    monkeypatch.setattr(stream.LyoExecutor, "stream_text", fake_stream, raising=False)
    monkeypatch.setattr(stream.LyoExecutor, "execute", fake_execute)
    response = await harness.response(text="Just answer: name two parts of a plant.",
                                     state_summary={"stream_capabilities": {"text_delta": True}})
    events = [event_payload(chunk) async for chunk in response.body_iterator]
    assert captured, events
    assert all(turn.get("content") != partial.content for turn in captured["conversation_history"])


@pytest.mark.asyncio
async def test_rest_delivers_persists_and_replays_canonical_blocks(
    async_client, auth_headers, monkeypatch,
):
    from lyo_app.api.v1 import chat_lyo2 as rest
    from lyo_app.ai.schemas.lyo2 import (
        Intent, RouterDecision, RouterResponse, UnifiedChatResponse, UIBlock, UIBlockType,
    )
    from lyo_app.chat import verification

    text = "Mitosis produces two similar cells. Meiosis produces four varied cells."
    source = {"title": "Cell research", "url": "https://example.com/cells", "kind": "web",
              "snippet": text, "retrieved_at": "2026-10-08T15:00:00-04:00"}
    monkeypatch.setattr(rest.router_agent, "route", AsyncMock(return_value=RouterResponse(
        trace_id="rest-canonical-test",
        decision=RouterDecision(intent=Intent.CHAT, confidence=1.0),
    )))
    execute = AsyncMock(return_value=UnifiedChatResponse(
        answer_block=UIBlock(type=UIBlockType.TUTOR_MESSAGE, content={"text": text}),
        metadata={"sources": [source], "search_status": "complete"},
    ))
    monkeypatch.setattr(rest.LyoExecutor, "execute", execute)
    monkeypatch.setattr(verification, "selectively_verify_answer", AsyncMock(
        return_value=verification.VerificationResult(False, False, text, "not_required"),
    ))
    payload = {"text": "Compare mitosis and meiosis.", "client_message_id": "rest-canonical-turn"}
    response = await async_client.post("/api/v1/lyo2/chat", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    result = response.json()
    blocks = result["metadata"]["smart_blocks"]
    assert any(block.get("subtype") == "comparison" for block in blocks)
    assert any(block.get("subtype") == "sourceNavigator" for block in blocks)
    conversation_id = result["metadata"]["conversation_id"]
    history = await async_client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers)
    assert history.status_code == 200, history.text
    saved = [message for message in history.json()["messages"] if message["role"] == "assistant"]
    assert len(saved) == 1
    assert saved[0]["content"] == text
    assert saved[0]["blocks"] == blocks
    replay = await async_client.post("/api/v1/lyo2/chat", headers=auth_headers,
                                    json={**payload, "conversation_id": conversation_id})
    assert replay.status_code == 200, replay.text
    assert replay.json()["metadata"]["smart_blocks"] == blocks
    assert replay.json()["metadata"]["replayed"] is True
    execute.assert_awaited_once()
