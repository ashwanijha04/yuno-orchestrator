"use client";

import { use, useEffect, useState } from "react";
import { api, type WorkflowDetail } from "@/lib/api";
import { WorkflowBuilder } from "@/components/workflow-builder/builder";

export default function EditWorkflowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [wf, setWf] = useState<WorkflowDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.getWorkflow(id).then(setWf).catch((e) => setError(String(e))); }, [id]);

  if (error) return <p className="text-sm text-[var(--color-status-failed)]">{error}</p>;
  if (!wf) return <p className="text-sm text-[var(--color-muted-foreground)]">Loading…</p>;

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">Edit: {wf.name} <span className="text-sm text-[var(--color-muted-foreground)]">v{wf.current_version}</span></h1>
      <WorkflowBuilder workflowId={id} initialName={wf.name} initialDescription={wf.description ?? ""} initialGraph={wf.graph} />
    </div>
  );
}
