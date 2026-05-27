"use client";

import { useEffect, useState } from "react";
import { api, type Agent, type RunDetail } from "@/lib/api";

type Live = {
  task: string | null;
  status: string;
  activeNow: Set<string>;   // agents currently being invoked
  done: Set<string>;        // agents that finished this run
  coordinatorBusy: boolean; // hub is thinking/delegating
};

/* Live "constellation" of the team: Jarvis at the hub, specialists in a ring.
   While a task runs, the agents Jarvis is invoking right now light up and
   message-flow lines animate from the hub to them. */
export function AgentConstellation({ runId }: { runId?: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [live, setLive] = useState<Live | null>(null);

  useEffect(() => { api.listAgents().then(setAgents).catch(() => {}); }, []);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        let detail: RunDetail | null = null;
        if (runId) {
          detail = await api.getRun(runId);
        } else {
          const runs = await api.listRuns();
          const act = runs.find((r) => r.status === "running" || r.status === "pending");
          detail = act ? await api.getRun(act.id) : null;
        }
        if (!alive) return;
        if (!detail) { setLive(null); return; }
        const activeNow = new Set<string>();
        const done = new Set<string>();
        for (const c of detail.children ?? []) {
          if (!c.agent_name) continue;
          if (c.status === "running" || c.status === "pending") activeNow.add(c.agent_name);
          else if (c.status === "completed") done.add(c.agent_name);
        }
        const running = detail.status === "running" || detail.status === "pending";
        setLive({
          task: detail.task,
          status: detail.status,
          activeNow,
          done,
          coordinatorBusy: running && activeNow.size === 0,
        });
      } catch { /* ignore */ }
    };
    tick();
    const t = setInterval(tick, 1200);
    return () => { alive = false; clearInterval(t); };
  }, [runId]);

  const ring = agents.filter((a) => a.name !== "Jarvis" && a.name !== "Orchestrator");
  const W = 680, H = 440, cx = W / 2, cy = H / 2 - 8, R = 150;
  const hubLive = (live?.activeNow.size ?? 0) > 0 || live?.coordinatorBusy;

  const state = (name: string): "active" | "done" | "idle" =>
    live?.activeNow.has(name) ? "active" : live?.done.has(name) ? "done" : "idle";

  const COLOR = {
    active: "var(--color-status-running)",
    done: "var(--color-status-completed)",
    idle: "var(--color-muted-foreground)",
  };

  const pts = ring.map((a, i) => {
    const ang = (i / Math.max(ring.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return { agent: a, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang), st: state(a.name) };
  });

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
      <defs>
        <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* guide ring */}
      <circle cx={cx} cy={cy} r={R} fill="none" stroke="var(--color-border)" strokeWidth={1} opacity={0.35} strokeDasharray="2 6" />

      {/* connection lines */}
      {pts.map((p) => {
        const on = p.st === "active";
        return (
          <line key={`l-${p.agent.id}`} x1={cx} y1={cy} x2={p.x} y2={p.y}
            stroke={on ? "var(--color-status-running)" : p.st === "done" ? "var(--color-status-completed)" : "var(--color-border)"}
            strokeWidth={on ? 2 : 1} className={on ? "hud-flow" : ""} opacity={on ? 0.9 : p.st === "done" ? 0.45 : 0.25} />
        );
      })}

      {/* ring agents */}
      {pts.map((p) => {
        const role = (p.agent.role || "").split("—")[0].split(" ")[0];
        return (
          <g key={p.agent.id} className={p.st === "active" ? "hud-pulse" : ""}>
            {p.st === "active" && <circle cx={p.x} cy={p.y} r={20} fill="url(#hubGlow)" />}
            <circle cx={p.x} cy={p.y} r={p.st === "active" ? 11 : 7}
              fill={p.st === "active" ? "var(--color-status-running)" : "var(--color-card)"}
              stroke={COLOR[p.st]} strokeWidth={2} />
            {p.st === "done" && <text x={p.x} y={p.y + 3.5} textAnchor="middle" fontSize={9} fill="var(--color-primary-foreground)">✓</text>}
            <text x={p.x} y={p.y + 26} textAnchor="middle" className="font-mono" fontSize={9.5}
              fill={p.st === "idle" ? "var(--color-muted-foreground)" : "var(--color-foreground)"}>
              {p.agent.name.split(" ")[0]}
            </text>
            <text x={p.x} y={p.y + 37} textAnchor="middle" fontSize={7.5} fill="var(--color-muted-foreground)">{role}</text>
          </g>
        );
      })}

      {/* central hub */}
      {hubLive && <circle cx={cx} cy={cy} r={48} fill="url(#hubGlow)" />}
      <circle cx={cx} cy={cy} r={30} fill="var(--color-card)" stroke="var(--color-primary)" strokeWidth={2} className={hubLive ? "hud-pulse" : ""} />
      <circle cx={cx} cy={cy} r={38} fill="none" stroke="var(--color-primary)" strokeWidth={1} opacity={0.3} />
      <text x={cx} y={cy + 4} textAnchor="middle" className="font-mono text-glow" fontSize={13} fill="var(--color-primary)" fontWeight={600}>JARVIS</text>

      {/* status caption */}
      <text x={cx} y={H - 26} textAnchor="middle" fontSize={11} fill="var(--color-muted-foreground)">
        {live
          ? live.coordinatorBusy ? "Jarvis is planning…"
            : live.activeNow.size > 0 ? `Delegating to ${live.activeNow.size} agent${live.activeNow.size > 1 ? "s" : ""}…`
            : live.status === "completed" ? "Task complete" : live.status
          : ring.length === 0 ? "No specialists yet — ask Jarvis to build a team." : "Idle — ready for a task"}
      </text>
      {live?.task && (
        <text x={cx} y={H - 10} textAnchor="middle" fontSize={9.5} fill="var(--color-foreground)" opacity={0.7}>
          {live.task.length > 80 ? live.task.slice(0, 79) + "…" : live.task}
        </text>
      )}
    </svg>
  );
}
