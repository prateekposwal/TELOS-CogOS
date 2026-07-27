"""
BenchmarkCollector — Comprehensive TELOS Performance Measurement Framework.

Measures 15+ metrics across 7 categories, collects per-cycle time-series data,
and produces session/epoch-level BenchmarkReports.

Designed to answer: "How is TELOS doing?"

Wired into pipeline_finalize.py: runs every cycle after axiom verification.

Categories:
  1. Pipeline Health     — DI, MD, cycle time, phase failures
  2. Cognitive Performance — curiosity, learning rate, compression
  3. Identity Health     — entropy, continuity, narrative coherence
  4. Ecosystem Health    — niche diversity, exhaustion, bridge formation
  5. Resource Efficiency  — compute, memory, bandwidth, storage utilization
  6. Research Productivity — discovery rate, debt, belief capital, genealogy
  7. Strategic Coherence  — project completion, abandonment rate
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


# ── Trend Analysis ────────────────────────────────────────────────────────────

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


# ── Snapshot Data Containers ──────────────────────────────────────────────────

@dataclass
class BenchmarkSnapshot:
    """Immutable per-cycle snapshot of all benchmark metrics."""
    cycle: int
    timestamp: float

    # 1. Pipeline Health
    decision_integrity: float
    mission_drift: float
    cycle_duration_ms: float
    council_blocked: bool
    axiom_pass_rate: float
    phases_completed: int
    phases_total: int

    # 2. Cognitive Performance
    curiosity_level: float
    learning_rate: float
    compression_rate: float
    boredom_count: int
    exploration_ratio: float

    # 3. Identity Health
    identity_entropy: float
    relational_coherence: float
    identity_continuity: float

    # 4. Ecosystem Health
    niche_count: int
    exhausted_niches: int
    bridge_count: int
    ecosystem_relations: int

    # 5. Resource Efficiency
    compute_utilization: float       # 0-1
    memory_utilization: float        # 0-1
    bandwidth_utilization: float     # 0-1
    storage_utilization: float       # 0-1

    # 6. Research Productivity
    discovery_marginal_rate: float
    research_debt: float
    debt_entries_open: int
    belief_capital_ideas: int
    belief_top_capital: float
    theory_nodes: int
    theory_roots: int

    # 7. Strategic Coherence
    active_projects: int
    total_projects: int
    terminated_projects: int
    strategic_coherence: float
    abandonment_rate: float

    # Composite
    health_score: float = 0.0

    @property
    def exhaustion_rate(self) -> float:
        return self.exhausted_niches / max(self.niche_count, 1)

    @property
    def project_completion_rate(self) -> float:
        """Ratio of non-terminated active projects."""
        return self.active_projects / max(self.total_projects, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "pipeline_health": {
                "decision_integrity": round(self.decision_integrity, 4),
                "mission_drift": round(self.mission_drift, 4),
                "cycle_duration_ms": round(self.cycle_duration_ms, 2),
                "council_blocked": self.council_blocked,
                "axiom_pass_rate": round(self.axiom_pass_rate, 4),
                "phases_completed": self.phases_completed,
                "phases_total": self.phases_total,
            },
            "cognitive_performance": {
                "curiosity_level": round(self.curiosity_level, 4),
                "learning_rate": round(self.learning_rate, 4),
                "compression_rate": round(self.compression_rate, 4),
                "boredom_count": self.boredom_count,
                "exploration_ratio": round(self.exploration_ratio, 4),
            },
            "identity_health": {
                "identity_entropy": round(self.identity_entropy, 4),
                "relational_coherence": round(self.relational_coherence, 4),
                "identity_continuity": round(self.identity_continuity, 4),
            },
            "ecosystem_health": {
                "niche_count": self.niche_count,
                "exhausted_niches": self.exhausted_niches,
                "exhaustion_rate": round(self.exhaustion_rate, 4),
                "bridge_count": self.bridge_count,
                "relations": self.ecosystem_relations,
            },
            "resource_efficiency": {
                "compute_utilization": round(self.compute_utilization, 4),
                "memory_utilization": round(self.memory_utilization, 4),
                "bandwidth_utilization": round(self.bandwidth_utilization, 4),
                "storage_utilization": round(self.storage_utilization, 4),
            },
            "research_productivity": {
                "discovery_marginal_rate": round(self.discovery_marginal_rate, 4),
                "research_debt": round(self.research_debt, 4),
                "debt_entries_open": self.debt_entries_open,
                "belief_capital_ideas": self.belief_capital_ideas,
                "belief_top_capital": round(self.belief_top_capital, 4),
                "theory_nodes": self.theory_nodes,
                "theory_roots": self.theory_roots,
            },
            "strategic_coherence": {
                "active_projects": self.active_projects,
                "total_projects": self.total_projects,
                "terminated_projects": self.terminated_projects,
                "project_completion_rate": round(self.project_completion_rate, 4),
                "strategic_coherence": round(self.strategic_coherence, 4),
                "abandonment_rate": round(self.abandonment_rate, 4),
            },
            "health_score": round(self.health_score, 4),
        }


# ── Aggregate Reports ─────────────────────────────────────────────────────────

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

        blocked = sum(1 for s in self.snapshots if s.council_blocked)
        axioms_ok = sum(
            1 for s in self.snapshots
            if s.axiom_pass_rate >= 0.95
        )

        return {
            "cycles": self.n_cycles,
            "duration_seconds": self.snapshots[-1].timestamp - self.snapshots[0].timestamp if self.n_cycles >= 2 else 0.0,
            "pipeline_health": {
                "avg_di": round(_mean("decision_integrity"), 4),
                "avg_md": round(_mean("mission_drift"), 4),
                "avg_cycle_ms": round(_mean("cycle_duration_ms"), 2),
                "blocked_cycles": blocked,
                "block_rate": round(blocked / max(self.n_cycles, 1), 4),
                "axiom_compliance_rate": round(axioms_ok / max(self.n_cycles, 1), 4),
            },
            "cognitive_performance": {
                "avg_curiosity": round(_mean("curiosity_level"), 4),
                "avg_learning_rate": round(_mean("learning_rate"), 4),
                "avg_compression": round(_mean("compression_rate"), 4),
                "avg_exploration_ratio": round(_mean("exploration_ratio"), 4),
            },
            "identity_health": {
                "avg_entropy": round(_mean("identity_entropy"), 4),
                "avg_relational_coherence": round(_mean("relational_coherence"), 4),
                "avg_continuity": round(_mean("identity_continuity"), 4),
            },
            "ecosystem_health": {
                "latest_niches": _last("niche_count"),
                "avg_exhaustion_rate": round(_mean("exhaustion_rate"), 4),
                "latest_bridges": _last("bridge_count"),
            },
            "resource_efficiency": {
                "avg_compute_util": round(_mean("compute_utilization"), 4),
                "avg_memory_util": round(_mean("memory_utilization"), 4),
                "avg_bandwidth_util": round(_mean("bandwidth_utilization"), 4),
                "avg_storage_util": round(_mean("storage_utilization"), 4),
            },
            "research_productivity": {
                "avg_discovery_rate": round(_mean("discovery_marginal_rate"), 4),
                "latest_debt": _last("research_debt"),
                "latest_ideas": _last("belief_capital_ideas"),
                "latest_theory_nodes": _last("theory_nodes"),
            },
            "strategic_coherence": {
                "avg_completion_rate": round(_mean("project_completion_rate"), 4),
                "avg_strategic_coherence": round(_mean("strategic_coherence"), 4),
                "avg_abandonment_rate": round(_mean("abandonment_rate"), 4),
            },
            "health_score": {
                "avg": round(_mean("health_score"), 4),
                "min": round(min(s.health_score for s in self.snapshots), 4),
                "max": round(max(s.health_score for s in self.snapshots), 4),
                "trend": classify_trend([s.health_score for s in self.snapshots]).value,
            },
        }


# ── Health Score Computation ──────────────────────────────────────────────────

def compute_health_score(snapshot: BenchmarkSnapshot) -> float:
    """Composite health score in [0, 1].
    
    Weighted harmonic mean of 7 category scores:
      - Pipeline Health (25%)
      - Cognitive Performance (15%)
      - Identity Health (15%)
      - Ecosystem Health (10%)
      - Resource Efficiency (15%)
      - Research Productivity (10%)
      - Strategic Coherence (10%)
    """
    # Pipeline Health (DI up good, MD down good, not blocked, axioms passing)
    ph = (
        snapshot.decision_integrity * 0.35
        + (1.0 - min(snapshot.mission_drift / 10.0, 1.0)) * 0.25
        + (0.0 if snapshot.council_blocked else 1.0) * 0.25
        + snapshot.axiom_pass_rate * 0.15
    )

    # Cognitive Performance (curiosity + learning + compression)
    cp = (
        snapshot.curiosity_level * 0.3
        + min(snapshot.learning_rate * 5.0, 1.0) * 0.3
        + snapshot.compression_rate * 0.2
        + snapshot.exploration_ratio * 0.2
    )

    # Identity Health (low entropy = good, high coherence = good)
    ih = (
        (1.0 - min(snapshot.identity_entropy * 2.0, 1.0)) * 0.35
        + snapshot.relational_coherence * 0.35
        + snapshot.identity_continuity * 0.3
    )

    # Ecosystem Health (diverse = good, low exhaustion = good, bridges = good)
    eh = (
        min(snapshot.niche_count / 20.0, 1.0) * 0.3
        + (1.0 - snapshot.exhaustion_rate) * 0.4
        + min(snapshot.bridge_count / 5.0, 1.0) * 0.3
    )

    # Resource Efficiency (low utilization = headroom, but not zero)
    re = (
        (1.0 - abs(snapshot.compute_utilization - 0.5) * 2.0) * 0.3
        + (1.0 - abs(snapshot.memory_utilization - 0.5) * 2.0) * 0.3
        + (1.0 - abs(snapshot.bandwidth_utilization - 0.5) * 2.0) * 0.2
        + (1.0 - abs(snapshot.storage_utilization - 0.5) * 2.0) * 0.2
    )

    # Research Productivity (discovering, low debt, high capital)
    rp = (
        min(snapshot.discovery_marginal_rate * 3.0, 1.0) * 0.35
        + (1.0 - min(snapshot.research_debt / 10.0, 1.0)) * 0.25
        + min(snapshot.belief_top_capital * 2.0, 1.0) * 0.25
        + min(snapshot.theory_nodes / 20.0, 1.0) * 0.15
    )

    # Strategic Coherence (high completion, high coherence, low abandonment)
    sc = (
        snapshot.project_completion_rate * 0.3
        + snapshot.strategic_coherence * 0.4
        + (1.0 - snapshot.abandonment_rate) * 0.3
    )

    weights = [0.25, 0.15, 0.15, 0.10, 0.15, 0.10, 0.10]
    scores = [ph, cp, ih, eh, re, rp, sc]
    # Weighted harmonic mean
    denom = sum(w / max(s, 0.001) for w, s in zip(weights, scores))
    return round(sum(weights) / denom, 4)


# ── Baseline Comparison ───────────────────────────────────────────────────────

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


# ── Benchmark Report ──────────────────────────────────────────────────────────

@dataclass
class BenchmarkReport:
    """Full benchmark report — on-demand or scheduled.
    
    Contains:
      - Session summary (all cycles so far)
      - Per-epoch aggregates (default: last 10, last 50, all)
      - Trend analysis per metric
      - Baseline comparison
      - Single composite health score
    """
    session_id: str
    generated_at: str
    cycle_count: int
    total_duration_seconds: float

    epochs: Dict[str, EpochSummary] = field(default_factory=dict)
    trends: Dict[str, str] = field(default_factory=dict)
    baseline: Optional[BaselineComparison] = None

    current_health_score: float = 0.0
    health_score_trend: str = "insufficient_data"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "session_id": self.session_id,
            "generated_at": self.generated_at,
            "cycle_count": self.cycle_count,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "health_score": {
                "current": round(self.current_health_score, 4),
                "trend": self.health_score_trend,
            },
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
            f"# TELOS Benchmark Report",
            f"**Session:** `{self.session_id}`",
            f"**Generated:** {self.generated_at}",
            f"**Cycles:** {self.cycle_count} | **Duration:** {self.total_duration_seconds:.1f}s",
            "",
            "---",
            "",
            "## Health Score",
            "",
            f"**{self.current_health_score:.3f}** — trend: **{self.health_score_trend}**",
            "",
            "| Metric | Current | Trend |",
            "|--------|---------|-------|",
        ]

        def _fmt(key: str, val: Any) -> str:
            if isinstance(val, float):
                return f"{val:.4f}"
            return str(val)

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
                "### Pipeline Health",
                f"- DI: {agg['pipeline_health']['avg_di']} | MD: {agg['pipeline_health']['avg_md']}",
                f"- Block Rate: {agg['pipeline_health']['block_rate']:.1%}",
                f"- Axiom Compliance: {agg['pipeline_health']['axiom_compliance_rate']:.1%}",
                f"- Avg Cycle: {agg['pipeline_health']['avg_cycle_ms']:.1f}ms",
                "",
                "### Cognitive Performance",
                f"- Curiosity: {agg['cognitive_performance']['avg_curiosity']}",
                f"- Learning Rate: {agg['cognitive_performance']['avg_learning_rate']}",
                f"- Compression: {agg['cognitive_performance']['avg_compression']}",
                f"- Exploration: {agg['cognitive_performance']['avg_exploration_ratio']:.1%}",
                "",
                "### Identity Health",
                f"- Entropy: {agg['identity_health']['avg_entropy']}",
                f"- Relational Coherence: {agg['identity_health']['avg_relational_coherence']}",
                f"- Continuity: {agg['identity_health']['avg_continuity']}",
                "",
                "### Ecosystem Health",
                f"- Niches: {agg['ecosystem_health']['latest_niches']}",
                f"- Exhaustion Rate: {agg['ecosystem_health']['avg_exhaustion_rate']:.1%}",
                f"- Bridges: {agg['ecosystem_health']['latest_bridges']}",
                "",
                "### Resource Efficiency",
                f"- Compute: {agg['resource_efficiency']['avg_compute_util']:.1%}",
                f"- Memory: {agg['resource_efficiency']['avg_memory_util']:.1%}",
                f"- Bandwidth: {agg['resource_efficiency']['avg_bandwidth_util']:.1%}",
                f"- Storage: {agg['resource_efficiency']['avg_storage_util']:.1%}",
                "",
                "### Research Productivity",
                f"- Discovery Rate: {agg['research_productivity']['avg_discovery_rate']}",
                f"- Debt: {agg['research_productivity']['latest_debt']}",
                f"- Ideas: {agg['research_productivity']['latest_ideas']}",
                f"- Theories: {agg['research_productivity']['latest_theory_nodes']}",
                "",
                "### Strategic Coherence",
                f"- Completion Rate: {agg['strategic_coherence']['avg_completion_rate']:.1%}",
                f"- Strategic Coherence: {agg['strategic_coherence']['avg_strategic_coherence']}",
                f"- Abandonment Rate: {agg['strategic_coherence']['avg_abandonment_rate']:.1%}",
                "",
                "### Health Score",
                f"- Avg: {agg['health_score']['avg']} | Min: {agg['health_score']['min']} | Max: {agg['health_score']['max']}",
                f"- Trend: {agg['health_score']['trend']}",
            ])

        lines.append("")
        lines.append("---")
        lines.append("*Generated by TELOS BenchmarkCollector*")
        return "\n".join(lines)


# ── Baseline Persistence ──────────────────────────────────────────────────────

def save_baseline(report: BenchmarkReport, path: str) -> None:
    """Save a benchmark report as a baseline for future comparison."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, 'w') as f:
        json.dump({
            "session_id": report.session_id,
            "generated_at": report.generated_at,
            "cycle_count": report.cycle_count,
            "health_score": report.current_health_score,
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


# ── Main Collector Class ─────────────────────────────────────────────────────

class BenchmarkCollector:
    """Collects, stores, and reports benchmark metrics every cycle.
    
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

    # ── Collection ──────────────────────────────────────────────────────────

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
        """Extract all metrics from pipeline subsystems."""
        cycle = getattr(ctx, 'cycle_count', 0)

        # 1. Pipeline Health
        di = getattr(trace, 'decision_integrity', 1.0) or 1.0
        md = getattr(trace, 'mission_drift', 0.0) or 0.0
        duration = getattr(trace, 'cycle_duration_ms', 0.0) or 0.0
        blocked = getattr(ctx, 'council_blocked', False) or getattr(ctx, 'firewall_blocked', False)
        
        # Axiom pass rate
        axiom_results = getattr(trace, 'axiom_results', None) or {}
        total_axioms = len(axiom_results)
        passed_axioms = sum(1 for r in axiom_results.values() if isinstance(r, dict) and r.get("passed", False))
        axiom_pass_rate = passed_axioms / max(total_axioms, 1)

        # Phases
        phases_completed = getattr(ctx, 'phases_completed', 9)
        phases_total = getattr(ctx, 'phases_total', 9)

        # 2. Cognitive Performance
        curiosity_report = getattr(trace, 'curiosity_state', None) or {}
        if not curiosity_report:
            cd = getattr(pipeline, '_curiosity_drive', None)
            if cd is not None:
                curiosity_report = cd.get_report() if hasattr(cd, 'get_report') else {}
        curiosity_level = curiosity_report.get('curiosity_level', 0.5)
        learning_rate = curiosity_report.get('learning_rate', 0.0)
        boredom_count = curiosity_report.get('boredom_count', 0)

        # Compression rate
        ic = getattr(pipeline, '_identity_compression', None)
        compression_rate = ic.overall_compression_rate if ic and hasattr(ic, 'overall_compression_rate') else 0.5
        
        # Exploration ratio
        exploration_cycles = curiosity_report.get('exploration_cycles', 0)
        exploitation_cycles = curiosity_report.get('exploitation_cycles', 0)
        total_ce = exploration_cycles + exploitation_cycles
        exploration_ratio = exploration_cycles / max(total_ce, 1)

        # 3. Identity Health
        ie = getattr(pipeline, '_identity_entropy', None)
        identity_entropy = ie.entropy if ie and hasattr(ie, 'entropy') else 0.0
        if hasattr(ie, 'current_entropy'):
            identity_entropy = ie.current_entropy
        
        relational_coherence = getattr(trace, 'relational_coherence', 1.0) or 1.0
        
        identity_state = getattr(trace, 'identity_state', None) or {}
        identity_continuity = identity_state.get('continuity', 0.5) if isinstance(identity_state, dict) else 0.5

        # 4. Ecosystem Health
        eco = getattr(pipeline, '_ecosystem', None)
        if eco is not None:
            eco_dict = eco.to_dict() if hasattr(eco, 'to_dict') else {}
            niche_count = eco_dict.get('niche_count', 0)
            exhausted_niches = eco_dict.get('exhausted', 0)
            bridge_count = eco_dict.get('bridges', 0)
            eco_relations = eco_dict.get('relations', 0)
        else:
            niche_count = exhausted_niches = bridge_count = eco_relations = 0

        # 5. Resource Efficiency
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

        # 6. Research Productivity
        dr = getattr(pipeline, '_discovery_rate', None)
        if dr is not None:
            disc_dict = dr.to_dict() if hasattr(dr, 'to_dict') else {}
            disc_rate = disc_dict.get('marginal_rate', 0.0)
        else:
            disc_rate = 0.0

        debt = getattr(pipeline, '_research_debt', None)
        if debt is not None:
            debt_dict = debt.to_dict() if hasattr(debt, 'to_dict') else {}
            debt_total = debt_dict.get('total_debt', 0.0)
            debt_open = debt_dict.get('open_entries', 0)
        else:
            debt_total = 0.0
            debt_open = 0

        bcm = getattr(pipeline, '_belief_capital', None)
        if bcm is not None:
            bc_dict = bcm.to_dict() if hasattr(bcm, 'to_dict') else {}
            bc_ideas = bc_dict.get('total_ideas', 0)
            top_ideas = bc_dict.get('top_ideas', [])
            bc_top_capital = top_ideas[0]['capital'] if top_ideas else 0.0
        else:
            bc_ideas = 0
            bc_top_capital = 0.0

        tg = getattr(pipeline, '_theory_genealogy', None)
        if tg is not None:
            tg_dict = tg.to_dict() if hasattr(tg, 'to_dict') else {}
            tg_nodes = tg_dict.get('total_nodes', 0)
            tg_roots = tg_dict.get('roots', 0)
        else:
            tg_nodes = 0
            tg_roots = 0

        # 7. Strategic Coherence
        portfolio = getattr(pipeline, '_project_portfolio', None)
        if portfolio is not None:
            projects = getattr(portfolio, 'projects', {}) or {}
            total_projects = len(projects)
            active_projects = sum(
                1 for p in projects.values()
                if getattr(p, 'lifecycle', None) in ('active', 'birth', 'stalled')
                or (hasattr(p, 'lifecycle') and p.lifecycle.value in ('active', 'birth', 'stalled'))
            )
            terminated = sum(
                1 for p in projects.values()
                if (hasattr(p, 'lifecycle') and p.lifecycle in ('terminated', 'archived'))
                or (hasattr(p, 'lifecycle') and hasattr(p.lifecycle, 'value') and p.lifecycle.value in ('terminated', 'archived'))
            )
        else:
            total_projects = 0
            active_projects = 0
            terminated = 0

        sc = getattr(pipeline, '_strategic_coherence', None)
        strategic_coherence = 0.5
        if sc is not None and hasattr(sc, '_history') and sc._history:
            last_sc = sc._history[-1]
            strategic_coherence = last_sc.get('score', 0.5) if isinstance(last_sc, dict) else 0.5

        abandonment_rate = terminated / max(total_projects, 1)

        # Build snapshot
        snap = BenchmarkSnapshot(
            cycle=cycle,
            timestamp=time.time(),
            decision_integrity=di,
            mission_drift=md,
            cycle_duration_ms=duration,
            council_blocked=blocked,
            axiom_pass_rate=axiom_pass_rate,
            phases_completed=phases_completed,
            phases_total=phases_total,
            curiosity_level=curiosity_level,
            learning_rate=learning_rate,
            compression_rate=compression_rate,
            boredom_count=boredom_count,
            exploration_ratio=exploration_ratio,
            identity_entropy=identity_entropy,
            relational_coherence=relational_coherence,
            identity_continuity=identity_continuity,
            niche_count=niche_count,
            exhausted_niches=exhausted_niches,
            bridge_count=bridge_count,
            ecosystem_relations=eco_relations,
            compute_utilization=compute_util,
            memory_utilization=memory_util,
            bandwidth_utilization=bandwidth_util,
            storage_utilization=storage_util,
            discovery_marginal_rate=disc_rate,
            research_debt=debt_total,
            debt_entries_open=debt_open,
            belief_capital_ideas=bc_ideas,
            belief_top_capital=bc_top_capital,
            theory_nodes=tg_nodes,
            theory_roots=tg_roots,
            active_projects=active_projects,
            total_projects=total_projects,
            terminated_projects=terminated,
            strategic_coherence=strategic_coherence,
            abandonment_rate=abandonment_rate,
            health_score=0.0,  # computed below
        )
        snap.health_score = compute_health_score(snap)
        return snap

    # ── Report Generation ───────────────────────────────────────────────────

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
            ("decision_integrity", "DI"),
            ("mission_drift", "MD"),
            ("curiosity_level", "Curiosity"),
            ("learning_rate", "Learning Rate"),
            ("compression_rate", "Compression"),
            ("identity_entropy", "Identity Entropy"),
            ("relational_coherence", "Relational Coherence"),
            ("discovery_marginal_rate", "Discovery Rate"),
            ("research_debt", "Research Debt"),
            ("strategic_coherence", "Strategic Coherence"),
            ("health_score", "Health Score"),
        ]
        trends = {}
        if snapshots:
            for attr, label in trend_keys:
                vals = [getattr(s, attr, 0.0) or 0.0 for s in snapshots]
                trends[label] = classify_trend(vals).value

        # Current health score
        current_hs = snapshots[-1].health_score if snapshots else 0.0
        hs_trend = classify_trend(
            [s.health_score for s in snapshots]
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
            current_health_score=current_hs,
            health_score_trend=hs_trend,
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

        # Compare key indicators
        delta_keys = [
            ("decision_integrity", "pipeline_health", "avg_di"),
            ("mission_drift", "pipeline_health", "avg_md"),
            ("curiosity_level", "cognitive_performance", "avg_curiosity"),
            ("learning_rate", "cognitive_performance", "avg_learning_rate"),
            ("identity_entropy", "identity_health", "avg_entropy"),
            ("discovery_marginal_rate", "research_productivity", "avg_discovery_rate"),
            ("research_debt", "research_productivity", "latest_debt"),
            ("strategic_coherence", "strategic_coherence", "avg_strategic_coherence"),
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
                # Direction: for most metrics up is good. For mission_drift,
                # identity_entropy, research_debt: down is good.
                inversion = metric_name in ("mission_drift", "identity_entropy", "research_debt")
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

    # ── Persistence ─────────────────────────────────────────────────────────

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
        # Convert dicts back to BenchmarkSnapshot objects
        loaded = 0
        for sd in data.get("snapshots", []):
            # Flatten nested dict back to flat BenchmarkSnapshot attrs
            try:
                flat = {}
                for category in ("pipeline_health", "cognitive_performance", "identity_health",
                                 "ecosystem_health", "resource_efficiency", "research_productivity",
                                 "strategic_coherence"):
                    for k, v in sd.get(category, {}).items():
                        flat[k] = v
                flat["cycle"] = sd["cycle"]
                flat["timestamp"] = sd["timestamp"]
                flat["health_score"] = sd.get("health_score", 0.0)
                # Map flat keys to BenchmarkSnapshot fields
                field_map = {
                    "cycle": "cycle",
                    "timestamp": "timestamp",
                    "health_score": "health_score",
                    "decision_integrity": "decision_integrity",
                    "mission_drift": "mission_drift",
                    "cycle_duration_ms": "cycle_duration_ms",
                    "council_blocked": "council_blocked",
                    "axiom_pass_rate": "axiom_pass_rate",
                    "phases_completed": "phases_completed",
                    "phases_total": "phases_total",
                    "curiosity_level": "curiosity_level",
                    "learning_rate": "learning_rate",
                    "compression_rate": "compression_rate",
                    "boredom_count": "boredom_count",
                    "exploration_ratio": "exploration_ratio",
                    "identity_entropy": "identity_entropy",
                    "relational_coherence": "relational_coherence",
                    "identity_continuity": "identity_continuity",
                    "niche_count": "niche_count",
                    "exhausted_niches": "exhausted_niches",
                    "bridge_count": "bridge_count",
                    "ecosystem_relations": "ecosystem_relations",
                    "compute_utilization": "compute_utilization",
                    "memory_utilization": "memory_utilization",
                    "bandwidth_utilization": "bandwidth_utilization",
                    "storage_utilization": "storage_utilization",
                    "discovery_marginal_rate": "discovery_marginal_rate",
                    "research_debt": "research_debt",
                    "debt_entries_open": "debt_entries_open",
                    "belief_capital_ideas": "belief_capital_ideas",
                    "belief_top_capital": "belief_top_capital",
                    "theory_nodes": "theory_nodes",
                    "theory_roots": "theory_roots",
                    "active_projects": "active_projects",
                    "total_projects": "total_projects",
                    "terminated_projects": "terminated_projects",
                    "strategic_coherence": "strategic_coherence",
                    "abandonment_rate": "abandonment_rate",
                }
                kwargs = {}
                for src_key, dst_key in field_map.items():
                    kwargs[dst_key] = flat.get(src_key, flat.get(dst_key, 0.0))
                # Boolean coercion
                kwargs["council_blocked"] = bool(kwargs.get("council_blocked", False))
                kwargs["health_score"] = flat.get("health_score", 0.0)
                snap = BenchmarkSnapshot(**kwargs)
                self._snapshots.append(snap)
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load snapshot: {e}")
                continue
        logger.info(f"Loaded {loaded} snapshots from {path}")
        return loaded

    def _auto_persist(self) -> None:
        """Auto-save to disk every 100 cycles."""
        if len(self._snapshots) > 0 and len(self._snapshots) % 100 == 0:
            self.save_snapshot_data()

    # ── Utility ─────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._snapshots.clear()
        self._session_start = time.time()

    @property
    def cycle_count(self) -> int:
        return len(self._snapshots)

    def latest_snapshot(self) -> Optional[BenchmarkSnapshot]:
        return self._snapshots[-1] if self._snapshots else None
