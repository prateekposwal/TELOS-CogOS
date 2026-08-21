"""Contract tests for telos/core/attention.py — BudgetManager governor."""

import pytest

from telos.core.attention import BudgetManager


def test_check_budget_respects_total():
    b = BudgetManager(total_budget_ms=100.0)
    assert b.check_budget('act', 100.0) is True
    assert b.check_budget('act', 100.1) is False


def test_reservation_reserved_by_its_owner():
    b = BudgetManager(total_budget_ms=100.0)
    b.reserve('perceive', 20.0)
    # owner may spend from its own reservation plus the unreserved pool
    assert b.check_budget('perceive', 120.0) is True


def test_reservation_blocks_other_streams():
    b = BudgetManager(total_budget_ms=100.0)
    b.reserve('perceive', 20.0)
    assert b.check_budget('act', 80.0) is True
    assert b.check_budget('act', 80.1) is False


def test_consume_accumulates_consumed_and_phase_costs():
    b = BudgetManager(total_budget_ms=100.0)
    b.consume('act', 30.0)
    b.consume('act', 10.0)
    assert b.consumed_ms == 40.0
    assert b.phase_costs == {'act': 40.0}


def test_consume_tracks_multiple_phases():
    b = BudgetManager(total_budget_ms=100.0)
    b.consume('perceive', 10.0)
    b.consume('act', 5.0)
    assert b.phase_costs == {'perceive': 10.0, 'act': 5.0}


def test_reset_clamps_carryover_to_half_total():
    b = BudgetManager(total_budget_ms=100.0)
    b.consume('act', 30.0)
    b.reset(carryover_ms=1000.0)
    assert b.budget_carryover_ms == 50.0
    assert b.consumed_ms == 0.0
    assert b.phase_costs == {}
    assert b._reservations == {}


def test_reset_never_negative_carryover():
    b = BudgetManager(total_budget_ms=100.0)
    b.reset(carryover_ms=-5.0)
    assert b.budget_carryover_ms == 0.0


def test_carryover_grants_headroom_in_check_budget():
    b = BudgetManager(total_budget_ms=100.0)
    b.reset(carryover_ms=20.0)
    # fresh cycle still gets carried-over headroom
    assert b.check_budget('act', 120.0) is True
