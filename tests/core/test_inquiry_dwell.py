"""
Bounded inquiry dwell (Λ3.1 backstop) + no risk_coverage plateau.

Inquiry intents (blended_inquiry / curiosity_explore) are exempt from the short
stagnation threshold because their dwell is deliberate exploration. But two
inquiry types can ALTERNATE, each clearing the firewall's same-action loop
window, so neither the firewall nor the per-family stagnation ledger arms and
the agent can dwell. `INQUIRY_DWELL_BUDGET` bounds that dwell: after N
consecutive no-action cycles the goal-seek backstop arms even for inquiry
types — while the firewall keeps owning true same-action traps.
"""
import tempfile
from types import SimpleNamespace

import numpy as np

from telos.core.runtime import INQUIRY_DWELL_BUDGET
from tests.core.test_loop_recovery import _build_pipeline


def _ctx(intent_type="blended_inquiry", cycle=0, action=None,
         firewall_blocked=False, blocked_by=None):
    return SimpleNamespace(
        cycle_count=cycle,
        selected_intent=SimpleNamespace(intent_type=intent_type),
        selected_action=action,
        no_action=action is None,
        firewall_blocked=firewall_blocked,
        firewall_verdict=SimpleNamespace(blocked_by=blocked_by) if blocked_by else None,
    )


def _pipe():
    return _build_pipeline(tempfile.mkdtemp())


def test_backstop_arms_only_after_the_dwell_budget():
    p = _pipe()
    ctx = _ctx()
    for i in range(INQUIRY_DWELL_BUDGET - 1):
        ctx.cycle_count = i
        p._update_stagnation_recovery_state(ctx)
    assert p._recovery_stagnation_armed is False, "short dwell must stay exempt"
    ctx.cycle_count = INQUIRY_DWELL_BUDGET
    p._update_stagnation_recovery_state(ctx)
    assert p._recovery_stagnation_armed is True
    assert p._recovery_reason == "inquiry_dwell_budget"


def test_alternating_inquiry_types_are_still_bounded():
    p = _pipe()
    types = ["blended_inquiry", "curiosity_explore"]
    for i in range(INQUIRY_DWELL_BUDGET):
        ctx = _ctx(intent_type=types[i % 2], cycle=i)
        p._update_stagnation_recovery_state(ctx)
    assert p._recovery_stagnation_armed is True, \
        "alternation must not evade the bounded-dwell backstop"


def test_action_resets_the_dwell_streak():
    p = _pipe()
    for i in range(INQUIRY_DWELL_BUDGET + 2):
        p._update_stagnation_recovery_state(_ctx(cycle=i))
    assert p._recovery_stagnation_armed is True
    p._update_stagnation_recovery_state(
        _ctx(cycle=99, action=np.array([1.0, 0.0])))
    assert p._consecutive_no_action_cycles == 0
    assert p._recovery_stagnation_armed is False


def test_action_loop_does_not_trigger_the_backstop():
    # A same-action trap is the firewall's to escape (it fires at 2); the
    # backstop must not race it.
    p = _pipe()
    for i in range(INQUIRY_DWELL_BUDGET + 3):
        ctx = _ctx(cycle=i, firewall_blocked=True, blocked_by="action_loop")
        p._update_stagnation_recovery_state(ctx)
    assert p._recovery_stagnation_armed is False
    assert p._consecutive_no_action_cycles == 0


def test_no_risk_coverage_plateau_in_real_run():
    # The described [4,2] plateau was an act-phase risk_coverage limit cycle
    # (fixed by world-scaled catastrophe ceiling). Assert it stays gone.
    tmpdir = tempfile.mkdtemp()
    p = _build_pipeline(tmpdir)
    state = np.array([0.0, 0.0])
    risk_blocks = 0
    for _ in range(60):
        res = p.execute(state, user_name="dwell-test")
        if res.governance_blocked_by == "risk_coverage":
            risk_blocks += 1
        t = res.decision_trace
        if t is not None and t.selected_action is not None and not res.firewall_blocked:
            state = p.config.simulator.transition(state, t.selected_action)
        if p.config.simulator.terminal(state):
            state = np.array([0.0, 0.0])
    assert risk_blocks == 0, "risk_coverage plateau regressed"
