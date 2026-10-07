"""Live web search for Lyo.

Tavily remains the independent research provider. Gemini Google Search is the
first-party fallback because it can decide/search/ground against current web
content and returns source metadata. Google Custom Search and unofficial
DuckDuckGo scraping are intentionally not part of the production fallback
chain.
"""

import logging
import os
from datetime import timedelta
from typing import Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResult
from lyo_app.chat.live_search import (
    LiveSearchRequest,
    prepare_live_search,
    usable_search_results,
)

logger = logging.getLogger(__name__)


class SearchParameters(BaseModel):
    query: str = Field(..., description="The search query to perform.")
    max_results: int = Field(5, description="Maximum number of results to return.")
    search_depth: str = Field(
        "balanced",
        description="Search depth: 'basic' (fast) or 'advanced' (thorough).",
    )


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Perform a live web search to find current information, facts, "
        "or authoritative sources."
    )
    parameters_schema = SearchParameters

    async def execute(self, user_id: int, **kwargs) -> ToolResult:
        query = str(kwargs.get("query") or "").strip()
        max_results = int(kwargs.get("max_results", 5) or 5)
        if not query:
            return ToolResult(
                success=False,
                output=None,
                message="Search query is required.",
            )

        request = prepare_live_search(
            query,
            conversation_history=kwargs.get("conversation_history"),
            current_time_context=str(kwargs.get("current_time_context") or ""),
        )
        if request.needs_location:
            return ToolResult(
                success=False, output=None, message="Weather location is required.",
                data={"search_status": "needs_location"},
            )

        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            result = await self._execute_tavily(
                request.provider_query, max_results, tavily_key, request=request
            )
            usable = usable_search_results(result.output, request) if result.success else []
            if usable:
                return result.model_copy(update={
                    "output": usable, "data": {"search_status": "complete"},
                })

        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            result = await self._execute_gemini_grounded(
                request.provider_query, max_results, gemini_key, request=request
            )
            usable = usable_search_results(result.output, request) if result.success else []
            if usable:
                return result.model_copy(update={
                    "output": usable, "data": {"search_status": "complete"},
                })

        return ToolResult(
            success=False,
            output=None,
            message="No usable live evidence was retrieved.",
            data={"search_status": "unavailable"},
        )

    async def _execute_tavily(
        self,
        query: str,
        max_results: int,
        api_key: str,
        *,
        request: Optional[LiveSearchRequest] = None,
    ) -> ToolResult:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                    "include_published_date": True,
                }
                if request and request.current and request.topic in {"news", "weather"}:
                    payload.update({
                        "topic": "news" if request.topic == "news" else "general",
                        "time_range": "day",
                        "filter_by_published_date": request.topic == "news",
                    })
                    if request.topic == "news" and request.target_day != request.now.date():
                        payload.pop("time_range", None)
                        payload.update({
                            "start_date": request.target_day.isoformat(),
                            "end_date": (request.target_day + timedelta(days=1)).isoformat(),
                        })
                response = await client.post(
                    "https://api.tavily.com/search",
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                formatted = [
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "snippet": item.get("content"),
                        "provider": "tavily",
                        "published_at": item.get("published_date"),
                    }
                    for item in results[:max_results] if isinstance(item, dict)
                ]
                return ToolResult(
                    success=bool(formatted),
                    output=formatted or None,
                    message=f"Found {len(formatted)} results via Tavily.",
                )
        except Exception as exc:
            logger.warning("Tavily search failed; trying Gemini grounding: %s", type(exc).__name__)
            return ToolResult(
                success=False,
                output=None,
                message="Tavily search unavailable.",
            )

    async def _execute_gemini_grounded(
        self,
        query: str,
        max_results: int,
        api_key: str,
        *,
        request: Optional[LiveSearchRequest] = None,
    ) -> ToolResult:
        """Use Gemini's native Google Search grounding as the safe fallback."""
        import httpx

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
            "systemInstruction": {"parts": [{"text": (
                "Search the web for authoritative evidence relevant to the question, "
                "across any topic. Prefer official current documentation, product, "
                "research and organization sources for changing facts. "
                "Retrieve evidence for the requested place and date when relevant. "
                "Include publication dates for news and explicit forecast dates and "
                "locations for weather in the cited text. Do not reuse old forecasts. "
                "General documentation and research need not have been published "
                "today to be relevant. Distinguish historical from current claims. "
                "If Search finds no supporting current sources, say so."
            )}]},
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 900,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    params={"key": api_key},
                    json=payload,
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()

            candidates = data.get("candidates") or []
            if not candidates:
                return ToolResult(
                    success=False,
                    output=None,
                    message="Gemini search returned no candidates.",
                )
            candidate = candidates[0]
            grounding = candidate.get("groundingMetadata") or {}
            supported_text = {}
            for support in grounding.get("groundingSupports") or []:
                if not isinstance(support, dict):
                    continue
                segment = str((support.get("segment") or {}).get("text") or "").strip()
                for index in support.get("groundingChunkIndices") or []:
                    if isinstance(index, int) and segment:
                        supported_text.setdefault(index, []).append(segment)
            results = []
            seen = set()
            for index, item in enumerate(grounding.get("groundingChunks") or []):
                web = item.get("web") if isinstance(item, dict) else None
                if not isinstance(web, dict):
                    continue
                url = str(web.get("uri") or "").strip()
                snippet = "\n".join(supported_text.get(index) or [])
                if not url or url in seen or not snippet:
                    continue
                seen.add(url)
                results.append(
                    {
                        "title": str(web.get("title") or url),
                        "url": url,
                        "snippet": snippet,
                        "provider": "gemini_google_search",
                    }
                )
                if len(results) >= max_results:
                    break

            # A model answer alone, even with Search enabled, is not evidence.
            if request:
                results = usable_search_results(results, request)

            return ToolResult(
                success=bool(results),
                output=results or None,
                message=(
                    f"Found {len(results)} grounded results via Gemini Google Search."
                    if results
                    else "Gemini Google Search returned no grounded results."
                ),
            )
        except Exception as exc:
            logger.error("Gemini Google Search error: %s", type(exc).__name__)
            return ToolResult(
                success=False,
                output=None,
                message="Live web search is temporarily unavailable.",
            )
