"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Approval, type RunDetail } from "@/lib/api";
import { subscribeRun, type RunEvent } from "@/lib/ws";
import { Markdown } from "@/components/markdown";
import { AgentComms } from "@/components/agent-comms";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)",
  completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)",
  pending: "var(--color-status-pending)",
  cancelled: "var(--color-muted-foreground)",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className="rounded-full px-2.5 py-0.5 text-xs text-white" style={{ background: STATUS_COLOR[status] ?? "var(--color-muted)" }}>
      {status}
    </span>
  );
}

function Thinking({ label = "thinking" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-[var(--color-status-running)]">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-status-running)] [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-status-running)] [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-status-running)]" />
      </span>
      {label}…
    </span>
  );
}

const ACTIVE = (s: string) => s === "running" || s === "pending";

function qcolor(q: string): string {
  const v = parseFloat(q);
  if (v >= 0.75) return "var(--color-status-completed)";
  if (v >= 0.5) return "var(--color-status-paused)";
  return "var(--color-status-failed)";
}

function latency(start: string, end: string | null): string | null {
  if (!end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms >= 0 ? `${(ms / 1000).toFixed(1)}s` : null;
}

export function LiveRun({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [liveStatus, setLiveStatus] = useState("pending");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [busy, setBusy] = useState(false);
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reload = () => api.getRun(runId).then((r) => { setRun(r); setLiveStatus(r.status); }).catch(() => {});

  // When paused, find this run's pending approval so we can act on it.
  useEffect(() => {
    if (run?.status !== "paused") { setApproval(null); return; }
    api.listApprovals().then((a) => setApproval(a.find((x) => x.run_id === runId) ?? null)).catch(() => {});
  }, [run?.status, runId]);

  async function decide(decision: "approve" | "reject") {
    if (!approval) return;
    setBusy(true);
    try { await api.decideApproval(approval.id, decision); setApproval(null); await reload(); }
    finally { setBusy(false); }
  }
  async function evaluate() {
    setBusy(true);
    try { await api.evaluateRun(runId); await reload(); } finally { setBusy(false); }
  }
  async function feedback(positive: boolean) {
    setBusy(true);
    try { await api.feedbackRun(runId, positive); await reload(); } finally { setBusy(false); }
  }

  useEffect(() => {
    let alive = true;
    setRun(null); setLiveStatus("pending");
    const apply = (r: RunDetail) => { if (alive) { setRun(r); setLiveStatus(r.status); } };
    const load = () => api.getRun(runId).then(apply).catch(() => {});
    load();
    const refetch = () => {
      if (refetchTimer.current) clearTimeout(refetchTimer.current);
      refetchTimer.current = setTimeout(load, 150);
    };
    // WS = instant parent transitions; interval = live sub-task (child) progress,
    // since delegated children change status inside the orchestrator's step.
    const unsub = subscribeRun(runId, (ev: RunEvent) => {
      if (ev.type === "step.started") setLiveStatus("running");
      if (["step.started", "step.completed", "run.completed", "run.failed"].includes(ev.type)) refetch();
    });
    const poll = setInterval(async () => {
      const r = await api.getRun(runId).catch(() => null);
      if (!r) return;
      apply(r);
      if (r.status === "completed" || r.status === "failed") clearInterval(poll);
    }, 1300);
    return () => { alive = false; unsub(); clearInterval(poll); if (refetchTimer.current) clearTimeout(refetchTimer.current); };
  }, [runId]);

  const status = run?.status && run.status !== "pending" ? run.status : liveStatus;
  const steps = run?.steps ?? [];
  // Agent (assistant) turns, for the conversation transcript.
  const turns = (run?.messages ?? []).filter((m) => ["assistant", "agent", "tool"].includes(m.role));
  // Per-step long-term-memory recall note (persisted as a 🧠 system message).
  const memNote: Record<string, string> = {};
  (run?.messages ?? []).forEach((m) => {
    if (m.step_id && m.role === "system" && m.content.startsWith("🧠")) memNote[m.step_id] = m.content;
  });

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
          {run?.quality != null && (
            <span className="rounded-full border px-2 py-0.5 font-mono text-xs"
              style={{ color: qcolor(run.quality), borderColor: qcolor(run.quality) }}>
              Q {Math.round(parseFloat(run.quality) * 100)}
            </span>
          )}
          {running && (
            <button
              onClick={() => api.cancelRun(runId).catch(() => {})}
              className="ml-auto shrink-0 rounded-md border border-[var(--color-status-failed)] px-2 py-0.5 text-xs text-[var(--color-status-failed)] hover:bg-[var(--color-status-failed)] hover:text-white">
              ■ Stop
            </button>
          )}
          <a href={`/runs/${runId}`} className={`${running ? "" : "ml-auto "}shrink-0 text-xs text-[var(--color-muted-foreground)] hover:underline`}>open run →</a>
        </div>
        {run?.task && (
          <div className="mt-2">
            <p className="text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">Task</p>
            <p className="mt-0.5 break-words text-base font-medium leading-snug">{run.task}</p>
          </div>
        )}
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

      {/* Human-in-the-loop: a paused run awaiting approval */}
      {status === "paused" && approval && (
        <div className="glow rounded-[var(--radius)] border border-[var(--color-status-paused)] bg-[var(--color-card)] p-4">
          <p className="text-sm font-medium text-[var(--color-status-paused)]">⏸ Approval required</p>
          <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">{approval.summary}</p>
          <div className="mt-3 flex gap-2">
            <button disabled={busy} onClick={() => decide("approve")}
              className="rounded-md bg-[var(--color-status-completed)] px-3 py-1.5 text-sm font-medium text-[var(--color-primary-foreground)] disabled:opacity-50">
              ✓ Approve & resume
            </button>
            <button disabled={busy} onClick={() => decide("reject")}
              className="rounded-md border border-[var(--color-status-failed)] px-3 py-1.5 text-sm text-[var(--color-status-failed)] disabled:opacity-50">
              ✕ Reject
            </button>
          </div>
        </div>
      )}

      {/* Quality: evaluate + 👍/👎, shown once the run has finished */}
      {(status === "completed" || status === "failed") && (
        <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3 text-sm">
          <span className="text-xs text-[var(--color-muted-foreground)]">Quality</span>
          <button disabled={busy} onClick={evaluate}
            className="rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs hover:border-[var(--color-primary)] disabled:opacity-50">
            ✦ Evaluate
          </button>
          <button disabled={busy} onClick={() => feedback(true)} title="Good"
            className="rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs hover:border-[var(--color-status-completed)] disabled:opacity-50">👍</button>
          <button disabled={busy} onClick={() => feedback(false)} title="Needs work"
            className="rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs hover:border-[var(--color-status-failed)] disabled:opacity-50">👎</button>
          {(run?.evaluations ?? []).slice(0, 1).map((e) => (
            <span key={e.id} className="ml-auto text-xs text-[var(--color-muted-foreground)]">
              {e.source === "judge" ? "judge" : "you"}: {e.verdict ?? "—"}
              {e.rationale ? ` · ${e.rationale.slice(0, 80)}` : ""}
            </span>
          ))}
        </div>
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
            <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-muted)] text-xs font-mono">{i + 1}</span>
              <span className="min-w-0 truncate font-medium">{s.agent_name ?? s.node_id}</span>
              <StatusPill status={s.status} />
              <span className="ml-auto flex items-center gap-3 font-mono text-xs text-[var(--color-muted-foreground)]">
                {s.tokens_in + s.tokens_out > 0 && <span>{(s.tokens_in + s.tokens_out).toLocaleString()} tok</span>}
                {latency(s.started_at, s.completed_at) && <span>{latency(s.started_at, s.completed_at)}</span>}
                {s.cost_usd !== "0" && <span>${s.cost_usd}</span>}
              </span>
            </div>
            {memNote[s.id] && (
              <div className="mb-2 inline-flex items-center rounded-full border border-[var(--color-status-running)]/40 bg-[var(--color-status-running)]/10 px-2 py-0.5 text-xs text-[var(--color-status-running)]">
                {memNote[s.id]}
              </div>
            )}
            {ACTIVE(s.status) && !s.output && <Thinking label="working" />}
            {s.output && (
              <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-background)] p-3">
                <Markdown>{s.output}</Markdown>
              </div>
            )}
            {s.error && <p className="mt-2 text-xs text-[var(--color-status-failed)]">{s.error}</p>}
          </div>
        ))}
      </div>

      {/* inter-agent conversation: who messaged whom, and the replies */}
      {(run?.children?.length ?? 0) > 0 && (
        <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <p className="mb-3 flex items-center gap-2 text-sm font-medium">
            💬 Agent conversation
            <span className="text-xs font-normal text-[var(--color-muted-foreground)]">
              {run!.children.length} exchange{run!.children.length > 1 ? "s" : ""}
            </span>
          </p>
          <AgentComms run={run!} />
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
