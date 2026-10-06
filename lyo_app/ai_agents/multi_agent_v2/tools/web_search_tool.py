"""Live web search for Lyo.

Tavily remains the independent research provider. Gemini Google Search is the
first-party fallback because it can decide/search/ground against current web
content and returns source metadata. Google Custom Search and unofficial
DuckDuckGo scraping are intentionally not part of the production fallback
chain.
"""

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResult

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

        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            result = await self._execute_tavily(query, max_results, tavily_key)
            if result.success:
                return result

        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            return await self._execute_gemini_grounded(
                query, max_results, gemini_key
            )

        return ToolResult(
            success=False,
            output=None,
            message=(
                "No production search provider is configured. Set TAVILY_API_KEY "
                "or GEMINI_API_KEY."
            ),
        )

    async def _execute_tavily(
        self,
        query: str,
        max_results: int,
        api_key: str,
    ) -> ToolResult:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "advanced",
                    },
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
                    }
                    for item in results[:max_results]
                ]
                return ToolResult(
                    success=True,
                    output=formatted,
                    message=f"Found {len(formatted)} results via Tavily.",
                )
        except Exception as exc:
            logger.warning("Tavily search failed; trying Gemini grounding: %s", exc)
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
            parts = ((candidate.get("content") or {}).get("parts") or [])
            answer = "".join(
                str(part.get("text") or "")
                for part in parts
                if isinstance(part, dict) and not part.get("thought")
            ).strip()

            grounding = candidate.get("groundingMetadata") or {}
            results = []
            seen = set()
            for item in grounding.get("groundingChunks") or []:
                web = item.get("web") if isinstance(item, dict) else None
                if not isinstance(web, dict):
                    continue
                url = str(web.get("uri") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(
                    {
                        "title": str(web.get("title") or url),
                        "url": url,
                        "snippet": answer if not results else "",
                        "provider": "gemini_google_search",
                    }
                )
                if len(results) >= max_results:
                    break

            if not results and answer:
                results.append(
                    {
                        "title": "Google Search grounded answer",
                        "url": "",
                        "snippet": answer,
                        "provider": "gemini_google_search",
                    }
                )

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
            logger.error("Gemini Google Search error: %s", exc)
            return ToolResult(
                success=False,
                output=None,
                message="Live web search is temporarily unavailable.",
            )
