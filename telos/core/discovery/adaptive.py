"""
Adaptive experiment sequences (V4).

The CanonicalExperimentSelector stays the ONLY authority for choosing the next
experiment. This planner adds the LOOP around it:

    observation → candidate assumptions → CanonicalExperimentSelector → experiment
    → observation → evidence update → Reality Gap → regenerate candidates
    → recompute value → CanonicalExperimentSelector → next experiment → … → stop

Nothing is precomputed: each next experiment is chosen from the UPDATED state.
Stopping is explicit (budget / resolution / no-value / contradiction), so the
loop can never become an unbounded curiosity engine. A one-experiment sequence
remains valid.

Epistemic safety: an unvaluable candidate is UNKNOWN — never zero-confidence
evidence; the loop terminates rather than fabricating an experiment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from telos.core.discovery.experiment_selection import (
    CanonicalExperimentSelector, Hypothesis,
)
from telos.world.epistemic import RealityGapTracker
from telos.core.reasoning.theory_builder import TheoryBuilder
from telos.core.knowledge.graph import KnowledgeGraph


class StopReason(str, Enum):
    """Why the adaptive loop stopped (explicit, never arbitrary)."""
    RESOLVED = "RESOLVED"                     # one survivor, sufficiently confident
    CONFIDENT = "CONFIDENT"                   # model confidence sufficient
    NO_VALUE = "NO_VALUE"                     # no VALUED experiment with value > 0
    CONTRADICTORY = "CONTRADICTORY"           # evidence falsified every candidate
    BUDGET_EXPERIMENTS = "BUDGET_EXPERIMENTS" # experiment-count budget exhausted
    BUDGET_COST = "BUDGET_COST"               # cost budget exhausted
    EXHAUSTED = "EXHAUSTED"                   # no candidate left


@dataclass
class Candidate:
    """A candidate assumption (a truth state the planner may test).

    Args:
        id: stable id.
        simulator: DomainSimulator used by the canonical selector's value calc.
        uncertainty: current uncertainty in [0,1].
        cost: experiment cost.
        predicts: {experiment_id: predicted diagnostic} for consistency checks.
        status: candidate | supported | promoted | falsified.
    """
    id: str
    simulator: Any
    uncertainty: float
    cost: float
    predicts: Dict[str, float] = field(default_factory=dict)
    status: str = "candidate"

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "uncertainty": round(self.uncertainty, 3),
                "cost": self.cost, "status": self.status}


@dataclass
class Step:
    """One adaptive step (auditable)."""
    index: int
    selected: str
    options: List[Dict[str, Any]]
    observation: float
    predicted: float
    reality_gap: float
    candidates_after: List[Dict[str, Any]]
    stop_reason: Optional[str] = None


class AdaptiveExperimentPlanner:
    """Adaptive multi-step experiment selection over competing candidates.

    Args:
        selector: the canonical (and only) experiment selector.
        candidates: the competing candidate assumptions.
        max_experiments: hard experiment-count budget.
        cost_budget: hard cumulative-cost budget.
        tol: diagnostic tolerance for refuting a candidate.
        gap_threshold: reality-gap size that counts as a contradiction.
        confidence: model confidence that stops the loop (existing semantics).
    """

    def __init__(self, selector: CanonicalExperimentSelector,
                 candidates: List[Candidate], *, max_experiments: int = 8,
                 cost_budget: float = 10.0, tol: float = 0.3,
                 gap_threshold: float = 0.5, confidence: float = 0.75):
        self.selector = selector
        self.candidates = list(candidates)
        self.max_experiments = int(max_experiments)
        self.cost_budget = float(cost_budget)
        self.tol = float(tol)
        self.gap_threshold = float(gap_threshold)
        self.confidence = float(confidence)
        self.reality_gap = RealityGapTracker()
        self.tb = TheoryBuilder()
        self.kg = KnowledgeGraph()
        # budget + audit state
        self.experiments = 0
        self.spent = 0.0
        self.sequence: List[str] = []
        self.steps: List[Step] = []
        self.stop_reason: Optional[StopReason] = None
        # durable, explicit state (restart contract)
        self.state_keys = ("sequence", "experiments", "spent", "stop_reason")

    # ── Candidate handling ───────────────────────────────────────────────────

    def _active(self) -> List[Candidate]:
        return [c for c in self.candidates if c.status != "falsified"]

    def _by_id(self, cid: str) -> Optional[Candidate]:
        return next((c for c in self.candidates if c.id == cid), None)

    def _hyps(self, active: List[Candidate]) -> List[Hypothesis]:
        return [Hypothesis(c.id, c.simulator, c.uncertainty, c.cost) for c in active]

    def select_next(self, state) -> Tuple[Optional[Any], List[Any]]:
        """Choose the next experiment via the canonical selector.

        Args:
            state: current state.

        Returns:
            (chosen ExperimentOption or None, all options). None ⇒ no VALUED
            experiment remains (the loop must stop, not fabricate one).
        """
        active = self._active()
        if not active:
            return None, []
        options = self.selector.evaluate(state, self._hyps(active))
        valued = [o for o in options if o.status == "VALUED" and o.value and o.value > 0.0]
        if not valued:
            return None, options
        return max(valued, key=lambda o: o.value), options

    # ── Evidence update ──────────────────────────────────────────────────────

    def observe(self, exp_id: str, observation: float) -> float:
        """Update evidence, candidates, Reality Gap, TheoryBuilder, KG.

        Args:
            exp_id: the tested candidate id.
            observation: the observed diagnostic value.

        Returns:
            The reality gap (|predicted − observed|).
        """
        exp = self._by_id(exp_id)
        predicted = exp.predicts.get(exp_id, 0.0) if exp else 0.0
        gap = abs(predicted - float(observation))
        self.reality_gap.record("adaptive", np.array([predicted]),
                                np.array([float(observation)]))

        # refute candidates inconsistent with the observation (fresh evidence only)
        for c in self._active():
            if abs(c.predicts.get(exp_id, 0.0) - float(observation)) > self.tol:
                c.status = "falsified"
                c.uncertainty = 0.0
                self.tb.observe_outcome(outcome=0.0, context=c.id)
                self.kg.record(domain="pattern", approach=c.id, outcome=0.0,
                               tags=["discovered", "falsified"],
                               provenance={"status": "falsified"})
        # the tested candidate, if consistent, is supported and gains confidence
        if exp is not None and exp.status != "falsified":
            exp.status = "supported"
            exp.uncertainty = max(0.0, exp.uncertainty - 0.3)
            self.tb.observe_outcome(outcome=1.0, context=exp.id)
            # legitimate promotion only when confidence is sufficient
            if exp.uncertainty <= (1.0 - self.confidence):
                exp.status = "promoted"
                self.kg.record(domain="pattern", approach=exp.id, outcome=1.0,
                               tags=["discovered", "promoted"],
                               provenance={"status": "promoted"})
        return gap

    # ── Stopping policy ──────────────────────────────────────────────────────

    def _stop_reason(self) -> Optional[StopReason]:
        """The explicit stopping decision (checked before each experiment)."""
        if self.experiments >= self.max_experiments:
            return StopReason.BUDGET_EXPERIMENTS
        if self.spent >= self.cost_budget:
            return StopReason.BUDGET_COST
        active = self._active()
        if not active:
            return StopReason.EXHAUSTED
        survivors = [c for c in active if c.status in ("supported", "promoted")]
        if len(survivors) == 1 and len(active) == 1:
            return StopReason.RESOLVED
        if len(survivors) >= 1 and all(
                c.uncertainty <= (1.0 - self.confidence) for c in survivors):
            return StopReason.CONFIDENT
        return None

    # ── The loop ─────────────────────────────────────────────────────────────

    def run(self, state, world, max_steps: int = 12) -> Dict[str, Any]:
        """Run the adaptive loop against a hidden world.

        Args:
            state: initial state.
            world: an object with `observation(exp_id) -> float`.
            max_steps: secondary safety bound (never the primary stop).

        Returns:
            The run result (sequence, metrics, stop reason).
        """
        steps = 0
        while steps < max_steps:
            steps += 1
            reason = self._stop_reason()
            if reason is not None:
                self.stop_reason = reason
                break
            choice, options = self.select_next(state)
            if choice is None:
                self.stop_reason = StopReason.NO_VALUE
                break
            if self.spent + choice.cost > self.cost_budget:
                self.stop_reason = StopReason.BUDGET_COST
                break
            # execute the chosen experiment
            exp_id = choice.hypothesis_id
            self.experiments += 1
            self.spent += choice.cost
            self.sequence.append(exp_id)
            observed = float(world.observation(exp_id))
            predicted = (self._by_id(exp_id).predicts.get(exp_id, 0.0)
                         if self._by_id(exp_id) else 0.0)
            gap = self.observe(exp_id, observed)
            self.steps.append(Step(
                index=self.experiments, selected=exp_id,
                options=[o.to_dict() for o in options],
                observation=observed, predicted=predicted, reality_gap=gap,
                candidates_after=[c.to_dict() for c in self.candidates]))
        if self.stop_reason is None:
            self.stop_reason = StopReason.BUDGET_EXPERIMENTS

        survivors = [c.id for c in self.candidates if c.status in ("supported", "promoted")]
        return {
            "sequence": list(self.sequence),
            "experiments": self.experiments,
            "cost": round(self.spent, 3),
            "stop_reason": self.stop_reason.value,
            "survivors": survivors,
            "steps": [s.__dict__ for s in self.steps],
            "candidates": [c.to_dict() for c in self.candidates],
        }

    # ── Restart contract ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """The state that must survive a restart (explicitly enumerated)."""
        return {
            "sequence": list(self.sequence),
            "experiments": self.experiments,
            "spent": self.spent,
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "reality_gap": self.reality_gap.to_dict(),
        }
