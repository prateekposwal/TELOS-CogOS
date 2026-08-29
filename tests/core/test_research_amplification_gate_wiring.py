"""Wiring tests: Research Amplification Gate as the pre-PERCEIVE pipeline stage.

The gate module's OWN contract lives in test_research_amplification_gate.py
(9 tests, untouched). These tests lock the WIRING into TelosV14Pipeline:

  - default research_gate knob ("off"/"legacy") leaves existing pipeline
    behavior byte-identical (no gate state, no block, no trace mutation);
  - report mode attaches the AmplificationReport verdict to the DecisionTrace
    truthfully — PASS when a caller attached 7/7-dimension external grounding,
    honest LEFT when it did not (and reporting never blocks);
  - require mode marks a run LEFT BEFORE any stream/simulation consumes the
    brief when 7/7-dimension external grounding is missing (the structural
    bounded-evidence-mode fix: never a silent pass, never fabricated
    grounding) and lets a fully-grounded run proceed.
"""

import os
import numpy as np
import pytest

from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS, GOAL
from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.research.amplification_gate import (
    MANDATORY_DIMENSIONS,
    EvidenceClaim,
    EvidenceSource,
    SourceClassification,
)
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    EvidenceProvenanceValidator,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine


def _build(gate_mode, tmp_path):
    """REAL pipeline (GridWorld sim + streams + validators) for gate wiring.

    Args:
        gate_mode: research_gate knob value ("off"/"legacy"/"report"/"require"
            or None = config default).
        tmp_path: pytest tmp dir for checkpoint/knowledge/ledger files.
    """
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    cfg = dict(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=8, horizon=5,
        checkpoint_path=str(tmp_path / "cp"),
        knowledge_path=str(tmp_path / "kg.json"),
        ledger_path=str(tmp_path / "ld.json"),
        identity_path=str(tmp_path / "id.json"),
        pattern_path=str(tmp_path / "pt.json"),
        deterministic_seed=42,
    )
    if gate_mode is not None:
        cfg["research_gate"] = gate_mode
    pipe = TelosV14Pipeline(PipelineConfig(**cfg))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipe, "_theory_builder", None))]:
        pipe.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipe.register_validator(v)
    return pipe


def _full_evidence():
    """External sources + one grounded claim per mandatory dimension."""
    sources = [
        EvidenceSource(source_id="A", name="LI News — Buying Time: Longevity Moves Into Real Estate",
                       venue="Longevity Investors",
                       classification=SourceClassification.SECONDARY),
        EvidenceSource(source_id="B", name="Longevity Book / Deep Knowledge Group",
                       venue="longevity-book.com",
                       classification=SourceClassification.PRIMARY),
    ]
    claims = [
        EvidenceClaim(source_id="A" if i % 2 == 0 else "B",
                      claim=f"grounded claim covering {dim}", dimension=dim)
        for i, dim in enumerate(MANDATORY_DIMENSIONS)
    ]
    return sources, claims


def _run(pipe, n_cycles=2, state=None):
    state = np.array([0.0, 0.0]) if state is None else state
    results = []
    for _ in range(n_cycles):
        r = pipe.execute(state, user_name="Prateek")
        results.append(r)
        act = r.decision_trace.selected_action
        if act is not None:
            state = pipe.config.simulator.transition(state, act)
    return results


# ── default / legacy = byte-identical ───────────────────────────────────────

def test_default_off_pipeline_unaffected(tmp_path):
    """Default config: no gate state, no gate block, trace carries nothing."""
    pipe = _build(None, tmp_path)
    results = _run(pipe, n_cycles=3)
    for r in results:
        assert r.decision_trace.amplification_report is None
        assert r.governance_blocked_by is None
        assert "research" not in (r.decision_trace.to_dict().get("amplification_report") or {})
    # the agent actually moved: the pipeline is fully live
    assert any(r.decision_trace.selected_action is not None for r in results)


def test_legacy_alias_matches_off(tmp_path):
    pipe = _build("legacy", tmp_path)
    assert pipe.research_gate is None
    results = _run(pipe, n_cycles=2)
    assert all(r.decision_trace.amplification_report is None for r in results)
    assert all(r.governance_blocked_by is None for r in results)


def test_default_is_byte_identical_to_explicit_off(tmp_path):
    """Default and explicit 'off' produce identical semantic traces."""
    def semantic(r):
        t = r.decision_trace
        return (
            round(t.decision_integrity, 6), round(t.mission_drift, 6),
            t.selected_intent.intent_type if t.selected_intent else None,
            None if t.selected_action is None else t.selected_action.tolist(),
            t.council_validated, t.firewall_blocked,
        )
    a = _run(_build(None, tmp_path / "a"), n_cycles=3)
    b = _run(_build("off", tmp_path / "b"), n_cycles=3)
    assert [semantic(r) for r in a] == [semantic(r) for r in b]


# ── report mode ─────────────────────────────────────────────────────────────

def test_report_mode_grounded_evidence_attaches_pass_verdict(tmp_path):
    pipe = _build("report", tmp_path)
    pipe.attach_research_evidence(*_full_evidence())
    results = _run(pipe, n_cycles=2)
    for r in results:
        rep = r.decision_trace.amplification_report
        assert rep is not None
        assert rep["passed"] is True
        assert rep["run_status"] == "DONE"
        assert rep["missing_dimensions"] == []
        assert rep["total_external_sources"] == 2
        assert r.governance_blocked_by is None  # report mode never blocks
        # surfaces truthfully in the serialized trace
        assert r.decision_trace.to_dict()["amplification_report"]["passed"] is True


def test_report_mode_without_evidence_attaches_honest_left(tmp_path):
    """report + zero grounding: honest LEFT verdict attached, never a silent
    pass, and reporting never blocks the run."""
    pipe = _build("report", tmp_path)
    results = _run(pipe, n_cycles=2)
    for r in results:
        rep = r.decision_trace.amplification_report
        assert rep is not None
        assert rep["passed"] is False
        assert rep["run_status"] == "LEFT"
        assert set(rep["missing_dimensions"]) == set(MANDATORY_DIMENSIONS)
        assert r.governance_blocked_by is None  # advisory report only


# ── require mode ────────────────────────────────────────────────────────────

def test_require_mode_zero_grounding_is_left_before_streams(tmp_path):
    pipe = _build("require", tmp_path)
    r = _run(pipe, n_cycles=1)[0]
    t = r.decision_trace
    # honestly LEFT at the gate: governance-blocked by the gate's own reason
    assert r.governance_blocked_by is not None
    assert r.governance_blocked_by.startswith("research_amplification_left:")
    rep = t.amplification_report
    assert rep["passed"] is False
    assert rep["run_status"] == "LEFT"
    assert set(rep["missing_dimensions"]) == set(MANDATORY_DIMENSIONS)
    # no stream / simulation consumed the brief
    assert t.selected_intent is None
    assert t.worlds_simulated == 0
    assert t.to_dict()["amplification_report"]["run_status"] == "LEFT"


def test_require_mode_with_full_grounding_passes(tmp_path):
    pipe = _build("require", tmp_path)
    pipe.attach_research_evidence(*_full_evidence())
    results = _run(pipe, n_cycles=2)
    for r in results:
        rep = r.decision_trace.amplification_report
        assert rep is not None and rep["passed"] is True
        assert rep["run_status"] == "DONE"
        assert r.governance_blocked_by is None  # fully grounded -> proceeds


def test_require_mode_with_coverage_gap_is_left(tmp_path):
    """ONE uncovered mandatory dimension -> LEFT with the exact gap named."""
    pipe = _build("require", tmp_path)
    sources, claims = _full_evidence()
    claims = [c for c in claims if c.dimension != MANDATORY_DIMENSIONS[-1]]
    pipe.attach_research_evidence(sources, claims)
    r = _run(pipe, n_cycles=1)[0]
    assert r.governance_blocked_by is not None
    assert r.governance_blocked_by.startswith("research_amplification_left:")
    rep = r.decision_trace.amplification_report
    assert rep["passed"] is False
    assert rep["missing_dimensions"] == [MANDATORY_DIMENSIONS[-1]]
    assert r.decision_trace.worlds_simulated == 0


# ── attach API discipline ───────────────────────────────────────────────────

def test_attach_research_evidence_requires_enabled_gate(tmp_path):
    pipe = _build(None, tmp_path)
    with pytest.raises(ValueError):
        pipe.attach_research_evidence(*_full_evidence())


def test_attach_research_evidence_validates_source_before_claim(tmp_path):
    pipe = _build("report", tmp_path)
    pipe.attach_research_evidence(
        [EvidenceSource(source_id="A", name="x", venue="y")],
        [],
    )
    with pytest.raises(ValueError):
        pipe.attach_research_evidence([], [EvidenceClaim(
            source_id="UNKNOWN", claim="orphan", dimension=MANDATORY_DIMENSIONS[0])])
    # nothing partial slipped in
    assert pipe.research_gate.claims == []
