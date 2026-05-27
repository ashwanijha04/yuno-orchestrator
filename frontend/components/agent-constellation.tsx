"use client";

import { useEffect, useState } from "react";
import { api, type Agent, type Run } from "@/lib/api";

/* A live "constellation" of the agent team: Jarvis at the hub, specialists in a
   ring. When a task is running, the involved agents light up and message-flow
   lines animate from the hub — the agents-talking-to-agents moment, made visual. */
export function AgentConstellation() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [active, setActive] = useState<Set<string>>(new Set());

  useEffect(() => {
    const load = async () => {
      const [a, runs] = await Promise.all([
        api.listAgents().catch(() => [] as Agent[]),
        api.listRuns().catch(() => [] as Run[]),
      ]);
      setAgents(a);
      const live = new Set<string>();
      runs.filter((r) => r.status === "running" || r.status === "pending")
        .forEach((r) => (r.agent_names ?? []).forEach((n) => live.add(n)));
      setActive(live);
    };
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, []);

  // Jarvis is the hub; everyone else rings around it.
  const ring = agents.filter((a) => a.name !== "Jarvis");
  const W = 640, H = 380, cx = W / 2, cy = H / 2, R = 132;
  const anyActive = active.size > 0;

  const pts = ring.map((a, i) => {
    const ang = (i / Math.max(ring.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return { agent: a, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang), on: active.has(a.name) };
  });

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
      {/* flow lines from the hub to active agents */}
      {pts.map((p) =>
        p.on ? (
          <line key={`l-${p.agent.id}`} x1={cx} y1={cy} x2={p.x} y2={p.y}
            stroke="var(--color-status-running)" strokeWidth={1.5} className="hud-flow" opacity={0.8} />
        ) : (
          <line key={`l-${p.agent.id}`} x1={cx} y1={cy} x2={p.x} y2={p.y}
            stroke="var(--color-border)" strokeWidth={1} opacity={0.4} />
        ),
      )}

      {/* ring agents */}
      {pts.map((p) => (
        <g key={p.agent.id} className={p.on ? "hud-pulse" : ""}>
          <circle cx={p.x} cy={p.y} r={p.on ? 9 : 6}
            fill={p.on ? "var(--color-status-running)" : "var(--color-muted)"}
            stroke={p.on ? "var(--color-status-running)" : "var(--color-border)"} strokeWidth={1.5} />
          <text x={p.x} y={p.y + 22} textAnchor="middle"
            className="font-mono" fontSize={9}
            fill={p.on ? "var(--color-foreground)" : "var(--color-muted-foreground)"}>
            {p.agent.name.length > 16 ? p.agent.name.slice(0, 15) + "…" : p.agent.name}
          </text>
        </g>
      ))}

      {/* central Jarvis hub */}
      <circle cx={cx} cy={cy} r={26} fill="var(--color-card)"
        stroke="var(--color-primary)" strokeWidth={2} className={anyActive ? "hud-pulse" : ""} />
      <circle cx={cx} cy={cy} r={34} fill="none" stroke="var(--color-primary)" strokeWidth={1} opacity={0.35} />
      <text x={cx} y={cy + 4} textAnchor="middle" className="font-mono text-glow"
        fontSize={12} fill="var(--color-primary)" fontWeight={600}>JARVIS</text>

      {ring.length === 0 && (
        <text x={cx} y={cy + 60} textAnchor="middle" fontSize={11} fill="var(--color-muted-foreground)">
          No specialists yet — ask Jarvis to build a team.
        </text>
      )}
    </svg>
  );
}
