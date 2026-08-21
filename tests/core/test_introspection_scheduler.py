"""
Contract tests for telos/core/introspection/scheduler.py — IntrospectionScheduler.

Multi-timescale introspection (cycle/reflect/strategic). Tests assert REAL
behavior: tier scheduling (should_run), report generation for each tier,
and state serialization.
"""

from telos.core.introspection.scheduler import (
    IntrospectionScheduler, IntrospectionTier, IntrospectionReport, TierConfig,
)


def test_default_tier_intervals():
    s = IntrospectionScheduler()
    assert s._tiers[IntrospectionTier.CYCLE].interval == 1
    assert s._tiers[IntrospectionTier.REFLECT].interval == 100
    assert s._tiers[IntrospectionTier.STRATEGIC].interval == 1000
    assert s._tiers[IntrospectionTier.REFLECT].min_cycles_before_first == 50
    assert s._tiers[IntrospectionTier.STRATEGIC].min_cycles_before_first == 500


def test_should_run_cycle_always():
    s = IntrospectionScheduler()
    assert s.should_run(IntrospectionTier.CYCLE, 0) is True
    assert s.should_run(IntrospectionTier.CYCLE, 5) is True


def test_should_run_reflect_respects_min_cycles():
    s = IntrospectionScheduler()
    assert s.should_run(IntrospectionTier.REFLECT, 0) is False
    assert s.should_run(IntrospectionTier.REFLECT, 49) is False
    assert s.should_run(IntrospectionTier.REFLECT, 50) is True


def test_should_run_disabled_tier():
    s = IntrospectionScheduler()
    s.configure_tier(IntrospectionTier.REFLECT, enabled=False)
    assert s.should_run(IntrospectionTier.REFLECT, 100) is False


def test_should_run_reflect_after_last_run():
    s = IntrospectionScheduler()
    s._last_run[IntrospectionTier.REFLECT] = 50
    assert s.should_run(IntrospectionTier.REFLECT, 149) is False
    assert s.should_run(IntrospectionTier.REFLECT, 150) is True


def test_configure_tier_interval():
    s = IntrospectionScheduler()
    s.configure_tier(IntrospectionTier.REFLECT, interval=20, min_cycles=10)
    assert s._tiers[IntrospectionTier.REFLECT].interval == 20
    assert s._tiers[IntrospectionTier.REFLECT].min_cycles_before_first == 10


def test_cycle_introspection_reports_and_metrics():
    s = IntrospectionScheduler()
    reports = s.introspect(cycle=0, cycle_data={
        "predicted_state": [0, 0], "actual_state": [0, 0],
    })
    assert len(reports) == 1
    cycle_report = reports[0]
    assert cycle_report.tier == IntrospectionTier.CYCLE
    assert cycle_report.triggered is True
    assert cycle_report.metrics["action_taken"] == 0.0
    assert cycle_report.findings


def test_cycle_high_divergence_finding():
    s = IntrospectionScheduler()
    reports = s.introspect(cycle=0, cycle_data={
        "predicted_state": [0, 0], "actual_state": [10, 10],
    })
    r = reports[0]
    assert r.metrics["prediction_divergence"] > 5.0
    assert any("High prediction divergence" in f for f in r.findings)


def test_reflect_introspection_recurring_blocks():
    s = IntrospectionScheduler()
    reports = s.introspect(cycle=100, reflection_data={"recurring_blocks": [1, 2, 3]})
    tiers = {r.tier for r in reports}
    assert IntrospectionTier.CYCLE in tiers
    assert IntrospectionTier.REFLECT in tiers
    reflect = [r for r in reports if r.tier == IntrospectionTier.REFLECT][0]
    assert reflect.triggered is True
    assert any("recurring block" in f.lower() for f in reflect.findings)
    assert any("validator" in rec for rec in reflect.recommendations)


def test_reflect_low_skill_diversity_finding():
    s = IntrospectionScheduler()
    reports = s.introspect(cycle=100, reflection_data={"skill_usage": {"a": 1}})
    reflect = [r for r in reports if r.tier == IntrospectionTier.REFLECT][0]
    assert any("Low skill diversity" in f for f in reflect.findings)
    assert reflect.metrics["skill_diversity"] == 1 / 6  # 1 used, /(1+5)


def test_reflect_low_di_finding():
    s = IntrospectionScheduler()
    traces = [{"decision_integrity": 0.2}] * 20
    reports = s.introspect(cycle=100, reflection_data={"recent_traces": traces})
    reflect = [r for r in reports if r.tier == IntrospectionTier.REFLECT][0]
    assert reflect.metrics["avg_di"] < 0.6
    assert any("Decision Integrity trending low" in f for f in reflect.findings)


def test_strategic_introspection():
    s = IntrospectionScheduler()
    reports = s.introspect(cycle=1000, strategic_data={"axiom_scores": {"a1": 0.3}})
    tiers = {r.tier for r in reports}
    assert IntrospectionTier.STRATEGIC in tiers
    strat = [r for r in reports if r.tier == IntrospectionTier.STRATEGIC][0]
    assert strat.triggered is True
    assert any("Axiom satisfaction below threshold" in f for f in strat.findings)
    assert strat.metrics["axiom_coverage"] == 0.3


def test_strategic_no_data_still_reports():
    s = IntrospectionScheduler()
    reports = s.introspect(cycle=1000)
    strat = [r for r in reports if r.tier == IntrospectionTier.STRATEGIC][0]
    assert any("Strategic review at cycle 1000" in f for f in strat.findings)


def test_get_due_tiers():
    s = IntrospectionScheduler()
    assert IntrospectionTier.CYCLE in s.get_due_tiers(0)
    assert IntrospectionTier.REFLECT not in s.get_due_tiers(0)
    assert IntrospectionTier.REFLECT in s.get_due_tiers(100)


def test_report_history_capped():
    s = IntrospectionScheduler()
    for cyc in range(30):
        s.introspect(cycle=cyc)
    assert len(s._report_history[IntrospectionTier.CYCLE]) == 20  # max 20


def test_to_dict_shape():
    s = IntrospectionScheduler()
    d = s.to_dict()
    assert set(d["tiers"].keys()) == {"cycle", "reflect", "strategic"}
    assert "interval" in d["tiers"]["cycle"]
    assert "enabled" in d["tiers"]["cycle"]
    assert "last_run" in d["tiers"]["cycle"]


def test_tier_config_defaults():
    cfg = TierConfig(interval=5)
    assert cfg.interval == 5
    assert cfg.enabled is True
    assert cfg.min_cycles_before_first == 0
