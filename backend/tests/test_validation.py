"""Workflow graph validation — table-driven over invalid graphs."""

from __future__ import annotations

from app.runtime.validation import validate_graph


def _codes(graph, **kw):
    return {i.code for i in validate_graph(graph, **kw)}


def test_valid_linear_graph_has_no_issues():
    graph = {
        "entry_node": "a",
        "variables": {},
        "nodes": [
            {"id": "a", "type": "agent", "agent_id": "1"},
            {"id": "b", "type": "agent", "agent_id": "2"},
        ],
        "edges": [{"id": "e1", "from": "a", "to": "b"}],
    }
    assert validate_graph(graph, known_agent_ids={"1", "2"}) == []


def test_missing_entry():
    assert "no_entry" in _codes({"nodes": [], "edges": []})


def test_bad_entry_reference():
    graph = {"entry_node": "x", "nodes": [{"id": "a", "type": "agent"}], "edges": [{"from": "a", "to": "a", "condition": "iteration_count < 2"}]}
    assert "bad_entry" in _codes(graph)


def test_unknown_agent():
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent", "agent_id": "999"}],
        "edges": [],
    }
    assert "unknown_agent" in _codes(graph, known_agent_ids={"1"})


def test_dangling_edge_targets():
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent"}],
        "edges": [{"id": "e1", "from": "a", "to": "ghost"}],
    }
    codes = _codes(graph)
    assert "bad_edge_target" in codes


def test_leaf_node_is_valid_terminal():
    # A leaf agent node legitimately ends the workflow -> no issue.
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent", "agent_id": "1"}, {"id": "b", "type": "agent", "agent_id": "2"}],
        "edges": [{"from": "a", "to": "b"}],
    }
    assert validate_graph(graph, known_agent_ids={"1", "2"}) == []


def test_unreachable_node():
    graph = {
        "entry_node": "a",
        "nodes": [
            {"id": "a", "type": "channel_out"},
            {"id": "orphan", "type": "channel_out"},
        ],
        "edges": [],
    }
    assert "unreachable" in _codes(graph)


def test_uncontrolled_cycle():
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent"}, {"id": "b", "type": "agent"}],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "a"},  # no termination condition
        ],
    }
    assert "uncontrolled_cycle" in _codes(graph)


def test_controlled_cycle_ok():
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent"}, {"id": "b", "type": "channel_out"}],
        "edges": [
            {"from": "a", "to": "a", "condition": "iteration_count < 3", "priority": 1},
            {"from": "a", "to": "b", "priority": 2},
        ],
    }
    assert "uncontrolled_cycle" not in _codes(graph)


def test_priority_overlap():
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent"}, {"id": "b", "type": "channel_out"}, {"id": "c", "type": "channel_out"}],
        "edges": [
            {"from": "a", "to": "b", "condition": "iteration_count < 2", "priority": 1},
            {"from": "a", "to": "c", "condition": "iteration_count > 5", "priority": 1},
        ],
    }
    assert "priority_overlap" in _codes(graph)


def test_bad_condition_syntax():
    graph = {
        "entry_node": "a",
        "nodes": [{"id": "a", "type": "agent"}, {"id": "b", "type": "channel_out"}],
        "edges": [{"from": "a", "to": "b", "condition": "this is not valid ==="}],
    }
    assert "bad_condition" in _codes(graph)


def test_unknown_variable_in_condition():
    graph = {
        "entry_node": "a",
        "variables": {"topic": {}},
        "nodes": [{"id": "a", "type": "agent"}, {"id": "b", "type": "channel_out"}],
        "edges": [{"from": "a", "to": "b", "condition": "variables.nonexistent == 1"}],
    }
    assert "unknown_variable" in _codes(graph)
