"""Defect 1 lock: the dashboard launcher must BOUND rotated-log disk.

Observed before the fix: `telos/start_dashboard.sh` rotated an oversized live
log to a single `LOGFILE.1` and kept it FOREVER uncompressed — the real file
was 544MB (+ a ~60MB live log). The new policy rotates only above the size
threshold, COMPRESSES every rotation, and keeps the newest N (MAX_ROTATED_LOGS),
deleting older ones — applied at startup (prune) and around rotation.

These tests source the launcher in library-only mode
(TELOS_LAUNCHER_LIB_ONLY=1) and drive the real rotation helpers in a temp dir.
"""
import os
import subprocess
import textwrap

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(REPO_ROOT, "telos", "start_dashboard.sh")


def _run_bash(body: str, tmp_path) -> str:
    """Source the launcher helpers and run `body` with tmp-scoped globals.

    Args:
        body: bash snippet using LOGFILE/ROTATE_LOG_BYTES/MAX_ROTATED_LOGS.
        tmp_path: pytest temp dir passed as $TMPD.

    Returns:
        Combined stdout of the snippet.
    """
    prefix = textwrap.dedent(
        """
        set -euo pipefail
        source "$LAUNCHER"
        LOGFILE="$TMPD/telos_dashboard.log"
        ROTATE_LOG_BYTES=1000
        MAX_ROTATED_LOGS=2
        """
    )
    env = dict(os.environ, TELOS_LAUNCHER_LIB_ONLY="1",
               LAUNCHER=LAUNCHER, TMPD=str(tmp_path))
    out = subprocess.run(["bash", "-c", prefix + body], env=env,
                         text=True, capture_output=True, timeout=60)
    assert out.returncode == 0, f"bash failed: {out.stderr}"
    return out.stdout


def test_legacy_uncompressed_rotation_is_compressed_and_bounded(tmp_path):
    """A 5KB legacy `.1` (stand-in for the 544MB copy) is compressed at
    startup; after several rotations only MAX_ROTATED_LOGS compressed files
    remain and the live log is truncated."""
    _run_bash(textwrap.dedent(
        """
        head -c 5000 /dev/zero > "$LOGFILE.1"
        head -c 2000 /dev/zero > "$LOGFILE"
        prune_rotated_logs
        rotate_log
        for i in 1 2 3; do
          head -c 2000 /dev/zero > "$LOGFILE"
          sleep 1.1
          rotate_log
        done
        """
    ), tmp_path)
    rotated = sorted(f for f in os.listdir(tmp_path) if ".gz" in f)
    # newest 2 kept, never more
    assert len(rotated) == 2, f"expected 2 rotated logs, got {rotated}"
    # the legacy uncompressed copy is gone (compressed or pruned)
    assert not (tmp_path / "telos_dashboard.log.1").exists()
    # the live log was truncated by rotation
    assert (tmp_path / "telos_dashboard.log").stat().st_size == 0


def test_below_threshold_live_log_is_not_rotated(tmp_path):
    """A live log under the threshold is left intact (rotation is size-gated);
    the legacy uncompressed copy still gets compressed at startup."""
    (tmp_path / "telos_dashboard.log").write_text("small live log line\n")
    (tmp_path / "telos_dashboard.log.1").write_bytes(b"x" * 5000)
    _run_bash(textwrap.dedent(
        """
        prune_rotated_logs
        rotate_log
        echo "live_size=$(stat -f%z "$LOGFILE")"
        """
    ), tmp_path)
    live = (tmp_path / "telos_dashboard.log").read_text()
    assert "small live log line" in live, "below-threshold log must not rotate"
    assert (tmp_path / "telos_dashboard.log.1.gz").exists()
    assert not (tmp_path / "telos_dashboard.log.1").exists()


def test_launcher_lib_guard_does_not_dispatch(tmp_path):
    """Library-only mode must NOT run the start/stop dispatch — sourcing the
    file in a test can never launch a real dashboard."""
    out = _run_bash('echo "guard-ok"', tmp_path)
    assert "guard-ok" in out
    assert "TELOS dashboard started" not in out
