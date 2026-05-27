"""OpenAI provider — thin adapter to the Chat Completions API.

SDK imported lazily so the harness imports cleanly without the dependency in
stub/replay environments.
"""

from __future__ import annotations

import json

from app.config import settings
from app.harness.call import ImageBlock, LLMRequest, LLMResponse, TextBlock, ToolCall
from app.harness.providers.base import FatalError, RetryableError


def _to_openai_content(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content:
        if isinstance(b, TextBlock):
            parts.append({"type": "text", "text": b.text})
        elif isinstance(b, ImageBlock):
            parts.append({"type": "image_url", "image_url": {"url": f"data:{b.mime};base64,{b.data}"}})
    return parts


class OpenAIProvider:
    name = "openai"
    supports_images = True

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.openai_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def complete(self, request: LLMRequest) -> LLMResponse:
        from openai import APIConnectionError, APITimeoutError, RateLimitError
        from openai import APIStatusError

        client = self._get_client()
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            role = "assistant" if m.role == "assistant" else "user" if m.role in ("user", "tool") else m.role
            messages.append({"role": role, "content": _to_openai_content(m.content)})

        kwargs: dict = {
            "model": request.model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            kwargs["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {})}}
                for t in request.tools
            ]
        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await client.chat.completions.create(**kwargs)
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            raise RetryableError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503):
                raise RetryableError(str(exc)) from exc
            raise FatalError(str(exc)) from exc

        choice = resp.choices[0].message
        tool_calls: list[ToolCall] = []
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))

        usage = resp.usage
        return LLMResponse(
            content=choice.content or "",
            tool_calls=tool_calls,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            finish_reason=resp.choices[0].finish_reason,
            raw={"id": resp.id},
        )

    def estimate_tokens(self, request: LLMRequest) -> int:
        chars = len(request.system or "")
        for m in request.messages:
            chars += len(m.content) if isinstance(m.content, str) else sum(len(getattr(b, "text", "")) for b in m.content)
        return chars // 3 + request.max_tokens
