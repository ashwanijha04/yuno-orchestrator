"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type Agent } from "@/lib/api";

// Compact provider chip — the model name is enterprise-relevant info (cost +
// capability hints at a glance), so render it as a badge, not raw text.
function ModelBadge({ model }: { model: string }) {
  const family = model.includes("claude") ? "anthropic" : model.includes("gpt") ? "openai" : model.includes("gemini") ? "google" : "stub";
  const color = family === "anthropic" ? "var(--color-status-paused)" : family === "openai" ? "var(--color-status-completed)" : family === "google" ? "var(--color-primary)" : "var(--color-muted-foreground)";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-[10px]" style={{ borderColor: color, color }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {model}
    </span>
  );
}

export default function AgentsPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [busyRunId, setBusyRunId] = useState<string | null>(null);

  const refresh = () => api.listAgents().then(setAgents).catch((e) => setError(String(e)));
  useEffect(() => { refresh(); }, []);

  async function remove(a: Agent) {
    if (!confirm(`Delete agent "${a.name}"? This can't be undone.`)) return;
    try {
      await api.deleteAgent(a.id);
      setAgents((list) => (list ?? []).filter((x) => x.id !== a.id));
    } catch (e) {
      setError(String(e));
    }
  }

  async function quickRun(a: Agent) {
    const input = prompt(`Quick-run · ${a.name}\n\nWhat should ${a.name.split(" ")[0]} do?`);
    if (!input?.trim()) return;
    setBusyRunId(a.id);
    try {
      const r = await api.quickRun(a.id, input);
      router.push(`/runs/${r.id}`);
    } catch (e) {
      setError(String(e));
      setBusyRunId(null);
    }
  }

  // Client-side fuzzy filter — name, role, traits, and model so the search
  // bar is forgiving about how you remember an agent.
  const filtered = useMemo(() => {
    const list = agents ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((a) => {
      const hay = [a.name, a.role, a.model_name, ...(a.persona?.traits ?? [])].join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }, [agents, q]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
          <p className="mt-0.5 text-sm text-[var(--color-muted-foreground)]">
            {agents === null ? "Loading…" : `${agents.length} specialist${agents.length === 1 ? "" : "s"} on the roster. Soul · persona · tools · memory · guardrails — everything is configurable per agent.`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <input
              value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, role, trait, model…"
              className="w-72 rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-1.5 pl-8 text-sm outline-none placeholder:text-[var(--color-muted-foreground)] focus:border-[var(--color-primary)]" />
            <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-[var(--color-muted-foreground)]">⌕</span>
          </div>
          <Link href="/agents/new" className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-primary-foreground)]">
            ＋ New agent
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-status-failed)] p-3 text-sm text-[var(--color-status-failed)]">{error}</div>
      )}

      {agents === null && (
        <div className="space-y-2">
          {[0,1,2,3].map((i) => <div key={i} className="h-16 animate-pulse rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]" />)}
        </div>
      )}

      {agents !== null && agents.length === 0 && (
        <div className="rounded-[var(--radius)] border border-dashed border-[var(--color-border)] p-10 text-center">
          <p className="text-sm text-[var(--color-muted-foreground)]">No agents yet.</p>
          <Link href="/agents/new" className="mt-3 inline-block rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)]">Create your first agent</Link>
        </div>
      )}

      {agents !== null && agents.length > 0 && filtered.length === 0 && (
        <p className="text-sm text-[var(--color-muted-foreground)]">No match for &ldquo;{q}&rdquo;.</p>
      )}

      <div className="space-y-2">
        {filtered.map((a) => (
          <div key={a.id}
            className="group flex items-center gap-3 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 transition-colors hover:border-[var(--color-primary)]">
            <Link href={`/agents/${a.id}`} className="min-w-0 flex-1">
              <p className="font-medium leading-tight hover:text-[var(--color-primary)]">{a.name}</p>
              <p className="mt-0.5 truncate text-sm text-[var(--color-muted-foreground)]">{a.role}</p>
            </Link>
            <div className="hidden items-center gap-1.5 lg:flex">
              {(a.persona?.traits ?? []).slice(0, 3).map((t) => (
                <span key={t} className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">{t}</span>
              ))}
            </div>
            <div className="hidden md:block"><ModelBadge model={a.model_name} /></div>
            <button
              onClick={() => quickRun(a)}
              disabled={busyRunId === a.id}
              title="Quick-run this agent on a one-off prompt"
              className="rounded-md bg-[var(--color-primary)]/10 px-3 py-1.5 text-xs font-medium text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-[var(--color-primary-foreground)] disabled:opacity-50">
              {busyRunId === a.id ? "Launching…" : "▶ Run"}
            </button>
            <Link href={`/chat?agent=${a.id}`} title="Chat with this agent"
              className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]">
              💬 Chat
            </Link>
            <Link href={`/agents/${a.id}`} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs">Edit</Link>
            <button
              onClick={() => remove(a)}
              title="Delete agent"
              className="rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-xs text-[var(--color-muted-foreground)] hover:border-[var(--color-status-failed)] hover:text-[var(--color-status-failed)]">
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
