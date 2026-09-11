"""Contract tests for DecisionFirewall — the final pre-execution reality audit.

Focused exact-basename coverage of the constitutional checks (council veto,
DI threshold, mission violation, no-intent). The full loop-recovery behavior
is covered by tests/core/test_loop_recovery.py.
"""
import numpy as np

from telos.core.governance.firewall import (
    DecisionFirewall, FirewallConfig, RECOVERY_AFTER_LOOP_BLOCKS,
)
from telos.intent_ir import IntentIR
from telos.world.world import World


def _world():
    return World(state=np.zeros(2))


def test_council_rejection_blocks():
    fw = DecisionFirewall()
    verdict = fw.inspect(_world(), IntentIR("move", 0.8), council_validated=False,
                         decision_integrity=0.9)
    assert not verdict.passed
    assert verdict.blocked_by == "council_rejection"


def test_low_di_blocks():
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    verdict = fw.inspect(_world(), IntentIR("move", 0.8), council_validated=True,
                         decision_integrity=0.2)
    assert not verdict.passed
    assert verdict.blocked_by == "low_integrity"


def test_no_intent_blocks():
    fw = DecisionFirewall()
    verdict = fw.inspect(_world(), None, council_validated=True,
                         decision_integrity=0.9)
    assert not verdict.passed
    assert verdict.blocked_by == "no_intent"


def test_mission_violation_blocks_when_enabled():
    fw = DecisionFirewall()
    verdict = fw.inspect(_world(), IntentIR("move", 0.8), council_validated=True,
                         decision_integrity=0.9, mission_violation=True)
    assert not verdict.passed
    assert verdict.blocked_by == "mission_violation"


def test_clean_intent_passes():
    fw = DecisionFirewall()
    verdict = fw.inspect(_world(), IntentIR("move", 0.8), council_validated=True,
                         decision_integrity=0.9)
    assert verdict.passed


def test_set_di_threshold_clamps():
    fw = DecisionFirewall()
    fw.set_di_threshold(2.0)
    assert fw.config.min_decision_integrity == 0.95
    fw.set_di_threshold(0.0)
    assert fw.config.min_decision_integrity == 0.05


def test_repeated_same_type_blocks_as_action_loop():
    """4+ consecutive same-type intents form the homogeneous run the loop
    detector is designed to catch: must block as action_loop (trap armed)."""
    fw = DecisionFirewall()
    for _ in range(3):
        v = fw.inspect(_world(), IntentIR("blended_inquiry", 0.8),
                       council_validated=True, decision_integrity=0.9)
        assert v.passed, "fewer than 4 repeats is not yet a loop"
    v = fw.inspect(_world(), IntentIR("blended_inquiry", 0.8),
                   council_validated=True, decision_integrity=0.9)
    assert not v.passed
    assert v.blocked_by == "action_loop"


def test_recovery_type_never_blocked_by_loop_detector():
    """goal_seek_recovery is the DESIGNED escape — the loop detector blocking
    it would trap the escape itself (the plateau's rebound). Repeated recovery
    intents must pass loop detection AND must not pollute the action history
    (they are the interrupt, not the loop member)."""
    from telos.core.governance.recovery_types import STAGNATION_EXEMPT_RECOVERY_TYPES
    fw = DecisionFirewall()
    # Prime the history with a full homogeneous non-recovery run so the loop
    # window is saturated BEFORE any recovery arrives — the exact rebound
    # shape examined live (history full of blended_inquiry x4+, then goal_seek).
    for n in range(6):
        v = fw.inspect(_world(), IntentIR("blended_inquiry", 0.8),
                       council_validated=True, decision_integrity=0.9)
        if n < 3:
            assert v.passed, "fewer than 4 repeats is not yet a loop"
        else:
            assert not v.passed, "the loop trap must form once the window saturates"
    # Recovery type repeated far past any loop threshold still passes the loop
    # check (other checks are trivially satisfied here).
    assert "goal_seek_recovery" in STAGNATION_EXEMPT_RECOVERY_TYPES
    for _ in range(6):
        v = fw.inspect(_world(), IntentIR("goal_seek_recovery", 0.8),
                       council_validated=True, decision_integrity=0.9)
        assert v.passed, "recovery intents must never be loop-blocked"
    # The recovery slots are NOT recorded into the action history.
    assert "goal_seek_recovery" not in fw._action_history
    # The history still reflects the original loop member (the trap's record
    # is untouched by escape attempts).
    assert set(fw._action_history) == {"blended_inquiry"}