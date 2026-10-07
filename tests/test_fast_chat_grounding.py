import pytest

from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.ai_agents.multi_agent_v2.tools.base import ToolResult
from lyo_app.chat.live_search import LIVE_SEARCH_UNAVAILABLE, WEATHER_LOCATION_REQUIRED, WEB_BACKGROUND_NOTICE
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
    assert "try a web search" in chunks[0]
    assert "October 2023" not in chunks[0]
    search.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "Trending news in Dominican Republic", "What are the latest Python features?",
    "What are the current visa requirements for Japan?",
])
async def test_planner_path_cannot_answer_current_information_without_live_evidence(monkeypatch, query):
    search = AsyncMock(return_value=ToolResult(success=True, output=[], message="No results"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Unsupported current news")
    response = await executor.execute(
        user_id="1", intent="CHAT", original_request=query,
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


@pytest.mark.asyncio
async def test_general_information_fetches_web_before_any_model_provider(monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=True, output=[{
        "title": "Official research page", "url": "https://example.com/research",
        "snippet": "A development not present in the model's training data.",
    }], message="Retrieved web page"))
    captured = {}
    async def generate(**kwargs):
        captured.update(kwargs)
        yield "Answer from retrieved research"
    monkeypatch.setattr(WebSearchTool, "execute", search)
    monkeypatch.setattr(ai_resilience_manager, "stream_chat_completion", generate)
    metadata = {}
    chunks = [c async for c in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="What is this research about?", enable_google_search=True,
        search_required=False, current_time_context="Current date/time: 2026-10-06T22:00:00-04:00",
        metadata_sink=metadata,
    )]
    assert chunks == ["Answer from retrieved research"]
    search.assert_awaited_once()
    assert captured["enable_google_search"] is False
    assert "not present in the model's training data" in str(captured["messages"])
    assert metadata["search_status"] == "complete"
    assert metadata["sources"][0]["url"] == "https://example.com/research"


@pytest.mark.asyncio
async def test_background_fallback_discloses_failed_web_lookup(monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=False, output=None, message="Unavailable"))
    captured = {}
    async def generate(**kwargs):
        captured.update(kwargs)
        yield "Historical background"
    monkeypatch.setattr(WebSearchTool, "execute", search)
    monkeypatch.setattr(ai_resilience_manager, "stream_chat_completion", generate)
    metadata = {}
    chunks = [c async for c in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="Who invented the transistor?", enable_google_search=True,
        search_required=False, metadata_sink=metadata,
    )]
    assert chunks == [WEB_BACKGROUND_NOTICE, "Historical background"]
    assert metadata["sources"] == []
    assert metadata["search_status"] == "unavailable"
    assert captured["enable_google_search"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("planner_search", [False, True])
async def test_planner_general_information_injects_search_and_uses_new_evidence(monkeypatch, planner_search):
    source = {"title": "Research", "url": "https://example.com/research", "snippet": "Newly retrieved evidence."}
    search = AsyncMock(return_value=ToolResult(success=True, output=[source], message="Retrieved"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Answer from web research")
    response = await executor.execute(
        user_id="1", intent="CHAT", original_request="Tell me about fusion energy",
        plan=LyoPlan(steps=[
            *([PlannedAction(action_type=ActionType.SEARCH_WEB, description="Search",
                parameters={"query": "An unrelated archived topic"})] if planner_search else []),
            PlannedAction(action_type=ActionType.GENERATE_TEXT,
            description="Answer", parameters={"content": "Old planner knowledge"})]),
    )
    search.assert_awaited_once()
    assert search.await_args.kwargs["query"] == "Tell me about fusion energy"
    context = executor._generate_text.await_args.args[1]
    assert context["requires_live_search"] is True
    assert context["retrieved_content"][0]["snippet"] == "Newly retrieved evidence."
    assert response.metadata["sources"][0]["url"] == source["url"]
    assert response.answer_block.content["text"] == "Answer from web research"


@pytest.mark.asyncio
async def test_planner_background_fallback_is_also_disclosed_in_stream_and_answer(monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=False, output=None, message="Unavailable"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Historical background")
    callback = AsyncMock()
    response = await executor.execute(
        user_id="1", intent="CHAT", original_request="Who invented the transistor?",
        plan=LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Answer")]),
        text_delta_callback=callback,
    )
    callback.assert_awaited_once_with(WEB_BACKGROUND_NOTICE)
    assert response.answer_block.content["text"] == WEB_BACKGROUND_NOTICE + "Historical background"
    assert response.metadata["search_status"] == "unavailable"
    assert response.metadata["sources"] == []
async def test_general_factual_stream_uses_shared_sources_with_any_answer_provider(monkeypatch):
    source = {"title": "Official documentation", "url": "https://example.com/docs", "snippet": "Maintained documentation describes the feature.", "provider": "tavily"}
    search = AsyncMock(return_value=ToolResult(success=True, output=[source], message="Found documentation"))
    captured = {}
    async def generate(**kwargs):
        captured.update(kwargs)
        yield "A grounded explanation."
    monkeypatch.setattr(WebSearchTool, "execute", search)
    monkeypatch.setattr(ai_resilience_manager, "stream_chat_completion", generate)
    metadata = {}
    chunks = [part async for part in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="Tell me about retrieval augmented generation",
        enable_google_search=True, search_required=False, metadata_sink=metadata,
    )]
    assert chunks == ["A grounded explanation."]
    search.assert_awaited_once()
    assert captured["enable_google_search"] is False
    assert "gpt-4o-mini" in captured["provider_order"]
    assert metadata["search_status"] == "complete"
    assert metadata["sources"][0]["url"] == source["url"]
    assert any(source["snippet"] in str(m["content"]) for m in captured["messages"])


@pytest.mark.asyncio
async def test_optional_search_failure_discloses_background_before_streaming(monkeypatch):
    monkeypatch.setattr(WebSearchTool, "execute", AsyncMock(return_value=ToolResult(success=False, output=None, message="Unavailable")))
    async def generate(**kwargs):
        assert kwargs["enable_google_search"] is False
        assert any("Web retrieval failed" in str(m["content"]) for m in kwargs["messages"])
        yield "Stable background."
    monkeypatch.setattr(ai_resilience_manager, "stream_chat_completion", generate)
    metadata = {}
    chunks = [part async for part in LyoExecutor.__new__(LyoExecutor).stream_text(
        original_request="Who invented the transistor?", enable_google_search=True,
        search_required=False, metadata_sink=metadata,
    )]
    assert chunks == [WEB_BACKGROUND_NOTICE, "Stable background."]
    assert metadata["search_status"] == "unavailable"
    assert metadata["sources"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["Latest FastAPI version", "Current iPhone pricing", "New research on batteries"])
async def test_general_current_information_cannot_bypass_shared_search(monkeypatch, query):
    search = AsyncMock(return_value=ToolResult(success=True, output=[], message="No results"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Unsupported fact")
    response = await executor.execute(user_id="1", intent="CHAT", original_request=query,
        plan=LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Answer", parameters={"content": "Old static fact"})]))
    assert response.answer_block.content["text"] == LIVE_SEARCH_UNAVAILABLE
    executor._generate_text.assert_not_awaited()
    search.assert_awaited_once()


@pytest.mark.asyncio
async def test_planner_general_question_retrieves_sources_even_without_a_search_step(monkeypatch):
    source = {"title": "Documentation", "url": "https://example.com/docs", "snippet": "A feature explanation."}
    search = AsyncMock(return_value=ToolResult(success=True, output=[source], message="Found evidence"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Grounded explanation")
    response = await executor.execute(user_id="1", intent="CHAT", original_request="Tell me about retrieval augmented generation",
        plan=LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Answer")]))
    search.assert_awaited_once()
    assert response.metadata["search_status"] == "complete"
    assert response.metadata["sources"][0]["url"] == source["url"]
    assert executor._generate_text.await_args.args[1]["uses_web_search"] is True


@pytest.mark.asyncio
async def test_attachment_verification_still_requires_successful_web_retrieval(monkeypatch):
    search = AsyncMock(return_value=ToolResult(success=False, output=None, message="Unavailable"))
    monkeypatch.setattr(WebSearchTool, "execute", search)
    executor = LyoExecutor.__new__(LyoExecutor)
    executor._generate_text = AsyncMock(return_value="Unsupported verification")
    response = await executor.execute(user_id="1", intent="CHAT",
        original_request="Verify this attached article against current web sources",
        media_attachments=[{"name": "article.txt", "extracted_text": "An old claim."}],
        plan=LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Answer")]))
    assert response.answer_block.content["text"] == LIVE_SEARCH_UNAVAILABLE
    search.assert_awaited_once()
    executor._generate_text.assert_not_awaited()
