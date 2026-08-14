#!/usr/bin/env bash
# TELOS Dashboard launcher — persistent, one command, survives terminal close.
#
#   ./telos/start_dashboard.sh           # start detached, print URL
#   ./telos/start_dashboard.sh status    # is it running?
#   ./telos/start_dashboard.sh stop      # stop it
#   ./telos/start_dashboard.sh restart   # stop + start
#
# The raw path `python3 telos/serve_dashboard.py` still works unchanged.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8765
PIDFILE="/tmp/telos_dashboard.pid"
LOGFILE="/tmp/telos_dashboard.log"

is_running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

cmd_status() {
  if is_running; then
    echo "TELOS dashboard RUNNING (pid $(cat "$PIDFILE")) -> http://localhost:${PORT}"
    return 0
  fi
  echo "TELOS dashboard NOT running"
  [ -f "$PIDFILE" ] && rm -f "$PIDFILE"
  return 1
}

cmd_stop() {
  if is_running; then
    local pid; pid="$(cat "$PIDFILE")"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "TELOS dashboard stopped"
  else
    echo "Not running - nothing to stop"
    rm -f "$PIDFILE"
  fi
}

cmd_start() {
  if is_running; then
    echo "Already running (pid $(cat "$PIDFILE")) -> http://localhost:${PORT}"
    return 0
  fi
  cd "$HERE"
  nohup python3 -u serve_dashboard.py >> "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 30); do
    if curl -sf -o /dev/null "http://localhost:${PORT}/"; then
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
