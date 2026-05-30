"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type Run } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
  cancelled: "var(--color-muted-foreground)",
};

type StatusFilter = "all" | "running" | "completed" | "failed";

function ago(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function StatusPill({ status }: { status: string }) {
  const color = STATUS_COLOR[status] ?? "var(--color-muted-foreground)";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
      style={{ borderColor: color, color }}>
      <span className={`h-1.5 w-1.5 rounded-full ${status === "running" || status === "pending" ? "hud-pulse" : ""}`} style={{ background: color }} />
      {status}
    </span>
  );
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");

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
    setRuns((list) => (list ?? []).filter((x) => x.id !== r.id));
  }

  async function stop(r: Run) {
    await api.cancelRun(r.id).catch(() => {});
    load();
  }

  async function clearFinished() {
    const all = runs ?? [];
    const finished = all.filter((r) => ["completed", "failed", "cancelled"].includes(r.status)).length;
    if (!finished || !confirm(`Clear ${finished} completed/failed task(s)? Running tasks are kept.`)) return;
    await api.clearFinishedRuns();
    load();
  }

  // Count summary by status, computed once per refresh, used for filter chips.
  const counts = useMemo(() => {
    const all = runs ?? [];
    const isRunning = (s: string) => s === "running" || s === "pending";
    return {
      all: all.length,
      running: all.filter((r) => isRunning(r.status)).length,
      completed: all.filter((r) => r.status === "completed").length,
      failed: all.filter((r) => r.status === "failed" || r.status === "cancelled").length,
    };
  }, [runs]);

  const filtered = useMemo(() => {
    const all = runs ?? [];
    const needle = q.trim().toLowerCase();
    return all.filter((r) => {
      if (filter === "running" && r.status !== "running" && r.status !== "pending") return false;
      if (filter === "completed" && r.status !== "completed") return false;
      if (filter === "failed" && r.status !== "failed" && r.status !== "cancelled") return false;
      if (!needle) return true;
      const hay = [r.task, r.workflow_name, r.trigger_type, ...(r.agent_names ?? [])].filter(Boolean).join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }, [runs, q, filter]);

  const hasFinished = (runs ?? []).some((r) => ["completed", "failed", "cancelled"].includes(r.status));

  const chip = (k: StatusFilter, label: string, count: number, color?: string) => (
    <button onClick={() => setFilter(k)}
      className="rounded-full border px-3 py-1 text-xs transition-colors"
      style={{
        borderColor: filter === k ? (color ?? "var(--color-primary)") : "var(--color-border)",
        color: filter === k ? (color ?? "var(--color-primary)") : "var(--color-muted-foreground)",
        background: filter === k ? "var(--color-primary)/10" : "transparent",
      }}>
      {label} <span className="ml-1 font-mono opacity-80">{count}</span>
    </button>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
          <p className="mt-0.5 text-sm text-[var(--color-muted-foreground)]">
            Every run — workflow, chat, channel — with live status, cost, and a click-through to the timeline.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search task, workflow, agent…"
              className="w-72 rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-1.5 pl-8 text-sm outline-none placeholder:text-[var(--color-muted-foreground)] focus:border-[var(--color-primary)]" />
            <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-[var(--color-muted-foreground)]">⌕</span>
          </div>
          {hasFinished && (
            <button onClick={clearFinished} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">
              Clear completed
            </button>
          )}
          <Link href="/orchestrate" className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-primary-foreground)]">
            ＋ New task
          </Link>
        </div>
      </div>

      {/* Filter chips with live counts — enterprise-table staple. */}
      <div className="flex flex-wrap items-center gap-2">
        {chip("all", "All", counts.all)}
        {chip("running", "Running", counts.running, "var(--color-status-running)")}
        {chip("completed", "Completed", counts.completed, "var(--color-status-completed)")}
        {chip("failed", "Failed", counts.failed, "var(--color-status-failed)")}
        {filtered.length !== counts.all && (
          <span className="ml-auto text-xs text-[var(--color-muted-foreground)]">Showing {filtered.length} of {counts.all}</span>
        )}
      </div>

      {runs === null && (
        <div className="space-y-2">
          {[0,1,2,3].map((i) => <div key={i} className="h-14 animate-pulse rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]" />)}
        </div>
      )}

      {runs !== null && counts.all === 0 && (
        <div className="rounded-[var(--radius)] border border-dashed border-[var(--color-border)] p-10 text-center">
          <p className="text-sm text-[var(--color-muted-foreground)]">No tasks yet.</p>
          <Link href="/workflows" className="mt-3 inline-block rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)]">Run a workflow template</Link>
        </div>
      )}

      {runs !== null && counts.all > 0 && filtered.length === 0 && (
        <p className="text-sm text-[var(--color-muted-foreground)]">No tasks match the current filter.</p>
      )}

      <div className="space-y-2">
        {filtered.map((r) => (
          <div key={r.id}
            className="group flex items-center gap-3 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3.5 transition-colors hover:border-[var(--color-primary)]">
            <Link href={`/runs/${r.id}`} className="min-w-0 flex-1">
              <p className="truncate font-medium">{r.task || r.workflow_name || "Run"}</p>
              <p className="mt-0.5 truncate text-xs text-[var(--color-muted-foreground)]">
                <span className="font-mono">{r.workflow_name ?? "ad-hoc"}</span> · {r.trigger_type} · {ago(r.started_at)}
                {r.agent_names?.length ? <> · {r.agent_names.slice(0, 3).join(", ")}{r.agent_names.length > 3 ? ` +${r.agent_names.length - 3}` : ""}</> : null}
              </p>
            </Link>
            <StatusPill status={r.status} />
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
