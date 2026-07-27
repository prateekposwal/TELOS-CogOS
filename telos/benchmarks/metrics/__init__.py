"""
from __future__ import annotations
import enum
import math
import time
import json
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

BenchmarkCollector — TELOS Cognitive Benchmark Framework.

===============================================================
  Observing the Hidden Cognitive State X
===============================================================

The system possesses an unobservable hidden cognitive state X(t) that
encodes all internal representations, beliefs, identity structures,
and strategic commitments. No single metric can observe X directly.

Instead, the benchmark framework projects X(t) onto 7 orthogonal
measurement axes corresponding to conserved cognitive processes.
Each metric is a projection ⟨X|M_i⟩ — a 1-dimensional shadow cast
by the hidden state onto an observable instrument.

Hierarchical aggregation:
  Metrics ──→ Subsystem Score ──→ System Score ──→ Mission Score

7 Conserved Cognitive Processes (measurement axes):
  1. Perception    — sensing, prediction, uncertainty calibration
  2. Learning      — curiosity, compression, knowledge acquisition
  3. Identity      — coherence, continuity, propagation through decisions
  4. Knowledge     — representation ecology, epistemic capital, yield pipeline
  5. Resources     — compute/memory/bandwidth/storage, CROI
  6. Projects      — completion, strategic alignment hierarchy
  7. Social        — ecosystem niches, bridges, collaboration

Wired into pipeline_finalize.py: runs every cycle after axiom verification.
"""

from __future__ import annotations

import json
import os
import time
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import enum

logger = logging.getLogger('telos_benchmark')


# ═══════════════════════════════════════════════════════════════════
# Trend Analysis
# ═══════════════════════════════════════════════════════════════════

class Trend(str, enum.Enum):
    """Three-state trend classification."""
    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"


def classify_trend(values: List[float], window: int = 5, threshold: float = 0.03) -> Trend:
    """Classify a time-series as rising, stable, or declining.

    Uses linear regression slope over the last `window` points.
    If |slope| < threshold, classified as stable.
    """
    if len(values) < 3:
        return Trend.INSUFFICIENT_DATA
    recent = values[-min(window, len(values)):]
    n = len(recent)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(recent) / n
    num = sum((xs[i] - mean_x) * (recent[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return Trend.STABLE
    slope = num / den
    if abs(slope) < threshold:
        return Trend.STABLE
    return Trend.RISING if slope > 0 else Trend.DECLINING


# ═══════════════════════════════════════════════════════════════════
# Snapshot: A single-cycle projection of hidden cognitive state X
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BenchmarkSnapshot:
    """Immutable per-cycle snapshot — a projection of hidden state X(t).

    Each field is an observable projection ⟨X|M_i⟩ of the unobservable
    cognitive state X onto measurement axis M_i.

    Organized by 7 conserved cognitive processes. Composite scores
    are computed at 4 levels: Metric → Subsystem → System → Mission.
    """
    cycle: int
    timestamp: float

    # ── 1. Perception ─────────────────────────────────────────────
    # Prediction Health metrics: calibration, surprise, unknown unknowns
    state_estimation_error: float       # 0+ (lower better)
    surprise_rate: float                # 0-1 (lower better — expected surprise)
    unknown_unknown_discovery_rate: float  # 0+ (new unexpected patterns found)
    forecast_accuracy: float            # 0-1 (Brier score / calibration)
    counterfactual_accuracy: float      # 0-1 (counterfactual reasoning quality)

    # ── 2. Learning ──────────────────────────────────────────────
    curiosity_level: float              # 0-1
    learning_rate: float                # 0+ (bits per cycle)
    compression_rate: float             # 0-1 (representation compression)
    boredom_count: int                  # cycles bored
    exploration_ratio: float            # 0-1
    # Knowledge Yield Pipeline: Observation → Theory → Prediction → Validated → Principles
    knowledge_yield_observations: int
    knowledge_yield_theories: int
    knowledge_yield_predictions: int
    knowledge_yield_validated: int
    knowledge_yield_principles: int

    # ── 3. Identity ──────────────────────────────────────────────
    identity_entropy: float             # 0+ (lower = more coherent)
    identity_continuity: float          # 0-1
    relational_coherence: float         # 0-1 (narrative consistency)
    # Identity Propagation: how identity flows through the system
    mission_alignment: float            # 0-1 (decisions ← mission)
    project_alignment: float            # 0-1 (projects ← mission)
    decision_alignment: float           # 0-1 (actions ← decisions)

    # ── 4. Knowledge ─────────────────────────────────────────────
    # Representation Ecology
    representation_age_mean: float      # mean age of representations
    representation_diversity: float     # 0-1 (Shannon diversity)
    retirement_rate: float              # 0-1 (fraction retired per cycle)
    bridge_density: float               # 0+ (bridges / total representations)
    reuse_rate: float                   # 0-1 (fraction of reused reps)
    compression_achieved: float         # 0-1 (compression ratio achieved)
    # Epistemic Capital (renamed from Belief Capital)
    epistemic_ideas: int
    epistemic_top_capital: float
    # Theory genealogy
    theory_nodes: int
    theory_roots: int
    # Bridge Potential (aggregate)
    bridge_potential_avg: float         # 0-1 (mean bridge potential across reps)

    # ── 5. Resources ─────────────────────────────────────────────
    compute_utilization: float          # 0-1
    memory_utilization: float           # 0-1
    bandwidth_utilization: float        # 0-1
    storage_utilization: float          # 0-1
    # Cognitive Return on Investment (CROI)
    croi: float                         # knowledge gained / resource consumed

    # ── 6. Projects ──────────────────────────────────────────────
    active_projects: int
    total_projects: int
    completed_projects: int
    abandoned_projects: int
    # Strategic Coherence — alignment hierarchy
    strategic_alignment_mission_projects: float   # Mission→Projects
    strategic_alignment_project_tasks: float      # Projects→Tasks
    strategic_alignment_task_actions: float       # Tasks→Actions
    mission_alignment_overall: float              # Mission→Actions (composite)

    # ── 7. Social ────────────────────────────────────────────────
    niche_count: int
    exhausted_niches: int
    bridge_count: int
    social_relations: int
    collaboration_efficiency: float     # 0-1

    # ── Composite Scores (4-level hierarchy, computed post-init) ──
    perception_score: float = 0.0       # Level 2: Subsystem
    learning_score: float = 0.0
    identity_score: float = 0.0
    knowledge_score: float = 0.0
    resource_score: float = 0.0
    project_score: float = 0.0
    social_score: float = 0.0
    system_score: float = 0.0           # Level 3: System
    mission_score: float = 0.0          # Level 4: Mission (context-weighted)

    @property
    def exhaustion_rate(self) -> float:
        return self.exhausted_niches / max(self.niche_count, 1)

    @property
    def project_completion_rate(self) -> float:
        return self.completed_projects / max(self.total_projects, 1)

    @property
    def abandonment_rate(self) -> float:
        return self.abandoned_projects / max(self.total_projects, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "perception": {
                "state_estimation_error": round(self.state_estimation_error, 4),
                "surprise_rate": round(self.surprise_rate, 4),
                "unknown_unknown_discovery_rate": round(self.unknown_unknown_discovery_rate, 4),
                "forecast_accuracy": round(self.forecast_accuracy, 4),
                "counterfactual_accuracy": round(self.counterfactual_accuracy, 4),
                "score": round(self.perception_score, 4),
            },
            "learning": {
                "curiosity_level": round(self.curiosity_level, 4),
                "learning_rate": round(self.learning_rate, 4),
                "compression_rate": round(self.compression_rate, 4),
                "boredom_count": self.boredom_count,
                "exploration_ratio": round(self.exploration_ratio, 4),
                "knowledge_yield": {
                    "observations": self.knowledge_yield_observations,
                    "theories": self.knowledge_yield_theories,
                    "predictions": self.knowledge_yield_predictions,
                    "validated": self.knowledge_yield_validated,
                    "principles": self.knowledge_yield_principles,
                },
                "score": round(self.learning_score, 4),
            },
            "identity": {
                "identity_entropy": round(self.identity_entropy, 4),
                "identity_continuity": round(self.identity_continuity, 4),
                "relational_coherence": round(self.relational_coherence, 4),
                "propagation": {
                    "mission_alignment": round(self.mission_alignment, 4),
                    "project_alignment": round(self.project_alignment, 4),
                    "decision_alignment": round(self.decision_alignment, 4),
                },
                "score": round(self.identity_score, 4),
            },
            "knowledge": {
                "representation_ecology": {
                    "mean_age": round(self.representation_age_mean, 2),
                    "diversity": round(self.representation_diversity, 4),
                    "retirement_rate": round(self.retirement_rate, 4),
                    "bridge_density": round(self.bridge_density, 4),
                    "reuse_rate": round(self.reuse_rate, 4),
                    "compression_achieved": round(self.compression_achieved, 4),
                },
                "epistemic_capital": {
                    "total_ideas": self.epistemic_ideas,
                    "top_capital": round(self.epistemic_top_capital, 4),
                },
                "theory_genealogy": {
                    "nodes": self.theory_nodes,
                    "roots": self.theory_roots,
                },
                "bridge_potential_avg": round(self.bridge_potential_avg, 4),
                "score": round(self.knowledge_score, 4),
            },
            "resources": {
                "compute_utilization": round(self.compute_utilization, 4),
                "memory_utilization": round(self.memory_utilization, 4),
                "bandwidth_utilization": round(self.bandwidth_utilization, 4),
                "storage_utilization": round(self.storage_utilization, 4),
                "croi": round(self.croi, 4),
                "score": round(self.resource_score, 4),
            },
            "projects": {
                "active_projects": self.active_projects,
                "total_projects": self.total_projects,
                "completed_projects": self.completed_projects,
                "abandoned_projects": self.abandoned_projects,
                "completion_rate": round(self.project_completion_rate, 4),
                "abandonment_rate": round(self.abandonment_rate, 4),
                "strategic_alignment": {
                    "mission_projects": round(self.strategic_alignment_mission_projects, 4),
                    "project_tasks": round(self.strategic_alignment_project_tasks, 4),
                    "task_actions": round(self.strategic_alignment_task_actions, 4),
                    "overall": round(self.mission_alignment_overall, 4),
                },
                "score": round(self.project_score, 4),
            },
            "social": {
                "niche_count": self.niche_count,
                "exhausted_niches": self.exhausted_niches,
                "exhaustion_rate": round(self.exhaustion_rate, 4),
                "bridge_count": self.bridge_count,
                "relations": self.social_relations,
                "collaboration_efficiency": round(self.collaboration_efficiency, 4),
                "score": round(self.social_score, 4),
            },
            "hierarchy": {
                "subsystem_scores": {
                    "perception": round(self.perception_score, 4),
                    "learning": round(self.learning_score, 4),
                    "identity": round(self.identity_score, 4),
                    "knowledge": round(self.knowledge_score, 4),
                    "resources": round(self.resource_score, 4),
                    "projects": round(self.project_score, 4),
                    "social": round(self.social_score, 4),
                },
                "system_score": round(self.system_score, 4),
                "mission_score": round(self.mission_score, 4),
            },
        }


# ═══════════════════════════════════════════════════════════════════
# Hierarchical Aggregation Functions
# ═══════════════════════════════════════════════════════════════════
# Level 1: Metrics (raw fields on BenchmarkSnapshot)
# Level 2: Subsystem Scores (one per conserved cognitive process)
# Level 3: System Score (aggregate of subsystem scores)
# Level 4: Mission Score (system score re-weighted for current mission)

def compute_subsystem_scores(snapshot: BenchmarkSnapshot) -> Dict[str, float]:
    """Compute 7 subsystem scores from raw metrics. (Level 2)"""

    # 1. Perception Score
    # Low estimation error = good, low surprise = good (but some is healthy),
    # high forecast accuracy = good, high counterfactual accuracy = good.
    # Unknown unknown discovery is healthy in moderation.
    inv_error = 1.0 - min(snapshot.state_estimation_error / 2.0, 1.0)
    inv_surprise = 1.0 - min(snapshot.surprise_rate * 2.0, 1.0)
    uu_healthy = min(snapshot.unknown_unknown_discovery_rate * 3.0, 1.0)
    perception_score = (
        inv_error * 0.25
        + inv_surprise * 0.15
        + snapshot.forecast_accuracy * 0.30
        + snapshot.counterfactual_accuracy * 0.20
        + uu_healthy * 0.10
    )

    # 2. Learning Score
    # Curiosity drives exploration, compression indicates pattern extraction.
    # Knowledge yield pipeline: observations → theories → predictions → validated → principles
    yield_obs = min(snapshot.knowledge_yield_observations / 50.0, 1.0) * 0.10
    yield_theories = min(snapshot.knowledge_yield_theories / 20.0, 1.0) * 0.15
    yield_preds = min(snapshot.knowledge_yield_predictions / 50.0, 1.0) * 0.15
    yield_validated = min(snapshot.knowledge_yield_validated / 20.0, 1.0) * 0.25
    yield_principles = min(snapshot.knowledge_yield_principles / 10.0, 1.0) * 0.35
    yield_pipeline = (yield_obs + yield_theories + yield_preds +
                      yield_validated + yield_principles) / 5.0
    learning_score = (
        snapshot.curiosity_level * 0.20
        + min(snapshot.learning_rate * 5.0, 1.0) * 0.20
        + snapshot.compression_rate * 0.15
        + snapshot.exploration_ratio * 0.15
        + yield_pipeline * 0.30
    )

    # 3. Identity Score
    # Low entropy = coherent identity, high continuity = stable, high coherence.
    # Identity propagation: do mission/project/decision alignments hold?
    inv_entropy = 1.0 - min(snapshot.identity_entropy * 2.0, 1.0)
    propagation = (
        snapshot.mission_alignment * 0.35
        + snapshot.project_alignment * 0.35
        + snapshot.decision_alignment * 0.30
    )
    identity_score = (
        inv_entropy * 0.20
        + snapshot.identity_continuity * 0.20
        + snapshot.relational_coherence * 0.25
        + propagation * 0.35
    )

    # 4. Knowledge Score
    # Representation ecology: diversity is good, low retirement is good,
    # high bridge density = good, high reuse = efficient,
    # high compression = effective.
    eco_diversity = min(snapshot.representation_diversity * 2.0, 1.0)
    eco_retirement = 1.0 - min(snapshot.retirement_rate * 5.0, 1.0)
    eco_bridge = min(snapshot.bridge_density * 3.0, 1.0)
    eco_reuse = snapshot.reuse_rate
    eco_compression = snapshot.compression_achieved
    ecology_score = (
        eco_diversity * 0.20
        + eco_retirement * 0.15
        + eco_bridge * 0.25
        + eco_reuse * 0.25
        + eco_compression * 0.15
    )
    # Epistemic capital
    epistemic = min(snapshot.epistemic_top_capital * 2.0, 1.0)
    # Theory nodes (healthy knowledge base)
    theory_health = min(snapshot.theory_nodes / 20.0, 1.0)
    # Bridge potential
    bridge_pot = snapshot.bridge_potential_avg
    knowledge_score = (
        ecology_score * 0.20
        + epistemic * 0.20
        + theory_health * 0.15
        + bridge_pot * 0.25
        + min(snapshot.reuse_rate, 1.0) * 0.10
        + min(snapshot.representation_age_mean / 200.0, 1.0) * 0.10
    )

    # 5. Resource Score
    # Sweet spot at ~50% utilization (headroom without waste)
    def _resource_sweetspot(util: float) -> float:
        return max(0.0, 1.0 - abs(util - 0.5) * 2.0)
    compute_h = _resource_sweetspot(snapshot.compute_utilization)
    memory_h = _resource_sweetspot(snapshot.memory_utilization)
    bandwidth_h = _resource_sweetspot(snapshot.bandwidth_utilization)
    storage_h = _resource_sweetspot(snapshot.storage_utilization)
    resource_score = (
        compute_h * 0.25
        + memory_h * 0.25
        + bandwidth_h * 0.15
        + storage_h * 0.15
        + min(snapshot.croi * 5.0, 1.0) * 0.20
    )

    # 6. Project Score
    # Completion rate, low abandonment, strategic alignment hierarchy
    completion = snapshot.project_completion_rate
    inv_abandon = 1.0 - snapshot.abandonment_rate
    alignment_hierarchy = (
        snapshot.strategic_alignment_mission_projects * 0.30
        + snapshot.strategic_alignment_project_tasks * 0.30
        + snapshot.strategic_alignment_task_actions * 0.25
        + snapshot.mission_alignment_overall * 0.15
    )
    project_score = (
        completion * 0.25
        + inv_abandon * 0.20
        + alignment_hierarchy * 0.40
        + min(snapshot.active_projects / 10.0, 1.0) * 0.15
    )

    # 7. Social Score
    # Niche diversity, low exhaustion, bridges, collaboration
    niche_div = min(snapshot.niche_count / 15.0, 1.0) * 0.20
    inv_exhaust = (1.0 - snapshot.exhaustion_rate) * 0.25
    bridges = min(snapshot.bridge_count / 5.0, 1.0) * 0.25
    collab = snapshot.collaboration_efficiency * 0.30
    social_score = niche_div + inv_exhaust + bridges + collab

    return {
        "perception": round(perception_score, 4),
        "learning": round(learning_score, 4),
        "identity": round(identity_score, 4),
        "knowledge": round(knowledge_score, 4),
        "resources": round(resource_score, 4),
        "projects": round(project_score, 4),
        "social": round(social_score, 4),
    }


def compute_system_score(subsystem_scores: Dict[str, float]) -> float:
    """Aggregate 7 subsystem scores into system score. (Level 3)

    Uses weighted arithmetic mean (not harmonic) since subsystem scores
    are already normalized composites. Weights reflect architectural
    priority: Identity and Knowledge are foundational; Perception and
    Learning are operational; Resources, Projects, Social are contextual.
    """
    weights = {
        "perception": 0.15,
        "learning": 0.15,
        "identity": 0.20,      # identity shapes decisions (Axiom 4.1)
        "knowledge": 0.20,     # epistemic foundation
        "resources": 0.10,
        "projects": 0.10,
        "social": 0.10,
    }
    total = sum(weights.get(k, 0.1) * v for k, v in subsystem_scores.items())
    return round(total, 4)


def compute_mission_score(system_score: float,
                          subsystem_scores: Dict[str, float],
                          mission_context: Optional[Dict[str, float]] = None) -> float:
    """Compute mission-contextualized system score. (Level 4)

    The hidden cognitive state X(t) is deployed in service of a mission.
    Mission context re-weights subsystem scores. Default (no context):
    system_score is used directly.

    mission_context: dict of subsystem → importance weight (0-1).
    """
    if not mission_context:
        return system_score
    # Re-weight subsystem scores according to mission context
    total_weight = sum(mission_context.values())
    if total_weight == 0:
        return system_score
    weighted = sum(
        subsystem_scores.get(k, 0.0) * w
        for k, w in mission_context.items()
    )
    context_score = round(weighted / total_weight, 4)
    # Blend with system score (mission contextualization should not fully
    # override the overall system assessment)
    return round(0.6 * context_score + 0.4 * system_score, 4)


# ═══════════════════════════════════════════════════════════════════
# Aggregate Reports
# ═══════════════════════════════════════════════════════════════════
