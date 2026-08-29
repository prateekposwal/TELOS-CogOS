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
from telos.core.types import DecisionTrace

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

        # Λ4.7 hot path (v7): read the trace's OWN scalar fields. The full
        # to_dict() serialization is reserved for checkpoint/API/audit events —
        # telemetry only needs ~12 scalars, so converting the whole DecisionTrace
        # (belief_state, axiom_results, reasoning_witness, ...) to a dict every
        # cycle was a wasteful hot-path rebuild (measured 1.003 serializations/
        # cycle at baseline; should be ~0 here).
        # Hybrid accessor: real DecisionTrace instances expose dataclass
        # attributes (short-circuits, never serializes); dict-backed stand-ins
        # (tests) fall back to their to_dict() shape.
        _missing = object()
        _is_real = isinstance(trace, DecisionTrace)

        def _field(name, default):
            """Real DecisionTrace: pure attribute access — NEVER serialized on
            this path (the contract's <=1 hot-path serialization). Dict-backed
            stand-ins (tests): fall back to their to_dict() shape."""
            if _is_real:
                v = getattr(trace, name, _missing)
                return default if v is None else v
            v = getattr(trace, name, _missing)
            if v is _missing or v is None:
                if hasattr(trace, "to_dict"):
                    v = trace.to_dict().get(name, default)
            return default if v is None else v

        def _g(name, default):
            return float(_field(name, default))

        self.record("di", _g("decision_integrity", 0.0), cycle)
        self.record("md", _g("mission_drift", 0.0), cycle)
        self.record("budget_consumed", _g("budget_consumed_ms", 0.0), cycle)
        self.record("budget_total", _g("budget_total_ms", 0.0), cycle)
        self.record("worlds_simulated", _g("worlds_simulated", 0.0), cycle)
        self.record("cycle_duration", _g("cycle_duration_ms", 0.0), cycle)
        self.record("health", _g("health_score", 1.0), cycle)
        self.record("council_validated",
                    1.0 if getattr(trace, "council_validated", True) else 0.0, cycle)
        self.record("firewall_blocked",
                    1.0 if getattr(trace, "firewall_blocked", False) else 0.0, cycle)

        # P2.2: Record escalation events
        self.record("escalation_requested",
                    1.0 if getattr(trace, "escalation_requested", False) else 0.0,
                    cycle)
        # P2.2: Record policy_mode (recovery mode active)
        policy_mode = 0.0
        reflection = getattr(trace, "reflection", None)
        if reflection and isinstance(reflection, dict):
            policy_mode = 1.0 if reflection.get("policy_mode", False) else 0.0
        self.record("policy_mode", policy_mode, cycle)

        # Stream-level metrics (direct attribute access on StreamActivation;
        # dict-shaped entries from serialized stand-ins also supported)
        _stream_acts = _field("stream_activations", None) or []
        for sa in (_stream_acts or []):
            name = getattr(sa, "stream_name", None)
            if not name and isinstance(sa, dict):
                name = sa.get("name", "unknown")
            name = name or "unknown"
            activated = getattr(sa, "activated", False)
            if isinstance(sa, dict):
                activated = sa.get("activated", False)
            self.record(f"stream.{name}.activated",
                        1.0 if activated else 0.0, cycle,
                        tags={"stream": name})
            cost = getattr(sa, "cost_ms", 0)
            if isinstance(sa, dict):
                cost = sa.get("cost_ms", 0)
            self.record(f"stream.{name}.cost",
                        float(cost or 0), cycle,
                        tags={"stream": name})
            intent = getattr(sa, "intent", None)
            if isinstance(sa, dict):
                intent = sa.get("intent")
            if intent is not None:
                conf = getattr(intent, "confidence", None)
                if conf is None and isinstance(intent, dict):
                    conf = intent.get("confidence", 0)
                self.record(f"stream.{name}.confidence",
                            float(conf or 0), cycle,
                            tags={"stream": name})

        # Council signals (already plain dicts on the trace)
        _sigs = _field("council_signals", None) or []
        for sig in (_sigs or []):
            vname = sig.get("validator", "unknown")
            self.record(f"council.{vname}.passed",
                        1.0 if sig.get("passed") else 0.0, cycle,
                        tags={"validator": vname})

        # Λ4.5: Record local-optima-escape event (attribute access, no to_dict)
        escape = _field("local_optima_escape", None)
        if escape is not None and hasattr(escape, "get"):
            escape = dict(escape)
        if escape:
            self.record("local_optima_escape", 1.0, cycle,
                        tags={"escaped_from": escape.get("escaped_from", "unknown"),
                              "escaped_to": escape.get("escaped_to", "unknown")})
            self._escape_count += 1
            self.record("local_optima_escape.count", float(self._escape_count), cycle)

        # P2.2: Record reflection patterns
        reflection = _field("reflection", None)
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
        knowledge_report = _field("knowledge_report", None)
        if knowledge_report:
            self.record("knowledge.approach_found",
                        1.0 if knowledge_report.get("approach") else 0.0, cycle)
            self.record("knowledge.outcome",
                        float(knowledge_report.get("outcome", 0) or 0), cycle)
            known_failures = knowledge_report.get("avoid", [])
            self.record("knowledge.known_failures",
                        float(len(known_failures)), cycle)

        # Bounded lean per-cycle record (v7): the full trace dict was stored
        # here every cycle (unbounded growth + hot serialization). Consumers
        # need only ~7 scalars — store those (reflection kept for the
        # history view) and cap the ring so historical traces never live on
        # as full objects (contract: memory after 1000 cycles ≈ idle).
        lean = {
            "decision_integrity": _g("decision_integrity", 1.0),
            "mission_drift": _g("mission_drift", 0.0),
            "health_score": _g("health_score", 1.0),
            "council_validated": bool(getattr(trace, "council_validated", True)),
            "worlds_simulated": int(_g("worlds_simulated", 0)),
            "cycle_duration_ms": _g("cycle_duration_ms", 0.0),
            "escalation_requested": bool(getattr(trace, "escalation_requested", False)),
            "escalation_reason": getattr(trace, "escalation_reason", None),
        }
        if reflection and isinstance(reflection, dict):
            lean["reflection"] = {
                "cross_domain_hits": reflection.get("cross_domain_hits", 0),
                "recurring_blocks": reflection.get("recurring_blocks", []),
                "adaptive_horizon": reflection.get("adaptive_horizon"),
                "pattern_count": reflection.get("pattern_count", 0),
                "stable": reflection.get("stable", False),
            }
        else:
            lean["reflection"] = None
        self._cycle_metrics[cycle] = lean
        if len(self._cycle_metrics) > 200:
            # HOT ring: drop the oldest cycles (never a full-trace retain)
            for c in sorted(self._cycle_metrics)[:-200]:
                del self._cycle_metrics[c]

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
