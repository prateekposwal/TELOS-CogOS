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
PIDFILE="/tmp/telos_dashboard.pid"
LOGFILE="/tmp/telos_dashboard.log"

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
  nohup python3 -u serve_dashboard.py >> "$LOGFILE" 2>&1 &
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

case "${1:-start}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  status)  cmd_status ;;
  restart) cmd_stop; cmd_start ;;
  *) echo "usage: $0 [start|stop|status|restart]"; exit 1 ;;
esac
