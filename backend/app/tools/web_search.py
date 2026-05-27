"""web_search — Tavily-backed web search; deterministic stub when no key is set
so the tool works offline / in the demo."""

from __future__ import annotations

import httpx

from app.config import settings
from app.tools.base import ToolContext


class WebSearchTool:
    name = "web_search"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        query = str(input.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}
        if not settings.tavily_api_key:
            return {
                "stub": True,
                "query": query,
                "results": [
                    {"title": f"(stub) Overview: {query}", "url": "https://example.com/1",
                     "content": f"Set TAVILY_API_KEY for live search. Stubbed summary for '{query}'."},
                ],
            }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": settings.tavily_api_key, "query": query, "max_results": 5},
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "query": query,
            "results": [
                {"title": r.get("title"), "url": r.get("url"), "content": (r.get("content") or "")[:500]}
                for r in data.get("results", [])
            ],
        }
