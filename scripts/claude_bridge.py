#!/usr/bin/env python3
"""Host-side bridge: runs your LOCAL Claude Code (`claude`) for coding sessions
the platform requests — so Jarvis (e.g. from Telegram) can spawn real coding
sessions using your own Claude auth, no API key.

Why a bridge? The platform runs in Docker; your authenticated `claude` CLI lives
on this host. This script (run on the host) polls the platform for coding jobs,
runs `claude --dangerously-skip-permissions` locally, and posts the result back.

Requirements: Python 3 (stdlib only) + the `claude` CLI installed & logged in.

Usage:
    python scripts/claude_bridge.py
    # custom API port (match your backend) / workspace:
    YUNO_API=http://localhost:8000 CLAUDE_WORKSPACE=~/yuno-coding python scripts/claude_bridge.py
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

API = os.environ.get("YUNO_API", "http://localhost:8000").rstrip("/")
WORKSPACE = os.path.expanduser(os.environ.get("CLAUDE_WORKSPACE", "~/yuno-coding-workspace"))
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
JOB_TIMEOUT = int(os.environ.get("CLAUDE_JOB_TIMEOUT", "1800"))


def _claim():
    try:
        with urllib.request.urlopen(f"{API}/coding/next", timeout=15) as resp:
            if resp.status == 204:
                return None
            return json.loads(resp.read() or b"{}")
    except urllib.error.URLError:
        return None
    except Exception:
        return None


def _post_result(session_id: str, result: str, ok: bool) -> None:
    data = json.dumps({"result": result, "ok": ok}).encode()
    req = urllib.request.Request(
        f"{API}/coding/{session_id}/result", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as exc:
        print(f"  ! failed to post result: {exc}")


def _run_claude(task: str, cwd: str) -> tuple[str, bool]:
    workdir = os.path.expanduser(cwd) if cwd else WORKSPACE
    os.makedirs(workdir, exist_ok=True)
    print(f"  ▶ claude in {workdir}: {task[:80]}")
    try:
        proc = subprocess.run(
            [CLAUDE, "-p", task, "--dangerously-skip-permissions"],
            cwd=workdir, capture_output=True, text=True, timeout=JOB_TIMEOUT,
        )
    except FileNotFoundError:
        return ("`claude` CLI not found on PATH — install Claude Code and log in.", False)
    except subprocess.TimeoutExpired:
        return (f"claude session timed out after {JOB_TIMEOUT}s", False)
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return (out or "(no output)", proc.returncode == 0)


def main() -> None:
    print(f"Claude bridge → {API}  ·  workspace {WORKSPACE}")
    print("Waiting for coding jobs… (Ctrl-C to stop)")
    while True:
        job = _claim()
        if not job:
            time.sleep(2)
            continue
        print(f"• job {job['id']}")
        result, ok = _run_claude(job.get("task", ""), job.get("cwd", ""))
        _post_result(job["id"], result, ok)
        print(f"  ✓ posted ({'ok' if ok else 'failed'}, {len(result)} chars)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbridge stopped.")
