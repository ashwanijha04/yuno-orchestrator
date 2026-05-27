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

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  useEffect(() => { api.listRuns().then(setRuns).catch(() => {}); }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Runs</h1>
      <div className="space-y-2">
        {runs.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">No runs yet — run an agent.</p>
        )}
        {runs.map((r) => (
          <Link
            key={r.id}
            href={`/runs/${r.id}`}
            className="flex items-center justify-between rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 hover:border-[var(--color-primary)]"
          >
            <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{r.id.slice(0, 8)}</span>
            <span className="rounded-full px-3 py-1 text-xs" style={{ background: STATUS_COLOR[r.status] ?? "var(--color-muted)", color: "white" }}>
              {r.status}
            </span>
            <span className="font-mono text-xs">${r.total_cost_usd}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
