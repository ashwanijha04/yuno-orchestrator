// Typed API client. Phase 8 generates these types from the backend OpenAPI;
// for the thin slice they're hand-written and kept in sync with api/schemas.py.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Persona {
  traits?: string[];
  tone?: string;
  values?: string[];
  speaking_style?: string;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  soul_md: string | null;
  persona: Persona;
  model_provider: string;
  model_name: string;
  task_type: string;
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
  workflow_name: string | null;
  task: string | null;
  agent_names: string[];
  quality: string | null; // latest judge score 0..1
  conversational: boolean; // plain chat reply — not a mission/task
}

export interface Step {
  id: string;
  node_id: string;
  agent_id: string | null;
  agent_name: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  cost_usd: string;
  tokens_in: number;
  tokens_out: number;
  error: string | null;
  output: string | null;
}

export interface Message {
  id: string;
  step_id: string | null;
  agent_id: string | null;
  recipient_agent_id: string | null;
  role: string;
  content: string;
  tool_calls: unknown;
  cost_usd: string;
  tokens_in: number;
  tokens_out: number;
  ts: string;
}

export interface ChildRun {
  id: string;
  agent_name: string | null;
  task: string | null;
  status: string;
  output: string | null;
  total_cost_usd: string;
}

export interface Evaluation {
  id: string;
  source: string; // judge | human
  overall: string | null;
  scores: Record<string, number>;
  verdict: string | null;
  rationale: string | null;
  created_at: string;
}

export interface RunDetail extends Run {
  steps: Step[];
  messages: Message[];
  children: ChildRun[];
  evaluations: Evaluation[];
}

export interface Approval {
  id: string;
  run_id: string;
  node_id: string;
  summary: string;
  status: string;
  note: string | null;
}

export interface Tool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  requires_approval: boolean;
}

export interface Stats {
  agents: number;
  workflows: number;
  channels: number;
  runs_total: number;
  runs_today: number;
  running: number;
  completed: number;
  failed: number;
  total_cost_usd: string;
  total_tokens: number;
}

export interface Channel {
  id: string;
  type: string;
  name: string;
  status: string;
  created_at: string;
}

export interface Binding {
  id: string;
  agent_id: string | null;
  channel_id: string;
  workflow_id: string | null;
  external_id: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  current_version: number;
  created_at: string;
}

export interface WorkflowGraph {
  version?: string;
  name?: string;
  entry_node: string;
  variables: Record<string, unknown>;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  type: string; // agent | tool | condition | human | channel_out
  agent_id?: string;
  tool?: string; // for tool nodes: built-in or mcp__server__tool
  output_key?: string;
  input_mapping?: Record<string, string>;
  on_error?: string; // node id to route to if this node fails
  position?: { x: number; y: number };
  label?: string;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  condition?: string;
  priority?: number;
}

export interface WorkflowDetail extends Workflow {
  graph: WorkflowGraph;
}

export interface ValidationIssue {
  code: string;
  message: string;
  node_id: string | null;
  edge_id: string | null;
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
  updateAgent: (id: string, body: Partial<Agent>) =>
    req<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteAgent: (id: string) =>
    req<void>(`/agents/${id}`, { method: "DELETE" }),
  quickRun: (agentId: string, input: string, maxCostUsd?: string) =>
    req<Run>(`/runs/agent/${agentId}`, {
      method: "POST",
      body: JSON.stringify({ input, max_cost_usd: maxCostUsd ?? null }),
    }),
  stats: () => req<Stats>("/stats"),
  listRuns: () => req<Run[]>("/runs"),
  getRun: (id: string) => req<RunDetail>(`/runs/${id}`),
  deleteRun: (id: string) => req<void>(`/runs/${id}`, { method: "DELETE" }),
  cancelRun: (id: string) => req<Run>(`/runs/${id}/cancel`, { method: "POST" }),
  evaluateRun: (id: string) => req<Evaluation>(`/runs/${id}/evaluate`, { method: "POST" }),
  followupRun: (id: string, message: string) =>
    req<Run>(`/runs/${id}/followup`, { method: "POST", body: JSON.stringify({ message }) }),
  feedbackRun: (id: string, positive: boolean, note?: string) =>
    req<Evaluation>(`/runs/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ positive, note: note ?? null }),
    }),
  codingBridgeStatus: () => req<{ connected: boolean }>("/coding/status"),
  listApprovals: () => req<Approval[]>("/approvals"),
  decideApproval: (id: string, decision: "approve" | "reject", note?: string) =>
    req<Approval>(`/approvals/${id}`, {
      method: "POST",
      body: JSON.stringify({ decision, note: note ?? null }),
    }),
  clearFinishedRuns: () => req<{ deleted: number }>("/runs/clear", { method: "POST" }),
  orchestrate: (task: string, agentIds: string[], mode: "pipeline" | "auto") =>
    req<Run>("/orchestrate", {
      method: "POST",
      body: JSON.stringify({ task, agent_ids: agentIds, mode }),
    }),

  chat: (agentId: string, message: string, conversationId?: string) =>
    req<{ conversation_id: string; reply: string; run_id: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, message, conversation_id: conversationId ?? null }),
    }),
  chatHistory: (conversationId: string) =>
    req<{ role: string; content: string }[]>(`/chat/${conversationId}`),

  listTools: () => req<Tool[]>("/tools"),

  listWorkflows: () => req<Workflow[]>("/workflows"),
  getWorkflow: (id: string) => req<WorkflowDetail>(`/workflows/${id}`),
  createWorkflow: (body: { name: string; description?: string; graph: WorkflowGraph }) =>
    req<WorkflowDetail>("/workflows", { method: "POST", body: JSON.stringify(body) }),
  saveWorkflowVersion: (id: string, graph: WorkflowGraph) =>
    req<WorkflowDetail>(`/workflows/${id}/versions`, { method: "POST", body: JSON.stringify({ graph }) }),
  deleteWorkflow: (id: string) => req<void>(`/workflows/${id}`, { method: "DELETE" }),
  duplicateWorkflow: (id: string) => req<WorkflowDetail>(`/workflows/${id}/duplicate`, { method: "POST" }),
  validateWorkflow: (graph: WorkflowGraph) =>
    req<{ valid: boolean; issues: ValidationIssue[] }>("/workflows/validate", {
      method: "POST",
      body: JSON.stringify({ graph }),
    }),
  runWorkflow: (id: string, variables: Record<string, unknown>, maxCostUsd?: string) =>
    req<Run>(`/runs/workflow/${id}`, {
      method: "POST",
      body: JSON.stringify({ variables, max_cost_usd: maxCostUsd ?? null }),
    }),

  listChannels: () => req<Channel[]>("/channels"),
  createChannel: (body: { type: string; name: string; config?: Record<string, unknown> }) =>
    req<Channel>("/channels", { method: "POST", body: JSON.stringify(body) }),
  listBindings: (channelId: string) => req<Binding[]>(`/channels/${channelId}/bindings`),
  createBinding: (
    channelId: string,
    body: { agent_id?: string; workflow_id?: string; external_id: string },
  ) => req<Binding>(`/channels/${channelId}/bindings`, { method: "POST", body: JSON.stringify(body) }),
};
