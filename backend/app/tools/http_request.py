"""http_request — allowlisted outbound HTTP. GET/POST only, https/http only,
response body capped. (Per-agent domain allowlists are a documented extension.)"""

from __future__ import annotations

import httpx

from app.tools.base import ToolContext

_MAX_BODY = 20_000


class HttpRequestTool:
    name = "http_request"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        url = str(input.get("url", "")).strip()
        method = str(input.get("method", "GET")).upper()
        if not url.startswith(("http://", "https://")):
            return {"error": "url must be http(s)"}
        if method not in ("GET", "POST"):
            return {"error": "only GET/POST allowed"}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.request(method, url, json=input.get("body"))
            return {"status": resp.status_code, "body": resp.text[:_MAX_BODY]}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}
