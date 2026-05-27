"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Agent } from "@/lib/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listAgents().then(setAgents).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Agents</h1>
        <Link href="/agents/new" className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">
          New agent
        </Link>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-status-failed)] p-3 text-sm text-[var(--color-status-failed)]">{error}</div>
      )}
      {!error && agents.length === 0 && (
        <p className="text-sm text-[var(--color-muted-foreground)]">No agents yet — create one.</p>
      )}

      <div className="space-y-2">
        {agents.map((a) => (
          <Link key={a.id} href={`/agents/${a.id}`}
            className="block rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 hover:border-[var(--color-primary)]">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">{a.name}</p>
                <p className="text-sm text-[var(--color-muted-foreground)]">{a.role}</p>
              </div>
              <div className="flex items-center gap-3">
                {(a.persona?.traits ?? []).slice(0, 3).map((t) => (
                  <span key={t} className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-muted-foreground)]">{t}</span>
                ))}
                <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{a.model_name}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
