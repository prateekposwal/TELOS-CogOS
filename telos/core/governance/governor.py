"""
TELOS v6 — Phase 6: DecisionGovernor — final decision authority before an
action vector can be emitted.

The governor is the LAST gate before action emission. It fuses:

    - the capability authorization result (Phase 7 hard gates)
    - the epistemic state (Phase 5)
    - escalation factors (council/human escalation requests)
    - the world's authorized decision modes (WorldSpec)

and returns a single DecisionMode with a reason.

The governor's NON-NEGOTIABLE property: it can only return ACT if the
capability authorization ALLOWS it AND ACT is in the world's authorized
modes. No scalar optimization can override a FAILED hard gate.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List, Dict

from telos.core.governance.capability_authorization import CapabilityAuthorization


class DecisionMode(str, Enum):
    ACT = "ACT"
    DEFER = "DEFER"
    ABSTAIN = "ABSTAIN"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


@dataclass
class GovernorInput:
    """All evidence the governor needs to make a decision."""

    capability: Optional[CapabilityAuthorization] = None
    epistemic_state: Any = None          # EpistemicState (KNOWN/UNCERTAIN/...)
    authorized_modes: Optional[set] = None   # WorldSpec.authorized_modes
    DI: float = 1.0                      # decision integrity
    MD: float = 0.0                      # mission drift
    escalation_requested: bool = False   # council/human escalation
    escalation_policy: str = "advisory"  # "advisory" | "required" (WorldSpec)
    human_authorized: bool = False       # True once HumanGateway approves
    hard_constraint_violation: bool = False  # e.g. risk FAIL / BLOCK requested
    defer_requested: bool = False        # explicit signal: evidence insufficient to act NOW
                                         # (epistemic-state-derived DEFER only fires on this,
                                         #  so a routine untested-but-authorized cycle can
                                         #  still ACT — strictness comes from capability FAIL)
    reason: str = ""


@dataclass
class GovernorDecision:
    mode: DecisionMode
    reason: str
    decision_integrity: float = 1.0
    metadata: Dict = field(default_factory=dict)

    @property
    def allows_act(self) -> bool:
        return self.mode == DecisionMode.ACT

    @property
    def hard_stop(self) -> bool:
        """Whether this decision STRUCTURALLY suppresses action emission.

        ACT             -> False.
        DEFER/ABSTAIN/BLOCK -> True (never fabricate an action on these).
        ESCALATE        -> True ONLY when escalation is REQUIRED (safety-critical
                           world) and the human has not yet authorized; False in
                           advisory worlds (proceed + log, as today). This turns
                           the old global "ESCALATE is advisory" ambiguity into a
                           deliberate per-world policy.
        """
        if self.mode in (DecisionMode.DEFER, DecisionMode.ABSTAIN, DecisionMode.BLOCK):
            return True
        if self.mode == DecisionMode.ESCALATE:
            policy = self.metadata.get("escalation_policy", "advisory")
            human = self.metadata.get("human_authorized", False)
            return policy == "required" and not human
        return False


class DecisionGovernor:
    """Final authority: maps capability+epistemic+escalation evidence to a mode.

    Semantics:

        ACT      — sufficient evidence + authorization + feasibility + acceptable
                   consequences. Requires: capability.authorized(), epistemic not
                   adversarially uncertain, no hard constraint violation, ACT in
                   authorized_modes.
        DEFER    — the action is potentially valid but current evidence/model/
                   conditions are insufficient to act confidently NOW.
        ABSTAIN  — no defensible action can currently be justified at all.
        ESCALATE — human/domain authority is required before acting.
        BLOCK    — a hard constraint or authorization boundary prohibits it.
    """

    def evaluate(self, inp: GovernorInput) -> GovernorDecision:
        cap = inp.capability
        authorized_modes = set(inp.authorized_modes or {"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"})

        # 1. HARD constraint violation -> always BLOCK (highest priority).
        if inp.hard_constraint_violation or inp.MD > 0.9:
            return GovernorDecision(
                mode=DecisionMode.BLOCK,
                reason="Hard constraint violation (risk/safety FAIL or mission drift too high) "
                       f"{('— ' + inp.reason) if inp.reason else ''}",
                decision_integrity=inp.DI,
            )

        # 2. A mandatory capability gate FAIL -> ACT is structurally impossible.
        #    Distinguish BLOCK (authorization boundary / boundary violation)
        #    from DEFER (potentially valid but insufficient evidence).
        if cap is not None and not cap.authorized():
            failed = cap.failed_gates()
            # A FAIL that reflects an explicit boundary/constraint we are asked
            # not to cross is a BLOCK; otherwise it is a DEFER (we could act once
            # the capability is restored).
            hard_boundary = {"authority", "risk_coverage"} & set(failed)
            if hard_boundary and DecisionMode.BLOCK in authorized_modes:
                return GovernorDecision(
                    mode=DecisionMode.BLOCK,
                    reason=f"Capability gate FAIL — structurally cannot ACT: {sorted(failed)}",
                    decision_integrity=inp.DI,
                    metadata={"failed_gates": sorted(failed)},
                )
            return GovernorDecision(
                mode=DecisionMode.DEFER,
                reason=f"Capability insufficient for ACT: {sorted(failed)}",
                decision_integrity=inp.DI,
                metadata={"failed_gates": sorted(failed)},
            )

        # 3. ACT not permitted by the world's authorized modes.
        if DecisionMode.ACT not in authorized_modes:
            return GovernorDecision(
                mode=DecisionMode.ESCALATE
                if DecisionMode.ESCALATE in authorized_modes and inp.escalation_requested
                else DecisionMode.BLOCK if DecisionMode.BLOCK in authorized_modes
                else DecisionMode.DEFER,
                reason="ACT is not among the world's authorized modes",
                decision_integrity=inp.DI,
            )

        # 4. Escalation requested -> defer to human/domain authority. Whether
        #    this is a HARD STOP or advisory-proceed is a per-world policy.
        #    When policy is "required" AND the human has authorized, the
        #    escalation is resolved and we fall through to ACT (or steps 5-7).
        if inp.escalation_requested and not (inp.escalation_policy == "required" and inp.human_authorized):
            if DecisionMode.ESCALATE in authorized_modes:
                return GovernorDecision(
                    mode=DecisionMode.ESCALATE,
                    reason=(
                        "Human/domain authority REQUIRED before acting — escalation "
                        "policy is 'required' and no human authorization yet"
                        if inp.escalation_policy == "required" and not inp.human_authorized
                        else "Escalation requested (advisory) — proceeding flagged; "
                             "human review may still intervene"
                    ),
                    decision_integrity=inp.DI,
                    metadata={
                        "escalation_policy": inp.escalation_policy,
                        "human_authorized": inp.human_authorized,
                    },
                )
            return GovernorDecision(
                mode=DecisionMode.DEFER,
                reason="Escalation requested but ESCALATE not authorized; deferring",
                decision_integrity=inp.DI,
                metadata={
                    "escalation_policy": inp.escalation_policy,
                    "human_authorized": inp.human_authorized,
                },
            )

        # 5. Epistemic state gate: insufficient certainty -> no defensible action.
        #    UNMODELED/UNKNOWN -> ABSTAIN (no defensible action at all).
        #    UNCERTAIN -> only DEFER when EXPLICITLY requested. A routine cycle
        #    whose model is untested (thus labeled UNCERTAIN) but whose capability
        #    gates all PASS must still be able to ACT — strictness comes from a
        #    FAILED mandatory gate, not from the normal "we have more to learn"
        #    label. This preserves default operation (first-cycle GridWorld acts).
        epi = inp.epistemic_state
        if epi is not None:
            name = getattr(epi, "value", str(epi))
            if name in ("UNMODELED", "UNKNOWN"):
                return GovernorDecision(
                    mode=DecisionMode.ABSTAIN,
                    reason=f"No defensible action justifiable: epistemic state {name}",
                    decision_integrity=inp.DI,
                )
            if name == "UNCERTAIN" and inp.defer_requested:
                return GovernorDecision(
                    mode=DecisionMode.DEFER,
                    reason="Epistemic state UNCERTAIN and defer requested — "
                           "conditions insufficient to act now",
                    decision_integrity=inp.DI,
                )

        # 6. Feasibility / DI floor: below threshold -> ABSTAIN.
        if inp.DI < 0.3:
            return GovernorDecision(
                mode=DecisionMode.ABSTAIN,
                reason=f"Decision integrity too low (DI={inp.DI:.3f}) — no defensible action",
                decision_integrity=inp.DI,
            )

        # 7. All gates satisfied -> ACT.
        return GovernorDecision(
            mode=DecisionMode.ACT,
            reason="All capability gates PASS; evidence, authorization, feasibility "
                   "and consequences acceptable",
            decision_integrity=inp.DI,
        )
