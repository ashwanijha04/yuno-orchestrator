# Yuno — recorded demo

Auto-driven 1:29 walkthrough of the platform end-to-end. Recorded with Playwright
against the running stack (no fakery; every API call, run, tool call, and
approval gate is real).

## Files

| | Size | Codec | Best for |
|---|---|---|---|
| `yuno-demo.mp4` | 1.4 MB | H.264 / yuv420p / 25 fps / 1440×900 / `+faststart` | Universal playback, embedding, submission attachment |
| `yuno-demo.webm` | 4.6 MB | VP8 (Playwright native) | Original; smaller than re-encoded but less compatible |

## What the video covers (in order)

| t≈ | Step | Brief requirement satisfied |
|---|---|---|
| 0:00 | **Cockpit** — gauges, the 15-specialist constellation around Jarvis, mission queue | Visual web UI · live monitoring |
| 0:09 | **Cited Research (demo)** — `web_search` TOOL node + Remy → Ana → Brie agent chain. Tool call lands as its own first-class step on the timeline. | "Run on a real runtime, execute real tools" · multi-agent collaboration |
| 0:48 | **PRD with Approval (demo)** — Pip drafts a PRD → **pauses on the human approval gate** → APPROVALS gauge ticks up on the cockpit → click Approve → Mara + Brie finish | Configurable interaction rules · agent communication · human-in-the-loop |
| 1:06 | **Team channels** — Slack-style #growth / #product / #research with seeded specialists | Multi-agent collaborative workflows |
| 1:13 | **Agents page** — search across 17 specialists, per-row Run / Chat / Edit | Agent CRUD · configurability |
| 1:20 | **Channels** — Telegram `@jarv_m1_bot` bound to Jarvis with an `ACTIVE` pill | External messaging channel (Telegram) |
| 1:25 | **Back to cockpit** — final state after the demo: SPEND and TOKENS have moved | Token + cost tracking |

## How to re-record

```bash
# 1. Make sure the stack is up and seeded
make up
make seed

# 2. Run the script (uses the Playwright install in /tmp/yuno-screens)
node /tmp/yuno-screens/demo.mjs

# 3. Convert WebM → MP4 (optional but recommended for embedding)
ffmpeg -i demo/yuno-demo.webm \
  -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p -movflags +faststart \
  demo/yuno-demo.mp4 -y
```

Recorded against:
- `LLM_MODE=live` with real provider keys
- Real Tavily web search
- 17 agents, 5 workflow templates, 3 team channels (all from `scripts.seed`)
