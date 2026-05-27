"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Agent } from "@/lib/api";
import { LiveRun } from "@/components/live-run";

const FIELD = "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm";

export default function OrchestratePage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [task, setTask] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"pipeline" | "auto">("auto");
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.listAgents().then(setAgents).catch((e) => setError(String(e))); }, []);

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!task.trim()) return;
    setBusy(true); setError(null); setRunId(null);
    try {
      const run = await api.orchestrate(task, selected, mode);
      setRunId(run.id);
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Orchestrate</h1>
          <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">
            Describe a task, choose agents (or let the orchestrator plan it), and watch them collaborate live.
          </p>
        </div>
        <Link href="/runs" className="text-sm text-[var(--color-muted-foreground)] hover:underline">View all tasks →</Link>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        <form onSubmit={go} className="h-fit space-y-4 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-muted-foreground)]">Task</label>
            <textarea className={FIELD} rows={3} placeholder="e.g. Research the case for AI agents and write a 3-bullet brief"
              value={task} onChange={(e) => setTask(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-muted-foreground)]">Mode</label>
            <div className="flex gap-2">
              {(["auto", "pipeline"] as const).map((m) => (
                <button key={m} type="button" onClick={() => setMode(m)}
                  className={`flex-1 rounded-md border px-3 py-2 text-sm capitalize ${mode === m ? "border-[var(--color-primary)]" : "border-[var(--color-border)]"}`}>
                  {m === "auto" ? "agentic" : m}
                  <span className="block text-[10px] text-[var(--color-muted-foreground)]">
                    {m === "auto" ? "plans, creates & delegates" : "selected agents, in order"}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-muted-foreground)]">
              Agents{mode === "auto" ? " (optional — it reuses these or creates new ones as needed)" : ""}
            </label>
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

        <div>
          {runId ? (
            <LiveRun runId={runId} />
          ) : (
            <div className="flex h-full min-h-48 items-center justify-center rounded-[var(--radius)] border border-dashed border-[var(--color-border)] text-sm text-[var(--color-muted-foreground)]">
              The live collaboration will appear here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
