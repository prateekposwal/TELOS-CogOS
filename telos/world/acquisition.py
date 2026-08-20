"""
TELOS v7.0 — Adaptive World Acquisition Layer (additive).

The bridge toward real-world generalization: TELOS can begin a new world with
UNKNOWN/UNMODELED knowledge, safely gather evidence through governed
experiments, form a provisional world model, and earn capability authority.

CRITICAL INVARIANTS (these are load-bearing):
  - LEARNING != AUTHORIZATION: discovering how the world behaves does NOT grant
    the right to act; CapabilityAuthorization remains the ONLY authority gate.
  - DISCOVERY != CERTIFICATION: a discovered capability is not certified.
  - UNKNOWN/UNMODELED are never coerced to 0/False/"safe"/"reversible".
  - One genuine mandatory FAIL remains a structural veto (conjunctive gates).

This layer is PURELY ADDITIVE. It does NOT modify runtime.py / engine.py /
phases / governor / council / capability / epistemic core. It builds ON TOP of
the existing EvidenceSource, Experiment, RealityGapTracker,
CapabilityAuthorization, EpistemicState, and DecisionGovernor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

import numpy as np

from telos.core.contracts.domain_model import WorldSpec
from telos.world.epistemic import (
    EpistemicState, RealityGapTracker,
)
from telos.world.evidence import (
    EvidenceInfo, EvidenceSource, ValidationStatus,
)
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus,
)


class DynamicsStatus(str, Enum):
    UNMODELED = "UNMODELED"
    PARTIAL = "PARTIAL"
    MODELED = "MODELED"
    VALIDATED = "VALIDATED"


@dataclass
class ProvisionalWorldSpec:
    """A WorldSpec that may begin with largely UNKNOWN structure.

    Explicitly marks what is not yet known — NEVER coercing UNKNOWN to 0/False.
    Composition over (risky) subclassing: carries a real WorldSpec it converges
    toward, but front-loads the unknown/unmodeled surface.
    """
    name: str
    state_dim: int = 0
    action_dim: int = 0
    observability: str = "UNKNOWN"        # UNKNOWN | PARTIAL | HIGH
    dynamics: DynamicsStatus = DynamicsStatus.UNMODELED
    action_cost: str = "UNKNOWN"          # UNKNOWN | KNOWN
    reversibility: str = "UNKNOWN"        # UNKNOWN | KNOWN
    risk: str = "UNKNOWN"                 # UNKNOWN | KNOWN
    consequence_model: str = "UNKNOWN"    # UNKNOWN | PARTIAL | KNOWN
    known_state_vars: List[str] = field(default_factory=list)
    known_actions: List[str] = field(default_factory=list)
    target_spec: Optional[WorldSpec] = None   # converges toward this

    def to_world_spec(self) -> WorldSpec:
        """Build a concrete WorldSpec from currently-known structure.

        Unknown fields are NOT assigned permissive defaults; they are recorded
        conservatively so downstream authorization must treat them as gaps.
        """
        return WorldSpec(
            name=self.name,
            state_dim=max(1, self.state_dim),
            action_dim=max(1, self.action_dim),
            observability="partial" if self.observability != "HIGH" else "high",
            constraints=["dynamics_unmodeled" if self.dynamics == DynamicsStatus.UNMODELED
                         else "dynamics_partial"],
            capabilities=list(self.known_actions),
            authorized_modes={"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"},
            escalation_policy="advisory",
        )

    def known_degree(self) -> Dict[str, str]:
        return {
            "observability": self.observability,
            "dynamics": self.dynamics.value,
            "action_cost": self.action_cost,
            "reversibility": self.reversibility,
            "risk": self.risk,
            "consequence_model": self.consequence_model,
        }


class CapabilityDiscoveryState(str, Enum):
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    LIMITED = "LIMITED"
    BLOCKED = "BLOCKED"


@dataclass
class CapabilityKnowledge:
    """Knowledge about a capability. Knowledge != authorization.

    DISCOVERED/VALIDATED here feed into authority ONLY via the existing
    CapabilityAuthorization hard gates (as UNKNOWN/LIMITED statuses that refuse
    authorization until validated). We do NOT create a second authority.
    """
    capability: str
    state: CapabilityDiscoveryState = CapabilityDiscoveryState.UNKNOWN
    validation_count: int = 0
    failure_count: int = 0
    evidence: List[EvidenceInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "state": self.state.value,
            "validation_count": self.validation_count,
            "failure_count": self.failure_count,
        }


@dataclass
class ProvisionalModel:
    """Minimum provisional world model. Distinguishes predicted vs observed.

    A model with zero empirical validation is UNVALIDATED, not KNOWN.
    """
    world_name: str
    # per-action learned effect signal (mean observed effect, count)
    action_effects: Dict[str, Dict[str, float]] = field(default_factory=dict)
    validation_count: int = 0
    failure_count: int = 0
    _tracker: RealityGapTracker = field(default_factory=RealityGapTracker)

    @property
    def fidelity(self) -> Optional[float]:
        return self._tracker.model_fidelity("model")

    def record(self, action: str, predicted: np.ndarray,
               observed: np.ndarray) -> float:
        self._tracker.record("model", predicted, observed)
        gap = float(np.linalg.norm(np.asarray(predicted) - np.asarray(observed)))
        self.validation_count += 1
        if gap > 0.6:
            self.failure_count += 1
        entry = self.action_effects.setdefault(action, {"n": 0.0, "mean_gap": 0.0})
        n = entry["n"] + 1.0
        entry["mean_gap"] = (entry["mean_gap"] * entry["n"] + gap) / n
        entry["n"] = n
        return gap

    @property
    def empirical_status(self) -> EpistemicState:
        """UNVALIDATED unless we have validated evidence and reasonable fidelity."""
        if self.validation_count == 0:
            return EpistemicState.UNMODELED
        f = self.fidelity
        if f is not None and f >= 0.7 and self.failure_count == 0:
            return EpistemicState.KNOWN
        if f is not None and f >= 0.7 and self.failure_count > 0:
            return EpistemicState.UNCERTAIN
        return EpistemicState.UNCERTAIN


class CapabilityDiscovery:
    """Thin knowledge-only tracker for capabilities. NOT an authority gate."""

    def __init__(self):
        self._caps: Dict[str, CapabilityKnowledge] = {}

    def propose(self, capability: str) -> CapabilityKnowledge:
        cap = self._caps.setdefault(
            capability, CapabilityKnowledge(capability, CapabilityDiscoveryState.DISCOVERED))
        return cap

    def record_validation(self, capability: str, success: bool,
                          evidence: EvidenceInfo) -> None:
        cap = self.propose(capability)
        cap.validation_count += 1
        if not success:
            cap.failure_count += 1
        cap.evidence.append(evidence)
        if success and cap.validation_count >= 3 and cap.failure_count == 0:
            cap.state = CapabilityDiscoveryState.VALIDATED
        elif cap.validation_count >= 1:
            cap.state = CapabilityDiscoveryState.VALIDATING
        if cap.failure_count >= 3:
            cap.state = CapabilityDiscoveryState.BLOCKED
        elif cap.failure_count > 0 and cap.validation_count > 0 \
                and cap.state != CapabilityDiscoveryState.VALIDATED:
            cap.state = CapabilityDiscoveryState.LIMITED

    def as_authorization(self, capability: str,
                         mandatory: bool = True) -> CapabilityStatus:
        """Translate discovered knowledge into a CapabilityStatus for the REAL
        authorization gate. This is the ONLY bridge to authority:
          - UNKNOWN/DISCOVERED (not yet validated)   -> UNKNOWN (refuses ACT)
          - VALIDATING                                -> LIMITED
          - VALIDATED                                 -> PASS
          - BLOCKED                                   -> FAIL
            - LIMITED                                 -> LIMITED

        Args:
            capability: the capability key to translate.
            mandatory: whether an unresolved capability must map to UNKNOWN
                (refusal) rather than a lenient fallback.
        """
        cap = self._caps.get(capability)
        if cap is None:
            return CapabilityStatus.UNKNOWN
        if cap.state == CapabilityDiscoveryState.VALIDATED:
            return CapabilityStatus.PASS
        if cap.state == CapabilityDiscoveryState.BLOCKED:
            return CapabilityStatus.FAIL
        if cap.state in (CapabilityDiscoveryState.VALIDATING,
                         CapabilityDiscoveryState.LIMITED):
            return CapabilityStatus.LIMITED
        return CapabilityStatus.UNKNOWN
