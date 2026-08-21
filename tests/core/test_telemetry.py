"""Tests for TelemetryCollector — time-series metric recording, cycle-level
trace ingestion, series queries, and JSON summaries."""

from telos.core.observability.telemetry import TelemetryCollector, MetricPoint


class FakeTrace:
    """Minimal stand-in for DecisionTrace with a to_dict() contract."""

    def __init__(self, data=None, reflection=None):
        self._data = dict(data or {})
        self.reflection = reflection

    def to_dict(self):
        return self._data


class TestRecord:
    def test_record_appends_point(self):
        tc = TelemetryCollector()
        tc.record("di", 0.9, cycle=1)
        assert len(tc._points) == 1
        p = tc._points[0]
        assert p.name == "di"
        assert p.value == 0.9
        assert p.cycle == 1
        assert p.tags == {}

    def test_record_with_tags(self):
        tc = TelemetryCollector()
        tc.record("stream.x.cost", 2.0, cycle=1, tags={"stream": "x"})
        assert tc._points[0].tags == {"stream": "x"}

    def test_record_uses_default_args(self):
        tc = TelemetryCollector()
        tc.record("di", 0.5)
        p = tc._points[0]
        assert p.cycle == 0
        assert p.timestamp > 0

    def test_window_capped(self):
        tc = TelemetryCollector(max_points=10)
        for i in range(25):
            tc.record("di", float(i), cycle=i)
        assert len(tc._points) == 10
        assert tc._points[0].cycle == 15


class TestRecordCycle:
    def test_none_trace_is_noop(self):
        tc = TelemetryCollector()
        tc.record_cycle(1, None)
        assert len(tc._points) == 0
        assert tc.get_cycle_count() == 0

    def test_records_core_metrics(self):
        tc = TelemetryCollector()
        trace = FakeTrace({
            "decision_integrity": 0.9,
            "mission_drift": 0.2,
            "budget_consumed_ms": 10.0,
            "budget_total_ms": 50.0,
            "worlds_simulated": 4,
            "cycle_duration_ms": 12.5,
            "health_score": 0.8,
            "council_validated": True,
            "firewall_blocked": False,
            "escalation_requested": True,
        })
        tc.record_cycle(3, trace)
        names = {p.name for p in tc._points}
        assert {
            "di", "md", "budget_consumed", "budget_total",
            "worlds_simulated", "cycle_duration", "health",
            "council_validated", "firewall_blocked", "escalation_requested",
            "policy_mode",
        } <= names
        assert tc.get_cycle_count() == 1
        di = tc.get_series("di")[0]
        assert di.value == 0.9 and di.cycle == 3

    def test_policy_mode_from_reflection(self):
        tc = TelemetryCollector()
        trace = FakeTrace(
            {"decision_integrity": 1.0},
            reflection={"policy_mode": True},
        )
        tc.record_cycle(1, trace)
        pm = tc.get_series("policy_mode")[0]
        assert pm.value == 1.0

    def test_stream_activations_recorded(self):
        tc = TelemetryCollector()
        trace = FakeTrace({
            "stream_activations": [
                {"name": "inquiry", "activated": True, "cost_ms": 2.5,
                 "intent_type": "blended_inquiry",
                 "intent": {"confidence": 0.6}},
                {"name": "reflex", "activated": False, "cost_ms": 0.0,
                 "intent_type": "react",
                 "intent": None},
            ],
            "council_signals": [
                {"validator": "safety", "passed": True},
            ],
        })
        tc.record_cycle(2, trace)
        names = {p.name for p in tc._points}
        assert "stream.inquiry.activated" in names
        assert "stream.inquiry.cost" in names
        assert "stream.inquiry.confidence" in names
        assert "stream.reflex.activated" in names
        assert "council.safety.passed" in names
        assert tc.get_series("council.safety.passed", limit=1)[0].value == 1.0

    def test_local_optima_escape_recorded_with_count(self):
        tc = TelemetryCollector()
        trace = FakeTrace({
            "local_optima_escape": {"escaped_from": "cartesian", "escaped_to": "polar"},
        })
        tc.record_cycle(1, trace)
        assert tc._escape_count == 1
        tag_point = [p for p in tc.get_series("local_optima_escape")][0]
        assert tag_point.tags == {"escaped_from": "cartesian", "escaped_to": "polar"}
        count = tc.get_series("local_optima_escape.count")[0]
        assert count.value == 1.0

    def test_reflection_metrics_recorded(self):
        tc = TelemetryCollector()
        trace = FakeTrace({
            "reflection": {
                "cross_domain_hits": 3,
                "recurring_blocks": ["block1"],
                "adaptive_horizon": 5,
                "pattern_count": 2,
                "stable": True,
            },
        })
        tc.record_cycle(1, trace)
        names = {p.name for p in tc._points}
        assert {
            "reflection.cross_domain_hits", "reflection.recurring_blocks",
            "reflection.adaptive_horizon", "reflection.pattern_count",
            "reflection.stable",
        } <= names

    def test_knowledge_report_recorded(self):
        tc = TelemetryCollector()
        trace = FakeTrace({
            "knowledge_report": {
                "approach": "use_polar",
                "outcome": 2,
                "avoid": ["trapped", "overheat"],
            },
        })
        tc.record_cycle(1, trace)
        names = {p.name for p in tc._points}
        assert {"knowledge.approach_found", "knowledge.outcome",
                "knowledge.known_failures"} <= names
        assert tc.get_series("knowledge.known_failures")[0].value == 2.0

    def test_cycle_metrics_map_stores_trace_dict(self):
        tc = TelemetryCollector()
        tc.record_cycle(1, FakeTrace({"decision_integrity": 0.7}))
        assert tc._cycle_metrics[1]["decision_integrity"] == 0.7


class TestQuery:
    def test_get_series_newest_first(self):
        tc = TelemetryCollector()
        for i in range(5):
            tc.record("di", float(i), cycle=i)
        series = tc.get_series("di")
        assert [p.cycle for p in series] == [4, 3, 2, 1, 0]

    def test_get_series_with_limit(self):
        tc = TelemetryCollector()
        for i in range(5):
            tc.record("di", float(i), cycle=i)
        assert len(tc.get_series("di", limit=2)) == 2

    def test_get_series_empty(self):
        tc = TelemetryCollector()
        assert tc.get_series("missing") == []


class TestSummary:
    def test_empty_summary(self):
        tc = TelemetryCollector()
        assert tc.summary() == {"cycles": 0, "metrics": {}}

    def test_aggregates_by_name(self):
        tc = TelemetryCollector()
        tc.record("di", 1.0, cycle=1)
        tc.record("di", 2.0, cycle=2)
        tc.record("di", 3.0, cycle=3)
        s = tc.summary()
        assert s["cycles"] == 3
        assert s["points"] == 3
        assert s["latest_cycle"] == 3
        assert s["di"] == {"mean": 2.0, "min": 1.0, "max": 3.0, "latest": 3.0}

    def test_tagged_points_excluded_from_mean(self):
        tc = TelemetryCollector()
        tc.record("di", 0.5, cycle=1)
        tc.record("di", 0.9, cycle=2, tags={"source": "x"})
        s = tc.summary()
        assert s["di"]["mean"] == 0.5
        assert s["di"]["latest"] == 0.5


class TestToDict:
    def test_to_dict_history_and_points(self):
        tc = TelemetryCollector()
        tc.record_cycle(2, FakeTrace({"decision_integrity": 0.8,
                                      "mission_drift": 0.1,
                                      "health_score": 0.7,
                                      "council_validated": True,
                                      "worlds_simulated": 3,
                                      "cycle_duration_ms": 9.0}))
        tc.record_cycle(1, FakeTrace({"decision_integrity": 0.5}))
        d = tc.to_dict()
        assert d["summary"]["cycles"] == 2
        assert len(d["history"]) == 2
        assert d["history"][0]["cycle"] == 1
        assert d["history"][1]["cycle"] == 2
        entry = d["history"][1]
        assert entry["di"] == 0.8
        assert "recent_points" in d