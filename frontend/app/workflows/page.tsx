"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type Workflow } from "@/lib/api";

export default function WorkflowsPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.listWorkflows().then(setWorkflows).catch((e) => setError(String(e)));
  useEffect(() => { load(); }, []);

  async function run(wf: Workflow) {
    const topic = prompt(`Run "${wf.name}" — topic / input:`, "OpenAI funding 2026");
    if (topic === null) return;
    const r = await api.runWorkflow(wf.id, { topic, input: topic });
    router.push(`/runs/${r.id}`);
  }

  async function duplicate(wf: Workflow) {
    const copy = await api.duplicateWorkflow(wf.id);
    router.push(`/workflows/${copy.id}/edit`);
  }

  async function remove(wf: Workflow) {
    if (!confirm(`Delete workflow "${wf.name}" and its task history? This can't be undone.`)) return;
    await api.deleteWorkflow(wf.id);
    setWorkflows((list) => list.filter((x) => x.id !== wf.id));
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Workflows</h1>
        <Link href="/workflows/new" className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">
          New workflow
        </Link>
      </div>
      <p className="text-sm text-[var(--color-muted-foreground)]">
        Multi-agent graphs. Build one in the visual editor, run it, and watch the agents hand off on the timeline.
      </p>
      {error && <div className="rounded-md border border-[var(--color-status-failed)] p-3 text-sm text-[var(--color-status-failed)]">{error}</div>}

      <div className="space-y-2">
        {workflows.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">No workflows yet — run <code>make seed</code>.</p>
        )}
        {workflows.map((wf) => (
          <div key={wf.id} className="flex items-center justify-between rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
            <div>
              <p className="font-medium">{wf.name}</p>
              <p className="text-sm text-[var(--color-muted-foreground)]">{wf.description ?? "—"}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="mr-1 font-mono text-xs text-[var(--color-muted-foreground)]">v{wf.current_version}</span>
              <Link href={`/workflows/${wf.id}/edit`} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm">Edit</Link>
              <button onClick={() => duplicate(wf)} title="Duplicate" className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm">Duplicate</button>
              <button onClick={() => run(wf)} className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">Run</button>
              <button onClick={() => remove(wf)} title="Delete workflow" className="rounded-md border border-[var(--color-border)] px-2 py-1.5 text-sm text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">✕</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
