"""DSL evaluator — table-driven over the edge-condition grammar."""

from __future__ import annotations

import pytest

from app.runtime.dsl import DSLError, evaluate, validate_expression

CTX = {
    "variables": {"topic": "OpenAI", "max_revisions": 2},
    "artifacts": {"category": "refund", "approved": False, "score": 7},
    "iteration_count": 3,
    "last_message": "Final verdict: APPROVED",
}

CASES = [
    ('artifacts.category == "refund"', True),
    ('artifacts.category == "billing"', False),
    ("artifacts.approved == false", True),
    ("artifacts.approved == true", False),
    ("iteration_count < 5", True),
    ("iteration_count >= 3", True),
    ("iteration_count > 3", False),
    ("artifacts.score >= 7 && artifacts.score <= 10", True),
    ('artifacts.category == "refund" && iteration_count < 2', False),
    ('artifacts.category == "refund" || iteration_count < 2', True),
    ('!(artifacts.approved == true)', True),
    ('last_message contains "APPROVED"', True),
    ('last_message contains "REJECTED"', False),
    ('variables.topic == "OpenAI"', True),
    ("iteration_count < variables.max_revisions", False),  # 3 < 2
    ("artifacts.missing == 5", False),  # unresolved path never matches
]


@pytest.mark.parametrize("expr,expected", CASES)
def test_evaluate(expr, expected):
    assert evaluate(expr, CTX) is expected


def test_invalid_expression_raises():
    with pytest.raises(DSLError):
        validate_expression("artifacts.x ===")
    with pytest.raises(DSLError):
        evaluate("&& bad", CTX)
