"""
DecisionRecord schema tests — Jev habits: typed/closed outputs, no malformed
results. The store refuses to persist an ill-formed record; the recorder attaches
the empirically recalibrated confidence.
"""

import numpy as np
import pytest

from telos.core.handoff import (
    DecisionRecord, DecisionStore, DecisionRecorder,
    validate_record, is_valid, assert_valid, schema_dict, SchemaError,
)
from telos.core.calibration import CalibrationTracker


def _good():
    return DecisionRecord(decision_id="D1", decision={"intent_type": "reflex"},
                          confidence=0.8)


def test_valid_record_passes():
    assert validate_record(_good()) == []
    assert is_valid(_good()) is True


def test_missing_decision_type_is_invalid():
    r = DecisionRecord(decision_id="D1", decision={})
    errs = validate_record(r)
    assert any("intent_type" in e or "choice" in e for e in errs)


def test_confidence_range_enforced():
    r = _good(); r.confidence = 1.5
    assert any("confidence" in e for e in validate_record(r))
    r2 = _good(); r2.calibrated_confidence = -0.1
    assert any("calibrated_confidence" in e for e in validate_record(r2))


def test_guarded_deps_must_be_subset_of_depends_on():
    r = _good(); r.depends_on = ["D0"]; r.guarded_deps = ["D9"]
    assert any("guarded_deps" in e for e in validate_record(r))
    r.guarded_deps = ["D0"]
    assert validate_record(r) == []


def test_store_rejects_malformed_record(tmp_path):
    store = DecisionStore(str(tmp_path))
    with pytest.raises(SchemaError):
        store.write(DecisionRecord(decision_id="D1", decision={}))
    assert store.count() == 0
    # a well-formed record is accepted, and can bypass validation explicitly
    store.write(_good())
    assert store.count() == 1
    store.write(DecisionRecord(decision_id="D2", decision={}), validate=False)
    assert store.count() == 2


def test_schema_dict_has_closed_enums():
    s = schema_dict()
    assert set(["OPEN", "VALIDATED", "FALSIFIED", "SUPERSEDED"]) <= set(s["closed_enums"]["status"])
    assert "SIMULATION" in s["closed_enums"]["evidence.source"]
    assert "MEASURED" in s["closed_enums"]["validation_status"]


def test_recorder_attaches_calibrated_confidence():
    tracker = CalibrationTracker(min_samples=1, min_bin_samples=1)
    for _ in range(10):
        tracker.record(0.8, 0.0)          # claims 0.8, never right -> calibrated 0.0
    pipeline = type("P", (), {})()
    pipeline.config = type("C", (), {"mission_name": "m"})()
    pipeline._calibration_tracker = tracker
    ctx = type("X", (), {})()
    ctx.cycle_count = 1
    ctx.state = np.array([0.0, 0.0])
    ctx.user_name = "tester"
    ctx.selected_intent = type("I", (), {"intent_type": "reflex", "confidence": 0.8, "params": {}})()
    ctx.selected_action = np.array([0.0, 1.0])
    ctx.strategic_options_data = []
    ctx.verdict = type("V", (), {"validated": True, "escalation_requested": False,
                                 "decision_integrity": 1.0, "mission_drift": 0.0,
                                 "blocking_validator": None})()
    ctx.firewall_blocked = False
    ctx.representation = "spatial"
    ctx.domain_facts = type("F", (), {"constraints": [], "domain": "gridworld"})()

    rec = DecisionRecorder().observe(pipeline, ctx)
    assert rec.confidence == 0.8
    assert rec.calibrated_confidence == 0.0   # the honest number, not the claim
