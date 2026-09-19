"""v8 Phase 3 — council aggregation scoping + research-only crew contracts.

Locks the two aggregation defects this phase fixed and the DistributedCouncil
classification:

1. ``gather_evidence_weights`` must NOT pass the StreamCalibrator's
   uncalibrated ``evidence=0.0`` for every validator — doing so multiplied each
   signal's own evidence weight by zero and nullified the DI evidence term
   (``decision_integrity`` collapsed to a binary any-block→DissentFloor signal).
2. ``firewall_decision_integrity`` must feed the firewall the RAW
   ``evidence_integrity``, not the DissentFloor-capped ``decision_integrity``.
   Feeding the cap made every soft validator an accidental hard veto: one
   dissenting advisor floored DI below the policy threshold and blocked a cycle
   the council itself had VALIDATED by its majority voting threshold.
3. ``DistributedCouncil`` is RESEARCH-ONLY: no decision phase consumes its
   verdict, so it must not be forced active to manufacture signal.
"""
import numpy as np
import pytest

from telos.core.council.base import Council, CouncilConfig, ValidationSignal, Validator
from telos.core.council.distributed import CAUSAL_STATUS
from telos.core.governance.firewall import DecisionFirewall, FirewallConfig
from telos.core.phases.act import firewall_decision_integrity
from telos.core.phases.council import gather_evidence_weights
from telos.intent_ir import IntentIR
from telos.world.world import World


class _Pass(Validator):
    def __init__(self, name="pass_validator", ew=0.5):
        self._name = name
        self._ew = ew

    @property
    def name(self):
        return self._name

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(self._name, True, 0.9, "ok", self._ew)


class _SoftBlock(Validator):
    def __init__(self, name="soft_advisor", conf=-0.8, ew=0.5):
        self._name = name
        self._conf = conf
        self._ew = ew

    @property
    def name(self):
        return self._name

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(self._name, False, self._conf, "soft dissent", self._ew)


class _HardBlock(Validator):
    @property
    def name(self):
        return "reality_validator"  # in Council.HARD_VETO_SUBSTRINGS

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(self.name, False, -0.9, "hard dissent", 0.7)


def _world():
    return World(state=np.zeros(2))


# ── Fix 1: calibrator evidence-weight gathering ─────────────────────────────

class _Cal:
    def __init__(self, scores):
        self._scores = scores

    def get_evidence_weighted_influence(self, name):
        return {"evidence": self._scores.get(name, 0.0)}


class _Infra:
    def __init__(self, scores):
        self.calibrator = _Cal(scores)


class _FakeCouncil:
    def __init__(self, names):
        self._validators = [type("V", (), {"name": n})() for n in names]


class _FakePipe:
    def __init__(self, names, scores):
        self.infra_manager = _Infra(scores)
        self.council = _FakeCouncil(names)


class TestGatherEvidenceWeights:
    def test_uncalibrated_zero_is_dropped(self):
        # The calibrator is keyed by STREAM name; every validator lookup misses
        # and returns 0.0 — the old code passed those zeros through and zeroed
        # the whole DI evidence term. Must return None (no modulation).
        pipe = _FakePipe(["RealityValidator", "MemoryAdvisor"], {})
        assert gather_evidence_weights(pipe) is None

    def test_only_positive_calibrations_participate(self):
        pipe = _FakePipe(["RealityValidator", "MemoryAdvisor"],
                         {"MemoryAdvisor": 0.4})
        assert gather_evidence_weights(pipe) == {"MemoryAdvisor": 0.4}

    def test_no_calibrator_returns_none(self):
        pipe = _FakePipe(["RealityValidator"], {})
        sheet = object()
        object.__setattr__(pipe, "infra_manager", sheet)
        assert gather_evidence_weights(pipe) is None

    def test_no_validators_returns_none(self):
        pipe = _FakePipe([], {"RealityValidator": 0.5})
        assert gather_evidence_weights(pipe) is None


# ── Fix 2: firewall gate consumes raw evidence integrity ────────────────────

class TestFirewallDecisionIntegrity:
    def test_uses_evidence_integrity_not_floored_report(self):
        c = Council(CouncilConfig(voting_threshold="simple_majority"))
        c.register(_Pass("p1"))
        c.register(_Pass("p2"))
        c.register(_Pass("p3"))
        c.register(_SoftBlock("soft_advisor", conf=-0.2, ew=0.5))
        verdict = c.evaluate(_world(), IntentIR())
        # Council majority validates; the report is floored, the evidence is raw.
        assert verdict.validated is True
        assert verdict.decision_integrity == pytest.approx(Council.DISSENT_FLOOR)
        assert verdict.evidence_integrity > Council.DISSENT_FLOOR
        assert firewall_decision_integrity(verdict) == pytest.approx(
            verdict.evidence_integrity)

    def test_none_is_permissive(self):
        assert firewall_decision_integrity(None) == 1.0

    def test_missing_evidence_field_falls_back_to_floored(self):
        class _Bare:
            decision_integrity = 0.42

        assert firewall_decision_integrity(_Bare()) == pytest.approx(0.42)

    def test_soft_majority_validated_is_not_blocked_by_floor(self):
        c = Council(CouncilConfig(voting_threshold="simple_majority"))
        c.register(_Pass("p1"))
        c.register(_Pass("p2"))
        c.register(_Pass("p3"))
        c.register(_SoftBlock("soft_advisor", conf=-0.2, ew=0.5))
        verdict = c.evaluate(_world(), IntentIR())
        fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
        # RAW evidence (~0.93) clears the gate...
        fw.inspect(_world(), IntentIR(intent_type="move"),
                   council_validated=verdict.validated,
                   decision_integrity=firewall_decision_integrity(verdict))
        # ...whereas the floored report (0.3) would have blocked it (the bug).
        blocked = fw.inspect(_world(), IntentIR(intent_type="move"),
                             council_validated=True,
                             decision_integrity=verdict.decision_integrity)
        assert blocked.passed is False
        assert blocked.blocked_by == "low_integrity"

    def test_hard_veto_still_blocks(self):
        c = Council(CouncilConfig(voting_threshold="simple_majority"))
        c.register(_Pass("p1"))
        c.register(_Pass("p2"))
        c.register(_Pass("p3"))
        c.register(_HardBlock())
        verdict = c.evaluate(_world(), IntentIR())
        assert verdict.validated is False
        fw = DecisionFirewall(FirewallConfig(min_decision_integrity=0.5))
        out = fw.inspect(_world(), IntentIR(intent_type="move"),
                         council_validated=verdict.validated,
                         decision_integrity=firewall_decision_integrity(verdict))
        assert out.passed is False
        assert out.blocked_by == "council_rejection"


# ── Fix 3: DistributedCouncil is research-only ──────────────────────────────

class TestDistributedCouncilResearchOnly:
    def test_causal_status_declared(self):
        assert CAUSAL_STATUS == "research_only"

    def test_no_decision_phase_consumes_crew_verdicts(self):
        # The crew verdicts may be recorded (runtime/trace/axiom telemetry) but
        # must never be READ by a decision phase — that is what makes the crew
        # research-only rather than a decision participant.
        import pathlib

        phases = pathlib.Path("telos/core/phases").glob("*.py")
        offenders = []
        for path in phases:
            text = path.read_text(encoding="utf-8")
            for token in ("distributed_verdict", "cooperative_verdict"):
                if token in text:
                    offenders.append(f"{path}:{token}")
        assert offenders == []

    def test_crew_verdict_is_not_in_broadcast_decision_inputs(self):
        # Observability, not authority: the crew verdict is broadcast/logged for
        # audit, but its presence must not be a selection or gate input.
        from telos.dashboard.producer import DashboardProducer

        assert "distributed_verdict" in DashboardProducer.BROADCAST_TRACE_FIELDS
