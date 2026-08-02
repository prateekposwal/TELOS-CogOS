"""
Tests for the Scale-Invariance Principle — deliberate recursion in TELOS.

Proves:
  - The canonical deliberation law (phase sequence) matches the runtime.
  - The pipeline runs at ≥2 scales (macro / meso / micro) with identical
    phase structure and identical verified axiom set at each scale.
  - The RecursionLedger records every recursive invocation and reports
    self-similarity.
  - The PipelineCoordinator records recursion deliberately and existing
    coordination behavior is unchanged.
"""

import numpy as np

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.scale.principle import (
    ScaleInvariancePrinciple, CANONICAL_PHASES, CANONICAL_AXIOM_COUNT,
)
from telos.core.scale.ledger import RecursionLedger
from telos.core.scale.verifier import ScaleVerifier, ScaleConfig
from telos.core.coordination.coordinator import (
    PipelineCoordinator, SubPipelineConfig,
)
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World


class TinySim(DomainSimulator):
    """Minimal 2-D simulator for scale tests."""

    def initialize(self): pass
    def cleanup(self): pass
    def legal_transitions(self, s):
        return [np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([-1.0, 0.0])]
    def transition(self, s, a): return s + a
    def simulate(self, s, h):
        return [World(state=s.copy() + np.random.randn(2) * 0.1) for _ in range(min(h, 3))]
    def get_facts(self, s):
        return DomainFacts(state=s.copy(), resources={}, constraints=[], events=[], metrics={})
    def terminal(self, s): return False
    def evaluate(self, s):
        return EvaluationReport(objectives={}, risks=0.0)


class TinyAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x
    def intent_to_action(self, intent, state, md):
        av = intent.params.get('action_vector')
        if av is not None:
            if isinstance(av, np.ndarray) and av.size > 0:
                return np.asarray(av)
            if av:
                return np.asarray(av)
        return np.sign(np.array([4.0, 4.0]) - state).astype(float)
    @property
    def name(self): return "tiny"


def _build_pipeline(sim=None, adapter=None, budget_ms=30.0, n_worlds=5, horizon=3):
    """Build a standard pipeline (same shape as coordinator sub-pipelines).

    Args:
        sim: optional domain simulator to attach to the pipeline.
        adapter: optional domain adapter to attach to the pipeline.
        budget_ms: compute budget for the pipeline.
        n_worlds: number of counterfactual worlds.
        horizon: simulation horizon.
    """
    config = PipelineConfig(simulator=sim, adapter=adapter,
                            compute_budget_ms=budget_ms, state_dim=2,
                            n_worlds=n_worlds, horizon=horizon)
    pipeline = TelosV14Pipeline(config)
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim) if sim else None)]:
        pipeline.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0)]:
        pipeline.register_validator(v)
    return pipeline


# ── Principle ────────────────────────────────────────────────────────────

def test_principle_canonical_phases_match_runtime():
    """The documented canonical law must match the actual runtime phases."""
    p = TelosV14Pipeline(PipelineConfig())
    actual = tuple(ph.name for ph in p._phases)
    assert ScaleInvariancePrinciple().canonical_phases == actual
    assert CANONICAL_PHASES == actual
    assert len(CANONICAL_PHASES) >= 7  # the classic 7-phase core is present


def test_principle_matches_phases():
    principle = ScaleInvariancePrinciple()
    assert principle.matches_phases(CANONICAL_PHASES)
    assert not principle.matches_phases(("perceive", "act"))
    assert principle.axiom_set_is_constitutional(frozenset({"1.1", "4.3", "6.5"}))
    assert not principle.axiom_set_is_constitutional(frozenset())
    assert principle.canonical_axiom_count == CANONICAL_AXIOM_COUNT == 42


def test_principle_to_dict():
    d = ScaleInvariancePrinciple().to_dict()
    assert d["id"] == "P1.0"
    assert "Scale Invariance" in d["name"]
    assert d["scales"] == ["macro", "meso", "micro"]


# ── RecursionLedger ──────────────────────────────────────────────────────

def test_recursion_ledger_records_and_reports_self_similarity():
    ledger = RecursionLedger()
    # Two invocations that follow the canonical law
    ledger.record(parent_scope="supervisor", scope="sub:a", scale="micro",
                  phase_signature=CANONICAL_PHASES, axiom_ids=("1.1", "4.3"),
                  success=True, decision_integrity=0.9, mission_drift=0.1)
    ledger.record(parent_scope="supervisor", scope="sub:b", scale="meso",
                  phase_signature=CANONICAL_PHASES, axiom_ids=("1.1", "4.3"),
                  success=True, decision_integrity=0.8, mission_drift=0.2)
    assert len(ledger.entries) == 2
    assert ledger.self_similarity() == 1.0
    assert ledger.invariant_holds() is True
    summary = ledger.summary()
    assert summary["by_scale"] == {"micro": 1, "meso": 1}
    assert summary["entries"] == 2


def test_recursion_ledger_detects_violation():
    ledger = RecursionLedger()
    ledger.record(parent_scope="supervisor", scope="sub:a", scale="micro",
                  phase_signature=CANONICAL_PHASES)
    ledger.record(parent_scope="supervisor", scope="bad:scale", scale="micro",
                  phase_signature=("perceive", "act"))  # not the law
    assert ledger.self_similarity() == 0.5
    assert ledger.invariant_holds() is False


def test_recursion_ledger_axiom_sets_by_scale():
    ledger = RecursionLedger()
    ledger.record(parent_scope="system", scope="supervisor", scale="macro",
                  kind="execute", phase_signature=CANONICAL_PHASES,
                  axiom_ids=("1.1", "1.2", "4.3"))
    ledger.record(parent_scope="supervisor", scope="sub:a", scale="micro",
                  kind="execute", phase_signature=CANONICAL_PHASES,
                  axiom_ids=("1.1", "1.2", "4.3"))
    sets = ledger.axiom_sets_by_scale()
    assert set(sets["macro"]) == {"1.1", "1.2", "4.3"}
    assert set(sets["micro"]) == set(sets["macro"])


def test_recursion_ledger_empty_is_vacuously_invariant():
    ledger = RecursionLedger()
    assert ledger.invariant_holds() is True
    assert ledger.self_similarity() == 0.0


# ── Multi-scale execution ────────────────────────────────────────────────

def test_pipeline_runs_at_multiple_scales_same_structure():
    """macro/meso/micro pipelines run the identical law (phases + axioms)."""
    sim = TinySim()
    verifier = ScaleVerifier(simulator=sim, adapter=TinyAdapter())
    report = verifier.run([
        ScaleConfig(name="macro", scale="macro", budget_ms=60.0, n_worlds=8, horizon=4),
        ScaleConfig(name="meso",  scale="meso",  budget_ms=30.0, n_worlds=5, horizon=3),
        ScaleConfig(name="micro", scale="micro", budget_ms=12.0, n_worlds=3, horizon=2),
    ])

    assert len(report.scales) == 3
    # Same phase structure at every scale
    assert set(report.phase_signatures) == {"macro", "meso", "micro"}
    for sig in report.phase_signatures.values():
        assert tuple(sig) == CANONICAL_PHASES
    # Same verified axiom constitution at every scale
    assert set(report.axiom_sets) == {"macro", "meso", "micro"}
    axiom_sets = list(report.axiom_sets.values())
    assert all(a == axiom_sets[0] for a in axiom_sets)
    assert report.invariant_holds is True
    assert report.violations == []
    assert report.canonical_phases == CANONICAL_PHASES


def test_scale_report_to_dict():
    sim = TinySim()
    verifier = ScaleVerifier(simulator=sim, adapter=TinyAdapter())
    report = verifier.run([ScaleConfig(name="micro", budget_ms=12.0, n_worlds=3)])
    d = report.to_dict()
    assert d["invariant_holds"] is True
    assert d["scales"] == ["micro"]
    assert d["canonical_phases"] == list(CANONICAL_PHASES)


def test_verify_single_pipeline():
    p = _build_pipeline(sim=TinySim(), adapter=TinyAdapter(), budget_ms=20.0)
    verifier = ScaleVerifier()
    ok, reason = verifier.verify_pipeline(p)
    assert ok is True
    assert reason == "ok"


# ── Coordinator: deliberate recursion ────────────────────────────────────

def test_coordinator_spawn_records_recursive_invocation():
    coord = PipelineCoordinator(default_simulator=TinySim(),
                                default_adapter=TinyAdapter())
    coord.spawn(SubPipelineConfig(name="analyst", budget_ms=20.0, scale="micro"))
    ledger = coord.recursion_ledger
    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry.kind == "spawn"
    assert entry.scale == "micro"
    assert tuple(entry.phase_signature) == CANONICAL_PHASES
    assert coord.stats["recursive_invocations"] == 1


def test_coordinator_orchestrate_records_recursion_and_behavior_unchanged():
    coord = PipelineCoordinator(default_simulator=TinySim(),
                                default_adapter=TinyAdapter())
    state = np.array([0.0, 0.0])

    result = coord.orchestrate(
        state=state,
        subtasks=[
            SubPipelineConfig(name="scout", budget_ms=15.0,
                              streams=["reflex", "perception"], scale="micro"),
            SubPipelineConfig(name="planner", budget_ms=25.0,
                              streams=["memory", "planning"], scale="meso"),
        ],
    )

    # ── existing behavior unchanged ──
    assert result.success is not None
    assert len(result.sub_results) == 2
    assert result.sub_results[0].name == "scout"
    assert result.sub_results[1].name == "planner"
    assert result.aggregate_di >= 0.0
    assert 0.0 <= result.aggregate_md <= 1.0

    # ── deliberate recursion recorded ──
    ledger = coord.recursion_ledger
    assert len(ledger.entries) == 4  # 2 spawn + 2 execute
    executes = [e for e in ledger.entries if e.kind == "execute"]
    assert len(executes) == 2
    assert {e.scope for e in executes} == {"sub:scout", "sub:planner"}
    assert {e.scale for e in executes} == {"micro", "meso"}
    assert all(e.success for e in executes)
    for e in executes:
        assert tuple(e.phase_signature) == CANONICAL_PHASES
        assert len(e.axiom_ids) > 0  # constitution was verified

    # ── invariant audit passes ──
    audit = coord.verify_scale_invariance()
    assert audit["invariant_holds"] is True
    assert audit["self_similarity"] == 1.0
    assert audit["entries"] == 4
    assert audit["formal"].startswith("∀ s ∈ Scales")


def test_coordinator_with_supervisor_records_macro_and_micro():
    sim = TinySim()
    supervisor = _build_pipeline(sim=sim, adapter=TinyAdapter(), budget_ms=50.0)
    coord = PipelineCoordinator(supervisor=supervisor,
                                default_simulator=sim,
                                default_adapter=TinyAdapter())

    result = coord.orchestrate(
        state=np.array([0.0, 0.0]),
        subtasks=[SubPipelineConfig(name="sub", budget_ms=15.0, scale="micro")],
    )

    assert result.coordinator_verdict is not None  # existing behavior
    ledger = coord.recursion_ledger
    scales_seen = set(ledger.summary()["by_scale"])
    assert "macro" in scales_seen   # supervisor = meta-cognitive scale
    assert "micro" in scales_seen   # sub-task scale
    macro = [e for e in ledger.entries if e.scope == "supervisor"]
    assert len(macro) == 1
    assert tuple(macro[0].phase_signature) == CANONICAL_PHASES
    assert coord.verify_scale_invariance()["invariant_holds"] is True


def test_coordinator_chain_records_recursion():
    coord = PipelineCoordinator(default_simulator=TinySim(),
                                default_adapter=TinyAdapter())
    result = coord.chain(
        state=np.array([0.0, 0.0]),
        subtasks=[
            SubPipelineConfig(name="step1", budget_ms=15.0, scale="micro"),
            SubPipelineConfig(name="step2", budget_ms=20.0, scale="micro"),
        ],
    )

    assert len(result.sub_results) == 2  # existing behavior
    ledger = coord.recursion_ledger
    executes = [e for e in ledger.entries if e.kind == "execute"]
    assert len(executes) == 2
    assert {e.scope for e in executes} == {"sub:step1", "sub:step2"}
    assert all(tuple(e.phase_signature) == CANONICAL_PHASES for e in executes)
    assert coord.verify_scale_invariance()["invariant_holds"] is True


def test_coordinator_ledger_attaches_to_spawned_pipeline():
    coord = PipelineCoordinator(default_simulator=TinySim(),
                                default_adapter=TinyAdapter())
    p = coord.spawn(SubPipelineConfig(name="tagged", budget_ms=15.0))
    assert p._scale_scope == "tagged"
    assert p._scale_parent == "PipelineCoordinator"
