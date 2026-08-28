"""Regression tests for the plateau root-cause fix (2026-08-29).

Pattern under test — governance suppression is not evidence, and stale
validation is not current falsification (Λ6.5):

  The live pipeline sat at DI=0.3 for tens of thousands of cycles because the
  trap's OWN governance blocks were misattributed as evidence:
   1) vetoed selections were recorded as KnowledgeGraph APPROACH failures
      (outcome 0.15, failure_reason="governance_intervention"),
   2) MemoryAdvisor's KG path blocked the suppressed approach (its ledger path
      already filters governance_intervention — the KG path must mirror it),
   3) EvidenceProvenanceValidator scored the designed escape type
      (goal_seek_recovery) falsified by the arming counter its suppressed
      attempts accumulated ("produced no action for 1204 consecutive cycles"),
   4) the RealityGapTracker's sticky ever_falsified + frozen recent_gap vetoed
      the act-phase capability gate forever (stale evidence as current truth).
"""
import numpy as np

from telos.world.epistemic import (
    RealityGapTracker, STALE_MODEL_VALIDATION_CYCLES,
)
from telos.world.world import World
from telos.intent_ir import IntentIR
from telos.core.council.validators.evidence import EvidenceProvenanceValidator
from telos.core.council.validators.memory import MemoryAdvisor
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.governance.recovery_types import STAGNATION_EXEMPT_RECOVERY_TYPES


def _evidence_ctx(no_action=0, total=0, tracker=None, cycle=1000):
    return {
        "intent_history": {
            "consecutive_no_action": no_action,
            "total_no_action": total,
            "recent_blocks": 0,
        },
        "reality_gap_tracker": tracker,
        "cycle_count": cycle,
    }


class TestEvidenceRecoveryExemption:
    """The designed escape type must never be scored falsified by the
    counter its own suppressed attempts accumulate."""

    def test_recovery_type_never_dissents_even_with_huge_counter(self):
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="goal_seek_recovery", confidence=0.6),
            context=_evidence_ctx(no_action=1204, total=2000),
        )
        assert sig.passed is True, sig.reason
        assert "recovery" in sig.metadata and sig.metadata["recovery"]

    def test_non_recovery_type_still_dissents(self):
        """The falsified-loop pressure for regular types is preserved."""
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context=_evidence_ctx(no_action=5, total=7),
        )
        assert sig.passed is False, "falsified regular type must still dissent"

    def test_blended_inquiry_still_dissents(self):
        """blended_inquiry is intentionally NOT in the evidence inquiry set
        (it was the pathology type) — its dissent pressure stays by design."""
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="blended_inquiry", confidence=0.6),
            context=_evidence_ctx(no_action=5, total=7),
        )
        assert sig.passed is False, "blended_inquiry falsified-loop dissent is designed"


class TestEvidenceModelRecency:
    """Stale gap history is frozen, not fresh — absence of validation is
    uncertainty, not ongoing falsification (mirrors act-then-learn)."""

    def _tracker(self, gap: float, at_cycle: int):
        t = RealityGapTracker()
        t.record("world", np.array([0.0]), np.array([gap]), cycle=at_cycle)
        return t

    def test_fresh_high_gap_is_current_falsification(self):
        t = self._tracker(2.88, 900)
        sig = EvidenceProvenanceValidator().validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context=_evidence_ctx(no_action=5, total=7, tracker=t, cycle=920),
        )
        assert sig.passed is False
        assert "world model falsified" in sig.reason

    def test_stale_gap_is_not_current_falsification(self):
        t = self._tracker(2.88, 100)
        sig = EvidenceProvenanceValidator().validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context=_evidence_ctx(no_action=5, total=7, tracker=t,
                                  cycle=100 + STALE_MODEL_VALIDATION_CYCLES + 10),
        )
        # dissent is about the type counter; the model is NOT cited as
        # currently falsified
        assert "world model falsified" not in sig.reason

    def test_fidelity_stale_returns_none_not_frozen_veto(self):
        t = self._tracker(2.88, 100)
        assert t.model_fidelity("world", now_cycle=1000) is None, (
            "stale fidelity must be 'currently unvalidated', not a frozen veto"
        )
        assert t.model_fidelity("world", now_cycle=101) is not None


class TestMemoryAdvisorKGFilter:
    """Governance-suppressed KG failures must not block the approach
    (mirrors the failure-ledger filter) — the live poisoned node was
    'goal_seek_recovery outcome=0.15 failure_reason=governance_intervention'."""

    def _advisor_with_kg(self):
        sl = SkillLibrary()
        advisor = MemoryAdvisor(sl)
        kg = KnowledgeGraph()
        advisor.connect(knowledge_graph=kg)
        return advisor, kg

    def test_governance_suppressed_failure_does_not_block(self):
        advisor, kg = self._advisor_with_kg()
        kg.record("unknown", "goal_seek_recovery", 0.15,
                  failure_reason="governance_intervention",
                  tags=["failure"])
        world = World(state=np.zeros(2))
        intent = IntentIR(intent_type="goal_seek_recovery", confidence=0.6,
                         params={"action_vector": [1, 0]})
        sig = advisor.validate(world, intent)
        assert sig.passed is True, sig.reason

    def test_genuine_failure_still_blocks(self):
        advisor, kg = self._advisor_with_kg()
        kg.record("unknown", "navigate", 0.15,
                  failure_reason="blocked_by_terrain_wall",
                  tags=["failure"])
        world = World(state=np.zeros(2))
        intent = IntentIR(intent_type="navigate", confidence=0.6,
                         params={"action_vector": [1, 0]})
        sig = advisor.validate(world, intent)
        assert sig.passed is False, "genuine approach failure must still block"
        assert "failed previously" in sig.reason

    def test_canonical_set_has_both_reasons(self):
        from telos.core.governance.recovery_types import GOVERNANCE_SUPPRESSION_REASONS
        assert "governance_intervention" in GOVERNANCE_SUPPRESSION_REASONS
        assert "simulation_divergence" in GOVERNANCE_SUPPRESSION_REASONS


class TestKnowledgeManagerAttribution:
    """A vetoed selection is never recorded as an approach failure."""

    def _result(self, firewall_blocked):
        from telos.core.runtime import PipelineResult
        from telos.core.types import PipelinePhase
        dt = type("DT", (), {
            "selected_intent": IntentIR(intent_type="goal_seek_recovery",
                                        confidence=0.6),
            "mission_drift": 1.9,
            "decision_integrity": 0.3,
        })()
        return PipelineResult(
            selected_trajectory=None, health_score=0.5,
            pipeline_phase=PipelinePhase.ACT,
            council_blocked=False, firewall_blocked=firewall_blocked,
            decision_integrity=0.3, mission_drift=1.9,
            decision_trace=dt,
        )

    def test_vetoed_trace_does_not_poison_kg(self):
        from telos.core.infra_manager.knowledge_manager import KnowledgeManager
        from telos.core.infra_manager.failure_ledger import FailureLedger
        km = KnowledgeManager(None, None, domain="unknown")
        kg = km.knowledge  # observe writes through recorder into this graph
        result = self._result(firewall_blocked=True)
        f = type("F", (), {"root_cause": "governance_intervention",
                           "blocked_by": "low_integrity",
                           "failure_type": "firewall_block",
                           "failure_id": "f1", "severity": 0.7,
                           "repair_outcome": None, "repair_effective": False,
                           "affected_entities": None})()
        km.observe(result, f, result.decision_trace)
        failed = kg.search_failures("unknown")
        approaches = [n.approach for n in failed]
        assert "goal_seek_recovery" not in approaches, (
            "vetoed selections must not be recorded as approach failures"
        )

    def test_unblocked_failure_still_records(self):
        from telos.core.infra_manager.knowledge_manager import KnowledgeManager
        km = KnowledgeManager(None, None, domain="unknown")
        kg = km.knowledge
        result = self._result(firewall_blocked=False)
        f = type("F", (), {"root_cause": "blocked_by_terrain_wall",
                           "blocked_by": "terrain",
                           "failure_type": "simulation_divergence",
                           "failure_id": "f2", "severity": 0.5,
                           "repair_outcome": None, "repair_effective": False,
                           "affected_entities": None})()
        km.observe(result, f, result.decision_trace)
        approaches = [n.approach for n in kg.search_failures("unknown")]
        assert "goal_seek_recovery" in approaches, (
            "a genuinely failed (unvetoed) approach must still be recorded"
        )


class TestCanonicalSets:
    def test_recovery_types_are_shared(self):
        # the evidence validator reads the SAME set as the stagnation armer
        from telos.core.council.validators.evidence import (
            STAGNATION_EXEMPT_RECOVERY_TYPES as ev_set,
        )
        assert ev_set == STAGNATION_EXEMPT_RECOVERY_TYPES
        assert "goal_seek_recovery" in STAGNATION_EXEMPT_RECOVERY_TYPES


class TestActRiskGateStaleness:
    """The act-phase risk gate must not sustain a FROZEN veto: during a
    governance-blocked streak no validation records arrive, so recent_mean_gap
    freezes. Stale evidence is not sustained divergence (Λ6.5)."""

    def test_fresh_high_gap_keeps_veto(self):
        from telos.core.phases.act import _md_with_staleness
        md, cat = _md_with_staleness(1.5, 1.5, 0.3, 2.0, 100, 99)
        assert md > 0.75, "fresh sustained divergence must still veto"

    def test_stale_high_gap_decays(self):
        from telos.core.phases.act import _md_with_staleness
        md, _ = _md_with_staleness(1.5, 1.5, 0.3, 2.0, 100, 50)
        assert md < 1.5, "stale gap must decay toward 0, not persist"
        md2, _ = _md_with_staleness(1.5, md, 0.3, 2.0, 101, 50)
        assert md2 < 0.75, "within ~2 stale cycles the veto must clear"

    def test_stale_frozen_catastrophe_suppressed(self):
        from telos.core.phases.act import _md_with_staleness
        _, cat = _md_with_staleness(2.5, 2.0, 0.3, 2.0, 100, 50)
        assert cat is False, "a frozen (stale) catastropic gap must not veto"

    def test_fresh_catastrophe_still_vetoes(self):
        from telos.core.phases.act import _md_with_staleness
        _, cat = _md_with_staleness(2.5, 2.0, 0.3, 2.0, 100, 99)
        assert cat is True, "a genuinely fresh out-of-band spike must veto"

    def test_fidelity_act_gate_short_window_unlocks_after_few_cycles(self):
        """The act gate uses a SHORT staleness window (the per-step gap is
        current for only a few cycles in a terrain-shifting world): a 300-cycle
        truth window would lock ACT out for ~300 cycles after one divergent
        step (the pre-fix stall was 1 move per ~50 cycles)."""
        t = RealityGapTracker()
        t.record("world", np.array([0.0]), np.array([1.0]), cycle=100)  # gap 1.0
        from telos.core.phases.act import ACT_FIDELITY_STALE_CYCLES
        assert ACT_FIDELITY_STALE_CYCLES == 5
        # fresh divergent gap still vetoes
        assert t.model_fidelity("world", now_cycle=101) == 0.0
        # long (council-truth) window still calls it fresh at 200
        assert t.model_fidelity("world", now_cycle=200) == 0.0
        # act gate window unlocks shortly after validation goes stale
        assert t.model_fidelity(
            "world", now_cycle=100 + ACT_FIDELITY_STALE_CYCLES + 1,
            stale_window=ACT_FIDELITY_STALE_CYCLES) is None
