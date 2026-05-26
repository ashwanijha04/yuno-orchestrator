"""Anthropic provider — thin adapter to the Messages API.

The SDK is imported lazily so the harness package imports cleanly in
environments (tests, stub/replay mode) without the dependency installed.
"""

from __future__ import annotations

from app.harness.call import ImageBlock, LLMRequest, LLMResponse, TextBlock, ToolCall
from app.harness.providers.base import FatalError, RetryableError
from app.config import settings


def _to_anthropic_content(content) -> object:
    if isinstance(content, str):
        return content
    blocks = []
    for b in content:
        if isinstance(b, TextBlock):
            blocks.append({"type": "text", "text": b.text})
        elif isinstance(b, ImageBlock):
            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": b.mime, "data": b.data},
                }
            )
    return blocks


class AnthropicProvider:
    name = "anthropic"
    supports_images = True

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.anthropic_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete(self, request: LLMRequest) -> LLMResponse:
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
        )

        client = self._get_client()
        messages = [
            {"role": m.role, "content": _to_anthropic_content(m.content)}
            for m in request.messages
            if m.role != "system"
        ]
        kwargs: dict = {
            "model": request.model_name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if request.system:
            kwargs["system"] = request.system
        if request.tools:
            kwargs["tools"] = request.tools

        try:
            resp = await client.messages.create(**kwargs)
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            raise RetryableError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503, 529):
                raise RetryableError(str(exc)) from exc
            raise FatalError(str(exc)) from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        return LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
            finish_reason=resp.stop_reason,
            raw={"id": resp.id},
        )

    def estimate_tokens(self, request: LLMRequest) -> int:
        # Conservative char/3 heuristic (rounds high) + a fixed output budget,
        # so the cost cap trips before the call rather than after.
        chars = 0
        for m in request.messages:
            if isinstance(m.content, str):
                chars += len(m.content)
            else:
                chars += sum(len(getattr(b, "text", "")) for b in m.content)
        if request.system:
            chars += len(request.system)
        return chars // 3 + request.max_tokens
