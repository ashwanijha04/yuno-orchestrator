"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type Workflow } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)", completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)", pending: "var(--color-status-pending)",
  paused: "var(--color-status-paused)", cancelled: "var(--color-muted-foreground)",
};
const BADGE: Record<string, string> = {
  tools: "🔧 tools", mcp: "🔌 MCP", human: "⏸ approval", branch: "🔀 branches", error: "⚠ failover",
};

function ago(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-muted-foreground)]">{children}</span>;
}

function WorkflowCard({ wf, onRun, onDuplicate, onDelete }: {
  wf: Workflow; onRun: (w: Workflow) => void; onDuplicate: (w: Workflow) => void; onDelete: (w: Workflow) => void;
}) {
  return (
    <div className="group flex flex-col rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 transition-colors hover:border-[var(--color-primary)]">
      <div className="flex items-start gap-2">
        <Link href={`/workflows/${wf.id}/edit`} className="min-w-0 flex-1">
          <p className="truncate font-medium hover:text-[var(--color-primary)]">{wf.name}</p>
          <p className="mt-0.5 line-clamp-2 text-xs text-[var(--color-muted-foreground)]">{wf.description || "No description"}</p>
        </Link>
        <span className="shrink-0 font-mono text-[10px] text-[var(--color-muted-foreground)]">v{wf.current_version}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Chip>👥 {wf.agent_count} agent{wf.agent_count === 1 ? "" : "s"}</Chip>
        <Chip>◇ {wf.node_count} node{wf.node_count === 1 ? "" : "s"}</Chip>
        {wf.badges.map((b) => <Chip key={b}>{BADGE[b] ?? b}</Chip>)}
      </div>

      <div className="mt-3 flex items-center gap-2 border-t border-[var(--color-border)] pt-3">
        <span className="flex min-w-0 flex-1 items-center gap-1.5 text-[11px] text-[var(--color-muted-foreground)]">
          {wf.last_run_status ? (
            <>
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: STATUS_COLOR[wf.last_run_status] ?? "var(--color-muted)" }} />
              <span className="truncate">{wf.last_run_status}{wf.last_run_at ? ` · ${ago(wf.last_run_at)}` : ""}</span>
            </>
          ) : <span>never run</span>}
        </span>
        <button onClick={() => onRun(wf)} className="shrink-0 rounded-md bg-[var(--color-primary)] px-2.5 py-1 text-xs font-medium text-[var(--color-primary-foreground)]">▶ Run</button>
        <Link href={`/workflows/${wf.id}/edit`} className="shrink-0 rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs">Edit</Link>
        <button onClick={() => onDuplicate(wf)} title="Duplicate" className="shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]">⧉</button>
        <button onClick={() => onDelete(wf)} title="Delete" className="shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">✕</button>
      </div>
    </div>
  );
}

function RunModal({ wf, onClose, onLaunched }: { wf: Workflow; onClose: () => void; onLaunched: (runId: string) => void }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      const r = await api.runWorkflow(wf.id, { topic: input, input, task: input });
      onLaunched(r.id);
    } finally { setBusy(false); }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="glow w-full max-w-lg rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-5" onClick={(e) => e.stopPropagation()}>
        <p className="text-sm font-medium">Run · {wf.name}</p>
        <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">Provide the input this workflow runs on.</p>
        <textarea autoFocus value={input} onChange={(e) => setInput(e.target.value)} rows={4}
          placeholder="e.g. the case for AI agents in enterprise support"
          className="mt-3 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]" />
        <div className="mt-3 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm">Cancel</button>
          <button onClick={go} disabled={busy || !input.trim()} className="rounded-md bg-[var(--color-primary)] px-4 py-1.5 text-sm font-medium text-[var(--color-primary-foreground)] disabled:opacity-50">
            {busy ? "Launching…" : "Run ▶"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function WorkflowsPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runTarget, setRunTarget] = useState<Workflow | null>(null);

  const load = () => api.listWorkflows().then(setWorkflows).catch((e) => setError(String(e)));
  useEffect(() => { load(); }, []);

  async function duplicate(wf: Workflow) {
    const copy = await api.duplicateWorkflow(wf.id);
    router.push(`/workflows/${copy.id}/edit`);
  }
  async function remove(wf: Workflow) {
    if (!confirm(`Delete workflow "${wf.name}" and its task history? This can't be undone.`)) return;
    await api.deleteWorkflow(wf.id);
    setWorkflows((list) => (list ?? []).filter((x) => x.id !== wf.id));
  }

  const templates = (workflows ?? []).filter((w) => w.is_template);
  const mine = (workflows ?? []).filter((w) => !w.is_template);
  const cardProps = { onRun: setRunTarget, onDuplicate: duplicate, onDelete: remove };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Workflows</h1>
          <p className="mt-0.5 text-sm text-[var(--color-muted-foreground)]">
            Design multi-agent flows — agents, tools &amp; MCP, branches, loops, approvals, and failover.
          </p>
        </div>
        <Link href="/workflows/new" className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-[var(--color-primary-foreground)]">
          ＋ New workflow
        </Link>
      </div>

      {error && <div className="rounded-md border border-[var(--color-status-failed)] p-3 text-sm text-[var(--color-status-failed)]">{error}</div>}

      {workflows === null && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => <div key={i} className="h-40 animate-pulse rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]" />)}
        </div>
      )}

      {workflows !== null && workflows.length === 0 && (
        <div className="rounded-[var(--radius)] border border-dashed border-[var(--color-border)] p-10 text-center">
          <p className="text-sm text-[var(--color-muted-foreground)]">No workflows yet.</p>
          <Link href="/workflows/new" className="mt-3 inline-block rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)]">Build your first workflow</Link>
        </div>
      )}

      {templates.length > 0 && (
        <section>
          <p className="mb-2 text-[11px] uppercase tracking-wider text-[var(--color-muted-foreground)]">Templates</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {templates.map((wf) => <WorkflowCard key={wf.id} wf={wf} {...cardProps} />)}
          </div>
        </section>
      )}

      {mine.length > 0 && (
        <section>
          {templates.length > 0 && <p className="mb-2 text-[11px] uppercase tracking-wider text-[var(--color-muted-foreground)]">Your workflows</p>}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {mine.map((wf) => <WorkflowCard key={wf.id} wf={wf} {...cardProps} />)}
          </div>
        </section>
      )}

      {/* Friendly nudge when only templates exist — keeps the page from feeling
          like a dead end and points at the two natural next steps. */}
      {workflows !== null && mine.length === 0 && templates.length > 0 && (
        <section>
          <p className="mb-2 text-[11px] uppercase tracking-wider text-[var(--color-muted-foreground)]">Start here</p>
          <div className="rounded-[var(--radius)] border border-dashed border-[var(--color-border)] bg-[var(--color-card)]/40 p-5 text-sm text-[var(--color-muted-foreground)]">
            Run a template above to see it execute, duplicate one to remix it, or{" "}
            <Link href="/workflows/new" className="text-[var(--color-primary)] hover:underline">build a new workflow from scratch</Link>{" "}
            with the visual builder.
          </div>
        </section>
      )}

      {runTarget && <RunModal wf={runTarget} onClose={() => setRunTarget(null)} onLaunched={(id) => router.push(`/runs/${id}`)} />}
    </div>
  );
}
