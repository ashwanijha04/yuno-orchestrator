"use client";

import { WorkflowBuilder } from "@/components/workflow-builder/builder";

export default function NewWorkflowPage() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">New workflow</h1>
      <WorkflowBuilder />
    </div>
  );
}
