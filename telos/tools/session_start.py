#!/usr/bin/env python3
"""
Session Start Primer — run at beginning of every session.
Checks all registered projects for their current state.

Usage:
  python3 telos/tools/session_start.py

Ouput: list of projects with their status, any CI failures,
and open questions that carried over from last session.
"""
import os, re, json, datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TELOS_PATH = BASE
BITCOIN_PATH = os.path.join(os.path.dirname(BASE), 'bitcoin-priority-oracle')

def read_agents(path):
    """Parse AGENTS.md for project state."""
    agents_file = os.path.join(path, 'AGENTS.md')
    if not os.path.exists(agents_file):
        return None
    with open(agents_file) as f:
        return f.read()

def read_live_data(path):
    """Check for live data from research monitor."""
    data_file = os.path.join(path, 'tools', 'live_data.json')
    if os.path.exists(data_file):
        with open(data_file) as f:
            return json.load(f)
    return None

def main():
    print("=" * 62)
    print(f"  Session Start — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 62)
    
    projects = {
        'TELOS CogOS': TELOS_PATH,
        'Bitcoin Priority Oracle': BITCOIN_PATH,
    }
    
    for name, path in projects.items():
        print(f"\n── {name} ──")
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
    print(f"  Run 'python3 research/utxo_cost_model.py' for Bitcoin model")
    print(f"{'='*62}")

if __name__ == "__main__":
    main()
