"use client";

import { useEffect, useState } from "react";
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

export function LiveRun({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [status, setStatus] = useState("pending");
  const [cost, setCost] = useState("0");

  useEffect(() => {
    setRun(null); setSteps([]); setStatus("pending"); setCost("0");
    api.getRun(runId).then((r) => {
      setRun(r); setStatus(r.status); setCost(r.total_cost_usd);
      setSteps(r.steps.map((s) => ({ node_id: s.node_id, status: s.status, cost_usd: s.cost_usd })));
    }).catch(() => {});

    const unsub = subscribeRun(runId, (ev: RunEvent) => {
      if (ev.type === "snapshot") {
        setStatus(String(ev.status)); setCost(String(ev.total_cost_usd ?? "0"));
        const snap = (ev.steps as TimelineStep[]) ?? [];
        if (snap.length) setSteps(snap);
        return;
      }
      if (ev.type === "step.started") {
        setStatus("running");
        setSteps((p) => p.some((s) => s.node_id === ev.node_id) ? p
          : [...p, { node_id: String(ev.node_id), agent: ev.agent as string, status: "running" }]);
      }
      if (ev.type === "step.completed") {
        setSteps((p) => p.map((s) => s.node_id === ev.node_id
          ? { ...s, status: ev.blocked ? "failed" : "completed", cost_usd: String(ev.cost_usd ?? s.cost_usd) } : s));
      }
      if (ev.type === "run.completed" || ev.type === "run.failed") {
        setStatus(ev.type === "run.completed" ? "completed" : "failed");
        api.getRun(runId).then((r) => { setRun(r); setCost(r.total_cost_usd); });
      }
    });
    return unsub;
  }, [runId]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <span className="rounded-full px-3 py-1 text-xs text-white" style={{ background: STATUS_COLOR[status] ?? "var(--color-muted)" }}>{status}</span>
        <span className="font-mono">${cost}</span>
        <a href={`/runs/${runId}`} className="ml-auto text-xs text-[var(--color-muted-foreground)] hover:underline">open run →</a>
      </div>

      {run?.error && (
        <div className="rounded-md border border-[var(--color-status-failed)] p-2 text-xs text-[var(--color-status-failed)]">
          {run.error}
        </div>
      )}

      <div className="space-y-2 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
        {steps.length === 0 && <p className="text-sm text-[var(--color-muted-foreground)]">Waiting for the first agent…</p>}
        {steps.map((s, i) => (
          <div key={`${s.node_id}-${i}`} className="flex items-center gap-3">
            <span className="w-40 truncate text-sm">{s.agent ?? s.node_id}</span>
            <div className="h-6 flex-1 overflow-hidden rounded">
              <div className="h-full transition-all duration-500"
                style={{ width: s.status === "running" ? "40%" : "100%", background: STATUS_COLOR[s.status] ?? "var(--color-muted)", opacity: s.status === "running" ? 0.7 : 1 }} />
            </div>
            <span className="w-20 text-right font-mono text-xs text-[var(--color-muted-foreground)]">{s.cost_usd ? `$${s.cost_usd}` : "—"}</span>
          </div>
        ))}
      </div>

      {run && run.messages.length > 0 && (
        <div className="space-y-2 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <p className="font-medium">Conversation &amp; handoffs</p>
          {run.messages.map((m) => {
            if (m.role === "agent") return (
              <div key={m.id} className="border-l-2 border-[var(--color-status-running)] pl-3 text-sm">
                <span className="text-xs font-medium text-[var(--color-status-running)]">→ handoff to another agent</span>
                <p className="text-[var(--color-muted-foreground)]">{m.content}</p>
              </div>
            );
            if (m.role === "tool") return (
              <div key={m.id} className="pl-3 font-mono text-xs text-[var(--color-muted-foreground)]">↳ tool · {m.content.slice(0, 160)}</div>
            );
            const blocked = m.content.startsWith("[blocked");
            return (
              <div key={m.id} className="text-sm">
                <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{m.role}</span>
                <p className={blocked ? "text-[var(--color-status-failed)]" : ""}>{m.content}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
