"""
DecisionRecord tests — the portable decision-context artifact.

Verifies it composes existing types (DecisionTrace, IntentIR, EvidenceInfo,
ModelRealityGap), round-trips through JSON, renders the reasoning as markdown,
and — the point of the schema — revalidates from the SAME falsification
machinery the pipeline uses.
"""

import numpy as np
import pytest

from telos.core.types import DecisionTrace
from telos.intent_ir import IntentIR
from telos.core.handoff import (
    DecisionRecord, Alternative, Assumption, RevalidationCondition, RecordStatus,
)
from telos.world.evidence import EvidenceSource, ValidationStatus
from telos.world.epistemic import RealityGapTracker
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import ReflexStream
from telos.core.ledger.skill_library import SkillLibrary
from tests.core.conftest import MockSimulator


def _trace() -> DecisionTrace:
    """A minimal but realistic DecisionTrace with alternatives + a verdict."""
    return DecisionTrace(
        cycle_id=7, timestamp=123.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None,
        stream_activations=[],
        selected_intent=IntentIR(intent_type="seek_reward", confidence=0.8),
        selected_action=np.array([0.0, 1.0]),
        representation="spatial",
        budget_consumed_ms=10.0, budget_total_ms=100.0,
        worlds_simulated=12, cycle_duration_ms=11.0,
        decision_integrity=1.0, mission_drift=0.4,
        council_validated=True,
        strategic_options=[
            {"rank": 1, "score": 0.9, "metadata": {"intent_type": "seek_reward"}},
            {"rank": 2, "score": 0.5, "metadata": {"intent_type": "explore"}},
        ],
        produced_ctx_id="ctx-abc",
    )


def test_from_trace_derives_the_decision():
    rec = DecisionRecord.from_trace(_trace(), objective="reach the reward",
                                    owner="Prateek", mission="gridworld")
    assert rec.decision_id == "ctx-abc"
    assert rec.decision["intent_type"] == "seek_reward"
    assert rec.confidence == pytest.approx(0.8)
    assert rec.objective == "reach the reward"
    assert rec.owner == "Prateek"
    assert rec.provenance["cycle"] == 7
    assert rec.provenance["schema_version"] == "1.0"


def test_from_trace_marks_assumed_evidence_by_default():
    rec = DecisionRecord.from_trace(_trace())
    assert rec.evidence, "decision evidence must be recorded"
    # An untested simulation decision is ASSUMED — never silently MEASURED.
    assert rec.evidence[0].evidence.source == EvidenceSource.SIMULATION
    assert rec.evidence[0].evidence.validation_status == ValidationStatus.ASSUMED


def test_from_trace_records_alternatives_and_rejections():
    rec = DecisionRecord.from_trace(_trace())
    chosen = [a for a in rec.alternatives if a.chosen]
    rejected = [a for a in rec.alternatives if not a.chosen]
    assert chosen and chosen[0].option == "seek_reward"
    assert rejected and rejected[0].option == "explore"
    assert "below chosen" in (rejected[0].rejected_reason or "")


def test_round_trip_is_lossless():
    rec = DecisionRecord.from_trace(
        _trace(),
        assumptions=[Assumption(statement="terrain stays navigable")],
        constraints=["obstacle_near"],
        expected_consequences=["reward collected"],
        revalidation_conditions=[RevalidationCondition(
            condition="terrain becomes impassable", watches="world_model")],
    )
    assert DecisionRecord.from_dict(rec.to_dict()).to_dict() == rec.to_dict()


def test_markdown_preserves_reasoning_not_just_answer():
    rec = DecisionRecord.from_trace(
        _trace(),
        assumptions=[Assumption(statement="terrain stays navigable")],
        revalidation_conditions=[RevalidationCondition(
            condition="terrain becomes impassable", watches="world_model")],
    )
    md = rec.to_markdown()
    for section in ("## Decision", "## Evidence", "## Assumptions",
                    "## Alternatives considered", "## Revalidation conditions",
                    "## Validation"):
        assert section in md
    assert "seek_reward" in md
    assert "explore" in md  # the rejected alternative survives the handoff


def test_revalidation_is_executable_via_falsification():
    tr = RealityGapTracker()
    for _ in range(5):
        tr.record("m", np.array([0.0, 0.0]), np.array([10.0, 10.0]))  # huge gap
    gap = tr.model("m")
    assert gap.is_falsified

    rec = DecisionRecord.from_trace(
        _trace(),
        revalidation_conditions=[RevalidationCondition(
            condition="prediction holds", watches="m")],
    )
    rec.apply_reality_gap(gap, cycle=9)
    assert rec.status == RecordStatus.FALSIFIED
    assert rec.revalidation_conditions[0].status == ValidationStatus.FALSIFIED
    assert rec.revalidation_conditions[0].last_checked_cycle == 9


def test_to_knowledge_node_shape():
    rec = DecisionRecord.from_trace(_trace())
    node = rec.to_knowledge_node(domain="gridworld")
    assert node["domain"] == "gridworld"
    assert node["approach"] == "seek_reward"
    assert 0.0 <= node["outcome"] <= 1.0
    assert "decision_record" in node["tags"]


def test_builds_from_a_real_pipeline_trace():
    sim = MockSimulator()
    sim.initialize()
    pl = TelosV14Pipeline(PipelineConfig(
        simulator=sim, compute_budget_ms=200.0, state_dim=2,
        n_worlds=5, horizon=3, quality_threshold=0.3,
    ))
    pl.register_stream(ReflexStream(SkillLibrary()))
    result = pl.execute(np.array([1.0, 2.0]))
    rec = DecisionRecord.from_trace(result.decision_trace, objective="navigate",
                                    owner="Prateek")
    assert rec.decision_id
    assert rec.provenance["cycle"] >= 1
    assert rec.validation["decision_integrity"] is not None
    # Round-trips from a real trace too.
    assert DecisionRecord.from_dict(rec.to_dict()).decision_id == rec.decision_id


def test_markdown_shows_the_choice_explicitly():
    rec = DecisionRecord(
        decision_id="d",
        decision={"choice": "PostgreSQL", "intent_type": "adopt_postgres"},
    )
    md = rec.to_markdown()
    assert "**PostgreSQL**" in md            # the choice is the headline
    assert "(`adopt_postgres`)" in md        # the intent type is shown alongside
    assert "**adopt_postgres**" not in md    # not the other way round


def test_markdown_falls_back_to_intent_type_without_choice():
    rec = DecisionRecord(decision_id="d", decision={"intent_type": "reflex"})
    assert "**reflex**" in rec.to_markdown()


def test_apply_reality_gap_can_target_a_single_condition():
    tr = RealityGapTracker()
    for _ in range(5):
        tr.record("m", np.array([0.0, 0.0]), np.array([10.0, 10.0]))
    gap = tr.model("m")
    rec = DecisionRecord.from_trace(
        _trace(),
        revalidation_conditions=[
            RevalidationCondition(condition="write volume exceeds 10k events/s"),
            RevalidationCondition(condition="multi-region writes required"),
        ],
    )
    rec.apply_reality_gap(gap, cycle=42, only=lambda c: "write volume" in c.condition)
    assert rec.revalidation_conditions[0].status == ValidationStatus.FALSIFIED
    assert rec.revalidation_conditions[1].status == ValidationStatus.UNVALIDATED
    assert rec.status == RecordStatus.FALSIFIED
    assert rec.revalidation_conditions[0].last_checked_cycle == 42
