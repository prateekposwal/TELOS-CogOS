"""
Tests for CheckpointManager + TelemetryCollector.
"""

import json
import tempfile
from pathlib import Path

import numpy as np

from telos.core.infra_manager.checkpoint_manager import CheckpointManager
from telos.core.observability.telemetry import TelemetryCollector


class FakeCalibrator:
    def __init__(self):
        self._weights = {"reflex": 1.0, "perception": 0.8}
        self._accuracy = {"reflex": 0.9, "perception": 0.85}
        self._total_calls = {"reflex": 10, "perception": 8}


class FakeFailureLedger:
    def __init__(self):
        self._records = []


class FakeMissionPolicy:
    def __init__(self):
        self._risk_tolerance = 0.5
        self._exploration_budget = 0.3
        self._ambition = 0.7


class FakeSkillLibrary:
    def __init__(self):
        self.skills = {}
        self._archived = []


class FakeWorldLedger:
    def __init__(self):
        self._user_profiles = {}


class FakeDecisionTrace:
    def __init__(self):
        self.cycle_id = 1
        self.decision_integrity = 0.95
        self.mission_drift = 0.05
        self.council_validated = True
        self.health_score = 0.9
        self.budget_consumed_ms = 25.0
        self.budget_total_ms = 50.0
        self.worlds_simulated = 10
        self.cycle_duration_ms = 45.0
        self.firewall_blocked = False
        self.selected_intent_type = "navigate"
        self.stream_activations = []
        self.council_signals = []
        self.strategic_options = []

    def to_dict(self):
        return {
            "cycle_id": self.cycle_id,
            "decision_integrity": self.decision_integrity,
            "mission_drift": self.mission_drift,
            "council_validated": self.council_validated,
            "health_score": self.health_score,
            "budget_consumed_ms": self.budget_consumed_ms,
            "budget_total_ms": self.budget_total_ms,
            "worlds_simulated": self.worlds_simulated,
            "cycle_duration_ms": self.cycle_duration_ms,
            "firewall_blocked": self.firewall_blocked,
            "stream_activations": self.stream_activations,
            "council_signals": self.council_signals,
            "strategic_options": self.strategic_options,
        }


# ── CheckpointManager Tests ──

def test_checkpoint_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = CheckpointManager(path=tmp, max_checkpoints=5)

        path = mgr.save(
            cycle=3,
            world_ledger=FakeWorldLedger(),
            skill_library=FakeSkillLibrary(),
            stream_calibrator=FakeCalibrator(),
            failure_ledger=FakeFailureLedger(),
            mission_policy=FakeMissionPolicy(),
            decision_trace=FakeDecisionTrace(),
        )
        assert path.exists()
        assert "checkpoint_0003" in str(path)

        loaded = mgr.load()
        assert loaded is not None
        assert loaded.cycle == 3
        assert loaded.decision_trace["cycle_id"] == 1


def test_checkpoint_multiple_cycles():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = CheckpointManager(path=tmp, max_checkpoints=3)

        for i in range(1, 6):
            cal = FakeCalibrator()
            mgr.save(i, FakeWorldLedger(), FakeSkillLibrary(), cal,
                     FakeFailureLedger(), FakeMissionPolicy())

        loaded = mgr.load()
        assert loaded is not None
        assert loaded.cycle == 5


def test_checkpoint_no_data():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = CheckpointManager(path=tmp)
        loaded = mgr.load()
        assert loaded is None


def test_checkpoint_clear():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = CheckpointManager(path=tmp)
        mgr.save(1, FakeWorldLedger(), FakeSkillLibrary(), FakeCalibrator(),
                 FakeFailureLedger(), FakeMissionPolicy())
        assert mgr.latest_path is not None
        mgr.clear()
        assert mgr.latest_path is None


def test_checkpoint_max_prunes_old():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = CheckpointManager(path=tmp, max_checkpoints=2)
        for i in range(1, 5):
            mgr.save(i, FakeWorldLedger(), FakeSkillLibrary(),
                     FakeCalibrator(), FakeFailureLedger(),
                     FakeMissionPolicy())

        checkpoints = list(Path(tmp).glob("checkpoint_*.json"))
        assert len(checkpoints) <= 2


# ── TelemetryCollector Tests ──

def test_telemetry_records_points():
    t = TelemetryCollector(max_points=100)
    t.record("di", 0.95, cycle=1)
    t.record("di", 0.90, cycle=2)
    assert len(t._points) == 2

    series = t.get_series("di")
    assert len(series) == 2


def test_telemetry_cycle_recording():
    t = TelemetryCollector()
    trace = FakeDecisionTrace()
    trace.stream_activations = [
        {"name": "ReflexStream", "activated": True, "cost_ms": 5.0},
        {"name": "PerceptionStream", "activated": True, "cost_ms": 8.0},
    ]
    trace.council_signals = [
        {"validator": "RealityValidator", "passed": True},
    ]

    t.record_cycle(1, trace)
    assert t.get_cycle_count() == 1
    assert len(t._points) > 5

    di_points = t.get_series("di")
    assert di_points[0].value == 0.95


def test_telemetry_summary():
    t = TelemetryCollector()
    t.record("di", 0.95, cycle=1)
    t.record("di", 0.85, cycle=2)
    t.record("di", 0.90, cycle=3)

    s = t.summary()
    assert s["cycles"] == 3
    assert "di" in s
    assert s["di"]["mean"] == 0.9
    assert s["di"]["latest"] == 0.9


def test_telemetry_summary_empty():
    t = TelemetryCollector()
    s = t.summary()
    assert s["cycles"] == 0


def test_telemetry_to_dict():
    t = TelemetryCollector()
    t.record("di", 0.95, cycle=1)
    d = t.to_dict()
    assert "summary" in d
    assert "recent_points" in d
    assert "history" in d
