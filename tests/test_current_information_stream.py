"""Real SSE route: current evidence, honest failures, source persistence/replay."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai_agents.multi_agent_v2.tools.base import ToolResult
from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool
from lyo_app.api.v1 import stream_lyo2 as stream
from lyo_app.chat import freshness
from lyo_app.chat.live_search import LIVE_SEARCH_UNAVAILABLE, WEB_BACKGROUND_NOTICE
from lyo_app.core.ai_resilience import ai_resilience_manager
from tests.test_live_search import NOW, weather_source
from tests.test_voice_turn_lifecycle import harness, event_payload  # noqa: F401


@pytest.fixture
def current_chat(harness, monkeypatch):
    monkeypatch.setattr(freshness, "current_time_context", lambda *_args: NOW)
    executor = LyoExecutor.__new__(LyoExecutor)
    monkeypatch.setattr(stream, "LyoExecutor", lambda _db: executor)
    harness.model_calls = []

    async def generate(**kwargs):
        harness.model_calls.append(kwargs)
        yield "New York forecast for October 6, 2026: 60 F."

    monkeypatch.setattr(ai_resilience_manager, "stream_chat_completion", generate)
    return harness


async def turn(control, text="Today's weather in New York"):
    response = await control.response(
        text=text, forced_intent=None,
        timezone="America/New_York",
        state_summary={"stream_capabilities": {"text_delta": True}},
    )
    return [event_payload(c) async for c in response.body_iterator]


@pytest.mark.asyncio
async def test_current_sources_have_dates_and_are_saved_with_canonical_answer(current_chat, monkeypatch):
    monkeypatch.setattr(WebSearchTool, "execute", AsyncMock(return_value=ToolResult(
        success=True, output=[weather_source()], message="Dated source",
    )))
    events = await turn(current_chat)
    statuses = [e["status"] for e in events if e["type"] == "search_status"]
    assert statuses == ["searching", "complete"]
    saved = next(w for w in current_chat.writes if w["role"] == "assistant")
    emitted = next(e["blocks"] for e in events if e["type"] == "smart_blocks")
    assert saved["blocks"] == emitted
    assert "Forecast for 2026-10-06" in emitted[0]["content"]["items"][0]["detail"]
    assert current_chat.model_calls[0]["enable_google_search"] is False


@pytest.mark.asyncio
async def test_empty_search_emits_unavailable_without_model_or_source_cards(current_chat, monkeypatch):
    monkeypatch.setattr(WebSearchTool, "execute", AsyncMock(return_value=ToolResult(
        success=True, output=[], message="No results",
    )))
    events = await turn(current_chat)
    assert current_chat.model_calls == []
    assert next(e for e in events if e["type"] == "answer")["block"]["content"]["text"] == LIVE_SEARCH_UNAVAILABLE
    assert [e["status"] for e in events if e["type"] == "search_status"] == ["searching", "unavailable"]
    assert not any(e["type"] in {"sources", "smart_blocks"} for e in events)


@pytest.mark.asyncio
async def test_retry_restores_saved_source_dates_without_claiming_a_new_lookup(current_chat, monkeypatch):
    blocks = [{
        "id": "sources-original", "schema_version": 1, "type": "interactive",
        "subtype": "sourceNavigator", "content": {"title": "Sources used", "items": [{
            "label": "Original source", "url": "https://example.com/weather",
            "detail": "Retrieved 2026-10-06T20:00:00-04:00",
        }]}, "metadata": {"role": "grounding"},
    }]
    monkeypatch.setattr(stream.conversation_store, "get_message_by_client_id", AsyncMock(
        return_value=SimpleNamespace(content="Previously saved answer", blocks=blocks, generation_status="completed")
    ))
    events = await turn(current_chat)
    assert next(e for e in events if e["type"] == "smart_blocks")["blocks"] == blocks
    assert current_chat.model_calls == []
    assert not any(e["type"] == "search_status" for e in events)


@pytest.mark.asyncio
async def test_general_knowledge_stream_fetches_and_persists_web_sources(current_chat, monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=True, output=[{
        "title": "Research reference", "url": "https://example.com/research",
        "snippet": "External information relevant to the question.",
    }], message="Retrieved external source"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    response = await current_chat.response(
        text="Who invented the transistor?", forced_intent=None,
        state_summary={"stream_capabilities": {"text_delta": True}},
    )
    events = [event_payload(c) async for c in response.body_iterator]
    search.assert_awaited_once()
    assert [e["status"] for e in events if e["type"] == "search_status"] == ["searching", "complete"]
    saved = next(w for w in current_chat.writes if w["role"] == "assistant")
    assert saved["blocks"][0]["content"]["items"][0]["url"] == "https://example.com/research"
    assert current_chat.model_calls[0]["enable_google_search"] is False
    assert "External information relevant" in str(current_chat.model_calls[0]["messages"])


@pytest.mark.asyncio
async def test_general_background_stream_discloses_failed_lookup(current_chat, monkeypatch):
    monkeypatch.setattr(WebSearchTool, "execute", AsyncMock(return_value=ToolResult(
        success=False, output=None, message="Unavailable",
    )))
    response = await current_chat.response(
        text="Who invented the transistor?", forced_intent=None,
        state_summary={"stream_capabilities": {"text_delta": True}},
    )
    events = [event_payload(c) async for c in response.body_iterator]
    answer = next(e for e in events if e["type"] == "answer")["block"]["content"]["text"]
    assert answer.startswith(WEB_BACKGROUND_NOTICE)
    assert [e["status"] for e in events if e["type"] == "search_status"] == ["searching", "unavailable"]
    assert len(current_chat.model_calls) == 1
    assert not any(e["type"] == "sources" for e in events)
async def test_general_question_stream_exposes_search_status_and_saved_sources(current_chat, monkeypatch):
    source = {"title": "Official reference", "url": "https://example.com/docs", "snippet": "Relevant documentation.", "provider": "tavily"}
    search = AsyncMock(return_value=ToolResult(success=True, output=[source], message="Found reference"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    events = await turn(current_chat, "What is retrieval augmented generation?")
    assert [e["status"] for e in events if e["type"] == "search_status"] == ["searching", "complete"]
    search.assert_awaited_once()
    blocks = next(e["blocks"] for e in events if e["type"] == "smart_blocks")
    assert blocks[0]["content"]["items"][0]["url"] == source["url"]
    assert next(w for w in current_chat.writes if w["role"] == "assistant")["blocks"] == blocks
