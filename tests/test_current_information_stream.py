"""Real SSE route: current evidence, honest failures, source persistence/replay."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai_agents.multi_agent_v2.tools.base import ToolResult
from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool
from lyo_app.api.v1 import stream_lyo2 as stream
from lyo_app.chat import freshness
from lyo_app.chat.live_search import LIVE_SEARCH_UNAVAILABLE
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


async def turn(control):
    response = await control.response(
        text="Today's weather in New York", forced_intent=None,
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
