"""
Canonical experiment selection — decision value from the CounterfactualEngine.

ONE authoritative mechanism: the decision sensitivity of a candidate experiment
is the spread of achievable outcomes across the hypothesis's truth states, and
the value is computed with the EXISTING
`CounterfactualEngine.compute_value_of_information()` — not a parallel
calculation.

Candidate assumption
  → possible truth states (a simulator per hypothesis)
  → CounterfactualEngine.generate_options → compute_value_of_information
  → decision sensitivity
  → × uncertainty ÷ experiment cost
  → experiment value → selection

Epistemic safety (Phase 5): a hypothesis the engine CANNOT evaluate (no sim, no
world, no transition) is reported as UNKNOWN — never silently zero-valued.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator


@dataclass
class Hypothesis:
    """One truth state of a candidate assumption.

    Args:
        id: stable id.
        simulator: a DomainSimulator representing this truth state.
        uncertainty: current uncertainty in this hypothesis [0,1].
        test_cost: relative cost of the experiment that would test it.
    """
    id: str
    simulator: DomainSimulator
    uncertainty: float = 0.5
    test_cost: float = 1.0


@dataclass
class ExperimentOption:
    """A scored experiment.

    Args:
        hypothesis_id: the hypothesis this experiment would test.
        status: "VALUED" or "UNKNOWN" (engine could not evaluate it).
        sensitivity: canonical decision sensitivity (None when UNKNOWN).
        uncertainty: the hypothesis uncertainty.
        cost: the test cost.
        value: sensitivity × uncertainty ÷ cost (None when UNKNOWN).
    """
    hypothesis_id: str
    status: str
    sensitivity: Optional[float]
    uncertainty: float
    cost: float
    value: Optional[float]

    def to_dict(self) -> dict:
        return {"hypothesis_id": self.hypothesis_id, "status": self.status,
                "sensitivity": None if self.sensitivity is None else round(self.sensitivity, 4),
                "uncertainty": round(self.uncertainty, 4), "cost": round(self.cost, 4),
                "value": None if self.value is None else round(self.value, 4)}


class CanonicalExperimentSelector:
    """Selects experiments by CANONICAL counterfactual decision value.

    Args:
        engine: the canonical CounterfactualEngine (its simulator is swapped per
            hypothesis during option generation, then restored).
        horizon: simulation horizon.
        n_worlds: world branches per hypothesis.
    """

    def __init__(self, engine: CounterfactualEngine, horizon: int = 3,
                 n_worlds: int = 8):
        self.engine = engine
        self.horizon = horizon
        self.n_worlds = n_worlds

    def _options_for(self, simulator: DomainSimulator, state):
        """Generate options under a hypothesis's simulator.

        Args:
            simulator: the hypothesis simulator.
            state: current state.

        Returns:
            The options (empty when the engine cannot simulate).
        """
        prev = self.engine.simulator
        self.engine.simulator = simulator
        try:
            return self.engine.generate_options(state, self.horizon, self.n_worlds)
        except Exception:
            return []
        finally:
            self.engine.simulator = prev

    def evaluate(self, state, hypotheses: List[Hypothesis]) -> List[ExperimentOption]:
        """Score every candidate experiment with the canonical engine.

        Args:
            state: current state.
            hypotheses: candidate truth states.

        Returns:
            One ExperimentOption per hypothesis (status UNKNOWN when unvaluable).
        """
        pooled: List[Any] = []
        owner: List[str] = []
        by_h = {}
        for h in hypotheses:
            opts = self._options_for(h.simulator, state)
            by_h[h.id] = opts
            for o in opts:
                pooled.append(o)
                owner.append(h.id)

        if not pooled:
            return [ExperimentOption(h.id, "UNKNOWN", None, h.uncertainty,
                                     h.test_cost, None) for h in hypotheses]

        optimal = max(o.score for o in pooled)
        voi = self.engine.compute_value_of_information(pooled, optimal)  # CANONICAL

        # Decision sensitivity of a hypothesis = how much the BEST achievable
        # outcome changes if that hypothesis is true: the VoI of its best option
        # (the min |score - optimal| over its options), not its worst option.
        sens: dict = {}
        for hid, v in zip(owner, voi):
            sens[hid] = float(v) if hid not in sens else min(sens[hid], float(v))

        options: List[ExperimentOption] = []
        for h in hypotheses:
            if not by_h.get(h.id):
                options.append(ExperimentOption(h.id, "UNKNOWN", None, h.uncertainty,
                                                h.test_cost, None))
            else:
                s = sens.get(h.id, 0.0)
                options.append(ExperimentOption(
                    h.id, "VALUED", s, h.uncertainty, h.test_cost,
                    s * h.uncertainty / max(h.test_cost, 1e-6)))
        return options

    def select(self, state, hypotheses: List[Hypothesis]) -> Optional[ExperimentOption]:
        """Pick the highest-value VALUED experiment.

        Args:
            state: current state.
            hypotheses: candidate truth states.

        Returns:
            The selected option, or None when every candidate is UNKNOWN (the
            honest "insufficient evidence" outcome — never a zero-value default).
        """
        valued = [o for o in self.evaluate(state, hypotheses) if o.status == "VALUED"]
        if not valued:
            return None
        return max(valued, key=lambda o: o.value)
