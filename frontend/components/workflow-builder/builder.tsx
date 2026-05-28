"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, type Agent, type Tool, type ValidationIssue, type WorkflowGraph } from "@/lib/api";

const FIELD =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] px-2.5 py-1.5 text-sm";

type AgentNodeData = {
  agentId: string;
  agentName: string;
  role: string;
  outputKey?: string;
  onError?: string;
  isEntry?: boolean;
};
type ToolNodeData = {
  tool: string;
  label: string;
  outputKey?: string;
  inputMapping?: string; // JSON string, e.g. {"expression":"$.variables.expr"}
  onError?: string;
  isEntry?: boolean;
  isTool: true;
};
type EdgeData = { condition?: string; priority?: number };

function ToolNode({ data, selected }: NodeProps) {
  const d = data as ToolNodeData;
  const mcp = d.tool?.startsWith("mcp__");
  return (
    <div className="min-w-44 rounded-[var(--radius)] border bg-[var(--color-card)] px-3 py-2 shadow-md"
      style={{ borderColor: selected ? "var(--color-primary)" : "var(--color-status-paused)" }}>
      <Handle type="target" position={Position.Top} style={{ background: "var(--color-muted-foreground)" }} />
      <div className="flex items-center gap-2">
        {d.isEntry && <span className="rounded bg-[var(--color-primary)] px-1.5 py-0.5 text-[10px] text-[var(--color-primary-foreground)]">ENTRY</span>}
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "var(--color-status-paused)", color: "var(--color-primary-foreground)" }}>
          {mcp ? "MCP" : "TOOL"}
        </span>
      </div>
      <div className="mt-1 break-all font-mono text-xs">{d.tool}</div>
      {d.outputKey && <div className="mt-1 font-mono text-[10px] text-[var(--color-muted-foreground)]">→ {d.outputKey}</div>}
      <Handle type="source" position={Position.Bottom} style={{ background: "var(--color-primary)" }} />
    </div>
  );
}

function AgentNode({ data, selected }: NodeProps) {
  const d = data as AgentNodeData;
  return (
    <div
      className="min-w-44 rounded-[var(--radius)] border bg-[var(--color-card)] px-3 py-2 shadow-md"
      style={{ borderColor: selected ? "var(--color-primary)" : "var(--color-border)" }}
    >
      <Handle type="target" position={Position.Top} style={{ background: "var(--color-muted-foreground)" }} />
      <div className="flex items-center gap-2">
        {d.isEntry && <span className="rounded bg-[var(--color-primary)] px-1.5 py-0.5 text-[10px] text-[var(--color-primary-foreground)]">ENTRY</span>}
        <span className="text-sm font-medium">{d.agentName}</span>
      </div>
      <div className="text-xs text-[var(--color-muted-foreground)]">{d.role}</div>
      {d.outputKey && <div className="mt-1 font-mono text-[10px] text-[var(--color-muted-foreground)]">→ {d.outputKey}</div>}
      <Handle type="source" position={Position.Bottom} style={{ background: "var(--color-primary)" }} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode, tool: ToolNode };

function nodeLabel(n: Node): string {
  const d = n.data as Partial<AgentNodeData & ToolNodeData>;
  return d.agentName || d.label || n.id;
}

export interface BuilderProps {
  workflowId?: string;
  initialName?: string;
  initialDescription?: string;
  initialGraph?: WorkflowGraph;
}

function BuilderInner({ workflowId, initialName, initialDescription, initialGraph }: BuilderProps) {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [name, setName] = useState(initialName ?? "");
  const [description, setDescription] = useState(initialDescription ?? "");
  const [variables, setVariables] = useState<string>(
    initialGraph ? Object.keys(initialGraph.variables ?? {}).join(", ") : "topic",
  );
  const [entryId, setEntryId] = useState<string | null>(initialGraph?.entry_node ?? null);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [counter, setCounter] = useState(1);

  const initialNodes: Node[] = (initialGraph?.nodes ?? []).map((n) => {
    const isEntry = n.id === initialGraph?.entry_node;
    if (n.type === "tool") {
      return {
        id: n.id, type: "tool", position: n.position ?? { x: 80, y: 80 },
        data: { tool: n.tool ?? "", label: n.label ?? n.id, outputKey: n.output_key,
                inputMapping: JSON.stringify(n.input_mapping ?? {}), onError: n.on_error, isEntry, isTool: true } as ToolNodeData,
      } as Node;
    }
    return {
      id: n.id, type: "agent", position: n.position ?? { x: 80, y: 80 },
      data: { agentId: n.agent_id ?? "", agentName: n.label ?? n.id, role: "", outputKey: n.output_key, onError: n.on_error, isEntry },
    } as Node;
  });
  const initialEdges: Edge[] = (initialGraph?.edges ?? []).map((e) => ({
    id: e.id,
    source: e.from,
    target: e.to,
    label: e.condition,
    data: { condition: e.condition, priority: e.priority },
  }));

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initialEdges);
  const [selNode, setSelNode] = useState<string | null>(null);
  const [selEdge, setSelEdge] = useState<string | null>(null);

  useEffect(() => {
    api.listAgents().then(setAgents).catch(() => {});
    api.listTools().then(setTools).catch(() => {});
  }, []);

  const onConnect = useCallback(
    (c: Connection) => setEdges((eds: Edge[]) => addEdge({ ...c, id: `e${Date.now()}`, data: {} }, eds)),
    [setEdges],
  );

  function patchNode(id: string, patch: Partial<AgentNodeData>) {
    setNodes((ns: Node[]) => ns.map((n: Node) => (n.id === id ? { ...n, data: { ...(n.data as AgentNodeData), ...patch } } : n)));
  }
  function patchEdge(id: string, patch: Partial<EdgeData>, label?: string) {
    setEdges((es: Edge[]) =>
      es.map((e: Edge) => (e.id === id ? { ...e, label: label ?? e.label, data: { ...(e.data as EdgeData), ...patch } } : e)),
    );
  }

  function addAgentNode(agent: Agent) {
    const id = `${agent.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 16)}-${counter}`;
    setCounter((c) => c + 1);
    const isFirst = nodes.length === 0;
    const node: Node = {
      id,
      type: "agent",
      position: { x: 120 + Math.random() * 240, y: 80 + nodes.length * 110 },
      data: { agentId: agent.id, agentName: agent.name, role: agent.role, outputKey: id, isEntry: isFirst },
    };
    setNodes((ns: Node[]) => [...ns, node]);
    if (isFirst) setEntryId(id);
  }

  function patchToolNode(id: string, patch: Partial<ToolNodeData>) {
    setNodes((ns: Node[]) => ns.map((n: Node) => (n.id === id ? { ...n, data: { ...(n.data as ToolNodeData), ...patch } } : n)));
  }

  function addToolNode(tool: Tool) {
    const short = tool.name.split("__").pop() ?? tool.name;
    const id = `${short.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 14)}-${counter}`;
    setCounter((c) => c + 1);
    const isFirst = nodes.length === 0;
    // Pre-fill the input mapping with the tool's first input, pointing at a variable.
    const firstArg = Object.keys((tool.input_schema?.properties as Record<string, unknown>) ?? {})[0];
    const im = firstArg ? { [firstArg]: `$.variables.${(variables.split(",")[0] || "input").trim()}` } : {};
    const node: Node = {
      id, type: "tool",
      position: { x: 120 + Math.random() * 240, y: 80 + nodes.length * 110 },
      data: { tool: tool.name, label: short, outputKey: id, inputMapping: JSON.stringify(im), isEntry: isFirst, isTool: true } as ToolNodeData,
    };
    setNodes((ns: Node[]) => [...ns, node]);
    if (isFirst) setEntryId(id);
  }

  function buildGraph(): WorkflowGraph {
    const vars: Record<string, unknown> = {};
    variables.split(",").map((s) => s.trim()).filter(Boolean).forEach((v) => (vars[v] = { type: "string" }));
    return {
      version: "1.0",
      name,
      entry_node: entryId ?? (nodes[0]?.id ?? ""),
      variables: vars,
      nodes: nodes.map((n: Node) => {
        const pos = { x: Math.round(n.position.x), y: Math.round(n.position.y) };
        if (n.type === "tool") {
          const d = n.data as ToolNodeData;
          let im: Record<string, string> = {};
          try { im = JSON.parse(d.inputMapping || "{}"); } catch { im = {}; }
          return { id: n.id, type: "tool", tool: d.tool, output_key: d.outputKey, input_mapping: im, on_error: d.onError || undefined, label: d.label, position: pos };
        }
        const d = n.data as AgentNodeData;
        return { id: n.id, type: "agent", agent_id: d.agentId, output_key: d.outputKey, on_error: d.onError || undefined, label: d.agentName, position: pos };
      }),
      edges: edges.map((e: Edge, i: number) => {
        const d = (e.data as EdgeData) ?? {};
        return { id: e.id, from: e.source, to: e.target, condition: d.condition || undefined, priority: d.priority ?? i + 1 };
      }),
    };
  }

  async function validate() {
    setError(null);
    try {
      const res = await api.validateWorkflow(buildGraph());
      setIssues(res.issues);
    } catch (e) { setError(String(e)); }
  }

  async function save() {
    setBusy(true); setError(null);
    try {
      const graph = buildGraph();
      const res = await api.validateWorkflow(graph);
      const blocking = res.issues.filter((i) => i.code !== "unreachable");
      if (blocking.length) { setIssues(res.issues); setBusy(false); return; }
      if (workflowId) await api.saveWorkflowVersion(workflowId, graph);
      else await api.createWorkflow({ name, description, graph });
      router.push("/workflows");
      router.refresh();
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  function setEntry(id: string) {
    setEntryId(id);
    setNodes((ns: Node[]) => ns.map((n: Node) => ({ ...n, data: { ...(n.data as AgentNodeData), isEntry: n.id === id } })));
  }
  function deleteNode(id: string) {
    setNodes((ns: Node[]) => ns.filter((n: Node) => n.id !== id));
    setEdges((es: Edge[]) => es.filter((e: Edge) => e.source !== id && e.target !== id));
    setSelNode(null);
  }
  function deleteEdge(id: string) {
    setEdges((es: Edge[]) => es.filter((e: Edge) => e.id !== id));
    setSelEdge(null);
  }

  const selectedNode = nodes.find((n: Node) => n.id === selNode);
  const selectedEdge = edges.find((e: Edge) => e.id === selEdge);

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${FIELD} max-w-xs`} placeholder="Workflow name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={`${FIELD} max-w-xs`} placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <input className={`${FIELD} max-w-[12rem]`} placeholder="variables (comma)" value={variables} onChange={(e) => setVariables(e.target.value)} />
        <button onClick={validate} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm">Validate</button>
        <button onClick={save} disabled={busy || !name || nodes.length === 0}
          className="rounded-md bg-[var(--color-primary)] px-3 py-1.5 text-sm text-[var(--color-primary-foreground)] disabled:opacity-50">
          {busy ? "Saving…" : workflowId ? "Save version" : "Create workflow"}
        </button>
      </div>

      {error && <div className="rounded-md border border-[var(--color-status-failed)] p-2 text-sm text-[var(--color-status-failed)]">{error}</div>}
      {issues.length > 0 && (
        <div className="rounded-md border border-[var(--color-status-paused)] p-2 text-xs">
          {issues.map((i, k) => (
            <div key={k} className="text-[var(--color-status-paused)]">⚠ {i.code}: {i.message}</div>
          ))}
        </div>
      )}

      <div className="flex flex-1 gap-3 overflow-hidden">
        <div className="w-56 shrink-0 overflow-auto rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3">
          <p className="mb-2 text-xs font-medium text-[var(--color-muted-foreground)]">Agents — click to add</p>
          <div className="space-y-2">
            {agents.map((a) => (
              <button key={a.id} onClick={() => addAgentNode(a)}
                className="block w-full rounded-md border border-[var(--color-border)] p-2 text-left text-sm hover:border-[var(--color-primary)]">
                <div className="font-medium">{a.name}</div>
                <div className="text-xs text-[var(--color-muted-foreground)]">{a.role}</div>
              </button>
            ))}
          </div>
          <p className="mb-2 mt-4 text-xs font-medium text-[var(--color-muted-foreground)]">Tools &amp; MCP — click to add</p>
          <div className="space-y-2">
            {tools.length === 0 && <p className="text-[10px] text-[var(--color-muted-foreground)]">No tools available.</p>}
            {tools.map((t) => {
              const mcp = t.name.startsWith("mcp__");
              return (
                <button key={t.name} onClick={() => addToolNode(t)}
                  className="block w-full rounded-md border border-[var(--color-border)] p-2 text-left text-sm hover:border-[var(--color-status-paused)]">
                  <div className="flex items-center gap-1.5">
                    <span className="rounded px-1 text-[9px]" style={{ background: mcp ? "var(--color-status-paused)" : "var(--color-muted)", color: mcp ? "var(--color-primary-foreground)" : "var(--color-muted-foreground)" }}>
                      {mcp ? "MCP" : "TOOL"}
                    </span>
                    <span className="break-all font-mono text-[11px]">{t.name}</span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-[var(--color-muted-foreground)]">{t.description}</div>
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-[10px] text-[var(--color-muted-foreground)]">
            Connect nodes via the bottom→top handles. Click an edge to add a condition (e.g. <code>iteration_count &lt; 3</code>) — point an edge back to an earlier node for a feedback loop.
          </p>
        </div>

        <div className="flex-1 overflow-hidden rounded-[var(--radius)] border border-[var(--color-border)]">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={(c: NodeChange[]) => onNodesChange(c)}
            onEdgesChange={(c: EdgeChange[]) => onEdgesChange(c)}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onNodeClick={(_e, n: Node) => { setSelNode(n.id); setSelEdge(null); }}
            onEdgeClick={(_e, ed: Edge) => { setSelEdge(ed.id); setSelNode(null); }}
            fitView
            colorMode="dark"
          >
            <Background />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>

        <div className="w-72 shrink-0 overflow-auto rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-3">
          {!selectedNode && !selectedEdge && (
            <p className="text-xs text-[var(--color-muted-foreground)]">Select a node or edge to configure it.</p>
          )}
          {selectedNode && selectedNode.type === "tool" && (
            <div className="space-y-3">
              <p className="break-all text-sm font-semibold">{(selectedNode.data as ToolNodeData).tool}</p>
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)]">Input mapping (JSON: arg → $.path)</label>
                <textarea className={`${FIELD} font-mono`} rows={3}
                  value={(selectedNode.data as ToolNodeData).inputMapping ?? "{}"}
                  onChange={(e) => patchToolNode(selectedNode.id, { inputMapping: e.target.value })} />
                <p className="mt-0.5 text-[10px] text-[var(--color-muted-foreground)]">
                  e.g. <code>{`{"expression":"$.variables.expr"}`}</code> or <code>$.artifacts.x</code>
                </p>
              </div>
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)]">Output key</label>
                <input className={FIELD} value={(selectedNode.data as ToolNodeData).outputKey ?? ""}
                  onChange={(e) => patchToolNode(selectedNode.id, { outputKey: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)]">On failure → route to</label>
                <select className={FIELD} value={(selectedNode.data as ToolNodeData).onError ?? ""}
                  onChange={(e) => patchToolNode(selectedNode.id, { onError: e.target.value || undefined })}>
                  <option value="">— fail the run —</option>
                  {nodes.filter((n) => n.id !== selectedNode.id).map((n) => (
                    <option key={n.id} value={n.id}>{nodeLabel(n)}</option>
                  ))}
                </select>
              </div>
              <button onClick={() => setEntry(selectedNode.id)} className="w-full rounded-md border border-[var(--color-border)] px-2 py-1.5 text-sm">Set as entry node</button>
              <button onClick={() => deleteNode(selectedNode.id)} className="w-full rounded-md border border-[var(--color-status-failed)] px-2 py-1.5 text-sm text-[var(--color-status-failed)]">Delete node</button>
            </div>
          )}
          {selectedNode && selectedNode.type !== "tool" && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">{(selectedNode.data as AgentNodeData).agentName}</p>
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)]">Output key</label>
                <input className={FIELD} value={(selectedNode.data as AgentNodeData).outputKey ?? ""}
                  onChange={(e) => patchNode(selectedNode.id, { outputKey: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)]">On failure → route to</label>
                <select className={FIELD} value={(selectedNode.data as AgentNodeData).onError ?? ""}
                  onChange={(e) => patchNode(selectedNode.id, { onError: e.target.value || undefined })}>
                  <option value="">— fail the run —</option>
                  {nodes.filter((n) => n.id !== selectedNode.id).map((n) => (
                    <option key={n.id} value={n.id}>{nodeLabel(n)}</option>
                  ))}
                </select>
              </div>
              <button onClick={() => setEntry(selectedNode.id)} className="w-full rounded-md border border-[var(--color-border)] px-2 py-1.5 text-sm">Set as entry node</button>
              <button onClick={() => deleteNode(selectedNode.id)} className="w-full rounded-md border border-[var(--color-status-failed)] px-2 py-1.5 text-sm text-[var(--color-status-failed)]">Delete node</button>
            </div>
          )}
          {selectedEdge && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">Edge condition</p>
              <p className="text-xs text-[var(--color-muted-foreground)]">Blank = unconditional. Conditions enable branches and feedback loops.</p>
              <input className={`${FIELD} font-mono`} placeholder="iteration_count < 3"
                value={(selectedEdge.data as EdgeData)?.condition ?? ""}
                onChange={(e) => patchEdge(selectedEdge.id, { condition: e.target.value }, e.target.value)} />
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)]">Priority (lower checked first)</label>
                <input type="number" className={FIELD} value={(selectedEdge.data as EdgeData)?.priority ?? 1}
                  onChange={(e) => patchEdge(selectedEdge.id, { priority: parseInt(e.target.value || "1") })} />
              </div>
              <button onClick={() => deleteEdge(selectedEdge.id)} className="w-full rounded-md border border-[var(--color-status-failed)] px-2 py-1.5 text-sm text-[var(--color-status-failed)]">Delete edge</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function WorkflowBuilder(props: BuilderProps) {
  return (
    <ReactFlowProvider>
      <BuilderInner {...props} />
    </ReactFlowProvider>
  );
}
