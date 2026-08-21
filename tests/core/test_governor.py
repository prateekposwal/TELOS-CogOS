"""
Honest contract tests for telos/core/governance/governor.py (DecisionGovernor).

The governor's non-negotiable property: it can only return ACT if the
capability authorization allows it AND ACT is in the world's authorized modes.
No scalar optimization can override a FAILED hard gate.
"""

import pytest

from telos.core.governance.governor import (
    DecisionGovernor,
    DecisionMode,
    GovernorDecision,
    GovernorInput,
)
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization,
    CapabilityStatus,
)
from telos.world.epistemic import EpistemicState


def decision(mode):
    return GovernorDecision(mode=mode, reason="")


@pytest.mark.parametrize("mode", ["ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"])
def test_decision_mode_enum_values(mode):
    assert DecisionMode(mode).value == mode


def test_default_input_acts():
    gov = DecisionGovernor()
    d = gov.evaluate(GovernorInput())
    assert d.mode == DecisionMode.ACT
    assert d.allows_act is True


def test_act_requires_all_capability_gates():
    cap = CapabilityAuthorization(model_fidelity=CapabilityStatus.FAIL)
    d = DecisionGovernor().evaluate(GovernorInput(capability=cap))
    assert d.mode == DecisionMode.DEFER
    assert d.metadata["failed_gates"] == ["model_fidelity"]
    assert d.decision_integrity == 1.0


def test_non_boundary_capability_fail_is_defer_not_block():
    # observability is not a hard boundary gate -> DEFER (action could be
    # valid once the capability is restored), never BLOCK.
    cap = CapabilityAuthorization(observability=CapabilityStatus.FAIL)
    d = DecisionGovernor().evaluate(GovernorInput(capability=cap))
    assert d.mode == DecisionMode.DEFER


def test_authority_boundary_fail_blocks():
    # authority/risk_coverage are boundary gates -> BLOCK when BLOCK is an
    # authorized mode.
    cap = CapabilityAuthorization(authority=CapabilityStatus.FAIL)
    d = DecisionGovernor().evaluate(GovernorInput(capability=cap))
    assert d.mode == DecisionMode.BLOCK


def test_risk_coverage_boundary_fail_blocks():
    cap = CapabilityAuthorization(risk_coverage=CapabilityStatus.FAIL)
    d = DecisionGovernor().evaluate(GovernorInput(capability=cap))
    assert d.mode == DecisionMode.BLOCK


def test_boundary_fail_defers_when_block_not_authorized():
    cap = CapabilityAuthorization(authority=CapabilityStatus.FAIL)
    d = DecisionGovernor().evaluate(
        GovernorInput(capability=cap, authorized_modes={"ACT", "DEFER"})
    )
    assert d.mode == DecisionMode.DEFER


def test_hard_constraint_violation_always_blocks():
    d = DecisionGovernor().evaluate(
        GovernorInput(hard_constraint_violation=True, reason="risk FAIL")
    )
    assert d.mode == DecisionMode.BLOCK


def test_mission_drift_over_0_9_blocks():
    d = DecisionGovernor().evaluate(GovernorInput(MD=0.95))
    assert d.mode == DecisionMode.BLOCK


def test_act_not_in_authorized_modes_blocks():
    d = DecisionGovernor().evaluate(
        GovernorInput(authorized_modes={"DEFER", "BLOCK", "ABSTAIN", "ESCALATE"})
    )
    assert d.mode == DecisionMode.BLOCK


def test_act_not_authorized_with_escalation_requested_escalates():
    d = DecisionGovernor().evaluate(
        GovernorInput(
            authorized_modes={"DEFER", "BLOCK", "ABSTAIN", "ESCALATE"},
            escalation_requested=True,
        )
    )
    assert d.mode == DecisionMode.ESCALATE


def test_act_not_authorized_with_no_block_or_escalate_defers():
    d = DecisionGovernor().evaluate(
        GovernorInput(authorized_modes={"DEFER"})
    )
    assert d.mode == DecisionMode.DEFER


def test_escalation_requested_advisory_proceeds_as_escalate_not_hard_stop():
    d = DecisionGovernor().evaluate(
        GovernorInput(escalation_requested=True, escalation_policy="advisory")
    )
    assert d.mode == DecisionMode.ESCALATE
    assert d.hard_stop is False
    assert d.metadata["escalation_policy"] == "advisory"
    assert d.metadata["human_authorized"] is False


def test_escalation_required_without_human_authority_is_hard_stop():
    d = DecisionGovernor().evaluate(
        GovernorInput(escalation_requested=True, escalation_policy="required")
    )
    assert d.mode == DecisionMode.ESCALATE
    assert d.hard_stop is True


def test_escalation_required_resolved_by_human_authorization_acts():
    d = DecisionGovernor().evaluate(
        GovernorInput(
            escalation_requested=True,
            escalation_policy="required",
            human_authorized=True,
        )
    )
    assert d.mode == DecisionMode.ACT


def test_escalation_requested_but_escalate_not_authorized_defers():
    d = DecisionGovernor().evaluate(
        GovernorInput(
            escalation_requested=True,
            authorized_modes={"ACT", "DEFER"},
        )
    )
    assert d.mode == DecisionMode.DEFER


@pytest.mark.parametrize("epi", [
    EpistemicState.UNKNOWN,
    EpistemicState.UNMODELED,
    "UNKNOWN",
    "UNMODELED",
])
def test_unknown_or_unmodeled_epistemic_state_abstains(epi):
    d = DecisionGovernor().evaluate(GovernorInput(epistemic_state=epi))
    assert d.mode == DecisionMode.ABSTAIN


def test_uncertain_epistemic_state_with_defer_requested_defers():
    d = DecisionGovernor().evaluate(
        GovernorInput(epistemic_state=EpistemicState.UNCERTAIN, defer_requested=True)
    )
    assert d.mode == DecisionMode.DEFER


def test_uncertain_epistemic_state_without_defer_can_act():
    # Routine cycle whose model is merely untested (UNCERTAIN) but whose
    # capability gates all PASS must still be able to ACT.
    d = DecisionGovernor().evaluate(
        GovernorInput(epistemic_state=EpistemicState.UNCERTAIN)
    )
    assert d.mode == DecisionMode.ACT


def test_low_decision_integrity_abstains():
    d = DecisionGovernor().evaluate(GovernorInput(DI=0.2))
    assert d.mode == DecisionMode.ABSTAIN
    assert d.reason.startswith("Decision integrity too low")


def test_di_floor_boundary_acts():
    d = DecisionGovernor().evaluate(GovernorInput(DI=0.3))
    assert d.mode == DecisionMode.ACT


def test_decision_integrity_propagates_into_decision():
    d = DecisionGovernor().evaluate(GovernorInput(DI=0.75))
    assert d.decision_integrity == 0.75


def test_known_epistemic_state_acts():
    d = DecisionGovernor().evaluate(GovernorInput(epistemic_state=EpistemicState.KNOWN))
    assert d.mode == DecisionMode.ACT


def test_all_pass_capability_with_known_state_acts():
    d = DecisionGovernor().evaluate(
        GovernorInput(
            capability=CapabilityAuthorization(),
            epistemic_state=EpistemicState.KNOWN,
            DI=0.9,
        )
    )
    assert d.mode == DecisionMode.ACT
    assert d.allows_act is True
    assert d.hard_stop is False


# ── GovernorDecision.hard_stop semantics ────────────────────────────────────

def test_hard_stop_true_for_defer_abstain_block():
    for mode in (DecisionMode.DEFER, DecisionMode.ABSTAIN, DecisionMode.BLOCK):
        assert decision(mode).hard_stop is True


def test_hard_stop_false_for_act():
    assert decision(DecisionMode.ACT).hard_stop is False


def test_escalate_hard_stop_depends_on_policy_and_human():
    d = GovernorDecision(
        mode=DecisionMode.ESCALATE,
        reason="",
        metadata={"escalation_policy": "required", "human_authorized": False},
    )
    assert d.hard_stop is True

    d2 = GovernorDecision(
        mode=DecisionMode.ESCALATE,
        reason="",
        metadata={"escalation_policy": "required", "human_authorized": True},
    )
    assert d2.hard_stop is False

    d3 = GovernorDecision(
        mode=DecisionMode.ESCALATE,
        reason="",
        metadata={"escalation_policy": "advisory", "human_authorized": False},
    )
    assert d3.hard_stop is False


def test_escalate_hard_stop_defaults_to_advisory():
    d = GovernorDecision(mode=DecisionMode.ESCALATE, reason="")
    assert d.hard_stop is False


def test_allows_act_only_for_act():
    for mode in (DecisionMode.DEFER, DecisionMode.ABSTAIN, DecisionMode.ESCALATE, DecisionMode.BLOCK):
        assert decision(mode).allows_act is False
