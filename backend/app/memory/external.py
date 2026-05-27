"""ExternalMemoryStrategy — long-term episodic recall via extremis, running
*embedded* (not over HTTP) and backed by our Postgres + pgvector.

extremis is configured entirely through EXTREMIS_* env (store, postgres url,
embedder, dim, home — see docker-compose). We use the OpenAI embedder, so no
sentence-transformers/torch is ever loaded. The SDK is synchronous, so every
call hops to a thread; calls per namespace (= agent id) are serialised behind a
lock because the underlying psycopg2 connection isn't thread-safe.

Degrades gracefully: if extremis isn't installed/reachable or no store is
configured, recall returns None and we fall back to BufferMemory — so the stack
(and the offline demo) still runs without it.

Continuous-learning loop: load -> recall (this file), and the engine calls
`remember(...)` after each agent turn so knowledge accumulates across tasks.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
from app.memory.base import MemoryContext
from app.memory.buffer import BufferMemory

log = get_logger("memory.external")

# Full-quality OpenAI embeddings. The sqlite store keeps embeddings as
# dimension-agnostic float32 BLOBs (cosine computed in Python), so 1536 dims work
# natively — no torch, no schema change. (The 384 cap only applied to extremis's
# hardcoded Postgres vector(384) column, which we don't use.)
_EMBED_DIM = 1536
_EMBED_MODEL = "text-embedding-3-small"

# One extremis client per namespace (agent), reused across calls so we don't
# churn Postgres connections; a per-namespace lock serialises access. A shared
# embedder (a stateless OpenAI client) is reused across all namespaces.
_clients: dict[str, Any] = {}
_locks: dict[str, asyncio.Lock] = {}
_embedder: Any = None


def _enabled() -> bool:
    return bool(settings.extremis_store)


def _make_embedder() -> Any:
    """A 384-dim OpenAI embedder, injected so extremis never loads MiniLM/torch."""
    import os

    import openai

    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    class _OpenAI384:
        dim = _EMBED_DIM

        def embed(self, text: str) -> list[float]:
            return self.embed_batch([text])[0]

        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            resp = client.embeddings.create(input=texts, model=_EMBED_MODEL, dimensions=_EMBED_DIM)
            return [d.embedding for d in resp.data]

    return _OpenAI384()


def _get_client(namespace: str) -> Any:
    global _embedder
    client = _clients.get(namespace)
    if client is None:
        from extremis import Extremis  # lazy: only import when actually used
        from extremis.config import Config

        from app.memory.pg_store import NamespacedPgVectorStore

        if _embedder is None:
            _embedder = _make_embedder()
        config = Config(namespace=namespace)
        # Inject our namespaced pgvector store (1536-dim, bug-fixed); the rest of
        # extremis (embedder, KG, log, API) is used as-is.
        store = NamespacedPgVectorStore(config.postgres_url, config)
        client = Extremis(config=config, local=store, embedder=_embedder)
        _clients[namespace] = client
    return client


async def _call(namespace: str, fn: Callable[[Any], Any]) -> Any:
    """Run a sync extremis call in a thread, serialised per namespace. On error,
    evict the client so a poisoned Postgres connection can't wedge later calls."""
    lock = _locks.setdefault(namespace, asyncio.Lock())
    async with lock:
        try:
            return await asyncio.to_thread(fn, _get_client(namespace))
        except Exception:
            _clients.pop(namespace, None)  # next call rebuilds a fresh connection
            raise


async def remember(
    agent_id, content: str, role: str = "assistant", conversation_id: str = "default"
) -> None:
    """Persist a memory for an agent (cheap: embed + store, no LLM). Best-effort."""
    if not _enabled() or not content or not content.strip():
        return
    try:
        await _call(
            str(agent_id),
            lambda mem: mem.remember(content.strip(), role=role, conversation_id=conversation_id),
        )
    except Exception as exc:  # noqa: BLE001 — memory writes never fail a run
        log.warning("extremis.remember_failed", detail=str(exc))


class ExternalMemoryStrategy:
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self._fallback = BufferMemory(max_messages)

    async def load(self, agent_id, ctx: MemoryContext, session: AsyncSession) -> list[dict]:
        recalled = await self._recall(agent_id, ctx)
        buffer = await self._fallback.load(agent_id, ctx, session)
        if recalled is None:  # extremis unavailable -> pure buffer fallback
            return buffer
        # Long-term memories first, then the in-run buffer.
        return recalled + buffer

    async def _recall(self, agent_id, ctx: MemoryContext) -> list[dict] | None:
        if not _enabled():
            return None
        query = (ctx.query or "").strip()
        if not query:
            return []  # nothing to retrieve against yet
        try:
            results = await _call(
                str(agent_id), lambda mem: mem.recall(query, limit=self.max_messages)
            )
            return [
                {"role": "system", "content": f"[memory] {r.memory.content}"}
                for r in results
            ]
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            log.warning("extremis.recall_unavailable", detail=str(exc))
            return None
