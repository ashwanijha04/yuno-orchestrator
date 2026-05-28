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


def _post(path: str, payload: dict) -> dict | None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def _poll_decision(session_id: str, timeout: int = 900) -> str:
    """Block until the plan is approved/denied (or time out → deny)."""
    waited = 0
    while waited < timeout:
        time.sleep(2)
        waited += 2
        try:
            with urllib.request.urlopen(f"{API}/coding/{session_id}", timeout=10) as r:
                d = json.loads(r.read() or b"{}")
            if d.get("decision") in ("allow", "deny"):
                return d["decision"]
        except Exception:
            pass
    return "deny"


def _run_claude(task: str, cwd: str, permission_mode: str | None = None, on_event=None) -> tuple[str, bool]:
    workdir = os.path.expanduser(cwd) if cwd else WORKSPACE
    os.makedirs(workdir, exist_ok=True)
    print(f"  ▶ claude in {workdir} ({permission_mode or 'execute'}): {task[:80]}", flush=True)
    cmd = [CLAUDE, "-p", task, "--output-format", "stream-json", "--verbose"]
    cmd += ["--permission-mode", permission_mode] if permission_mode else ["--dangerously-skip-permissions"]
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


APPROVALS = os.environ.get("CODING_APPROVALS", "plan")  # "plan" (review first) | "off"


def _handle(job: dict) -> None:
    sid, task, cwd = job["id"], job.get("task", ""), job.get("cwd", "")
    if APPROVALS != "off":
        # Plan first (no execution), get it approved, then execute.
        plan, ok = _run_claude(task, cwd, permission_mode="plan")
        if not ok:
            _post_result(sid, plan, False)
            return
        print("  ⏸ plan ready — awaiting approval", flush=True)
        _post(f"/coding/{sid}/plan", {"plan": plan})
        if _poll_decision(sid) != "allow":
            _post_result(sid, "Plan was not approved — nothing was changed.", True)
            print("  ✗ denied", flush=True)
            return
        print("  ✓ approved — executing", flush=True)
    result, ok = _run_claude(task, cwd)  # execute (skip-permissions)
    _post_result(sid, result, ok)
    print(f"  ✓ posted ({'ok' if ok else 'failed'}, {len(result)} chars)", flush=True)


def main() -> None:
    print(f"Claude bridge → {API}  ·  workspace {WORKSPACE}  ·  approvals: {APPROVALS}")
    print("Waiting for coding jobs… (Ctrl-C to stop)")
    while True:
        job = _claim()
        if not job:
            time.sleep(2)
            continue
        print(f"• job {job['id']}")
        _handle(job)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbridge stopped.")
