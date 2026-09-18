"""Layer-3 F(I) classification lock (non-mutating).

Locks the DIAGNOSIS produced by telos/tools/layer3_fi_diagnostic.py:
  * the canonical IdentityProjectionGate (F(I)) has a real rejection boundary
    when its inputs are strict (T8's primitive), AND
  * the LIVE caller can never reach it: `missionless_bootstrap =
    not mission_active` makes the Layer-3 mission guard a tautology, and the
    default narrative role 'agent' plus literal-substring Layer-1 checks mean
    no live intent type is ever identity-inadmissible.

This is a classification lock, NOT a fix. It asserts the current (defective)
wiring so a follow-up fix must update these tests deliberately.
"""
import pytest

from telos.core.identity.projection_gate import IdentityProjectionGate
from telos.core.identity.system_self import IdentityCore, IdentityNarrative
from telos.tools.layer3_fi_diagnostic import (
    RecordingGate, ROLE_INCOMPATIBLE, MISSION_EXEMPT,
)

# The intent types the live GridWorld streams/select path actually produce.
# (runtime.py:1402 emits the dynamic f"explore_{source}" family.)
LIVE_INTENT_TYPES = [
    "reflex", "perceive", "memory_miss", "memory_recall", "plan_noop",
    "plan_empty", "plan_trajectory", "domain_plan", "plan_error",
    "propose_theory", "propose_hypothesis", "theory_idle", "blended_inquiry",
    "bootstrap_navigate", "goal_seek_recovery", "curiosity_explore",
    "explore_unknown_unknown", "explore_curiosity", "inquiry",
]

# The live caller's mission context: either a mission is active (bootstrap
# False) or there is none (bootstrap True). Both are covered.
LIVE_CONTEXTS = [
    dict(mission_active=True, missionless_bootstrap=False),
    dict(mission_active=False, missionless_bootstrap=True),
]


def _gate():
    return IdentityProjectionGate()


@pytest.mark.parametrize("ctx", LIVE_CONTEXTS)
@pytest.mark.parametrize("itype", LIVE_INTENT_TYPES)
def test_no_live_intent_is_ever_inadmissible(ctx, itype):
    """The headline lock: every live intent passes F(I) under both live contexts."""
    assert _gate().is_admissible(itype, **ctx) is True


def test_l3_mission_guard_is_a_tautology_under_live_context():
    """`not mission_active and not missionless_bootstrap` is unsatisfiable when
    the caller sets missionless_bootstrap = not mission_active (select.py:857)."""
    g = _gate()
    for mission_active in (True, False):
        bootstrap = not mission_active
        # Layer 3 can never fire: the guard's two conjuncts are complements.
        blocked_at_l3 = (not mission_active and not bootstrap
                         and "plan_trajectory" not in MISSION_EXEMPT)
        assert blocked_at_l3 is False
        assert g.is_admissible("plan_trajectory", mission_active=mission_active,
                               missionless_bootstrap=bootstrap) is True


def test_strict_l3_boundary_still_exists_for_normal_intent():
    """The predicate CAN reject: strict default (no mission, no bootstrap)
    projects a normal mission-less trajectory out. The boundary is real; the
    live path just never presents this context."""
    assert _gate().is_admissible("plan_trajectory", mission_active=False,
                                 missionless_bootstrap=False) is False


def test_layer1_rejects_adversarial_substrings():
    """Layer 1's boundary exists for literal adversarial intent types."""
    g = _gate()
    assert g.is_admissible("steal_payload", mission_active=True) is False
    assert g.is_admissible("deceive_peer", mission_active=True) is False
    assert g.is_admissible("exploit_explore_harm", mission_active=True) is False


def test_layer1_does_not_reject_any_live_type():
    """No live type contains steal/deceive (default core recognizes integrity),
    and curiosity is recognized — so Layer 1 never fires in the live loop."""
    core = IdentityCore()
    assert core.recognizes("integrity") and core.recognizes("curiosity")
    for itype in LIVE_INTENT_TYPES:
        assert "steal" not in itype and "deceive" not in itype


def test_layer2_default_role_never_blocks():
    """The production narrative role is the default 'agent', which is absent
    from the role map — so Layer 2 never fires."""
    assert IdentityNarrative().role == "agent"
    assert "agent" not in ROLE_INCOMPATIBLE
    for itype in LIVE_INTENT_TYPES:
        assert _gate().is_admissible(
            itype, mission_active=True, narrative_role="agent") is True


def test_adversarial_twin_is_rejected_and_projected_out():
    """§5 decisive experiment: an identity-incompatible twin (differs only in
    intent_type) FAILS F(I) and the live enforcement path removes it."""
    from telos.core.phases.select import SelectPhase
    from telos.core.phases.base import PhaseContext
    from telos.intent_ir import IntentIR

    gate = IdentityProjectionGate()
    normal = IntentIR(intent_type="plan_trajectory", confidence=0.8)
    evil = IntentIR(intent_type="steal_payload", confidence=0.8)
    assert gate.is_admissible(normal.intent_type, mission_active=True) is True
    assert gate.is_admissible(evil.intent_type, mission_active=True) is False

    class _Mission:
        id = "m1"
        project_ids = []

    class _Portfolio:
        def active_missions(self):
            return [_Mission()]

    class _Pipe:
        _identity_projection_gate = gate
        _mission_portfolio = _Portfolio()
        _identity_narrative = IdentityNarrative()

    ctx = PhaseContext(cycle_count=0, state=[0.0, 0.0], user_name=None)
    ctx.intents = [(normal, 0.8), (evil, 0.8)]
    ctx.selected_intent = evil
    SelectPhase()._enforce_identity_projection(_Pipe(), ctx)
    assert ctx.selected_intent.intent_type == "plan_trajectory"
    assert "steal_payload" in ctx.identity_projection["projected_out"]
    assert ctx.identity_projection["rejected_selected"] == "steal_payload"


def test_recording_gate_is_decision_neutral():
    """The diagnostic's RecordingGate returns byte-identical verdicts."""
    plain = IdentityProjectionGate()
    rec = RecordingGate()
    matrix = [
        ("plan_trajectory", True, False, None, None, None),
        ("plan_trajectory", False, False, None, None, None),
        ("plan_trajectory", False, True, None, None, None),
        ("steal_payload", True, False, None, None, None),
        ("explore_dangerous", True, False, "guardian", None, None),
        ("reflex", False, False, None, None, None),
        ("plan_trajectory", True, False, "agent", "proj_x", ["m1", "proj_x"]),
        ("plan_trajectory", True, False, "agent", "proj_y", ["m1", "proj_x"]),
    ]
    for itype, ma, mb, role, pid, mids in matrix:
        a = plain.is_admissible(itype, project_id=pid, mission_active=ma,
                                mission_ids=mids, narrative_role=role,
                                missionless_bootstrap=mb)
        b = rec.is_admissible(itype, project_id=pid, mission_active=ma,
                              mission_ids=mids, narrative_role=role,
                              missionless_bootstrap=mb)
        assert a == b
    assert len(rec.calls) == len(matrix)


def test_mission_exempt_set_spares_live_idle_types():
    """The live loop's idle/recall types bypass the L3 guard even in the strict
    context — one more reason L3 cannot reject live traffic."""
    g = _gate()
    for itype in MISSION_EXEMPT:
        assert g.is_admissible(itype, mission_active=False,
                               missionless_bootstrap=False) is True


def test_diagnostic_tool_ci_gate_passes(tmp_path):
    """The diagnostic tool's own --ci gate passes on a bounded real workload."""
    import os
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = tmp_path / "layer3_fi_diagnostic.json"
    env = dict(os.environ, PYTHONPATH=root)
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "telos", "tools", "layer3_fi_diagnostic.py"),
         "--cycles", "6", "--out", str(out), "--ci"],
        cwd=root, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()
