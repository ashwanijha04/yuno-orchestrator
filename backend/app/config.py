"""Application configuration, loaded from environment via pydantic-settings.

Secrets never get hardcoded and never get logged. See `.env.example` for the
full set of variables; everything here has a local-dev default so the stack
boots with `docker-compose up` even before keys are filled in.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMMode = Literal["live", "record", "replay", "stub"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Infrastructure ---
    database_url: str = "postgresql+asyncpg://yuno:yuno@postgres:5432/yuno"
    redis_url: str = "redis://redis:6379/0"

    # --- LLM providers (no defaults; absence is handled by the harness) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    aws_region: str | None = None

    # --- Harness mode (see Subsystem B) ---
    llm_mode: LLMMode = "stub"
    llm_provider_default: str = "anthropic"
    llm_recording_name: str | None = None
    llm_script_path: str | None = None

    # --- Tools ---
    tavily_api_key: str | None = None
    code_runner_socket: str = "/var/run/code-runner.sock"

    # --- Channels ---
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    # 'polling' for friction-free dev, 'webhook' for the snappy demo/production path
    telegram_transport: Literal["polling", "webhook"] = "polling"
    public_base_url: str | None = None  # for webhook registration (tunnel URL)

    # --- Memory ---
    extremis_store: str | None = None  # e.g. postgres DSN for the extremis server
    extremis_url: str | None = None

    # --- App ---
    app_env: Literal["dev", "prod"] = "dev"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
