"""python_exec — run a short snippet in the isolated code-runner container over
its Unix socket (no network, ephemeral, ulimited). Returns stdout/stderr/exit."""

from __future__ import annotations

import asyncio
import json

from app.config import settings
from app.tools.base import ToolContext


class PythonExecTool:
    name = "python_exec"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        code = input.get("code")
        if not code:
            return {"error": "code is required"}
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(settings.code_runner_socket), timeout=5
            )
        except (OSError, asyncio.TimeoutError) as exc:
            return {"error": f"code-runner unavailable: {exc}"}
        try:
            writer.write((json.dumps({"code": code}) + "\n").encode())
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=15)
            return json.loads(line) if line else {"error": "no response from code-runner"}
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
