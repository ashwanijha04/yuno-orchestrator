"""NamespacedPgVectorStore — a thin, vendored fix over extremis 0.3.1's Postgres
store, injected into Extremis(local=...).

extremis 0.3.1's stock PostgresMemoryStore has three gaps for our use:
  1. the schema hardcodes `embedding vector(384)` (sized for the local MiniLM
     model) — we want full 1536-dim OpenAI embeddings;
  2. it has NO namespace column or filter, so every agent would recall every
     other agent's memories (the sqlite store does isolate by namespace);
  3. its recall "touch" step runs `UPDATE ... WHERE id = ANY(%s)` passing text
     against a uuid column, which throws.

We override only the schema + store + search; everything else (embedder, KG,
log, consolidation, the Extremis API, types) is reused from extremis unchanged.
`id` is TEXT here, which both keeps per-row ids as the string uuids extremis
already passes and sidesteps the uuid/text mismatch in the touch query.
"""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from extremis.storage.postgres import PostgresMemoryStore, _row_to_memory
from extremis.types import Memory, MemoryLayer, RecallResult

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS memories (
    id                  TEXT PRIMARY KEY,
    namespace           TEXT NOT NULL DEFAULT 'default',
    layer               TEXT NOT NULL
                            CHECK (layer IN ('episodic','semantic','procedural','identity')),
    content             TEXT NOT NULL,
    embedding           vector(1536),
    score               REAL NOT NULL DEFAULT 0.0,
    confidence          REAL NOT NULL DEFAULT 0.5,
    metadata            JSONB NOT NULL DEFAULT '{}',
    source_memory_ids   TEXT[] NOT NULL DEFAULT '{}',
    validity_start      TIMESTAMPTZ NOT NULL,
    validity_end        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed_at    TIMESTAMPTZ,
    access_count        INTEGER NOT NULL DEFAULT 0,
    do_not_consolidate  BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_memories_ns ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON memories USING hnsw (embedding vector_cosine_ops);
"""


class NamespacedPgVectorStore(PostgresMemoryStore):
    def _init_schema(self) -> None:
        with self._conn.cursor() as cur:
            # Auto-heal: if a stock (namespace-less / 384-dim) `memories` table
            # exists from a prior run, drop it — it's a rebuildable cache.
            cur.execute("SELECT to_regclass('public.memories')")
            exists = cur.fetchone()[0] is not None
            if exists:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='memories' AND column_name='namespace'"
                )
                if cur.fetchone() is None:
                    cur.execute("DROP TABLE memories CASCADE")
            cur.execute(_SCHEMA)
        self._conn.commit()

    def store(self, memory: Memory) -> Memory:
        self._ensure_clean()
        import numpy as np

        embedding = np.array(memory.embedding, dtype=np.float32) if memory.embedding else None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories (
                    id, namespace, layer, content, embedding, score, confidence,
                    metadata, source_memory_ids, validity_start, validity_end,
                    created_at, last_accessed_at, access_count, do_not_consolidate
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    score = EXCLUDED.score,
                    confidence = EXCLUDED.confidence,
                    metadata = EXCLUDED.metadata,
                    validity_end = EXCLUDED.validity_end,
                    last_accessed_at = EXCLUDED.last_accessed_at,
                    access_count = EXCLUDED.access_count
                """,
                (
                    str(memory.id), self._config.namespace, memory.layer.value,
                    memory.content, embedding, memory.score, memory.confidence,
                    json.dumps(memory.metadata), [str(s) for s in memory.source_memory_ids],
                    memory.validity_start, memory.validity_end, memory.created_at,
                    memory.last_accessed_at, memory.access_count, memory.do_not_consolidate,
                ),
            )
        self._conn.commit()
        return memory

    def search(
        self,
        query_embedding: list[float],
        layers: Optional[list[MemoryLayer]] = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[RecallResult]:
        import numpy as np

        from extremis.storage.recall_reason import build_reason

        vec = np.array(query_embedding, dtype=np.float32)
        layer_values = [lyr.value for lyr in layers] if layers else None

        with self._conn.cursor(cursor_factory=self._dict_cursor()) as cur:
            cur.execute(
                """
                SELECT *,
                    1 - (embedding <=> %(vec)s) AS relevance,
                    (1 - (embedding <=> %(vec)s))
                      * (1 + %(alpha)s * tanh(score))
                      * exp(-0.693147 * EXTRACT(EPOCH FROM (NOW() - created_at))
                            / 86400.0 / %(half_life)s) AS final_rank
                FROM memories
                WHERE embedding IS NOT NULL
                  AND validity_end IS NULL
                  AND namespace = %(ns)s
                  AND (%(layers)s::text[] IS NULL OR layer = ANY(%(layers)s::text[]))
                ORDER BY final_rank DESC
                LIMIT %(limit)s
                """,
                {
                    "vec": vec, "alpha": self._config.rl_alpha,
                    "half_life": float(self._config.recency_half_life_days),
                    "ns": self._config.namespace, "layers": layer_values, "limit": limit,
                },
            )
            rows = cur.fetchall()

        results: list[RecallResult] = []
        for row in rows:
            if float(row["final_rank"]) < min_score:
                continue
            mem = _row_to_memory(row)
            results.append(RecallResult(
                memory=mem, relevance=float(row["relevance"]),
                final_rank=float(row["final_rank"]),
                reason=build_reason(float(row["relevance"]), float(row["score"]),
                                    int(row["access_count"]), row["created_at"], mem.layer),
            ))

        if results:  # touch access stats — id is TEXT here, so ANY(text[]) works
            ids = [str(r.memory.id) for r in results]
            with self._conn.cursor() as cur:
                cur.execute(
                    "UPDATE memories SET access_count = access_count + 1, "
                    "last_accessed_at = NOW() WHERE id = ANY(%s)",
                    (ids,),
                )
            self._conn.commit()
        return results
