"""Outer workflow graph — compiled dynamically from the workflow JSON into a
LangGraph StateGraph at run start (not handwritten per workflow).

Nodes are generic: each delegates to an injected `node_runner` that knows how to
execute an agent / condition / channel_out node and persist the result. Edges are
grouped by source: a single unconditional edge is a plain edge; otherwise a
priority-sorted router evaluates DSL conditions, first match wins, else END.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Awaitable, Callable

from langgraph.graph import END, StateGraph

from app.runtime.dsl import evaluate
from app.runtime.state import GraphState, build_eval_context

# node_runner(node_spec, state) -> partial state update
NodeRunner = Callable[[dict, GraphState], Awaitable[dict]]


def _make_router(node_id: str, edges: list[dict], on_error: str | None):
    ordered = sorted(edges, key=lambda e: e.get("priority", 1_000_000))

    def router(state: GraphState) -> str:
        # Failure routing wins: if this node recorded an error, divert to its
        # on_error handler instead of the normal edges.
        if on_error and (state.get("errors") or {}).get(node_id):
            return on_error
        ctx = build_eval_context(state)
        for edge in ordered:
            cond = edge.get("condition")
            if cond is None or evaluate(cond, ctx):
                return edge["to"]
        return END

    return router


def build_outer_graph(graph: dict, node_runner: NodeRunner, entry_override: str | None = None):
    builder: StateGraph = StateGraph(GraphState)

    for node in graph["nodes"]:
        node_id = node["id"]

        def _wrap(node_spec):
            async def _fn(state: GraphState) -> dict:
                return await node_runner(node_spec, state)

            return _fn

        builder.add_node(node_id, _wrap(node))

    edges_by_source: dict[str, list[dict]] = defaultdict(list)
    for edge in graph.get("edges", []):
        edges_by_source[edge["from"]].append(edge)

    for node in graph["nodes"]:
        node_id = node["id"]
        outs = edges_by_source.get(node_id, [])
        on_error = node.get("on_error")
        # A plain unconditional edge stays plain; anything with branching, a
        # condition, or an on_error handler routes through the dynamic router.
        needs_router = bool(on_error) or len(outs) > 1 or (len(outs) == 1 and outs[0].get("condition"))
        if not outs and not on_error:
            builder.add_edge(node_id, END)
        elif not needs_router:
            builder.add_edge(node_id, outs[0]["to"])
        else:
            targets = {e["to"] for e in outs}
            if on_error:
                targets.add(on_error)
            mapping = {t: t for t in targets}
            mapping[END] = END
            builder.add_conditional_edges(node_id, _make_router(node_id, outs, on_error), mapping)

    # On resume, re-enter at the paused node instead of the workflow's entry.
    builder.set_entry_point(entry_override or graph["entry_node"])
    return builder.compile()


def recursion_limit_for(graph: dict, max_loops: int = 10) -> int:
    """A generous ceiling so legitimate loops run but runaway graphs stop."""
    return max(25, len(graph.get("nodes", [])) * max_loops)
