"""
Novelty-varying actions are exempt from same-TYPE firewall loop detection.

Check 5 keys on `intent.intent_type`; a novelty adapter emits a VARYING action
for a repeated exploratory type, so a repeated type is not a same-action loop.
The exemption is flagged by the runtime only when adapter novelty is active, so
control (no novelty) still blocks a genuine same-type loop.
"""
import numpy as np

from telos.core.governance.firewall import DecisionFirewall
from telos.world.world import World
from telos.intent_ir import IntentIR


def _inspect(firewall, intent_type, params=None):
    world = World(state=np.zeros(2))
    intent = IntentIR(intent_type=intent_type, confidence=0.8, params=params or {})
    return firewall.inspect(world, intent,
                            council_validated=True, decision_integrity=1.0)


def test_novelty_action_intent_is_exempt_from_loop_detection():
    fw = DecisionFirewall()
    for _ in range(12):
        verdict = _inspect(fw, "curiosity_explore", params={"novelty_action": True})
        assert verdict.passed is True, f"blocked by {verdict.blocked_by}"


def test_plain_repeated_type_still_blocks():
    fw = DecisionFirewall()
    blocked = False
    for _ in range(6):
        verdict = _inspect(fw, "plan_trajectory")
        if not verdict.passed:
            blocked = True
            assert verdict.blocked_by == "action_loop"
            break
    assert blocked, "a same-type loop must still block without the novelty flag"
