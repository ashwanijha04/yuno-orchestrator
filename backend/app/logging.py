"""Structured logging via structlog.

Every log line can carry run_id / step_id / agent_id through contextvars binding
(see structlog.contextvars), so an operator greps one id and sees the whole story.
"""

from __future__ import annotations

import logging

import structlog

from app.config import settings


def configure_logging() -> None:
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.app_env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
