"""Regression tests for the v6 fix-sprint:
  - live-pathology: blended_inquiry no-action loop escape (Lambda 3.1)
  - decision-provenance-as-evidence council validator
  - P2 budget-carryover telemetry (consumed_ms never negative)
  - P1 handoff cycle-reconciliation stamping
"""
import os
import tempfile
import numpy as np

from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS, GOAL
from telos.core.runtime import PipelineConfig, TelosV14Pipeline
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
from telos.core.attention import BudgetManager
from telos.core.session.agents_writer import AgentsWriter, SessionSummary


def _build_pipeline(tmpdir):
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        checkpoint_path=os.path.join(tmpdir, "cp"),
        knowledge_path=os.path.join(tmpdir, "kg.json"),
        ledger_path=os.path.join(tmpdir, "ld.json"),
        identity_path=os.path.join(tmpdir, "id.json"),
        pattern_path=os.path.join(tmpdir, "pt.json"),
        deterministic_seed=42,
    ))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipeline, "_theory_builder", None))]:
        pipeline.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipeline.register_validator(v)
    return pipeline


def test_pipeline_escapes_stagnation_and_reaches_goal():
    """REAL pipeline, REAL adapter, REAL driver loop: the agent must move
    (emit legal cardinal actions) and reach the goal, escaping any no-action
    stagnation — not sit in blended_inquiry emitting action_taken=null."""
    tmpdir = tempfile.mkdtemp()
    pipeline = _build_pipeline(tmpdir)
    state = np.array([0.0, 0.0])
    actions = []
    for i in range(40):
        r = pipeline.execute(state, user_name="Prateek")
        t = r.decision_trace
        act = t.selected_action
        if act is not None:
            actions.append(t.selected_intent.intent_type)
            state = pipeline.config.simulator.transition(state, act)
        if np.linalg.norm(GOAL - state) < 0.5:
            break
    # The agent must have MOVED (actions emitted) and reached the goal.
    assert actions, "the pipeline emitted no executable actions (stagnation)"
    assert np.linalg.norm(GOAL - state) < 0.5, \
        f"agent did not reach goal; stuck at {state.tolist()}"
    # The reality gap (true per-step prediction error) must converge low.
    rg = pipeline._reality_gap_tracker.model("world")
    assert rg.tested, "reality gap tracker must be fed by the real run"
    assert rg.recent_mean_gap is not None and rg.recent_mean_gap < 2.0, \
        f"per-step reality gap did not converge: {rg.recent_mean_gap}"


def test_council_evidence_validator_dissents_on_falsified_loop():
    """The EvidenceProvenanceValidator must dissent when an intent type has
    produced prolonged no-action (a falsified loop), pushing the system to
    escape — and must NOT penalise legitimate inquiry types."""
    from telos.intent_ir import IntentIR
    from telos.world.world import World
    tracker = pipeline_tracker = None
    v = EvidenceProvenanceValidator()
    # A non-inquiry type repeatedly stuck in no-action -> dissent.
    ctx = {
        "intent_history": {"intent_type": "blended_inquiry",
                           "consecutive_no_action": 5,
                           "total_no_action": 7, "recent_blocks": 2},
        "reality_gap_tracker": tracker,
    }
    sig = v.validate(World(state=np.zeros(2)),
                     IntentIR(intent_type="blended_inquiry", confidence=0.6),
                     context=ctx)
    assert sig.passed is False, "falsified loop must dissent"

    # A legitimate inquiry type is never penalised.
    ctx2 = {"intent_history": {"intent_type": "curiosity_explore",
                               "consecutive_no_action": 9}, "reality_gap_tracker": None}
    sig2 = v.validate(World(state=np.zeros(2)),
                      IntentIR(intent_type="curiosity_explore", confidence=0.6),
                      context=ctx2)
    assert sig2.passed is True, "inquiry types must not be penalised"

    # A fresh type with no record passes.
    sig3 = v.validate(World(state=np.zeros(2)),
                      IntentIR(intent_type="navigate", confidence=0.6),
                      context={"intent_history": {"consecutive_no_action": 0,
                                                  "total_no_action": 0,
                                                  "recent_blocks": 0}})
    assert sig3.passed is True, "unfalsified type must pass"


def test_budget_carryover_keeps_consumed_nonnegative():
    """P2: budget carryover must be tracked in its own field; serialized
    consumed_ms must NEVER go negative (never reads as a bug)."""
    bm = BudgetManager(total_budget_ms=100.0)
    bm.consume("a", 40.0)
    bm.reset(carryover_ms=30.0)
    assert bm.consumed_ms >= 0.0, "consumed_ms must stay >= 0"
    assert bm.budget_carryover_ms == 30.0, "carryover held in its own field"
    assert bm.check_budget("b", 20.0) is True, "carryover grants fresh headroom"
    # carryover is clamped to 50% of budget
    bm2 = BudgetManager(total_budget_ms=100.0)
    bm2.reset(carryover_ms=999.0)
    assert bm2.budget_carryover_ms == 50.0


def test_trace_serializes_budget_carryover():
    """The decision trace carries budget_carryover_ms so the audit never
    misreads a carried-over budget as a negative/absent consumption figure."""
    from telos.core.types import DecisionTrace
    from telos.core.trace_builder import build_trace
    import numpy as np
    tmpdir = tempfile.mkdtemp()
    pipeline = _build_pipeline(tmpdir)
    r = pipeline.execute(np.array([0.0, 0.0]), user_name="Prateek")
    d = r.decision_trace.to_dict()
    assert "budget_carryover_ms" in d, "trace must serialize budget_carryover_ms"
    assert d["budget_carryover_ms"] >= 0


def test_governor_no_action_loop_injects_stagnation_recovery():
    """Regression: a governor-driven no-action loop (firewall NOT blocking,
    so firewall.consecutive_loop_blocks stays 0) must STILL inject the
    goal_seek_recovery escape via the Λ3.1 stagnation armer.

    Pre-fix bug: _update_stagnation_recovery_state armed _recovery_goal_seek_pending
    but both injection guards gated on firewall.consecutive_loop_blocks, which
    stays 0 for governor no-action loops -> the escape was armed but never
    injected, leaving the agent in a permanent no-action loop. This test asserts
    the recovery intent is injected for a stagnation-only path (fw == 0).
    """
    import tempfile
    tmpdir = tempfile.mkdtemp()
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    # Adversarially small compute budget forces no-action cycles (governor
    # starvation) so stagnation accumulates WITHOUT a firewall action_loop block.
    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=5.0, state_dim=2, n_worlds=2, horizon=2,
        checkpoint_path=os.path.join(tmpdir, "cp"),
        knowledge_path=os.path.join(tmpdir, "kg.json"),
        ledger_path=os.path.join(tmpdir, "ld.json"),
        identity_path=os.path.join(tmpdir, "id.json"),
        pattern_path=os.path.join(tmpdir, "pt.json"),
        deterministic_seed=99,
    ))
    sl = SkillLibrary()
    for s in [ReflexStream(sl), PerceptionStream(sl), MemoryStream(sl),
              PlanningStream(sl, sim_engine=CounterfactualEngine(sim)),
              InquiryStream(sl),
              TheoryStream(sl, theory_builder=getattr(pipeline, "_theory_builder", None))]:
        pipeline.register_stream(s)
    for v in [RealityValidator(), ConstraintValidator(), MemoryAdvisor(sl),
              MissionDriftDetector(drift_threshold=5.0), EvidenceProvenanceValidator()]:
        pipeline.register_validator(v)

    state = np.array([0.0, 0.0])
    saw_stagnation_recovery_injected = False
    saw_stagnation_reason = False
    for i in range(14):
        r = pipeline.execute(state, user_name="Prateek")
        t = r.decision_trace
        it = t.selected_intent.intent_type if t.selected_intent else None
        fw = getattr(pipeline._firewall, "consecutive_loop_blocks", 0)
        if pipeline._recovery_reason == "no_action_stagnation":
            saw_stagnation_reason = True
        if it == "goal_seek_recovery" and fw == 0:
            saw_stagnation_recovery_injected = True
        if t.selected_action is not None:
            state = pipeline.config.simulator.transition(state, t.selected_action)

    assert saw_stagnation_reason, \
        "the stagnation armer must record reason=no_action_stagnation"
    assert saw_stagnation_recovery_injected, \
        "governor no-action loop (fw==0) never injected goal_seek_recovery — " \
        "stagnation escape was armed but firewall-gated, so the loop never escaped"


def test_handoff_stamps_cycle_reconciliation():
    """P1: the handoff writer stamps cycle_source + pipeline_cycle_id +
    log_total_cycles so AGENTS.md Cycles reconciles with the decision log."""
    w = AgentsWriter()
    s = SessionSummary(
        metrics={"di": 1.0, "md": 0.0, "cycle_count": 11,
                 "cycle_source": "step_count", "pipeline_cycle_id": 11,
                 "log_total_cycles": 5},
    )
    md = w.generate_markdown(s)
    assert "Cycles: 11" in md
    assert "step_count" in md and "pipeline=11" in md and "log=5" in md, \
        "handoff must stamp the reconciliation provenance"
