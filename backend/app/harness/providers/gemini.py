"""Gemini provider — thin adapter to the google-genai SDK.

Lazy import; if the SDK/key is absent the ModelRouter simply skips Gemini and
falls back to the next provider. Tool-calling is intentionally minimal here
(text-first); conversations route to Gemini.
"""

from __future__ import annotations

from app.config import settings
from app.harness.call import LLMRequest, LLMResponse
from app.harness.providers.base import FatalError, RetryableError


class GeminiProvider:
    name = "gemini"
    supports_images = True

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.gemini_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._get_client()
        # Flatten conversation to text parts (text-first).
        parts: list[str] = []
        for m in request.messages:
            text = m.content if isinstance(m.content, str) else " ".join(getattr(b, "text", "") for b in m.content)
            parts.append(f"{m.role}: {text}")
        contents = "\n".join(parts)
        config = {"temperature": request.temperature, "max_output_tokens": request.max_tokens}
        if request.system:
            config["system_instruction"] = request.system
        try:
            resp = await client.aio.models.generate_content(
                model=request.model_name, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 — SDK error taxonomy varies
            msg = str(exc).lower()
            if any(k in msg for k in ("rate", "timeout", "503", "unavailable", "overloaded")):
                raise RetryableError(str(exc)) from exc
            raise FatalError(str(exc)) from exc

        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            content=resp.text or "",
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
            finish_reason="stop",
            raw={},
        )

    def estimate_tokens(self, request: LLMRequest) -> int:
        chars = len(request.system or "")
        for m in request.messages:
            chars += len(m.content) if isinstance(m.content, str) else sum(len(getattr(b, "text", "")) for b in m.content)
        return chars // 3 + request.max_tokens
