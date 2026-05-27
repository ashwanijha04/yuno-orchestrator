"""Workflow execution state — the LangGraph StateGraph schema.

Reducers matter here (see the LangGraph reducer gotcha): `messages` must append
across agents and `artifacts`/`metadata` must merge, so they're Annotated.
`iteration_count` and `current_agent` use default overwrite semantics.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(old: dict | None, new: dict | None) -> dict:
    return {**(old or {}), **(new or {})}


class GraphState(TypedDict, total=False):
    run_id: str
    variables: dict[str, Any]
    artifacts: Annotated[dict[str, Any], merge_dicts]
    messages: Annotated[list[dict], operator.add]
    current_agent: str | None
    iteration_count: int
    metadata: Annotated[dict[str, Any], merge_dicts]


def build_eval_context(state: GraphState) -> dict[str, Any]:
    """The flattened view the DSL evaluates edge conditions against."""
    messages = state.get("messages", [])
    last = messages[-1]["content"] if messages else ""
    return {
        "variables": state.get("variables", {}),
        "artifacts": state.get("artifacts", {}),
        "iteration_count": state.get("iteration_count", 0),
        "last_message": last,
    }


def initial_state(run_id: str, variables: dict[str, Any] | None = None) -> GraphState:
    return GraphState(
        run_id=run_id,
        variables=variables or {},
        artifacts={},
        messages=[],
        current_agent=None,
        iteration_count=0,
        metadata={},
    )
