"""Honest contract tests for telos/core/streams/inquiry_stream.py."""

import numpy as np

from telos.core.ledger.skill_library import SkillLibrary
from telos.core.streams.inquiry_stream import InquiryStream
from telos.world.world import World


def _world(metadata=None, state=None):
    return World(state=np.array(state if state is not None else [1.0, 2.0]),
                 metadata=metadata or {})


def test_inquiry_priority_and_cost():
    i = InquiryStream(SkillLibrary())
    assert i.priority == 0.8
    assert i.estimated_cost_ms == 4.0


def test_inquiry_zero_uncertainty_still_generates_default():
    i = InquiryStream(SkillLibrary())
    ir = i.process(_world({}))
    assert ir.intent_type == "inquiry"
    assert ir.confidence == 0.0
    assert ir.params["candidate_count"] >= 1
    assert ir.params["candidate_questions"][-1]["id"] == "default_navigate"


def test_inquiry_builds_question_context():
    i = InquiryStream(SkillLibrary())
    w = _world({"U_W": 0.6, "U_I": 0.2, "U_O": 0.4})
    ir = i.process(w)
    ctx = ir.params["question_context"]
    assert ctx["U_W"] == 0.6
    assert ctx["U_I"] == 0.2
    assert ctx["U_O"] == 0.4
    assert "composite_uncertainty" in ctx
    assert ctx["council_signal_count"] == 0


def test_inquiry_generates_candidates_per_uncertainty():
    i = InquiryStream(SkillLibrary())
    w = _world({"U_W": 0.6, "U_I": 0.7, "U_O": 0.8})
    ir = i.process(w)
    ids = [c["id"] for c in ir.params["candidate_questions"]]
    assert "explore_terrain" in ids
    assert "recalibrate_identity" in ids
    assert "resolve_disagreement" in ids
    assert "default_navigate" in ids


def test_inquiry_counts_council_blockers():
    i = InquiryStream(SkillLibrary())
    w = _world({"U_O": 0.5, "council_signals": [
        {"passed": False}, {"passed": True}, {"passed": False},
    ]})
    ir = i.process(w)
    ctx = ir.params["question_context"]
    assert ctx["council_signal_count"] == 3
    assert ctx["council_blockers"] == 2


def test_inquiry_confidence_scales_with_composite():
    i = InquiryStream(SkillLibrary())
    low = i.process(_world({"U_W": 0.1, "U_I": 0.1, "U_O": 0.1}))
    high = i.process(_world({"U_W": 1.0, "U_I": 1.0, "U_O": 1.0}))
    assert high.confidence > low.confidence
    assert high.confidence <= 1.0


def test_inquiry_metadata_flags_active():
    i = InquiryStream(SkillLibrary())
    ir = i.process(_world({"U_W": 0.6, "U_I": 0.6, "U_O": 0.0}))
    assert ir.metadata["stream"] == "inquiry"
    assert ir.metadata["inquiry_active"] is True
    assert ir.metadata["candidate_count"] >= 1


def test_inquiry_state_norm_computed_from_state():
    i = InquiryStream(SkillLibrary())
    ir = i.process(_world({}, state=[3.0, 4.0]))
    assert ir.params["question_context"]["state_norm"] == 5.0


def test_inquiry_property_accessors():
    i = InquiryStream(SkillLibrary())
    assert i.inquiry_active is False
    i.inquiry_active = True
    assert i.inquiry_active is True

    assert i.last_question is None
    i.last_question = {"id": "q1"}
    assert i.last_question == {"id": "q1"}

    assert i.last_omega == 0.0
    i.last_omega = 0.77
    assert i.last_omega == 0.77


def test_generate_candidates_includes_default_option():
    i = InquiryStream(SkillLibrary())
    c = i._generate_candidates(0.0, 0.0, 0.0, [])
    assert len(c) == 1
    assert c[0]["id"] == "default_navigate"
    assert c[0]["type"] == "proceed"