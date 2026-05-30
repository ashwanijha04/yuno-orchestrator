# Yuno — recorded demo

Auto-driven 2:23 walkthrough of the platform end-to-end. Recorded with Playwright
against the running stack (no fakery; every API call, run, tool call, approval
gate, and cost-cap trip is real).

## Files

| | Size | Codec | Best for |
|---|---|---|---|
| `yuno-demo.mp4` | 2.5 MB | H.264 / yuv420p / 25 fps / 1440×900 / `+faststart` | Universal playback, embedding, submission attachment |
| `yuno-demo.webm` | 8.0 MB | VP8 (Playwright native) | Original; not committed (intermediate only) |

## What the video covers (in order)

| t≈ | § | Beat | Brief requirement satisfied |
|---|---|---|---|
| 0:00 | 1 | **Cockpit** — live gauges, the 15-specialist constellation, mission queue | Visual web UI · live monitoring |
| 0:14 | 2 | **Cited Research** — `web_search` TOOL node + Remy → Ana → Brie chain. Tool call lands as its own first-class step on the timeline. | "Real runtime · execute real tools" · multi-agent collaboration |
| 1:06 | 3 | **PRD with Approval** — Pip drafts → **pauses on the human gate** → APPROVALS gauge ticks up on cockpit → click Approve → Mara + Brie resume | Interaction rules · agent communication · human-in-the-loop |
| 1:30 | 4 | **Cost guardrail** — Market Briefing kicked off with `max_cost_usd=$0.0001`. Each agent step's output literally reads `[blocked: cost cap $0.0001 would be exceeded (spent $0, est +$0.004556)]`. Graceful degradation — run completes at $0 spent. | Configurable limits · cost tracking |
| 1:55 | 5 | **Channels** — `@jarv_m1_bot` Telegram binding, status pill `ACTIVE` | External messaging channel (Telegram) |
| 2:02 | 6 | **Real Telegram round-trip** — open a historical Jarvis conversation: a user DM'd a YouTube URL, Jarvis fetched it via `http_request`, summarised, replied. Visible timeline with the inbound message, tool call, and reply. | Async agent communication · external channel round-trip |
| 2:11 | 7 | **Team channels** — `#growth / #product / #research` with named specialists | Multi-agent collaborative workflows |
| 2:18 | 8 | **Agents** — search ("research" filter), per-row Run / Chat / Edit | Agent CRUD · configurability |
| 2:22 | 9 | **Back to cockpit** — final state: SPEND, TOKENS, RUNNING gauges have moved | Live cost + token tracking |

## How to re-record

```bash
# 1. Make sure the stack is up and seeded
make up
make seed

# 2. Run the script (uses the Playwright install in /tmp/yuno-screens)
node /tmp/yuno-screens/demo.mjs

# 3. Convert WebM → MP4 (smaller, universally playable, +faststart for instant scrub)
ffmpeg -i demo/yuno-demo.webm \
  -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p -movflags +faststart \
  demo/yuno-demo.mp4 -y
```

Recorded against:
- `LLM_MODE=live` with real Anthropic + OpenAI keys (ModelRouter picks per `task_type`)
- Real Tavily web search for the Cited Research step
- 17 agents, 5 workflow templates, 3 team channels (all from `scripts.seed`)
- A real `@jarv_m1_bot` Telegram binding with the existing conversation history

## Notes on the cost-guardrail step (§4)

The `CostCapInterceptor` is designed as a **graceful pre-flight blocker**, not a
hard run-killer:

- Before each LLM call, it estimates the cost (`provider.estimate_tokens` → `cost_model.cost`)
- If `run.total_cost + estimate > cap`, it returns a synthetic `[blocked: …]` response
- The agent step "completes" cleanly with the blocked content as its output
- Run-level cost stays at $0; downstream steps see the same block

That's why the timeline shows green-status steps with blocked content rather than
a red termination block. It's the right design — the run never *spends* over cap,
and the diagnostic message tells the operator exactly why. A harder
"fail-and-stop" mode would be a one-line policy change in the interceptor.
