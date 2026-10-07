import pytest

from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.ai_agents.multi_agent_v2.tools.base import ToolResult
from lyo_app.chat.live_search import LIVE_SEARCH_UNAVAILABLE, WEATHER_LOCATION_REQUIRED
from lyo_app.ai.schemas.lyo2 import ActionType, LyoPlan, PlannedAction
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_required_search_uses_shared_grounding_before_model(monkeypatch):
    captured = {}

    async def fake_search(self, user_id, **kwargs):
        return ToolResult(
            success=True,
            output=[
                {
                    "title": "Fresh Source",
                    "url": "https://example.com/fresh",
                    "snippet": "Fresh verified fact.",
                    "provider": "tavily",
                    "published_at": "2026-10-06T05:00:00-04:00",
                }
            ],
            message="Found 1 result via Tavily.",
        )

    async def fake_stream_chat_completion(**kwargs):
        captured.update(kwargs)
        yield "Grounded answer"

    monkeypatch.setattr(WebSearchTool, "execute", fake_search)
    monkeypatch.setattr(
        ai_resilience_manager,
        "stream_chat_completion",
        fake_stream_chat_completion,
    )

    executor = LyoExecutor.__new__(LyoExecutor)
    metadata = {}
    chunks = [
        chunk
        async for chunk in executor.stream_text(
            original_request="What happened today?",
            conversation_history=[],
            teaching_decision={"action": "answer"},
            interaction_contract=None,
            current_time_context="Current date/time: 2026-10-06T06:00:00-04:00",
            enable_google_search=True,
            search_required=True,
            metadata_sink=metadata,
        )
    ]

    assert chunks == ["Grounded answer"]
    assert captured["enable_google_search"] is False
    assert captured["provider_order"] != ["gemini-2.5-flash"]
    assert metadata["search_provider"] == "tavily"
    assert metadata["sources"] == [
        {
            "title": "Fresh Source",
            "url": "https://example.com/fresh",
            "provider": "tavily",
            "retrieved_at": "2026-10-06T06:00:00-04:00",
            "published_at": "2026-10-06T05:00:00-04:00",
        }
    ]
    assert any(
        "LIVE SEARCH MATERIAL" in str(message.get("content", ""))
        for message in captured["messages"]
    )


@pytest.mark.asyncio
async def test_required_search_does_not_generate_without_evidence(monkeypatch):
    captured = {}

    async def unavailable_search(self, user_id, **kwargs):
        return ToolResult(
            success=False,
            output=None,
            message="No live provider available.",
        )

    async def fake_stream_chat_completion(**kwargs):
        captured.update(kwargs)
        yield "Native grounded answer"

    monkeypatch.setattr(WebSearchTool, "execute", unavailable_search)
    monkeypatch.setattr(
        ai_resilience_manager,
        "stream_chat_completion",
        fake_stream_chat_completion,
    )

    executor = LyoExecutor.__new__(LyoExecutor)
    metadata = {}
    chunks = [
        chunk
        async for chunk in executor.stream_text(
            original_request="What happened today?",
            conversation_history=[],
            teaching_decision={"action": "answer"},
            interaction_contract=None,
            enable_google_search=True,
            search_required=True,
            metadata_sink=metadata,
        )
    ]

    assert chunks == [LIVE_SEARCH_UNAVAILABLE]
    assert captured == {}
    assert metadata["search_status"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [[], [{}], [{
    "title": "USA WEATHER FORECAST FOR JULY 10, 2026",
    "url": "https://example.com/july", "snippet": "July 10, 2026: New York 85 F.",
}]])
async def test_fast_weather_never_generates_from_empty_or_stale_evidence(monkeypatch, output):
    search = AsyncMock(return_value=ToolResult(success=True, output=output, message="Results"))
    generated = []
    async def fake_stream(**kwargs):
        generated.append(kwargs)
        yield "Unsupported weather"
    monkeypatch.setattr(WebSearchTool, "execute", search)
    monkeypatch.setattr(ai_resilience_manager, "stream_chat_completion", fake_stream)
    metadata = {}
    chunks = [chunk async for chunk in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="Today's weather in New York",
        current_time_context="Current date/time: 2026-10-06T22:00:00-04:00",
        search_required=True, enable_google_search=True, metadata_sink=metadata,
    )]
    assert chunks == [LIVE_SEARCH_UNAVAILABLE]
    assert generated == []
    assert metadata["sources"] == []


@pytest.mark.asyncio
async def test_weather_without_city_asks_before_fetching(monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(WebSearchTool, "execute", search)
    chunks = [chunk async for chunk in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="What is the weather today?", search_required=True,
    )]
    assert chunks == [WEATHER_LOCATION_REQUIRED]
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_capability_reply_does_not_invent_access_or_cutoff(monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(WebSearchTool, "execute", search)
    chunks = [chunk async for chunk in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="Bit how can you generare weather update", search_required=False,
    )]
    assert "try a live search" in chunks[0]
    assert "October 2023" not in chunks[0]
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_planner_path_cannot_answer_current_news_without_live_evidence(monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=True, output=[], message="No results"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Unsupported current news")
    response = await executor.execute(
        user_id="1", intent="CHAT", original_request="Trending news in Dominican Republic",
        plan=LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT,
            description="Answer", parameters={"content": "Old planner answer"})]),
        current_time_context="Current date/time: 2026-10-06T22:00:00-04:00",
    )
    assert response.answer_block.content["text"] == LIVE_SEARCH_UNAVAILABLE
    assert response.metadata["search_status"] == "unavailable"
    executor._generate_text.assert_not_awaited()
    search.assert_awaited_once()


@pytest.mark.asyncio
async def test_planner_search_cannot_replace_current_user_query_with_july(monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=True, output=[{
        "title": "New York weather October 6, 2026", "url": "https://example.com/weather",
        "snippet": "New York forecast October 6, 2026: 60 F.",
    }], message="Found source"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Fresh grounded weather")
    response = await executor.execute(
        user_id="1", intent="CHAT", original_request="Weather in New York today",
        plan=LyoPlan(steps=[
            PlannedAction(action_type=ActionType.SEARCH_WEB, description="Search",
                parameters={"query": "July 10 weather in Dallas"}),
            PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Answer"),
        ]),
        current_time_context="Current date/time: 2026-10-06T22:00:00-04:00",
    )
    assert search.await_args.kwargs["query"] == "Weather in New York today"
    assert response.answer_block.content["text"] == "Fresh grounded weather"
    assert response.metadata["sources"][0]["forecast_date"] == "2026-10-06"
    assert executor._generate_text.await_args.args[1]["requires_live_search"] is True
