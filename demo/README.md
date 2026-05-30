# Yuno — recorded demo

Auto-driven 3:57 walkthrough of the platform end-to-end. Captions are baked
directly into the video pixels (no separate SRT to wrangle). Recorded with
Playwright against the running stack — every API call, run, tool call,
approval gate, and cost-cap trip is real.

## Files

| | Size | Codec | Best for |
|---|---|---|---|
| `yuno-demo.mp4` | 5.2 MB | H.264 / yuv420p / 25 fps / 1440×900 / `+faststart` | Universal playback, embedding, submission attachment |
| `yuno-demo.webm` | 15 MB | VP8 (Playwright native) | Original; not committed (intermediate only) |

## What the video covers (in order)

| t≈ | § | Beat | Brief requirement satisfied |
|---|---|---|---|
| 0:00 | 1 | **Cockpit panorama** — live gauges, the 15-specialist constellation, mission queue | Visual web UI · live monitoring |
| 0:10 | 1b | **Talk to Jarvis live** — type a question into the cockpit console, watch the constellation light up while Jarvis works, reply lands inline with cost tracking | Conversational interaction · live monitoring |
| 0:36 | 2 | **Cited Research** — `web_search` TOOL node runs as its own step ($0, no LLM) then feeds Remy → Ana → Brie. Captions walk through each agent's job. | "Real runtime · execute real tools" · multi-agent collaboration |
| 1:42 | 3 | **PRD with Approval** — Pip drafts → pauses on the human gate → APPROVALS gauge ticks up on cockpit → click Approve → Mara + Brie resume | Interaction rules · agent communication · human-in-the-loop |
| 2:24 | 4 | **Cost guardrail** — Market Briefing kicked off with `max_cost_usd=$0.0001`. Each LLM call is estimated before it runs, cap exceeded → blocked. Graceful degradation, $0 spent, with the exact diagnostic on every step. | Configurable limits · cost tracking |
| 2:50 | 5 | **Channels** — `@jarv_m1_bot` Telegram binding, status pill `ACTIVE` | External messaging channel (Telegram) |
| 3:00 | 6 | **Real Telegram round-trip** — open a historical conversation: a real user DM'd a YouTube URL on Telegram. Jarvis used `http_request`, summarised, replied back to Telegram. Visible timeline. | Async agent communication · external channel round-trip |
| 3:20 | 7 | **Team channels** — `#growth / #product / #research` with seeded specialists | Multi-agent collaborative workflows |
| 3:30 | 8 | **Agents** — search filter ("research") narrows to Remy + Ana + Iris, per-row Run / Chat / Edit | Agent CRUD · configurability |
| 3:45 | 9 | **Final cockpit** — SPEND, TOKENS, RUNNING gauges have moved — proof the demo cost real money | Live cost + token tracking |

## How to re-record

```bash
# 1. Make sure the stack is up and seeded
make up
make seed

# 2. Run the script (uses the Playwright install in /tmp/yuno-screens)
node /tmp/yuno-screens/demo.mjs

# 3. Convert WebM → MP4 (smaller, universally playable, +faststart)
ffmpeg -i demo/yuno-demo.webm \
  -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p -movflags +faststart \
  demo/yuno-demo.mp4 -y
```

Captions are injected directly into the page DOM as a fixed-position overlay
(see the `cap(page, ...)` helper in `demo.mjs`), so they're part of the
recorded video pixels rather than a separate subtitle track. That means:
- No separate `.srt` file to ship
- Plays correctly on every player without subtitle support
- Styling is exactly what you see (Apple-system font, frosted-glass background)

## Recorded against

- `LLM_MODE=live` with real Anthropic + OpenAI keys (ModelRouter routes by `task_type`)
- Real Tavily web search for Cited Research + the live Jarvis question
- 17 agents, 5 workflow templates, 3 team channels (all from `scripts.seed`)
- The real `@jarv_m1_bot` Telegram binding with existing conversation history

## Note on §4 (cost guardrail)

`CostCapInterceptor` is a **graceful pre-flight blocker**, not a hard
run-killer. Before each LLM call it estimates cost (`provider.estimate_tokens`
→ `cost_model.cost`); if `run.total_cost + estimate > cap`, it returns a
synthetic `[blocked: cost cap …]` response. Steps "complete" cleanly with the
blocked content as their output, run-level cost stays at $0, and the operator
gets a precise diagnostic on every step ("spent $0, est +$0.0046 exceeds
$0.0001 cap"). A harder fail-and-stop mode would be a one-line policy change.
