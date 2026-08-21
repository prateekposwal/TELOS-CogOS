"""Contract tests for telos.core.infra_manager.cost_tracker.MaintenanceCostTracker.

Covers the Axiom 5.1 cost-accounting contract:
  - rolling maintenance/recovery cost totals with per-cycle 10% decay
  - window trimming (keeps last `window_size` entries once over 2x window)
  - ratio and efficiency properties (with neutral defaults on empty state)
  - trend classification once 3+ cycles are recorded
  - the stats summary dict
"""
import pytest

from telos.core.infra_manager.cost_tracker import MaintenanceCostTracker


def test_initial_state_is_neutral():
    t = MaintenanceCostTracker()
    assert t.total_maintenance == 0.0
    assert t.total_recovery == 0.0
    assert t.total_cost == 0.0
    assert t.maintenance_ratio == 0.5
    assert t.recovery_ratio == 0.5
    assert t.cost_efficiency == 1.0
    assert t.trend == "insufficient_data"
    assert t.stats["cycles_recorded"] == 0


def test_record_maintenance_accumulates_with_decay():
    t = MaintenanceCostTracker()
    t.record_maintenance(100.0)
    assert t.total_maintenance == 100.0
    assert t.total_cost == 100.0
    # Second record decays the first by 10% before appending.
    t.record_maintenance(100.0)
    assert t.total_maintenance == pytest.approx(190.0)


def test_record_recovery_accumulates_with_decay():
    t = MaintenanceCostTracker()
    t.record_recovery(50.0)
    t.record_recovery(50.0)
    assert t.total_recovery == pytest.approx(95.0)


def test_negative_costs_are_clamped_to_zero():
    t = MaintenanceCostTracker()
    t.record_maintenance(-5.0)
    t.record_recovery(-3.0)
    assert t.total_maintenance == 0.0
    assert t.total_recovery == 0.0
    assert t.stats["cycles_recorded"] == 2


def test_ratios_sum_to_one_when_both_present():
    t = MaintenanceCostTracker()
    t.record_maintenance(100.0)
    # Recording the recovery decays the maintenance entry to 90.
    t.record_recovery(50.0)
    assert t.maintenance_ratio == pytest.approx(90.0 / 140.0)
    assert t.recovery_ratio == pytest.approx(50.0 / 140.0)
    assert t.maintenance_ratio + t.recovery_ratio == pytest.approx(1.0)


def test_cost_efficiency_with_no_recovery():
    t = MaintenanceCostTracker()
    t.record_maintenance(100.0)
    assert t.cost_efficiency == 2.0


def test_cost_efficiency_ratio():
    t = MaintenanceCostTracker()
    t.record_maintenance(200.0)
    # Recording the recovery decays maintenance to 180.
    t.record_recovery(50.0)
    assert t.cost_efficiency == pytest.approx(180.0 / 50.0)


def test_window_trimming_keeps_last_window_size():
    t = MaintenanceCostTracker(window_size=2)
    for _ in range(5):
        t.record_maintenance(10.0)
    # After 5 records with window_size=2: only the last 2 survive the trim.
    # Decay math: after the 4th record the list exceeds 2*window_size and is
    # trimmed to the last `window_size` entries.
    assert t.stats["cycles_recorded"] == 5
    assert t.total_maintenance == pytest.approx(19.0)


def test_trend_insufficient_below_three_cycles():
    t = MaintenanceCostTracker()
    t.record_maintenance(100.0)
    t.record_recovery(100.0)
    assert t.trend == "insufficient_data"


def test_trend_healthy_when_maintenance_dominates():
    t = MaintenanceCostTracker()
    for _ in range(3):
        t.record_maintenance(100.0)
    assert t.trend == "healthy — maintenance dominates, proactive posture"


def test_trend_critical_when_recovery_dominates():
    t = MaintenanceCostTracker()
    for _ in range(3):
        t.record_recovery(100.0)
    assert t.trend == "critical — recovery dominates, firefighting mode"


def test_trend_stable_slight_maintenance_advantage():
    t = MaintenanceCostTracker()
    for _ in range(3):
        t.record_maintenance(100.0)
        t.record_recovery(80.0)
    assert t.trend == "stable — slight maintenance advantage"


def test_trend_deteriorating_when_recovery_rising():
    t = MaintenanceCostTracker()
    for _ in range(3):
        t.record_maintenance(100.0)
        t.record_recovery(100.0)
    assert t.trend == "deteriorating — recovery costs rising"


def test_stats_dict_reports_all_contract_fields():
    t = MaintenanceCostTracker()
    t.record_maintenance(10.0)
    t.record_recovery(5.0)
    stats = t.stats
    assert set(stats.keys()) == {
        "total_maintenance", "total_recovery", "total_cost",
        "maintenance_ratio", "recovery_ratio", "cost_efficiency",
        "trend", "cycles_recorded", "recent_maintenance", "recent_recovery",
    }
    # Recording recovery decays the earlier maintenance entry 10 -> 9.
    assert stats["total_maintenance"] == pytest.approx(9.0)
    assert stats["total_recovery"] == pytest.approx(5.0)
    assert stats["cycles_recorded"] == 2
    assert stats["recent_maintenance"] == [9.0]
    assert stats["recent_recovery"] == [5.0]


def test_recent_lists_bounded_by_five():
    t = MaintenanceCostTracker()
    for i in range(8):
        t.record_maintenance(float(i))
    stats = t.stats
    assert len(stats["recent_maintenance"]) <= 5
    assert stats["recent_maintenance"] == stats["recent_maintenance"][-5:]
