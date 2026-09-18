"""
Memory retrieval evaluation — the measured proof the memory layer works.

The eval must (a) run deterministically, (b) PASS when the controller beats the
naive baseline, and (c) FAIL if the controller's advantage is removed (a
regression guard against a rigged fixture).
"""

from telos.core.memory.controller import MemoryController
from telos.tools.memory_eval import build_fixture, evaluate, _build_controller, _metrics


def test_fixture_is_well_formed():
    """The fixture has paired records and one expected high-importance hit each."""
    fixture = build_fixture()
    assert fixture["queries"]
    assert len(fixture["records"]) >= len(fixture["queries"])
    for item in fixture["queries"]:
        assert item["expected"]


def test_evaluate_passes():
    """The controller beats naive (recall@1 >= 0.9) on the fixed fixture."""
    result = evaluate()
    assert result["beats_naive"] is True
    assert result["controller"]["recall@1"] >= 0.9
    assert result["controller"]["mrr"] > result["naive"]["mrr"]


def test_evaluate_is_deterministic():
    """Two evaluations over the fixture are identical."""
    assert evaluate() == evaluate()


def test_naive_baseline_is_actually_weaker():
    """If the controller is reduced to naive, the measured advantage vanishes.

    This locks the eval against a fixture that would pass trivially: when the
    ranking function is swapped for the baseline, recall@1 must drop.
    """
    fixture = build_fixture()
    controller = _build_controller(fixture["records"])
    naive = _build_controller(fixture["records"])
    good = _metrics(controller.search, fixture["queries"], k=1)
    base = _metrics(naive.naive_search, fixture["queries"], k=1)
    assert good["recall@1"] > base["recall@1"]


def test_metrics_are_bounded():
    """Recall/precision/MRR stay within [0, 1]."""
    result = evaluate()
    for section in ("controller", "naive"):
        for key, value in result[section].items():
            assert 0.0 <= value <= 1.0, (section, key, value)
