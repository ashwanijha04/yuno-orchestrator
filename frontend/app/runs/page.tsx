"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Run } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
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

  useEffect(() => {
    const load = () => api.listRuns().then(setRuns).catch(() => {});
    load();
    const t = setInterval(load, 3000); // keep the list fresh
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Tasks</h1>
        <Link href="/orchestrate" className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">
          ＋ New task
        </Link>
      </div>
      <div className="space-y-2">
        {runs.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">No tasks yet — orchestrate one.</p>
        )}
        {runs.map((r) => (
          <Link key={r.id} href={`/runs/${r.id}`}
            className="flex items-center gap-4 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 hover:border-[var(--color-primary)]">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: STATUS_COLOR[r.status] ?? "var(--color-muted)" }} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{r.task || r.workflow_name || "Run"}</p>
              <p className="truncate text-xs text-[var(--color-muted-foreground)]">
                {r.workflow_name ?? "—"} · {r.trigger_type} · {ago(r.started_at)}
              </p>
            </div>
            <span className="shrink-0 text-xs capitalize text-[var(--color-muted-foreground)]" style={{ color: STATUS_COLOR[r.status] }}>{r.status}</span>
            <span className="w-20 shrink-0 text-right font-mono text-xs text-[var(--color-muted-foreground)]">${r.total_cost_usd}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
