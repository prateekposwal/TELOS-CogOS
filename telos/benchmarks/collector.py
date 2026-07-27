"""
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

@dataclass
class EpochSummary:
    """Aggregate statistics across a window of cycles."""
    cycle_start: int
    cycle_end: int
    snapshots: List[BenchmarkSnapshot] = field(default_factory=list)

    @property
    def n_cycles(self) -> int:
        return len(self.snapshots)

    def aggregate(self) -> Dict[str, Any]:
        """Compute summary statistics over the epoch."""
        if not self.snapshots:
            return {}

        def _mean(key: str) -> float:
            vals = [getattr(s, key, 0.0) or 0.0 for s in self.snapshots]
            return sum(vals) / len(vals)

        def _sum(key: str) -> float:
            return sum(getattr(s, key, 0.0) or 0.0 for s in self.snapshots)

        def _last(key: str) -> float:
            return getattr(self.snapshots[-1], key, 0.0) or 0.0

        s = self.snapshots
        return {
            "cycles": self.n_cycles,
            "duration_seconds": s[-1].timestamp - s[0].timestamp if self.n_cycles >= 2 else 0.0,
            "perception": {
                "avg_estimation_error": round(_mean("state_estimation_error"), 4),
                "avg_surprise_rate": round(_mean("surprise_rate"), 4),
                "avg_forecast_accuracy": round(_mean("forecast_accuracy"), 4),
                "avg_counterfactual_accuracy": round(_mean("counterfactual_accuracy"), 4),
                "avg_score": round(_mean("perception_score"), 4),
            },
            "learning": {
                "avg_curiosity": round(_mean("curiosity_level"), 4),
                "avg_learning_rate": round(_mean("learning_rate"), 4),
                "avg_compression": round(_mean("compression_rate"), 4),
                "avg_exploration": round(_mean("exploration_ratio"), 4),
                "latest_yield_observations": _last("knowledge_yield_observations"),
                "latest_yield_theories": _last("knowledge_yield_theories"),
                "latest_yield_validated": _last("knowledge_yield_validated"),
                "avg_score": round(_mean("learning_score"), 4),
            },
            "identity": {
                "avg_entropy": round(_mean("identity_entropy"), 4),
                "avg_continuity": round(_mean("identity_continuity"), 4),
                "avg_coherence": round(_mean("relational_coherence"), 4),
                "avg_mission_alignment": round(_mean("mission_alignment"), 4),
                "avg_project_alignment": round(_mean("project_alignment"), 4),
                "avg_decision_alignment": round(_mean("decision_alignment"), 4),
                "avg_score": round(_mean("identity_score"), 4),
            },
            "knowledge": {
                "avg_representation_diversity": round(_mean("representation_diversity"), 4),
                "avg_bridge_density": round(_mean("bridge_density"), 4),
                "avg_reuse_rate": round(_mean("reuse_rate"), 4),
                "latest_epistemic_ideas": _last("epistemic_ideas"),
                "latest_theory_nodes": _last("theory_nodes"),
                "avg_bridge_potential": round(_mean("bridge_potential_avg"), 4),
                "avg_score": round(_mean("knowledge_score"), 4),
            },
            "resources": {
                "avg_compute_util": round(_mean("compute_utilization"), 4),
                "avg_memory_util": round(_mean("memory_utilization"), 4),
                "avg_croi": round(_mean("croi"), 4),
                "avg_score": round(_mean("resource_score"), 4),
            },
            "projects": {
                "avg_completion_rate": round(_mean("project_completion_rate"), 4),
                "avg_abandonment_rate": round(_mean("abandonment_rate"), 4),
                "avg_mission_alignment": round(_mean("mission_alignment_overall"), 4),
                "avg_score": round(_mean("project_score"), 4),
            },
            "social": {
                "latest_niches": _last("niche_count"),
                "avg_exhaustion_rate": round(_mean("exhaustion_rate"), 4),
                "latest_bridges": _last("bridge_count"),
                "avg_collaboration": round(_mean("collaboration_efficiency"), 4),
                "avg_score": round(_mean("social_score"), 4),
            },
            "system_score": {
                "avg": round(_mean("system_score"), 4),
                "min": round(min(s.system_score for s in self.snapshots), 4),
                "max": round(max(s.system_score for s in self.snapshots), 4),
                "trend": classify_trend([s.system_score for s in self.snapshots]).value,
            },
            "mission_score": {
                "avg": round(_mean("mission_score"), 4),
                "trend": classify_trend([s.mission_score for s in self.snapshots]).value,
            },
        }


# ═══════════════════════════════════════════════════════════════════
# Baseline Comparison
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BaselineComparison:
    """Compares current metrics against a saved baseline."""
    baseline_label: str
    baseline_time: str
    deltas: Dict[str, float] = field(default_factory=dict)
    regressions: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_label": self.baseline_label,
            "baseline_time": self.baseline_time,
            "deltas": self.deltas,
            "regressions": self.regressions,
            "improvements": self.improvements,
        }


# ═══════════════════════════════════════════════════════════════════
# Benchmark Report
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BenchmarkReport:
    """Full benchmark report — on-demand or scheduled.

    Contains:
      - Session summary (all cycles so far)
      - Per-epoch aggregates (default: last 10, last 50, all)
      - Trend analysis per metric
      - Baseline comparison
      - 4-level hierarchical scores
    """
    session_id: str
    generated_at: str
    cycle_count: int
    total_duration_seconds: float

    epochs: Dict[str, EpochSummary] = field(default_factory=dict)
    trends: Dict[str, str] = field(default_factory=dict)
    baseline: Optional[BaselineComparison] = None

    current_system_score: float = 0.0
    current_mission_score: float = 0.0
    system_score_trend: str = "insufficient_data"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "session_id": self.session_id,
            "generated_at": self.generated_at,
            "cycle_count": self.cycle_count,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "system_score": {
                "current": round(self.current_system_score, 4),
                "trend": self.system_score_trend,
            },
            "mission_score": round(self.current_mission_score, 4),
            "trends": self.trends,
            "epochs": {
                label: summary.aggregate()
                for label, summary in self.epochs.items()
            },
        }
        if self.baseline:
            result["baseline"] = self.baseline.to_dict()
        return result

    def to_markdown(self) -> str:
        """Render a human-readable markdown report."""
        lines = [
            f"# TELOS Benchmark Report — Hidden Cognitive State X(t)",
            f"**Session:** `{self.session_id}`",
            f"**Generated:** {self.generated_at}",
            f"**Cycles:** {self.cycle_count} | **Duration:** {self.total_duration_seconds:.1f}s",
            "",
            "---",
            "",
            "## Hierarchical Scores",
            "",
            f"**System Score:** {self.current_system_score:.4f} — trend: **{self.system_score_trend}**",
            f"**Mission Score:** {self.current_mission_score:.4f}",
            "",
            "| Metric | Current | Trend |",
            "|--------|---------|-------|",
        ]

        for key, trend in sorted(self.trends.items()):
            lines.append(f"| {key} | — | {trend} |")

        if self.baseline:
            lines.extend([
                "",
                "## Baseline Comparison",
                "",
                f"**Baseline:** `{self.baseline.baseline_label}` ({self.baseline.baseline_time})",
                "",
                "| Metric | Delta |",
                "|--------|-------|",
            ])
            for metric, delta in self.baseline.deltas.items():
                emoji = "🟢" if delta > 0 else "🔴" if delta < 0 else "⚪"
                lines.append(f"| {metric} | {emoji} {delta:+.4f} |")

            if self.baseline.improvements:
                lines.extend(["", "**Improvements:**"] + [
                    f"  - ✅ {m}" for m in self.baseline.improvements
                ])
            if self.baseline.regressions:
                lines.extend(["", "**Regressions:**"] + [
                    f"  - ⚠️ {m}" for m in self.baseline.regressions
                ])

        for label, summary in self.epochs.items():
            agg = summary.aggregate()
            if not agg:
                continue
            lines.extend([
                "",
                f"## Epoch: {label} ({summary.n_cycles} cycles)",
                "",
                "### 1. Perception",
                f"- Est. Error: {agg['perception']['avg_estimation_error']}",
                f"- Surprise: {agg['perception']['avg_surprise_rate']:.3f}",
                f"- Forecast Acc: {agg['perception']['avg_forecast_accuracy']:.3f}",
                f"- Counterfactual Acc: {agg['perception']['avg_counterfactual_accuracy']:.3f}",
                f"- **Subsystem Score:** {agg['perception']['avg_score']}",
                "",
                "### 2. Learning",
                f"- Curiosity: {agg['learning']['avg_curiosity']}",
                f"- Learning Rate: {agg['learning']['avg_learning_rate']}",
                f"- Compression: {agg['learning']['avg_compression']}",
                f"- Exploration: {agg['learning']['avg_exploration']:.1%}",
                f"- Yield Pipeline: Obs={agg['learning']['latest_yield_observations']} "
                f"Th={agg['learning']['latest_yield_theories']} "
                f"Val={agg['learning']['latest_yield_validated']}",
                f"- **Subsystem Score:** {agg['learning']['avg_score']}",
                "",
                "### 3. Identity",
                f"- Entropy: {agg['identity']['avg_entropy']}",
                f"- Continuity: {agg['identity']['avg_continuity']}",
                f"- Coherence: {agg['identity']['avg_coherence']}",
                f"- Propagation: Mission={agg['identity']['avg_mission_alignment']} "
                f"Project={agg['identity']['avg_project_alignment']} "
                f"Decision={agg['identity']['avg_decision_alignment']}",
                f"- **Subsystem Score:** {agg['identity']['avg_score']}",
                "",
                "### 4. Knowledge",
                f"- Rep Diversity: {agg['knowledge']['avg_representation_diversity']}",
                f"- Bridge Density: {agg['knowledge']['avg_bridge_density']}",
                f"- Reuse Rate: {agg['knowledge']['avg_reuse_rate']:.1%}",
                f"- Epistemic Ideas: {agg['knowledge']['latest_epistemic_ideas']}",
                f"- Theories: {agg['knowledge']['latest_theory_nodes']}",
                f"- Bridge Potential: {agg['knowledge']['avg_bridge_potential']}",
                f"- **Subsystem Score:** {agg['knowledge']['avg_score']}",
                "",
                "### 5. Resources",
                f"- Compute: {agg['resources']['avg_compute_util']:.1%}",
                f"- Memory: {agg['resources']['avg_memory_util']:.1%}",
                f"- CROI: {agg['resources']['avg_croi']}",
                f"- **Subsystem Score:** {agg['resources']['avg_score']}",
                "",
                "### 6. Projects",
                f"- Completion Rate: {agg['projects']['avg_completion_rate']:.1%}",
                f"- Abandonment Rate: {agg['projects']['avg_abandonment_rate']:.1%}",
                f"- Mission Alignment: {agg['projects']['avg_mission_alignment']:.3f}",
                f"- **Subsystem Score:** {agg['projects']['avg_score']}",
                "",
                "### 7. Social",
                f"- Niches: {agg['social']['latest_niches']}",
                f"- Exhaustion Rate: {agg['social']['avg_exhaustion_rate']:.1%}",
                f"- Bridges: {agg['social']['latest_bridges']}",
                f"- Collaboration: {agg['social']['avg_collaboration']:.3f}",
                f"- **Subsystem Score:** {agg['social']['avg_score']}",
                "",
                "### System Score (Level 3)",
                f"- Avg: {agg['system_score']['avg']} | Min: {agg['system_score']['min']} "
                f"| Max: {agg['system_score']['max']}",
                f"- Trend: {agg['system_score']['trend']}",
                "",
                "### Mission Score (Level 4)",
                f"- Avg: {agg['mission_score']['avg']} | Trend: {agg['mission_score']['trend']}",
            ])

        lines.append("")
        lines.append("---")
        lines.append("*Projections of hidden cognitive state X — generated by TELOS BenchmarkCollector*")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Baseline Persistence
# ═══════════════════════════════════════════════════════════════════

def save_baseline(report: BenchmarkReport, path: str) -> None:
    """Save a benchmark report as a baseline for future comparison."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, 'w') as f:
        json.dump({
            "session_id": report.session_id,
            "generated_at": report.generated_at,
            "cycle_count": report.cycle_count,
            "system_score": report.current_system_score,
            "mission_score": report.current_mission_score,
            "epoch_aggregates": {
                label: summary.aggregate()
                for label, summary in report.epochs.items()
            },
            "trends": report.trends,
        }, f, indent=2, default=str)
    logger.info(f"Baseline saved to {path}")


def load_baseline(path: str) -> Optional[Dict]:
    """Load a saved baseline for comparison."""
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════
# Main Collector Class
# ═══════════════════════════════════════════════════════════════════

class BenchmarkCollector:
    """Collects, stores, and reports benchmark metrics every cycle.

    Each call to collect() takes a projection of the hidden cognitive
    state X(t) and records it as a BenchmarkSnapshot. The snapshot is
    organized along 7 conserved cognitive process axes, then aggregated
    through a 4-level hierarchy: Metrics → Subsystem → System → Mission.

    Usage:
        collector = BenchmarkCollector()

        # In pipeline_finalize.py, after axiom verification:
        collector.collect(pipeline, trace, ctx)

        # On demand:
        report = collector.get_report()
        print(report.to_markdown())

        # Save baseline:
        collector.save_baseline("/tmp/telos_baseline.json")
    """

    def __init__(self, output_dir: str = "telos/benchmarks/data",
                 max_snapshots: int = 5000):
        self.output_dir = output_dir
        self._snapshots: List[BenchmarkSnapshot] = []
        self._max_snapshots = max_snapshots
        self._session_start = time.time()
        self._session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self._baseline_path: Optional[str] = None
        os.makedirs(output_dir, exist_ok=True)

    # ── Collection ──────────────────────────────────────────────

    def collect(self, pipeline: Any, trace: Any, ctx: Any) -> BenchmarkSnapshot:
        """Collect a full benchmark snapshot from the pipeline state.

        Called from pipeline_finalize.py once per cycle.
        `pipeline` is the TelosV14Pipeline instance.
        `trace` is the DecisionTrace for this cycle.
        `ctx` is the PipelineContext.
        """
        snapshot = self._build_snapshot(pipeline, trace, ctx)
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]
        self._auto_persist()
        return snapshot

    def _build_snapshot(self, pipeline: Any, trace: Any, ctx: Any) -> BenchmarkSnapshot:
        """Extract all metrics from pipeline subsystems — projections of X(t)."""
        cycle = getattr(ctx, 'cycle_count', 0)

        # ═══════════════════════════════════════════════════════════
        # 1. Perception — prediction health, uncertainty, surprise
        # ═══════════════════════════════════════════════════════════

        # Prediction/estimation error from trace
        state_estimation_error = getattr(trace, 'prediction_error', 0.0) or 0.0
        # Try curiosity drive for prediction error as well
        cd = getattr(pipeline, '_curiosity_drive', None)
        if cd is not None:
            cd_report = cd.get_report() if hasattr(cd, 'get_report') else {}
            cd_pred_error = cd_report.get('prediction_error', None)
            if cd_pred_error is not None:
                state_estimation_error = cd_pred_error

        # Surprise rate from unknown unknown detector
        uud = getattr(pipeline, '_unknown_unknown_detector', None)
        if uud is not None and hasattr(uud, 'surprise_rate'):
            surprise_rate = uud.surprise_rate
        else:
            surprise_rate = 0.0

        uu_discovery = 0.0
        if uud is not None:
            if hasattr(uud, 'discovery_rate'):
                uu_discovery = uud.discovery_rate
            elif hasattr(uud, 'n_unknown_unknowns'):
                uu_discovery = min(uud.n_unknown_unknowns / max(cycle, 1), 1.0)

        # Forecast accuracy from model competition
        mc = getattr(pipeline, '_model_competition', None)
        if mc is not None and hasattr(mc, 'dominant_model'):
            dm = getattr(mc, 'dominant_model', None)
            if dm is not None and hasattr(dm, 'accuracy'):
                forecast_accuracy = dm.accuracy
            else:
                forecast_accuracy = getattr(mc, 'ensemble_accuracy', 0.5)
        else:
            forecast_accuracy = 0.5

        # Counterfactual accuracy from simulation engine
        sim = getattr(pipeline, '_simulator', None)
        if sim is not None and hasattr(sim, 'counterfactual_accuracy'):
            counterfactual_accuracy = sim.counterfactual_accuracy
        else:
            counterfactual_accuracy = 0.5

        # ═══════════════════════════════════════════════════════════
        # 2. Learning — curiosity, compression, knowledge yield
        # ═══════════════════════════════════════════════════════════

        curiosity_report = getattr(trace, 'curiosity_state', None) or {}
        if not curiosity_report and cd is not None:
            curiosity_report = cd.get_report() if hasattr(cd, 'get_report') else {}
        curiosity_level = curiosity_report.get('curiosity_level', 0.5)
        learning_rate = curiosity_report.get('learning_rate', 0.0)
        boredom_count = curiosity_report.get('boredom_count', 0)

        ic = getattr(pipeline, '_identity_compression', None)
        compression_rate = ic.overall_compression_rate if ic and hasattr(ic, 'overall_compression_rate') else 0.5

        exploration_cycles = curiosity_report.get('exploration_cycles', 0)
        exploitation_cycles = curiosity_report.get('exploitation_cycles', 0)
        total_ce = exploration_cycles + exploitation_cycles
        exploration_ratio = exploration_cycles / max(total_ce, 1)

        # Knowledge Yield Pipeline
        tb = getattr(pipeline, '_theory_builder', None)
        if tb is not None:
            ky_observations = getattr(tb, 'total_experiences', 0)
            ky_theories = len(getattr(tb, '_theories', {}))
            ky_predictions = getattr(tb, 'total_predictions', 0)
            ky_validated = getattr(tb, 'validated_predictions', 0)
            ky_principles = getattr(tb, 'general_principles', 0)
        else:
            ky_observations = ky_theories = ky_predictions = ky_validated = ky_principles = 0

        # ═══════════════════════════════════════════════════════════
        # 3. Identity — coherence, continuity, propagation
        # ═══════════════════════════════════════════════════════════

        ie = getattr(pipeline, '_identity_entropy', None)
        identity_entropy = 0.0
        if ie is not None:
            if hasattr(ie, 'current_entropy'):
                identity_entropy = ie.current_entropy
            elif hasattr(ie, 'entropy'):
                identity_entropy = ie.entropy

        identity_state = getattr(trace, 'identity_state', None) or {}
        identity_continuity = identity_state.get('continuity', 0.5) if isinstance(identity_state, dict) else 0.5
        relational_coherence = getattr(trace, 'relational_coherence', 1.0) or 1.0

        # Identity Propagation
        mission_alignment = getattr(trace, 'mission_alignment', 0.5) or 0.5
        project_alignment = getattr(trace, 'project_alignment', 0.5) or 0.5
        decision_alignment = getattr(trace, 'decision_alignment', 0.5) or 0.5

        # ═══════════════════════════════════════════════════════════
        # 4. Knowledge — representation ecology, epistemic capital
        # ═══════════════════════════════════════════════════════════

        eco = getattr(pipeline, '_ecosystem', None)
        if eco is not None:
            eco_dict = eco.to_dict() if hasattr(eco, 'to_dict') else {}
            rep_age = eco_dict.get('mean_representation_age', 0.0)
            rep_diversity = eco_dict.get('representation_diversity', 0.0)
            retirement_rate = eco_dict.get('retirement_rate', 0.0)
            bridge_density = eco_dict.get('bridge_density', 0.0)
            reuse_rate = eco_dict.get('reuse_rate', 0.0)
            compression_achieved = eco_dict.get('compression_achieved', compression_rate)
            bridge_potential = eco_dict.get('bridge_potential_avg', 0.0)
        else:
            rep_age = rep_diversity = retirement_rate = 0.0
            bridge_density = reuse_rate = 0.0
            compression_achieved = compression_rate
            bridge_potential = 0.0

        # Epistemic Capital (renamed from Belief Capital)
        bcm = getattr(pipeline, '_belief_capital', None)
        if bcm is not None:
            bc_dict = bcm.to_dict() if hasattr(bcm, 'to_dict') else {}
            ep_ideas = bc_dict.get('total_ideas', 0)
            top_ideas = bc_dict.get('top_ideas', [])
            ep_top_capital = top_ideas[0]['capital'] if top_ideas else 0.0
        else:
            ep_ideas = 0
            ep_top_capital = 0.0

        # Theory genealogy
        tg = getattr(pipeline, '_theory_genealogy', None)
        if tg is not None:
            tg_dict = tg.to_dict() if hasattr(tg, 'to_dict') else {}
            tg_nodes = tg_dict.get('total_nodes', 0)
            tg_roots = tg_dict.get('roots', 0)
        else:
            tg_nodes = 0
            tg_roots = 0

        # ═══════════════════════════════════════════════════════════
        # 5. Resources — compute, memory, bandwidth, storage, CROI
        # ═══════════════════════════════════════════════════════════

        ra = getattr(pipeline, '_resource_accounting', None)
        if ra is not None:
            summary = ra.cycle_summary() if hasattr(ra, 'cycle_summary') else {}
            total_compute = summary.get('total_compute_ms', 0.0)
            total_memory = summary.get('total_memory_traces', 0)
            total_bandwidth = summary.get('total_bandwidth_bytes', 0.0)
            total_storage = summary.get('total_storage_entries', 0)
        else:
            total_compute = total_memory = total_bandwidth = total_storage = 0.0

        budget_total = getattr(trace, 'budget_total_ms', 1000.0) or 1000.0
        compute_util = min(total_compute / max(budget_total, 1), 1.0)
        memory_util = min(total_memory / max(100, 1), 1.0)
        bandwidth_util = min(total_bandwidth / max(10000.0, 1), 1.0)
        storage_util = min(total_storage / max(50, 1), 1.0)

        # CROI: Cognitive Return on Investment
        # knowledge gained (yield pipeline) / resource consumed (compute + memory)
        ky_total = ky_observations + ky_theories + ky_predictions + ky_validated + ky_principles
        resource_total = total_compute + total_memory * 10.0  # weight memory traces
        croi = ky_total / max(resource_total, 1.0) * 100.0  # scale for readability

        # ═══════════════════════════════════════════════════════════
        # 6. Projects — completion, strategic alignment hierarchy
        # ═══════════════════════════════════════════════════════════

        portfolio = getattr(pipeline, '_project_portfolio', None)
        if portfolio is not None:
            projects = getattr(portfolio, 'projects', {}) or {}
            total_projects = len(projects)
            active_projects = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('active', 'birth', 'stalled'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value')
                    and p.lifecycle.value in ('active', 'birth', 'stalled'))
            )
            completed = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('completed', 'done'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value')
                    and p.lifecycle.value in ('completed', 'done'))
            )
            abandoned = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('terminated', 'archived'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value')
                    and p.lifecycle.value in ('terminated', 'archived'))
            )
        else:
            total_projects = active_projects = completed = abandoned = 0

        # Strategic alignment hierarchy
        sc = getattr(pipeline, '_strategic_coherence', None)
        if sc is not None and hasattr(sc, '_history') and sc._history:
            last_sc = sc._history[-1]
            if isinstance(last_sc, dict):
                sc_mp = last_sc.get('mission_projects', 0.5)
                sc_pt = last_sc.get('project_tasks', 0.5)
                sc_ta = last_sc.get('task_actions', 0.5)
                sc_overall = last_sc.get('overall', 0.5)
            else:
                sc_mp = sc_pt = sc_ta = sc_overall = 0.5
        else:
            sc_mp = sc_pt = sc_ta = sc_overall = 0.5

        # ═══════════════════════════════════════════════════════════
        # 7. Social — ecosystem niches, bridges, collaboration
        # ═══════════════════════════════════════════════════════════

        if eco is not None:
            eco_dict = eco.to_dict() if hasattr(eco, 'to_dict') else {}
            niche_count = eco_dict.get('niche_count', 0)
            exhausted_niches = eco_dict.get('exhausted', 0)
            bridge_count = eco_dict.get('bridges', 0)
            social_relations = eco_dict.get('relations', 0)
            collab_eff = eco_dict.get('collaboration_efficiency', 0.5)
        else:
            niche_count = exhausted_niches = bridge_count = social_relations = 0
            collab_eff = 0.5

        # ═══════════════════════════════════════════════════════════
        # Build Snapshot
        # ═══════════════════════════════════════════════════════════

        snap = BenchmarkSnapshot(
            cycle=cycle,
            timestamp=time.time(),
            # 1. Perception
            state_estimation_error=state_estimation_error,
            surprise_rate=surprise_rate,
            unknown_unknown_discovery_rate=uu_discovery,
            forecast_accuracy=forecast_accuracy,
            counterfactual_accuracy=counterfactual_accuracy,
            # 2. Learning
            curiosity_level=curiosity_level,
            learning_rate=learning_rate,
            compression_rate=compression_rate,
            boredom_count=boredom_count,
            exploration_ratio=exploration_ratio,
            knowledge_yield_observations=ky_observations,
            knowledge_yield_theories=ky_theories,
            knowledge_yield_predictions=ky_predictions,
            knowledge_yield_validated=ky_validated,
            knowledge_yield_principles=ky_principles,
            # 3. Identity
            identity_entropy=identity_entropy,
            identity_continuity=identity_continuity,
            relational_coherence=relational_coherence,
            mission_alignment=mission_alignment,
            project_alignment=project_alignment,
            decision_alignment=decision_alignment,
            # 4. Knowledge
            representation_age_mean=rep_age,
            representation_diversity=rep_diversity,
            retirement_rate=retirement_rate,
            bridge_density=bridge_density,
            reuse_rate=reuse_rate,
            compression_achieved=compression_achieved,
            epistemic_ideas=ep_ideas,
            epistemic_top_capital=ep_top_capital,
            theory_nodes=tg_nodes,
            theory_roots=tg_roots,
            bridge_potential_avg=bridge_potential,
            # 5. Resources
            compute_utilization=compute_util,
            memory_utilization=memory_util,
            bandwidth_utilization=bandwidth_util,
            storage_utilization=storage_util,
            croi=croi,
            # 6. Projects
            active_projects=active_projects,
            total_projects=total_projects,
            completed_projects=completed,
            abandoned_projects=abandoned,
            strategic_alignment_mission_projects=sc_mp,
            strategic_alignment_project_tasks=sc_pt,
            strategic_alignment_task_actions=sc_ta,
            mission_alignment_overall=sc_overall,
            # 7. Social
            niche_count=niche_count,
            exhausted_niches=exhausted_niches,
            bridge_count=bridge_count,
            social_relations=social_relations,
            collaboration_efficiency=collab_eff,
            # Composite scores (computed below)
        )

        # ── Compute 4-level hierarchy ──
        subscores = compute_subsystem_scores(snap)
        snap.perception_score = subscores["perception"]
        snap.learning_score = subscores["learning"]
        snap.identity_score = subscores["identity"]
        snap.knowledge_score = subscores["knowledge"]
        snap.resource_score = subscores["resources"]
        snap.project_score = subscores["projects"]
        snap.social_score = subscores["social"]

        snap.system_score = compute_system_score(subscores)

        # Mission context — extract from pipeline if available
        mission_ctx = None
        mission_mgr = getattr(pipeline, '_mission_manager', None)
        if mission_mgr is not None and hasattr(mission_mgr, 'get_context_weights'):
            mission_ctx = mission_mgr.get_context_weights()
        snap.mission_score = compute_mission_score(snap.system_score, subscores, mission_ctx)

        return snap

    # ── Report Generation ───────────────────────────────────────

    def get_report(self, baseline_path: Optional[str] = None) -> BenchmarkReport:
        """Generate a complete benchmark report on demand."""
        snapshots = self._snapshots
        now = datetime.now().isoformat()

        # Build epochs: last 10, last 50, all
        epochs = {}
        if len(snapshots) >= 10:
            epochs["last_10"] = EpochSummary(
                cycle_start=snapshots[-10].cycle,
                cycle_end=snapshots[-1].cycle,
                snapshots=snapshots[-10:],
            )
        if len(snapshots) >= 50:
            epochs["last_50"] = EpochSummary(
                cycle_start=snapshots[-50].cycle,
                cycle_end=snapshots[-1].cycle,
                snapshots=snapshots[-50:],
            )
        epochs["all"] = EpochSummary(
            cycle_start=snapshots[0].cycle if snapshots else 0,
            cycle_end=snapshots[-1].cycle if snapshots else 0,
            snapshots=list(snapshots),
        )

        # Compute trends per key metric
        trend_keys = [
            ("perception_score", "Perception Score"),
            ("learning_score", "Learning Score"),
            ("identity_score", "Identity Score"),
            ("knowledge_score", "Knowledge Score"),
            ("resource_score", "Resource Score"),
            ("project_score", "Project Score"),
            ("social_score", "Social Score"),
            ("system_score", "System Score"),
            ("mission_score", "Mission Score"),
            ("curiosity_level", "Curiosity"),
            ("learning_rate", "Learning Rate"),
            ("identity_entropy", "Identity Entropy"),
            ("forecast_accuracy", "Forecast Accuracy"),
            ("croi", "CROI"),
        ]
        trends = {}
        if snapshots:
            for attr, label in trend_keys:
                vals = [getattr(s, attr, 0.0) or 0.0 for s in snapshots]
                trends[label] = classify_trend(vals).value

        # Current scores
        current_ss = snapshots[-1].system_score if snapshots else 0.0
        current_ms = snapshots[-1].mission_score if snapshots else 0.0
        ss_trend = classify_trend(
            [s.system_score for s in snapshots]
        ).value if snapshots else "insufficient_data"

        # Baseline comparison
        baseline_cmp = None
        if baseline_path:
            baseline_cmp = self._compare_baseline(baseline_path)

        report = BenchmarkReport(
            session_id=self._session_id,
            generated_at=now,
            cycle_count=len(snapshots),
            total_duration_seconds=time.time() - self._session_start,
            epochs=epochs,
            trends=trends,
            baseline=baseline_cmp,
            current_system_score=current_ss,
            current_mission_score=current_ms,
            system_score_trend=ss_trend,
        )
        return report

    def _compare_baseline(self, baseline_path: str) -> Optional[BaselineComparison]:
        """Compare current session metrics against a saved baseline."""
        baseline = load_baseline(baseline_path)
        if baseline is None or not self._snapshots:
            return None

        current = self._snapshots[-1]
        baseline_agg = baseline.get("epoch_aggregates", {}).get("all", {})
        if not baseline_agg:
            return None

        # Compare key indicators across the new structure
        delta_keys = [
            ("perception_score", "perception", "avg_score"),
            ("learning_score", "learning", "avg_score"),
            ("identity_score", "identity", "avg_score"),
            ("knowledge_score", "knowledge", "avg_score"),
            ("resource_score", "resources", "avg_score"),
            ("project_score", "projects", "avg_score"),
            ("social_score", "social", "avg_score"),
            ("system_score", "system_score", "avg"),
            ("curiosity_level", "learning", "avg_curiosity"),
            ("learning_rate", "learning", "avg_learning_rate"),
            ("identity_entropy", "identity", "avg_entropy"),
            ("forecast_accuracy", "perception", "avg_forecast_accuracy"),
            ("croi", "resources", "avg_croi"),
        ]

        deltas = {}
        improvements = []
        regressions = []

        for metric_name, category, key in delta_keys:
            cur_val = getattr(current, metric_name, 0.0) or 0.0
            base_val = baseline_agg.get(category, {}).get(key, None)
            if base_val is not None and base_val != 0:
                delta = cur_val - base_val
                deltas[metric_name] = round(delta, 4)
                # Inversion: for identity_entropy, down is good
                inversion = metric_name == "identity_entropy"
                if (delta > 0 and not inversion) or (delta < 0 and inversion):
                    improvements.append(metric_name)
                elif delta != 0:
                    regressions.append(metric_name)

        return BaselineComparison(
            baseline_label=baseline.get("session_id", "unknown"),
            baseline_time=baseline.get("generated_at", "unknown"),
            deltas=deltas,
            improvements=improvements,
            regressions=regressions,
        )

    # ── Persistence ─────────────────────────────────────────────

    def save_baseline(self, path: str) -> None:
        """Save current state as baseline for future comparisons."""
        report = self.get_report()
        save_baseline(report, path)
        self._baseline_path = path

    def save_snapshot_data(self, path: Optional[str] = None) -> str:
        """Persist all snapshot data to JSON for offline analysis."""
        path = path or os.path.join(self.output_dir, f"{self._session_id}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "session_id": self._session_id,
            "session_start": self._session_start,
            "total_cycles": len(self._snapshots),
            "snapshots": [s.to_dict() for s in self._snapshots],
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Benchmark snapshots saved to {path} ({len(self._snapshots)} cycles)")
        return path

    def load_snapshot_data(self, path: str) -> int:
        """Load previously saved snapshot data for continued analysis."""
        if not os.path.exists(path):
            logger.warning(f"No snapshot data found at {path}")
            return 0
        with open(path, 'r') as f:
            data = json.load(f)
        loaded = 0
        for sd in data.get("snapshots", []):
            try:
                snapshot = self._dict_to_snapshot(sd)
                if snapshot:
                    self._snapshots.append(snapshot)
                    loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load snapshot: {e}")
                continue
        logger.info(f"Loaded {loaded} snapshots from {path}")
        return loaded

    def _dict_to_snapshot(self, sd: Dict) -> Optional[BenchmarkSnapshot]:
        """Convert a serialized dict back to a BenchmarkSnapshot."""
        try:
            # Navigate the nested dict structure
            perception = sd.get("perception", {})
            learning = sd.get("learning", {})
            identity = sd.get("identity", {})
            knowledge = sd.get("knowledge", {})
            resources = sd.get("resources", {})
            projects = sd.get("projects", {})
            social = sd.get("social", {})
            hierarchy = sd.get("hierarchy", {})

            yield_data = learning.get("knowledge_yield", {})
            eco = knowledge.get("representation_ecology", {})
            epi = knowledge.get("epistemic_capital", {})
            theory = knowledge.get("theory_genealogy", {})
            propagation = identity.get("propagation", {})
            alignment = projects.get("strategic_alignment", {})

            snap = BenchmarkSnapshot(
                cycle=sd["cycle"],
                timestamp=sd["timestamp"],
                # 1. Perception
                state_estimation_error=perception.get("state_estimation_error", 0.0),
                surprise_rate=perception.get("surprise_rate", 0.0),
                unknown_unknown_discovery_rate=perception.get("unknown_unknown_discovery_rate", 0.0),
                forecast_accuracy=perception.get("forecast_accuracy", 0.5),
                counterfactual_accuracy=perception.get("counterfactual_accuracy", 0.5),
                # 2. Learning
                curiosity_level=learning.get("curiosity_level", 0.5),
                learning_rate=learning.get("learning_rate", 0.0),
                compression_rate=learning.get("compression_rate", 0.5),
                boredom_count=learning.get("boredom_count", 0),
                exploration_ratio=learning.get("exploration_ratio", 0.5),
                knowledge_yield_observations=yield_data.get("observations", 0),
                knowledge_yield_theories=yield_data.get("theories", 0),
                knowledge_yield_predictions=yield_data.get("predictions", 0),
                knowledge_yield_validated=yield_data.get("validated", 0),
                knowledge_yield_principles=yield_data.get("principles", 0),
                # 3. Identity
                identity_entropy=identity.get("identity_entropy", 0.0),
                identity_continuity=identity.get("identity_continuity", 0.5),
                relational_coherence=identity.get("relational_coherence", 1.0),
                mission_alignment=propagation.get("mission_alignment", 0.5),
                project_alignment=propagation.get("project_alignment", 0.5),
                decision_alignment=propagation.get("decision_alignment", 0.5),
                # 4. Knowledge
                representation_age_mean=eco.get("mean_age", 0.0),
                representation_diversity=eco.get("diversity", 0.0),
                retirement_rate=eco.get("retirement_rate", 0.0),
                bridge_density=eco.get("bridge_density", 0.0),
                reuse_rate=eco.get("reuse_rate", 0.0),
                compression_achieved=eco.get("compression_achieved", 0.5),
                epistemic_ideas=epi.get("total_ideas", 0),
                epistemic_top_capital=epi.get("top_capital", 0.0),
                theory_nodes=theory.get("nodes", 0),
                theory_roots=theory.get("roots", 0),
                bridge_potential_avg=knowledge.get("bridge_potential_avg", 0.0),
                # 5. Resources
                compute_utilization=resources.get("compute_utilization", 0.5),
                memory_utilization=resources.get("memory_utilization", 0.5),
                bandwidth_utilization=resources.get("bandwidth_utilization", 0.5),
                storage_utilization=resources.get("storage_utilization", 0.5),
                croi=resources.get("croi", 0.0),
                # 6. Projects
                active_projects=projects.get("active_projects", 0),
                total_projects=projects.get("total_projects", 0),
                completed_projects=projects.get("completed_projects", 0),
                abandoned_projects=projects.get("abandoned_projects", 0),
                strategic_alignment_mission_projects=alignment.get("mission_projects", 0.5),
                strategic_alignment_project_tasks=alignment.get("project_tasks", 0.5),
                strategic_alignment_task_actions=alignment.get("task_actions", 0.5),
                mission_alignment_overall=alignment.get("overall", 0.5),
                # 7. Social
                niche_count=social.get("niche_count", 0),
                exhausted_niches=social.get("exhausted_niches", 0),
                bridge_count=social.get("bridge_count", 0),
                social_relations=social.get("relations", 0),
                collaboration_efficiency=social.get("collaboration_efficiency", 0.5),
            )
            # Compute scores
            subscores = compute_subsystem_scores(snap)
            snap.perception_score = subscores["perception"]
            snap.learning_score = subscores["learning"]
            snap.identity_score = subscores["identity"]
            snap.knowledge_score = subscores["knowledge"]
            snap.resource_score = subscores["resources"]
            snap.project_score = subscores["projects"]
            snap.social_score = subscores["social"]
            snap.system_score = compute_system_score(subscores)
            snap.mission_score = compute_mission_score(snap.system_score, subscores, None)
            return snap
        except Exception as e:
            logger.warning(f"Failed to reconstruct snapshot: {e}")
            return None

    def _auto_persist(self) -> None:
        """Auto-save to disk every 100 cycles."""
        if len(self._snapshots) > 0 and len(self._snapshots) % 100 == 0:
            self.save_snapshot_data()

    # ── Utility ─────────────────────────────────────────────────

    def clear(self) -> None:
        self._snapshots.clear()
        self._session_start = time.time()

    @property
    def cycle_count(self) -> int:
        return len(self._snapshots)

    def latest_snapshot(self) -> Optional[BenchmarkSnapshot]:
        return self._snapshots[-1] if self._snapshots else None


# ═══════════════════════════════════════════════════════════════════
# Backward Compatibility
# ═══════════════════════════════════════════════════════════════════

def compute_health_score(snapshot: BenchmarkSnapshot) -> float:
    """Legacy alias — delegates to system_score (Level 3).

    Previously computed a weighted harmonic mean; now returns the
    hierarchical system_score for backward API compatibility.
    """
    return snapshot.system_score
