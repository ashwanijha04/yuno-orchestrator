"""extremis long-term memory round-trip (remember -> recall), namespaced.

Skipped cleanly when extremis isn't installed, no store is configured, or no
OpenAI key is present — so the suite stays green offline / in CI. When those are
present (the docker stack), it exercises the real embedded extremis + pgvector
path: write a memory under one namespace, recall it, and confirm a different
namespace can't see it.
"""

from __future__ import annotations

import os

import pytest

from app.config import settings


def _available() -> bool:
    if not settings.extremis_store or not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import extremis  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(not _available(), reason="extremis/store/key not configured")


async def test_remember_recall_is_namespaced():
    import uuid

    from app.memory.base import MemoryContext
    from app.memory.external import ExternalMemoryStrategy, remember

    ns = f"test-agent-{uuid.uuid4().hex[:8]}"
    other = f"test-agent-{uuid.uuid4().hex[:8]}"
    fact = "The codename for the spring release is Project Heron."

    await remember(ns, fact, role="assistant", conversation_id="t1")

    strat = ExternalMemoryStrategy(max_messages=5)
    hits = await strat._recall(ns, MemoryContext(run_id=None, query="what is the spring release codename?"))
    assert hits is not None and any("Heron" in h["content"] for h in hits)

    # Isolation: a different agent's namespace must not see it.
    miss = await strat._recall(other, MemoryContext(run_id=None, query="what is the spring release codename?"))
    assert not (miss or [])
