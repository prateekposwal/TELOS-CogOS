"""
TELOS Book-Mirror Principle & Observer Coupling Architecture

Recognizes that when a system's identity, mission, or survival is entangled
with a decision, the reasoning engine moves from "Book Mode" (objective
analysis) to "Mirror Mode" (identity-entangled distortion).

Q_eff = Q_t * (1 - phi * B_t)
"""
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum


class CouplingMode(Enum):
    BOOK = "book"
    MIRROR = "mirror"
    CRITICAL = "critical"


@dataclass
class CouplingState:
    b_t: float              # Observer Coupling Index [0, 1]
    mode: CouplingMode
    q_eff: float            # Effective reasoning quality
    entanglement_factors: List[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class RedTeamResult:
    trajectory_id: str
    counter_role_id: str
    utility: float
    is_bias_breaker: bool


class ObserverCouplingIndex:
    """Computes B_t — the degree of identity entanglement in a decision."""

    def __init__(self, sensitivity: float = 0.5, threshold: float = 0.4):
        self.phi = sensitivity
        self.threshold = threshold
        self._history: deque = deque(maxlen=100)

    def compute(self, mission_threat: float, survival_risk: float,
                identity_investment: float, structural_stability: float,
                merit_flow: float) -> float:
        """B_t = weighted composite of entanglement signals.

        Args:
            mission_threat:  how directly G_0 is challenged [0,1]
            survival_risk:   probability of systemic failure [0,1]
            identity_investment: ego-involvement in a specific outcome [0,1]
            structural_stability: how fragile the current state is [0,1]
            merit_flow:      current Merit Flow score [0,1]
        """
        raw = (0.30 * mission_threat +
               0.25 * survival_risk +
               0.25 * identity_investment +
               0.15 * structural_stability +
               0.05 * (1.0 - merit_flow))
        b_t = float(np.clip(raw, 0.0, 1.0))
        self._history.append(b_t)
        return b_t

    def get_effective_q(self, q_t: float, b_t: float) -> float:
        """Q_eff = Q_t * (1 - phi * B_t)"""
        return float(max(0.0, q_t * (1.0 - self.phi * b_t)))

    def get_mode(self, b_t: float) -> CouplingMode:
        if b_t >= self.threshold * 1.5:
            return CouplingMode.CRITICAL
        elif b_t >= self.threshold:
            return CouplingMode.MIRROR
        return CouplingMode.BOOK

    def check_mode(self, b_t: float) -> CouplingMode:
        return self.get_mode(b_t)

    def get_statistics(self) -> dict:
        recent = list(self._history)
        return {
            'avg_b_t': round(float(np.mean(recent)), 4) if recent else 0.0,
            'max_b_t': round(float(np.max(recent)), 4) if recent else 0.0,
            'sensitivity_phi': self.phi,
            'threshold': self.threshold,
            'samples': len(recent),
        }


class RedTeamEngine:
    """Generates counter-intuitive counterfactuals to break identity-bias."""

    def __init__(self):
        self._generated_count = 0

    def generate_counter_role(self, primary_role_id: str,
                               available_roles: List[str]) -> str:
        """Force-select a role that contradicts the identity-aligned path."""
        opposites = [r for r in available_roles if r != primary_role_id]
        if not opposites:
            return primary_role_id
        # Pick the least-similar role
        idx = hash(primary_role_id + str(self._generated_count)) % len(opposites)
        self._generated_count += 1
        return opposites[idx]

    def generate_bias_breaking_action(self, primary_action: np.ndarray,
                                       state_dim: int) -> np.ndarray:
        """Generate a mirror-opposite action to the identity-aligned one."""
        anti = -primary_action
        noise = np.random.randn(state_dim) * 0.3
        return np.clip(anti + noise, -1.0, 1.0)

    def get_statistics(self) -> dict:
        return {'counter_roles_generated': self._generated_count}


class BookMirrorAuditor:
    """Performs Identity Entanglement Audit and manages mode switching."""

    def __init__(self, coupling: Optional[ObserverCouplingIndex] = None,
                 red_team: Optional[RedTeamEngine] = None,
                 baseline_q: float = 0.8):
        self.coupling = coupling or ObserverCouplingIndex()
        self.red_team = red_team or RedTeamEngine()
        self.baseline_q = baseline_q
        self._current_b_t: float = 0.0
        self._current_mode: CouplingMode = CouplingMode.BOOK
        self._current_q_eff: float = baseline_q
        self._audit_count = 0
        self._mirror_mode_entries = 0

    def audit(self, trajectory_coupling_metrics: dict,
              available_roles: Optional[List[str]] = None) -> CouplingState:
        """Execute the Identity Entanglement Audit."""
        self._audit_count += 1
        b_t = self.coupling.compute(
            mission_threat=trajectory_coupling_metrics.get('mission_threat', 0.0),
            survival_risk=trajectory_coupling_metrics.get('survival_risk', 0.0),
            identity_investment=trajectory_coupling_metrics.get('identity_investment', 0.0),
            structural_stability=trajectory_coupling_metrics.get('structural_stability', 0.0),
            merit_flow=trajectory_coupling_metrics.get('merit_flow', 1.0),
        )
        mode = self.coupling.get_mode(b_t)
        q_eff = self.coupling.get_effective_q(self.baseline_q, b_t)

        self._current_b_t = b_t
        self._current_mode = mode
        self._current_q_eff = q_eff

        if mode == CouplingMode.MIRROR or mode == CouplingMode.CRITICAL:
            self._mirror_mode_entries += 1

        factors = []
        if trajectory_coupling_metrics.get('mission_threat', 0.0) > 0.5:
            factors.append('mission_threat')
        if trajectory_coupling_metrics.get('survival_risk', 0.0) > 0.5:
            factors.append('survival_risk')
        if trajectory_coupling_metrics.get('identity_investment', 0.0) > 0.5:
            factors.append('identity_investment')

        rec = self._recommendation(mode, b_t, factors)

        return CouplingState(
            b_t=b_t, mode=mode, q_eff=q_eff,
            entanglement_factors=factors, recommendation=rec,
        )

    def _recommendation(self, mode: CouplingMode, b_t: float,
                        factors: List[str]) -> str:
        if mode == CouplingMode.BOOK:
            return "Proceed with standard trajectory search."
        elif mode == CouplingMode.MIRROR:
            return (f"Forced Externalization: Activate Red-Team. "
                    f"B_t={b_t:.2f}, factors={factors}")
        else:
            return (f"CRITICAL: B_t={b_t:.2f}. "
                    f"Require Second Observer. Decouple decision.")

    def get_coupling_metrics(self) -> dict:
        return {
            'b_t': self._current_b_t,
            'mode': self._current_mode.value,
            'q_eff': self._current_q_eff,
        }

    def is_in_mirror_mode(self) -> bool:
        return self._current_mode in (CouplingMode.MIRROR, CouplingMode.CRITICAL)

    def get_statistics(self) -> dict:
        return {
            'total_audits': self._audit_count,
            'mirror_mode_entries': self._mirror_mode_entries,
            'mirror_rate': (self._mirror_mode_entries / self._audit_count
                            if self._audit_count else 0.0),
            'current_b_t': round(self._current_b_t, 4),
            'current_mode': self._current_mode.value,
            'coupling': self.coupling.get_statistics(),
            'red_team': self.red_team.get_statistics(),
        }
