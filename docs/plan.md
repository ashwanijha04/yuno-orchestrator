# AI Agent Orchestration Platform — Build Plan

## Context

This is the Yuno AI Engineer hiring challenge (`~/Downloads/Yuno AI Engineer Challenge.pdf`). We must deliver a working repo + README + recorded demo for a platform where users **create AI agents** (personality, tools, schedules, memory, limits), **wire them into collaborative workflows**, run them on a **real runtime** executing **real tools**, have them **communicate asynchronously**, and expose **at least one agent through an external messaging channel** (Telegram) for a live human conversation. Everything must run locally with a single setup command and ship with a visual web UI.

Grade weights drive priorities: **working end-to-end demo 40% · architecture & code quality 30% · UI/UX & configurability 20% · documentation 10%.**

**Decisions made (locked):**
- **Stack:** Python — FastAPI control plane + separate asyncio worker pool + LangGraph runtime + PostgreSQL + Redis; **Next.js** frontend.
- **Channel:** **Telegram** (real). Slack + WhatsApp ship as documented stubs proving the `Channel` abstraction.
- **Scope:** **Full brief, everything built** — plus the two load-bearing subsystems below (workflow creation, unified harness).
- **Memory:** **extremis wired for real** as a selectable per-agent `ExternalMemoryStrategy` alongside Buffer / Summary / ChannelScoped.

New project location: `/Users/ashwanijha/yuno-orchestrator` (git repo already initialized on `main`; plan copied to `docs/plan.md`). The long architecture brief is the canonical reference, checked in as `docs/architecture.md`. This file is the execution plan on top of it.

---

## Two invariants enforced in code
1. **Agents are config (DB rows); the runtime is generic code.** Adding an agent = a row; adding a workflow = a `graph` JSONB; never new Python.
2. **Every side effect is a Postgres row first, then a Redis publish.** Redis is transport, Postgres is truth.

## System topology
- **Next.js UI (3000)** — Agent/Workflow CRUD, React Flow builder, run timeline + live monitor (WebSocket), eval pages.
- **FastAPI control plane (8000)** — REST, WebSocket gateway, channel webhooks, scheduler.
- **Worker pool (asyncio)** — LangGraph outer (workflow) + inner (ReAct agent) graphs, tool runtime, all LLM calls flow through the **harness**.
- **Redis** — pub/sub, run queue, rate limits, agent inbox.
- **Postgres** — source of truth (all tables below).
- **code-runner** — separate no-network container for sandboxed `python_exec`.

---

# Subsystem A — Workflow creation (where the "platform" value lives)

### Three creation paths, one artifact
All three produce the **same** `workflows` row with the same `graph` JSONB. The builder is just a UI over the same API tests and templates use.
1. **Pre-built templates** — shipped in code, loaded by `scripts/seed.py`; users clone → edit. (Rubric requires ≥2.)
2. **Visual builder** — React Flow canvas; primary creation path, most UI effort.
3. **JSON import / `POST /workflows`** — falls out for free if the schema is right; used by templates, tests, git-versioned workflows.

### The graph schema (the contract everything depends on)
Top-level: `version, name, description, entry_node, variables, nodes, edges`.
- **`variables`** — typed input signature (`{type, required, default}`). Manual trigger → form generated from this; channel trigger → message becomes a default variable. No more black-box "some text" workflows.
- **node `input_mapping`** — JSONPath-style slice of state each node needs (`$.artifacts.x`, `$.variables.topic`). Makes agents reusable across workflows.
- **node `output_key`** — where the node's output lands in `artifacts`; downstream nodes reference it explicitly. Clean state flow, no implicit message-passing.
- **node `config_overrides` / `harness_overrides`** — per-node overrides of agent defaults (e.g. `max_iterations` here vs elsewhere) without cloning agents.
- **edge `condition` + `priority`** — DSL expression; edges from the same source evaluated in priority order, first match wins; unconditional edges are priority-∞ fallback → `END` if none match. Avoids ambiguity without forcing mutually-exclusive conditions.

### Node types
`agent` (run inner graph), `condition` (pure routing, no LLM), `transform` (deterministic state map), `human` (pause for approval, resume on UI action), `parallel` (fan-out N children, join), `channel_in` (await inbound), `channel_out` (send without an agent).
- **Ship now:** `agent`, `condition`, `channel_out`.
- **Stub (schema admits them, executor returns not-implemented):** `transform`, `human`, `channel_in`.
- **Stretch (week 2 if time):** `parallel` — the differentiator most candidates won't have.

### Dynamic outer-graph compilation (`runtime/outer_graph.py`)
The outer LangGraph is **generated from the workflow JSON at run start**, not handwritten per workflow. Build `StateGraph(WorkflowState)`; add one node per graph node via a per-type executor (`AgentNodeExecutor`, `ConditionNodeExecutor`, `ChannelOutExecutor`); group edges by source — single unconditional edge → `add_edge`, otherwise `add_conditional_edges` with a priority-sorted router that evaluates DSL conditions and falls back to `END`. ~150 lines. **Compile per run, not per workflow** (compilation is single-digit ms; caching invites state-sharing bugs).

### Validation (`runtime/validation.py`, canonical in Python; TS copy is a UX nicety — write twice, don't share)
Reject a workflow when: entry node missing/undeclared; node references nonexistent `agent_id`; node unreachable from entry; non-terminal node with no outgoing edges; cycle with no termination condition on any edge; condition references unknown variables/artifacts; `input_mapping` references an artifact produced later (outside cycles); two edges from one source overlap at the same priority. Runs **client-side** for live builder feedback and **server-side** on save.

### Template system (`backend/app/templates/`)
A template is a dict with `template_id, name, description, required_agents[] (role_key + default_config), graph` — graph uses **`role_key`s, not agent UUIDs**. Cloning: create agents from `default_config` (or map role_keys to existing agents), substitute role_keys → agent_ids, create the workflow row, open the builder. **Adding a template = one file in `templates/` + one line in `templates/__init__.py`**; documented in `docs/adding-a-template.md` with a worked example.
- **Templates to ship:** `market_intel.py` (Researcher → Analyst → Critic **feedback loop** → Briefer → Telegram) and `personal_assistant.py` (Telegram-bound Router → Specialists, ChannelScoped/extremis memory, scheduled digest).

### Versioning & edit semantics
Editing a workflow creates a new `workflow_versions` row (immutable). In-flight runs reference `(workflow_id, version)` and continue against the **old** version; new runs use the new one. UI: version dropdown, old versions load read-only with "Restore as new version"; "Re-run with same inputs" uses the run's recorded version. ~4h, and the answer to "what if I edit a workflow while it's running?"

### Channel ↔ workflow binding (what makes the system cohere)
Inbound Telegram message → `/webhooks/{channel_id}` → `parse_webhook` → lookup `channel_binding` by `(channel_id, external_id)`:
- binding has `workflow_id` → trigger that workflow with the message as input variable;
- else agent's `default_workflow` if set;
- else a **synthetic single-node workflow** (not persisted) that just runs the agent's inner graph and replies — the "talk to an agent" experience.
The platform feature is binding a channel to a **multi-agent** workflow (Personal Assistant template does this). Don't hardcode "one bot per agent."

### Visual builder (React Flow) — four panels
Left **palette** (drag agents from `agents` table; node primitives; pre-wired "patterns" = graph fragments). Center **canvas** (custom renderers: agent shows name/role, condition shows expression, channel shows binding; edges label conditions). Right **inspector** (context-sensitive node/edge config; **CodeMirror DSL editor** with syntax highlight + autocomplete for `artifacts.*`/`variables.*`/`iteration_count`). Top bar: **Save** (new version), **Test Run** (variables modal → live execution highlighted on canvas), **Versions** (history + diff), **Validate** (static analysis with inline warnings).

### Workflow-specific tests
`test_graph_validation` (table-driven, ~30 invalid graphs → right error code); `test_conditional_routing` (branches exercised, assert path via `steps` rows); `test_workflow_versioning` (run on v1 survives edit to v2; replay still uses v1).

---

# Subsystem B — The unified harness (the most defensible layer)

### Thesis
Everything that happens around every LLM call is one lifecycle observed at different injection points: build request → call (retries/timeouts/provider quirks) → record → validate → replay → judge. **Production, test, eval, replay are configurations of one runtime, not separate systems.** No `if testing:` anywhere — test mode is `provider=StubProvider`, demo mode is `provider=ReplayProvider`, eval mode adds an interceptor.

### Core abstraction (`harness/call.py`, `harness/executor.py`)
`HarnessedCall` is the per-invocation transaction object: identity (call/run/step/agent ids), `request: LLMRequest`, resolution (`provider`, `cost_model`, `validators[]`, `interceptors[]`), result (`response`, `attempts[]`, `validation_results[]`), and observation hooks (`events`, `trace_context`). `HarnessExecutor.execute` runs six phases: (1) interceptor `before` (block/modify), (2) execute with retry on transient + validation failures, (3) validate, (4) success normalize, (5) interceptor `after`, (6) **transactional persist then `events.emit`**. The inner graph uses the harness from day one — no retrofit.

### Providers (`harness/providers/`, the ONLY layer that knows provider shapes)
Protocol: `complete`, `stream`, `estimate_tokens`, `cost_model`. Ship five: **Anthropic / OpenAI / Bedrock** (thin adapters: auth via env, tool-call format translation, system-prompt placement, structured-output APIs, streaming normalization, 429/`Retry-After`); **StubProvider** (deterministic, backed by a YAML `Script` resolved by `agent_id`/`call_index`/`content_contains`/`messages_hash`, first-match-wins, latency + error injection); **ReplayProvider** (replays recorded real calls in sequence with original latency × speed_factor). **Discipline: never write `if provider == "anthropic":` outside `providers/anthropic.py`** — extend `LLMRequest`/`LLMResponse` with optional fields instead. Adding Gemini = implement `GeminiProvider`, register; nothing else changes.

### Scripts (`tests/scripts/*.yaml`)
First-class, checked-in, diffable, Jinja2-templated, composable (`include:`), generatable from real runs (`harness script generate <run_id>`). The seam that makes the test harness usable.

### Validators (`harness/validators/`) — pass / fail / fail-with-retry
`JSONSchemaValidator` (reinject error + schema, retry ≤2 — recovers ~90% of malformed output), `ToolCallValidator`, `ContentSafetyValidator` (redact, no retry), `CitationValidator` (per-agent opt-in), `MaxLengthValidator` (truncate, log). Listed in `agents.guardrails.validators`; adding one = a class + a config entry.

### Interceptors (`harness/interceptors/`) — cross-cutting before/after
`CostCapInterceptor` (**the demo circuit breaker** — block when `run.total_cost + estimate > max_cost_per_run_usd`, return synthetic budget-exceeded response), `IterationCapInterceptor`, `PIIRedactionInterceptor` (when bound to external channel), `EvalRecorderInterceptor` (eval mode only), `RecordingInterceptor` (record mode only), `TraceInterceptor` (OTel span per call). The seam where peekr / Langfuse plug in later — adding observability = one interceptor.

### Five modes, one architecture (README table)
| Mode | Provider | Interceptors | Use |
|---|---|---|---|
| live | Anthropic/OpenAI/Bedrock | Trace, CostCap, IterationCap, PIIRedact | production |
| record | real | live + Recording | capture demo / build fixtures |
| replay | Replay | Trace | deterministic demo + tests |
| stub | Stub | Trace | unit/integration tests |
| eval | live or replay | live + EvalRecorder | quality measurement |

Same outer/inner graph, workflows, tools — only harness config changes. This table answers "how do you test in CI / measure quality / record the demo?" in one breath.

### Recording & replay (`harness/recording/`)
`RecordingInterceptor` writes every completed call to `llm_recorded_calls`; `ReplayProvider` reads them back in `sequence` order. `LLM_MODE=record RECORDING_NAME=demo_market_intel make run` → go through the flow → auto-saved; `LLM_MODE=replay …` → free, deterministic, offline demos. Roundtrip test asserts replayed final state is byte-identical to the recorded run.

### Eval framework, on the same primitives (`harness/eval/`)
An eval is a run with eval interceptors + a downstream judge — `execute_target` is the **same code path production uses**, so evals catch real regressions. Tables: `eval_datasets, eval_examples, eval_runs, eval_results`. Judge protocol returns `{scores{criterion→0..1}, rationale, passed, cost_usd}`. Ship `ExactMatchJudge` (free), `LLMJudge` (itself a `HarnessedCall` — traced/cost-tracked/replayable), `CompositeJudge` (weighted). Runner: bounded-parallel (`Semaphore(5)`), per-example execute-then-judge, emit live events. UI: `/evals` (datasets + pass-rate sparkline), `/evals/{dataset}`, `/evals/runs/{id}` (input|expected|actual|scores|pass|rationale + **link to the actual run's timeline**). Datasets: 10 examples per template, rubric-judged.

### Harness CLI (`harness/cli.py`, ~300 lines over REST)
`harness record start/stop/list/show`, `harness eval run/status/diff`, `harness script generate/validate/run`, `harness providers list/test`, `harness cost summary`. Recording/eval/script-gen are operational, not UI, workflows; pulling up a terminal in the walkthrough is more compelling than clicking.

### Config hierarchy (`harness/config.py: HarnessConfigResolver`)
env defaults (`LLM_MODE`, `LLM_PROVIDER_DEFAULT`, `LLM_RECORDING_NAME`, `LLM_SCRIPT_PATH`) **<** per-agent `harness{max_attempts, retry_on, validators[], interceptors[]}` **<** per-node `harness_overrides`. Resolution in one place.

### Harness tests
`test_executor` (retry on rate-limit/validation, fatal propagation, interceptor ordering), `test_stub_provider`, `test_replay_provider`, `test_validators` (table-driven), `test_cost_models` (**Decimal not float**), `test_recording` (record→replay roundtrip byte-identical), `test_eval_runner` (end-to-end against stub target).

---

# Subsystem C — Multimodal (images real, video designed-not-built)

Text is the baseline; **images are built end-to-end**, video is parsed + documented. Unsupported media → **graceful text reply** ("I can't process that media type yet"), never a silent failure.

- **Channels (`telegram.py`).** `parse_webhook` handles `photo`/`document(image/*)` updates: resolve `file_id → getFile → download bytes`, emit `Attachment{type, mime, file_id, bytes|url}` on `InboundMessage`. `voice`/`video`/other → `Attachment{type=unsupported}` so the runtime can issue the graceful reply. (Voice transcription explicitly deferred.)
- **Harness (`call.py`, providers).** `LLMRequest.content` becomes **typed content blocks** (`TextBlock | ImageBlock{mime, data}`), not a bare string. Anthropic + OpenAI providers encode images natively (base64/image_url); Bedrock/Stub/Replay pass through. A capability flag (`provider.supports_images`) gates routing; if an agent's model can't see images, the prepare node substitutes a placeholder + sets the graceful-reply path. **Discipline holds:** image encoding lives only inside each provider.
- **Inner graph `prepare` node.** Builds multimodal content from `InboundMessage.attachments`; drops/annotates unsupported types and flags the run so `send_to_channel` returns the graceful message.
- **Persistence.** New `media_assets` table (id, run_id, message_id, channel_id, type, mime, storage_ref, bytes_or_url, created_at); `messages` gains a nullable `attachments JSONB` referencing asset ids. Media stored on a local volume (or Postgres large object for the demo), referenced — not inlined into `messages.content`.
- **UI timeline.** Render image thumbnails inline on the message/step; click → full view. Outbound images supported via `send_to_channel`.
- **Video (designed-not-built).** `parse_webhook` already yields the attachment; document the implementation path: ffmpeg frame-sampling → image blocks, or Whisper transcription, or a `GeminiProvider` for native video. Executor returns the graceful reply for now.

---

## Data model
Base tables per `docs/architecture.md §4`: `agents, workflows, workflow_versions, channels, channel_bindings, runs, steps, messages, tool_invocations, schedules, outbound_messages` (costs denormalized message→step→run). Workflow rows carry the `variables/nodes/edges` schema above.

Harness/eval additions:
- `llm_attempts` (one row per retry: provider, request, raw_response, error, validation_failures, latency_ms — UI shows "succeeded on attempt 2/3").
- `llm_recordings`, `llm_recorded_calls` (sequence-ordered request/response/latency).
- `eval_datasets, eval_examples, eval_runs, eval_results`.
- `media_assets` (image attachments) + `messages.attachments JSONB`.

Alembic migrations for all.

---

## Build phases (dependency order)

- **Phase 0 — Scaffold/infra.** docker-compose (postgres, redis, backend, worker, frontend, code-runner). `backend/pyproject.toml` (fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, langgraph, anthropic, openai, boto3, redis, apscheduler, lark, structlog, opentelemetry, python-telegram-bot, tavily-python, httpx, jinja2, pyyaml, pytest). Frontend: Next.js + Tailwind + shadcn + React Flow + CodeMirror. `.env.example`. Health endpoints. **Milestone:** `docker-compose up` boots; health green.
- **Phase 1 — Data model & repositories.** All models + Alembic initial migration + `repositories/` per aggregate. **Milestone:** migrations apply; CRUD repo tests pass.
- **Phase 2 — Harness foundation (days 2–4).** `HarnessExecutor`, `LLMProvider` protocol, AnthropicProvider, CostCap + Trace interceptors, JSONSchema validator, cost models (Decimal). Then **StubProvider + Script + first integration test** (unblocks all later testing). **Milestone:** `test_executor` + stub-backed integration test pass.
- **Phase 3 — Two-layer runtime.** `state.py`; `inner_graph.py` (prepare→llm→router→{tool|end}, guardrail chokepoint, every transition persists steps/messages, **all LLM calls via harness**); `outer_graph.py` (dynamic compile from JSON); `dsl/` (Lark grammar+AST+evaluator, no `eval`); `validation.py`; `executor.py` (worker pops run from Redis, runs outer graph). **Milestone:** `test_workflow_execution`, `test_graph_validation`, `test_conditional_routing`.
- **Phase 4 — Tools, memory, guardrails.** Tools: web_search (Tavily), http_request (allowlist), send_to_agent (outbox + Redis inbox), send_to_channel, python_exec (code-runner over unix socket). Memory: buffer, summary, channel_scoped, **external→extremis**. Guardrails enforcer (CONTINUE/TERMINATE/PAUSE) at router. **Milestone:** tool/memory/guardrail units + extremis round-trip.
- **Phase 5 — Channels + outbox + image ingestion.** `Channel` protocol; real `telegram.py` (text + photo download → `Attachment`, unsupported types flagged); slack/whatsapp stubs; `webhooks.py`; transactional outbox + dispatcher (backoff/retry); prompt-injection prefix. Harness `LLMRequest` → typed content blocks + image encoding in Anthropic/OpenAI providers; `media_assets` persistence; graceful-reply path for unsupported media. **Milestone:** `test_channel_roundtrip`; live bot reply; send a photo → agent describes it.
- **Phase 6 — Scheduler + real-time.** APScheduler; events publish post-commit; `ws.py` forwards; backpressure + replay from `messages`; structlog context binding; OTel→optional Jaeger. **Milestone:** run streams live; reconnect replays cleanly.
- **Phase 7 — Frontend (priority order, cut from bottom).** (1) schema-driven agent/workflow config forms + versioned saves; (2) React Flow builder (palette, canvas, inspector, DSL editor, live validation, dry-run highlight); (3) run timeline + live monitor (the demo surface); (4) eval pages. `lib/api.ts` from OpenAPI; `lib/ws.ts`. **Milestone:** create agent → build 2-agent workflow → trigger → watch timeline → see cost.
- **Phase 8 — Recording/replay + eval (days 9–11).** RecordingInterceptor + ReplayProvider + recording CLI; eval data model + LLMJudge + runner + minimal eval UI; 10-example datasets per template. **Milestone:** record→replay roundtrip byte-identical; `harness eval run` produces results.
- **Phase 9 — Templates, seed, docs, demo (day 12).** Two templates + `scripts/seed.py`; README per `docs/architecture.md §16` **plus the Harness chapter** (modes table, add-a-provider/validator, recording flow, eval framework) and the workflow chapter (graph schema, node types, add-a-template); `docs/{adding-a-channel,adding-a-tool,adding-a-template,workflow-dsl}.md`. Playwright golden-path E2E. **Record demo in replay mode by day 10–12, two takes.**

---

## Files to create (representative)
- Runtime: `backend/app/runtime/{state,inner_graph,outer_graph,executor,validation}.py`, `runtime/dsl/{grammar.lark,parser.py,evaluator.py}`
- Harness: `backend/app/harness/{executor,call,config,cli}.py`, `harness/providers/{base,anthropic,openai,bedrock,stub,replay}.py`, `harness/validators/*`, `harness/interceptors/*`, `harness/cost/{models,pricing}.py`, `harness/recording/{recorder,replayer,script_generator}.py`, `harness/eval/{runner,reports}.py` + `harness/eval/judges/{base,exact_match,llm_judge,composite}.py`
- Persistence: `backend/app/db/models.py`, `db/repositories/{agents,workflows,runs,channels,evals}.py`, `alembic/versions/*`
- Seams: `channels/{base,telegram,slack,whatsapp,registry}.py`, `tools/*`, `memory/{base,buffer,summary,channel_scoped,external}.py`, `guardrails/{enforcer,policies}.py`
- Frontend: `components/{workflow-builder,timeline,agent-config,evals,ui}/`, `lib/{api,ws}.ts`
- Infra/docs: `docker-compose.yml`, `code-runner/{Dockerfile,runner.py}`, `scripts/{seed,reset_db}.py`, `tests/scripts/*.yaml`, `README.md`, `docs/*.md`, `.env.example`

## Reuse from existing code
`~/agentwork` is a different stack — **patterns only**: Anthropic SDK usage and the extremis client init (`extremis.Extremis(Config(namespace=...))`) for `memory/external.py`. Treat as greenfield.

---

## Scope & sequencing note
This is a large build (~14 days; harness alone ~30% of budget). Cut order if time runs short, preserving the 40% demo + 30% architecture: drop `parallel` node → eval UI polish → Bedrock provider → CitationValidator. Never cut: the two-layer runtime, harness executor + Stub/Replay providers, Telegram round-trip, live timeline, cost circuit breaker, two templates. Keep the "scope vs cut" table in the README — it signals judgment.

## Verification (end-to-end, in order)
1. `cp .env.example .env` (fill keys) → `docker-compose up` → health endpoints green.
2. `python scripts/seed.py` → two templates + sample agents in UI.
3. `pytest backend/tests` — integration (`agent_lifecycle`, `workflow_execution`, `channel_roundtrip`, `conditional_routing`, `workflow_versioning`) + harness (`executor`, `stub/replay providers`, `validators`, `cost_models` Decimal, `recording` roundtrip, `eval_runner`) + DSL + guardrails + extremis round-trip.
4. Playwright E2E: create agent → run workflow → timeline renders expected steps.
5. **Live Telegram:** point bot webhook at local tunnel, message the bound agent, watch the run on the timeline, get a reply. (The 40%.)
6. **Guardrail demo:** set `max_cost_per_run_usd=$0.10`; confirm graceful termination, red timeline block, `runs.error` set.
6b. **Image round-trip:** send a photo via Telegram → agent (vision model) describes it; thumbnail renders in the timeline. Send a voice note → graceful "can't process that yet" reply.
7. **Deterministic demo:** `LLM_MODE=record` once, then `LLM_MODE=replay` reproduces the run offline at zero API cost.
8. **Eval:** `harness eval run market_intel_briefing` → results table populated, click a failed example → lands on its actual run timeline.
9. **Extensibility proof:** diff to add the Slack stub (only `channels/slack.py` + registry line + UI form) — no orchestrator/agent/workflow changes; diff to add a provider (only `providers/<x>.py` + registry).

## Primary risk
Not technical — the **demo recording**. Replay mode exists precisely to de-risk it: capture once, replay deterministically. Script the narrative before building, record by day 10, two takes. If a feature can't earn screen time, question whether it earns build time.
