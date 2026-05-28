"use client";

import { useEffect, useRef, useState } from "react";
import { api, type RunDetail } from "@/lib/api";
import { agentColor } from "@/components/agent-comms";

const STATUS_COLOR: Record<string, string> = {
  running: "var(--color-status-running)", completed: "var(--color-status-completed)",
  failed: "var(--color-status-failed)", pending: "var(--color-status-pending)",
  paused: "var(--color-status-paused)", cancelled: "var(--color-muted-foreground)",
};

type Ev = { key: string; icon: string; text: string; who?: string; tone?: string };

function eventsOf(run: RunDetail): Ev[] {
  const evs: Ev[] = [];
  (run.messages ?? []).forEach((m, i) => {
    if (m.role === "system" && m.content.startsWith("🧠"))
      evs.push({ key: "m" + i, icon: "🧠", text: m.content.replace(/^🧠\s*/, "") });
    if (m.role === "tool") {
      const tc = Array.isArray(m.tool_calls) ? (m.tool_calls[0] as { name?: string })?.name : undefined;
      const mcp = (tc ?? "").startsWith("mcp__");
      evs.push({ key: "t" + i, icon: mcp ? "🔌" : "🔧", text: `${tc ?? "tool"} → ${m.content.slice(0, 60)}` });
    }
  });
  (run.children ?? []).forEach((c, i) =>
    evs.push({ key: "c" + i, icon: "🤝", who: c.agent_name ?? "agent", text: c.task ?? "", tone: c.status }));
  return evs;
}

/* The right-hand Jarvis panel's feed: what Jarvis is doing right now — tool/MCP
   calls, delegations, debate turns, memory recalls — for the active (or latest) run. */
export function LiveActivity() {
  const [run, setRun] = useState<RunDetail | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const runs = await api.listRuns();
        const target = runs.find((r) => r.status === "running" || r.status === "pending") ?? runs[0];
        const detail = target ? await api.getRun(target.id) : null;
        if (alive) setRun(detail);
      } catch { /* ignore */ }
    };
    tick();
    const t = setInterval(tick, 1300);
    return () => { alive = false; clearInterval(t); };
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [run]);

  const running = run?.status === "running" || run?.status === "pending";
  const evs = run ? eventsOf(run) : [];

  return (
    <div className="flex h-full min-h-0 flex-col rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3">
      <p className="mb-2 flex shrink-0 items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">
        {running && <span className="h-1.5 w-1.5 rounded-full hud-pulse" style={{ background: "var(--color-status-running)" }} />}
        Live Activity {run?.task && <span className="truncate normal-case text-[var(--color-foreground)]">· {run.task.slice(0, 40)}</span>}
      </p>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {!run && <p className="text-sm text-[var(--color-muted-foreground)]">Idle — ask Jarvis to do something.</p>}
        {run && evs.length === 0 && (
          <p className="text-sm text-[var(--color-status-running)] hud-pulse">{running ? "Jarvis is thinking…" : "Answered directly — no tool calls."}</p>
        )}
        {evs.map((e) => (
          <div key={e.key} className="flex items-start gap-2 text-xs">
            <span className="shrink-0">{e.icon}</span>
            {e.who && <span className="shrink-0 font-medium" style={{ color: agentColor(e.who) }}>{e.who}</span>}
            <span className="min-w-0 flex-1 break-words text-[var(--color-muted-foreground)]">{e.text}</span>
            {e.tone && <span className="shrink-0" style={{ color: STATUS_COLOR[e.tone] }}>•</span>}
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
