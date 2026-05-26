# AI Agent Orchestration Platform — Build Plan

## Context

This is the Yuno AI Engineer hiring challenge (`~/Downloads/Yuno AI Engineer Challenge.pdf`). We must deliver a working repo + README + recorded demo for a platform where users **create AI agents** (personality, tools, schedules, memory, limits), **wire them into collaborative workflows**, run them on a **real runtime** executing **real tools**, have them **communicate asynchronously**, and expose **at least one agent through an external messaging channel** (Telegram) for a live human conversation. Everything must run locally with a single setup command and ship with a visual web UI.

Grade weights drive priorities: **working end-to-end demo 40% · architecture & code quality 30% · UI/UX & configurability 20% · documentation 10%.**

**Decisions made (locked):**
- **Stack:** Python — FastAPI control plane + separate asyncio worker pool + LangGraph runtime + PostgreSQL + Redis; **Next.js** frontend. (Justified in README: real separation of UI / runtime / persistence; LangGraph gives the two-layer execution model; a stuck agent can't freeze the UI.)
- **Channel:** **Telegram** (real, working integration). Slack + WhatsApp ship as documented stubs proving the `Channel` abstraction.
- **Scope:** **Full brief** — DSL parser, transactional outbox, sandboxed `python_exec` container, OTel, versioned workflows, schema-driven forms all built.
- **Memory:** **extremis wired for real** as a selectable per-agent `ExternalMemoryStrategy`, alongside Buffer / Summary / ChannelScoped strategies.

New project location: `/Users/ashwanijha/yuno-orchestrator` (fresh git repo, `git init`).

The companion design doc (the long brief the user pasted) is the canonical architecture reference and will be checked in verbatim as `docs/architecture.md`. This file is the *execution* plan layered on top of it.

---

## Target architecture (recap)

Four processes, one `docker-compose up`:
- **Next.js UI (3000)** — Agent/Workflow CRUD, React Flow workflow builder, run timeline + live monitor (WebSocket).
- **FastAPI control plane (8000)** — REST, WebSocket gateway, channel webhooks, run scheduler.
- **Worker pool (asyncio)** — LangGraph outer (workflow) + inner (ReAct agent) graphs, tool runtime.
- **Redis** — pub/sub for live UI, run queue, rate limits, agent inbox.
- **Postgres** — source of truth: agents, workflows + immutable versions, runs, steps, messages, tool_invocations, channels, bindings, schedules, outbox.
- **code-runner** — separate no-network container for sandboxed `python_exec`.

Two invariants enforced in code:
1. **Agents are config (DB rows); the runtime is generic code.** Adding an agent = a row, never new Python.
2. **Every side effect is a Postgres row first, then a Redis publish.** Never the reverse. Redis is transport, Postgres is truth.

---

## Repository layout

Build to the tree in `docs/architecture.md §11`. Key roots:
- `backend/app/runtime/` — `outer_graph.py`, `inner_graph.py`, `state.py`, `executor.py`, `dsl/` (heart of the system, **zero FastAPI imports**).
- `backend/app/{api,channels,tools,memory,guardrails,schedules,observability,templates}/`
- `backend/app/db/{models.py,session.py,repositories/}` + `alembic/`
- `frontend/app/`, `frontend/components/{workflow-builder,timeline,agent-config,ui}/`, `frontend/lib/{api.ts,ws.ts}`
- `code-runner/` — Dockerfile + `runner.py`
- `scripts/seed.py`, `scripts/reset_db.py`
- `docker-compose.yml`, `README.md`, `docs/`, `.env.example`

---

## Build phases (milestones, in dependency order)

### Phase 0 — Scaffold & infra
- `git init`; `docker-compose.yml` with postgres, redis, backend, worker, frontend, code-runner.
- `backend/pyproject.toml`: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, langgraph, anthropic, openai, redis, apscheduler, lark (DSL), structlog, opentelemetry, python-telegram-bot, tavily-python, httpx, pytest.
- `frontend`: Next.js (App Router) + Tailwind + shadcn + React Flow + CodeMirror + a WS client.
- `.env.example` (ANTHROPIC_API_KEY, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TAVILY_API_KEY, DATABASE_URL, REDIS_URL, EXTREMIS_STORE).
- Health endpoints: `/health`, `/health/db`, `/health/redis`, `/health/channels`.
- **Milestone:** `docker-compose up` boots all services; health checks green.

### Phase 1 — Data model & repositories
- SQLAlchemy models for every table in `docs/architecture.md §4`: `agents, workflows, workflow_versions, channels, channel_bindings, runs, steps, messages, tool_invocations, schedules, outbound_messages`. Cost columns denormalized up the hierarchy (message → step → run).
- Alembic initial migration.
- `repositories/` per aggregate (agents, workflows, runs, channels) — all data access goes through here; API handlers stay thin.
- **Milestone:** migrations apply; repo unit tests for CRUD pass.

### Phase 2 — Two-layer runtime (the core, build first and carefully)
- `runtime/state.py`: `WorkflowState` TypedDict (run_id, messages, artifacts, current_agent, iteration_count, metadata).
- `runtime/inner_graph.py`: ReAct LangGraph — `prepare → llm → router → {tool|end}` with guardrail chokepoint at `router`. Each node transition persists a `steps`/`messages` row.
- `runtime/outer_graph.py`: LangGraph `StateGraph` built from the workflow `graph` JSONB. Nodes are agents (generic node looks up agent config by id, runs its inner graph, persists, returns). Edges carry DSL conditions.
- `runtime/dsl/`: Lark grammar + AST + evaluator for guarded edges (`artifacts.x == "y"`, `iteration_count < 3`, `last_message.contains(...)`). **No `eval`.** ~200 lines.
- `runtime/executor.py`: worker entrypoint — pops run from Redis queue, loads workflow version, runs outer graph, writes results.
- **Cost tracking** (`observability/cost.py`): per-provider pricing tables; compute cost at write time on every `messages` row.
- **Milestone:** `test_workflow_execution` — fixture workflow, 2 stubbed deterministic agents, trigger a run, assert steps+messages persisted in order, costs summed, run reaches `completed`.

### Phase 3 — Tools, memory, guardrails
- `tools/`: `base.py` (Tool protocol + `ToolContext` with ReadOnlySession, allowlisted HTTP, BudgetTracker), `web_search` (Tavily), `http_request` (domain allowlist), `send_to_agent` (writes message row + publishes to recipient Redis inbox, outbox-mediated), `send_to_channel`, `python_exec` (calls code-runner container over unix socket). `registry.py`.
- `memory/`: `base.py` (MemoryStrategy protocol + MemoryContext), `buffer.py`, `summary.py` (rolling LLM summary), `channel_scoped.py` (keyed to `channel_external_id` for cross-run user memory), **`external.py` → extremis** (`mcp__extremis__memory_recall`/`remember`/`consolidate` via the extremis Python client / MCP store; selectable per agent in `memory_policy`).
- `guardrails/`: `Guardrails` pydantic model + `GuardrailEnforcer` returning `CONTINUE|TERMINATE|PAUSE_FOR_APPROVAL`, invoked at every router transition. Implement: max_iterations, max_tokens_per_turn, **max_cost_per_run_usd (the demo circuit breaker)**, max_tool_calls, allowed_tools, require_approval_for, pii_redaction (regex stub), output_max_length.
- **Milestone:** unit tests — DSL parser (table-driven), cost calculator per provider, each guardrail policy, memory buffer eviction + summary trigger; extremis round-trip integration test.

### Phase 4 — Channels (Telegram real, outbox delivery)
- `channels/base.py`: `Channel` protocol (`initialize`, `send`, `parse_webhook`, `health_check`) + `InboundMessage`. `registry.py`.
- `channels/telegram.py`: real impl (signature/secret-token verification, parse, send). `slack.py` + `whatsapp.py` as documented stubs.
- `api/webhooks.py`: `POST /webhooks/{channel_id}` → parse+verify → resolve `channel_bindings` → resolve workflow → enqueue run (`trigger_type='channel'`) → return 200 immediately.
- **Transactional outbox**: agent `send_to_channel` writes `outbound_messages` in the same txn as the `messages` row; a dispatcher polls `pending` rows, calls `channel.send`, retries w/ backoff, marks sent/failed.
- Prompt-injection hardening: prefix external channel content with an explicit "from external user" marker.
- **Milestone:** `test_channel_roundtrip` — simulated Telegram webhook → binding resolved → run triggered → outbound row written → dispatcher (mocked API) sends. Live: real bot replies in Telegram.

### Phase 5 — Scheduler & real-time events
- `schedules/scheduler.py`: APScheduler reads `schedules`, enqueues runs on cron.
- `observability/events.py`: worker publishes to `channel:run:{run_id}` **after** Postgres commit; `api/ws.py` subscribes and forwards to UI clients. Backpressure: drop slow clients; they reconnect and replay from `messages` by `run_id + ts`.
- `structlog` context binding (run_id/step_id/agent_id on every line); OTel spans per step exported to optional Jaeger container (behind a flag).
- **Milestone:** triggering a run streams live events to a connected WS client; killing+reconnecting the client replays cleanly.

### Phase 6 — Frontend (priority order; cut from the bottom if needed)
1. **Agent & Workflow config** — schema-driven forms (RJSF or equivalent) over the JSONB config + guardrails; versioned workflow saves with one-click "run old version".
2. **Visual workflow builder** — React Flow, custom nodes per agent role, edge condition editor (CodeMirror with the DSL grammar), live validation (disconnected/unreachable/uncontrolled cycles), dry-run with live path highlight, inspect-node side panel.
3. **Run timeline & live monitor** — the demo-defining surface: one row per agent, blocks scaled to duration, tool calls + inter-agent messages as annotations, hover for tokens/cost/latency, click for full message thread; live block animation over WebSocket.
- `frontend/lib/api.ts` typed from backend OpenAPI (`openapi-typescript`); `lib/ws.ts` subscriber.
- **Milestone:** create agent in UI → build 2-agent workflow → trigger → watch timeline animate → see cost.

### Phase 7 — Templates, seed, tests, docs, demo
- `templates/`: **two** prebuilt workflows — `market_intel.py` (Researcher → Analyst → Critic loop → Briefer → Telegram) demonstrating a **feedback loop + conditional edge**, and `personal_assistant.py` (Telegram-driven conversational agent with ChannelScoped/extremis memory + scheduled digest).
- `scripts/seed.py` creates templates + sample agents + a channel binding.
- Tests: 3 integration (`test_agent_lifecycle`, `test_workflow_execution`, `test_channel_roundtrip`) + targeted units + one Playwright golden-path E2E.
- **README** per `docs/architecture.md §16`: what/why, 60s demo gif, ≤5-command quickstart, topology diagram, runtime justification, "how to add a channel/tool/template" (with the concrete Discord extensibility claim), scope-vs-cut table, failure-modes table (§14), future work (extremis already wired → note as the differentiator; peekr compatibility note). `docs/{adding-a-channel,adding-a-tool,workflow-dsl}.md`.
- **Demo recording** scripted and recorded by ~day 10: dashboard → create agent → wire 2 agents in builder → trigger via Telegram → live timeline → cost tracking → show the conditional loop + cost circuit breaker terminating gracefully.

---

## Files to create (representative, not exhaustive)

Runtime core (read in isolation, no web imports):
`backend/app/runtime/{state,inner_graph,outer_graph,executor}.py`, `backend/app/runtime/dsl/{grammar.lark,parser.py,evaluator.py}`

Persistence: `backend/app/db/models.py`, `backend/app/db/repositories/{agents,workflows,runs,channels}.py`, `backend/alembic/versions/0001_init.py`

Extensible seams (the abstractions that score architecture points):
`backend/app/channels/base.py` + `telegram.py`, `backend/app/tools/base.py` + per-tool files, `backend/app/memory/base.py` + `{buffer,summary,channel_scoped,external}.py`, `backend/app/guardrails/{enforcer,policies}.py`

Frontend: `frontend/components/workflow-builder/`, `frontend/components/timeline/`, `frontend/components/agent-config/`, `frontend/lib/{api,ws}.ts`

Infra/docs: `docker-compose.yml`, `code-runner/{Dockerfile,runner.py}`, `scripts/{seed,reset_db}.py`, `README.md`, `docs/*.md`, `.env.example`

## Reuse from existing code
The `~/agentwork` repo uses a different stack (Next.js + Drizzle/SQLite + custom polling loop) — **not** directly importable. Reusable *patterns* only: Anthropic SDK usage, the extremis client init (`extremis.Extremis(Config(namespace=...))`) for `memory/external.py`, and the API-key hashing pattern if we add auth later. Treat this as a clean greenfield build.

---

## Verification

End-to-end, in order:
1. `cp .env.example .env` (fill keys) → `docker-compose up` → all health endpoints green.
2. `python scripts/seed.py` → two templates + sample agents visible in UI.
3. **Backend tests:** `pytest backend/tests` — the 3 integration tests + units pass. Confirms persistence, workflow execution, cost summing, channel wiring, DSL, guardrails, extremis round-trip.
4. **UI golden path:** Playwright E2E (create agent → run workflow → timeline renders expected steps).
5. **Live Telegram:** point the bot webhook at the local tunnel, send a message to the bound agent, watch the run appear in the timeline, get a reply in Telegram. This is the 40% demo.
6. **Guardrail demo:** set a run's `max_cost_per_run_usd` to $0.10 and confirm the workflow terminates gracefully with a red block in the timeline and `runs.error` set.
7. **Extensibility proof:** show the diff to add the Slack stub (only `channels/slack.py` + registry line + UI config form) — no orchestrator/agent/workflow changes.

## Primary risk
Not technical — the **demo recording**. Script it before building, record by day 10, two takes. If a feature can't earn screen time, question whether it earns build time.
