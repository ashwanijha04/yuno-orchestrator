"use client";

import { useEffect, useState } from "react";
import { api, type Binding, type Channel } from "@/lib/api";

const FIELD =
  "rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm";

export function ChannelsPanel({ agentId }: { agentId: string }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [bindings, setBindings] = useState<Record<string, Binding[]>>({});
  const [newChannel, setNewChannel] = useState({ type: "telegram", name: "" });
  const [bindForm, setBindForm] = useState<{ channelId: string; externalId: string }>({ channelId: "", externalId: "" });

  const refresh = async () => {
    const chs = await api.listChannels();
    setChannels(chs);
    const map: Record<string, Binding[]> = {};
    for (const c of chs) map[c.id] = await api.listBindings(c.id);
    setBindings(map);
  };
  useEffect(() => { refresh().catch(() => {}); }, []);

  async function addChannel(e: React.FormEvent) {
    e.preventDefault();
    await api.createChannel(newChannel);
    setNewChannel({ type: "telegram", name: "" });
    refresh();
  }

  async function bind(channelId: string) {
    if (!bindForm.externalId) return;
    await api.createBinding(channelId, { agent_id: agentId, external_id: bindForm.externalId });
    setBindForm({ channelId: "", externalId: "" });
    refresh();
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--color-muted-foreground)]">
        Connect this agent to a channel so a human can reach it. (Live Telegram delivery lands in Phase 6.)
      </p>

      {channels.map((c) => {
        const mine = (bindings[c.id] ?? []).filter((b) => b.agent_id === agentId);
        return (
          <div key={c.id} className="rounded-md border border-[var(--color-border)] p-3 text-sm">
            <div className="flex items-center justify-between">
              <span><span className="font-medium">{c.name}</span> <span className="font-mono text-xs text-[var(--color-muted-foreground)]">{c.type}</span></span>
              <span className="text-xs text-[var(--color-muted-foreground)]">{mine.length} binding(s)</span>
            </div>
            {mine.map((b) => (
              <div key={b.id} className="mt-1 font-mono text-xs text-[var(--color-muted-foreground)]">↳ {b.external_id}</div>
            ))}
            <div className="mt-2 flex gap-2">
              <input className={FIELD} placeholder="chat / channel id"
                value={bindForm.channelId === c.id ? bindForm.externalId : ""}
                onChange={(e) => setBindForm({ channelId: c.id, externalId: e.target.value })} />
              <button onClick={() => bind(c.id)} className="rounded-md border border-[var(--color-border)] px-3 text-sm">Bind</button>
            </div>
          </div>
        );
      })}

      <form onSubmit={addChannel} className="flex gap-2">
        <select className={FIELD} value={newChannel.type} onChange={(e) => setNewChannel({ ...newChannel, type: e.target.value })}>
          <option value="telegram">telegram</option>
          <option value="slack">slack</option>
          <option value="whatsapp">whatsapp</option>
        </select>
        <input className={`${FIELD} flex-1`} placeholder="channel name" value={newChannel.name} required
          onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })} />
        <button type="submit" className="rounded-md border border-[var(--color-border)] px-3 text-sm">Add channel</button>
      </form>
    </div>
  );
}
