"""
ModelCompetition — Multiple Competing Hypotheses with Bayesian Evidence.

Prateek's insight: "Carry multiple competing hypotheses with probability
weights (80/15/5). Don't kill losing models. Let evidence shift probabilities."

Most systems commit to a single interpretation of the world. Model Competition
maintains a ensemble of competing explanatory hypotheses. Each model is a
candidate explanation for observed phenomena. Evidence shifts probability
mass between models using a Bayesian update.

Key principles:
  - No model is ever fully killed (no zero probability)
  - A losing model at 5% can become dominant if evidence flips
  - Models compete on predictive accuracy + simplicity (Occam)
  - Evidence is multi-modal: observation fit, prediction success, parsimony

Architecture:
  - Model: a hypothesis with a generator (predict function) and prior
  - Evidence: observed data that updates model probabilities
  - Competition Pool: the ensemble of active models with probability weights
  - Bayesian Update: P(M|E) = P(E|M) * P(M) / P(E)
  - New models can be proposed at any time (from TheoryBuilder or externally)
"""

from __future__ import annotations

import logging
import math
import time
import numpy as np
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger('telos_model_competition')


@dataclass
class Model:
    """A competing hypothesis with probability weight."""
    id: str
    name: str
    description: str
    source: str  # e.g., "theory_builder", "expert", "stream"
    probability: float  # P(M) — current probability weight
    prior: float  # P(M) at initialization
    likelihood_history: List[float] = field(default_factory=list)
    age_cycles: int = 0
    times_updated: int = 0
    parsimony: float = 0.5  # Simplicity score (0=complex, 1=simple)
    metadata: Dict[str, Any] = field(default_factory=dict)
    predictions_correct: int = 0
    predictions_total: int = 0
    bridges_formed: int = 0

    @property
    def accuracy(self) -> float:
        return self.predictions_correct / max(self.predictions_total, 1)

    @property
    def market_price(self) -> float:
        """Theory Market price based on prediction accuracy, parsimony, bridging."""
        return (self.accuracy * 0.4 + self.parsimony * 0.3 +
                min(1.0, self.bridges_formed * 0.1) * 0.2 + self.probability * 0.1)

    @property
    def evidence_weight(self) -> float:
        """Total accumulated evidence for this model (product of likelihoods)."""
        if not self.likelihood_history:
            return self.prior
        # Geometric mean of likelihoods * prior (avoids vanishing underflow)
        log_evidence = math.log(max(self.prior, 1e-10))
        for lh in self.likelihood_history:
            log_evidence += math.log(max(lh, 1e-10))
        return math.exp(log_evidence)

@dataclass
class EvidenceRecord:
    """A piece of evidence used to update model probabilities."""
    id: str
    description: str
    likelihoods: Dict[str, float]  # model_id -> P(E|M)
    timestamp: float = field(default_factory=time.time)
    cycle: int = 0
    source: str = "observation"
    weight: float = 1.0  # Evidence weight (some evidence is more important)


@dataclass
class CompetitionSnapshot:
    """A snapshot of the competition state at a point in time."""
    cycle: int
    models: Dict[str, float]  # model_id -> probability
    dominant_model: Optional[str]
    entropy: float  # Probability distribution entropy
    evidence_count: int
    consensus_level: float  # 1.0 if one model dominates, 0.0 if uniform


class ModelCompetition:
    """Maintains multiple competing hypotheses with probability weights.

    The competition:
    1. Holds a pool of models with probability weights summing to 1.0
    2. Updates probabilities via Bayesian inference on new evidence
    3. Prevents any model from reaching 0.0 or 1.0 (always leaves room)
    4. Supports model proposal (new hypotheses) and retirement
    5. Records evidence history for audit and transparency

    Models can represent:
      - Competing explanations for an observed phenomenon
      - Different strategies for achieving a goal
      - Alternative causal models of the environment
      - Different interpretations of ambiguous input
    """

    def __init__(self, min_probability: float = 0.01,
                 max_models: int = 10,
                 entropy_floor: float = 0.01):
        self._models: Dict[str, Model] = {}
        self._evidence_history: List[EvidenceRecord] = []
        self._max_evidence = 200
        self._min_probability = min_probability  # Never go below this
        self._max_models = max_models
        self._entropy_floor = entropy_floor
        self._snapshots: List[CompetitionSnapshot] = []
        self._max_snapshots = 100
        self._update_count: int = 0

    def propose_model(self, name: str, description: str,
                       probability: Optional[float] = None,
                       source: str = "external",
                       parsimony: float = 0.5,
                       metadata: Optional[Dict] = None) -> str:
        """Propose a new competing model.

        Args:
            name: Human-readable name for the model
            description: What this model hypothesizes
            probability: Initial probability weight (auto-set if None)
            source: Origin of the model
            parsimony: Simplicity score [0-1]
            metadata: Additional info

        Returns:
            model_id of the new model
        """
        if len(self._models) >= self._max_models:
            # Retire the weakest model to make room
            weakest = min(self._models.items(), key=lambda x: x[1].probability)
            logger.info(f"ModelCompetition: retiring weakest model '{weakest[1].name}' "
                       f"(p={weakest[1].probability:.3f}) to make room")
            del self._models[weakest[0]]

        model_id = f"model_{int(time.time()*1000)}_{len(self._models)}"

        if probability is None:
            # Equal prior among all models
            n_models = len(self._models) + 1
            probability = 1.0 / n_models

        model = Model(
            id=model_id,
            name=name,
            description=description,
            source=source,
            probability=probability,
            prior=probability,
            parsimony=parsimony,
            metadata=metadata or {},
        )

        self._models[model_id] = model
        self._renormalize()

        logger.info(f"ModelCompetition: proposed model '{name}' (p={probability:.3f}, "
                   f"source={source}) — {len(self._models)} models active")

        return model_id

    def record_prediction(self, model_id: str, correct: bool) -> None:
        """Record a prediction outcome for Theory Market pricing.
        model_id: the model id for this operation
        correct: the correct for this operation
"""
        model = self._models.get(model_id)
        if model:
            model.predictions_total += 1
            if correct:
                model.predictions_correct += 1

    def submit_evidence(self, description: str,
                         likelihoods: Dict[str, float],
                         source: str = "observation",
                         cycle: int = 0,
                         weight: float = 1.0) -> EvidenceRecord:
        """Submit evidence that updates model probabilities.

        Args:
            description: What the evidence is
            likelihoods: Dict mapping model_id -> P(E|M) (likelihood of evidence
                        given each model). If a model is missing, default 0.5 used.
            source: Origin of the evidence
            cycle: Pipeline cycle
            weight: Importance weight for this evidence

        Returns:
            EvidenceRecord
        """
        # Fill in missing models with neutral likelihood
        filled_likelihoods = {}
        for mid in self._models:
            filled_likelihoods[mid] = likelihoods.get(mid, 0.5)

        evidence = EvidenceRecord(
            id=f"ev_{int(time.time()*1000)}",
            description=description,
            likelihoods=filled_likelihoods,
            source=source,
            cycle=cycle,
            weight=weight,
        )

        self._evidence_history.append(evidence)
        if len(self._evidence_history) > self._max_evidence:
            self._evidence_history.pop(0)

        # Apply Bayesian update
        self._bayesian_update(evidence)

        self._update_count += 1

        # Take snapshot
        self._snapshot(cycle)

        return evidence

    def _bayesian_update(self, evidence: EvidenceRecord) -> None:
        """Apply Bayes' rule: P(M|E) = P(E|M) * P(M) / normalize.
        evidence: the evidence for this operation
"""
        if not self._models:
            return

        # Compute unnormalized posteriors
        posteriors: Dict[str, float] = {}
        for mid, model in self._models.items():
            likelihood = evidence.likelihoods.get(mid, 0.5)
            # Apply evidence weight as exponent (weight=1.0 is standard)
            weighted_likelihood = likelihood ** evidence.weight
            posteriors[mid] = weighted_likelihood * model.probability

        # Normalize
        total = sum(posteriors.values())
        if total <= 0:
            return  # All zero — keep current probabilities

        for mid in self._models:
            raw = posteriors[mid] / total
            # Clamp to [min_probability, 1.0]
            self._models[mid].probability = max(self._min_probability, min(1.0, raw))
            self._models[mid].likelihood_history.append(evidence.likelihoods.get(mid, 0.5))
            self._models[mid].age_cycles += 1
            self._models[mid].times_updated += 1

        # Renormalize after clamping
        self._renormalize()

        # Log dominant model
        dominant = self.dominant_model
        if dominant:
            logger.debug(
                f"ModelCompetition: evidence '{evidence.description[:30]}...' → "
                f"dominant={dominant.name} (p={dominant.probability:.3f})"
            )

    def _renormalize(self) -> None:
        """Ensure probabilities sum to 1.0 after clamping."""
        total = sum(m.probability for m in self._models.values())
        if total <= 0:
            return
        for model in self._models.values():
            model.probability /= total

    def _snapshot(self, cycle: int) -> None:
        """Record current state of the competition.
        cycle: the current pipeline cycle number
"""
        snapshot = CompetitionSnapshot(
            cycle=cycle,
            models={mid: m.probability for mid, m in self._models.items()},
            dominant_model=self.dominant_model.id if self.dominant_model else None,
            entropy=self.compute_entropy(),
            evidence_count=len(self._evidence_history),
            consensus_level=self.compute_consensus(),
        )
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)

    def compute_entropy(self) -> float:
        """Shannon entropy of the probability distribution over models."""
        if not self._models:
            return 0.0
        entropy = 0.0
        for model in self._models.values():
            p = model.probability
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy / math.log2(len(self._models)) if len(self._models) > 1 else 0.0

    def compute_consensus(self) -> float:
        """How much consensus exists. 1.0 = one model dominates, 0.0 = uniform."""
        if not self._models:
            return 0.0
        max_p = max(m.probability for m in self._models.values())
        n = len(self._models)
        # Normalize: max_p = 1.0 → 1.0, max_p = 1/n → 0.0
        if n <= 1:
            return 1.0
        return (max_p - 1.0/n) / (1.0 - 1.0/n)

    @property
    def dominant_model(self) -> Optional[Model]:
        """The model with highest probability."""
        if not self._models:
            return None
        return max(self._models.values(), key=lambda m: m.probability)

    @property
    def second_best(self) -> Optional[Model]:
        """The second highest probability model (the challenger)."""
        if len(self._models) < 2:
            return None
        sorted_models = sorted(self._models.values(), key=lambda m: m.probability, reverse=True)
        return sorted_models[1]

    def get_winner(self) -> Optional[Model]:
        """Get the model that has won the competition (dominant for most updates)."""
        if not self._snapshots or self._update_count < 3:
            return self.dominant_model

        # Check which model has been dominant most recently
        recent = self._snapshots[-min(10, len(self._snapshots)):]
        dominance_counts: Dict[str, int] = defaultdict(int)
        for snap in recent:
            if snap.dominant_model:
                dominance_counts[snap.dominant_model] += 1

        if not dominance_counts:
            return self.dominant_model

        most_consistent = max(dominance_counts, key=dominance_counts.get)
        return self._models.get(most_consistent)

    def to_dict(self) -> Dict:
        return {
            "update_count": self._update_count,
            "active_models": len(self._models),
            "entropy": round(self.compute_entropy(), 4),
            "consensus": round(self.compute_consensus(), 4),
            "models": [
                {
                    "id": mid,
                    "name": m.name,
                    "probability": round(m.probability, 4),
                    "prior": round(m.prior, 4),
                    "parsimony": round(m.parsimony, 3),
                    "source": m.source,
                    "age_cycles": m.age_cycles,
                    "times_updated": m.times_updated,
                    "description": m.description[:60],
                }
                for mid, m in sorted(
                    self._models.items(),
                    key=lambda x: -x[1].probability,
                )
            ],
            "evidence_count": len(self._evidence_history),
            "dominant_model": self.dominant_model.name if self.dominant_model else None,
            "second_best": self.second_best.name if self.second_best else None,
        }
