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


def _kg_with_node(domain, reason):
    kg = KnowledgeGraph()
    node = ProjectNode(node_id="n1", domain=domain, approach="blended_inquiry",
                       outcome=0.15, failure_reason=reason)
    kg._nodes["n1"] = node
    kg._domain_index[domain].add("n1")
    return kg


def _validate(domain, reason):
    kg = _kg_with_node(domain, reason)
    advisor = MemoryAdvisor(SkillLibrary(), knowledge_graph=kg)
    world = SimpleNamespace(state=np.zeros(2), domain=domain, metadata={})
    intent = IntentIR(intent_type="blended_inquiry", confidence=0.8, params={"k": 1})
    return advisor.validate(world, intent)


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
