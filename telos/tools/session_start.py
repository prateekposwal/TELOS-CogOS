#!/usr/bin/env python3
"""
Session Start Primer — run at beginning of every session.
Checks all registered projects for their current state.

Usage:
  python3 telos/tools/session_start.py

Output: list of projects with their status, any CI failures,
and open questions that carried over from last session.

PROJECT MAP (authoritative — do not "correct" unless the repos move):
  ACTIVE  #1  TELOS CogOS            = this workspace (Vrooom-computation)
  ACTIVE  #2  Bitcoin Block Space    = ../block-space-economics  (bitcoinsahi.com)
                                          (formerly "Bitcoin Priority Oracle" v1 —
                                           that path is DEAD; never repoint here)
  PARKED  #3  Trading Project        = tracked in TRADING_PROJECT_STATE.md
"""
import os, re, json, datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TELOS_PATH = BASE
BITCOIN_PATH = os.path.join(os.path.dirname(BASE), 'block-space-economics')  # ACTIVE #2 (v2+). v1 `bitcoin-priority-oracle` is DEAD — do not restore.

def read_agents(path):
    """Parse AGENTS.md for project state.

    Args:
        path: the project directory whose AGENTS.md to read.
    """
    agents_file = os.path.join(path, 'AGENTS.md')
    if not os.path.exists(agents_file):
        return None
    with open(agents_file) as f:
        return f.read()

def read_live_data(path):
    """Check for live data from research monitor.

    Args:
        path: the project directory to search for live data files.
    """
    for data_file in (os.path.join(path, 'tools', 'live_data.json'),
                      os.path.join(path, 'data', 'latest.json')):
        if os.path.exists(data_file):
            try:
                with open(data_file) as f:
                    return json.load(f)
            except Exception:
                continue
    return None

def read_marker(path, filename):
    """Read a small state marker file (e.g. PARKED state).

    Args:
        path: the project directory containing the marker.
        filename: the marker file name within `path`.
    """
    p = os.path.join(path, filename)
    if os.path.exists(p):
        with open(p) as f:
            return f.read().strip()
    return None

def main():
    print("=" * 62)
    print(f"  Session Start — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 62)

    projects = [
        ('TELOS CogOS  [ACTIVE]', TELOS_PATH, 'TRADING_PROJECT_STATE.md'),
        ('Bitcoin Block Space (bitcoinsahi.com)  [ACTIVE]', BITCOIN_PATH, None),
    ]

    for name, path, marker in projects:
        print(f"\n── {name} ──")
        if not os.path.isdir(path):
            print(f"  ⚠ PATH MISSING: {path}")
            continue
        agents = read_agents(path)
        if agents:
            # Extract open questions
            questions = re.findall(r'Q\d[:\.]\s*(.*)', agents)
            if questions:
                print(f"  Open questions carryover:")
                for q in questions:
                    print(f"    • {q}")

            # Extract current focus
            focus = re.search(r'Current focus:\s*(.*)', agents)
            if focus:
                print(f"  Last focus: {focus.group(1)}")
        else:
            print(f"  No AGENTS.md found — run bootstrap_project.py")

        if marker:
            state = read_marker(TELOS_PATH, marker)
            if state:
                print(f"  Trading project: {state[:160]}")

        data = read_live_data(path)
        if data:
            fees = data.get('fees', {})
            price = data.get('btc_price')
            alerts = data.get('alerts', [])
            print(f"  Live data: fees={fees.get('fastestFee', '?')} sat/vB, BTC=${price if price else '?'}")
            if alerts:
                for a in alerts:
                    print(f"  ⚠ {a}")
        else:
            print(f"  No live data — research monitor may not have run yet")

    print(f"\n{'='*62}")
    print(f"  Run 'python3 telos/tools/self_audit.py' for TELOS health")
    print(f"  Run 'node tools/data-engineering/monitor.js' in ../block-space-economics for endpoint health")
    print(f"  PROJECT MAP: ACTIVE = TELOS core + Bitcoin block-space | PARKED = trading | DEAD = bitcoin-priority-oracle (v1)")
    print(f"{'='*62}")

if __name__ == "__main__":
    main()
