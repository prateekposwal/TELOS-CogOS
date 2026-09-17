"""
Coverage-priority analyzer (telos/tools/coverage_priority.py) — contract.

The analyzer measures REAL coverage (test references a module's dotted path or a
specific symbol) rather than basename matching, and ranks genuinely-uncovered
modules by criticality. These tests pin its shape and monotonicity.
"""
from telos.tools.coverage_priority import (
    analyze, _module_dotted, _coverage_weight,
)


def test_module_dotted_conversion():
    assert _module_dotted("reasoning/theory/builder.py") == \
        "telos.core.reasoning.theory.builder"
    assert _module_dotted("runtime.py") == "telos.core.runtime"


def test_critical_package_weighting():
    assert _coverage_weight("runtime.py") >= 4.0
    assert _coverage_weight("phases/streams.py") >= 3.0
    assert _coverage_weight("reasoning/theory/builder.py") >= 3.0
    assert _coverage_weight("some/random/module.py") == 1.0


def test_analyze_shape_and_consistency():
    report = analyze()
    assert report["total"] > 100
    assert report["covered"] + report["uncovered"] == report["total"]
    assert isinstance(report["rows"], list)
    # rows are ranked by descending score
    scores = [r["score"] for r in report["rows"]]
    assert scores == sorted(scores, reverse=True)
    for row in report["rows"]:
        assert set(row) == {"module", "fan_in", "loc", "weight", "score"}
        assert row["module"].startswith("core/")
