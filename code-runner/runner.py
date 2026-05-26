"""Sandboxed code execution service for the `python_exec` tool.

Runs in a separate container with NO network, an ephemeral volume, and ulimits
(see docker-compose). The worker calls in over a Unix socket; this process only
ever executes short, untrusted snippets and returns stdout/stderr + exit status.

Phase 0: a minimal line-delimited JSON server over the Unix socket so the
boundary exists and is testable. Phase 5 hardens limits and wires the tool.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys

SOCKET_PATH = os.environ.get("CODE_RUNNER_SOCKET", "/var/run/code-runner.sock")
EXEC_TIMEOUT_S = float(os.environ.get("CODE_RUNNER_TIMEOUT", "10"))


def _run_snippet(code: str) -> dict:
    try:
        proc = subprocess.run(  # noqa: S603 — intentional sandboxed execution
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_S,
        )
        return {
            "stdout": proc.stdout[-10_000:],
            "stderr": proc.stderr[-10_000:],
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "execution timed out", "exit_code": -1}


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    line = await reader.readline()
    if line:
        try:
            req = json.loads(line)
            result = _run_snippet(req.get("code", ""))
        except json.JSONDecodeError:
            result = {"stdout": "", "stderr": "invalid request", "exit_code": -1}
        writer.write((json.dumps(result) + "\n").encode())
        await writer.drain()
    writer.close()
    await writer.wait_closed()


async def main() -> None:
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    server = await asyncio.start_unix_server(_handle, path=SOCKET_PATH)
    print(f"code-runner listening on {SOCKET_PATH}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
