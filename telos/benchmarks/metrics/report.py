from __future__ import annotations
import math
import statistics
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from telos.benchmarks.metrics import BenchmarkSnapshot, classify_trend

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
