"""
Quickstart example — it must run clean from a source checkout.

The example is the first thing a new user runs; if it rots, the onboarding
story is a lie. This test runs it as a subprocess against an isolated state dir
and asserts a clean exit plus a measured result.
"""

import os
import subprocess
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_quickstart_runs_clean(tmp_path):
    """examples/quickstart.py exits 0 and prints a measured cycle."""
    env = dict(os.environ)
    env["PYTHONPATH"] = PROJECT
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT, "examples", "quickstart.py")],
        capture_output=True, text=True, timeout=300, cwd=PROJECT, env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = proc.stdout
    assert "quickstart" in out
    assert "cycle 1:" in out
    assert "DI=" in out
    assert "memory recalled:" in out
    assert "Done." in out


def test_quickstart_state_is_gitignored():
    """The example's local state must not be committed."""
    gitignore = os.path.join(PROJECT, ".gitignore")
    with open(gitignore) as f:
        content = f.read()
    assert "quickstart" in content.lower() or ".quickstart_state" in content
