"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Agent } from "@/lib/api";

const FIELD = "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm";

export default function AgentsPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    role: "",
    system_prompt: "",
    model_provider: "anthropic",
    model_name: "claude-sonnet-4-6",
  });

  const refresh = () => api.listAgents().then(setAgents).catch((e) => setError(String(e)));
  useEffect(() => { refresh(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createAgent(form);
      setForm({ ...form, name: "", role: "", system_prompt: "" });
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function run(agent: Agent) {
    const input = prompt(`Message for ${agent.name}:`);
    if (!input) return;
    const r = await api.quickRun(agent.id, input);
    router.push(`/runs/${r.id}`);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Agents</h1>
      {error && (
        <div className="rounded-md border border-[var(--color-status-failed)] bg-[var(--color-card)] p-3 text-sm text-[var(--color-status-failed)]">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-3">
          {agents.length === 0 && (
            <p className="text-sm text-[var(--color-muted-foreground)]">No agents yet — create one.</p>
          )}
          {agents.map((a) => (
            <div key={a.id} className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{a.name}</p>
                  <p className="text-sm text-[var(--color-muted-foreground)]">{a.role}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{a.model_name}</span>
                  <button onClick={() => run(a)} className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)]">
                    Run
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <form onSubmit={create} className="h-fit space-y-3 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <p className="font-medium">New agent</p>
          <input className={FIELD} placeholder="Name" value={form.name} required
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className={FIELD} placeholder="Role" value={form.role} required
            onChange={(e) => setForm({ ...form, role: e.target.value })} />
          <textarea className={FIELD} placeholder="System prompt" rows={4} value={form.system_prompt} required
            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} />
          <input className={FIELD} placeholder="Model" value={form.model_name}
            onChange={(e) => setForm({ ...form, model_name: e.target.value })} />
          <button type="submit" className="w-full rounded-md bg-[var(--color-primary)] px-3 py-2 text-sm text-[var(--color-primary-foreground)]">
            Create agent
          </button>
        </form>
      </div>
    </div>
  );
}
