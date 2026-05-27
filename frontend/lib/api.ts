// Typed API client. Phase 8 generates these types from the backend OpenAPI;
// for the thin slice they're hand-written and kept in sync with api/schemas.py.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  model_provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  tool_ids: string[];
  memory_policy: Record<string, unknown>;
  guardrails: Record<string, unknown>;
  harness: Record<string, unknown>;
  created_at: string;
}

export interface Run {
  id: string;
  workflow_id: string;
  workflow_version: number;
  status: string;
  trigger_type: string;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: string;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface Step {
  id: string;
  node_id: string;
  agent_id: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  cost_usd: string;
  tokens_in: number;
  tokens_out: number;
  error: string | null;
}

export interface Message {
  id: string;
  step_id: string | null;
  agent_id: string | null;
  role: string;
  content: string;
  cost_usd: string;
  tokens_in: number;
  tokens_out: number;
  ts: string;
}

export interface RunDetail extends Run {
  steps: Step[];
  messages: Message[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  listAgents: () => req<Agent[]>("/agents"),
  getAgent: (id: string) => req<Agent>(`/agents/${id}`),
  createAgent: (body: Partial<Agent>) =>
    req<Agent>("/agents", { method: "POST", body: JSON.stringify(body) }),
  deleteAgent: (id: string) =>
    req<void>(`/agents/${id}`, { method: "DELETE" }),
  quickRun: (agentId: string, input: string, maxCostUsd?: string) =>
    req<Run>(`/runs/agent/${agentId}`, {
      method: "POST",
      body: JSON.stringify({ input, max_cost_usd: maxCostUsd ?? null }),
    }),
  listRuns: () => req<Run[]>("/runs"),
  getRun: (id: string) => req<RunDetail>(`/runs/${id}`),
};
