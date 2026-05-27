"use client";

import { useEffect, useState } from "react";
import { api, type Agent, type Run } from "@/lib/api";
import { LiveRun } from "@/components/live-run";

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

const FIELD = "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm";

function Compose({ agents, onLaunched }: { agents: Agent[]; onLaunched: (runId: string) => void }) {
  const [task, setTask] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"pipeline" | "auto">("pipeline");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!task.trim()) return;
    setBusy(true); setError(null);
    try {
      const run = await api.orchestrate(task, selected, mode);
      onLaunched(run.id);
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  }

  return (
    <form onSubmit={go} className="space-y-4">
      <h2 className="text-lg font-semibold">New task</h2>
      <textarea className={FIELD} rows={3} placeholder="e.g. Research the case for AI agents and write a 3-bullet brief"
        value={task} onChange={(e) => setTask(e.target.value)} required />
      <div className="flex gap-2">
        {(["pipeline", "auto"] as const).map((m) => (
          <button key={m} type="button" onClick={() => setMode(m)}
            className={`flex-1 rounded-md border px-3 py-2 text-sm capitalize ${mode === m ? "border-[var(--color-primary)]" : "border-[var(--color-border)]"}`}>
            {m}
            <span className="block text-[10px] text-[var(--color-muted-foreground)]">
              {m === "pipeline" ? "selected agents, in order" : "orchestrator delegates"}
            </span>
          </button>
        ))}
      </div>
      <div>
        <p className="mb-1 text-xs font-medium text-[var(--color-muted-foreground)]">
          Agents{mode === "auto" ? " (optional — it picks from all if none chosen)" : ""}
        </p>
        <div className="max-h-72 space-y-1 overflow-auto">
          {agents.map((a) => (
            <label key={a.id} className="flex items-center gap-2 rounded-md border border-[var(--color-border)] p-2 text-sm">
              <input type="checkbox" checked={selected.includes(a.id)} onChange={() => toggle(a.id)} />
              <span className="flex-1"><span className="font-medium">{a.name}</span>
                <span className="text-xs text-[var(--color-muted-foreground)]"> — {a.role}</span></span>
              {mode === "pipeline" && selected.includes(a.id) && (
                <span className="font-mono text-[10px] text-[var(--color-muted-foreground)]">#{selected.indexOf(a.id) + 1}</span>
              )}
            </label>
          ))}
        </div>
      </div>
      <button type="submit" disabled={busy || !task.trim() || (mode === "pipeline" && selected.length === 0)}
        className="w-full rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)] disabled:opacity-50">
        {busy ? "Starting…" : "Orchestrate ▶"}
      </button>
      {error && <p className="text-xs text-[var(--color-status-failed)]">{error}</p>}
    </form>
  );
}

export default function OrchestratePage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [view, setView] = useState<"new" | string>("new");

  useEffect(() => { api.listAgents().then(setAgents).catch(() => {}); }, []);
  useEffect(() => {
    const load = () => api.listRuns().then(setRuns).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const selectedRun = view !== "new" ? runs.find((r) => r.id === view) : null;

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* tasks sidebar with history */}
      <aside className="flex w-72 shrink-0 flex-col rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]">
        <button onClick={() => setView("new")}
          className={`m-3 rounded-md px-3 py-2 text-sm font-medium ${view === "new" ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]" : "border border-[var(--color-border)]"}`}>
          ＋ New task
        </button>
        <p className="px-3 pb-1 text-xs font-medium text-[var(--color-muted-foreground)]">History</p>
        <div className="flex-1 space-y-1 overflow-auto px-2 pb-2">
          {runs.length === 0 && <p className="px-1 text-xs text-[var(--color-muted-foreground)]">No tasks yet.</p>}
          {runs.map((r) => (
            <button key={r.id} onClick={() => setView(r.id)}
              className={`block w-full rounded-md p-2 text-left ${view === r.id ? "bg-[var(--color-muted)]" : "hover:bg-[var(--color-muted)]"}`}>
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: STATUS_COLOR[r.status] ?? "var(--color-muted)" }} />
                <span className="flex-1 truncate text-xs">{r.task || r.workflow_name || "Run"}</span>
                <span className="shrink-0 text-[10px] text-[var(--color-muted-foreground)]">{ago(r.started_at)}</span>
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* main panel */}
      <main className="flex-1 overflow-auto">
        {view === "new" ? (
          <div className="max-w-xl">
            <Compose agents={agents} onLaunched={(id) => { setView(id); api.listRuns().then(setRuns).catch(() => {}); }} />
          </div>
        ) : (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">{selectedRun?.task || "Task"}</h2>
            <LiveRun runId={view} />
          </div>
        )}
      </main>
    </div>
  );
}
