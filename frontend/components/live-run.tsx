"use client";

import { useEffect, useRef, useState } from "react";
import { api, type RunDetail } from "@/lib/api";
import { subscribeRun, type RunEvent } from "@/lib/ws";
import { Markdown } from "@/components/markdown";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className="rounded-full px-2.5 py-0.5 text-xs text-white" style={{ background: STATUS_COLOR[status] ?? "var(--color-muted)" }}>
      {status}
    </span>
  );
}

export function LiveRun({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [liveStatus, setLiveStatus] = useState("pending");
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setRun(null); setLiveStatus("pending");
    const load = () => api.getRun(runId).then((r) => { setRun(r); setLiveStatus(r.status); }).catch(() => {});
    load();
    // Coalesce refetches triggered by live events.
    const refetch = () => {
      if (refetchTimer.current) clearTimeout(refetchTimer.current);
      refetchTimer.current = setTimeout(load, 150);
    };
    const unsub = subscribeRun(runId, (ev: RunEvent) => {
      if (ev.type === "step.started") setLiveStatus("running");
      if (ev.type === "run.completed") setLiveStatus("completed");
      if (ev.type === "run.failed") setLiveStatus("failed");
      if (["step.started", "step.completed", "run.completed", "run.failed"].includes(ev.type)) refetch();
    });
    return () => { unsub(); if (refetchTimer.current) clearTimeout(refetchTimer.current); };
  }, [runId]);

  const status = run?.status && run.status !== "pending" ? run.status : liveStatus;
  const steps = run?.steps ?? [];
  // Agent (assistant) turns, for the conversation transcript.
  const turns = (run?.messages ?? []).filter((m) => ["assistant", "agent", "tool"].includes(m.role));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <StatusPill status={status} />
        <span className="font-mono text-[var(--color-muted-foreground)]">${run?.total_cost_usd ?? "0"}</span>
        {run?.task && <span className="truncate text-[var(--color-muted-foreground)]">· {run.task}</span>}
        <a href={`/runs/${runId}`} className="ml-auto shrink-0 text-xs text-[var(--color-muted-foreground)] hover:underline">open run →</a>
      </div>

      {run?.error && (
        <div className="rounded-md border border-[var(--color-status-failed)] p-2 text-xs text-[var(--color-status-failed)]">{run.error}</div>
      )}

      {/* who-is-doing-what: one card per agent step */}
      <div className="space-y-2">
        {steps.length === 0 && (
          <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 text-sm text-[var(--color-muted-foreground)]">
            Waiting for the first agent…
          </div>
        )}
        {steps.map((s, i) => (
          <div key={s.id} className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
            <div className="mb-2 flex items-center gap-3">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--color-muted)] text-xs font-mono">{i + 1}</span>
              <span className="font-medium">{s.agent_name ?? s.node_id}</span>
              <StatusPill status={s.status} />
              <span className="ml-auto font-mono text-xs text-[var(--color-muted-foreground)]">{s.cost_usd !== "0" ? `$${s.cost_usd}` : ""}</span>
            </div>
            {s.status === "running" && !s.output && (
              <p className="text-sm text-[var(--color-muted-foreground)]">working…</p>
            )}
            {s.output && (
              <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-background)] p-3">
                <Markdown>{s.output}</Markdown>
              </div>
            )}
            {s.error && <p className="mt-2 text-xs text-[var(--color-status-failed)]">{s.error}</p>}
          </div>
        ))}
      </div>

      {/* inter-agent handoffs + tool calls (if any) */}
      {turns.some((m) => m.role === "agent" || m.role === "tool") && (
        <div className="space-y-2 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <p className="text-sm font-medium">Handoffs &amp; tools</p>
          {turns.filter((m) => m.role === "agent" || m.role === "tool").map((m) => (
            m.role === "agent" ? (
              <div key={m.id} className="border-l-2 border-[var(--color-status-running)] pl-3 text-sm">
                <span className="text-xs font-medium text-[var(--color-status-running)]">→ handoff to another agent</span>
                <p className="text-[var(--color-muted-foreground)]">{m.content}</p>
              </div>
            ) : (
              <div key={m.id} className="pl-3 font-mono text-xs text-[var(--color-muted-foreground)]">↳ tool · {m.content.slice(0, 160)}</div>
            )
          ))}
        </div>
      )}
    </div>
  );
}
