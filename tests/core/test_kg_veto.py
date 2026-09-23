"""
KnowledgeGraph approach-veto grounding — canonical-rule regression.

MemoryAdvisor's KG path must NOT veto an approach on (a) an ungrounded domain
('unknown'/missing) or (b) a not-evidence reason such as `resource_exhaustion`
(budget starvation = a compute condition, not an approach falsification).
Those two bugs produced the live `blended_inquiry` forever-veto.
"""
from types import SimpleNamespace

import numpy as np

from telos.core.council.validators.memory import MemoryAdvisor
from telos.core.knowledge.graph import KnowledgeGraph, ProjectNode
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.governance.recovery_types import NOT_EVIDENCE_APPROACH_FAILURE_REASONS
from telos.intent_ir import IntentIR


def _kg_with_node(domain, reason, cycle=None):
    kg = KnowledgeGraph()
    params = {} if cycle is None else {"cycle": cycle}
    node = ProjectNode(node_id="n1", domain=domain, approach="blended_inquiry",
                       outcome=0.15, failure_reason=reason, params=params)
    kg._nodes["n1"] = node
    kg._domain_index[domain].add("n1")
    return kg


def _validate(domain, reason, cycle=None, now_cycle=None):
    kg = _kg_with_node(domain, reason, cycle=cycle)
    advisor = MemoryAdvisor(SkillLibrary(), knowledge_graph=kg)
    world = SimpleNamespace(state=np.zeros(2), domain=domain, metadata={})
    intent = IntentIR(intent_type="blended_inquiry", confidence=0.8, params={"k": 1})
    context = None if now_cycle is None else {"cycle_count": now_cycle}
    return advisor.validate(world, intent, context=context)


def test_resource_exhaustion_is_not_evidence():
    assert "resource_exhaustion" in NOT_EVIDENCE_APPROACH_FAILURE_REASONS


def test_grounded_real_failure_vetoes():
    sig = _validate("gridworld", "sensor_divergence")
    assert sig.passed is False
    assert "KnowledgeGraph" in sig.reason


def test_resource_exhaustion_does_not_veto():
    sig = _validate("gridworld", "resource_exhaustion")
    assert sig.passed is True


def test_resource_exhaustion_does_not_block_even_in_unknown_domain():
    # The live bug: a `resource_exhaustion` node under domain 'unknown' vetoed
    # `blended_inquiry` forever. The reason gate (not a domain gate) excludes it.
    sig = _validate("unknown", "resource_exhaustion")
    assert sig.passed is True


def test_known_domain_genuine_failure_still_blocks():
    # Design preserved (v8): a GENUINE approach failure blocks regardless of
    # domain — only non-evidence reasons are filtered.
    sig = _validate("unknown", "blocked_by_terrain_wall")
    assert sig.passed is False


def test_recent_genuine_failure_still_blocks():
    sig = _validate("gridworld", "sensor_divergence", cycle=4950, now_cycle=5000)
    assert sig.passed is False, "a recent real failure must still block"


def test_stale_genuine_failure_no_longer_blocks():
    from telos.core.council.validators.memory import KG_VETO_STALE_CYCLES
    sig = _validate("gridworld", "sensor_divergence",
                    cycle=1, now_cycle=1 + KG_VETO_STALE_CYCLES + 1)
    assert sig.passed is True, "stale validation is not current falsification"


def test_unstamped_node_keeps_legacy_veto():
    # No cycle stamp -> legacy behavior (block), so nothing silently weakens.
    sig = _validate("gridworld", "sensor_divergence", cycle=None, now_cycle=999999)
    assert sig.passed is False
