"use client";

import { use, useEffect, useState } from "react";
import { api, type RunDetail } from "@/lib/api";
import { subscribeRun, type RunEvent } from "@/lib/ws";

interface TimelineStep {
  node_id: string;
  agent?: string;
  status: string;
  cost_usd?: string;
}

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
};

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [status, setStatus] = useState<string>("pending");
  const [cost, setCost] = useState<string>("0");
  const [events, setEvents] = useState<string[]>([]);

  useEffect(() => {
    api.getRun(id).then((r) => {
      setRun(r);
      setStatus(r.status);
      setCost(r.total_cost_usd);
      setSteps(r.steps.map((s) => ({ node_id: s.node_id, status: s.status, cost_usd: s.cost_usd })));
    });

    const unsub = subscribeRun(id, (ev: RunEvent) => {
      setEvents((prev) => [...prev, `${ev.type} ${ev.node_id ?? ev.agent ?? ""}`.trim()]);
      if (ev.type === "snapshot") {
        setStatus(String(ev.status));
        setCost(String(ev.total_cost_usd ?? "0"));
        const snap = (ev.steps as TimelineStep[]) ?? [];
        if (snap.length) setSteps(snap);
        return;
      }
      if (ev.type === "step.started") {
        setStatus("running");
        setSteps((prev) =>
          prev.some((s) => s.node_id === ev.node_id)
            ? prev
            : [...prev, { node_id: String(ev.node_id), agent: ev.agent as string, status: "running" }],
        );
      }
      if (ev.type === "step.completed") {
        setSteps((prev) =>
          prev.map((s) =>
            s.node_id === ev.node_id
              ? { ...s, status: ev.blocked ? "failed" : "completed", cost_usd: String(ev.cost_usd ?? s.cost_usd) }
              : s,
          ),
        );
      }
      if (ev.type === "run.completed") setStatus("completed");
      if (ev.type === "run.failed") setStatus("failed");
      // Refresh authoritative totals from Postgres when the run ends.
      if (ev.type === "run.completed" || ev.type === "run.failed") {
        api.getRun(id).then((r) => { setRun(r); setCost(r.total_cost_usd); });
      }
    });
    return unsub;
  }, [id]);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Run</h1>
          <p className="font-mono text-xs text-[var(--color-muted-foreground)]">{id}</p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="rounded-full px-3 py-1 text-xs" style={{ background: STATUS_COLOR[status] ?? "var(--color-muted)", color: "white" }}>
            {status}
          </span>
          <span className="font-mono">${cost}</span>
        </div>
      </div>

      <div className="space-y-2 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
        {steps.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">Waiting for the first step…</p>
        )}
        {steps.map((s, i) => (
          <div key={`${s.node_id}-${i}`} className="flex items-center gap-3">
            <span className="w-40 truncate text-sm">{s.agent ?? s.node_id}</span>
            <div className="h-6 flex-1 overflow-hidden rounded">
              <div
                className="h-full transition-all duration-500"
                style={{
                  width: s.status === "running" ? "40%" : "100%",
                  background: STATUS_COLOR[s.status] ?? "var(--color-muted)",
                  opacity: s.status === "running" ? 0.7 : 1,
                }}
              />
            </div>
            <span className="w-20 text-right font-mono text-xs text-[var(--color-muted-foreground)]">
              {s.cost_usd ? `$${s.cost_usd}` : "—"}
            </span>
          </div>
        ))}
      </div>

      {run && run.messages.length > 0 && (
        <div className="space-y-3 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <p className="font-medium">Messages</p>
          {run.messages.map((m) => (
            <div key={m.id} className="text-sm">
              <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{m.role}</span>
              <p>{m.content}</p>
            </div>
          ))}
        </div>
      )}

      <details className="text-xs text-[var(--color-muted-foreground)]">
        <summary className="cursor-pointer">event log</summary>
        <ul className="mt-2 space-y-1 font-mono">
          {events.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      </details>
    </div>
  );
}
