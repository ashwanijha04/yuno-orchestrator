# Local Setup — Yuno

For the live demo session. Three commands from clone to a working orchestration platform with two LLM providers, a Telegram bot, and five demo workflows seeded.

---

## 0. Prerequisites

| | Required | How to check |
|---|---|---|
| **Docker Desktop** | ≥ 20.10 with Compose v2 | `docker --version && docker compose version` |
| **RAM available to Docker** | 2 GB minimum (4 GB comfortable) | Docker Desktop → Settings → Resources |
| **Disk** | ~3 GB free | `df -h .` |
| **Python 3** | 3.10+ (host, for the port-scanning helper) | `python3 --version` |
| **`make`** | any | `make --version` |
| **One LLM API key** (optional) | Anthropic, OpenAI, or Gemini | Yuno runs in `LLM_MODE=stub` (deterministic canned replies) without keys, so the *flow* still demos offline. Set `LLM_MODE=live` + a key for real output. |

Nothing else to install. Everything else (Postgres + pgvector, Redis, Python deps, Node deps, Caddy-style routing) ships inside containers.

---

## 1. Three-command setup

```bash
git clone <repo>                           # whatever your clone URL is
cd yuno-orchestrator

cp .env.example .env                       # optional: open .env and add keys
make up                                    # builds everything; auto-picks free host ports
make seed                                  # Jarvis + standing team + 5 demo templates + 3 team channels
```

That's it. `make up` runs `scripts/dev-up.sh`, which:
- Scans for free host ports (so it works even if you already have something on 3000/8000)
- Boots `postgres → redis → backend → worker → frontend → code-runner → playwright-mcp`
- Auto-launches the host-side **Claude Code bridge** (for the optional on-machine coding feature)
- Prints the URLs at the end:

```
UI         http://localhost:3001        (or next free port — usually 3000)
API        http://localhost:8000        (OpenAPI docs at /docs)
```

`make seed` is **idempotent** — safe to re-run. Creates only what's missing.

### Expected timing

| | First run | After that |
|---|---|---|
| `make up` | **5–10 min** (image builds — Python deps + Next.js deps) | ~20 s |
| `make seed` | < 5 s | < 5 s |
| Frontend cold-start in browser | ~10 s (Next.js dev compile on first hit per route) | instant |

---

## 2. Verification checklist

After `make seed`, in this exact order:

| | Check | What you should see |
|---|---|---|
| 1 | `curl http://localhost:8000/health` | `{"status":"ok","env":"dev","llm_mode":"live"}` (or `stub`) |
| 2 | Open the UI (`http://localhost:3001`) | Cockpit "Mission Control" with the Jarvis constellation (15 named specialists ringed around JARVIS) |
| 3 | Cockpit gauges | `AGENTS 17`, `SPEND $…`, `TOKENS …` — non-`—` values mean stats API works |
| 4 | `/agents` | Search bar + 17 rows with model badges (claude / gpt / gemini), one Run + Chat + Edit per row |
| 5 | `/workflows` | **5 templates**: Market Briefing, Draft & Critique, Cited Research (tools badge), Page Summariser · MCP (mcp badge), PRD with Approval (approval badge) |
| 6 | `/team` | Three channels: `#growth`, `#product`, `#research` with named members |
| 7 | `/channels` | `Telegram · @<your_bot>` shown with an `ACTIVE` pill (if `TELEGRAM_BOT_TOKEN` set) |
| 8 | `docker compose exec backend pytest -q` | `84 passed, 1 skipped` |

If any check fails, see **§5 troubleshooting**.

---

## 3. The demo path

A 2–3 minute walk-through that touches every brief requirement. Run in this order:

### Step 1 — Cockpit (the system at a glance, ~15 s)
- Land on `/`. Point at:
  - The **gauges** (live cost + token counters)
  - The **constellation** — "15 named specialists, one chief of staff (Jarvis)"
  - The **mission queue** below — every prior run as history

### Step 2 — Multi-agent workflow with a tool node (~45 s) — *the brief's "execute real tools"*
- Navigate to `/workflows`, click **▶ Run** on **`Cited Research (demo)`**.
- Enter a topic, e.g. `"prompt caching for LLM agents — benefits and pitfalls"`.
- Watch the timeline:
  - **`search` step** — the `web_search` *tool node* runs first (status badge, no LLM cost — it's a tool, not an agent)
  - **`cite → analyse → brief`** — three agents in series, each step shows the agent's name, tokens, cost, and the actual output
- End on a brief that cites real, current sources (proves Tavily was hit live).

### Step 3 — MCP integration (~30 s) — *the brief's "configurable tools"*
- Back to `/workflows`, click **▶ Run** on **`Page Summariser · MCP (demo)`**.
- Paste any URL.
- Two MCP Playwright steps (`browser_navigate` → `browser_snapshot`) followed by Brie summarising. **Point out** that adding browser capability required *zero backend code* — it's all MCP.

### Step 4 — Human-in-the-loop (~30 s) — *the brief's "interaction rules"*
- `/workflows` → **▶ Run** on **`PRD with Approval (demo)`**.
- Enter an idea, e.g. `"a Slack bot that summarises long threads"`.
- Pip drafts a PRD → run **pauses on the approval gate** (a red pill appears on the cockpit's `APPROVALS` gauge).
- Click ✓ Approve → Mara + Brie finish.

### Step 5 — Async agent-to-agent + Telegram (~30 s) — *the brief's "agent-to-agent + external channel"*
- Open Telegram → message your bot (`@<your_bot>` from `/channels`).
- It reaches **Jarvis** (chief of staff), which may delegate to specialists via `send_message_to_agent` — each delegation appears as a **child run** linked from the parent.
- Reply lands back in Telegram.
- Show the same conversation on `/runs/<id>` — every handoff, every tool call, full cost ledger.

### Step 6 — Cost guardrail (~15 s) — *the brief's "limits"*
- On the agent's edit page, set `max_cost_per_run_usd: 0.02`.
- Run a workflow expensive enough to trip it. The run terminates gracefully with a **destructive-coloured timeline block** and `runs.error = "cost cap exceeded"`.

Total: ~2:45.

---

## 4. Configuration knobs you'll likely touch

In `.env`:

| Var | Purpose | Default |
|---|---|---|
| `LLM_MODE` | `stub` (offline, free) · `live` (real providers via ModelRouter) | `stub` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | Provider keys — set at least one for `live` mode | empty |
| `TAVILY_API_KEY` | Real `web_search` tool. Without it, `web_search` returns a graceful stub. | empty |
| `TELEGRAM_BOT_TOKEN` | Your bot (get one from @BotFather in 2 min) | empty |
| `TELEGRAM_TRANSPORT` | `polling` (no TLS needed, default) or `webhook` | `polling` |
| `PUBLIC_BASE_URL` | Only needed for `webhook` transport — a public HTTPS URL pointed at the backend | empty |

After editing `.env`, restart only what needs it:

```bash
docker compose restart backend worker
```

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `make up` fails on `next build`-step | Docker has < 2 GB RAM | Docker Desktop → Settings → Resources → bump Memory to 4 GB → restart |
| Cockpit gauges stuck on `—` | Stats API not responding | `docker compose logs backend | tail`. Usually backend lost DB connection — `docker compose restart backend`. |
| Frontend takes 17 s on first page hit | Next.js cold-compile in dev mode | Normal once per route. Subsequent hits are instant. To eliminate, run in production mode (see §6). |
| `Cited Research` returns no real sources | `TAVILY_API_KEY` missing | Add it to `.env` and `docker compose restart worker` — or accept the stub result for the demo. |
| Telegram bot doesn't respond | Token is already polling from another machine | Telegram allows only ONE poller per bot. Stop the other instance, or create a second bot via @BotFather. |
| `make seed` shows existing agents but no new ones | Already seeded — idempotent | This is the success path. Nothing to do. |
| Jarvis names agents that don't exist | Stale long-term memory in pgvector | `docker compose exec backend python -m scripts.cleanup_demo_state` — purges orphan memories + ghost team channels. Re-runs are no-ops. |
| Pytest fails on `test_shared_memory_is_recalled_with_attribution` | Pre-existing test isolation bug — old `codename%` memories crowd out the new probe | `docker compose exec postgres psql -U yuno -d yuno -c "DELETE FROM memories WHERE content ILIKE '%codename%' OR content ILIKE '%spring release%';"` then re-run pytest. |

---

## 6. Reset / re-seed / nuke

```bash
# Soft reset — clear test artefacts (junk agents, ghost workflows, stale memories), keep schema
docker compose exec backend python -m scripts.cleanup_demo_state

# Re-seed (idempotent — only creates what's missing)
make seed

# Hard reset — destroy DB volume and start over
docker compose down -v
make up
make seed
```

To stop everything cleanly: `make down`. Containers + the host Claude bridge come down together.

---

## 7. (Optional) Production-mode frontend

`make up` runs the frontend in `next dev` for HMR. For a snappier demo without the 10-s first-hit compile:

```bash
docker compose exec frontend npm run build
docker compose exec frontend npm run start
```

Drops idle RAM from ~740 MB → ~200 MB and removes cold-start latency on every route. Suitable for the recorded demo.

---

## 8. Where to read more

- `docs/architecture.md` — full architecture rationale (two-layer execution model, harness, channels, memory, guardrails)
- `docs/plan.md` — build plan with rationale per subsystem
- `README.md` — quickstart + feature catalogue + scope/cut table
- `backend/scripts/cleanup_demo_state.py` — exactly what the cleanup script does
- `backend/scripts/seed.py` — the canonical agent + workflow + team-channel definitions
