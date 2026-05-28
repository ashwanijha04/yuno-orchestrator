#!/usr/bin/env bash
# Reliable startup: auto-select free host ports instead of hardcoding them, so
# `docker compose up` works regardless of what else is running on the machine.
#
# - Internal service traffic (postgres:5432, redis:6379) is unaffected; only the
#   host-published ports are chosen here.
# - Sticky: if our own compose stack already publishes a port, we reuse it (no
#   churn across restarts). Otherwise we reuse the value in .env if it's free,
#   else scan upward from the default until a free port is found.
#
# Usage: scripts/dev-up.sh [extra docker compose up args]   e.g. --build -d
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

# True if a TCP port on 127.0.0.1 is free (can be bound).
port_free() {
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
    sys.exit(0)
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

# First free port at or above $1.
first_free() {
  local p=$1
  while ! port_free "$p"; do p=$((p + 1)); done
  echo "$p"
}

# Upsert KEY=VALUE in .env (portable BSD/GNU sed).
set_env() {
  local key=$1 val=$2
  if grep -q "^${key}=" .env; then
    sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
  else
    echo "${key}=${val}" >> .env
  fi
}

# Choose a host port for a service: reuse our own running mapping if present
# (sticky), else the .env value if free, else scan from the default.
choose_port() {
  local svc=$1 internal=$2 envkey=$3 default=$4
  local running
  running=$(docker compose port "$svc" "$internal" 2>/dev/null | awk -F: 'NF{print $NF}' | tr -d '[:space:]')
  if [ -n "$running" ]; then
    echo "$running"; return
  fi
  local desired
  desired=$(grep "^${envkey}=" .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
  desired=${desired:-$default}
  if port_free "$desired"; then echo "$desired"; else first_free "$desired"; fi
}

POSTGRES_PORT=$(choose_port postgres 5432 POSTGRES_PORT 5432)
REDIS_PORT=$(choose_port redis 6379 REDIS_PORT 6379)
BACKEND_PORT=$(choose_port backend 8000 BACKEND_PORT 8000)
FRONTEND_PORT=$(choose_port frontend 3000 FRONTEND_PORT 3000)

set_env POSTGRES_PORT "$POSTGRES_PORT"
set_env REDIS_PORT "$REDIS_PORT"
set_env BACKEND_PORT "$BACKEND_PORT"
set_env FRONTEND_PORT "$FRONTEND_PORT"
set_env PUBLIC_API_URL "http://localhost:${BACKEND_PORT}"

cat <<EOF

  Yuno — selected host ports (free-port scan):
    UI         http://localhost:${FRONTEND_PORT}
    API        http://localhost:${BACKEND_PORT}  (docs: /docs)
    Postgres   localhost:${POSTGRES_PORT}
    Redis      localhost:${REDIS_PORT}

EOF

# Auto-start the host-side Claude Code bridge so `coding_session` works out of the
# box (it uses your LOCAL `claude` CLI — must run on the host, not in Docker). It
# retries until the backend is up. Skip with YUNO_NO_BRIDGE=1 or if claude is absent.
start_bridge() {
  if [ "${YUNO_NO_BRIDGE:-0}" = "1" ]; then echo "  claude bridge: skipped (YUNO_NO_BRIDGE=1)"; return; fi
  if ! command -v claude >/dev/null 2>&1; then
    echo "  claude bridge: skipped — 'claude' CLI not on PATH (install Claude Code to enable coding_session)"; return
  fi
  if [ -f .bridge.pid ] && kill -0 "$(cat .bridge.pid 2>/dev/null)" 2>/dev/null; then
    echo "  claude bridge: already running (pid $(cat .bridge.pid))"; return
  fi
  YUNO_API="http://localhost:${BACKEND_PORT}" \
  CLAUDE_WORKSPACE="${CLAUDE_WORKSPACE:-$HOME/yuno-coding-workspace}" \
    nohup python3 scripts/claude_bridge.py >/tmp/yuno-claude-bridge.log 2>&1 &
  echo "$!" > .bridge.pid
  echo "  claude bridge: started (pid $!) · log /tmp/yuno-claude-bridge.log"
}
start_bridge

exec docker compose up "$@"
