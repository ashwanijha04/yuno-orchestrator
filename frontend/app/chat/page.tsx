"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Agent } from "@/lib/api";
import { Markdown } from "@/components/markdown";

interface Turn {
  role: string;
  content: string;
}

// Per-agent conversation id, persisted so history survives navigation/reload.
const convKey = (agentId: string) => `chat:conv:${agentId}`;
const getConv = (agentId: string): string | undefined =>
  (typeof window !== "undefined" ? localStorage.getItem(convKey(agentId)) : null) ?? undefined;
const setConv = (agentId: string, conv: string) => {
  if (typeof window !== "undefined") localStorage.setItem(convKey(agentId), conv);
};

export default function ChatPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load an agent's stored conversation history (if any).
  async function openAgent(id: string) {
    setAgentId(id);
    setError(null);
    const conv = getConv(id);
    setConversationId(conv);
    if (conv) {
      try { setTurns(await api.chatHistory(conv)); }
      catch { setTurns([]); }
    } else {
      setTurns([]);
    }
  }

  useEffect(() => {
    api.listAgents().then((a) => {
      setAgents(a);
      if (a.length && !agentId) openAgent(a[0].id);
    }).catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, sending]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !agentId || sending) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", content: text }]);
    setSending(true);
    setError(null);
    try {
      const res = await api.chat(agentId, text, conversationId);
      setConversationId(res.conversation_id);
      setConv(agentId, res.conversation_id);  // persist so history reloads later
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
    } catch (err) {
      setError(String(err));
      setTurns((t) => [...t, { role: "assistant", content: "⚠️ failed — is the agent's provider key set? (LLM_MODE=live)" }]);
    } finally {
      setSending(false);
    }
  }

  function newConversation() {
    if (!agentId) return;
    if (typeof window !== "undefined") localStorage.removeItem(convKey(agentId));
    setConversationId(undefined);
    setTurns([]);
  }

  const agent = agents.find((a) => a.id === agentId);

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* agent list */}
      <div className="w-64 shrink-0 overflow-auto rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3">
        <p className="mb-2 text-xs font-medium text-[var(--color-muted-foreground)]">Talk to an agent</p>
        <div className="space-y-1">
          {agents.map((a) => (
            <button key={a.id} onClick={() => openAgent(a.id)}
              className={`block w-full rounded-md p-2 text-left text-sm ${a.id === agentId ? "bg-[var(--color-muted)]" : "hover:bg-[var(--color-muted)]"}`}>
              <div className="font-medium">{a.name}</div>
              <div className="text-xs text-[var(--color-muted-foreground)]">{a.role}</div>
            </button>
          ))}
        </div>
      </div>

      {/* conversation */}
      <div className="flex flex-1 flex-col rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]">
        <div className="flex items-center gap-3 border-b border-[var(--color-border)] px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="font-medium">{agent?.name ?? "Select an agent"}</p>
            {agent && <p className="truncate text-xs text-[var(--color-muted-foreground)]">{agent.role} · routing: {agent.task_type}</p>}
          </div>
          {agent && turns.length > 0 && (
            <button onClick={newConversation} title="Start a fresh conversation"
              className="shrink-0 rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]">
              ＋ New chat
            </button>
          )}
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-4">
          {turns.length === 0 && (
            <p className="text-sm text-[var(--color-muted-foreground)]">Say hello to start the conversation.</p>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[75%] overflow-hidden break-words rounded-[var(--radius)] px-3 py-2 text-sm ${
                t.role === "user"
                  ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
                  : "border border-[var(--color-border)] bg-[var(--color-background)]"
              }`}>
                {t.role === "assistant" ? <Markdown>{t.content}</Markdown> : t.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-[var(--radius)] border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-muted-foreground)]">…thinking</div>
            </div>
          )}
        </div>

        {error && <div className="px-4 pb-1 text-xs text-[var(--color-status-failed)]">{error}</div>}

        <form onSubmit={send} className="flex gap-2 border-t border-[var(--color-border)] p-3">
          <input
            className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
            placeholder={agent ? `Message ${agent.name}…` : "Select an agent first"}
            value={input}
            disabled={!agentId || sending}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" disabled={!agentId || sending || !input.trim()}
            className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)] disabled:opacity-50">
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
