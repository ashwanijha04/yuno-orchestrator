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

  const agents = Array.from(new Set(run?.agent_names ?? []));
  const running = status === "running" || status === "pending";

  return (
    <div className="space-y-4">
      {/* task header */}
      <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
        <div className="flex items-center gap-3">
          {running && <span className="h-2.5 w-2.5 animate-pulse rounded-full" style={{ background: "var(--color-status-running)" }} />}
          <StatusPill status={status} />
          <span className="font-mono text-xs text-[var(--color-muted-foreground)]">${run?.total_cost_usd ?? "0"}</span>
          <a href={`/runs/${runId}`} className="ml-auto shrink-0 text-xs text-[var(--color-muted-foreground)] hover:underline">open run →</a>
        </div>
        {run?.task && <p className="mt-2 text-sm">{run.task}</p>}
        {agents.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-[var(--color-muted-foreground)]">
            <span>agents:</span>
            {agents.map((a) => (
              <span key={a} className="rounded-full border border-[var(--color-border)] px-2 py-0.5">{a}</span>
            ))}
          </div>
        )}
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

      {/* delegated sub-tasks: each agent the coordinator messaged + its result */}
      {(run?.children?.length ?? 0) > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Delegated to agents</p>
          {run!.children.map((c) => (
            <div key={c.id} className="rounded-[var(--radius)] border border-[var(--color-status-running)]/40 bg-[var(--color-card)] p-4">
              <div className="mb-1 flex items-center gap-2">
                <span className="text-xs font-medium text-[var(--color-status-running)]">→ {c.agent_name ?? "agent"}</span>
                <StatusPill status={c.status} />
                <a href={`/runs/${c.id}`} className="ml-auto text-xs text-[var(--color-muted-foreground)] hover:underline">sub-run →</a>
              </div>
              {c.task && <p className="mb-2 text-xs italic text-[var(--color-muted-foreground)]">“{c.task}”</p>}
              {c.output && (
                <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-background)] p-3">
                  <Markdown>{c.output}</Markdown>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* inter-agent handoff messages (the coordinator's delegation messages) */}
      {turns.some((m) => m.role === "tool") && (
        <details className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3 text-xs">
          <summary className="cursor-pointer text-[var(--color-muted-foreground)]">tool calls</summary>
          <div className="mt-2 space-y-1">
            {turns.filter((m) => m.role === "tool").map((m) => (
              <div key={m.id} className="font-mono text-[var(--color-muted-foreground)]">↳ {m.content.slice(0, 200)}</div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
