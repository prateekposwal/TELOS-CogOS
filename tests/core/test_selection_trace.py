"""
Selection instrumentation + A/B policy — non-behavioral by default.

Phase 1 pinned: recording WHY an intent won must not change WHICH intent wins.
These tests lock the instrument shape, the inquiry classifier, the optional
mission-progress hook, and the config-gated policy (control = byte-identical).
"""
from types import SimpleNamespace

import numpy as np

from telos.core.decision.selection_trace import (
    build_selection_decision, is_inquiry_intent, mission_progress,
    SelectionDecision, IntentScoreBreakdown,
)
from telos.intent_ir import IntentIR


def _ctx(**kw):
    base = dict(
        cycle_count=7, state=np.zeros(2), intents=[],
        selected_intent=None, inquiry_blend=0.0, inquiry_omega_value=0.1,
        curiosity_state={"curiosity_level": 0.2},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_is_inquiry_intent_classifies_by_type_and_stream():
    assert is_inquiry_intent(IntentIR(intent_type="blended_inquiry")) is True
    assert is_inquiry_intent(IntentIR(intent_type="curiosity_explore")) is True
    assert is_inquiry_intent(IntentIR(intent_type="mystery",
                                      metadata={"stream": "inquiry"})) is True
    assert is_inquiry_intent(IntentIR(intent_type="plan_trajectory")) is False


def test_mission_progress_none_without_hook():
    p = SimpleNamespace()
    assert mission_progress(p, _ctx(), IntentIR(intent_type="x")) is None


def test_mission_progress_uses_hook():
    p = SimpleNamespace(_mission_progress_fn=lambda state, intent: 0.42)
    assert mission_progress(p, _ctx(), IntentIR(intent_type="x")) == 0.42


def test_build_selection_decision_shape_and_regime():
    si = IntentIR(intent_type="blended_inquiry")
    ctx = _ctx(selected_intent=si, inquiry_blend=0.5,
               intents=[(si, 0.8), (IntentIR(intent_type="plan_trajectory"), 0.7)])
    p = SimpleNamespace(config=SimpleNamespace(selection_policy="control"))
    d = build_selection_decision(ctx, p)
    assert d["regime"] == "blended"
    assert d["selected_type"] == "blended_inquiry"
    types = {c["intent_type"] for c in d["candidates"]}
    assert {"blended_inquiry", "plan_trajectory"} <= types
    # serializes to plain JSON-ready types
    assert set(d) == {
        "cycle", "regime", "omega_value", "omega_threshold", "blend",
        "blend_effective", "curiosity_level", "selection_policy",
        "selected_type", "candidates"}
    for c in d["candidates"]:
        assert isinstance(c, dict)
        assert "mission_progress" in c and "is_inquiry" in c


def test_regime_boundaries():
    si = IntentIR(intent_type="x")
    p = SimpleNamespace(config=SimpleNamespace(selection_policy="control"))
    assert build_selection_decision(_ctx(selected_intent=si, inquiry_blend=0.0), p)["regime"] == "action"
    assert build_selection_decision(_ctx(selected_intent=si, inquiry_blend=0.5), p)["regime"] == "blended"
    assert build_selection_decision(_ctx(selected_intent=si, inquiry_blend=1.0), p)["regime"] == "inquiry"
