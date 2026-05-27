"""Edge-condition DSL: parse once, evaluate against workflow state.

Used to guard outer-graph transitions. Deliberately not `eval` — a real parser
over a constrained grammar, so workflow JSON is safe to load and inspect.
"""

from __future__ import annotations

import operator
from functools import lru_cache
from pathlib import Path
from typing import Any

from lark import Lark, Transformer, v_args
from lark.exceptions import LarkError

_GRAMMAR = (Path(__file__).parent / "grammar.lark").read_text()


class DSLError(ValueError):
    pass


class _Missing:
    """Sentinel for an unresolved path; compares falsey, never matches."""

    def __repr__(self) -> str:
        return "<missing>"


MISSING = _Missing()


def _resolve(context: dict, parts: list[str]) -> Any:
    cur: Any = context
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return MISSING
    return cur


_COMPARATORS = {
    "lt": operator.lt,
    "gt": operator.gt,
    "le": operator.le,
    "ge": operator.ge,
}


@v_args(inline=True)
class _Evaluator(Transformer):
    def __init__(self, context: dict):
        super().__init__()
        self.context = context

    # literals
    def str_lit(self, token):
        return str(token)[1:-1]  # strip quotes

    def num_lit(self, token):
        text = str(token)
        return float(text) if ("." in text or "e" in text.lower()) else int(text)

    def true_lit(self):
        return True

    def false_lit(self):
        return False

    def path(self, *names):
        return [str(n) for n in names]

    def getpath(self, parts):
        return _resolve(self.context, parts)

    # boolean
    def or_op(self, a, b):
        return bool(a) or bool(b)

    def and_op(self, a, b):
        return bool(a) and bool(b)

    def not_op(self, a):
        return not bool(a)

    # comparisons
    def eq(self, a, b):
        return a == b

    def ne(self, a, b):
        return a != b

    def lt(self, a, b):
        return self._cmp("lt", a, b)

    def gt(self, a, b):
        return self._cmp("gt", a, b)

    def le(self, a, b):
        return self._cmp("le", a, b)

    def ge(self, a, b):
        return self._cmp("ge", a, b)

    def contains(self, a, token):
        needle = str(token)[1:-1]
        return needle in a if isinstance(a, str) else False

    @staticmethod
    def _cmp(op: str, a, b) -> bool:
        if a is MISSING or b is MISSING:
            return False
        try:
            return _COMPARATORS[op](a, b)
        except TypeError:
            return False


@lru_cache(maxsize=256)
def _parser() -> Lark:
    # LALR + contextual lexer makes keyword terminals (true/false/contains) win
    # over CNAME deterministically, avoiding earley's ambiguous lexing.
    return Lark(_GRAMMAR, parser="lalr")


def validate_expression(expr: str) -> None:
    """Raise DSLError if the expression doesn't parse."""
    try:
        _parser().parse(expr)
    except LarkError as exc:
        raise DSLError(f"invalid condition {expr!r}: {exc}") from exc


def evaluate(expr: str, context: dict) -> bool:
    """Evaluate a condition expression to a boolean against `context`."""
    try:
        tree = _parser().parse(expr)
    except LarkError as exc:
        raise DSLError(f"invalid condition {expr!r}: {exc}") from exc
    return bool(_Evaluator(context).transform(tree))


def referenced_paths(expr: str) -> list[list[str]]:
    """Top-level paths referenced (for validation of unknown vars/artifacts)."""
    tree = _parser().parse(expr)
    out: list[list[str]] = []
    for node in tree.iter_subtrees():
        if node.data == "path":
            out.append([str(t) for t in node.children])
    return out
