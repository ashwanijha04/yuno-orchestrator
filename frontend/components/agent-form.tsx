"use client";

import { useEffect, useState } from "react";
import { api, type Agent, type Tool } from "@/lib/api";

const FIELD =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm";
const LABEL = "block text-xs font-medium text-[var(--color-muted-foreground)] mb-1";

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {hint && <p className="text-xs text-[var(--color-muted-foreground)]">{hint}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export interface AgentFormValue {
  name: string;
  role: string;
  system_prompt: string;
  soul_md: string;
  persona: { traits: string[]; tone: string; values: string[]; speaking_style: string };
  model_provider: string;
  model_name: string;
  task_type: string;
  temperature: number;
  max_tokens: number;
  tool_ids: string[];
  memory_policy: { strategy: string };
  guardrails: { max_iterations: number; max_cost_per_run_usd: string; max_tokens_per_turn: number };
}

export function emptyAgent(): AgentFormValue {
  return {
    name: "",
    role: "",
    system_prompt: "",
    soul_md: "",
    persona: { traits: [], tone: "", values: [], speaking_style: "" },
    model_provider: "anthropic",
    model_name: "claude-sonnet-4-6",
    task_type: "auto",
    temperature: 0.7,
    max_tokens: 2048,
    tool_ids: [],
    memory_policy: { strategy: "buffer" },
    guardrails: { max_iterations: 8, max_cost_per_run_usd: "1.00", max_tokens_per_turn: 8000 },
  };
}

export function fromAgent(a: Agent): AgentFormValue {
  return {
    name: a.name,
    role: a.role,
    system_prompt: a.system_prompt,
    soul_md: a.soul_md ?? "",
    persona: {
      traits: a.persona?.traits ?? [],
      tone: a.persona?.tone ?? "",
      values: a.persona?.values ?? [],
      speaking_style: a.persona?.speaking_style ?? "",
    },
    model_provider: a.model_provider,
    model_name: a.model_name,
    task_type: a.task_type ?? "auto",
    temperature: a.temperature,
    max_tokens: a.max_tokens,
    tool_ids: a.tool_ids ?? [],
    memory_policy: { strategy: (a.memory_policy?.strategy as string) ?? "buffer" },
    guardrails: {
      max_iterations: (a.guardrails?.max_iterations as number) ?? 8,
      max_cost_per_run_usd: String(a.guardrails?.max_cost_per_run_usd ?? "1.00"),
      max_tokens_per_turn: (a.guardrails?.max_tokens_per_turn as number) ?? 8000,
    },
  };
}

export function AgentForm({
  initial,
  isNew,
  onSubmit,
  submitting,
  error,
}: {
  initial: AgentFormValue;
  isNew: boolean;
  onSubmit: (v: AgentFormValue) => void;
  submitting: boolean;
  error: string | null;
}) {
  const [v, setV] = useState<AgentFormValue>(initial);
  const [tools, setTools] = useState<Tool[]>([]);
  useEffect(() => setV(initial), [initial]);
  useEffect(() => { api.listTools().then(setTools).catch(() => {}); }, []);

  const set = (patch: Partial<AgentFormValue>) => setV({ ...v, ...patch });
  const setPersona = (patch: Partial<AgentFormValue["persona"]>) => setV({ ...v, persona: { ...v.persona, ...patch } });
  const setGuard = (patch: Partial<AgentFormValue["guardrails"]>) => setV({ ...v, guardrails: { ...v.guardrails, ...patch } });

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(v); }}
      className="grid grid-cols-1 gap-5 lg:grid-cols-2"
    >
      {error && (
        <div className="lg:col-span-2 rounded-md border border-[var(--color-status-failed)] p-3 text-sm text-[var(--color-status-failed)]">
          {error}
        </div>
      )}

      <Section title="Identity" hint="Who the agent is and what it does.">
        <div>
          <label className={LABEL}>Name</label>
          <input className={FIELD} value={v.name} required disabled={!isNew}
            onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div>
          <label className={LABEL}>Role</label>
          <input className={FIELD} value={v.role} required onChange={(e) => set({ role: e.target.value })} />
        </div>
        <div>
          <label className={LABEL}>Instructions (system prompt)</label>
          <textarea className={FIELD} rows={4} value={v.system_prompt} required
            onChange={(e) => set({ system_prompt: e.target.value })} />
        </div>
      </Section>

      <Section title="Soul & personality" hint="SOUL.md identity + structured persona, composed into every prompt.">
        <div>
          <label className={LABEL}>SOUL.md</label>
          <textarea className={`${FIELD} font-mono`} rows={5} placeholder="You are Remy, a relentless fact-finder…"
            value={v.soul_md} onChange={(e) => set({ soul_md: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL}>Traits (comma-separated)</label>
            <input className={FIELD} value={v.persona.traits.join(", ")}
              onChange={(e) => setPersona({ traits: csv(e.target.value) })} />
          </div>
          <div>
            <label className={LABEL}>Values (comma-separated)</label>
            <input className={FIELD} value={v.persona.values.join(", ")}
              onChange={(e) => setPersona({ values: csv(e.target.value) })} />
          </div>
          <div>
            <label className={LABEL}>Tone</label>
            <input className={FIELD} value={v.persona.tone} onChange={(e) => setPersona({ tone: e.target.value })} />
          </div>
          <div>
            <label className={LABEL}>Speaking style</label>
            <input className={FIELD} value={v.persona.speaking_style}
              onChange={(e) => setPersona({ speaking_style: e.target.value })} />
          </div>
        </div>
      </Section>

      <Section title="Model" hint="Provider, model, and sampling.">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL}>Provider</label>
            <select className={FIELD} value={v.model_provider} onChange={(e) => set({ model_provider: e.target.value })}>
              <option value="anthropic">anthropic</option>
              <option value="openai">openai</option>
            </select>
          </div>
          <div>
            <label className={LABEL}>Model</label>
            <input className={FIELD} value={v.model_name} onChange={(e) => set({ model_name: e.target.value })} />
          </div>
          <div>
            <label className={LABEL}>Temperature: {v.temperature}</label>
            <input type="range" min={0} max={1} step={0.1} className="w-full" value={v.temperature}
              onChange={(e) => set({ temperature: parseFloat(e.target.value) })} />
          </div>
          <div>
            <label className={LABEL}>Max tokens</label>
            <input type="number" className={FIELD} value={v.max_tokens}
              onChange={(e) => set({ max_tokens: parseInt(e.target.value || "0") })} />
          </div>
          <div className="col-span-2">
            <label className={LABEL}>Routing (task type)</label>
            <select className={FIELD} value={v.task_type} onChange={(e) => set({ task_type: e.target.value })}>
              <option value="auto">auto — use the model above, fall back if it fails</option>
              <option value="coding">coding — route to Anthropic (Sonnet), fallback OpenAI</option>
              <option value="normal">normal — route to OpenAI, fallback Anthropic</option>
              <option value="conversation">conversation — route to Gemini, fallback OpenAI/Anthropic</option>
            </select>
          </div>
        </div>
      </Section>

      <Section title="Tools" hint="Capabilities this agent may call.">
        <div className="space-y-2">
          {tools.map((t) => (
            <label key={t.name} className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={v.tool_ids.includes(t.name)} className="mt-1"
                onChange={(e) => set({ tool_ids: e.target.checked ? [...v.tool_ids, t.name] : v.tool_ids.filter((x) => x !== t.name) })} />
              <span>
                <span className="font-mono">{t.name}</span>
                <span className="text-[var(--color-muted-foreground)]"> — {t.description}</span>
              </span>
            </label>
          ))}
        </div>
      </Section>

      <Section title="Memory" hint="How the agent remembers across turns and runs.">
        <select className={FIELD} value={v.memory_policy.strategy} onChange={(e) => set({ memory_policy: { strategy: e.target.value } })}>
          <option value="buffer">buffer — last N messages this run</option>
          <option value="summary">summary — rolling summary</option>
          <option value="channel_scoped">channel_scoped — per user, across runs</option>
          <option value="external">external — extremis (episodic + procedural)</option>
        </select>
      </Section>

      <Section title="Guardrails" hint="Limits enforced at the reasoning chokepoint.">
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className={LABEL}>Max iterations</label>
            <input type="number" className={FIELD} value={v.guardrails.max_iterations}
              onChange={(e) => setGuard({ max_iterations: parseInt(e.target.value || "0") })} />
          </div>
          <div>
            <label className={LABEL}>Max $/run</label>
            <input className={FIELD} value={v.guardrails.max_cost_per_run_usd}
              onChange={(e) => setGuard({ max_cost_per_run_usd: e.target.value })} />
          </div>
          <div>
            <label className={LABEL}>Max tokens/turn</label>
            <input type="number" className={FIELD} value={v.guardrails.max_tokens_per_turn}
              onChange={(e) => setGuard({ max_tokens_per_turn: parseInt(e.target.value || "0") })} />
          </div>
        </div>
      </Section>

      <div className="lg:col-span-2">
        <button type="submit" disabled={submitting}
          className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-[var(--color-primary-foreground)] disabled:opacity-50">
          {submitting ? "Saving…" : isNew ? "Create agent" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
