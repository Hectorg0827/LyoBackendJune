"""
Web Search Tool for the Lyo OS.
Provides agents with live web context using external search engines.
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from .base import BaseTool, ToolResult
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

class SearchParameters(BaseModel):
    query: str = Field(..., description="The search query to perform.")
    max_results: int = Field(5, description="Maximum number of results to return.")
    search_depth: str = Field("balanced", description="Search depth: 'basic' (fast) or 'advanced' (thorough).")

class WebSearchTool(BaseTool):
    """
    Tool to perform live web searches for grounding and fact-finding.
    """
    name = "web_search"
    description = "Perform a live web search to find current information, facts, or authoritative sources."
    parameters_schema = SearchParameters

    async def execute(self, user_id: int, **kwargs) -> ToolResult:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", 5)
        
        if not query:
            return ToolResult(success=False, output=None, message="Search query is required.")

        # Priority 1: Tavily (Modern, AI-optimized)
        tavily_key = os.getenv("TAVILY_API_KEY") 
        if tavily_key:
            return await self._execute_tavily(query, max_results, tavily_key)

        # Priority 2: Google Custom Search (Legacy fallback)
        google_key = getattr(settings, "google_search_api_key", None)
        cx = os.getenv("GOOGLE_CSE_ID")
        if google_key and cx:
            return await self._execute_google(query, max_results, google_key, cx)

        # Priority 3: DuckDuckGo (Free, no-auth fallback)
        try:
            return await self._execute_ddg(query, max_results)
        except Exception as e:
            logger.error(f"DDG Search failed: {e}")
            return ToolResult(
                success=False,
                output=None,
                message="No search engine available. Please configure TAVILY_API_KEY."
            )

    async def _execute_tavily(self, query: str, max_results: int, api_key: str) -> ToolResult:
        """Execute search using Tavily API"""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "advanced"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                formatted_results = [
                    {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
                    for r in results
                ]
                
                return ToolResult(
                    success=True,
                    output=formatted_results,
                    message=f"Found {len(formatted_results)} results via Tavily."
                )
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return await self._execute_ddg(query, max_results)

    async def _execute_google(self, query: str, max_results: int, api_key: str, cx: str) -> ToolResult:
        """Execute search using Google Custom Search API"""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": api_key,
                        "cx": cx,
                        "q": query,
                        "num": max_results
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                items = data.get("items", [])
                formatted_results = [
                    {"title": item.get("title"), "url": item.get("link"), "snippet": item.get("snippet")}
                    for item in items
                ]
                
                return ToolResult(
                    success=True,
                    output=formatted_results,
                    message=f"Found {len(formatted_results)} results via Google."
                )
        except Exception as e:
            logger.error(f"Google Search error: {e}")
            return await self._execute_ddg(query, max_results)

    async def _execute_ddg(self, query: str, max_results: int) -> ToolResult:
        """Execute search using DuckDuckGo (duckduckgo_search package)"""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                formatted_results = [
                    {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
                    for r in results
                ]
                
                return ToolResult(
                    success=True,
                    output=formatted_results,
                    message=f"Found {len(formatted_results)} results via DuckDuckGo."
                )
        except ImportError:
            return ToolResult(
                success=False,
                output=None,
                message="duckduckgo_search package not installed. Cannot perform search."
            )
        except Exception as e:
            logger.error(f"DDG unexpected error: {e}")
            raise e
