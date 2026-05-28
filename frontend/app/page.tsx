"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type Agent, type Approval, type Stats } from "@/lib/api";
import { AgentConstellation } from "@/components/agent-constellation";
import { MissionQueue } from "@/components/mission-queue";
import { Markdown } from "@/components/markdown";

function Gauge({ label, value, accent, pulse }: { label: string; value: string | number; accent?: string; pulse?: boolean }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-[var(--radius)] border bg-[var(--color-card)] p-3"
      style={{ borderColor: pulse ? "var(--color-status-running)" : "var(--color-border)" }}>
      <p className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">
        {pulse && <span className="h-1.5 w-1.5 shrink-0 rounded-full hud-pulse" style={{ background: "var(--color-status-running)" }} />}
        {label}
      </p>
      <p className="mt-1 truncate font-mono text-xl" style={accent ? { color: accent } : undefined}>{value}</p>
    </div>
  );
}

type Turn = { role: "user" | "assistant"; content: string };

function JarvisConsole({ jarvisId }: { jarvisId: string | null }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [convo, setConvo] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Scroll the message list itself — not the page.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  async function send() {
    const msg = input.trim();
    if (!msg || !jarvisId || busy) return;
    setInput(""); setBusy(true);
    setTurns((t) => [...t, { role: "user", content: msg }]);
    try {
      const res = await api.chat(jarvisId, msg, convo);
      setConvo(res.conversation_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "assistant", content: `⚠️ ${String(e)}` }]);
    } finally { setBusy(false); }
  }

  return (
    <div className="flex h-full flex-col rounded-[var(--radius)] border border-[var(--color-primary)]/40 bg-[var(--color-card)] glow">
      <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-2.5">
        <span className="h-2 w-2 rounded-full hud-pulse" style={{ background: "var(--color-primary)" }} />
        <span className="font-mono text-sm text-glow" style={{ color: "var(--color-primary)" }}>JARVIS</span>
        <span className="text-xs text-[var(--color-muted-foreground)]">· your AI chief of staff</span>
      </div>
      <div ref={scrollRef} className="min-h-[180px] flex-1 space-y-3 overflow-auto p-4">
        {turns.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">
            Ask me to plan something, build a team of agents, or run a task. e.g.{" "}
            <em>“Research the case for AI agents and write a 3-bullet brief.”</em>
          </p>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <div className={`inline-block max-w-[90%] overflow-hidden break-words rounded-[var(--radius)] px-3 py-2 text-left text-sm ${
              t.role === "user" ? "bg-[var(--color-muted)]" : "border border-[var(--color-border)] bg-[var(--color-background)]"}`}>
              {t.role === "assistant" ? <Markdown>{t.content}</Markdown> : t.content}
            </div>
          </div>
        ))}
        {busy && <p className="text-xs text-[var(--color-status-running)] hud-pulse">Jarvis is thinking…</p>}
      </div>
      <div className="flex gap-2 border-t border-[var(--color-border)] p-3">
        <input
          value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder={jarvisId ? "Tell Jarvis what to do…" : "Seed agents to enable Jarvis (python -m scripts.seed)"}
          disabled={!jarvisId || busy}
          className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)] disabled:opacity-50" />
        <button onClick={send} disabled={!jarvisId || busy || !input.trim()}
          className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-[var(--color-primary-foreground)] disabled:opacity-50">
          Send
        </button>
      </div>
    </div>
  );
}

export default function Cockpit() {
  const [s, setS] = useState<Stats | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [coding, setCoding] = useState<{ id: string; task: string; plan: string }[]>([]);
  const [jarvis, setJarvis] = useState<string | null>(null);
  const [bridge, setBridge] = useState(false);

  useEffect(() => {
    api.listAgents().then((a) => setJarvis(a.find((x: Agent) => x.name === "Jarvis")?.id ?? null)).catch(() => {});
    const load = () => {
      api.stats().then(setS).catch(() => {});
      api.listApprovals().then(setApprovals).catch(() => {});
      api.codingApprovals().then(setCoding).catch(() => setCoding([]));
      api.codingBridgeStatus().then((b) => setBridge(b.connected)).catch(() => setBridge(false));
    };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  async function decide(a: Approval, decision: "approve" | "reject") {
    await api.decideApproval(a.id, decision).catch(() => {});
    setApprovals((list) => list.filter((x) => x.id !== a.id));
  }
  async function decideCoding(id: string, decision: "allow" | "deny") {
    await api.decideCoding(id, decision).catch(() => {});
    setCoding((list) => list.filter((x) => x.id !== id));
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Mission Control</h1>
          <p className="mt-0.5 text-sm text-[var(--color-muted-foreground)]">Talk to Jarvis. Watch the team work.</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 rounded-full border border-[var(--color-border)] px-2.5 py-1 text-xs"
            title={bridge ? "Local Claude Code bridge is connected — Jarvis can run coding tasks on this machine" : "No coding bridge — run `make up` or `python3 scripts/claude_bridge.py`"}>
            <span className={`h-2 w-2 rounded-full ${bridge ? "hud-pulse" : ""}`}
              style={{ background: bridge ? "var(--color-status-completed)" : "var(--color-muted-foreground)" }} />
            <span className="text-[var(--color-muted-foreground)]">coding bridge {bridge ? "connected" : "offline"}</span>
          </span>
          <Link href="/workflows/new" className="rounded-md border border-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-[var(--color-primary-foreground)]">
            Build a workflow ▶
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Gauge label="Running" value={s?.running ?? "—"} accent={s?.running ? "var(--color-status-running)" : undefined} pulse={!!s?.running} />
        <Gauge label="Approvals" value={approvals.length} accent={approvals.length ? "var(--color-status-paused)" : undefined} pulse={approvals.length > 0} />
        <Gauge label="Agents" value={s?.agents ?? "—"} />
        <Gauge label="Spend" value={s ? `$${s.total_cost_usd}` : "—"} />
        <Gauge label="Tokens" value={s ? s.total_tokens.toLocaleString() : "—"} />
      </div>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
        <div className="h-[480px] min-w-0"><JarvisConsole jarvisId={jarvis} /></div>
        <div className="hud-grid h-[480px] min-w-0 overflow-hidden rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)]/40 p-3">
          <AgentConstellation />
        </div>
      </div>

      <div className="h-[300px]"><MissionQueue /></div>

      {coding.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--color-status-paused)]">🔐 Claude Code — approve the plan before it runs</p>
          {coding.map((c) => (
            <div key={c.id} className="rounded-[var(--radius)] border border-[var(--color-status-paused)] bg-[var(--color-card)] p-3">
              <p className="text-sm font-medium">{c.task}</p>
              <pre className="mt-1 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-md bg-[var(--color-background)] p-2 text-xs text-[var(--color-muted-foreground)]">{c.plan}</pre>
              <div className="mt-2 flex gap-2">
                <button onClick={() => decideCoding(c.id, "allow")} className="rounded-md bg-[var(--color-status-completed)] px-3 py-1 text-xs font-medium text-[var(--color-primary-foreground)]">✓ Allow &amp; run</button>
                <button onClick={() => decideCoding(c.id, "deny")} className="rounded-md border border-[var(--color-status-failed)] px-3 py-1 text-xs text-[var(--color-status-failed)]">✕ Deny</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {approvals.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--color-status-paused)]">⏸ Awaiting your approval</p>
          {approvals.map((a) => (
            <div key={a.id} className="flex items-center gap-3 rounded-[var(--radius)] border border-[var(--color-status-paused)] bg-[var(--color-card)] p-3">
              <span className="min-w-0 flex-1 truncate text-sm">{a.summary}</span>
              <Link href={`/runs/${a.run_id}`} className="shrink-0 text-xs text-[var(--color-muted-foreground)] hover:underline">view run →</Link>
              <button onClick={() => decide(a, "approve")} className="shrink-0 rounded-md bg-[var(--color-status-completed)] px-3 py-1 text-xs font-medium text-[var(--color-primary-foreground)]">✓ Approve</button>
              <button onClick={() => decide(a, "reject")} className="shrink-0 rounded-md border border-[var(--color-status-failed)] px-3 py-1 text-xs text-[var(--color-status-failed)]">✕ Reject</button>
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
