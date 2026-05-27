"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Agent } from "@/lib/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => api.listAgents().then(setAgents).catch((e) => setError(String(e)));
  useEffect(() => { refresh(); }, []);

  async function remove(a: Agent) {
    if (!confirm(`Delete agent "${a.name}"? This can't be undone.`)) return;
    try {
      await api.deleteAgent(a.id);
      setAgents((list) => list.filter((x) => x.id !== a.id));
    } catch (e) {
      setError(String(e));
    }
  }

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
          <div key={a.id}
            className="flex items-center gap-3 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 hover:border-[var(--color-primary)]">
            <Link href={`/agents/${a.id}`} className="min-w-0 flex-1">
              <p className="font-medium">{a.name}</p>
              <p className="truncate text-sm text-[var(--color-muted-foreground)]">{a.role}</p>
            </Link>
            <div className="hidden items-center gap-2 sm:flex">
              {(a.persona?.traits ?? []).slice(0, 3).map((t) => (
                <span key={t} className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-muted-foreground)]">{t}</span>
              ))}
            </div>
            <span className="hidden font-mono text-xs text-[var(--color-muted-foreground)] md:inline">{a.model_name}</span>
            <Link href={`/agents/${a.id}`} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm">Edit</Link>
            <button
              onClick={() => remove(a)}
              title="Delete agent"
              className="rounded-md border border-[var(--color-status-failed)] px-3 py-1.5 text-sm text-[var(--color-status-failed)] hover:bg-[var(--color-status-failed)] hover:text-white">
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
