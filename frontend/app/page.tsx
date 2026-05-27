"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Run, type Stats } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
};

function ago(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function Stat({ label, value, href, accent }: { label: string; value: string | number; href?: string; accent?: string }) {
  const inner = (
    <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-5 transition-colors hover:border-[var(--color-primary)]">
      <p className="text-sm text-[var(--color-muted-foreground)]">{label}</p>
      <p className="mt-2 font-mono text-2xl" style={accent ? { color: accent } : undefined}>{value}</p>
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

export default function Dashboard() {
  const [s, setS] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);

  useEffect(() => {
    const load = () => {
      api.stats().then(setS).catch(() => {});
      api.listRuns().then((r) => setRuns(r.slice(0, 6))).catch(() => {});
    };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">Your agents, tasks, and spend at a glance.</p>
        </div>
        <Link href="/orchestrate" className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)]">
          Orchestrate a task ▶
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Agents" value={s?.agents ?? "—"} href="/agents" />
        <Stat label="Tasks (24h)" value={s?.runs_today ?? "—"} href="/runs" />
        <Stat label="Running now" value={s?.running ?? "—"} accent={s?.running ? "var(--color-status-running)" : undefined} href="/runs" />
        <Stat label="Total spend" value={s ? `$${s.total_cost_usd}` : "—"} />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Tasks total" value={s?.runs_total ?? "—"} href="/runs" />
        <Stat label="Completed" value={s?.completed ?? "—"} accent="var(--color-status-completed)" />
        <Stat label="Failed" value={s?.failed ?? "—"} accent={s?.failed ? "var(--color-status-failed)" : undefined} />
        <Stat label="Tokens used" value={s ? s.total_tokens.toLocaleString() : "—"} />
      </div>

      <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-medium">Recent tasks</p>
          <Link href="/runs" className="text-xs text-[var(--color-muted-foreground)] hover:underline">View all →</Link>
        </div>
        {runs.length === 0 && <p className="text-sm text-[var(--color-muted-foreground)]">No tasks yet — orchestrate one.</p>}
        <div className="space-y-1">
          {runs.map((r) => (
            <Link key={r.id} href={`/runs/${r.id}`} className="flex items-center gap-3 rounded-md p-2 hover:bg-[var(--color-muted)]">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: STATUS_COLOR[r.status] ?? "var(--color-muted)" }} />
              <span className="min-w-0 flex-1 truncate text-sm">{r.task || r.workflow_name || "Run"}</span>
              <span className="shrink-0 text-xs text-[var(--color-muted-foreground)]">{ago(r.started_at)}</span>
              <span className="w-16 shrink-0 text-right font-mono text-xs text-[var(--color-muted-foreground)]">${r.total_cost_usd}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
