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