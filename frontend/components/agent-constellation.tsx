"use client";

import { useEffect, useState } from "react";
import { api, type Agent, type RunDetail } from "@/lib/api";

type Live = {
  task: string | null;
  status: string;
  activeNow: Set<string>;
  done: Set<string>;
  coordinatorBusy: boolean;
  recalled: number;       // long-term memories recalled this run
  tools: string[];        // real tool / MCP calls (names), latest last
};

// Coordination tools are the delegation mechanism (shown as lit agents), not
// "tool calls" worth surfacing separately.
const COORDINATION = new Set(["list_agents", "create_agent", "send_message_to_agent", "run_debate"]);

/* The single live view of Jarvis at work: hub + specialists, the ones being
   invoked light up with animated message-flow lines, and a status strip shows
   memory recalls and real tool/MCP calls. */
export function AgentConstellation() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [live, setLive] = useState<Live | null>(null);

  useEffect(() => { api.listAgents().then(setAgents).catch(() => {}); }, []);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const runs = await api.listRuns();
        const act = runs.find((r) => r.status === "running" || r.status === "pending") ?? runs[0];
        const d: RunDetail | null = act ? await api.getRun(act.id) : null;
        if (!alive) return;
        if (!d) { setLive(null); return; }
        const activeNow = new Set<string>(), done = new Set<string>();
        for (const c of d.children ?? []) {
          if (!c.agent_name) continue;
          (c.status === "running" || c.status === "pending" ? activeNow : c.status === "completed" ? done : new Set()).add(c.agent_name);
        }
        const msgs = d.messages ?? [];
        const recalled = msgs.filter((m) => m.role === "system" && m.content.startsWith("🧠")).length;
        const tools = msgs
          .filter((m) => m.role === "tool")
          .map((m) => (Array.isArray(m.tool_calls) ? (m.tool_calls[0] as { name?: string })?.name : undefined))
          .filter((n): n is string => !!n && !COORDINATION.has(n));
        const running = d.status === "running" || d.status === "pending";
        setLive({ task: d.task, status: d.status, activeNow, done, coordinatorBusy: running && activeNow.size === 0, recalled, tools });
      } catch { /* ignore */ }
    };
    tick();
    const t = setInterval(tick, 1200);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const ring = agents.filter((a) => a.name !== "Jarvis" && a.name !== "Orchestrator");
  const W = 680, H = 380, cx = W / 2, cy = H / 2, R = 142;
  const hubLive = (live?.activeNow.size ?? 0) > 0 || live?.coordinatorBusy;
  const state = (n: string): "active" | "done" | "idle" =>
    live?.activeNow.has(n) ? "active" : live?.done.has(n) ? "done" : "idle";
  const COLOR = { active: "var(--color-status-running)", done: "var(--color-status-completed)", idle: "var(--color-muted-foreground)" };

  const pts = ring.map((a, i) => {
    const ang = (i / Math.max(ring.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return { agent: a, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang), st: state(a.name) };
  });

  const lastTool = live?.tools.at(-1);
  const caption = live
    ? live.coordinatorBusy ? "Jarvis is planning…"
      : live.activeNow.size > 0 ? `Working with ${live.activeNow.size} agent${live.activeNow.size > 1 ? "s" : ""}…`
      : live.status === "completed" ? "Task complete" : live.status
    : ring.length === 0 ? "No specialists yet — ask Jarvis to build a team." : "Idle — ready for a task";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-h-0 w-full flex-1">
        <defs>
          <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="var(--color-border)" strokeWidth={1} opacity={0.3} strokeDasharray="2 6" />
        {pts.map((p) => {
          const on = p.st === "active";
          return (
            <line key={`l-${p.agent.id}`} x1={cx} y1={cy} x2={p.x} y2={p.y}
              stroke={on ? "var(--color-status-running)" : p.st === "done" ? "var(--color-status-completed)" : "var(--color-border)"}
              strokeWidth={on ? 2 : 1} className={on ? "hud-flow" : ""} opacity={on ? 0.9 : p.st === "done" ? 0.45 : 0.22} />
          );
        })}
        {pts.map((p) => {
          const role = (p.agent.role || "").split("—")[0].split(" ")[0];
          return (
            <g key={p.agent.id} className={p.st === "active" ? "hud-pulse" : ""}>
              {p.st === "active" && <circle cx={p.x} cy={p.y} r={20} fill="url(#hubGlow)" />}
              <circle cx={p.x} cy={p.y} r={p.st === "active" ? 11 : 7}
                fill={p.st === "active" ? "var(--color-status-running)" : "var(--color-card)"} stroke={COLOR[p.st]} strokeWidth={2} />
              {p.st === "done" && <text x={p.x} y={p.y + 3.5} textAnchor="middle" fontSize={9} fill="var(--color-primary-foreground)">✓</text>}
              <text x={p.x} y={p.y + 26} textAnchor="middle" className="font-mono" fontSize={9.5}
                fill={p.st === "idle" ? "var(--color-muted-foreground)" : "var(--color-foreground)"}>{p.agent.name.split(" ")[0]}</text>
              <text x={p.x} y={p.y + 37} textAnchor="middle" fontSize={7.5} fill="var(--color-muted-foreground)">{role}</text>
            </g>
          );
        })}
        {hubLive && <circle cx={cx} cy={cy} r={48} fill="url(#hubGlow)" />}
        <circle cx={cx} cy={cy} r={30} fill="var(--color-card)" stroke="var(--color-primary)" strokeWidth={2} className={hubLive ? "hud-pulse" : ""} />
        <circle cx={cx} cy={cy} r={38} fill="none" stroke="var(--color-primary)" strokeWidth={1} opacity={0.3} />
        <text x={cx} y={cy + 4} textAnchor="middle" className="font-mono text-glow" fontSize={13} fill="var(--color-primary)" fontWeight={600}>JARVIS</text>
      </svg>

      {/* status strip: mode + memory recalls + latest real tool/MCP call */}
      <div className="shrink-0 space-y-1 px-1 pt-1 text-xs">
        <p className="truncate text-[var(--color-muted-foreground)]">
          <span className={hubLive ? "text-[var(--color-status-running)]" : ""}>{caption}</span>
          {live?.task ? <span className="text-[var(--color-foreground)]"> · {live.task.slice(0, 60)}</span> : null}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          {!!live?.recalled && (
            <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px]">🧠 recalled {live.recalled}</span>
          )}
          {lastTool && (
            <span className="rounded-full border px-2 py-0.5 font-mono text-[10px]"
              style={{ borderColor: "var(--color-status-paused)", color: "var(--color-status-paused)" }}>
              {lastTool.startsWith("mcp__") ? "🔌" : "🔧"} {lastTool}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
