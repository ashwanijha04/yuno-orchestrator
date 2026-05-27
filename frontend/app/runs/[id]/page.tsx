"use client";

import { use } from "react";
import { LiveRun } from "@/components/live-run";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Run</h1>
        <p className="font-mono text-xs text-[var(--color-muted-foreground)]">{id}</p>
      </div>
      <LiveRun runId={id} />
    </div>
  );
}
