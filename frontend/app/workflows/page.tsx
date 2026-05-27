"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Workflow } from "@/lib/api";

export default function WorkflowsPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.listWorkflows().then(setWorkflows).catch((e) => setError(String(e))); }, []);

  async function run(wf: Workflow) {
    const topic = prompt(`Run "${wf.name}" — topic / input:`, "OpenAI funding 2026");
    if (topic === null) return;
    const r = await api.runWorkflow(wf.id, { topic, input: topic });
    router.push(`/runs/${r.id}`);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Workflows</h1>
      <p className="text-sm text-[var(--color-muted-foreground)]">
        Multi-agent graphs. Run one and watch the agents hand off on the timeline.
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
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-[var(--color-muted-foreground)]">v{wf.current_version}</span>
              <button onClick={() => run(wf)} className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">Run</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
