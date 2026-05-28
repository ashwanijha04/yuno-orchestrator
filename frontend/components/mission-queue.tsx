"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ChildRun, type Run } from "@/lib/api";
import { agentColor } from "@/components/agent-comms";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
  paused: "var(--color-status-paused)",
  cancelled: "var(--color-muted-foreground)",
};

/* The master-task queue: top-level missions (not delegated sub-runs), the active
   one highlighted. Each is clickable; its subtasks expand inline. */
export function MissionQueue() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [open, setOpen] = useState<Record<string, ChildRun[] | null>>({});

  useEffect(() => {
    const load = () =>
      api.listRuns()
        // drop delegated sub-runs + plain chat replies (only real missions here)
        .then((all) => setRuns(all.filter((r) => r.trigger_type !== "agent" && !r.conversational)))
        .catch(() => {});
    load();
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, []);

  async function toggle(r: Run) {
    if (r.id in open) {
      setOpen((o) => { const n = { ...o }; delete n[r.id]; return n; });
      return;
    }
    setOpen((o) => ({ ...o, [r.id]: null }));
    const d = await api.getRun(r.id).catch(() => null);
    setOpen((o) => ({ ...o, [r.id]: d?.children ?? [] }));
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3">
      <p className="mb-2 shrink-0 text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">
        Mission Queue
      </p>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {runs.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">No missions yet — ask Jarvis.</p>
        )}
        {runs.map((r) => {
          const active = r.status === "running" || r.status === "pending";
          const expanded = r.id in open;
          const kids = open[r.id];
          return (
            <div key={r.id}
              className={`rounded-md border bg-[var(--color-background)] ${active ? "glow" : ""}`}
              style={{ borderColor: active ? "var(--color-status-running)" : "var(--color-border)" }}>
              <div className="flex items-center gap-2 px-2 py-2">
                <button onClick={() => toggle(r)} aria-label={expanded ? "collapse subtasks" : "expand subtasks"}
                  title={expanded ? "Hide subtasks" : "Show subtasks"}
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-muted-foreground)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]">
                  <svg width="11" height="11" viewBox="0 0 16 16" fill="none"
                    style={{ transform: expanded ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>
                    <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${active ? "hud-pulse" : ""}`}
                  style={{ background: STATUS_COLOR[r.status] ?? "var(--color-muted)" }} />
                <Link href={`/runs/${r.id}`} className="min-w-0 flex-1 truncate text-sm hover:text-[var(--color-primary)]">
                  {r.task || r.workflow_name || "Task"}
                </Link>
                {r.quality != null && (
                  <span className="shrink-0 font-mono text-[10px] text-[var(--color-muted-foreground)]">
                    Q{Math.round(parseFloat(r.quality) * 100)}
                  </span>
                )}
                <span className="shrink-0 text-[10px] capitalize" style={{ color: STATUS_COLOR[r.status] }}>{r.status}</span>
              </div>
              {expanded && (
                <div className="space-y-1 border-t border-[var(--color-border)] px-2.5 py-2">
                  {kids === null && <p className="text-xs text-[var(--color-muted-foreground)]">loading…</p>}
                  {kids && kids.length === 0 && (
                    <p className="text-xs text-[var(--color-muted-foreground)]">No subtasks — answered directly.</p>
                  )}
                  {kids?.map((c) => (
                    <Link key={c.id} href={`/runs/${c.id}`} className="flex items-center gap-2 text-xs hover:underline">
                      <span className="shrink-0 font-medium" style={{ color: agentColor(c.agent_name ?? "") }}>
                        → {c.agent_name?.split(" ")[0] ?? "agent"}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[var(--color-muted-foreground)]">{c.task}</span>
                      <span className="shrink-0" style={{ color: STATUS_COLOR[c.status] }}>{c.status}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
