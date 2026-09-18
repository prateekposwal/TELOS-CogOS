"""Layer-3 F(I) wiring lock (post-fix).

Locks the DIAGNOSIS-and-FIX produced by telos/tools/layer3_fi_diagnostic.py:

  * the canonical IdentityProjectionGate (F(I)) has a real rejection boundary
    (T8's primitive), AND
  * the LIVE caller now presents it with real inputs: `missionless_bootstrap`
    is True ONLY on a GENUINE pre-mission bootstrap (no objective ever
    defined). A kernel that DECLARED an objective but currently has no active
    mission scope is strict, so a mission-less live-shaped intent is projected
    out. The old wiring set `missionless_bootstrap = not mission_active`, which
    made the Layer-3 guard a tautology.

The pre-fix classification lock asserted the DEFECT. These tests now assert the
fix, including the default live run (objective ACTIVE) staying admissible.
"""
import numpy as np
import pytest

from telos.core.identity.projection_gate import (
    IdentityProjectionGate, ROLE_INCOMPATIBLE, MISSION_EXEMPT,
)
from telos.core.identity.system_self import IdentityCore, IdentityNarrative
from telos.tools.layer3_fi_diagnostic import (
    RecordingGate, _build_pipeline, _run_workload,
)

# The intent types the live GridWorld streams/select path actually produce.
LIVE_INTENT_TYPES = [
    "reflex", "perceive", "memory_miss", "memory_recall", "plan_noop",
    "plan_empty", "plan_trajectory", "domain_plan", "plan_error",
    "propose_theory", "propose_hypothesis", "theory_idle", "blended_inquiry",
    "bootstrap_navigate", "goal_seek_recovery", "curiosity_explore",
    "explore_unknown_unknown", "explore_curiosity", "inquiry",
]


def _gate():
    return IdentityProjectionGate()


# ── The default live run: objective declared AND active ─────────────────────

@pytest.mark.parametrize("itype", LIVE_INTENT_TYPES)
def test_no_live_intent_is_inadmissible_while_mission_active(itype):
    """The production kernel declares an objective AND it is active: the
    mission scope exists, so every live intent stays admissible."""
    assert _gate().is_admissible(
        itype, mission_active=True, mission_defined=True,
        missionless_bootstrap=False) is True


# ── The tautology is gone: defined objective, no active mission ─────────────

@pytest.mark.parametrize("itype", ["plan_trajectory", "domain_plan",
                                   "bootstrap_navigate", "curiosity_explore"])
def test_defined_objective_without_active_mission_rejects_live_intent(itype):
    """A kernel that declared an objective but has NO active mission scope must
    project a mission-serving live-shaped intent out. Under the old
    `missionless_bootstrap = not mission_active` wiring this was unreachable."""
    assert _gate().is_admissible(
        itype, mission_active=False, mission_defined=True,
        missionless_bootstrap=False) is False


def test_l3_tautology_is_gone_under_live_shaped_caller():
    """The exact live context a mission-defined-but-inactive kernel now
    produces (select.py::_identity_gate_context) rejects; reflex still passes."""
    g = _gate()
    # The new caller contract for that configuration:
    mission_active, mission_defined = False, True
    bootstrap = not mission_defined          # genuine-bootstrap signal
    assert bootstrap is False
    assert g.is_admissible("plan_trajectory", mission_active=mission_active,
                           mission_defined=mission_defined,
                           missionless_bootstrap=bootstrap) is False
    assert g.is_admissible("reflex", mission_active=mission_active,
                           mission_defined=mission_defined,
                           missionless_bootstrap=bootstrap) is True


def test_misset_bootstrap_cannot_reopen_the_bypass():
    """A caller that wrongly sets missionless_bootstrap=True while an objective
    IS defined must not re-open the Layer-3 bypass (robustness, not wiring)."""
    assert _gate().is_admissible(
        "plan_trajectory", mission_active=False,
        missionless_bootstrap=True, mission_defined=True) is False


# ── Genuine bootstrap still works ───────────────────────────────────────────

def test_genuine_bootstrap_admits_mission_serving_intent():
    """No objective has EVER been defined: Layer 3 has nothing to reference and
    is skipped; a mission-serving intent is admitted."""
    assert _gate().is_admissible(
        "plan_trajectory", mission_active=False,
        missionless_bootstrap=True, mission_defined=False) is True


def test_genuine_bootstrap_still_enforces_core_values():
    """The bootstrap exception skips ONLY Layer 3 — Layers 1-2 still hold."""
    assert _gate().is_admissible(
        "steal_payload", mission_active=False,
        missionless_bootstrap=True, mission_defined=False) is False


def test_strict_default_still_rejects_mission_less_intent():
    """T8's primitive, unchanged: strict default (no mission, no bootstrap)
    projects a mission-less trajectory out."""
    assert _gate().is_admissible("plan_trajectory", mission_active=False) is False


# ── Layer 1 boundary ────────────────────────────────────────────────────────

def test_layer1_rejects_adversarial_substrings():
    g = _gate()
    assert g.is_admissible("steal_payload", mission_active=True) is False
    assert g.is_admissible("deceive_peer", mission_active=True) is False
    assert g.is_admissible("exploit_explore_harm", mission_active=True) is False


def test_layer1_does_not_reject_any_live_type():
    core = IdentityCore()
    assert core.recognizes("integrity") and core.recognizes("curiosity")
    for itype in LIVE_INTENT_TYPES:
        assert "steal" not in itype and "deceive" not in itype


# ── Layer 2: the default role now has a real predicate ──────────────────────

def test_layer2_default_role_has_a_real_compatibility_predicate():
    """The production role is the default 'agent'. It now has a real,
    conservative predicate: intents that CEDE AGENCY (or terminate the agent)
    are role-incompatible — an agent is by identity the acting party. This is
    role-specific and distinct from Layer 1's integrity/humility checks."""
    assert IdentityNarrative().role == "agent"
    assert "agent" in ROLE_INCOMPATIBLE
    for itype in ("abdicate_agency", "surrender_control", "self_destruct",
                  "self_terminate", "delegate_all"):
        assert _gate().is_admissible(
            itype, mission_active=True, narrative_role="agent") is False


def test_layer2_default_role_still_admits_live_intents():
    """L2 is live-capable but inert for live traffic: no live stream emits an
    agency-ceding intent. That is legitimate defense-in-depth, not tautology."""
    for itype in LIVE_INTENT_TYPES:
        assert _gate().is_admissible(
            itype, mission_active=True, narrative_role="agent") is True


def test_layer2_agent_predicate_does_not_duplicate_layer1():
    """The agent predicate is not a copy of Layer 1: an integrity violator is
    rejected by L1 with the role map absent, and the agency set is disjoint
    from L1's integrity/humility substrings."""
    agent_set = set(ROLE_INCOMPATIBLE["agent"])
    for token in ("steal", "deceive", "harm"):
        assert all(token not in item for item in agent_set)


# ── Adversarial twin: still rejected and projected out ──────────────────────

def test_adversarial_twin_is_rejected_and_projected_out():
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


# ── Live-path integration: a REAL pipeline can now reject ───────────────────

def test_real_pipeline_rejects_live_shaped_intent_when_mission_inactive(tmp_path):
    """Decisive: a real pipeline that DECLARED the production objective can have
    L3 fire once the objective is defined but no active mission remains. The
    live-shaped `plan_trajectory` is projected out and replaced by reflex."""
    from telos.core.phases.select import SelectPhase
    from telos.core.phases.base import PhaseContext
    from telos.intent_ir import IntentIR

    cp = str(tmp_path / "l3_cp")
    pipe, _gate = _build_pipeline(cp, mission=True, recorder=False)
    # Objective declared and active: L3 passes and the guard is not a tautology
    # by accident — the context is strict-capable.
    active_ctx = SelectPhase()._identity_gate_context(pipe)
    assert active_ctx[1] is True and active_ctx[4] is True
    assert active_ctx[3] is False  # missionless_bootstrap False
    # Complete the mission: objective still defined, no active scope.
    for m in pipe._mission_portfolio.active_missions():
        m.complete(cycle=0)
    inactive_ctx = SelectPhase()._identity_gate_context(pipe)
    assert inactive_ctx[1] is False and inactive_ctx[4] is True
    assert inactive_ctx[3] is False  # still NOT genuine bootstrap

    ctx = PhaseContext(cycle_count=5, state=np.zeros(2), user_name=None)
    intent = IntentIR(intent_type="plan_trajectory", confidence=0.9)
    ctx.intents = [(intent, 0.9)]
    ctx.selected_intent = intent
    SelectPhase()._enforce_identity_projection(pipe, ctx)
    assert ctx.identity_projection["projected_out"] == ["plan_trajectory"]
    assert ctx.identity_projection["rejected_selected"] == "plan_trajectory"
    assert ctx.identity_projection["fallback"] is True
    assert ctx.selected_intent.intent_type == "reflex"


def test_genuine_bootstrap_real_pipeline_keeps_working():
    """A real mission-less pipeline takes the genuine-bootstrap path: live
    intents are admitted (no collapse), and its gate context says so."""
    from telos.core.phases.select import SelectPhase
    stats = _run_workload(6, mission=False, seed=42, recorder=True,
                          cp_dir="/tmp/telos_l3_bootstrap_test")
    assert stats["failures"] == 0
    assert stats["projected_out_total"] == 0
    # Context assertion on a fresh mission-less pipeline.
    cp = "/tmp/telos_l3_bootstrap_ctx"
    import shutil
    import os
    if os.path.isdir(cp):
        shutil.rmtree(cp)
    pipe, _ = _build_pipeline(cp, mission=False, recorder=False)
    gate, mission_active, mission_ids, bootstrap, mission_defined = (
        SelectPhase()._identity_gate_context(pipe))
    assert mission_defined is False
    assert bootstrap is True
    assert mission_active is False
    assert mission_ids == []


# ── Recording gate neutrality + exempt set + tool gate ──────────────────────

def test_recording_gate_is_decision_neutral():
    plain = IdentityProjectionGate()
    rec = RecordingGate()
    matrix = [
        ("plan_trajectory", True, False, None, None, None, True),
        ("plan_trajectory", False, False, None, None, None, True),
        ("plan_trajectory", False, True, None, None, None, False),
        ("steal_payload", True, False, None, None, None, False),
        ("explore_dangerous", True, False, "guardian", None, None, False),
        ("reflex", False, False, None, None, None, False),
        ("surrender_control", True, False, "agent", None, None, True),
        ("plan_trajectory", True, False, "agent", "proj_x", ["m1", "proj_x"], True),
        ("plan_trajectory", True, False, "agent", "proj_y", ["m1", "proj_x"], True),
    ]
    for itype, ma, mb, role, pid, mids, mdef in matrix:
        a = plain.is_admissible(itype, project_id=pid, mission_active=ma,
                                mission_ids=mids, narrative_role=role,
                                missionless_bootstrap=mb, mission_defined=mdef)
        b = rec.is_admissible(itype, project_id=pid, mission_active=ma,
                              mission_ids=mids, narrative_role=role,
                              missionless_bootstrap=mb, mission_defined=mdef)
        assert a == b
    assert len(rec.calls) == len(matrix)


def test_mission_exempt_set_spares_live_idle_types():
    g = _gate()
    for itype in MISSION_EXEMPT:
        assert g.is_admissible(itype, mission_active=False,
                               mission_defined=True) is True


def test_diagnostic_tool_ci_gate_passes(tmp_path):
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
