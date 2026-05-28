"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Run } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
  cancelled: "var(--color-muted-foreground)",
};

function ago(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);

  // Tasks = real missions; plain chat replies live in the Chat tab.
  const load = () => api.listRuns().then((all) => setRuns(all.filter((r) => !r.conversational))).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  async function remove(r: Run) {
    if (!confirm(`Delete this task?\n\n${r.task || r.workflow_name || r.id}`)) return;
    await api.deleteRun(r.id);
    setRuns((list) => list.filter((x) => x.id !== r.id));
  }

  async function stop(r: Run) {
    await api.cancelRun(r.id).catch(() => {});
    load();
  }

  async function clearFinished() {
    const finished = runs.filter((r) => ["completed", "failed", "cancelled"].includes(r.status)).length;
    if (!finished || !confirm(`Clear ${finished} completed/failed task(s)? Running tasks are kept.`)) return;
    await api.clearFinishedRuns();
    load();
  }

  const hasFinished = runs.some((r) => ["completed", "failed", "cancelled"].includes(r.status));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Tasks</h1>
        <div className="flex gap-2">
          {hasFinished && (
            <button onClick={clearFinished} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">
              Clear completed
            </button>
          )}
          <Link href="/orchestrate" className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">
            ＋ New task
          </Link>
        </div>
      </div>
      <div className="space-y-2">
        {runs.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">No tasks yet — orchestrate one.</p>
        )}
        {runs.map((r) => (
          <div key={r.id}
            className="flex items-center gap-4 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 hover:border-[var(--color-primary)]">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: STATUS_COLOR[r.status] ?? "var(--color-muted)" }} />
            <Link href={`/runs/${r.id}`} className="min-w-0 flex-1">
              <p className="truncate font-medium">{r.task || r.workflow_name || "Run"}</p>
              <p className="truncate text-xs text-[var(--color-muted-foreground)]">
                {r.workflow_name ?? "—"} · {r.trigger_type} · {ago(r.started_at)}
              </p>
            </Link>
            <span className="shrink-0 text-xs capitalize" style={{ color: STATUS_COLOR[r.status] }}>{r.status}</span>
            <span className="hidden w-20 shrink-0 text-right font-mono text-xs text-[var(--color-muted-foreground)] sm:inline">${r.total_cost_usd}</span>
            {(r.status === "running" || r.status === "pending") && (
              <button onClick={() => stop(r)} title="Stop task"
                className="shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">
                ■
              </button>
            )}
            <button onClick={() => remove(r)} title="Delete task"
              className="shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
