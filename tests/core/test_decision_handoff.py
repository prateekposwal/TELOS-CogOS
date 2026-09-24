"""
Context-handoff tests — DecisionRecorder emission + the end-to-end handoff.

The load-bearing test is `test_end_to_end_handoff_and_revalidation`:

    TELOS decision → DecisionRecord → JSON → second context → reconstruct
    decision + why → reality gap changes → record revalidates/falsifies

That is the loop that makes the "preserve the reasoning, not just the answer"
claim real.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from telos.core.handoff import (
    DecisionRecorder, DecisionRecord, RecordStatus,
    DecisionStore, AssumptionRegistry,
)
from telos.world.evidence import ValidationStatus
from telos.world.epistemic import RealityGapTracker


def _ctx(intent_type="reflex", *, validated=True, escalation=False,
         firewall=False, action=True, cycle=1, owner="Prateek"):
    """A minimal post-ACT context stub."""
    verdict = SimpleNamespace(validated=validated, escalation_requested=escalation,
                              decision_integrity=1.0, mission_drift=0.2,
                              blocking_validator=None if validated else "RealityValidator")
    return SimpleNamespace(
        cycle_count=cycle,
        state=np.array([1.0, 2.0]),
        user_name=owner,
        selected_intent=SimpleNamespace(intent_type=intent_type, confidence=0.8, params={}),
        selected_action=np.array([0.0, 1.0]) if action else None,
        strategic_options_data=[{"rank": 1, "score": 0.9,
                                 "metadata": {"intent_type": intent_type}}],
        verdict=verdict,
        firewall_blocked=firewall,
        representation="spatial",
        domain_facts=SimpleNamespace(constraints=["obstacle_near"], domain="gridworld"),
    )


def _pipeline_stub(mission="gridworld navigation"):
    return SimpleNamespace(config=SimpleNamespace(mission_name=mission))


# ── Policy ───────────────────────────────────────────────────────────────────

def test_meaningful_on_new_committed_decision():
    rec = DecisionRecorder()
    assert rec.is_meaningful(_ctx("reflex")) is True
    rec.observe(_pipeline_stub(), _ctx("reflex"))          # record it
    assert rec.is_meaningful(_ctx("reflex")) is False      # same type -> not new
    assert rec.is_meaningful(_ctx("explore")) is True      # new type -> new decision


def test_meaningful_on_new_governance_signature_only():
    rec = DecisionRecorder()
    blocked = _ctx("reflex", validated=False, action=False)
    assert rec.is_meaningful(blocked) is True
    rec.observe(_pipeline_stub(), blocked)
    # same refusal signature again -> not a new decision
    assert rec.is_meaningful(_ctx("reflex", validated=False, action=False)) is False
    # a different governance signature -> meaningful
    assert rec.is_meaningful(_ctx("reflex", escalation=True)) is True


def test_not_meaningful_when_no_intent_and_no_event():
    ctx = _ctx("reflex"); ctx.selected_intent = None; ctx.selected_action = None
    assert DecisionRecorder().is_meaningful(ctx) is False


# ── Recorder ─────────────────────────────────────────────────────────────────

def test_recorder_emits_new_decisions_and_skips_repeats():
    rec = DecisionRecorder()
    pl = _pipeline_stub()
    assert rec.observe(pl, _ctx("reflex", cycle=1)) is not None
    assert rec.observe(pl, _ctx("reflex", cycle=2)) is None       # repeat -> skipped
    assert rec.observe(pl, _ctx("explore", cycle=3)) is not None  # new -> emitted
    assert rec.stats()["emitted"] == 2
    assert rec.stats()["skipped"] == 1
    assert rec.latest().decision["intent_type"] == "explore"


def test_recorder_is_bounded():
    rec = DecisionRecorder(max_records=3)
    pl = _pipeline_stub()
    for i, it in enumerate(["a", "b", "c", "d", "e"]):
        rec.observe(pl, _ctx(it, cycle=i + 1))
    assert len(rec.records) == 3
    assert [r.decision["intent_type"] for r in rec.records] == ["c", "d", "e"]


def test_recorder_disabled_is_noop():
    rec = DecisionRecorder(enabled=False)
    assert rec.observe(_pipeline_stub(), _ctx("reflex")) is None
    assert rec.records == []


def test_recorder_marks_unspecified_caller_fields():
    rec = DecisionRecorder()
    r = rec.observe(_pipeline_stub(), _ctx("reflex"))
    assert "assumptions" in r.provenance["unspecified"]
    assert "expected_consequences" in r.provenance["unspecified"]
    # objective comes from the declared mission, not invented
    assert r.objective == "gridworld navigation"
    # a system-derived revalidation condition is present (the real check)
    assert r.revalidation_conditions
    assert r.revalidation_conditions[0].watches == "world_model"


# ── The end-to-end handoff ───────────────────────────────────────────────────

def _gridworld_pipeline(tmp_path):
    """A real GridWorld pipeline (has an adapter, so actions are emitted)."""
    from telos.cli import _build_gridworld_pipeline
    return _build_gridworld_pipeline(str(tmp_path / "cp"))


def test_end_to_end_handoff_and_revalidation(tmp_path):
    # 1. TELOS makes decisions.
    from telos.tools.bench_loop import drive
    pl = _gridworld_pipeline(tmp_path)
    for _ in drive(pl, cycles=20, user_name="handoff_test"):
        pass

    records = pl.decision_recorder.records
    assert records, "the pipeline must emit at least one DecisionRecord"
    original = records[-1]

    # 2. Serialize and hand off (a second context reads only the JSON).
    path = tmp_path / "decision.json"
    path.write_text(original.to_json())
    handed = DecisionRecord.from_dict(json.loads(path.read_text()))

    # 3. The second context reconstructs the decision AND the why.
    assert handed.decision["intent_type"] == original.decision["intent_type"]
    assert handed.evidence and handed.evidence[0].evidence.source.value == "SIMULATION"
    assert handed.alternatives, "the rejected alternatives survive the handoff"
    assert handed.provenance["schema_version"] == "1.0"

    # Deterministic: two consumers of the same JSON agree.
    assert DecisionRecord.from_dict(json.loads(path.read_text())).to_dict() == handed.to_dict()

    # 4. Reality changes and the record revalidates (executably, not by re-reading).
    assert handed.status == RecordStatus.OPEN
    tr = RealityGapTracker()
    for _ in range(5):
        tr.record("m", np.array([0.0, 0.0]), np.array([10.0, 10.0]))  # prediction falsified
    gap = tr.model("m")
    assert gap.is_falsified
    handed.apply_reality_gap(gap, cycle=99)
    assert handed.status == RecordStatus.FALSIFIED
    assert handed.revalidation_conditions[0].status == ValidationStatus.FALSIFIED
    assert handed.revalidation_conditions[0].last_checked_cycle == 99


def test_recorder_binds_assumption_refs_from_registry():
    reg = AssumptionRegistry({"G1": "peak writes < 10k/s"})
    reg.bind("reflex", ["G1"])
    rec = DecisionRecorder(registry=reg)
    record = rec.observe(_pipeline_stub(), _ctx("reflex"))
    assert record.assumption_refs == ["G1"]
    # an unbound intent type yields no refs
    assert rec.observe(_pipeline_stub(), _ctx("explore")).assumption_refs == []


def test_recorder_bind_callable_overrides_registry():
    reg = AssumptionRegistry({"G1": "a", "G2": "b"})
    reg.bind("reflex", ["G1"])
    rec = DecisionRecorder(registry=reg,
                           bind=lambda it, dom: ["G2"] if it == "reflex" else [])
    assert rec.observe(_pipeline_stub(), _ctx("reflex")).assumption_refs == ["G2"]


def test_recorder_persists_registry_and_feeds_graph(tmp_path):
    store = DecisionStore(str(tmp_path))
    reg = AssumptionRegistry({"G1": "peak writes < 10k/s"})
    reg.bind("reflex", ["G1"])
    rec = DecisionRecorder(store=store, registry=reg)
    rec.observe(_pipeline_stub(), _ctx("reflex", cycle=1))
    # registry persisted alongside the records
    assert store.load_registry().refs_for("reflex") == ["G1"]
    # the live record feeds the executable graph
    assert store.graph().affected_decisions("G1") == ["cycle-1-reflex"]


def test_pipeline_exposes_records_and_reflection(tmp_path):
    from telos.tools.bench_loop import drive
    pl = _gridworld_pipeline(tmp_path)
    for _ in drive(pl, cycles=20, user_name="handoff_test"):
        pass
    # The pipeline exposes records as plain dicts.
    records = pl.decision_records()
    assert isinstance(records, list) and records
    assert records[0]["schema_version"] == "1.0"
    # The recorder emitted meaningfully, not once per cycle.
    stats = pl.decision_recorder.stats()
    assert stats["emitted"] <= stats["emitted"] + stats["skipped"]
    assert stats["skipped"] > 0, "repeated intents must be skipped, not recorded"
