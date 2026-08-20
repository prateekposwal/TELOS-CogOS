"""
TELOS v6 — Phases 6/7/8 governance red-team + safety tests.

Proves the two fundamental v6 claims:

1. Can TELOS be forced to ACT when a mandatory capability gate is FAIL but
   utility/confidence/DI/other scores are maximal?
   -> NO. ACT is STRUCTURALLY impossible (conjunctive hard gates + governor).

2. Can repeated real evidence change TELOS's authority?
   -> YES. Upward when validated, downward when falsified (Reality Gap).

Also verifies DecisionMode distinctness (ACT/DEFER/ABSTAIN/ESCALATE/BLOCK) and
that WorldSpec.authorized_modes can remove ACT.
"""

import numpy as np

from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus, all_pass, from_dimensions,
)
from telos.core.governance.governor import (
    DecisionMode, DecisionGovernor, GovernorInput, GovernorDecision,
)
from telos.world.epistemic import (
    EpistemicState, RealityGapTracker, derive_epistemic_state,
)


# ─── Phase 7: non-tradeable hard gates ─────────────────────────────────────────

def test_all_pass_authorized():
    cap = all_pass()
    assert cap.authorized() is True
    assert cap.failed_gates() == []


def test_single_fail_vetoes_regardless_of_others():
    # Everything maximal EXCEPT risk_coverage=FAIL -> ACT must be impossible.
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.PASS,
        model_fidelity=CapabilityStatus.PASS,
        action_validity=CapabilityStatus.PASS,
        risk_coverage=CapabilityStatus.FAIL,   # the fatal one
        causal_confidence=CapabilityStatus.PASS,
        recovery=CapabilityStatus.PASS,
        authority=CapabilityStatus.PASS,
    )
    assert cap.authorized() is False
    assert "risk_coverage" in cap.failed_gates()


def test_high_di_utility_fidelity_cannot_override_failed_risk():
    # Simulate DI=1.0, utility=0.99, confidence=0.99, model_fidelity=0.98
    # (all encoded as PASS/optimal) BUT risk_coverage FAIL -> still unauthorized.
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.PASS,
        model_fidelity=CapabilityStatus.PASS,   # 0.98 fidelity -> PASS
        action_validity=CapabilityStatus.PASS,
        risk_coverage=CapabilityStatus.FAIL,    # 1.0
        causal_confidence=CapabilityStatus.PASS,
        recovery=CapabilityStatus.PASS,
        authority=CapabilityStatus.PASS,
    )
    assert cap.authorized() is False


def test_every_dimension_is_a_veto():
    # A FAIL in ANY mandatory dimension must veto.
    for dim in ("observability", "model_fidelity", "action_validity",
                "risk_coverage", "causal_confidence", "recovery", "authority"):
        cap = from_dimensions({dim: CapabilityStatus.FAIL})
        assert cap.authorized() is False, f"{dim} FAIL must veto ACT"


def test_limited_does_not_veto():
    # LIMITED is "ok" for authorization (doesn't veto), distinct from FAIL.
    cap = from_dimensions({"risk_coverage": CapabilityStatus.LIMITED})
    assert cap.authorized() is True


def test_unknown_does_not_authorize():
    # UNKNOWN does not grant authorization (a gap can't be waved through),
    # but is distinguished from FAIL.
    cap = from_dimensions(
        {"risk_coverage": CapabilityStatus.UNKNOWN},
        default=CapabilityStatus.UNKNOWN,
    )
    assert cap.authorized() is False


def test_profile_dict_reports_failed_gates():
    cap = from_dimensions({"model_fidelity": CapabilityStatus.FAIL})
    d = cap.to_dict()
    assert d["authorized"] is False
    assert d["profile"]["model_fidelity"] == "FAIL"


# ─── Phase 6: DecisionGovernor distinct modes ──────────────────────────────────

def test_governor_act_when_all_ok():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.KNOWN,
        DI=0.9, MD=0.1,
    ))
    assert dec.mode == DecisionMode.ACT
    assert dec.allows_act


def test_governor_block_on_hard_constraint_violation():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.KNOWN,
        DI=1.0, MD=0.95,          # mission drift -> risk proxy above threshold
        hard_constraint_violation=True,
    ))
    assert dec.mode == DecisionMode.BLOCK


def test_governor_defer_when_capability_insufficient_non_boundary():
    # risk_coverage FAIL is a hard boundary -> BLOCK. A non-boundary insufficiency
    # (e.g. causal_confidence FAIL) -> DEFER (could act once restored).
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=from_dimensions({"causal_confidence": CapabilityStatus.FAIL}),
        epistemic_state=EpistemicState.KNOWN,
        DI=0.7, MD=0.1,
    ))
    assert dec.mode == DecisionMode.DEFER


def test_governor_block_on_authority_fail():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=from_dimensions({"authority": CapabilityStatus.FAIL}),
        epistemic_state=EpistemicState.KNOWN,
    ))
    assert dec.mode == DecisionMode.BLOCK


def test_governor_abstain_on_unmodeled():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.UNMODELED,
        DI=1.0, MD=0.0,
    ))
    assert dec.mode == DecisionMode.ABSTAIN


def test_governor_defer_on_uncertain_when_explicitly_requested():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.UNCERTAIN,
        DI=0.9, MD=0.1,
        defer_requested=True,
    ))
    assert dec.mode == DecisionMode.DEFER


def test_governor_act_on_uncertain_when_not_requested():
    # A routine untested-but-authorized cycle must still ACT (strictness comes
    # from capability FAIL, not the normal UNCERTAIN label).
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.UNCERTAIN,
        DI=0.9, MD=0.1,
        defer_requested=False,
    ))
    assert dec.mode == DecisionMode.ACT


def test_governor_modes_are_distinct():
    assert len({DecisionMode.ACT, DecisionMode.DEFER, DecisionMode.ABSTAIN,
                DecisionMode.ESCALATE, DecisionMode.BLOCK}) == 5


def test_world_removing_act_from_authorized_modes_blocks_act():
    g = DecisionGovernor()
    # WorldSpec says ACT is not permitted here -> governor cannot emit ACT.
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.KNOWN,
        authorized_modes={"DEFER", "ABSTAIN", "ESCALATE", "BLOCK"},  # no ACT
        DI=1.0, MD=0.0,
    ))
    assert dec.mode != DecisionMode.ACT


# ─── Phase 4/5 + 7: learning changes authority (up AND down) ───────────────────

def test_learning_increases_authority_when_validated():
    tracker = RealityGapTracker()
    # Repeated accurate predictions -> high fidelity -> model_fidelity PASS.
    for _ in range(10):
        tracker.record("m", np.array([0.0, 0.0]), np.array([0.02, 0.02]))
    fid = tracker.model_fidelity("m")
    assert fid is not None and fid > 0.7
    cap = from_dimensions({
        "model_fidelity": CapabilityStatus.PASS if fid >= 0.5 else CapabilityStatus.FAIL,
    })
    assert cap.authorized() is True


def test_learning_decreases_authority_when_falsified():
    tracker = RealityGapTracker()
    # Repeated wrong predictions -> mean_gap large -> fidelity low -> FAIL.
    for _ in range(10):
        tracker.record("m", np.array([0.0, 0.0]), np.array([2.0, 2.0]))
    fid = tracker.model_fidelity("m")
    assert fid is not None
    status = CapabilityStatus.FAIL if fid < 0.5 else CapabilityStatus.PASS
    cap = from_dimensions({"model_fidelity": status})
    # With low fidelity the model_fidelity gate FAILs and ACT becomes impossible.
    assert cap.authorized() is (status != CapabilityStatus.FAIL)
    assert fid < 0.5


def test_epistemic_state_tracks_learning():
    # Untested -> UNCERTAIN (not KNOWN).
    es_untested = derive_epistemic_state(
        model_fidelity=None, tested=False, composite_uncertainty=0.1)
    assert es_untested == EpistemicState.UNCERTAIN
    # Validated low-uncertainty -> KNOWN.
    es_known = derive_epistemic_state(
        model_fidelity=0.9, tested=True, composite_uncertainty=0.1)
    assert es_known == EpistemicState.KNOWN


def test_reality_gap_feeds_governor_authorization():
    # Even if DI/utility are maximal, a model that keeps mispredicting pushes
    # model_fidelity below threshold -> governor cannot ACT.
    tracker = RealityGapTracker()
    for _ in range(10):
        tracker.record("m", np.array([0.0]), np.array([5.0]))
    fid = tracker.model_fidelity("m")
    cap = from_dimensions({
        "model_fidelity": CapabilityStatus.FAIL if fid < 0.5 else CapabilityStatus.PASS,
    })
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=cap,
        epistemic_state=EpistemicState.UNCERTAIN,
        DI=1.0, MD=0.0,   # maximal DI/MD but model fidelity FAIL
    ))
    assert dec.mode != DecisionMode.ACT


# ─── ESCALATE policy (TELOS v6 — per-world advisory vs required) ──────────────

def test_required_escalation_is_hard_stop_without_human_approval():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.KNOWN,
        DI=0.9, MD=0.1,
        escalation_requested=True,
        escalation_policy="required",
        human_authorized=False,
    ))
    assert dec.mode == DecisionMode.ESCALATE
    assert dec.hard_stop is True            # structural, not advisory
    assert dec.allows_act is False


def test_required_escalation_released_by_human_approval():
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.KNOWN,
        DI=0.9, MD=0.1,
        escalation_requested=True,
        escalation_policy="required",
        human_authorized=True,
    ))
    # capability all-pass + human authorization -> proceeds to ACT
    assert dec.mode == DecisionMode.ACT
    assert dec.hard_stop is False


def test_advisory_escalation_proceeds_and_logs():
    # Low-risk world preserves current behavior: ESCALATE does not suppress.
    g = DecisionGovernor()
    dec = g.evaluate(GovernorInput(
        capability=all_pass(),
        epistemic_state=EpistemicState.UNCERTAIN,
        DI=0.9, MD=0.1,
        escalation_requested=True,
        escalation_policy="advisory",
    ))
    assert dec.mode == DecisionMode.ESCALATE
    assert dec.hard_stop is False           # proceeds; act logs escalation


def test_defer_abstain_block_are_always_hard_stops():
    g = DecisionGovernor()
    cases = [
        (GovernorInput(capability=all_pass(), epistemic_state=EpistemicState.UNMODELED), DecisionMode.ABSTAIN),
        (GovernorInput(capability=from_dimensions({"causal_confidence": CapabilityStatus.FAIL}),
                       epistemic_state=EpistemicState.KNOWN), DecisionMode.DEFER),
        (GovernorInput(capability=all_pass(), epistemic_state=EpistemicState.KNOWN,
                       hard_constraint_violation=True), DecisionMode.BLOCK),
    ]
    for inp, expected in cases:
        dec = g.evaluate(inp)
        assert dec.mode == expected
        assert dec.hard_stop is True


def test_worldspec_escalation_policy_validation():
    from telos.core.contracts.domain_model import WorldSpec
    good = WorldSpec(name="w", state_dim=2, escalation_policy="required")
    assert good.validate() is None
    bad = WorldSpec(name="w", state_dim=2, escalation_policy="always")
    assert bad.validate() is not None
    d = good.to_dict()
    assert d["escalation_policy"] == "required"


# ─── Over-conservatism fixes (V1 MD smoothing, V2 single-dissenter) ────────────
# Prove the ACTUAL safety invariant survives: genuine FAIL gates still veto,
# but a single non-critical dissenter / a single transient MD spike do NOT.

from telos.core.council.base import Council, CouncilConfig, ValidationSignal
from telos.world.world import World


class _ProbeValidator:
    """Minimal validator helper for council tests."""
    def __init__(self, name, passed, confidence=0.9, weight=0.5, hard=False):
        self._name = name
        self._passed = passed
        self._hard = hard
        self._vw = confidence
        self._ew = weight

    @property
    def name(self):
        return self._name

    def validate(self, world, intent, domain_facts=None):
        return ValidationSignal(
            validator_name=self._name, passed=self._passed,
            confidence=self._vw, reason="probe",
            evidence_weight=self._ew,
            metadata={"hard_veto": self._hard},
        )


def test_single_dissenter_not_refused_under_majority():
    """V2: one non-critical dissenter in a healthy majority must not refuse."""
    council = Council(config=CouncilConfig(voting_threshold="simple_majority"))
    for v in ["health", "reality", "mission", "memory", "planning"]:
        council.register(_ProbeValidator(v, passed=True, weight=0.5))
    council.register(_ProbeValidator("analystX", passed=False, weight=0.5))
    world = World(state=np.zeros(2))
    verdict = council.evaluate(world, None)
    # 5 approve, 1 block, n=6 -> simple_majority threshold=4 -> validated True
    assert verdict.validated is True


def test_hard_veto_validator_always_blocks():
    """V2: a genuine risk/authority-style BLOCK must veto regardless of majority."""
    council = Council(config=CouncilConfig(voting_threshold="simple_majority"))
    for v in ["health", "reality", "mission", "memory", "planning"]:
        council.register(_ProbeValidator(v, passed=True, weight=0.5))
    council.register(_ProbeValidator("RiskValidator", passed=False, weight=0.5))
    world = World(state=np.zeros(2))
    verdict = council.evaluate(world, None)
    assert verdict.validated is False  # risk substring -> hard veto


def test_genuine_fail_still_vetoes_governance():
    """The conjunctive-veto fuel for the above: a FAIL gate still blocks ACT."""
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.PASS, model_fidelity=CapabilityStatus.PASS,
        action_validity=CapabilityStatus.PASS, risk_coverage=CapabilityStatus.PASS,
        causal_confidence=CapabilityStatus.PASS, recovery=CapabilityStatus.PASS,
        authority=CapabilityStatus.FAIL,   # genuine FAIL
    )
    dec = DecisionGovernor().evaluate(GovernorInput(
        capability=cap, epistemic_state=EpistemicState.KNOWN, DI=1.0, MD=0.0))
    assert dec.mode == DecisionMode.BLOCK
    assert dec.hard_stop is True


def test_unanimous_council_still_blocks_on_any_dissent():
    """Unanimous config preserves the strict behavior when explicitly chosen."""
    council = Council(config=CouncilConfig(voting_threshold="unanimous"))
    for v in ["health", "reality", "mission", "memory", "planning"]:
        council.register(_ProbeValidator(v, passed=True, weight=0.5))
    council.register(_ProbeValidator("analystX", passed=False, weight=0.5))
    verdict = council.evaluate(World(state=np.zeros(2)), None)
    assert verdict.validated is False


def test_evidence_integrity_decoupled_from_floor():
    """V2: reported DI caps at DISSENT_FLOOR, but evidence_integrity reflects the
    truly-minor dissent (so causal/recovery capability gates are not spuriously
    failed by one dissenter's floor cap)."""
    council = Council(config=CouncilConfig(voting_threshold="simple_majority"))
    for v in ["health", "reality", "mission", "memory", "planning"]:
        council.register(_ProbeValidator(v, passed=True, weight=1.0))
    council.register(_ProbeValidator("analystX", passed=False, weight=1.0))
    verdict = council.evaluate(World(state=np.zeros(2)), None)
    assert verdict.validated is True
    # reported DI floored (any block caps at 0.3)
    assert verdict.decision_integrity <= Council.DISSENT_FLOOR + 1e-9
    # evidence integrity high (single minor dissent in a 5/6 majority)
    assert verdict.evidence_integrity > 0.5
