"use client";

import { useEffect, useState } from "react";
import { api, type Agent, type Binding, type Channel } from "@/lib/api";

const FIELD = "rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm";

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [bindings, setBindings] = useState<Record<string, Binding[]>>({});
  const [agents, setAgents] = useState<Agent[]>([]);
  const [form, setForm] = useState({ type: "telegram", name: "", bot_token: "" });
  const [bindForm, setBindForm] = useState<Record<string, { agent_id: string; external_id: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    const chs = await api.listChannels();
    setChannels(chs);
    const map: Record<string, Binding[]> = {};
    for (const c of chs) map[c.id] = await api.listBindings(c.id);
    setBindings(map);
  };
  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
    api.listAgents().then(setAgents).catch(() => {});
  }, []);

  const agentName = (id: string | null) => agents.find((a) => a.id === id)?.name ?? id ?? "—";

  async function addChannel(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createChannel({ type: form.type, name: form.name, config: form.bot_token ? { bot_token: form.bot_token } : {} });
      setForm({ type: "telegram", name: "", bot_token: "" });
      refresh();
    } catch (e) { setError(String(e)); }
  }

  async function bind(channelId: string) {
    const f = bindForm[channelId];
    if (!f?.external_id) return;
    await api.createBinding(channelId, { agent_id: f.agent_id || undefined, external_id: f.external_id });
    setBindForm({ ...bindForm, [channelId]: { agent_id: "", external_id: "" } });
    refresh();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Channels</h1>
        <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">
          Connect agents to external messaging (Telegram). Bind a chat (or <code>*</code> for any chat) to an agent.
        </p>
      </div>
      {error && <div className="rounded-md border border-[var(--color-status-failed)] p-3 text-sm text-[var(--color-status-failed)]">{error}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {channels.length === 0 && <p className="text-sm text-[var(--color-muted-foreground)]">No channels yet.</p>}
          {channels.map((c) => (
            <div key={c.id} className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
              <div className="flex items-center justify-between">
                <div><span className="font-medium">{c.name}</span> <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{c.type}</span></div>
                <span className="text-xs" style={{ color: c.status === "active" ? "var(--color-status-completed)" : "var(--color-muted-foreground)" }}>{c.status}</span>
              </div>
              {(bindings[c.id] ?? []).map((b) => (
                <div key={b.id} className="mt-1 text-xs text-[var(--color-muted-foreground)]">↳ {b.external_id} → {agentName(b.agent_id)}</div>
              ))}
              <div className="mt-2 flex gap-2">
                <select className={FIELD} value={bindForm[c.id]?.agent_id ?? ""}
                  onChange={(e) => setBindForm({ ...bindForm, [c.id]: { ...(bindForm[c.id] ?? { external_id: "" }), agent_id: e.target.value } })}>
                  <option value="">pick agent…</option>
                  {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <input className={`${FIELD} flex-1`} placeholder="chat id or *"
                  value={bindForm[c.id]?.external_id ?? ""}
                  onChange={(e) => setBindForm({ ...bindForm, [c.id]: { ...(bindForm[c.id] ?? { agent_id: "" }), external_id: e.target.value } })} />
                <button onClick={() => bind(c.id)} className="rounded-md border border-[var(--color-border)] px-3 text-sm">Bind</button>
              </div>
            </div>
          ))}
        </div>

        <form onSubmit={addChannel} className="h-fit space-y-3 rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <p className="font-medium">New channel</p>
          <select className={`${FIELD} w-full`} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="telegram">telegram</option>
            <option value="slack">slack (stub)</option>
            <option value="whatsapp">whatsapp (stub)</option>
          </select>
          <input className={`${FIELD} w-full`} placeholder="name" value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className={`${FIELD} w-full`} placeholder="bot token (Telegram)" value={form.bot_token} onChange={(e) => setForm({ ...form, bot_token: e.target.value })} />
          <button type="submit" className="w-full rounded-md bg-[var(--color-primary)] px-3 py-2 text-sm text-[var(--color-primary-foreground)]">Add channel</button>
          <p className="text-[10px] text-[var(--color-muted-foreground)]">Create a bot via @BotFather, paste the token, then bind it to an agent.</p>
        </form>
      </div>
    </div>
  );
}
