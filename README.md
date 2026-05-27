# Yuno — AI Agent Orchestration Platform

Create AI agents (personality, tools, memory, limits), wire them into collaborative
multi-agent workflows on a **real runtime**, run them with live cost/latency
tracking, and reach an agent through **Telegram**. Everything runs locally with a
single command.

> Built for the Yuno AI Engineer challenge. Architecture rationale lives in
> [`docs/architecture.md`](docs/architecture.md); the full build plan in
> [`docs/plan.md`](docs/plan.md).

---

## Quickstart

```bash
cp .env.example .env          # optional: add ANTHROPIC_API_KEY + TELEGRAM_BOT_TOKEN
make up                       # builds + starts everything, auto-selecting free ports
make seed                     # 5 souled agents + 2 workflow templates
```

`make up` runs `scripts/dev-up.sh`, which **scans for free host ports** (so it works
regardless of what else is on your machine) and prints the URLs:

```
UI         http://localhost:3000   (or the next free port)
API        http://localhost:8000   (docs at /docs)
```

No API key? It still runs: `LLM_MODE=stub` (the default) gives deterministic canned
responses so the whole flow is demoable offline. Set `LLM_MODE=live` +
`ANTHROPIC_API_KEY` for real agent output.

---

## What you can do

- **Agents** — create/configure agents: name, role, system prompt, **SOUL.md +
  persona**, model, temperature, tools, memory strategy, guardrails. Each opens its
  own config page with a Channels tab.
- **Workflows** — build multi-agent graphs in a **visual React Flow builder** (drag
  agents, connect edges, add DSL conditions for branches & feedback loops), or clone
  a template. Run one and watch it execute.
- **Run timeline** — live per-agent execution with token/cost tracking, inter-agent
  handoffs, and tool calls, streamed over WebSocket.
- **Telegram** — bind a bot to an agent/workflow and chat with it; replies come back
  automatically.
- **Schedules** — trigger workflows on a cron.

---

## Architecture

Four processes + Postgres + Redis, one `docker compose`:

```
 Next.js UI (3000) ──HTTP+WS──► FastAPI control plane (8000) ──► PostgreSQL (truth)
                                      │  REST · WebSocket gateway · webhooks · schedules
                                      ▼
                                   Redis  ◄──► Worker pool (asyncio)
                          (queue · pub/sub)     LangGraph outer graph + ReAct inner loop
                                                tool runtime · outbox · scheduler · poller
                                      │
                                      ▼
                          code-runner (sandboxed python_exec)
```

Two invariants enforced in code:
1. **Agents are configuration (DB rows); the runtime is generic code.** Adding an
   agent is a row; a workflow is a `graph` JSONB. No new Python.
2. **Every side effect is a Postgres row first, then a Redis publish.** Redis is
   transport; Postgres is truth. The live UI derives from rows, so dropped clients
   replay.

### The two-layer execution model
- **Outer graph (workflow)** — compiled per run from the workflow JSON into a
  **LangGraph `StateGraph`**. Nodes are agents; edges are transitions guarded by a
  small **condition DSL** (Lark/LALR, not `eval`), priority-ordered with feedback
  loops bounded by `iteration_count`.
- **Inner loop (agent)** — a structured ReAct loop (`prepare → llm → router →
  tool`*) that runs through the **harness**. Every LLM turn, tool call, and handoff
  is persisted, so the timeline reflects exactly what ran.

### The harness (`app/harness/`)
Everything around an LLM call — retries, validation, cost, tracing — is one
lifecycle with pluggable **providers / validators / interceptors**. Production,
tests, and demos are *configurations* of the same runtime:

| Mode | Provider | Use |
|---|---|---|
| `live` | Anthropic / OpenAI | real runs |
| `stub` | StubProvider (scripted/canned) | deterministic tests + offline demo |
| `replay` | ReplayProvider | deterministic recorded demo |

The cost circuit-breaker (`CostCapInterceptor`) terminates a run gracefully when it
would exceed `guardrails.max_cost_per_run_usd`.

### Identity & learning (the differentiators)
- **Soul + persona** — an agent's `soul_md` (SOUL.md-style identity) + structured
  persona compose into its effective system prompt, so personality shapes every
  response (`app/runtime/persona.py`).
- **Structured handoffs** — inter-agent messages (`send_message_to_agent`) record a
  handoff on the sender's run and **enqueue a new run** for the recipient
  (run-per-message + inbox), so multi-agent collaboration is visible on the timeline.
- **Continuous learning** — the `ExternalMemoryStrategy` recalls/learns via extremis
  (New Task → Execute → Observe → Learn → Encode Skill), degrading gracefully when
  extremis is offline.

## Why these choices (runtime justification)
- **LangGraph for the outer graph** — workflows are genuinely graphs with conditional
  edges and feedback loops; LangGraph gives a real, inspectable `StateGraph`. The
  inner ReAct loop is hand-written so every step flows through the harness and is
  persisted (LangGraph's prebuilt agent wouldn't give that control). The challenge
  permits a custom runtime; this is a deliberate hybrid.
- **Postgres + Redis, no broker** — Postgres is the source of truth (run history,
  cost ledger, replay); Redis is ephemeral transport (at-least-once run queue via
  Streams, pub/sub for the live UI). RabbitMQ/Kafka would be over-engineering here.
- **Telegram** — lowest-friction live human↔agent channel; polling for dev, webhooks
  for production. Slack/WhatsApp ship as stubs proving the `Channel` abstraction.

---

## How to add things

- **An agent** — UI → Agents → New, or `POST /agents`. Pure config.
- **A tool** — implement `Tool` in `app/tools/<name>.py`, register in
  `tools/registry.py` + `tools/runtime.py`. Grant it to an agent via `tool_ids`.
- **A channel** — implement `Channel` in `app/channels/<name>.py` (see `telegram.py`;
  `stubs.py` shows the shape), register in `channels/registry.py`. No orchestrator
  changes. (Slack mirror is the documented next one.)
- **A workflow template** — add it to `scripts/seed.py` using `role_key`s; or build
  it in the visual builder and save.

---

## Testing

`make test` runs the suite in-container against a **dedicated `yuno_test` database**
(isolated from the live worker). Highlights:

- `tests/test_requirements.py` — **requirements traceability**: one test per rubric
  Functional Requirement (agent CRUD, channels, config dimensions, conditional +
  feedback-loop workflow, 2 templates, Telegram binding, live monitoring, e2e 2+
  agents). The report doubles as a compliance matrix.
- Layer tests: harness (retry/validation/cost-cap), runtime (execution, routing,
  loops), tools + inter-agent messaging, memory strategies, guardrails, channel
  roundtrip, scheduler, queue/events. **76 passing**, 1 skipped (live Telegram —
  needs a bot token).

---

## Live Telegram demo

1. Create a bot with [@BotFather](https://t.me/botfather); put the token in `.env`
   (`TELEGRAM_BOT_TOKEN`) and restart.
2. UI → Channels: create a Telegram channel; bind it (`external_id` = your chat id,
   or `*` for any chat) to an agent or workflow.
3. Message the bot. Polling mode (default) needs no tunnel; the run appears on the
   timeline and the reply comes back in Telegram. For the snappier production path,
   set `TELEGRAM_TRANSPORT=webhook` + `PUBLIC_BASE_URL` (e.g. a cloudflared tunnel).

---

## Failure modes

| Failure | Response |
|---|---|
| Worker crash mid-run | at-least-once queue re-delivers (Redis Streams pending list) |
| LLM timeout / 429 | harness retries with backoff; fatal errors fail the step |
| Cost cap exceeded | run terminates gracefully, red block on the timeline |
| Agent infinite loop | `iteration_count` guard at the router terminates it |
| Channel/API down | transactional outbox retries delivery with an attempt cap |
| Redis down | runs still execute (Postgres writes succeed); live UI degrades |
| extremis offline | memory degrades to buffer; the run continues |

## Security (local-first)
Secrets via `.env` (never logged); webhook secret-token verification; `python_exec`
in a no-network sandbox container; `http_request` capped; PII-redaction interceptor;
no auth on the single-user local UI (production would add per-user scoping).

## Scope vs. cut
**Built:** agent CRUD + full config + soul, visual builder, two-layer runtime + DSL,
harness (stub/replay/live), 5 tools + inter-agent messaging, memory (4 strategies),
guardrails + cost breaker, Telegram + outbox + auto-reply, scheduler, live timeline,
2 templates, requirements test suite.
**Deferred (documented):** Slack run-mirror, recording/replay capture UI, eval
framework, OpenTelemetry export, the `transform`/`human`/`parallel` node types.

## Future work
Slack visibility mirror (on the existing Channel + event-stream seam) · extremis
deepening (procedural-memory skills) · recording/replay capture for offline demos ·
eval framework on the same harness · OTel → Jaeger.
