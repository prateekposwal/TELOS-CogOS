"""Contract tests for MissionArbiter — resolves conflicts between competing
missions on four axes (core alignment, urgency, priority, inertia)."""
import pytest

from telos.core.identity.mission_arbitration import (
    MissionArbiter, ArbitrationVerdict, WEIGHT_CORE_ALIGNMENT,
)
from telos.core.identity.mission import Mission, MissionPortfolio, MissionLifecycle


def _mission(mid, value):
    return Mission(id=mid, name=mid, description="d",
                   identity_core_alignment=value, priority=0.5, urgency=0.5,
                   lifecycle=MissionLifecycle.ACTIVE)


class _Portfolio:
    def __init__(self, missions):
        self._missions = missions

    def active_missions(self):
        return self._missions


def test_empty_portfolio_yields_no_verdicts():
    assert MissionArbiter().arbitrate(_Portfolio([])) == []


def test_single_mission_becomes_active():
    verdicts = MissionArbiter().arbitrate(_Portfolio([_mission("m1", 0.9)]))
    v = verdicts[0]
    assert isinstance(v, ArbitrationVerdict)
    assert v.becomes_active is True
    assert v.rank == 0


def test_higher_alignment_ranks_first():
    verdicts = MissionArbiter().arbitrate(_Portfolio(
        [_mission("low", 0.2), _mission("high", 0.9)]))
    by_id = {v.mission_id: v for v in verdicts}
    assert by_id["high"].rank == 0
    assert by_id["high"].becomes_active is True
    assert by_id["low"].becomes_active is False


def test_weights_are_documented():
    assert 0.0 < WEIGHT_CORE_ALIGNMENT < 1.0