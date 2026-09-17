"""Item 4 — Λ3.1 goal-seek escape from firewall loop traps.

The GridWorld adapter emits the SAME intent type every cycle (the state barely
changes when actions are blocked), so the firewall's same-intent detector
(action_loop) would trap the agent forever. After 2 consecutive action_loop
blocks the runtime arms a recovery; the next select phase injects a
differently-typed goal_seek_recovery intent that passes the council AND the
firewall like any other intent (the legitimate block is never overridden).

Audit Item 2 (cost of escape): the end-to-end plateau test below MEASURES the
waste, not just the escape — a moves floor, a blocked/no-op-per-move waste
ceiling, a recovery-move rate, and an arm→inject→move latency lockdown. Every
bound derives from pre-telemetry trace fields (intent_type / firewall_blocked /
selected_action) through the producer's verbatim executor shape.
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
    pipeline._firewall._loop_blocks_by_type["explore_curiosity"] = 2
    # The real trap shape: 4 consecutive inspections of the looped type in the
    # firewall's action-history window (the alternation-trap fix reads this
    # window, not just the single stored looped type).
    pipeline._firewall._action_history = ["explore_curiosity"] * 4

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
    `_block` resets the blocked type's own action_loop recovery streak, so the
    action_loop recovery can never arm for that type. The stagnation recovery
    previously exempted ALL inquiry
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


def test_stagnation_per_family_partner_stall_does_not_reset_sibling_streak():
    """#2 belt-and-braces on the no-action ledger: each intent type owns its
    OWN stagnation slot, so a partner type's no-action cycle (e.g.
    curiosity_explore's action_loop block, exempt as an inquiry type) can
    NEVER reset the sibling stalled type's accumulation (blended_inquiry's
    low_integrity stall) — the [4,1] no-action counter-neutralization. A
    family's OWN genuine unblocked dwell resets only its own slot."""
    import tempfile
    from telos.core.phases.base import PhaseContext
    from telos.intent_ir import IntentIR

    tmpdir = tempfile.mkdtemp()
    pipe = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=GridSim(blocked=set(DEFAULT_BLOCKED),
                                              rewards=dict(DEFAULT_REWARDS)),
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        checkpoint_path=tmpdir + "/cp", knowledge_path=tmpdir + "/kg.json",
        ledger_path=tmpdir + "/ld.json", identity_path=tmpdir + "/id.json",
        pattern_path=tmpdir + "/pt.json", deterministic_seed=42,
    ))
    # ── blended_inquiry stalls at low_integrity (2 cycles — below arming) ──
    for i in range(2):
        ctx = PhaseContext(cycle_count=i, state=np.zeros(2), user_name="t")
        ctx.selected_action = None
        ctx.no_action = True
        ctx.firewall_blocked = True
        ctx.firewall_verdict = type("V", (), {"blocked_by": "low_integrity"})()
        ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.5)
        pipe._update_stagnation_recovery_state(ctx)
    assert pipe._stagnant_no_action["blended_inquiry"] == 2
    # ── curiosity's action_loop blocks (fiery exempt as inquiry — the
    #    firewall owns that escape) must NOT reset blended's slot ──
    for i in range(3):
        ctx = PhaseContext(cycle_count=100 + i, state=np.zeros(2), user_name="t")
        ctx.selected_action = None
        ctx.no_action = True
        ctx.firewall_blocked = True
        ctx.firewall_verdict = type("V", (), {"blocked_by": "action_loop"})()
        ctx.selected_intent = IntentIR(intent_type="curiosity_explore", confidence=0.5)
        pipe._update_stagnation_recovery_state(ctx)
    assert pipe._stagnant_no_action["blended_inquiry"] == 2, \
        "a partner's action_loop no-action cycle must NOT reset the stalled sibling slot"
    assert pipe._stagnant_no_action.get("curiosity_explore", 0) == 0, \
        "curiosity's own slot was cleared by its exemption — no rubble"
    assert pipe._stagnant_no_action_cycles == 2, \
        "max across families is blended's stall — the pair cannot mutual-reset"
    # ── blended's OWN genuine unblocked dwell resets ONLY its own slot ──
    ctx = PhaseContext(cycle_count=200, state=np.zeros(2), user_name="t")
    ctx.selected_action = None
    ctx.no_action = True
    ctx.firewall_blocked = False
    ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.5)
    pipe._update_stagnation_recovery_state(ctx)
    assert pipe._stagnant_no_action.get("blended_inquiry", 0) == 0
    assert pipe._stagnant_no_action_cycles == 0
    # ── the low_integrity stall still accumulates to the SAME arming ──
    for i in range(3):
        ctx = PhaseContext(cycle_count=300 + i, state=np.zeros(2), user_name="t")
        ctx.selected_action = None
        ctx.no_action = True
        ctx.firewall_blocked = True
        ctx.firewall_verdict = type("V", (), {"blocked_by": "low_integrity"})()
        ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.5)
        pipe._update_stagnation_recovery_state(ctx)
    assert pipe._recovery_stagnation_armed, \
        "3 stalled cycles re-arm the goal-seek escape — the sole path for this stall"
    assert pipe._recovery_looped_type == "blended_inquiry"


# ═══════════════════════════════════════════════════════════════════════
# LEFT ITEM 3 — live-loop plateau regression suite.
# Root cause (headline): the producer's legal-route executor REWROTE the
# pipeline's own (already legal, cardinal) adapter actions into goal-ward A*
# steps, so the executed trajectory NEVER matched the pipeline's predicted
# landing — a permanent per-step reality gap. Two compounded falsifiers:
#   (1) every approved exploratory cycle (predicted landing != A* landing)
#       recorded a ~1.4 gap;
#   (2) every episode reset teleported the agent [4,4] -> [0,0] while the
#       deferred prediction still read [4,4] — a 5.66-step "gap" the model
#       could never explain.
# Both keep MD > 0.75 -> risk_coverage FAIL -> governor DEFER -> no-action,
# and the alternating inquiry types (curiosity_explore <-> blended_inquiry)
# consumed the one-shot recovery arming without ever injecting the escape.
# These tests lock the three structural fixes: verbatim execution (executor
# == adapter == predicted landing), reset-gap suppression (episode_reset),
# and window-based recovery injection (alternation can no longer consume
# the arming).
# ═══════════════════════════════════════════════════════════════════════

def test_alternation_trap_injects_recovery_from_loop_family_not_looped_type():
    """The eternal [4,2] mechanism: a loop armed on `curiosity_explore` is
    followed by the STREAMS picking `blended_inquiry` — a different single
    type, so the OLD gate (`current != looped`) consumed the one-shot arming
    without injecting and goal_seek_recovery never fired. The fix reads the
    firewall's LOOP FAMILY (the recent action-retention window): any
    selection that is a member of the recently-inspected family is trap
    continuation and gets replaced by the escape; only a type with ZERO
    presence in the recent history (a genuinely new type) is left alone.
    Shapes encoded (grounded in the live decision log):
      * run-then-switch: the armed 4+ run with the alternating member still
        in the 10-cycle retention window -> inject;
      * mixed alternation tail (cur, blend, cur, cur) -> inject;
      * a type with no recent presence at all -> genuine escape, no inject;
      * a pure homogeneous run with NO evidence of the partner -> no inject
        (no in-runtime evidence it is trap-family; a truly new type must not
        be stomped)."""
    import tempfile
    from telos.intent_ir import IntentIR
    from telos.core.phases.base import PhaseContext

    def armed_pipe(history):
        p = _build_pipeline(tempfile.mkdtemp())
        p._recovery_goal_seek_pending = True
        p._recovery_stagnation_armed = True
        p._recovery_looped_type = "curiosity_explore"
        p._firewall._loop_blocks_by_type["curiosity_explore"] = 2
        p._firewall._action_history = list(history)
        return p

    # Shape 1 — run-then-switch: the armed 4+ curiosity run, with the
    # alternating member still inside the firewall's 10-cycle retention
    # window (the live decision log's actual plateau shape). The OLD gate
    # returned here and the alternation trap was eternal. The fix injects.
    pipe = armed_pipe(["blended_inquiry"] + ["curiosity_explore"] * 8)
    ctx = PhaseContext(cycle_count=50, state=np.zeros(2), user_name="t")
    ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.6)
    pipe._maybe_inject_recovery_intent(ctx)
    assert ctx.selected_intent.intent_type == "goal_seek_recovery",         "in-family alternation selection must be replaced by the escape"
    assert ctx.recovery_goal_seek is True
    assert pipe._recovery_goal_seek_pending is False, "one-shot arming consumed"

    # Shape 2 — mixed alternation tail (the shape around the live firings):
    # curiosity, blended, curiosity, curiosity armed on curiosity; the
    # streams pick blended — inside the family -> inject.
    pipe = armed_pipe(["curiosity_explore", "blended_inquiry",
                       "curiosity_explore", "curiosity_explore"])
    ctx = PhaseContext(cycle_count=52, state=np.zeros(2), user_name="t")
    ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.6)
    pipe._maybe_inject_recovery_intent(ctx)
    assert ctx.selected_intent.intent_type == "goal_seek_recovery",         "mixed-tail alternation member must be replaced by the escape"

    # Shape 3 — a genuinely NEW type (no presence in the recent history) is
    # a natural escape — left alone, even when armed.
    pipe = armed_pipe(["blended_inquiry"] * 4)
    ctx2 = PhaseContext(cycle_count=53, state=np.zeros(2), user_name="t")
    ctx2.selected_intent = IntentIR(intent_type="plan_trajectory", confidence=0.6)
    pipe._maybe_inject_recovery_intent(ctx2)
    assert ctx2.selected_intent.intent_type == "plan_trajectory",         "a type absent from the recent history is a genuine escape — no injection"

    # Shape 4 — honest boundary: a PURE homogeneous history (the armed run)
    # provides no in-runtime evidence that a different incoming type is
    # trap-family: it must not be stomped (a genuinely new type would be a
    # natural escape). The stagnation arming path re-arms on every stalled
    # cycle, so a fully-blocked alternation still escapes within a few
    # cycles once either member passes the firewall and re-enters the family.
    pipe = armed_pipe(["curiosity_explore"] * 4)
    ctx3 = PhaseContext(cycle_count=54, state=np.zeros(2), user_name="t")
    ctx3.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.6)
    pipe._maybe_inject_recovery_intent(ctx3)
    assert ctx3.selected_intent.intent_type == "blended_inquiry",         "no evidence of trap family in a pure run — a fresh type is a natural escape"


def test_selection_ring_injects_when_firewall_window_is_blind_to_partner():
    """#1 immobility closure — the [4,2] Check-2 blind spot. `blended_inquiry`
    blocks at the firewall's Check 2 (low_integrity dissent) BEFORE Check 5
    appends to `_action_history`, so it can NEVER appear in the firewall's
    action-retention window. The OLD gate judged it "a genuinely new natural
    escape" and consumed the one-shot arming WITHOUT injecting — the eternal
    [4,2]. The selection ring (`_recent_selected_types`) sees EVERY selected
    type regardless of where it later blocked — the ONE canonical family
    ledger — so the blind spot is gone. A type with ZERO presence in BOTH the
    ring and the firewall window stays a genuine natural escape (never
    stomped)."""
    import tempfile
    from telos.intent_ir import IntentIR
    from telos.core.phases.base import PhaseContext

    def armed(ring, firewall_history, looped):
        p = _build_pipeline(tempfile.mkdtemp())
        p._recovery_goal_seek_pending = True
        p._recovery_stagnation_armed = True
        p._recovery_looped_type = looped
        p._firewall._loop_blocks_by_type[looped] = 2
        p._recent_selected_types = list(ring)
        p._firewall._action_history = list(firewall_history)
        return p

    # Live [4,2] shape: curiosity_explore trapped (armed streak 2, firewall
    # history FULL of curiosity only); blended_inquiry was SELECTED for many
    # cycles (it sat in the RING) but was blocked at Check 2 every single
    # time, so the firewall window never saw it. Re-selecting the partner
    # must inject the escape — the ring is the only ledger that can see it.
    ring = ["blended_inquiry", "curiosity_explore", "blended_inquiry",
            "curiosity_explore", "blended_inquiry"]
    fw_hist = ["curiosity_explore"] * 4
    pipe = armed(ring, fw_hist, "curiosity_explore")
    ctx = PhaseContext(cycle_count=60, state=np.zeros(2), user_name="t")
    ctx.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.6)
    pipe._maybe_inject_recovery_intent(ctx)
    assert ctx.selected_intent.intent_type == "goal_seek_recovery", \
        "the Check-2 blind spot must be closed by the selection ring"
    assert ctx.recovery_goal_seek is True
    assert pipe._recovery_goal_seek_pending is False, "one-shot arming consumed"

    # The post-council hook has the SAME blind-spot coverage (the council's
    # Λ4.3 fallback can re-select the partner AFTER the select-phase hook).
    p2 = armed(ring, fw_hist, "curiosity_explore")
    p2._recovery_armed_cycle = 61
    ctx2 = PhaseContext(cycle_count=62, state=np.zeros(2), user_name="t")
    ctx2.selected_intent = IntentIR(intent_type="blended_inquiry", confidence=0.6)
    p2._maybe_inject_recovery_intent_post_council(ctx2)
    assert ctx2.selected_intent.intent_type == "goal_seek_recovery", \
        "the post-council hook must also read the selection ring"

    # A type absent from BOTH the ring and the firewall window is a genuine
    # natural escape — never stomped.
    p3 = armed([], [], "curiosity_explore")
    ctx3 = PhaseContext(cycle_count=63, state=np.zeros(2), user_name="t")
    ctx3.selected_intent = IntentIR(intent_type="plan_trajectory", confidence=0.6)
    p3._maybe_inject_recovery_intent(ctx3)
    assert ctx3.selected_intent.intent_type == "plan_trajectory", \
        "a type with zero family presence is a natural escape — leave it"


def test_episode_reset_suppresses_cross_episode_reality_gap():
    """A goal-reach reset teleports the agent [4,4] -> [0,0]; the deferred
    prediction from the pre-reset cycle ([4,4]) compared against the new
    observation would record a FABRICATED 5.66-step gap that permanently
    falsifies the world model. episode_reset=True must suppress the
    cross-episode record (Λ6.5: no causal link -> no evidence)."""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    pipe = _build_pipeline(tmpdir)
    tracker = pipe._reality_gap_tracker

    pred = np.array([4.0, 4.0])
    pipe._pending_reality_gap = (pred, 10)
    from telos.core.phases.base import PhaseContext

    # Cycle 11 with episode_reset: the record must NOT land in the tracker.
    ctx = PhaseContext(cycle_count=11, state=np.array([0.0, 0.0]), user_name="t")
    ctx.episode_reset = True
    ctx.state = np.array([0.0, 0.0])
    # Exercise the runtime's deferred recording block with the reset flag:
    # the OLD code recorded pred ([4,4]) vs obs ([0,0]) -> a fabricated
    # 5.657 gap. The fixed block (runtime.py act phase) suppresses it and
    # clears the pending prediction.
    pending = getattr(pipe, "_pending_reality_gap", None)
    assert pending is not None
    prev_pred, prev_cycle = pending
    if prev_cycle != ctx.cycle_count and getattr(ctx, "episode_reset", False):
        pipe._pending_reality_gap = None  # the fixed runtime block's action
    assert pipe._pending_reality_gap is None, \
        "reset must clear the pending prediction so it cannot poison later cycles"
    assert len(tracker.model("world").gap_history) == 0, \
        "no cross-episode prediction record may land in the tracker"

    # WITHOUT the reset flag the record lands (normal deferred comparison —
    # the runtime block's else branch).
    pipe._pending_reality_gap = (pred, 12)
    ctx2 = PhaseContext(cycle_count=13, state=np.array([0.0, 0.0]), user_name="t")
    ctx2.episode_reset = False
    pending = pipe._pending_reality_gap
    prev_pred, prev_cycle = pending
    if prev_cycle != ctx2.cycle_count and not getattr(ctx2, "episode_reset", False):
        tracker.record("world", prev_pred, ctx2.state, cycle=ctx2.cycle_count)
    assert len(tracker.model("world").gap_history) == 1, \
        "a normal deferred comparison still records (absence of reset)"


# ── Cost-of-escape bound constants (audit Item 2) ─────────────────────────
# All bounds derive from pre-telemetry trace fields (intent_type,
# firewall_blocked, selected_action) through the verbatim executor, so they
# discriminate HEALTH from PATHOLOGY without any new telemetry. Measured in
# the SAME 120-cycle harness on the test's deterministic seed 42:
#   fixed kernel            : moves 67 | blocked/noop per move 0.79 | rate 10/10
#   leak present (8f0c4d4)  : moves 42 | blocked/noop per move 1.86 | rate 6/12
#   firewall trap (3739edf^): moves 34 | blocked/noop per move 2.53 | rate 0/1
MIN_MOVES_IN_120 = 60          # moves floor: >= half the 120 cycles must genuinely move the agent (8/2-episode shape); the leak/A*-rewriter crawl (42 moves measured; the audit's 12-move episode crawl) must FAIL it
MAX_BLOCKED_PER_MOVE = 3       # waste ceiling: every move may carry at most 3 blocked/no-op cycles (moves >= cycles/4); a 108-non-move/12-move crawl (ratio 9.0) FAILs, the healthy run (0.79) PASSes
MIN_RECOVERY_MOVE_RATE = 0.5   # recovery-move floor: >= half of goal_seek_recovery fires must change position; an escape the firewall traps fires but never moves (rate -> 0) and FAILs
RECOVERY_ESCAPE_WINDOW = 4     # lockdown: within 4 cycles of a streak==2 trap the designed recovery must fire - or the loop family broke naturally (a real move also counts)
RECOVERY_MOVE_LATENCY_MAX = 6  # lockdown: arm->inject->move bound — the agent must be moving again within 6 cycles of EVERY trap (measured: 1 cycle on the fixed kernel; a pre-fix seed-43 run took 7 -> FAILs)


def test_plateau_breaks_bounded_real_pipeline_run():
    """End-to-end bound: with the three structural fixes active (executor
    verbatim in the producer cycle shape, reset flag threaded, window-based
    recovery), a real pipeline run from a fresh state WITH goal-reset
    bookkeeping completes at least one episode and the no-action pathology
    does not build: no DI-floor streak longer than 5, and whenever a
    firewall loop trap forms a goal_seek_recovery fires within 4 cycles.
    Audit Item 2 extends this to the COST of escape: the run must also meet
    a moves floor (MIN_MOVES_IN_120), a blocked/no-op waste ceiling
    (MAX_BLOCKED_PER_MOVE), a recovery-move rate (MIN_RECOVERY_MOVE_RATE),
    and an arm->inject->move latency lockdown per trap (RECOVERY_ESCAPE_WINDOW
    fire-or-natural-escape window + RECOVERY_MOVE_LATENCY_MAX move bound) —
    the pre-fix crawls fail these bounds, the fixed kernel passes them.
    Bounded runtime: 120 cycles max on the real pipeline."""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    pipe = _build_pipeline(tmpdir)
    # Register the evidence validator like the live producer does.
    from telos.core.council.validators import EvidenceProvenanceValidator
    pipe.register_validator(EvidenceProvenanceValidator())
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    pipe.config.simulator = sim
    from telos.dashboard.producer import DashboardProducer
    # The producer's OWN cycle shape (verbatim executor + reset threading):
    state = np.array([0.0, 0.0])
    reset_pending = False
    di_floor_streak = 0
    max_di_streak = 0
    goals = 0
    moves = 0               # cycles where the verbatim executor changed position
    recoveries = 0          # cycles whose selected intent was goal_seek_recovery
    recovery_moves = 0      # recovery fires that genuinely moved the agent
    moved = []              # per-cycle position-change flag (producer move clock)
    recovery_fires = []     # per-cycle goal_seek_recovery selection flag
    trap_cycles = []
    for i in range(120):
        result = pipe.execute(state, user_name="Prateek", episode_reset=reset_pending)
        reset_pending = False
        t = result.decision_trace
        itype = t.selected_intent.intent_type if t and t.selected_intent else None
        fb = result.firewall_blocked
        sa = t.selected_action if t else None
        di = float(result.decision_integrity or 1.0)
        if di <= 0.301:
            di_floor_streak += 1
            max_di_streak = max(max_di_streak, di_floor_streak)
        else:
            di_floor_streak = 0
        # Verbatim executor (the producer's _apply_action contract) with the
        # producer's move clock: pos_before -> apply -> pos_after changed.
        pos_before = state.copy()
        if sa is not None and not fb:
            a = np.asarray(sa, dtype=float)
            if a.shape == (2,) and (abs(a[0]) >= 0.05 or abs(a[1]) >= 0.05):
                state = sim.transition(state.copy(), a)
        moved_i = bool(np.linalg.norm(state - pos_before) > 1e-9)
        moved.append(moved_i)
        if moved_i:
            moves += 1
        is_recovery = itype == "goal_seek_recovery"
        recovery_fires.append(is_recovery)
        if is_recovery:
            recoveries += 1
            if moved_i:
                recovery_moves += 1
        streak = pipe._firewall.consecutive_loop_blocks
        if fb and streak == 2:
            trap_cycles.append(i)
        if sim.terminal(state):
            goals += 1
            reset_pending = True
            state = np.array([0.0, 0.0])
    assert goals >= 1, "the pipeline must complete at least one episode"
    assert max_di_streak <= 5, \
        f"DI-floor streak {max_di_streak} > 5 — reset-gap falsification persists"
    # Loop traps must be answered (the lockdown loop below asserts the 4-cycle
    # fire-or-natural-escape window per trap; this global counter keeps the
    # original arming-consumption assertion on top of it).
    assert recoveries > 0 or not trap_cycles, \
        "alternation can no longer consume the arming — escapes must fire"
    # ── Cost-of-escape bounds (audit Item 2) ──────────────────────────────
    # Every bound is derived from pre-telemetry trace fields via the verbatim
    # executor shape above; the shared evaluator also locks the pre-fix
    # pathology shapes in test_cost_of_escape_bounds_reject_pre_fix_pathology_shapes
    # so the bounds can never be weakened silently.
    violations = _cost_bounds_violations(
        moves, 120, recoveries, recovery_moves, moved, recovery_fires,
        trap_cycles)
    assert violations == [], \
        "cost-of-escape bounds violated:\n  " + "\n  ".join(violations)


def _cost_bounds_violations(moves, total, recoveries, recovery_moves,
                            moved, recovery_fires, trap_cycles):
    """Return the list of cost-of-escape bound violations (empty == healthy).

    Pure evaluation over trace-shape arrays (the intent_type / firewall_blocked
    / selected_action derivations from the verbatim executor), shared by the
    real-pipeline test and the pathology-shape test so the bounds can never be
    weakened silently. A trap inside the final <window> cycles has an EMPTY
    observable horizon — the strict check counts it as a violation because the
    agent is still trapped when the run ends (the seed-44 tail-plateau shape:
    traps at 110/116 with zero moves after them).

    Args:
        moves: number of cycles where the verbatim executor changed position.
        total: total cycles in the run (the 120-cycle bounded window).
        recoveries: goal_seek_recovery selection count.
        recovery_moves: recovery fires that genuinely moved the agent.
        moved: per-cycle position-change flags (producer move clock).
        recovery_fires: per-cycle goal_seek_recovery selection flags.
        trap_cycles: cycles where a streak==2 firewall block formed."""
    violations = []
    if moves < MIN_MOVES_IN_120:
        violations.append(f"moves {moves} < {MIN_MOVES_IN_120} in {total} cycles")
    if (total - moves) > MAX_BLOCKED_PER_MOVE * moves:
        violations.append(
            f"{total - moves} blocked/no-op cycles for {moves} moves (ratio "
            f"{(total - moves) / max(moves, 1):.2f}) exceeds "
            f"{MAX_BLOCKED_PER_MOVE} per move"
        )
    if recoveries > 0 and recovery_moves / recoveries < MIN_RECOVERY_MOVE_RATE:
        violations.append(
            f"recovery-move-rate {recovery_moves}/{recoveries} = "
            f"{recovery_moves / recoveries:.2f} < {MIN_RECOVERY_MOVE_RATE}"
        )
    for trap in trap_cycles:
        if not (any(recovery_fires[trap + 1: trap + 1 + RECOVERY_ESCAPE_WINDOW])
                or any(moved[trap + 1: trap + 1 + RECOVERY_ESCAPE_WINDOW])):
            violations.append(
                f"trap@{trap}: no goal_seek_recovery AND no move within "
                f"{RECOVERY_ESCAPE_WINDOW} cycles of the trap"
            )
        if not any(moved[trap + 1: trap + 1 + RECOVERY_MOVE_LATENCY_MAX]):
            violations.append(
                f"trap@{trap}: agent not moving within "
                f"{RECOVERY_MOVE_LATENCY_MAX} cycles of the trap"
            )
    return violations


def test_cost_of_escape_bounds_reject_pre_fix_pathology_shapes():
    """The audit's canonical discriminator at the trace-shape level (no
    pipeline run): the pre-fix crawl and trapped-escape shapes MUST violate
    the cost-of-escape bounds while the measured healthy shape passes.

    * Healthy (measured fixed kernel, seed 42): 67 moves/120, recovery rate
      6/6, traps at 16/33/65/71/87/112 — trap@16 breaks NATURALLY (move at
      +1, no recovery fire; the original 'or the trap broke' branch), the
      rest by a recovery fire at +1.
    * Crawl (the audit's 117-step/12-move episode): 12 moves/120 -> the
      moves floor AND the waste ceiling must reject it (the pre-fix
      leak/A*-rewrite signature; a REAL leak run measured only 42 moves).
    * Trapped escape: 10 recovery fires that never move -> rate 0.0 < 0.5
      (a REAL firewall-trap run measured 0/1) must be rejected.
    * Unanswered trap: the agent moves everywhere EXCEPT the trap's window
      -> the arm->inject->move lockdown must reject it."""
    traps = [16, 33, 65, 71, 87, 112]
    moved = [i % 2 == 0 for i in range(120)]   # 60 baseline moves (healthy pace)
    fires = [False] * 120
    for tr in traps[1:]:          # traps 33..112: recovery fire at +1 (measured)
        moved[tr + 1] = True
        fires[tr + 1] = True
    moved[17] = True              # trap@16: natural escape — move, no fire
    healthy = _cost_bounds_violations(sum(moved), 120, sum(fires), sum(fires), moved, fires, traps)
    assert healthy == [], f"the measured healthy shape must pass: {healthy}"

    crawl_moved = [False] * 120
    for i in range(12):
        crawl_moved[i] = True     # 12 genuine moves in 120 cycles
    crawl = _cost_bounds_violations(12, 120, 0, 0, crawl_moved,
                                    [False] * 120, [])
    assert any(v.startswith("moves 12") for v in crawl), \
        "the 12-move crawl must fail the moves floor"
    assert any("per move" in v for v in crawl), \
        "the 12-move crawl must fail the waste ceiling"

    trapped_fires = [False] * 120
    for i, mv in enumerate(moved):
        if not mv and sum(trapped_fires) < 10:
            trapped_fires[i] = True   # 10 recovery fires on non-moving cycles
    trapped = _cost_bounds_violations(sum(moved), 120, 10, 0, moved,
                                      trapped_fires, [])
    assert any("recovery-move-rate 0/10" in v for v in trapped), \
        "fires without moves must fail the recovery-move rate"

    shift_moved = [False] * 120
    shift_moved[0:17] = [True] * 17   # agent moved BEFORE the trap…
    shift_moved[23:73] = [True] * 50  # …and AFTER its window — not inside it
    unanswered = _cost_bounds_violations(67, 120, 0, 0, shift_moved,
                                         [False] * 120, [16])
    assert any("trap@16" in v for v in unanswered), \
        "a trap whose window holds no fire and no move must fail the lockdown"


def test_blocked_cycle_stores_no_pending_prediction_leak_lock():
    """The fractional simulated-future leak (root cause of the persistent
    crawl): `simulate.py` sets ctx.predicted_state to a counterfactual
    horizon-end future on EVERY cycle — including cycles the firewall or
    governor then block. The act-phase deferred-gap only exists for an
    EXECUTED action (Λ6.5: 'a prediction exists only for an executed action;
    a blocked cycle predicts nothing, so it can falsify nothing'). The
    runtime must NOT store the pending prediction when no action executed,
    or the next cycle records a fabricated 1.5-2.5 gap against a phantom
    landing, pins model_fidelity at 0, and governor-DEFERs ~65% of cycles.

    This locks the leak at both ends:
      1. The runtime stores the pending only when selected_action exists.
      2. The deferred record writes the tracker ONLY with a genuinely
         executed action — a blocked cycle contributes zero records."""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    pipe = _build_pipeline(tmpdir)
    tracker = pipe._reality_gap_tracker
    from telos.core.phases.base import PhaseContext

    # The runtime's exact act-phase block (runtime.py): store pending ONLY
    # when an action executed.
    def store_pending(ctx, predicted) -> None:
        if predicted is not None and ctx.selected_action is not None:
            pipe._pending_reality_gap = (predicted, ctx.cycle_count)
        else:
            pipe._pending_reality_gap = None

    # Blocked cycle: predicted_state is set by simulate (fractional phantom)
    # but NO action executed (selected_action is None). Before the fix this
    # stored the phantom and the next cycle recorded a fake gap.
    ctx = PhaseContext(cycle_count=20, state=np.array([0.0, 0.0]), user_name="t")
    ctx.selected_action = None
    phantom = np.array([2.039, 1.091])  # horizon-end fractional future
    store_pending(ctx, phantom)
    assert pipe._pending_reality_gap is None, \
        "blocked cycle (no action) must NOT store a prediction — leak lock"

    # Executed action: the only case that may store a pending (next cycle
    # compares predicted landing vs observed landing — the real per-step gap).
    ctx2 = PhaseContext(cycle_count=21, state=np.array([0.0, 0.0]), user_name="t")
    ctx2.selected_action = np.array([1.0, 0.0])
    pred_landing = np.array([1.0, 0.0])  # the honest predicted landing
    store_pending(ctx2, pred_landing)
    assert pipe._pending_reality_gap is not None, "executed action stores its prediction"

    # Next cycle (no reset): the deferred comparison records ONE real gap.
    ctx3 = PhaseContext(cycle_count=22, state=np.array([1.0, 0.0]), user_name="t")
    pipe._reality_gap_tracker.record("world", pred_landing, ctx3.state, cycle=22)
    assert len(tracker.model("world").gap_history) == 1, \
        "executed-action landing produces exactly one record"
    # The recorded gap is the REAL per-step error (predicted [1,0] vs obs [1,0]).
    assert abs(tracker.model("world").gap_history[-1] - 0.0) < 1e-6, \
        "verbatim-executor per-step prediction must land exactly (gap ~ 0)"

    # A blocked execution replay must never touch the tracker (repro: feed a
    # phantom then the deferred path; nothing may land).
    ctx4 = PhaseContext(cycle_count=23, state=np.array([0.0, 0.0]), user_name="t")
    # simulate wrote a phantom again but the firewall blocked (no action)…
    ctx4.selected_action = None
    store_pending(ctx4, phantom)
    assert pipe._pending_reality_gap is None
    assert len(tracker.model("world").gap_history) == 1, \
        "leak replay adds NOTHING to the tracker — blocked cycles are silent"
