"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Agent } from "@/lib/api";

interface Turn {
  role: string;
  content: string;
}

export default function ChatPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listAgents().then((a) => {
      setAgents(a);
      if (a.length && !agentId) setAgentId(a[0].id);
    }).catch((e) => setError(String(e)));
  }, [agentId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, sending]);

  function pickAgent(id: string) {
    setAgentId(id);
    setConversationId(undefined);  // fresh conversation per agent switch
    setTurns([]);
    setError(null);
  }

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
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
    } catch (err) {
      setError(String(err));
      setTurns((t) => [...t, { role: "assistant", content: "⚠️ failed — is the agent's provider key set? (LLM_MODE=live)" }]);
    } finally {
      setSending(false);
    }
  }

  const agent = agents.find((a) => a.id === agentId);

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* agent list */}
      <div className="w-64 shrink-0 overflow-auto rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3">
        <p className="mb-2 text-xs font-medium text-[var(--color-muted-foreground)]">Talk to an agent</p>
        <div className="space-y-1">
          {agents.map((a) => (
            <button key={a.id} onClick={() => pickAgent(a.id)}
              className={`block w-full rounded-md p-2 text-left text-sm ${a.id === agentId ? "bg-[var(--color-muted)]" : "hover:bg-[var(--color-muted)]"}`}>
              <div className="font-medium">{a.name}</div>
              <div className="text-xs text-[var(--color-muted-foreground)]">{a.role}</div>
            </button>
          ))}
        </div>
      </div>

      {/* conversation */}
      <div className="flex flex-1 flex-col rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]">
        <div className="border-b border-[var(--color-border)] px-4 py-3">
          <p className="font-medium">{agent?.name ?? "Select an agent"}</p>
          {agent && <p className="text-xs text-[var(--color-muted-foreground)]">{agent.role} · routing: {agent.task_type}</p>}
        </div>

        <div className="flex-1 space-y-3 overflow-auto p-4">
          {turns.length === 0 && (
            <p className="text-sm text-[var(--color-muted-foreground)]">Say hello to start the conversation.</p>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[75%] rounded-[var(--radius)] px-3 py-2 text-sm ${
                t.role === "user"
                  ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
                  : "border border-[var(--color-border)] bg-[var(--color-background)]"
              }`}>
                {t.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-[var(--radius)] border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-muted-foreground)]">…thinking</div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {error && <div className="px-4 pb-1 text-xs text-[var(--color-status-failed)]">{error}</div>}

        <form onSubmit={send} className="flex gap-2 border-t border-[var(--color-border)] p-3">
          <input
            className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
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
