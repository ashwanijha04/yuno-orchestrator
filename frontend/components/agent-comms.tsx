"use client";

import { useState } from "react";
import { type ChildRun, type RunDetail } from "@/lib/api";
import { Markdown } from "@/components/markdown";

/* Deterministic colour + initials per agent, so each speaker is recognisable. */
function hue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}
export function agentColor(name: string): string {
  if (name === "Jarvis" || name === "Orchestrator") return "var(--color-primary)";
  return `oklch(0.72 0.13 ${hue(name)})`;
}
function initials(name: string): string {
  const w = name.replace(/^(the|a) /i, "").split(/\s+/).filter(Boolean);
  return ((w[0]?.[0] ?? "") + (w[1]?.[0] ?? "")).toUpperCase() || name.slice(0, 2).toUpperCase();
}

function Avatar({ name, size = 26 }: { name: string; size?: number }) {
  const c = agentColor(name);
  return (
    <span className="flex shrink-0 items-center justify-center rounded-full font-mono font-semibold"
      style={{ width: size, height: size, fontSize: size * 0.38, background: `color-mix(in oklch, ${c} 22%, transparent)`, color: c, border: `1px solid ${c}` }}>
      {initials(name)}
    </span>
  );
}

function Bubble({ from, to, body, kind, status }: {
  from: string; to?: string; body: string | null; kind: "ask" | "reply"; status?: string;
}) {
  const [open, setOpen] = useState(false);
  const c = agentColor(from);
  const long = (body?.length ?? 0) > 320;
  const shown = body && !open && long ? body.slice(0, 320) + "…" : body;
  const pending = !body && (status === "running" || status === "pending");
  return (
    <div className="flex gap-2.5">
      <Avatar name={from} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-xs">
          <span className="font-medium" style={{ color: c }}>{from}</span>
          {to && (
            <>
              <span className="text-[var(--color-muted-foreground)]">→</span>
              <span className="text-[var(--color-muted-foreground)]">{to}</span>
            </>
          )}
          <span className="rounded px-1.5 text-[10px] uppercase tracking-wide text-[var(--color-muted-foreground)]">
            {kind === "ask" ? "delegates" : "replies"}
          </span>
        </div>
        <div className="mt-1 rounded-[var(--radius)] border px-3 py-2 text-sm"
          style={{ borderColor: `color-mix(in oklch, ${c} 35%, var(--color-border))`,
                   background: kind === "ask" ? "var(--color-background)" : "color-mix(in oklch, " + c + " 7%, var(--color-card))" }}>
          {pending ? (
            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--color-status-running)]">
              <span className="hud-pulse">●</span> thinking…
            </span>
          ) : kind === "reply" ? (
            <Markdown>{shown || "(no reply)"}</Markdown>
          ) : (
            <span>{shown}</span>
          )}
          {long && (
            <button onClick={() => setOpen((o) => !o)} className="mt-1 block text-xs text-[var(--color-primary)] hover:underline">
              {open ? "show less" : "show more"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function AgentComms({ run }: { run: RunDetail }) {
  const children: ChildRun[] = run.children ?? [];
  const names = run.agent_names ?? [];
  const coordinator =
    names.find((n) => n === "Jarvis") ?? names.find((n) => n === "Orchestrator") ?? names[0] ?? "Coordinator";

  if (children.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted-foreground)]">
        No inter-agent messages yet. When the coordinator delegates, the conversation appears here.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {children.map((c) => (
        <div key={c.id} className="space-y-2 border-l-2 pl-3"
          style={{ borderColor: `color-mix(in oklch, ${agentColor(c.agent_name ?? coordinator)} 40%, transparent)` }}>
          {/* coordinator delegates a subtask to a specialist */}
          <Bubble from={coordinator} to={c.agent_name ?? "agent"} kind="ask" body={c.task} />
          {/* the specialist answers back */}
          <Bubble from={c.agent_name ?? "agent"} to={coordinator} kind="reply" body={c.output} status={c.status} />
          <a href={`/runs/${c.id}`} className="ml-9 block text-[11px] text-[var(--color-muted-foreground)] hover:underline">
            open {c.agent_name?.split(" ")[0]}&apos;s sub-run →
          </a>
        </div>
      ))}
    </div>
  );
}
