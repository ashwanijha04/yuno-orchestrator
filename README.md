# Yuno — AI Agent Orchestration Platform

Create AI agents (personality, tools, memory, limits), wire them into collaborative
multi-agent workflows on a **real runtime**, **talk to a team of them** like a chief
of staff and his staff, reach them through **Telegram**, and even have them spawn
**real Claude Code sessions on your machine**. Everything runs locally with a single
command.

> Built for the Yuno AI Engineer challenge. Architecture rationale lives in
> [`docs/architecture.md`](docs/architecture.md); the full build plan in
> [`docs/plan.md`](docs/plan.md).

---

## Quickstart

```bash
cp .env.example .env          # optional: add OPENAI/ANTHROPIC keys + TELEGRAM_BOT_TOKEN
make up                       # builds + starts everything, auto-selecting free ports
make seed                     # Jarvis + a standing "company" of specialists + templates
```

`make up` runs `scripts/dev-up.sh`, which **scans for free host ports** (so it works
regardless of what else is on your machine), starts the stack, and **auto-launches the
host-side Claude Code bridge** (see below). It prints the URLs:

```
UI         http://localhost:3000   (or the next free port — e.g. 3001)
API        http://localhost:8000   (docs at /docs)
```

No API key? It still runs: `LLM_MODE=stub` (the default) gives deterministic canned
responses so the whole flow is demoable offline. Set `LLM_MODE=live` + at least one
provider key for real output — the **ModelRouter** routes by an agent's `task_type`
(coding→Anthropic, normal→OpenAI, conversation→Gemini) and falls back across whatever
keys you've set.

---

## What you can do

- **Talk to Jarvis** — a conversational chief-of-staff agent that plans work, **creates
  new agents**, **delegates** to a standing team, **pauses for your approval**, and
  reports back. Chat in the UI or over Telegram.
- **Cockpit** — a live "mission control": an agent **constellation** that lights up to
  show who Jarvis is talking to, a command console, the mission queue, cost/throughput
  gauges, the Claude-bridge status, and pending coding approvals.
- **Agents** — create/configure agents: name, role, system prompt, **SOUL.md +
  persona**, model, temperature, tools, **shared long-term memory**, guardrails.
- **Workflows** — build multi-agent graphs in a **visual React Flow builder**: agents,
  tools & MCP, DSL-conditioned branches and feedback loops, **human-approval gates**,
  and **on-failure routing**. Validate (errors ring the offending node on the canvas),
  **Tidy** (auto-layout), and **Test run** right from the canvas — it saves, launches,
  and opens the live timeline. Or clone a template.
- **Tasks / run timeline** — live per-agent execution with token/cost tracking,
  inter-agent handoffs, tool calls, and long-term-memory recalls, streamed over
  WebSocket. **Follow up in place** (continues the *same* task, one timeline + cost
  roll-up), **evaluate** (LLM judge) or 👍/👎 (feeds the agents' learning), and **cancel**
  (stops the whole delegation tree, not just the run you clicked).
- **Chat** — a continuous DM thread with any agent, history persisted per agent.
- **Team channels** — Slack-style group spaces; `@mention` a teammate to pull their
  reply into the channel (they can loop in others via their collaboration tools).
- **Telegram** — bind a bot to an agent/workflow and chat with it; replies come back
  automatically, including approving coding plans with `/allow` · `/deny`.
- **Claude Code on your machine** — ask Jarvis to do something on your filesystem and it
  runs a real local `claude` session through the host bridge (see below).
- **Schedules** — trigger workflows on a cron.

---

## Talk to Jarvis (the conversational layer)

`make seed` creates **Jarvis** plus a standing **company** of specialists he can
delegate to and a research pipeline:

| | |
|---|---|
| **Jarvis** | Chief of staff — plans, builds a team, delegates, escalates, gets it done |
| **Athena** the Strategist · **Devin** the Engineer · **Mara** the Marketer · **Pixel** the Designer · **Otto** the Ops Lead | The "company" Jarvis delegates to |
| **Remy** the Researcher → **Ana** the Analyst → **Brie** the Briefer | A market-intel pipeline |
| **Dex** the Drafter ⇄ **Cy** the Critic | A draft → critique → revise debate loop |
| **Mnemo** the Assistant | Remembers you across conversations |

Give Jarvis a high-level task and he breaks it into subtasks, **reuses or creates** the
right specialist, and delegates via `send_message_to_agent` — each handoff is a real
**child run** visible on the timeline as an agent-to-agent conversation. Any agent can
hold the collaboration tools, so teammates can talk to each other and **escalate back to
Jarvis**, like a real team. `run_debate` runs the Drafter/Critic loop for higher-quality
output.

When a workflow hits a **human-approval gate**, the run **pauses** (status `paused`,
an approval row is created) and resumes exactly where it left off when you approve — in
the UI or from Telegram.

---

## Claude Code on your machine (the host bridge)

Jarvis can run **real Claude Code sessions on your own computer**, using *your* `claude`
login — no API key, no tunnel.

- **Why a bridge?** The platform runs in Docker; your authenticated `claude` CLI lives
  on the host. `scripts/claude_bridge.py` (stdlib-only, auto-started by `make up`) polls
  the platform for coding jobs, runs `claude` locally in a workspace, and posts results
  back over the API. `make bridge-logs` tails it; `make down` stops it.
- **The `coding_session` tool** lets Jarvis (from the UI *or Telegram*) say "list the
  files on my Desktop" or "scaffold a script in ~/code" and have it actually happen.
- **Approvals.** Because the CLI can do real work, the bridge defaults to a
  **plan-preview** flow (`CODING_APPROVALS=plan`): Claude proposes a plan, which is
  surfaced to the cockpit **and** Telegram; you `/allow` or `/deny`, and only then does
  it execute. The bridge status chip in the cockpit shows whether it's connected.

---

## Memory & continuous learning

- **Shared team memory.** Agents on the `external` strategy read and write a **shared
  `team` namespace** — everyone can recall what teammates learned, not just their own
  history. Backed by **Postgres + pgvector** with **OpenAI `text-embedding-3-small`
  (1536-dim)**; extremis runs *embedded* (no separate server, no torch, no model
  download) and **degrades gracefully** to the in-run buffer if unavailable.
- **Recall is visible.** When an agent pulls context from long-term memory, the run
  timeline shows a "🧠 Recalled N memories" note on that step.
- **Learning loop.** Evaluate a finished run (LLM judge) or give 👍/👎 — the verdict is
  distilled into a lesson and written to memory, so the agents improve on similar tasks
  next time (New Task → Execute → Observe → Learn → Encode).

Other memory strategies (buffer, summary, channel-scoped) remain selectable per agent;
chat/DM continuity is keyed by conversation id regardless of strategy.

---

## MCP (Model Context Protocol)

Real MCP is wired in: a bundled FastMCP demo server (`app/mcp/demo_server.py` —
`calculate`, `current_time`, `word_stats`) is discovered at startup, its tools surface in
the palette as `mcp__server__tool`, and they can be granted to agents or dropped into a
workflow as tool nodes. Connection is per-call over stdio, so a flaky server can't wedge
the platform.

---

## Architecture

Four processes + Postgres + Redis, one `docker compose` (plus the host-side bridge):

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

  host machine:  scripts/claude_bridge.py  ──polls /coding──►  control plane
                 (runs your local `claude` CLI for coding_session jobs)
```

Two invariants enforced in code:
1. **Agents are configuration (DB rows); the runtime is generic code.** Adding an
   agent is a row; a workflow is a `graph` JSONB. No new Python.
2. **Every side effect is a Postgres row first, then a Redis publish.** Redis is
   transport; Postgres is truth. The live UI derives from rows, so dropped clients
   replay.

### The two-layer execution model
- **Outer graph (workflow)** — compiled per run from the workflow JSON into a
  **LangGraph `StateGraph`**. Nodes are agents/tools/logic; edges are transitions guarded
  by a small **condition DSL** (Lark/LALR, not `eval`), priority-ordered with feedback
  loops bounded by `iteration_count`. A `human` node pauses the run for approval and
  resumes from the saved state.
- **Inner loop (agent)** — a structured ReAct loop (`prepare → llm → router → tool`*)
  that runs through the **harness**. Every LLM turn, tool call, and handoff is persisted,
  so the timeline reflects exactly what ran. The loop polls for **cancellation** between
  turns and before delegating, so stopping a task halts the whole tree promptly.

### The harness (`app/harness/`)
Everything around an LLM call — retries, validation, cost, tracing — is one lifecycle
with pluggable **providers / validators / interceptors**. Production, tests, and demos
are *configurations* of the same runtime:

| Mode | Provider | Use |
|---|---|---|
| `live` | ModelRouter → Anthropic / OpenAI / Gemini | real runs |
| `stub` | StubProvider (scripted/canned) | deterministic tests + offline demo |
| `replay` | ReplayProvider | deterministic recorded demo |

The cost circuit-breaker (`CostCapInterceptor`) terminates a run gracefully when it would
exceed `guardrails.max_cost_per_run_usd`.

**Latency + cost optimisations on the LLM path:**
- **Prompt caching** on Anthropic (`cache_control: ephemeral` on system + tool defs) —
  repeat calls within ~5 min read at 10% input cost and TTFT drops materially. `LLMResponse`
  carries `cache_read_tokens` / `cache_creation_tokens` and `CostModel` applies the 0.10×
  / 1.25× bands so the ledger is exact.
- **Model routing** by `task_type` (coding → Anthropic, conversation → Gemini, normal →
  OpenAI) with fallback across whatever providers are keyed — cheaper-model defaults
  unless the agent needs the strong one.
- **Observability seams** — the `Interceptor` protocol (existing examples: `CostCap`,
  `Trace`, `PIIRedact`) is the one place to plug an LLM-tracing service (peekr, Langfuse,
  Phoenix, etc.) without touching agents or workflows. Add a class, register it; nothing
  else changes.

### Identity, collaboration & learning (the differentiators)
- **Soul + persona** — an agent's `soul_md` (SOUL.md-style identity) + structured persona
  compose into its effective system prompt (`app/runtime/persona.py`).
- **Structured handoffs** — `send_message_to_agent` records a handoff on the sender's run
  and **runs a linked child run** for the recipient, returning its reply — so multi-agent
  collaboration and escalation are visible on the timeline.
- **Continuous learning** — shared `external` memory via extremis + the evaluate/feedback
  learning loop (above).

## Why these choices (runtime justification)
- **LangGraph for the outer graph** — workflows are genuinely graphs with conditional
  edges and feedback loops; LangGraph gives a real, inspectable `StateGraph`. The inner
  ReAct loop is hand-written so every step flows through the harness and is persisted
  (LangGraph's prebuilt agent wouldn't give that control). A deliberate hybrid.
- **Postgres + Redis, no broker** — Postgres is the source of truth (run history, cost
  ledger, replay); Redis is ephemeral transport (at-least-once run queue via Streams,
  pub/sub for the live UI). RabbitMQ/Kafka would be over-engineering here.
- **Telegram** — lowest-friction live human↔agent channel; polling for dev, webhooks for
  production. Slack/WhatsApp ship as stubs proving the `Channel` abstraction.
- **A host bridge for Claude Code** — uses your real `claude` auth instead of an API key,
  with plan-preview approvals so real filesystem work stays under your control.

---

## How to add things

- **An agent** — UI → Agents → New, or `POST /agents`. Pure config.
- **A tool** — implement `Tool` in `app/tools/<name>.py`, register in `tools/registry.py`
  + `tools/runtime.py`. Grant it to an agent via `tool_ids`.
- **An MCP tool** — point the client at a server; discovered tools appear as
  `mcp__server__tool` and are grantable like any tool. No orchestrator changes.
- **A channel** — implement `Channel` in `app/channels/<name>.py` (see `telegram.py`;
  `stubs.py` shows the shape), register in `channels/registry.py`. (Slack mirror is the
  documented next one.)
- **A workflow / template** — build it in the visual builder and save, or add it to
  `scripts/seed.py` using `role_key`s.

---

## Testing

`make test` runs the suite in-container against a **dedicated `yuno_test` database**
(isolated from the live worker). Highlights:

- `tests/test_requirements.py` — **requirements traceability**: one test per rubric
  Functional Requirement (agent CRUD, channels, config dimensions, conditional +
  feedback-loop workflow, 2 templates, Telegram binding, live monitoring, e2e 2+ agents).
  The report doubles as a compliance matrix.
- Layer tests: harness (retry/validation/cost-cap), runtime (execution, routing, loops,
  cancellation), tools + inter-agent messaging, memory strategies, guardrails, channel
  roundtrip, scheduler, queue/events. **84 passing**, 1 skipped (live Telegram — needs a
  bot token).

---

## Live Telegram demo

1. Create a bot with [@BotFather](https://t.me/botfather); put the token in `.env`
   (`TELEGRAM_BOT_TOKEN`) and restart. (Keep the token in `.env` only — never commit it.)
2. UI → Channels: create a Telegram channel; bind it (`external_id` = your chat id, or
   `*` for any chat) to an agent (e.g. Jarvis) or a workflow.
3. Message the bot. Polling mode (default) needs no tunnel; the run appears on the
   timeline and the reply comes back in Telegram. Ask for filesystem work and Jarvis
   spawns a local Claude Code session — approve its plan with `/allow`. For the snappier
   production path, set `TELEGRAM_TRANSPORT=webhook` + `PUBLIC_BASE_URL` (e.g. cloudflared).

---

## Failure modes

| Failure | Response |
|---|---|
| Worker crash mid-run | at-least-once queue re-delivers (Redis Streams pending list) |
| LLM timeout / 429 | harness retries with backoff; fatal errors fail the step |
| Cost cap exceeded | run terminates gracefully, red block on the timeline |
| Agent infinite loop | `iteration_count` guard at the router terminates it |
| Run cancelled | cancellation cascades to every delegated sub-run; the inner loop stops between turns |
| Channel/API down | transactional outbox retries delivery with an attempt cap |
| Claude bridge offline | `coding_session` fails fast with a clear message instead of hanging |
| Redis down | runs still execute (Postgres writes succeed); live UI degrades |
| extremis offline | memory degrades to the in-run buffer; the run continues |

## Security (local-first)
Secrets via `.env` (never logged or committed — including the Telegram bot token);
webhook secret-token verification; `python_exec` in a no-network sandbox container;
`http_request` allowlisted; Claude Code runs under your own auth with plan-preview
approval before any real work; no auth on the single-user local UI (production would add
per-user scoping).

## Scope vs. cut
**Built:** Jarvis conversational layer + cockpit, agent CRUD + full config + soul, visual
builder (validation-on-canvas, Tidy, Test run, approval gates, failover), two-layer
runtime + DSL, **human approval (pause/resume)**, harness (stub/replay/live), tools +
inter-agent collaboration/escalation + `run_debate`, real **MCP**, **Claude Code host
bridge** + approvals, **shared team memory** + evaluate/feedback learning, Telegram +
outbox + auto-reply, **team channels**, **same-run follow-ups**, **cancel-cascade**,
scheduler, live timeline, 2 templates, requirements test suite.
**Deferred (documented):** Slack run-mirror, recording/replay capture UI, eval framework,
OpenTelemetry export, the `transform`/`parallel` node types.

## Future work
Slack visibility mirror (on the existing Channel + event-stream seam) · extremis
deepening (procedural-memory skills) · recording/replay capture for offline demos · eval
framework on the same harness · OTel → Jaeger · drag-from-palette + CodeMirror DSL editor
+ workflow version history/diff in the builder.
