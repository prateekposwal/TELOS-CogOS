"""Contract tests for telos/core/council/base.py.

Covers the ValidationSignal/CouncilVerdict/CouncilConfig dataclasses, the
abstract Validator interface, the voting-threshold resolution, and the
Council's evaluate() orchestration: DI computation with the DissentFloor,
MD computation, hard-veto semantics, voting-threshold validation, auto-
escalation, and the exception-swallow path.
"""
import numpy as np
import pytest

from telos.core.council.base import (
    Validator,
    ValidationSignal,
    CouncilVerdict,
    CouncilConfig,
    Council,
)
from telos.world.world import World
from telos.intent_ir import IntentIR


class TestValidationSignal:
    def test_defaults(self):
        s = ValidationSignal(validator_name="v", passed=True, confidence=0.9, reason="ok")
        assert s.evidence_weight == 0.0
        assert s.metadata == {}
        assert s.verdict == "PASS"

    def test_positional_construction(self):
        s = ValidationSignal("v", False, -0.8, "nope", 0.6)
        assert s.validator_name == "v"
        assert s.passed is False
        assert s.confidence == -0.8
        assert s.reason == "nope"
        assert s.evidence_weight == 0.6


class TestCouncilConfig:
    def test_unanimous(self):
        c = CouncilConfig(voting_threshold="unanimous")
        assert c.resolve_threshold(1) == 1
        assert c.resolve_threshold(4) == 4

    def test_supermajority(self):
        c = CouncilConfig(voting_threshold="supermajority_2/3")
        assert [c.resolve_threshold(n) for n in (1, 2, 3, 4, 6)] == [1, 2, 2, 3, 4]

    def test_simple_majority(self):
        c = CouncilConfig(voting_threshold="simple_majority")
        assert [c.resolve_threshold(n) for n in (1, 2, 3, 4, 6)] == [1, 2, 2, 3, 4]

    def test_unknown_threshold_falls_back_to_unanimous(self):
        c = CouncilConfig(voting_threshold="bogus")
        assert c.resolve_threshold(5) == 5

    def test_from_criticality(self):
        assert CouncilConfig.from_criticality("critical").voting_threshold == "unanimous"
        assert CouncilConfig.from_criticality("high").voting_threshold == "supermajority_2/3"
        assert CouncilConfig.from_criticality("medium").voting_threshold == "simple_majority"
        assert CouncilConfig.from_criticality("low").voting_threshold == "simple_majority"

    def test_from_criticality_preserves_unknown_label(self):
        c = CouncilConfig.from_criticality("default")
        assert c.decision_criticality == "default"
        assert c.voting_threshold == "simple_majority"


class TestValidatorAbstract:
    def test_abstract_members(self):
        assert "name" in Validator.__abstractmethods__
        assert "validate" in Validator.__abstractmethods__

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            Validator()


class TestCouncilVerdictSummary:
    def test_summary_all_clear(self):
        v = CouncilVerdict(
            validated=True,
            signals=[
                ValidationSignal("a", True, 0.9, "ok"),
                ValidationSignal("b", True, 0.8, "ok"),
            ],
            decision_integrity=1.0,
            mission_drift=0.25,
        )
        s = v.summary
        assert "2/2 produced" in s.replace("produced: ", "passed") or "2/2 passed" in s
        assert "DI=1.000" in s
        assert "MD=0.250" in s
        assert "all clear" in s

    def test_summary_blocked_and_escalated(self):
        v = CouncilVerdict(
            validated=False,
            signals=[
                ValidationSignal("safety_check", False, -0.9, "unsafe"),
                ValidationSignal("drift_check", True, 0.5, "uncertain"),
            ],
            escalation_signals=[
                ValidationSignal("drift_check", True, 0.5, "uncertain"),
            ],
        )
        s = v.summary
        assert "1/2 passed" in s
        assert "BLOCKED by: safety_check" in s
        assert "ESCALATED by: drift_check" in s


# ---------------------------------------------------------------------------
# Validator stubs used to drive Council evaluation behaviour.
# ---------------------------------------------------------------------------

class PassValidator(Validator):
    def __init__(self, name="pass_validator", confidence=0.9,
                 evidence_weight=0.5):
        self._name = name
        self._confidence = confidence
        self._evidence_weight = evidence_weight

    @property
    def name(self):
        return self._name

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(
            validator_name=self._name, passed=True, confidence=self._confidence,
            reason="ok", evidence_weight=self._evidence_weight,
        )


class BlockValidator(Validator):
    def __init__(self, name="block_validator", confidence=-0.9,
                 evidence_weight=0.5):
        self._name = name
        self._confidence = confidence
        self._evidence_weight = evidence_weight

    @property
    def name(self):
        return self._name

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(
            validator_name=self._name, passed=False, confidence=self._confidence,
            reason="blocked", evidence_weight=self._evidence_weight,
        )


class EscalateValidator(Validator):
    @property
    def name(self):
        return "escalate_validator"

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.5,
            reason="uncertain", evidence_weight=0.5,
        )


class BoomValidator(Validator):
    @property
    def name(self):
        return "boom_validator"

    def validate(self, world, intent, domain_facts=None):
        raise RuntimeError("validator exploded")


class ContextValidator(Validator):
    @property
    def name(self):
        return "context_validator"

    def validate(self, world, intent, domain_facts=None, context=None):
        self.last_context = context
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=1.0,
            reason="read context", evidence_weight=0.0,
        )


class TestCouncilEvaluate:
    def _world(self):
        return World(state=np.zeros(2))

    def test_no_validators_validates(self):
        c = Council()
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.validated is True
        assert verdict.signals == []
        assert verdict.decision_integrity == 1.0
        assert verdict.mission_drift == 0.0

    def test_register_and_count(self):
        c = Council()
        c.register(PassValidator())
        c.register(BlockValidator())
        assert c.validator_count == 2

    def test_all_pass_validates_with_di_md(self):
        c = Council()
        c.register(PassValidator())
        verdict = c.evaluate(
            self._world(), IntentIR(),
            predicted_state=np.array([1.0, 0.0]),
            observed_state=np.array([0.0, 0.0]),
        )
        assert verdict.validated is True
        assert verdict.decision_integrity == 1.0
        assert verdict.evidence_integrity == 1.0
        assert verdict.mission_drift == pytest.approx(1.0)

    def test_any_block_forces_validate_false_unanimous(self):
        c = Council(CouncilConfig(voting_threshold="unanimous"))
        c.register(PassValidator())
        c.register(BlockValidator())
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.validated is False
        assert verdict.blocking_validator == "block_validator"

    def test_hard_veto_block_ignores_majority(self):
        # A single safety-named blocker must veto even under simple majority.
        c = Council(CouncilConfig(voting_threshold="simple_majority"))
        c.register(PassValidator())
        c.register(PassValidator())
        c.register(BlockValidator(name="reality_validator"))
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.validated is False
        assert verdict.blocking_validator == "reality_validator"

    def test_non_hard_block_resolved_by_simple_majority(self):
        c = Council(CouncilConfig(voting_threshold="simple_majority"))
        c.register(PassValidator(name="p1"))
        c.register(PassValidator(name="p2"))
        c.register(BlockValidator(name="b1"))
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.validated is True
        assert verdict.blocking_validator == "b1"

    def test_soft_block_still_low_integrity(self):
        # Even when a non-hard single dissenter no longer vetoes, the DI must
        # be capped at DISSENT_FLOOR while the raw evidence integrality is kept.
        c = Council(CouncilConfig(voting_threshold="simple_majority"))
        c.register(PassValidator(name="p1"))
        c.register(PassValidator(name="p2"))
        c.register(BlockValidator(name="b1", confidence=-0.2, evidence_weight=0.5))
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.validated is True
        assert verdict.decision_integrity == pytest.approx(Council.DISSENT_FLOOR)
        assert verdict.evidence_integrity == pytest.approx(
            1.0 - (0.5 * abs(-0.2) / 1.5)
        )

    def test_autoconfigure_saturating_confidence_passes(self):
        # confidence 0.9 keeps a verdict PASS (no auto-escalation).
        c = Council()
        c.register(PassValidator(confidence=0.9))
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.escalation_requested is False
        assert verdict.signals[0].verdict == "PASS"

    def test_uncertain_confidence_autoescalates(self):
        c = Council()
        c.register(EscalateValidator())
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.escalation_requested is True
        assert verdict.escalation_reason is not None
        assert "escalate_validator" in verdict.escalation_reason
        assert verdict.signals[0].verdict == "ESCALATE"
        assert verdict.escalation_signals == [verdict.signals[0]]

    def test_validator_exception_surface_as_block(self):
        c = Council()
        c.register(BoomValidator())
        verdict = c.evaluate(self._world(), IntentIR())
        assert verdict.validated is False
        s = verdict.signals[0]
        assert s.passed is False
        assert s.validator_name == "boom_validator"
        assert "validator error" in s.reason
        assert s.evidence_weight == 0.5

    def test_context_kwarg_validator_receives_context(self):
        c = Council()
        cv = ContextValidator()
        c.register(cv)
        c.evaluate(self._world(), IntentIR())
        assert cv.last_context is not None


class TestCouncilDIComputation:
    def test_evidence_weights_modulate_di(self):
        signals = [
            ValidationSignal("x", True, 0.9, "ok", evidence_weight=0.5),
        ]
        c = Council()
        di, di_evidence = c._compute_decision_integrity(signals, None)
        assert di == 1.0
        assert di_evidence == 1.0

    def test_dissent_caps_reported_di(self):
        signals = [
            ValidationSignal("x", False, -0.5, "no", evidence_weight=0.5),
        ]
        c = Council()
        di, di_evidence = c._compute_decision_integrity(signals, None)
        assert di == pytest.approx(Council.DISSENT_FLOOR)
        assert di_evidence == pytest.approx(1.0 - 0.5 * 0.5 / 0.5)

    def test_evidence_weights_scale_ignored_evidence(self):
        signals = [
            ValidationSignal("y", False, -1.0, "no", evidence_weight=0.5),
        ]
        c = Council()
        di, di_evidence = c._compute_decision_integrity(
            signals, {"y": 0.5}
        )
        # ew becomes 0.25; ignored = 0.25*1.0 / total 0.25 -> 1 - 1 = 0
        assert di_evidence == pytest.approx(0.0)
        assert di == 0.0

    def test_mission_drift_norm(self):
        c = Council()
        md = c._compute_mission_drift(
            np.array([3.0, 4.0]), np.array([0.0, 0.0])
        )
        assert md == pytest.approx(5.0)

    def test_mission_drift_missing_returns_zero(self):
        c = Council()
        assert c._compute_mission_drift(None, np.zeros(2)) == 0.0
        assert c._compute_mission_drift(np.zeros(2), None) == 0.0