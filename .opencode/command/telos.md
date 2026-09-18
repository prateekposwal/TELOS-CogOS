---
description: Run TELOS routines (health, gates, audits, dashboard, scan) in ~/dev/telos.
agent: build
---

# /telos — run a TELOS CogOS routine

The user invoked `/telos` with these arguments:

    $ARGUMENTS

## Hard rules (load-bearing)

- `cd ~/dev/telos` first. The canonical repo is `~/dev/telos` — never the
  iCloud/Desktop copy.
- Use `./.venv/bin/python` or the `make` targets. **NEVER** call bare
  `python3` — inside opencode it is the bundled interpreter and lacks
  numpy/websockets (this broke the dashboard before).
- Show the **real** command output. Never claim success without it.
- End with an explicit `DONE (verified)` and `LEFT (verified)` list (TELOS's
  reporting rule).

## Routine map (match the first argument)

| Argument | Command |
|---|---|
| (empty) or `health` | `make health` |
| `check` | `make check` |
| `check-fast` | `make check-fast` |
| `audit` | `make audit` |
| `coverage` | `make coverage` |
| `falsify` | `./.venv/bin/python telos/tools/falsify_axioms.py --ci` |
| `theorems` | `./.venv/bin/python telos/tools/theorem_audit.py --cycles 20 --ci` |
| `selection` | `./.venv/bin/python telos/tools/selection_audit.py --compare --cycles 150` |
| `act` | `./.venv/bin/python telos/tools/act_gate_audit.py --cycles 150` |
| `council` | `./.venv/bin/python telos/tools/council_gate_audit.py --cycles 150` |
| `policy` | `./.venv/bin/python telos/tools/policy_audit.py --cycles 150` |
| `scan [path]` | `./.venv/bin/python telos_dev_agent.py --scan -p ${path:-.}` |
| `dashboard` | `./telos/start_dashboard.sh` then report http://localhost:8765 |
| `dashboard stop\|status\|restart` | `./telos/start_dashboard.sh <sub>` |
| `run` | interactive GridWorld task: `./.venv/bin/python telos_task.py` |

## Notes

- `run` (and `telos_task.py`) is **interactive** and needs **Ollama** on
  `localhost:11434`; warn the user and only launch it if they want a REPL.
- `check` and `check-fast` run the full invariant gates (tests + self-audit +
  falsifier + theorems + cognitive health); `check-fast` uses shorter
  simulations for a per-commit loop.
- If the argument is unrecognised, run `make health` and ask what they want.
- If any step fails, surface the exact error output and stop — do not paper
  over it.
