from unittest.mock import AsyncMock

import httpx
import pytest

from lyo_app.ai_agents.multi_agent_v2.tools.base import ToolResult
from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool
from lyo_app.chat.live_search import (
    prepare_live_search, source_descriptor, source_navigator, usable_search_results,
)


NOW = "Current date/time: 2026-10-06T22:00:00-04:00 (America/New_York)."


def weather_source(**updates):
    return {
        "title": "New York weather October 6, 2026",
        "url": "https://example.com/weather",
        "snippet": "New York forecast for October 6, 2026: 60 F.",
        "published_at": "2026-10-06T20:00:00-04:00",
        "provider": "tavily", **updates,
    }


@pytest.mark.parametrize("source", [
    weather_source(title="USA WEATHER FORECAST FOR JULY 10, 2026", snippet="July 10, 2026: 85 F in New York."),
    weather_source(url="https://example.com/2026/07/10/weather"),
    weather_source(title="Dallas weather October 6, 2026", snippet="Dallas forecast for October 6, 2026: 80 F."),
    weather_source(title="New York weather", snippet="New York: 60 F."),
    weather_source(published_at="2026-07-10T20:00:00-04:00"),
    weather_source(url="", snippet="New York forecast for October 6, 2026"),
    weather_source(url="https://[invalid"),
])
def test_current_weather_rejects_stale_undated_and_wrong_city_results(source):
    request = prepare_live_search("Today's weather in New York", current_time_context=NOW)
    assert usable_search_results([source], request) == []


def test_weather_keeps_forecast_publication_and_retrieval_dates_distinct():
    request = prepare_live_search("Today's weather in New York", current_time_context=NOW)
    result = usable_search_results([weather_source()], request)[0]
    assert result["forecast_date"] == "2026-10-06"
    assert result["retrieved_at"] == "2026-10-06T22:00:00-04:00"
    block = source_navigator([source_descriptor(result)], "sources-test")[0]
    detail = block["content"]["items"][0]["detail"]
    assert "Forecast for 2026-10-06" in detail
    assert "Published 2026-10-06T20:00:00-04:00" in detail
    assert "Retrieved 2026-10-06T22:00:00-04:00" in detail
    assert "Live web source" not in detail


def test_tomorrow_forecast_uses_local_day_and_requested_place():
    request = prepare_live_search("New York weather tomorrow", current_time_context=NOW)
    assert request.location == "New York"
    assert request.target_day.isoformat() == "2026-10-07"
    assert "Current local date: 2026-10-06" in request.provider_query
    assert "Requested date: 2026-10-07" in request.provider_query
    assert usable_search_results([weather_source()], request) == []


@pytest.mark.parametrize("query,location", [
    ("Weather for tomorrow in New York", "New York"),
    ("Weather tomorrow in New York", "New York"),
    ("Weather in New York for tomorrow", "New York"),
    ("Pronóstico para mañana en Nueva York", "Nueva York"),
    ("Clima en Nueva York para mañana", "Nueva York"),
])
def test_temporal_weather_qualifiers_do_not_remove_the_supplied_city(query, location):
    request = prepare_live_search(query, current_time_context=NOW)
    assert request.location == location
    assert not request.needs_location
    assert request.target_day.isoformat() == "2026-10-07"
    source = weather_source(
        title="New York forecast October 7, 2026",
        snippet="New York forecast for October 7, 2026: 60 F.",
    )
    assert usable_search_results([source], request)


def test_historical_weather_is_not_forced_into_current_date_window():
    request = prepare_live_search("Weather in New York on July 10, 2026", current_time_context=NOW)
    result = weather_source(title="July 10, 2026 weather", snippet="July 10, 2026 in New York: 85 F.", published_at="2026-07-10")
    assert request.current is False
    assert request.provider_query == request.query
    assert usable_search_results([result], request)


def test_follow_up_changes_place_without_using_old_assistant_claims():
    request = prepare_live_search("What about Boston?", current_time_context=NOW, conversation_history=[
        {"role": "user", "content": "Weather in New York today"},
        {"role": "assistant", "content": "July 10, 2026 in Dallas: 85 F."},
    ])
    assert request.topic == "weather"
    assert request.location == "Boston"
    assert "July" not in request.provider_query
    assert usable_search_results([weather_source()], request) == []


@pytest.mark.parametrize("published", [None, "2026-07-10", "2026-10-07", "2026-10-07T12:00:00-04:00"])
def test_news_requires_recent_dated_evidence(published):
    request = prepare_live_search("Trending news in Dominican Republic", current_time_context=NOW)
    result = {"title": "Dominican Republic headlines", "url": "https://example.com/news", "snippet": "Dominican Republic news.", "published_at": published}
    assert usable_search_results([result], request) == []


def test_news_dates_are_compared_in_users_timezone():
    request = prepare_live_search("Noticias de hoy en República Dominicana", current_time_context=NOW)
    result = {"title": "República Dominicana", "url": "https://example.com/news", "snippet": "Noticias de República Dominicana.", "published_at": "Wed, 07 Oct 2026 01:00:00 GMT"}
    assert usable_search_results([result], request)


@pytest.mark.parametrize("offset", ["-04:00", "-07:00", "+00:00", "+09:00"])
def test_date_only_news_stays_on_its_calendar_day_and_preserves_date_precision(offset):
    request = prepare_live_search("News today", current_time_context=f"Current date/time: 2026-10-06T15:00:00{offset}")
    source = {"title": "Headlines", "url": "https://example.com/news", "snippet": "A news update.", "published_at": "2026-10-06"}
    result = usable_search_results([source], request)[0]
    assert result["published_at"] == "2026-10-06"
    assert usable_search_results([{**source, "published_at": "2026-10-07"}], request) == []
    assert usable_search_results([{**source, "published_at": "2026-10-05"}], request) == []


@pytest.mark.parametrize("query", [
    "Latest FastAPI version", "Current iPhone pricing", "New research on batteries",
    "Tell me about retrieval augmented generation",
])
def test_general_web_lookup_accepts_maintained_pages_without_news_date_rules(query):
    request = prepare_live_search(query, current_time_context=NOW)
    source = {"title": "Official reference", "url": "https://example.com/docs", "snippet": "Relevant information from maintained documentation."}
    assert request.topic == "general"
    assert usable_search_results([source], request)
    assert "authoritative" in request.provider_query
    assert "exclude archived forecasts" not in request.provider_query


def test_live_financial_quotes_still_require_dated_evidence():
    request = prepare_live_search("Stock price right now", current_time_context=NOW)
    source = {"title": "Market data", "url": "https://example.com/quote", "snippet": "Stock price: 100."}
    assert usable_search_results([source], request) == []


def test_today_news_cannot_be_replaced_with_yesterdays_article():
    request = prepare_live_search("News today", current_time_context=NOW)
    result = {"title": "Headlines", "url": "https://example.com/news", "snippet": "A news update.", "published_at": "2026-10-05T18:00:00-04:00"}
    assert usable_search_results([result], request) == []


def test_current_year_does_not_disable_recency_for_latest_news():
    request = prepare_live_search("Latest news in 2026", current_time_context=NOW)
    assert request.current is True


def test_yesterday_news_uses_the_requested_day():
    request = prepare_live_search("News yesterday", current_time_context=NOW)
    result = {"title": "Headlines", "url": "https://example.com/news", "snippet": "A news update.", "published_at": "2026-10-05T18:00:00-04:00"}
    assert usable_search_results([result], request)
    assert not usable_search_results([{**result, "published_at": "2026-10-06T18:00:00-04:00"}], request)


def test_stable_search_does_not_need_a_recent_publication():
    request = prepare_live_search("Search for the history of the transistor", current_time_context=NOW)
    result = {"title": "Transistor history", "url": "https://example.com/history", "snippet": "The transistor was invented in 1947."}
    assert usable_search_results([result], request)


def test_historical_follow_up_keeps_the_requested_date():
    request = prepare_live_search("What about Boston?", current_time_context=NOW, conversation_history=[
        {"role": "user", "content": "Weather in New York on July 10, 2026"},
    ])
    assert request.target_day.isoformat() == "2026-07-10"
    assert request.current is False


@pytest.mark.asyncio
@pytest.mark.parametrize("tavily_output", [[], [weather_source(title="July 10, 2026 forecast", snippet="July 10, 2026 in New York.")]])
async def test_empty_or_stale_tavily_results_attempt_gemini(monkeypatch, tavily_output):
    monkeypatch.setenv("TAVILY_API_KEY", "offline-test")
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test")
    tavily = AsyncMock(return_value=ToolResult(success=True, output=tavily_output, message="Provider returned results"))
    gemini = AsyncMock(return_value=ToolResult(success=True, output=[weather_source(provider="gemini_google_search")], message="Grounded result"))
    monkeypatch.setattr(WebSearchTool, "_execute_tavily", tavily)
    monkeypatch.setattr(WebSearchTool, "_execute_gemini_grounded", gemini)
    result = await WebSearchTool().execute(0, query="Weather in New York today", current_time_context=NOW)
    assert result.success
    gemini.assert_awaited_once()
    assert result.output[0]["provider"] == "gemini_google_search"


@pytest.mark.asyncio
async def test_no_provider_returns_explicit_unavailable_status(monkeypatch):
    for key in ("TAVILY_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    result = await WebSearchTool().execute(0, query="News today", current_time_context=NOW)
    assert not result.success
    assert result.output is None
    assert result.data["search_status"] == "unavailable"


def mock_http(monkeypatch, response_body, captured):
    original_client = httpx.AsyncClient
    async def respond(request):
        import json
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=response_body)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))


@pytest.mark.asyncio
async def test_tavily_receives_date_window_and_preserves_publication_date(monkeypatch):
    captured = {}
    mock_http(monkeypatch, {"results": [{"title": "Dominican Republic headlines", "url": "https://example.com/news", "content": "Dominican Republic news.", "published_date": "Tue, 06 Oct 2026 20:00:00 GMT"}]}, captured)
    request = prepare_live_search("Trending news in Dominican Republic", current_time_context=NOW)
    result = await WebSearchTool()._execute_tavily(request.provider_query, 5, "offline-test", request=request)
    assert captured["topic"] == "news"
    assert captured["time_range"] == "day"
    assert captured["filter_by_published_date"] is True
    assert captured["include_published_date"] is True
    assert "2026-10-06" in captured["query"]
    assert result.output[0]["published_at"] == "Tue, 06 Oct 2026 20:00:00 GMT"


@pytest.mark.asyncio
@pytest.mark.parametrize("grounding", [{}, {"groundingChunks": [{"web": {"uri": "https://example.com/weather", "title": "Weather"}}]}])
async def test_gemini_answer_without_supported_web_evidence_is_failure(monkeypatch, grounding):
    mock_http(monkeypatch, {"candidates": [{"content": {"parts": [{"text": "Today is 85 degrees."}]}, "groundingMetadata": grounding}]}, {})
    result = await WebSearchTool()._execute_gemini_grounded("Weather today", 5, "offline-test")
    assert not result.success
    assert result.output is None


@pytest.mark.asyncio
async def test_gemini_keeps_only_cited_text_for_each_source(monkeypatch):
    mock_http(monkeypatch, {"candidates": [{
        "content": {"parts": [{"text": "Uncited old weather July 10, 2026."}]},
        "groundingMetadata": {
            "groundingChunks": [
                {"web": {"uri": "https://example.com/weather", "title": "New York weather October 6, 2026"}},
                {"web": {"uri": "https://example.com/uncited", "title": "Uncited source"}},
            ],
            "groundingSupports": [{"segment": {"text": "New York forecast October 6, 2026: 60 F."}, "groundingChunkIndices": [0]}],
        },
    }]}, {})
    request = prepare_live_search("Weather in New York today", current_time_context=NOW)
    result = await WebSearchTool()._execute_gemini_grounded(request.provider_query, 5, "offline-test", request=request)
    assert result.success
    assert len(result.output) == 1
    assert "July" not in result.output[0]["snippet"]
