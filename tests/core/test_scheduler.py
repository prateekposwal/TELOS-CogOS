"""
Contract tests for telos/core/scheduler.py — ProactiveScheduler.

Periodically runs the TELOS pipeline over a codebase. Tests assert REAL
behavior: construction, interval derivation, start/stop thread lifecycle,
and idempotent start.
"""

import tempfile

from telos.core.scheduler import ProactiveScheduler


def test_constructs_pipeline_with_dev_domain():
    d = tempfile.mkdtemp()
    s = ProactiveScheduler(d, interval_minutes=5)
    assert s.project_path == d
    assert s.interval == 300
    assert s.on_findings is None
    assert s._cycle == 0
    assert s._running is False
    assert s._thread is None
    assert s.pipeline is not None


def _record(calls):
    def _f(findings):
        calls.append(findings)
    return _f


def test_custom_on_findings_callable():
    calls = []
    cb = _record(calls)
    d = tempfile.mkdtemp()
    s = ProactiveScheduler(d, interval_minutes=10, on_findings=cb)
    assert s.interval == 600
    assert s.on_findings is cb


def test_start_and_stop_lifecycle():
    d = tempfile.mkdtemp()
    s = ProactiveScheduler(d, interval_minutes=60)
    s.start()
    assert s._running is True
    assert s._thread is not None
    assert s._thread.daemon is True
    s.stop()
    assert s._running is False


def test_start_idempotent():
    d = tempfile.mkdtemp()
    s = ProactiveScheduler(d, interval_minutes=60)
    s.start()
    first_thread = s._thread
    s.start()  # already running -> returns without new thread
    assert s._thread is first_thread
    s.stop()
    assert s._running is False
