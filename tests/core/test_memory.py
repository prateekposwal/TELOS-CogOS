"""Contract tests for telos/core/council/validators/memory.py.

MemoryAdvisor scores candidate intents against the SkillLibrary's learned
lessons, the FailureLedger's Kintsugi record, and the KnowledgeGraph's
proven/failed approaches.
"""
import hashlib

import numpy as np
import pytest

from telos.core.council.validators.memory import MemoryAdvisor
from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.ledger.skill_library import SkillLibrary, Skill
from telos.core.infra_manager.failure_ledger import FailureLedger, FailureRecord
from telos.world.world import World
from telos.intent_ir import IntentIR


def _index_skill(library, state, utility):
    fingerprint = hashlib.md5(state.tobytes()).hexdigest()[:12]
    library.index_skill(Skill(
        skill_id=f"s{len(library.skills)}", fingerprint=fingerprint,
        trajectory=None, utility_score=utility,
    ))


def _empty_skill_lib():
    return SkillLibrary()


class TestMemoryAdvisorBasics:
    def test_name(self):
        assert MemoryAdvisor(_empty_skill_lib()).name == "MemoryAdvisor"

    def test_no_intent_is_neutral(self):
        sig = MemoryAdvisor(_empty_skill_lib()).validate(World(state=np.zeros(2)), None)
        assert sig.passed is True
        assert sig.confidence == 0.0
        assert sig.evidence_weight == 0.0

    def test_connect_returns_self_and_wires_services(self):
        ledger = FailureLedger()
        advisor = MemoryAdvisor(_empty_skill_lib())
        assert advisor.failure_ledger is None
        ret = advisor.connect(failure_ledger=ledger)
        assert ret is advisor
        assert advisor.failure_ledger is ledger


class TestMemoryAdvisorSkillLibrary:
    def test_clean_intent_passes_no_contradiction(self):
        sig = MemoryAdvisor(_empty_skill_lib()).validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="move", confidence=0.8),
        )
        assert sig.passed is True
        assert sig.confidence == 0.5
        assert "no contradictory historical evidence" in sig.reason
        assert sig.evidence_weight == 0.1

    def test_positive_precedent_passes(self):
        library = _empty_skill_lib()
        state = np.array([1.0, 2.0])
        _index_skill(library, state, 0.9)
        sig = MemoryAdvisor(library).validate(
            World(state=state), IntentIR(intent_type="move", confidence=0.8)
        )
        assert sig.passed is True
        assert sig.confidence == 0.6
        assert "precedents are positive" in sig.reason

    def test_low_utility_skill_blocks(self):
        library = _empty_skill_lib()
        state = np.array([1.0, 2.0])
        _index_skill(library, state, 0.15)
        sig = MemoryAdvisor(library).validate(
            World(state=state), IntentIR(intent_type="move", confidence=0.8)
        )
        assert sig.passed is False
        assert sig.confidence == -0.7
        assert "historical skill" in sig.reason
        assert sig.metadata["worst_skill_id"] == "s0"
        assert sig.metadata["worst_utility"] == 0.15
        assert sig.evidence_weight == pytest.approx(0.3 + 0.2 * (1.0 - 0.15))

    def test_omega_other_raises_evidence_tolerance(self):
        library = _empty_skill_lib()
        sig = MemoryAdvisor(library).validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="move", confidence=0.8),
            omega_vector={"other": 0.9},
        )
        # tolerance = 1.0 - 0.3*o where o=0.9 -> 0.73 -> ew = 0.1 * 0.73
        assert sig.evidence_weight == pytest.approx(0.073)


class TestMemoryAdvisorKintsugi:
    def test_matching_failure_blocks(self):
        ledger = FailureLedger()
        ledger.record_direct(FailureRecord(
            failure_id="fail_abc12345", cycle=1, timestamp=0.0,
            failure_type="council_block", severity=0.9, root_cause="council_rejection",
            blocked_by="navigate",
        ))
        advisor = MemoryAdvisor(_empty_skill_lib(), failure_ledger=ledger)
        sig = advisor.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.8),
        )
        assert sig.passed is False
        assert "Kintsugi" in sig.reason
        assert sig.reason.startswith("Kintsugi: past failure #")
        assert sig.metadata["kintsugi_match_count"] == 1
        assert sig.metadata["worst_failure_id"] == "fail_abc12345"
        assert sig.metadata["worst_failure_type"] == "council_block"
        assert sig.metadata["kintsugi_trend"] == "council_rejection"

    def test_governance_and_simulation_root_causes_are_skipped(self):
        ledger = FailureLedger()
        ledger.record_direct(FailureRecord(
            failure_id="fail_gov", cycle=1, timestamp=0.0,
            failure_type="firewall_block", severity=0.9,
            root_cause="governance_intervention", blocked_by="navigate",
        ))
        advisor = MemoryAdvisor(_empty_skill_lib(), failure_ledger=ledger)
        sig = advisor.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.8),
        )
        assert sig.passed is True
        assert "Kintsugi" not in sig.reason

    def test_pattern_exploit_move_match_blocks(self):
        ledger = FailureLedger()
        ledger.record_direct(FailureRecord(
            failure_id="fail_exploit", cycle=5, timestamp=0.0,
            failure_type="pattern_exploit", severity=0.7, root_cause="pattern_lock",
            blocked_by="0 1",
        ))
        advisor = MemoryAdvisor(_empty_skill_lib(), failure_ledger=ledger)
        sig = advisor.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="move", confidence=0.8,
                     params={"action_vector": np.array([0, 1])}),
        )
        assert sig.passed is False
        assert "Kintsugi" in sig.reason


class TestMemoryAdvisorKnowledgeGraph:
    def test_proven_approach_passes_high_confidence(self):
        kg = KnowledgeGraph()
        kg.record_success("gridworld", "fastest_route", 0.9)
        advisor = MemoryAdvisor(_empty_skill_lib(), knowledge_graph=kg)
        world = World(state=np.zeros(2))
        world.domain = "gridworld"
        sig = advisor.validate(
            world, IntentIR(intent_type="fastest_route", confidence=0.8, params={"a": 1})
        )
        assert sig.passed is True
        assert sig.confidence == 0.8
        assert "proven solution" in sig.reason
        assert sig.metadata["proven_approach"] == "fastest_route"

    def test_failed_approach_blocks(self):
        kg = KnowledgeGraph()
        kg.record_failure("gridworld", "slow_mess", 0.2, "full")
        advisor = MemoryAdvisor(_empty_skill_lib(), knowledge_graph=kg)
        world = World(state=np.zeros(2))
        world.domain = "gridworld"
        sig = advisor.validate(
            world, IntentIR(intent_type="slow_mess", confidence=0.8, params={"a": 1})
        )
        assert sig.passed is False
        assert sig.confidence == -0.6
        assert "failed" in sig.reason and "previously" in sig.reason
        assert sig.evidence_weight == 0.7