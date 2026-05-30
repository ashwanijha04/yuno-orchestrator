"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, type Agent } from "@/lib/api";
import { Markdown } from "@/components/markdown";

// Role-tuned conversation starters — give the empty chat pane an obvious next
// action instead of "Say hello". Keyword-matched against the agent's role.
function starterPrompts(role: string): string[] {
  const r = role.toLowerCase();
  if (r.includes("research")) return ["What's been published on agent runtimes in the last month?", "Give me 3 credible sources on prompt caching and summarise each.", "What are people getting wrong about RAG in 2026?"];
  if (r.includes("analyst")) return ["Here are some research notes — pull out the 3 most important takeaways.", "What's the 'so what' across these findings?", "Steelman the weakest argument I'd find in this analysis."];
  if (r.includes("brief")) return ["Turn this analysis into a 4-bullet executive brief.", "Write a 30-second elevator brief for a busy exec.", "Rewrite this brief so a non-technical reader gets it."];
  if (r.includes("critic")) return ["Critique this draft and tell me what to fix first.", "What would a skeptical reader push back on?", "Score this on clarity, accuracy, and persuasiveness."];
  if (r.includes("draft") || r.includes("write")) return ["Draft a 200-word answer to this question.", "Take this rough idea and turn it into prose.", "Write a second pass on this — same content, sharper tone."];
  if (r.includes("product manager") || r.includes("prd")) return ["Turn this idea into a one-page PRD.", "What's the MVP scope and what's deliberately out?", "Define a success metric and the test for it."];
  if (r.includes("strateg")) return ["Turn this goal into a 4-week plan with milestones.", "What are the top 3 risks in this plan, ranked?", "What's the critical path to ship this in 30 days?"];
  if (r.includes("market")) return ["Give me 3 positioning angles for this product.", "Write a launch tweet + LinkedIn post for this.", "Who's the customer that *must* hear about this first?"];
  if (r.includes("design") || r.includes("ux")) return ["Sketch the core flow and the one screen that must feel great.", "What are the 3 empty states this product needs?", "Propose two opposite visual directions for the homepage."];
  if (r.includes("engineer") || r.includes("code")) return ["Write a Python script that summarises a folder of markdown files.", "Design a simple in-memory rate limiter with TTL.", "Review this snippet and call out the bugs."];
  if (r.includes("ops") || r.includes("finance")) return ["Lay out a rough budget + 6-week timeline for this plan.", "What dependencies are likely to slip?", "Estimate the per-month run cost at 1k DAU."];
  if (r.includes("counsel") || r.includes("legal")) return ["Flag the privacy + compliance risks in this proposal.", "What contract terms should I push back on here?", "Summarise GDPR's impact on storing chat transcripts."];
  if (r.includes("voice") || r.includes("user")) return ["Design 5 user-interview questions for this hypothesis.", "Cluster these quotes into 3 themes with evidence.", "What's the 'unsaid' thing customers actually want?"];
  if (r.includes("data") || r.includes("scientist")) return ["Compute the mean + 95% CI for this dataset.", "What's the effect size — is it actually big?", "Propose an A/B test for this change."];
  if (r.includes("chief") || r.includes("staff")) return ["Plan a week-long product sprint for me.", "Build a team and brief the AI agent runtime market.", "What should I be working on right now?"];
  if (r.includes("personal assistant") || r.includes("remember")) return ["Remember: I prefer briefings as 3 bullets, never paragraphs.", "What do you remember about me so far?", "Add to memory: my product launches on Friday."];
  return ["What can you do?", "Help me with something concrete you're best at.", "Tell me about yourself in one paragraph."];
}

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
  const searchParams = useSearchParams();
  const wantedAgentId = searchParams.get("agent"); // ?agent=<id> deep link from /agents
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState(""); // agent-rail search
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
      // Honour the ?agent=<id> deep link so "Chat" buttons on /agents open
      // straight into the right conversation.
      const target = wantedAgentId && a.find((x) => x.id === wantedAgentId)?.id;
      if (target) openAgent(target);
      else if (a.length && !agentId) openAgent(a[0].id);
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

  const agent = agents.find((a) => a.id === agentId);

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* agent list */}
      <div className="flex w-64 shrink-0 flex-col overflow-hidden rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]">
        <div className="border-b border-[var(--color-border)] p-3">
          <p className="mb-2 text-xs font-medium text-[var(--color-muted-foreground)]">Talk to an agent</p>
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search agents…"
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-2.5 py-1.5 text-xs outline-none placeholder:text-[var(--color-muted-foreground)] focus:border-[var(--color-primary)]" />
        </div>
        <div className="flex-1 space-y-1 overflow-auto p-2">
          {agents
            .filter((a) => !q || (a.name + " " + a.role).toLowerCase().includes(q.toLowerCase()))
            .map((a) => (
              <button key={a.id} onClick={() => openAgent(a.id)}
                className={`block w-full rounded-md p-2 text-left text-sm transition-colors ${a.id === agentId ? "bg-[var(--color-muted)] ring-1 ring-[var(--color-primary)]" : "hover:bg-[var(--color-muted)]"}`}>
                <div className="font-medium">{a.name}</div>
                <div className="line-clamp-1 text-xs text-[var(--color-muted-foreground)]">{a.role}</div>
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
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-4">
          {turns.length === 0 && agent && (
            // Role-aware starters — clicking sends immediately. Beats a generic
            // "Say hello" because the user instantly sees the agent's range.
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-wider text-[var(--color-muted-foreground)]">Try asking {agent.name.split(" ")[0]}…</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {starterPrompts(agent.role).map((s, i) => (
                  <button key={i}
                    onClick={() => { setInput(s); /* one-click send-on-pick UX */ setTimeout(() => (document.querySelector("form button[type=submit]") as HTMLButtonElement)?.click(), 0); }}
                    className="group rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-background)] p-3 text-left text-sm text-[var(--color-foreground)]/90 transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-foreground)]">
                    <span className="text-[var(--color-primary)] opacity-70 group-hover:opacity-100">›</span> {s}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-[var(--color-muted-foreground)]">…or type your own below. Conversation is remembered per agent.</p>
            </div>
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
