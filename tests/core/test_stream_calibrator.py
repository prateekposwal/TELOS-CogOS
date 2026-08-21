"""
Contract tests for telos/core/infra_manager/stream_calibrator.py — StreamCalibrator.

Evidence-weighted influence tracking for cognitive streams. Tests assert REAL
behavior: calibration recompute, forced exploration (stuck detection), waste
tracking, experience-map calibration, and influence accessors.
"""

import numpy as np

from telos.core.runtime import PipelineResult, PipelinePhase, DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.phases.base import StreamActivation
from telos.core.infra_manager.stream_calibrator import (
    StreamCalibrator, StreamCalibration, ExperienceMap, ExperienceEntry,
)


def _trace(cycle, stream_name, intent_type, conf, md, selected=True,
           world_state=None, council=False, semantic=None):
    intent = IntentIR(intent_type, confidence=conf)
    sa = StreamActivation(
        stream_name=stream_name, priority=1.0, activated=True,
        intent=intent, cost_ms=10.0, budget_remaining_ms=50.0,
    )
    sel_intent = intent if selected else None
    council_signals = [{"passed": False}] if council else []
    ts = DecisionTrace(
        cycle_id=cycle, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]) if world_state is None else world_state,
        domain_facts=None,
        stream_activations=[sa],
        selected_intent=sel_intent,
        selected_action=np.array([0.1]),
        representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0,
        health_score=0.9, decision_integrity=max(0.1, 1.0 - md),
        mission_drift=md, council_validated=not council,
        council_signals=council_signals,
    )
    return ts


def _result(trace):
    return PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=trace)


def test_uncalibrated_stream_defaults():
    cal = StreamCalibrator()
    assert cal.get_influence_weight("unknown") == 1.0
    assert cal.get_calibration("unknown") is None
    assert cal.get_evidence_weighted_influence("unknown") == {
        "evidence": 0.0, "confidence": 0.5, "reliability": 0.5, "influence_weight": 1.0,
    }


def test_empty_stream_uncertainties():
    cal = StreamCalibrator()
    assert cal.get_stream_uncertainties() == {}


def test_observe_none_trace_is_noop():
    cal = StreamCalibrator()
    cal.observe(PipelineResult(None, 0.9, PipelinePhase.COMPLETE, decision_trace=None))
    assert cal.stats["calibrated_streams"] == 0


def test_observe_selected_low_drift_counts_accurate():
    cal = StreamCalibrator()
    trace = _trace(1, "ReflexStream", "reflex", 0.8, md=0.2)
    cal.observe(_result(trace))
    c = cal.get_calibration("ReflexStream")
    assert c is not None
    assert c.total_calls == 1
    assert c.accurate_calls == 1
    assert c.consecutive_not_selected == 0
    assert c.evidence_score > 0.0
    assert 0.0 <= c.influence_weight <= 2.0


def test_observe_selected_high_drift_not_accurate():
    cal = StreamCalibrator()
    trace = _trace(1, "S", "x", 0.8, md=6.0)
    cal.observe(_result(trace))
    c = cal.get_calibration("S")
    assert c.total_calls == 1
    assert c.accurate_calls == 0
    assert c.accuracy == 0.0


def test_observe_non_selected_gets_inertia_boost():
    cal = StreamCalibrator()
    # stream B activated but not selected -> this stream is not in stream_activations here...
    # Build trace with stream A selected and stream B in activations as non-selected
    ia = IntentIR("a", confidence=0.8)
    ib = IntentIR("b", confidence=0.8)
    sa = StreamActivation(stream_name="A", priority=1.0, activated=True,
                          intent=ia, cost_ms=10.0, budget_remaining_ms=50.0)
    sb = StreamActivation(stream_name="B", priority=1.0, activated=True,
                          intent=ib, cost_ms=10.0, budget_remaining_ms=50.0)
    trace = DecisionTrace(
        cycle_id=1, timestamp=0.0, world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[sa, sb],
        selected_intent=ia, selected_action=np.array([0.1]),
        representation="cartesian", budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0, health_score=0.9,
        decision_integrity=0.9, mission_drift=0.2,
    )
    cal.observe(_result(trace))
    cb = cal.get_calibration("B")
    assert cb is not None
    assert cb.consecutive_not_selected == 1
    assert cb.influence_weight > 1.0  # boosted


def test_dominant_stream_requires_stuck_dominance_cycles():
    cal = StreamCalibrator()
    assert cal.dominant_stream is None
    # manually push selection history of one stream 10 times
    cal._selection_history = ["S"] * 10
    assert cal.dominant_stream == "S"


def test_dominant_stream_not_dominant_when_mixed():
    cal = StreamCalibrator()
    cal._selection_history = ["S"] * 5 + ["T"] * 5
    assert cal.dominant_stream is None


def test_is_stuck_false_when_no_history():
    assert StreamCalibrator().is_stuck() is False


def test_forced_exploration_stream_none_when_not_stuck():
    cal = StreamCalibrator()
    assert cal.forced_exploration_stream() is None


def test_experience_map_confidence():
    em = ExperienceMap("s")
    assert em.get_confidence("ctx") == (0.5, 1.0)
    em.update("ctx", 0.9)
    mean, unc = em.get_confidence("ctx")
    assert abs(mean - 0.9) < 1e-9
    assert abs(unc - 0.2) < 1e-9  # 0.2/sqrt(1)


def test_experience_map_tracks_mean_across_updates():
    em = ExperienceMap("s")
    em.update("ctx", 0.8)
    em.update("ctx", 0.4)
    mean, _ = em.get_confidence("ctx")
    assert abs(mean - 0.6) < 1e-9


def test_get_calibrated_confidence_default_stream():
    cal = StreamCalibrator()
    assert cal.get_calibrated_confidence("newstream", "ctx") == (0.5, 1.0)


def test_record_waste_penalty():
    cal = StreamCalibrator()
    # drive waste ratio above 0.5 with total > 20
    cal.record_waste("S", 16.0)
    old_weight = cal.get_calibration("S").influence_weight
    cal.record_waste("S", 16.0)  # total 32, waste 32 -> ratio 1.0
    c = cal.get_calibration("S")
    assert c.waste_cost_ms == 32.0
    assert c.total_cost_ms == 32.0
    assert c.influence_weight < old_weight


def test_record_escape_telemetry():
    cal = StreamCalibrator()
    cal.record_escape(5, "a", "b")
    assert cal._escape_count == 1
    assert cal._last_escape_cycle == 5
    assert cal._last_escape_from == "a"
    assert cal._last_escape_to == "b"
    assert cal.stats["local_optima_escapes"] == 1


def test_update_experience_map_and_uncertainties():
    cal = StreamCalibrator()
    cal.update_experience_map("S", "ctx", 0.9)
    unc = cal.get_stream_uncertainties()
    assert "S" in unc
    assert unc["S"] < 1.0


def test_apply_council_block_penalty_reduces_influence():
    cal = StreamCalibrator()
    c = cal._get_or_create("S")
    c.total_calls = 10
    c.council_blocks = 8  # 0.8 > 0.3
    old = c.influence_weight
    cal.apply_council_block_penalty()
    assert c.influence_weight < old


def test_council_block_counted_in_observe():
    cal = StreamCalibrator()
    trace = _trace(1, "S", "x", 0.8, md=0.2, council=True)
    cal.observe(_result(trace))
    assert cal.get_calibration("S").council_blocks == 1


def test_stats_shape():
    cal = StreamCalibrator()
    stats = cal.stats
    for key in ["calibrated_streams", "total_calibrations", "dominant_stream",
                "is_stuck", "local_optima_escapes", "last_escape",
                "selection_history", "calibrations"]:
        assert key in stats
