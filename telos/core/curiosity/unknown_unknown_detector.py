"""
UnknownUnknownDetector — Detect What the System Should Know But Hasn't Considered.

Prateek's insight: "Unknown unknowns — the system should detect anomalies,
find what it should know but hasn't considered. Observation → Prediction →
Residual → Novelty Cluster → New Question."

Most anomaly detection finds known unknowns (deviations from expected patterns).
This detector finds unknown unknowns: regions of the state space where the
system lacks a model entirely — not just prediction error, but surprise that
reveals a missing concept.

Architecture:
  Observation → Prediction → Residual (error) → Residual Cluster →
  Novelty Score → New Question Formation → Belief Update Request

Pipeline:
  1. Observe state vector S_t
  2. Generate prediction P_t from current world model
  3. Compute residual R_t = |S_t - P_t|
  4. Cluster residuals over time to find persistent blind spots
  5. Compute novelty score: does this residual correspond to a known concept?
  6. If novelty exceeds threshold, form a New Question (unknown unknown)
  7. Submit question to pipeline for belief revision

Key insight: Unknown unknowns are NOT just high residuals. They are residuals
that don't match any known error pattern — the system doesn't know it doesn't know.
"""

from __future__ import annotations

import logging
import time
import math
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('telos_unknown_unknown_detector')


class ResidualClass(Enum):
    KNOWN_KNOWN = "known_known"           # Predicted correctly — no surprise
    KNOWN_UNKNOWN = "known_unknown"       # Expected error — within noise model
    UNKNOWN_KNOWN = "unknown_known"       # Predicted incorrectly but pattern known
    UNKNOWN_UNKNOWN = "unknown_unknown"   # No model exists for this region — TRUE BLIND SPOT


@dataclass
class Residual:
    """A single prediction residual with classification."""
    cycle: int
    feature_name: str
    predicted: float
    observed: float
    magnitude: float
    residual_class: ResidualClass
    cluster_id: Optional[str] = None
    novelty_score: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class NoveltyCluster:
    """A cluster of related residuals that may indicate an unknown unknown."""
    id: str
    residuals: List[Residual] = field(default_factory=list)
    centroid: Optional[np.ndarray] = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    persistent_count: int = 0       # How many cycles this cluster has appeared
    novelty_score: float = 0.0      # Rolling novelty score
    elevated_to_question: bool = False  # Has this been promoted to a question?

    @property
    def mean_residual(self) -> float:
        if not self.residuals:
            return 0.0
        return sum(r.magnitude for r in self.residuals) / len(self.residuals)

    @property
    def age_cycles(self) -> int:
        return max(r.cycle for r in self.residuals) - min(r.cycle for r in self.residuals) if len(self.residuals) > 1 else 0


@dataclass
class NewQuestion:
    """A question formed from an unknown unknown — submitted to the pipeline."""
    id: str
    source_cluster_id: str
    question_text: str
    feature_names: List[str]
    residual_magnitude: float
    formed_at_cycle: int
    answered: bool = False
    answer_summary: str = ""
    dismissed: bool = False
    dismissal_reason: str = ""


class UnknownUnknownDetector:
    """Detects anomalies that indicate missing concepts (unknown unknowns).

    The detector:
    1. Maintains a library of known residual patterns (known unknowns)
    2. Classifies new residuals against known patterns
    3. Clusters residuals that don't match any known pattern
    4. Promotes persistent clusters to "New Questions"
    5. Tracks which questions have been answered vs dismissed

    Integrates with:
      - Pipeline evaluation phase (receives predictions and observations)
      - TheoryBuilder (new questions feed hypothesis generation)
      - CuriosityDrive (unknown unknowns trigger epistemic curiosity)
    """

    def __init__(self, window_size: int = 50,
                 novelty_threshold: float = 0.7,
                 persistence_threshold: int = 3,
                 max_clusters: int = 20):
        self._window_size = window_size
        self._novelty_threshold = novelty_threshold
        self._persistence_threshold = persistence_threshold  # cycles before promotion
        self._max_clusters = max_clusters

        # Known error patterns — keyed by (feature_name, pattern_signature)
        self._known_patterns: Dict[str, Dict] = {}

        # Residual history
        self._residual_history: List[Residual] = []
        self._max_history = 200

        # Active novelty clusters
        self._clusters: Dict[str, NoveltyCluster] = {}

        # Questions formed
        self._questions: List[NewQuestion] = []
        self._max_questions = 50

        # Stats
        self._total_residuals: int = 0
        self._total_unknown_unknowns: int = 0
        self._total_new_questions: int = 0

    def _make_pattern_key(self, feature: str, residual: float) -> str:
        """Create a key for known pattern matching using discretized residual."""
        bucket = round(residual * 10) / 10  # discretize to 0.1 buckets
        return f"{feature}:{bucket}"

    def record_observation(self, cycle: int, predictions: Dict[str, float],
                           observations: Dict[str, float]) -> List[Residual]:
        """Record a set of predictions and observations, compute residuals.

        Args:
            cycle: Current pipeline cycle
            predictions: Dict mapping feature_name -> predicted value
            observations: Dict mapping feature_name -> observed value

        Returns:
            List of Residual objects, one per feature
        """
        residuals: List[Residual] = []
        all_features = set(list(predictions.keys()) + list(observations.keys()))

        for feature in all_features:
            pred = predictions.get(feature)
            obs = observations.get(feature)

            # Handle missing predictions (feature not modelled)
            if pred is None and obs is not None:
                magnitude = float(obs) if isinstance(obs, (int, float)) else 1.0
                rclass = ResidualClass.UNKNOWN_UNKNOWN
            elif pred is not None and obs is None:
                # Predicted feature not observed — model expects signal missing
                magnitude = abs(pred)
                rclass = ResidualClass.KNOWN_UNKNOWN
            elif pred is not None and obs is not None:
                magnitude = abs(obs - pred)
                rclass = self._classify_residual(feature, magnitude)
            else:
                continue

            residual = Residual(
                cycle=cycle,
                feature_name=feature,
                predicted=pred or 0.0,
                observed=obs or 0.0,
                magnitude=magnitude,
                residual_class=rclass,
                novelty_score=self._compute_novelty(feature, magnitude, rclass),
            )
            residuals.append(residual)

        # Store and cluster
        self._residual_history.extend(residuals)
        if len(self._residual_history) > self._max_history:
            self._residual_history = self._residual_history[-self._max_history:]

        self._total_residuals += len(residuals)

        # Cluster unknown unknowns
        uu_residuals = [r for r in residuals if r.residual_class == ResidualClass.UNKNOWN_UNKNOWN]
        if uu_residuals:
            self._cluster_unknown_unknowns(cycle, uu_residuals)

        return residuals

    def _classify_residual(self, feature: str, magnitude: float) -> ResidualClass:
        """Classify a residual against known error patterns."""
        pattern_key = self._make_pattern_key(feature, magnitude)

        if pattern_key in self._known_patterns:
            pattern = self._known_patterns[pattern_key]
            expected = pattern.get('expected_magnitude', magnitude)
            variance = pattern.get('variance', 0.1)

            if abs(magnitude - expected) <= 2 * variance:
                return ResidualClass.KNOWN_KNOWN
            else:
                return ResidualClass.UNKNOWN_KNOWN
        else:
            # No pattern exists — potential unknown unknown
            # Check if close to any existing pattern
            for pk, pat in self._known_patterns.items():
                if pk.startswith(f"{feature}:"):
                    expected = pat.get('expected_magnitude', magnitude)
                    if abs(magnitude - expected) <= 3 * pat.get('variance', 0.2):
                        return ResidualClass.KNOWN_UNKNOWN
            return ResidualClass.UNKNOWN_UNKNOWN

    def _compute_novelty(self, feature: str, magnitude: float,
                         rclass: ResidualClass) -> float:
        """Compute a novelty score for this residual.

        Novelty is high when:
        - The residual class is unknown unknown (no model exists)
        - The magnitude is large relative to known patterns
        - The feature has never been seen before
        """
        if rclass == ResidualClass.UNKNOWN_UNKNOWN:
            base = 0.8
        elif rclass == ResidualClass.UNKNOWN_KNOWN:
            base = 0.5
        elif rclass == ResidualClass.KNOWN_UNKNOWN:
            base = 0.3
        else:
            base = 0.0

        # Scale by magnitude (saturating at 2.0)
        magnitude_factor = min(1.0, magnitude / 2.0)

        # Check if feature is entirely new
        feature_seen = any(
            r.feature_name == feature
            for r in self._residual_history[-100:]
        )
        novelty_boost = 0.2 if not feature_seen else 0.0

        return min(1.0, base + magnitude_factor * 0.3 + novelty_boost)

    def _cluster_unknown_unknowns(self, cycle: int,
                                   residuals: List[Residual]) -> None:
        """Cluster unknown unknown residuals by feature proximity."""
        for residual in residuals:
            # Try to match to existing cluster
            matched = False
            for cid, cluster in self._clusters.items():
                if cluster.elevated_to_question:
                    continue
                # Check feature overlap
                cluster_features = {r.feature_name for r in cluster.residuals}
                if residual.feature_name in cluster_features:
                    cluster.residuals.append(residual)
                    cluster.last_seen = time.time()
                    cluster.persistent_count += 1
                    cluster.novelty_score = max(cluster.novelty_score,
                                                residual.novelty_score)
                    matched = True
                    break

            if not matched and len(self._clusters) < self._max_clusters:
                # Create new cluster
                cid = f"uucluster_{int(time.time()*1000)}_{len(self._clusters)}"
                cluster = NoveltyCluster(
                    id=cid,
                    residuals=[residual],
                    novelty_score=residual.novelty_score,
                )
                self._clusters[cid] = cluster

    def promote_to_questions(self, cycle: int) -> List[NewQuestion]:
        """Promote persistent unknown unknown clusters to New Questions.

        A cluster is promoted when:
        - It has appeared for >= persistence_threshold cycles
        - Its novelty score exceeds novelty_threshold
        - It hasn't already been promoted
        """
        new_questions: List[NewQuestion] = []

        for cid, cluster in list(self._clusters.items()):
            if cluster.elevated_to_question:
                continue
            if cluster.persistent_count < self._persistence_threshold:
                continue
            if cluster.novelty_score < self._novelty_threshold:
                continue

            # Extract common features
            features = list({r.feature_name for r in cluster.residuals})
            avg_residual = cluster.mean_residual

            # Formulate question
            if len(features) == 1:
                question = f"Why does feature '{features[0]}' consistently produce "
                f"unexpected observations (avg residual: {avg_residual:.3f})?"
            else:
                question = (f"What explains the persistent residual pattern across "
                           f"features {features} (avg residual: {avg_residual:.3f})?")

            new_q = NewQuestion(
                id=f"uq_{cycle}_{self._total_new_questions}",
                source_cluster_id=cid,
                question_text=question,
                feature_names=features,
                residual_magnitude=avg_residual,
                formed_at_cycle=cycle,
            )

            self._questions.append(new_q)
            if len(self._questions) > self._max_questions:
                self._questions.pop(0)

            cluster.elevated_to_question = True
            new_questions.append(new_q)
            self._total_new_questions += 1
            self._total_unknown_unknowns += 1

            logger.info(
                f"UnknownUnknownDetector: New Question formed — "
                f"'{question[:60]}...' (novelty={cluster.novelty_score:.2f})"
            )

        return new_questions

    def learn_pattern(self, feature: str, residual: float) -> None:
        """Register a residual pattern as a known (learned) pattern.

        Called when a previously unknown pattern has been explained.
        """
        pattern_key = self._make_pattern_key(feature, residual)

        if pattern_key not in self._known_patterns:
            self._known_patterns[pattern_key] = {
                'feature': feature,
                'expected_magnitude': residual,
                'variance': 0.1,
                'samples': 1,
                'learned_at': time.time(),
            }
            logger.debug(f"UnknownUnknownDetector: learned pattern {pattern_key}")
        else:
            # Update running stats
            pat = self._known_patterns[pattern_key]
            n = pat['samples']
            pat['expected_magnitude'] = (pat['expected_magnitude'] * n + residual) / (n + 1)
            # Update variance
            old_var = pat['variance']
            pat['variance'] = math.sqrt((old_var**2 * n + (residual - pat['expected_magnitude'])**2) / (n + 1))
            pat['samples'] = n + 1

    def answer_question(self, question_id: str, summary: str) -> bool:
        """Mark a question as answered with a summary."""
        for q in self._questions:
            if q.id == question_id:
                q.answered = True
                q.answer_summary = summary
                # Pattern is now known — remove corresponding cluster
                cid = q.source_cluster_id
                if cid in self._clusters:
                    # Learn the pattern from cluster residuals
                    for r in self._clusters[cid].residuals:
                        self.learn_pattern(r.feature_name, r.magnitude)
                    del self._clusters[cid]
                logger.info(f"UnknownUnknownDetector: Question '{q.id}' answered")
                return True
        return False

    def dismiss_question(self, question_id: str, reason: str = "false positive") -> bool:
        """Dismiss a question as a false positive."""
        for q in self._questions:
            if q.id == question_id:
                q.dismissed = True
                q.dismissal_reason = reason
                logger.info(f"UnknownUnknownDetector: Question '{q.id}' dismissed: {reason}")
                return True
        return False

    def get_unanswered_questions(self) -> List[NewQuestion]:
        return [q for q in self._questions if not q.answered and not q.dismissed]

    def get_active_clusters(self) -> List[NoveltyCluster]:
        return [c for c in self._clusters.values() if not c.elevated_to_question]

    @property
    def unknown_unknown_count(self) -> int:
        return self._total_unknown_unknowns

    @property
    def new_question_count(self) -> int:
        return self._total_new_questions

    @property
    def known_pattern_count(self) -> int:
        return len(self._known_patterns)

    def to_dict(self) -> Dict:
        return {
            "total_residuals": self._total_residuals,
            "total_unknown_unknowns": self._total_unknown_unknowns,
            "total_new_questions": self._total_new_questions,
            "known_patterns_count": self.known_pattern_count,
            "active_clusters": [
                {
                    "id": c.id,
                    "residual_count": len(c.residuals),
                    "persistent_cycles": c.persistent_count,
                    "novelty_score": round(c.novelty_score, 3),
                    "mean_residual": round(c.mean_residual, 3),
                    "features": list({r.feature_name for r in c.residuals}),
                    "elevated": c.elevated_to_question,
                }
                for c in self._clusters.values()
            ],
            "unanswered_questions": [
                {
                    "id": q.id,
                    "question": q.question_text[:80],
                    "features": q.feature_names,
                    "formed_at_cycle": q.formed_at_cycle,
                }
                for q in self.get_unanswered_questions()
            ],
            "known_patterns_sample": list(self._known_patterns.keys())[:20],
        }
