"""
Counterfactual simulation option types (core/simulation/options.py).

Honest contract coverage: StrategicOption, ProbabilisticScore, TrajectoryClass.
"""
import numpy as np
import pytest

from telos.core.simulation.options import (
    StrategicOption, ProbabilisticScore, TrajectoryClass,
)


class TestProbabilisticScore:
    def test_fields(self):
        s = ProbabilisticScore(mean=0.5, std=0.1, n_samples=10,
                               ci_lower=0.3, ci_upper=0.7, min_score=0.0,
                               max_score=1.0)
        assert s.mean == 0.5
        assert s.n_samples == 10


class TestStrategicOption:
    def test_defaults(self):
        o = StrategicOption(world=None, score=0.5, rank=0)
        assert o.project_id == "default"
        assert o.horizon == 0
        assert o.metadata == {}
        assert o.probabilistic is None

    def test_variance_with_probabilistic(self):
        s = ProbabilisticScore(mean=0.5, std=0.2, n_samples=5,
                               ci_lower=0.4, ci_upper=0.6, min_score=0.0,
                               max_score=1.0)
        o = StrategicOption(world=None, score=0.5, rank=0, probabilistic=s)
        assert o.variance == pytest.approx(0.04)

    def test_variance_no_probabilistic(self):
        o = StrategicOption(world=None, score=0.5, rank=0)
        assert o.variance == 0.0


class TestTrajectoryClass:
    def test_values(self):
        assert TrajectoryClass.EXPLORE.value == "explore"
        assert TrajectoryClass.EXIT.value == "exit"
        assert len(list(TrajectoryClass)) == 5
