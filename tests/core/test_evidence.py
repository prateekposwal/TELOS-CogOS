"""Contract tests for telos/core/council/validators/evidence.py.

EvidenceProvenanceValidator scores a candidate intent against the
falsification record: the RealityGapTracker's world-model state plus the
intent-type no-action history. Genuine inquiry types are never penalised.
"""
import numpy as np

from telos.core.council.validators.evidence import (
    EvidenceProvenanceValidator,
    FALSIFICATION_DISSENT_AFTER,
)
from telos.world.world import World
from telos.world.epistemic import RealityGapTracker
from telos.intent_ir import IntentIR


def _clean_context():
    return {
        "reality_gap_tracker": None,
        "intent_history": {
            "consecutive_no_action": 0,
            "total_no_action": 0,
            "recent_blocks": 0,
        },
    }


class TestEvidenceProvenanceValidator:
    def test_module_constants(self):
        assert FALSIFICATION_DISSENT_AFTER == 3

    def test_name(self):
        assert EvidenceProvenanceValidator().name == "EvidenceProvenanceValidator"

    def test_no_intent_is_neutral(self):
        sig = EvidenceProvenanceValidator().validate(World(state=np.zeros(2)), None)
        assert sig.passed is True
        assert sig.confidence == 0.0
        assert sig.evidence_weight == 0.0

    def test_fresh_type_passes_high_confidence(self):
        sig = EvidenceProvenanceValidator().validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context=_clean_context(),
        )
        assert sig.passed is True
        assert sig.confidence == 0.7
        assert sig.evidence_weight == 0.3
        assert sig.metadata["intent_type"] == "navigate"

    def test_inquiry_type_never_penalised(self):
        v = EvidenceProvenanceValidator()
        ctx = {"intent_history": {"consecutive_no_action": 9, "total_no_action": 12,
                                  "recent_blocks": 3}}
        for intent_type in (
            "inquiry", "inquiry_explore", "inquiry_recalibrate",
            "inquiry_resolve", "curiosity_explore", "perceive", "memory_miss",
        ):
            sig = v.validate(
                World(state=np.zeros(2)),
                IntentIR(intent_type=intent_type, confidence=0.6),
                context=ctx,
            )
            assert sig.passed is True, intent_type
            assert sig.confidence == 0.4
            assert sig.metadata["inquiry"] is True
            assert sig.evidence_weight == 0.2

    def test_consecutive_no_action_triggers_dissent_at_boundary(self):
        v = EvidenceProvenanceValidator()
        world = World(state=np.zeros(2))

        sig_ok = v.validate(
            world, IntentIR(intent_type="navigate", confidence=0.6),
            context={"intent_history": {"consecutive_no_action": 2,
                                        "total_no_action": 2, "recent_blocks": 0}},
        )
        assert sig_ok.passed is True

        sig = v.validate(
            world, IntentIR(intent_type="navigate", confidence=0.6),
            context={"intent_history": {"consecutive_no_action": 3,
                                        "total_no_action": 3, "recent_blocks": 0}},
        )
        assert sig.passed is False
        assert sig.confidence == -0.7
        assert sig.evidence_weight == 0.6
        assert "falsified loop" in sig.reason
        assert sig.metadata["consecutive_no_action"] == 3

    def test_high_total_no_action_dissents_even_without_streak(self):
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context={"intent_history": {"consecutive_no_action": 2,
                                        "total_no_action": 5, "recent_blocks": 1}},
        )
        assert sig.passed is False
        assert "pattern of non-execution" in sig.reason

    def test_two_no_actions_is_not_yet_a_dissent(self):
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context={"intent_history": {"consecutive_no_action": 2,
                                        "total_no_action": 2, "recent_blocks": 1}},
        )
        assert sig.passed is True

    def test_falsified_model_warns_but_does_not_dissent_alone(self):
        tracker = RealityGapTracker()
        tracker.record("world", np.zeros(4), np.full(4, 5.0))
        assert tracker.model("world").is_falsified is True

        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context={"reality_gap_tracker": tracker, "intent_history": _clean_context()},
        )
        assert sig.passed is True
        assert sig.confidence == 0.3
        assert "world model falsified" in sig.reason
        assert sig.reason.endswith("(not yet dissenting)")

    def test_falsified_model_plus_streak_dissents_with_both_reasons(self):
        tracker = RealityGapTracker()
        tracker.record("world", np.zeros(4), np.full(4, 5.0))
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context={
                "reality_gap_tracker": tracker,
                "intent_history": {"consecutive_no_action": 4,
                                   "total_no_action": 5, "recent_blocks": 2},
            },
        )
        assert sig.passed is False
        assert "world model falsified" in sig.reason
        assert "falsified loop" in sig.reason
        assert sig.metadata["model_falsified"] is True

    def test_untested_model_is_not_falsified(self):
        # model() auto-creates an untested ModelRealityGap -> not falsified.
        tracker = RealityGapTracker()
        v = EvidenceProvenanceValidator()
        sig = v.validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context={"reality_gap_tracker": tracker, "intent_history": _clean_context()},
        )
        assert sig.passed is True
        assert sig.confidence == 0.7

    def test_none_context_defaults_to_clean(self):
        sig = EvidenceProvenanceValidator().validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context=None,
        )
        assert sig.passed is True

    def test_missing_context_key_defaults_clean(self):
        sig = EvidenceProvenanceValidator().validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="navigate", confidence=0.6),
            context={"other_key": 1},
        )
        assert sig.passed is True