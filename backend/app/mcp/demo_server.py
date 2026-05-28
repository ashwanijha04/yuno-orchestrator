"""A small, self-contained MCP server (stdio) used to demonstrate the platform's
real Model Context Protocol integration. Offline-only tools, so the demo never
depends on the network.

Run standalone:  python -m app.mcp.demo_server
The platform's MCP client (app/mcp/client.py) spawns this and exposes its tools
to agents as `mcp__demo__<tool>`.
"""

from __future__ import annotations

import ast
import operator
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo")

# Safe arithmetic: evaluate +-*/ ** and parentheses over numbers, nothing else.
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '(3 + 4) * 2 ** 3'."""
    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except Exception:
        return "Error: only basic arithmetic (+ - * / ** % and parentheses) is supported."


@mcp.tool()
def current_time() -> str:
    """Return the current UTC date and time in ISO-8601."""
    return datetime.now(UTC).isoformat()


@mcp.tool()
def word_stats(text: str) -> str:
    """Return word and character counts for a piece of text."""
    words = len(text.split())
    return f"{words} words, {len(text)} characters"


if __name__ == "__main__":
    mcp.run()  # stdio transport
