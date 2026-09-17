"""
Governance Layer tests — TrustManager, ReadinessEngine, DecisionFirewall.
"""

import numpy as np

from telos.core.governance.trust_manager import TrustManager
from telos.core.governance.timing import InformationReadinessEngine, ReadinessCondition
from telos.core.governance.firewall import DecisionFirewall, FirewallConfig
from telos.world.world import World
from telos.intent_ir import IntentIR


def test_governance():
    # ── TrustManager ──
    tm = TrustManager()
    tm.set_mission("payment_processing")

    tm.register_stream("PlanningStream", knowledge_domains={"public", "simulation"})
    tm.register_stream("PaymentStream", knowledge_domains={"financial", "public"},
                       authorized_missions={"payment_processing"})

    assert tm.authorize_stream("PaymentStream", "financial") is True
    assert tm.authorize_stream("PlanningStream", "financial") is False
    assert tm.authorize_stream("PlanningStream", "public") is True

    tm.set_mission("support")
    assert tm.authorize_stream("PaymentStream", "financial") is False

    # ── InformationReadinessEngine ──
    re = InformationReadinessEngine()
    re.register_fact("disaster_plan", conditions=[
        ReadinessCondition("signal_detected", threshold=1.0, description="high_severity_alarm"),
    ])

    assert not re.is_ready("disaster_plan")

    re.emit_signal("high_severity_alarm", strength=1.0)
    re.tick()
    assert re.is_ready("disaster_plan")

    re2 = InformationReadinessEngine()
    re2.register_fact("strategic_data", conditions=[
        ReadinessCondition("cycle_count", threshold=3),
    ])
    for _ in range(2):
        re2.tick()
    assert not re2.is_ready("strategic_data")
    re2.tick()
    assert re2.is_ready("strategic_data")

    # ── DecisionFirewall ──
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    world = World(state=np.array([1.0, 2.0]))
    intent = IntentIR("test")

    v1 = fw.inspect(world, intent, council_validated=True, decision_integrity=0.9)
    assert v1.passed is True

    v2 = fw.inspect(world, intent, council_validated=False, decision_integrity=0.9)
    assert v2.passed is False
    assert v2.blocked_by == "council_rejection"

    v3 = fw.inspect(world, intent, council_validated=True, decision_integrity=0.2)
    assert v3.passed is False
    assert v3.blocked_by == "low_integrity"


def test_knowledge_release_authorization():
    """TrustManager.authorize_knowledge_release blocks sensitive domains on default mission."""
    tm = TrustManager()
    tm.set_mission("default")
    assert tm.authorize_knowledge_release("public") is True
    assert tm.authorize_knowledge_release("financial") is False
    assert tm.authorize_knowledge_release("classified") is False
    assert tm.authorize_knowledge_release("personal") is False


def test_knowledge_release_authorized_mission():
    """TrustManager.authorize_knowledge_release allows sensitive domains on authorized mission."""
    tm = TrustManager()
    tm.set_mission("payment_processing")
    assert tm.authorize_knowledge_release("financial") is True
    assert tm.authorize_knowledge_release("public") is True


def test_stream_access_level():
    """TrustManager.get_stream_access_level returns correct default."""
    tm = TrustManager()
    from telos.core.governance.trust_manager import AccessLevel
    level = tm.get_stream_access_level("UnknownStream")
    assert level == AccessLevel.OBSERVE


def test_manual_release():
    """ReadinessEngine.release_manually force-releases a locked fact."""
    re = InformationReadinessEngine()
    re.register_fact("locked_fact", conditions=[
        ReadinessCondition("signal", threshold=1.0, description="needs_signal"),
    ])
    assert not re.is_ready("locked_fact")

    result = re.release_manually("locked_fact")
    assert result is True
    assert re.is_ready("locked_fact")


def test_manual_release_unknown_fact():
    """ReadinessEngine.release_manually returns False for unknown facts."""
    re = InformationReadinessEngine()
    result = re.release_manually("nonexistent")
    assert result is False


def test_firewall_di_threshold_update():
    """DecisionFirewall.set_di_threshold updates the threshold with clamping."""
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
    fw.set_di_threshold(0.8)
    assert fw.config.min_decision_integrity == 0.8

    fw.set_di_threshold(1.5)
    assert fw.config.min_decision_integrity == 0.95

    fw.set_di_threshold(-1.0)
    assert fw.config.min_decision_integrity == 0.05


def test_firewall_no_intent_block():
    """DecisionFirewall blocks when no intent is provided (no council rejection)."""
    fw = DecisionFirewall()
    world = World(state=np.array([1.0, 2.0]))
    v = fw.inspect(world, intent=None, council_validated=True, decision_integrity=0.5)
    assert v.passed is False
    assert v.blocked_by == "no_intent"


# ═══════════════════════════════════════════════════════════════════════
# Item 4 — Λ3.1 loop-trap escape: after RECOVERY_AFTER_LOOP_BLOCKS (2)
# consecutive action_loop blocks the firewall's verdict carries a
# recovery_requested signal. The block is NEVER waived — recovery only
# informs the next selection (the recovery intent passes every check).
# ═══════════════════════════════════════════════════════════════════════

def test_firewall_loop_recovery_signal_after_repeated_blocks():
    """Two consecutive action_loop blocks request a goal-seek recovery; a
    genuine pass clears the streak; a NON-loop block can no longer cancel an
    armed same-type streak (Item 2 — Check 1/2 fire before loop detection);
    the block still happens."""
    from telos.core.governance.firewall import (
        DecisionFirewall, FirewallConfig, RECOVERY_AFTER_LOOP_BLOCKS,
    )
    fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.3))
    world = World(state=np.array([1.0, 2.0]))

    def same_intent(tag):
        return IntentIR(tag, confidence=0.9)

    # First streak: 4 repeats of the same type → blocked, streak = 1.
    for _ in range(4):
        v = fw.inspect(world, same_intent("navigate_to_goal"), council_validated=True,
                       decision_integrity=0.9)
    assert not v.passed and v.blocked_by == "action_loop"
    assert fw.consecutive_loop_blocks == 1
    assert not any(s.get("recovery_requested") for s in v.governance_signals), \
        "recovery must not be requested on the FIRST loop block"

    # Second streak: ONE more repeat (the sliding window of 4 is full of the
    # same type) → blocked again, streak = 2 → recovery requested.
    v = fw.inspect(world, same_intent("navigate_to_goal"), council_validated=True,
                   decision_integrity=0.9)
    assert not v.passed and v.blocked_by == "action_loop"
    assert fw.consecutive_loop_blocks == 2
    recovery = [s for s in v.governance_signals if s.get("recovery_requested")]
    assert recovery, "2nd consecutive loop block must request recovery (Λ3.1)"
    assert recovery[0]["consecutive_loop_blocks"] == 2
    assert recovery[0].get("axiom") == "3.1"

    # A legitimate pass (different intent) clears the streak.
    v = fw.inspect(world, same_intent("explore_terrain"), council_validated=True,
                   decision_integrity=0.9)
    assert v.passed and fw.consecutive_loop_blocks == 0

    # A non-loop block of the SAME type mid-accumulation must NOT cancel the
    # in-flight escape (Item 2 fix): the window needs 4 repeats to re-form
    # the trap; once the streak is at 2, the council-rejection block fires
    # at Check 1 — BEFORE Check 5's loop detector — and its same-type reset
    # used to zero the armed streak so the escape could never fire (pinned at
    # max 1 forever). The armed streak now survives the interruption.
    for _ in range(4):
        fw.inspect(world, same_intent("navigate_to_goal"), council_validated=True,
                   decision_integrity=0.9)
    assert fw.consecutive_loop_blocks == 1, "streak must rebuild after passes"
    fw.inspect(world, same_intent("navigate_to_goal"), council_validated=True,
               decision_integrity=0.9)
    assert fw.consecutive_loop_blocks == 2, "second consecutive block reaches the threshold"
    v = fw.inspect(world, same_intent("navigate_to_goal"), council_validated=False,
                   decision_integrity=0.9)
    assert v.blocked_by == "council_rejection"
    assert fw.consecutive_loop_blocks == 2, \
        "an armed same-type streak survives a non-loop block (escape stays in flight)"
    # A genuine pass still clears the whole ledger (the agent acted, trap broken).
    v = fw.inspect(world, same_intent("explore_terrain"), council_validated=True,
                   decision_integrity=0.9)
    assert v.passed and fw.consecutive_loop_blocks == 0
    assert RECOVERY_AFTER_LOOP_BLOCKS == 2


def test_firewall_loop_recovery_threshold_constant():
    """RECOVERY_AFTER_LOOP_BLOCKS must be exactly 2 (the spec: 'after 2+
    consecutive action_loop firewall blocks, trigger a recovery path')."""
    from telos.core.governance.firewall import RECOVERY_AFTER_LOOP_BLOCKS
    assert RECOVERY_AFTER_LOOP_BLOCKS == 2
