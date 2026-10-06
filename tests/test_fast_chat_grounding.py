import pytest

from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai_agents.multi_agent_v2.tools.web_search_tool import WebSearchTool
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.ai_agents.multi_agent_v2.tools.base import ToolResult


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

    executor = LyoExecutor(None)
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
        }
    ]
    assert any(
        "LIVE SEARCH MATERIAL" in str(message.get("content", ""))
        for message in captured["messages"]
    )


@pytest.mark.asyncio
async def test_required_search_falls_back_to_native_gemini_grounding(monkeypatch):
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

    executor = LyoExecutor(None)
    chunks = [
        chunk
        async for chunk in executor.stream_text(
            original_request="What happened today?",
            conversation_history=[],
            teaching_decision={"action": "answer"},
            interaction_contract=None,
            enable_google_search=True,
            search_required=True,
            metadata_sink={},
        )
    ]

    assert chunks == ["Native grounded answer"]
    assert captured["provider_order"] == ["gemini-2.5-flash"]
    assert captured["enable_google_search"] is True
