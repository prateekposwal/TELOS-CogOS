"""Item 4 — Λ3.1 goal-seek escape from firewall loop traps.

The GridWorld adapter emits the SAME intent type every cycle (the state barely
changes when actions are blocked), so the firewall's same-intent detector
(action_loop) would trap the agent forever. After 2 consecutive action_loop
blocks the runtime arms a recovery; the next select phase injects a
differently-typed goal_seek_recovery intent that passes the council AND the
firewall like any other intent (the legitimate block is never overridden).
"""
import os
import tempfile

import numpy as np

from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
from telos.core.runtime import PipelineConfig, TelosV14Pipeline, STAGNATION_RECOVERY_AFTER
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
from telos.core.simulation import CounterfactualEngine


def _build_pipeline(tmpdir: str) -> TelosV14Pipeline:
    """Build the REAL GridWorld pipeline exactly as the dashboard producer
    does (same streams, validators, deterministic seed) on isolated paths.

    Args:
        tmpdir: isolated directory for checkpoint/knowledge/ledger paths."""
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
    skill_lib = SkillLibrary()
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=CounterfactualEngine(sim)))
    pipeline.register_stream(InquiryStream(skill_lib))
    pipeline.register_stream(TheoryStream(skill_lib, theory_builder=getattr(pipeline, "_theory_builder", None)))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))
    return pipeline


def test_loop_recovery_escapes_firewall_trap_in_real_pipeline():
    """Run the real pipeline: after 2 consecutive action_loop blocks a
    goal_seek_recovery intent is selected and PASSES the firewall (the
    escape is a new intent through every check — never an override)."""
    tmpdir = tempfile.mkdtemp()
    pipeline = _build_pipeline(tmpdir)
    state = np.array([0.0, 0.0])
    cycles = []
    for i in range(40):
        r = pipeline.execute(state, user_name="Prateek")
        t = r.decision_trace
        itype = t.selected_intent.intent_type if t and t.selected_intent else None
        cycles.append({
            "intent": itype,
            "firewall_blocked": r.firewall_blocked,
            "firewall_blocked_by": t.firewall_blocked_by if t else None,
            "streak": pipeline._firewall.consecutive_loop_blocks,
            "council_ok": not r.council_blocked,
        })

    # The trap must form (same intent repeated → action_loop blocks) and the
    # recovery must fire: find every streak==2 block and require a passing
    # goal_seek_recovery within the next 3 cycles.
    recoveries = [c for c in cycles if c["intent"] == "goal_seek_recovery"]
    assert recoveries, "goal_seek_recovery must appear in the real run"
    for rc in recoveries:
        assert not rc["firewall_blocked"], \
            "the recovery intent must pass the firewall like any other intent"
        assert rc["council_ok"], "the recovery intent must pass the council"
        assert rc["streak"] == 0, "a pass must clear the loop streak"
    # Every 2nd consecutive loop block must be followed by a recovery (the
    # 2+ threshold from the spec). Collect streak==2 block indexes.
    trap_cycles = [i for i, c in enumerate(cycles)
                   if c["firewall_blocked"] and c["streak"] == 2]
    assert trap_cycles, "the loop trap must form in the real pipeline"
    for idx in trap_cycles:
        window = cycles[idx + 1: idx + 4]
        assert any(w["intent"] == "goal_seek_recovery" for w in window), (
            f"cycle {idx}: streak==2 block not followed by a recovery escape"
        )
    # The agent's world still moves after recovery: the recovery intent's
    # adapter action is non-zero (goal-directed), so the world is not stuck.
    acted = [c for c in cycles if c["intent"] == "goal_seek_recovery"]
    assert acted, "recovery cycles must exist"


def test_post_council_injection_fires_on_final_looped_intent():
    """The council's Λ4.3 fallback can re-select the looped intent AFTER the
    select-phase hook ran; the post-council hook must inject the escape when
    the FINAL intent is the looped type (and stay quiet otherwise)."""
    tmpdir = tempfile.mkdtemp()
    pipeline = _build_pipeline(tmpdir)
    from telos.intent_ir import IntentIR
    from telos.core.phases.base import PhaseContext
    import numpy as _np

    # Arm recovery as if the previous cycle ended on a 2nd loop block.
    pipeline._recovery_goal_seek_pending = True
    pipeline._recovery_armed_cycle = 41
    pipeline._recovery_looped_type = "explore_curiosity"
    pipeline._firewall._consecutive_loop_blocks = 2

    # Cycle 42, council fell back to the looped type.
    ctx = PhaseContext(cycle_count=42, state=_np.array([0.0, 0.0]), user_name="t")
    ctx.selected_intent = IntentIR(intent_type="explore_curiosity", confidence=0.6)
    pipeline._maybe_inject_recovery_intent_post_council(ctx)
    assert ctx.selected_intent.intent_type == "goal_seek_recovery", \
        "post-council hook must replace the final looped intent"
    assert ctx.recovery_goal_seek is True

    # Genuinely different final intent → the trap broke naturally, no injection.
    pipeline._recovery_goal_seek_pending = True
    pipeline._recovery_armed_cycle = 43
    ctx2 = PhaseContext(cycle_count=44, state=_np.array([0.0, 0.0]), user_name="t")
    ctx2.selected_intent = IntentIR(intent_type="explore_terrain", confidence=0.6)
    pipeline._maybe_inject_recovery_intent_post_council(ctx2)
    assert ctx2.selected_intent.intent_type == "explore_terrain", \
        "different final intent must be left alone"

    # Recovery armed two cycles ago (stale) → no injection.
    pipeline._recovery_armed_cycle = 1
    ctx3 = PhaseContext(cycle_count=44, state=_np.array([0.0, 0.0]), user_name="t")
    ctx3.selected_intent = IntentIR(intent_type="explore_curiosity", confidence=0.6)
    pipeline._maybe_inject_recovery_intent_post_council(ctx3)
    assert ctx3.selected_intent.intent_type == "explore_curiosity", \
        "stale arming must not inject"


# ═══════════════════════════════════════════════════════════════════════
# LEFT ITEM 1 — REAL degradation diagnosis (not an aggregation artifact).
# Live evidence: the producer sat in an infinite `blended_inquiry` loop where
# every cycle got DI floored to 0.3 (DISSENT_FLOOR) and the firewall blocked
# it at `low_integrity` (threshold raised to 0.94 by Λ3.1 risk tightening),
# so mood/DI honestly read 0.3 / cautious for hundreds of cycles. THIS test
# locks the two defeat-mechanisms that make that loop terminal — proving the
# dashboard was faithfully reporting REAL degradation, and giving a future
# recovery fix a red test to make green.
# ═══════════════════════════════════════════════════════════════════════

def test_low_integrity_inquiry_loop_escapes_via_stagnation_recovery():
    """A `blended_inquiry` intent DI-floored below a raised firewall threshold
    is a STUCK RETRY, not a deliberate explore-pause (Λ6.5). The firewall
    blocks it at `low_integrity` (Check 2, BEFORE loop detection), whose
    `_block` RESETS `_consecutive_loop_blocks`, so the action_loop recovery
    can never arm. The stagnation recovery previously exempted ALL inquiry
    types, leaving this no-op loop with NO escape (DI 0.3 forever). The fix:
    stagnation keeps the inquiry exemption for genuine unblocked exploration
    AND for `action_loop` traps (the firewall owns those), but arms the
    goal-seek escape for a `low_integrity`-STALLED inquiry retry."""
    # ── (a) Firewall still blocks at low_integrity; loop recovery stays dead ──
    from telos.core.governance.firewall import DecisionFirewall, FirewallConfig, RECOVERY_AFTER_LOOP_BLOCKS
    from telos.intent_ir import IntentIR
    from telos.world.world import World

    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.94, domain="gridworld"))
    world = World(state=np.zeros(2))
    for _ in range(RECOVERY_AFTER_LOOP_BLOCKS + 3):
        intent = IntentIR(intent_type="blended_inquiry", confidence=0.5)
        verdict = fw.inspect(
            world=world, intent=intent, council_validated=True,
            decision_integrity=0.3,  # exactly the live DI-floored value
            domain="gridworld",
        )
        assert not verdict.passed, "DI 0.3 below threshold 0.94 must block"
        assert verdict.blocked_by == "low_integrity", f"got {verdict.blocked_by}"
        assert fw.consecutive_loop_blocks == 0, (
            "low_integrity _block resets the loop counter, so the firewall "
            "action_loop recovery alone can never free this loop"
        )

    # ── (b) Stagnation recovery NOW arms for the low_integrity stall ──
    import tempfile
    from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.phases.base import PhaseContext

    tmpdir = tempfile.mkdtemp()
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=GridSim(blocked=set(DEFAULT_BLOCKED),
                                              rewards=dict(DEFAULT_REWARDS)),
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        checkpoint_path=tmpdir + "/cp", knowledge_path=tmpdir + "/kg.json",
        ledger_path=tmpdir + "/ld.json", identity_path=tmpdir + "/id.json",
        pattern_path=tmpdir + "/pt.json", deterministic_seed=42,
    ))
    for i in range(STAGNATION_RECOVERY_AFTER + 2):
        ctx = PhaseContext(cycle_count=i, state=np.zeros(2), user_name="t")
        ctx.selected_action = None             # no action flowed (blocked)
        ctx.no_action = True
        ctx.firewall_blocked = True            # stalled retry — the real live shape
        ctx.firewall_verdict = type("V", (), {"blocked_by": "low_integrity"})()
        ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.5)
        pipe._update_stagnation_recovery_state(ctx)
        if i < STAGNATION_RECOVERY_AFTER - 1:
            assert not pipe._recovery_stagnation_armed, (
                "stall must accumulate towards the threshold first"
            )
    assert pipe._recovery_stagnation_armed, (
        "stagnation recovery MUST arm for a low_integrity-STALLED inquiry "
        "retry — this is the escape the loop previously had no access to"
    )
    assert pipe._recovery_looped_type == "blended_inquiry"
    assert pipe._recovery_reason == "no_action_stagnation"

    # ── (c) Genuine unblocked inquiry exploration stays exempt ──
    pipe2 = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=GridSim(blocked=set(DEFAULT_BLOCKED),
                                              rewards=dict(DEFAULT_REWARDS)),
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        checkpoint_path=tmpdir + "/cp2", knowledge_path=tmpdir + "/kg2.json",
        ledger_path=tmpdir + "/ld2.json", identity_path=tmpdir + "/id2.json",
        pattern_path=tmpdir + "/pt2.json", deterministic_seed=42,
    ))
    for i in range(STAGNATION_RECOVERY_AFTER + 2):
        ctx = PhaseContext(cycle_count=i, state=np.zeros(2), user_name="t")
        ctx.selected_action = None
        ctx.no_action = True
        ctx.firewall_blocked = False           # deliberate explore — not blocked
        ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.5)
        pipe2._update_stagnation_recovery_state(ctx)
    assert not pipe2._recovery_stagnation_armed, (
        "genuine unblocked inquiry exploration stays exempt (Λ6.5) — do NOT "
        "force-escape deliberate curiosity"
    )
    assert pipe2._stagnant_no_action_cycles == 0, (
        "the unblocked inquiry exemption must keep resetting the no-action counter"
    )
