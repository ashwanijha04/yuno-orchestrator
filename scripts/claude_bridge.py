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


def _summarize(ev: dict):
    """(human-readable live line | None, final result text | None) for a stream event."""
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        return ("▶ session started", None)
    if t == "assistant":
        lines = []
        for b in ev.get("message", {}).get("content", []):
            if b.get("type") == "text" and b.get("text", "").strip():
                lines.append("💬 " + b["text"].strip().replace("\n", " ")[:200])
            elif b.get("type") == "tool_use":
                inp = b.get("input", {}) or {}
                hint = inp.get("file_path") or inp.get("command") or inp.get("path") or inp.get("pattern") or ""
                lines.append(f"🔧 {b.get('name', 'tool')} {str(hint)[:90]}".rstrip())
        return ("\n    ".join(lines) if lines else None, None)
    if t == "user":
        return ("↳ tool result", None)
    if t == "result":
        return (None, ev.get("result", ""))
    return (None, None)


def _run_claude(task: str, cwd: str, on_event=None) -> tuple[str, bool]:
    workdir = os.path.expanduser(cwd) if cwd else WORKSPACE
    os.makedirs(workdir, exist_ok=True)
    print(f"  ▶ claude in {workdir}: {task[:80]}", flush=True)
    cmd = [CLAUDE, "-p", task, "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]
    try:
        proc = subprocess.Popen(cmd, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        return ("`claude` CLI not found on PATH — install Claude Code and log in.", False)
    final = ""
    try:
        for line in proc.stdout:  # one JSON event per line, streamed live
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            summary, result_text = _summarize(ev)
            if summary:
                print(f"    {summary}", flush=True)
                if on_event:
                    on_event(summary)
            if result_text is not None:
                final = result_text
        proc.wait(timeout=JOB_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        return (f"claude session timed out after {JOB_TIMEOUT}s", False)
    if not final:
        final = (proc.stderr.read() if proc.stderr else "").strip() or "(no output)"
    return (final, proc.returncode == 0)


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
