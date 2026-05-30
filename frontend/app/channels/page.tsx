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
          {channels.length === 0 && (
            <div className="rounded-[var(--radius)] border border-dashed border-[var(--color-border)] p-10 text-center text-sm text-[var(--color-muted-foreground)]">
              No channels yet. Add a Telegram bot on the right to reach an agent from the outside world.
            </div>
          )}
          {channels.map((c) => {
            const isActive = c.status === "active";
            const isError = c.status === "error";
            const color = isActive ? "var(--color-status-completed)" : isError ? "var(--color-status-failed)" : "var(--color-muted-foreground)";
            const bound = bindings[c.id] ?? [];
            return (
              <div key={c.id} className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-4 transition-colors hover:border-[var(--color-primary)]/40">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="font-medium">{c.name}</span>
                    <span className="rounded border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[var(--color-muted-foreground)]">{c.type}</span>
                  </div>
                  {/* Proper status pill — green dot + label, with a pulse when active. */}
                  <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
                    style={{ borderColor: color, color }}>
                    <span className={`h-1.5 w-1.5 rounded-full ${isActive ? "hud-pulse" : ""}`} style={{ background: color }} />
                    {c.status}
                  </span>
                </div>
                {/* Bindings list: external_id → agent. Empty state nudges toward the form below. */}
                <div className="mt-2 space-y-0.5">
                  {bound.length === 0 ? (
                    <p className="text-xs text-[var(--color-muted-foreground)]">No bindings — bind a chat below to start receiving messages.</p>
                  ) : bound.map((b) => (
                    <div key={b.id} className="flex items-center gap-2 text-xs">
                      <span className="font-mono text-[var(--color-muted-foreground)]">{b.external_id === "*" ? "any chat" : b.external_id}</span>
                      <span className="text-[var(--color-muted-foreground)]">→</span>
                      <span>{agentName(b.agent_id)}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex gap-2">
                  <select className={FIELD} value={bindForm[c.id]?.agent_id ?? ""}
                    onChange={(e) => setBindForm({ ...bindForm, [c.id]: { ...(bindForm[c.id] ?? { external_id: "" }), agent_id: e.target.value } })}>
                    <option value="">pick agent…</option>
                    {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                  <input className={`${FIELD} flex-1`} placeholder="chat id or *"
                    value={bindForm[c.id]?.external_id ?? ""}
                    onChange={(e) => setBindForm({ ...bindForm, [c.id]: { ...(bindForm[c.id] ?? { agent_id: "" }), external_id: e.target.value } })} />
                  <button onClick={() => bind(c.id)} className="rounded-md border border-[var(--color-border)] px-3 text-sm hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]">Bind</button>
                </div>
              </div>
            );
          })}
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
