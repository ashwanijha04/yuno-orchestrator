"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Agent } from "@/lib/api";
import { AgentForm, fromAgent, type AgentFormValue } from "@/components/agent-form";
import { ChannelsPanel } from "@/components/channels-panel";

type Tab = "config" | "channels";

export default function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [tab, setTab] = useState<Tab>("config");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.getAgent(id).then(setAgent).catch((e) => setError(String(e))); }, [id]);

  async function save(v: AgentFormValue) {
    setSubmitting(true); setError(null); setSaved(false);
    try {
      const updated = await api.updateAgent(id, v);
      setAgent(updated); setSaved(true);
    } catch (e) { setError(String(e)); }
    finally { setSubmitting(false); }
  }

  async function run() {
    const input = prompt(`Message for ${agent?.name}:`);
    if (!input) return;
    const r = await api.quickRun(id, input);
    router.push(`/runs/${r.id}`);
  }

  async function remove() {
    if (!confirm(`Delete ${agent?.name}?`)) return;
    await api.deleteAgent(id);
    router.push("/agents");
  }

  if (!agent) return <p className="text-sm text-[var(--color-muted-foreground)]">{error ?? "Loading…"}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{agent.name}</h1>
          <p className="text-sm text-[var(--color-muted-foreground)]">{agent.role}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={run} className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">Run</button>
          <button onClick={remove} className="rounded-md border border-[var(--color-status-failed)] px-3 py-1.5 text-sm text-[var(--color-status-failed)]">Delete</button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-[var(--color-border)]">
        {(["config", "channels"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm capitalize ${tab === t ? "border-b-2 border-[var(--color-primary)] text-[var(--color-foreground)]" : "text-[var(--color-muted-foreground)]"}`}>
            {t}
          </button>
        ))}
        {saved && <span className="ml-auto self-center text-xs text-[var(--color-status-completed)]">saved ✓</span>}
      </div>

      {tab === "config" ? (
        <AgentForm initial={fromAgent(agent)} isNew={false} onSubmit={save} submitting={submitting} error={error} />
      ) : (
        <ChannelsPanel agentId={id} />
      )}
    </div>
  );
}
