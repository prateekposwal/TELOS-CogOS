"""
TelemetryCollector — Records Pipeline metrics over time.

Collects DI, MD, budget, stream hit rates, and council signals
into time-series memory, exposed as JSON for dashboards.
"""

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger('telos_telemetry')


@dataclass
class MetricPoint:
    cycle: int
    timestamp: float
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


class TelemetryCollector:
    """Collects Pipeline metrics as time-series points.

    Stores in-memory with a max window. Exposed as JSON for the
    FastAPI /metrics dashboard.
    """

    def __init__(self, max_points: int = 1000):
        self._points: List[MetricPoint] = []
        self._max_points = max_points
        self._cycle_metrics: Dict[int, Dict] = {}
        self._escape_count: int = 0

    def record(self, name: str, value: float,
               cycle: int = 0,
               tags: Optional[Dict[str, str]] = None) -> None:
        """Record a single metric point.
            Args:
                name: the name/key of the item
                value: the value argument for this call.
                cycle: the current cycle count
                tags: the tags argument for this call.
        """
        point = MetricPoint(
            cycle=cycle,
            timestamp=time.time(),
            name=name,
            value=value,
            tags=tags or {},
        )
        self._points.append(point)
        if len(self._points) > self._max_points:
            self._points = self._points[-self._max_points:]

    def record_cycle(self, cycle: int, trace: Any) -> None:
        """Record all metrics from a DecisionTrace.
            Args:
                cycle: the current cycle count
        """
        if trace is None:
            return

        td = trace.to_dict() if hasattr(trace, 'to_dict') else {}

        self.record("di", td.get("decision_integrity", 0), cycle)
        self.record("md", td.get("mission_drift", 0), cycle)
        self.record("budget_consumed", td.get("budget_consumed_ms", 0), cycle)
        self.record("budget_total", td.get("budget_total_ms", 0), cycle)
        self.record("worlds_simulated", td.get("worlds_simulated", 0), cycle)
        self.record("cycle_duration", td.get("cycle_duration_ms", 0), cycle)
        self.record("health", td.get("health_score", 1.0), cycle)
        self.record("council_validated", 1.0 if td.get("council_validated") else 0.0,
                    cycle)
        self.record("firewall_blocked", 1.0 if td.get("firewall_blocked") else 0.0,
                    cycle)

        # P2.2: Record escalation events
        self.record("escalation_requested", 1.0 if td.get("escalation_requested") else 0.0,
                    cycle)
        # P2.2: Record policy_mode (recovery mode active)
        policy_mode = 0.0
        if trace and hasattr(trace, 'reflection') and trace.reflection:
            policy_mode = 1.0 if trace.reflection.get("policy_mode", False) else 0.0
        self.record("policy_mode", policy_mode, cycle)

        # Stream-level metrics
        for sa in td.get("stream_activations", []):
            name = sa.get("name", "unknown")
            self.record(f"stream.{name}.activated",
                        1.0 if sa.get("activated") else 0.0, cycle,
                        tags={"stream": name})
            self.record(f"stream.{name}.cost",
                        sa.get("cost_ms", 0), cycle,
                        tags={"stream": name})
            if sa.get("intent_type"):
                self.record(f"stream.{name}.confidence",
                            sa.get("intent", {}).get("confidence", 0) if isinstance(sa.get("intent"), dict) else 0,
                            cycle, tags={"stream": name})

        # Council signals
        for sig in td.get("council_signals", []):
            vname = sig.get("validator", "unknown")
            self.record(f"council.{vname}.passed",
                        1.0 if sig.get("passed") else 0.0, cycle,
                        tags={"validator": vname})

        # Λ4.5: Record local-optima-escape event
        escape = td.get("local_optima_escape")
        if escape:
            self.record("local_optima_escape", 1.0, cycle,
                        tags={"escaped_from": escape.get("escaped_from", "unknown"),
                              "escaped_to": escape.get("escaped_to", "unknown")})
            self._escape_count += 1
            self.record("local_optima_escape.count", float(self._escape_count), cycle)

        # P2.2: Record reflection patterns
        reflection = td.get("reflection")
        if reflection:
            self.record("reflection.cross_domain_hits",
                        float(reflection.get("cross_domain_hits", 0)), cycle)
            self.record("reflection.recurring_blocks",
                        float(len(reflection.get("recurring_blocks", []))), cycle)
            if reflection.get("adaptive_horizon") is not None:
                self.record("reflection.adaptive_horizon",
                            float(reflection["adaptive_horizon"]), cycle)
            self.record("reflection.pattern_count",
                        float(reflection.get("pattern_count", 0)), cycle)
            self.record("reflection.stable",
                        1.0 if reflection.get("stable") else 0.0, cycle)

        # P2.2: Record knowledge consultation report
        knowledge_report = td.get("knowledge_report")
        if knowledge_report:
            self.record("knowledge.approach_found",
                        1.0 if knowledge_report.get("approach") else 0.0, cycle)
            self.record("knowledge.outcome",
                        float(knowledge_report.get("outcome", 0) or 0), cycle)
            known_failures = knowledge_report.get("avoid", [])
            self.record("knowledge.known_failures",
                        float(len(known_failures)), cycle)

        self._cycle_metrics[cycle] = td

    def get_series(self, name: str,
                   limit: Optional[int] = None) -> List[MetricPoint]:
        """Get all points for a metric name, newest first.
            Args:
                limit: the limit argument for this call.
        """
        points = [p for p in self._points if p.name == name]
        points.sort(key=lambda p: p.cycle, reverse=True)
        if limit:
            points = points[:limit]
        return points

    def get_cycle_count(self) -> int:
        return len(self._cycle_metrics)

    def summary(self) -> Dict:
        """Aggregate summary of all collected metrics."""
        if not self._points:
            return {"cycles": 0, "metrics": {}}

        cycles = set(p.cycle for p in self._points)
        names = set(p.name for p in self._points)

        summary = {
            "cycles": len(cycles),
            "points": len(self._points),
            "latest_cycle": max(cycles) if cycles else 0,
            "local_optima_escapes": self._escape_count,
        }

        for name in sorted(names):
            vals = [p.value for p in self._points if p.name == name and not p.tags]
            if vals:
                summary[name] = {
                    "mean": round(sum(vals) / len(vals), 3),
                    "min": round(min(vals), 3),
                    "max": round(max(vals), 3),
                    "latest": round(vals[-1], 3),
                }

        return summary

    def to_dict(self) -> Dict:
        """Export all data as dict for API response."""
        history = []
        for c, d in sorted(self._cycle_metrics.items()):
            entry = {
                "cycle": c,
                "di": d.get("decision_integrity"),
                "md": d.get("mission_drift"),
                "health": d.get("health_score"),
                "council_validated": d.get("council_validated"),
                "worlds": d.get("worlds_simulated"),
                "duration": d.get("cycle_duration_ms"),
            }
            # P2.2: Include extended fields in history
            if d.get("escalation_requested"):
                entry["escalation_requested"] = True
                entry["escalation_reason"] = d.get("escalation_reason")
            if d.get("reflection"):
                entry["reflection"] = {
                    "cross_domain_hits": d["reflection"].get("cross_domain_hits", 0),
                    "adaptive_horizon": d["reflection"].get("adaptive_horizon"),
                    "recurring_blocks": len(d["reflection"].get("recurring_blocks", [])),
                }
            if d.get("knowledge_report"):
                entry["knowledge"] = {
                    "approach": d["knowledge_report"].get("approach"),
                    "outcome": d["knowledge_report"].get("outcome"),
                    "failures": len(d["knowledge_report"].get("avoid", [])),
                }
            escape = d.get("local_optima_escape")
            if escape:
                entry["local_optima_escape"] = escape
            history.append(entry)

        return {
            "summary": self.summary(),
            "recent_points": [
                {"cycle": p.cycle, "name": p.name, "value": p.value,
                 "tags": p.tags}
                for p in sorted(self._points, key=lambda x: x.timestamp,
                                reverse=True)[:200]
            ],
            "history": history,
        }
