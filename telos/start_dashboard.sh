#!/usr/bin/env bash
# TELOS Dashboard launcher — persistent, one command, survives terminal close.
#
#   ./telos/start_dashboard.sh           # start detached, print URL
#   ./telos/start_dashboard.sh status    # is it really serving?
#   ./telos/start_dashboard.sh stop      # stop it
#   ./telos/start_dashboard.sh restart   # stop + start
#
# The raw path `python3 telos/serve_dashboard.py` still works unchanged.
#
# Robustness: "running" means the port actually answers OR a live (non-zombie)
# process exists. Zombies answer kill -0 but serve nothing — they must never
# block a restart (pattern: a stale marker must not gate the live surface).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8765
# Persistent runtime dir in the repo (NOT /tmp): macOS periodically purges
# /tmp, which previously destroyed the pidfile AND the crash log, leaving a
# dead dashboard with no diagnosable cause. Runtime artifacts are gitignored.
RUNTIME_DIR="$HERE/audit/runtime"
mkdir -p "$RUNTIME_DIR"
PIDFILE="$RUNTIME_DIR/dashboard.pid"
LOGFILE="$RUNTIME_DIR/dashboard.log"
# Log retention (Defect 1): rotation must BOUND disk, not hoard a single
# forever-growing uncompressed copy (observed: telos_dashboard.log.1 = 544MB,
# plus a ~60MB live log — 1 rotated copy kept forever, never compressed).
# Policy: rotate the live log only when it exceeds ROTATE_LOG_BYTES; COMPRESS
# every rotation; keep the newest MAX_ROTATED_LOGS compressed rotations;
# delete older ones. Applied at startup and after every rotation. Legacy
# uncompressed rotations are compressed on the next start.
ROTATE_LOG_BYTES=52428800   # 50MB
MAX_ROTATED_LOGS=3          # newest N compressed rotations retained

port_alive() {
  curl -sf -o /dev/null "http://localhost:${PORT}/"
}

pid_is_zombie() {
  local pid="$1" stat
  [ -n "$pid" ] || return 1
  stat="$(ps -p "$pid" -o stat= 2>/dev/null | tr -d ' ' || true)"
  case "$stat" in Z*) return 0 ;; "") return 1 ;; *) return 1 ;; esac
}

pid_alive() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  pid_is_zombie "$pid" && return 1
  return 0
}

is_running() {
  # A dashboard is running if the port answers (authoritative) or a live
  # non-zombie process holds the pidfile.
  port_alive && return 0
  [ -f "$PIDFILE" ] || return 1
  pid_alive "$(cat "$PIDFILE" 2>/dev/null || true)"
}

cmd_status() {
  if is_running; then
    if port_alive; then
      echo "TELOS dashboard RUNNING (pid $(cat "$PIDFILE" 2>/dev/null || echo '?') -> http://localhost:${PORT}"
    else
      echo "TELOS dashboard RUNNING (process $(cat "$PIDFILE") alive, warming up) -> http://localhost:${PORT}"
    fi
    return 0
  fi
  echo "TELOS dashboard NOT running"
  rm -f "$PIDFILE"
  return 1
}

cmd_stop() {
  if is_running; then
    if port_alive; then
      # Find the actual listener PID (more reliable than the pidfile).
      local pid
      pid="$(lsof -ti tcp:${PORT} 2>/dev/null | head -1 || true)"
      [ -n "$pid" ] || pid="$(cat "$PIDFILE" 2>/dev/null || true)"
      if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
          kill -0 "$pid" 2>/dev/null || break
          sleep 0.2
        done
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PIDFILE"
    echo "TELOS dashboard stopped"
  else
    echo "Not running - nothing to stop"
    rm -f "$PIDFILE"
  fi
}

prune_rotated_logs() {
  # 1. Compress any uncompressed rotated log (legacy LOGFILE.1, LOGFILE.2, ...).
  #    A compression failure must never abort startup — record and continue.
  local f
  for f in "$LOGFILE".[0-9]*; do
    [ -e "$f" ] || continue
    case "$f" in *.gz) continue ;; esac
    if gzip -f "$f" 2>/dev/null; then
      echo "TELOS dashboard: compressed rotated log $f -> $f.gz" >&2
    else
      echo "TELOS dashboard: WARNING could not compress $f" >&2
    fi
  done
  # 2. Keep only the newest MAX_ROTATED_LOGS compressed rotations (mtime order).
  local files
  files="$(ls -1t "$LOGFILE".[0-9]*.gz 2>/dev/null || true)"
  [ -n "$files" ] || return 0
  local i=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    i=$((i + 1))
    if [ "$i" -gt "$MAX_ROTATED_LOGS" ]; then
      rm -f "$f" && echo "TELOS dashboard: pruned old rotated log $f" >&2
    fi
  done <<< "$files"
}

rotate_log() {
  local size ts comp
  size="$(stat -f%z "$LOGFILE" 2>/dev/null || echo 0)"
  if [ -f "$LOGFILE" ] && [ "$size" -gt "$ROTATE_LOG_BYTES" ]; then
    ts="$(date +%Y%m%dT%H%M%S)"
    comp="$LOGFILE.$ts.gz"
    if gzip -c "$LOGFILE" > "$comp" 2>/dev/null; then
      : > "$LOGFILE"
      echo "TELOS dashboard: rotated oversized log to $comp" >&2
    else
      rm -f "$comp"
      echo "TELOS dashboard: WARNING log rotation failed; leaving $LOGFILE in place" >&2
    fi
  fi
  prune_rotated_logs
}

cmd_start() {
  # The port is authoritative: if it answers, the dashboard is serving even
  # if the pidfile is stale/zombie — never start a second instance.
  if port_alive; then
    echo "TELOS dashboard already serving (pid $(cat "$PIDFILE" 2>/dev/null || echo '?')) -> http://localhost:${PORT}"
    return 0
  fi
  # Clear stale or zombie pidfiles that would block a fresh start.
  if [ -f "$PIDFILE" ]; then
    local old; old="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [ -z "$old" ] || ! pid_alive "$old"; then
      rm -f "$PIDFILE"
    fi
  fi
  cd "$HERE"
  # Bound rotated-log disk at every start (compress legacy copies, prune the
  # oldest), then rotate the live log if oversized.
  prune_rotated_logs
  rotate_log
  # Prefer the repo venv interpreter (has numpy/flask/websockets); a bare
  # `python3` may resolve to an interpreter without the dependencies.
  PY="$HERE/../.venv/bin/python"
  [ -x "$PY" ] || PY="$(command -v python3)"
  nohup "$PY" -u serve_dashboard.py >> "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 40); do
    if port_alive; then
      echo "TELOS dashboard started (pid $(cat "$PIDFILE"))"
      echo "   URL:  http://localhost:${PORT}"
      echo "   WS:   ws://localhost:8766"
      echo "   Log:  $LOGFILE"
      echo "   Stop: $HERE/start_dashboard.sh stop"
      return 0
    fi
    sleep 0.5
  done
  echo "Dashboard did not answer on http://localhost:${PORT} - see $LOGFILE" >&2
  return 1
}

# Tests source this file with TELOS_LAUNCHER_LIB_ONLY=1 to exercise the
# rotation helpers without launching the dashboard.
if [ "${TELOS_LAUNCHER_LIB_ONLY:-0}" = "1" ]; then
  return 0 2>/dev/null || true
fi

case "${1:-start}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  status)  cmd_status ;;
  restart) cmd_stop; cmd_start ;;
  *) echo "usage: $0 [start|stop|status|restart]"; exit 1 ;;
esac
