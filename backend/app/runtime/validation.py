"""Static workflow-graph validation. Runs server-side on save (and the same
rules are mirrored client-side for live builder feedback). Catches the bugs that
make a builder untrustworthy: dangling refs, unreachable nodes, uncontrolled
cycles, conditions over unknown state.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.runtime.dsl import DSLError, referenced_paths, validate_expression


@dataclass
class ValidationIssue:
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


def validate_graph(graph: dict, known_agent_ids: set[str] | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n["id"] for n in nodes}
    node_by_id = {n["id"]: n for n in nodes}
    variables = set(graph.get("variables", {}).keys())

    entry = graph.get("entry_node")
    if not entry:
        issues.append(ValidationIssue("no_entry", "entry_node is not declared"))
    elif entry not in node_ids:
        issues.append(ValidationIssue("bad_entry", f"entry_node {entry!r} does not exist"))

    # Agent nodes must reference an existing agent (when a registry is supplied);
    # on_error handlers must point at a real node.
    for n in nodes:
        if n.get("type") == "agent" and known_agent_ids is not None:
            aid = str(n.get("agent_id"))
            if aid not in known_agent_ids:
                issues.append(
                    ValidationIssue("unknown_agent", f"node {n['id']!r} references unknown agent {aid!r}", node_id=n["id"])
                )
        oe = n.get("on_error")
        if oe and oe not in node_ids:
            issues.append(
                ValidationIssue("bad_on_error", f"node {n['id']!r} on_error target {oe!r} does not exist", node_id=n["id"])
            )

    # Edge endpoints must exist; conditions must parse and reference known state.
    edges_by_source: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        if e["from"] not in node_ids:
            issues.append(ValidationIssue("bad_edge_source", f"edge from unknown node {e['from']!r}", edge_id=e.get("id")))
        if e["to"] not in node_ids:
            issues.append(ValidationIssue("bad_edge_target", f"edge to unknown node {e['to']!r}", edge_id=e.get("id")))
        edges_by_source[e["from"]].append(e)
        cond = e.get("condition")
        if cond:
            try:
                validate_expression(cond)
            except DSLError as exc:
                issues.append(ValidationIssue("bad_condition", str(exc), edge_id=e.get("id")))
                continue
            for path in referenced_paths(cond):
                root = path[0]
                if root == "variables" and len(path) > 1 and path[1] not in variables:
                    issues.append(
                        ValidationIssue("unknown_variable", f"condition references unknown variable {path[1]!r}", edge_id=e.get("id"))
                    )

    # A node with no outgoing edge is a valid workflow terminal (the run ends
    # there), so we don't flag leaves. Reachability (below) catches orphans.

    # Overlapping priorities from one source.
    for source, outs in edges_by_source.items():
        seen: dict[int, int] = defaultdict(int)
        for e in outs:
            if e.get("condition"):
                seen[e.get("priority", 0)] += 1
        for prio, count in seen.items():
            if count > 1:
                issues.append(
                    ValidationIssue("priority_overlap", f"node {source!r} has {count} conditional edges at priority {prio}", node_id=source)
                )

    # Reachability from entry (following normal edges + on_error handlers).
    if entry in node_ids:
        reachable = _reachable(entry, edges_by_source, node_by_id)
        for n in nodes:
            if n["id"] not in reachable:
                issues.append(ValidationIssue("unreachable", f"node {n['id']!r} is unreachable from entry", node_id=n["id"]))

    # Cycles must have at least one edge with a termination-style condition.
    for cycle in _find_cycles(node_ids, edges):
        if not _cycle_has_termination(cycle, edges):
            issues.append(
                ValidationIssue("uncontrolled_cycle", f"cycle {' -> '.join(cycle)} has no termination condition")
            )

    return issues


def _reachable(entry: str, edges_by_source: dict[str, list[dict]], node_by_id: dict[str, dict]) -> set[str]:
    seen: set[str] = set()
    stack = [entry]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for e in edges_by_source.get(cur, []):
            stack.append(e["to"])
        on_error = (node_by_id.get(cur) or {}).get("on_error")
        if on_error:
            stack.append(on_error)
    return seen


def _find_cycles(node_ids: set[str], edges: list[dict]) -> list[list[str]]:
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e["from"]].append(e["to"])
    cycles: list[list[str]] = []
    color: dict[str, int] = {}  # 0=white,1=gray,2=black
    stack: list[str] = []

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in adj.get(u, []):
            if color.get(v, 0) == 1 and v in stack:
                idx = stack.index(v)
                cycles.append(stack[idx:] + [v])
            elif color.get(v, 0) == 0:
                dfs(v)
        stack.pop()
        color[u] = 2

    for n in node_ids:
        if color.get(n, 0) == 0:
            dfs(n)
    return cycles


def _cycle_has_termination(cycle: list[str], edges: list[dict]) -> bool:
    cycle_edges = set(zip(cycle, cycle[1:], strict=False))
    for e in edges:
        if (e["from"], e["to"]) in cycle_edges and e.get("condition"):
            cond = e["condition"]
            if "iteration_count" in cond or "<" in cond or "approved" in cond:
                return True
    return False
