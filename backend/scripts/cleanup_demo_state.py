"""Wipe ad-hoc test artefacts so the platform demos from a clean baseline.

Targets *named* test fixtures (Sender/Recipient/Mem Demo *, "T-08022b",
"UX Test *", debate->* workflows, etc.) and stale long-term memories that
reference deleted agents. Synthetic plumbing rows (chat:, msg->, channel:,
Orchestration ·, __chat__) are already hidden from the UI by
`_SYNTHETIC_PREFIXES` in `app/api/workflows.py`, so we leave them alone — their
runs still show up as meaningful Mission Queue history.

Idempotent: re-running on an already-clean DB is a no-op. Cascades take care of
runs → steps → messages → tool_invocations → llm_attempts.

Run:  docker compose exec backend python -m scripts.cleanup_demo_state
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import SessionFactory
from app.logging import configure_logging, get_logger

log = get_logger("cleanup")

# Named test agents that don't belong in a demo. The standing team — Jarvis,
# Athena/Mara/Pixel/Devin/Otto, Remy/Ana/Brie + Dex/Cy (templates), Mnemo,
# Orchestrator — is preserved.
JUNK_AGENT_NAMES = (
    "Sender",
    "Recipient",
    "Coffee Brand Marketer",
    "Espresso Enthusiast",
    "Coffee Expert",
    "AI Case Researcher",
    "Tagline Creator",
    "Launch Brief Drafter",
    "Launch Brief Writer",
    "Competitor Researcher",
    "Marketing Trends Researcher",
    "Marketing Specialist",
    "iOS Advocate",
    "Android Advocate",
)
JUNK_AGENT_LIKE = ("Mem Demo %", "MCP Tester %")

# Named test workflows + the auto-created `debate->*` ones (debate workflows
# proliferate quickly and add no demo value once the debate has happened).
JUNK_WORKFLOW_NAMES = (
    "T-08022b",
    "test",
    "UX Test 1779871771",
    "Approval Demo 1779903926",
    "Market Briefing (demo) (copy)",
    "Tool Node Demo 1779968954",
    "Failure Routing Demo 1779970125",
)
JUNK_WORKFLOW_LIKE = ("debate->%",)


async def main() -> None:
    configure_logging()
    async with SessionFactory() as session:
        # Phase 1: delete runs that touch either kill list. Cascades through
        # steps, messages, tool_invocations, llm_attempts, approvals,
        # media_assets, run_evaluations.
        result = await session.execute(
            text(
                """
                DELETE FROM runs WHERE
                  workflow_id IN (
                    SELECT id FROM workflows WHERE
                      name = ANY(:wf_names)
                      OR name LIKE ANY(:wf_like)
                  )
                  OR id IN (
                    SELECT DISTINCT run_id FROM steps WHERE agent_id IN (
                      SELECT id FROM agents WHERE
                        name = ANY(:ag_names)
                        OR name LIKE ANY(:ag_like)
                    )
                  )
                """
            ),
            {
                "wf_names": list(JUNK_WORKFLOW_NAMES),
                "wf_like": list(JUNK_WORKFLOW_LIKE),
                "ag_names": list(JUNK_AGENT_NAMES),
                "ag_like": list(JUNK_AGENT_LIKE),
            },
        )
        log.info("cleanup.runs_deleted", n=result.rowcount)

        # Phase 2: workflows (cascades workflow_versions; SET NULL on
        # agents.default_workflow_id and channel_bindings.workflow_id).
        result = await session.execute(
            text(
                """
                DELETE FROM workflows WHERE
                  name = ANY(:wf_names)
                  OR name LIKE ANY(:wf_like)
                """
            ),
            {"wf_names": list(JUNK_WORKFLOW_NAMES), "wf_like": list(JUNK_WORKFLOW_LIKE)},
        )
        log.info("cleanup.workflows_deleted", n=result.rowcount)

        # Phase 3: agents (channel_bindings.agent_id cascades).
        result = await session.execute(
            text(
                """
                DELETE FROM agents WHERE
                  name = ANY(:names)
                  OR name LIKE ANY(:like)
                """
            ),
            {"names": list(JUNK_AGENT_NAMES), "like": list(JUNK_AGENT_LIKE)},
        )
        log.info("cleanup.agents_deleted", n=result.rowcount)

        # Phase 4: orphan long-term memories that reference deleted agents by
        # name. Otherwise Jarvis recalls ghost teammates in chat replies.
        all_junk = list(JUNK_AGENT_NAMES) + ["Mem Demo", "MCP Tester"]
        result = await session.execute(
            text("DELETE FROM memories WHERE " + " OR ".join(f"content ILIKE :p{i}" for i in range(len(all_junk)))),
            {f"p{i}": f"%{name}%" for i, name in enumerate(all_junk)},
        )
        log.info("cleanup.memories_deleted", n=result.rowcount)

        # Phase 5: any 'pending'/'running' runs older than an hour are orphans
        # from previous worker restarts. Mark them cancelled so the cockpit
        # gauge ('RUNNING n') reflects reality.
        result = await session.execute(
            text(
                """
                UPDATE runs SET status='cancelled', completed_at=now(),
                  error='orphaned: cleanup_demo_state'
                WHERE status IN ('pending','running')
                  AND started_at < now() - interval '1 hour'
                """
            )
        )
        log.info("cleanup.stale_runs_cancelled", n=result.rowcount)

        # Phase 6: drop ad-hoc team channels ('test', 'marketing' with ghost
        # UUID members) so /team shows the seeded #growth/#product/#research
        # channels cleanly. Re-running seed re-creates the canonical set.
        result = await session.execute(
            text("DELETE FROM team_messages WHERE channel_id IN (SELECT id FROM team_channels WHERE name IN ('test','marketing'))")
        )
        await session.execute(
            text("DELETE FROM team_channels WHERE name IN ('test','marketing')")
        )
        log.info("cleanup.team_channels_dropped", n=result.rowcount)

        await session.commit()
        log.info("cleanup.done")


if __name__ == "__main__":
    asyncio.run(main())
