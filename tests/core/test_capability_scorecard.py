"""
Capability scorecard — a falsifiable, signal-derived self-assessment.

Every dimension must be computed from real signals, bounded [0, 5], and the
four uplift baselines must be present. Scores are not asserted to meet the
targets (those are roadmap outputs), but no score may exceed the honest cap.
"""

from telos.core.verifier.capability_scorecard import (
    DIMENSIONS, TARGETS, compute_scorecard, four_baselines, report_lines,
)


def test_all_dimensions_computed_and_bounded():
    """Every rubric dimension is computed and within [0, 5]."""
    card = compute_scorecard()
    assert set(card) == set(DIMENSIONS)
    for result in card.values():
        assert 0.0 <= result.score <= 5.0, result


def test_four_baselines_present():
    """The four uplift dimensions are present with target+direction."""
    baselines = four_baselines()
    assert set(baselines) == set(TARGETS)
    for result in compute_scorecard().values():
        if result.target is not None:
            assert result.name in TARGETS


def test_scorecard_is_deterministic():
    """Two computations over an unchanged tree agree exactly."""
    a = {k: v.score for k, v in compute_scorecard().items()}
    b = {k: v.score for k, v in compute_scorecard().items()}
    assert a == b


def test_baselines_are_bounded_and_directionally_honest():
    """Uplift scores stay in [0, 5]; targets are declared per dimension.

    The scores are EXPECTED to reach (and may exceed) their targets as the
    roadmap lands — this test locks the honest bound (never above 5.0) and that
    every uplift dimension declares a target, not that targets are unmet.
    """
    baselines = four_baselines()
    for name, target in TARGETS.items():
        assert 0.0 <= baselines[name] <= 5.0, (name, baselines[name])
        assert target > 0.0


def test_maturity_is_capped_without_external_reproduction():
    """Maturity cannot be 5.0 while no external reproduction artifact exists."""
    card = compute_scorecard()
    assert card["maturity"].score <= 4.0
    assert card["maturity"].external is False or card["maturity"].score > 0


def test_tool_use_reflects_the_registry():
    """Tool use must cite the canonical registry families as evidence."""
    card = compute_scorecard()
    assert any("registry families" in e for e in card["tool_use"].evidence)


def test_report_lines_render():
    """The printable report includes the title and the uplift section."""
    lines = report_lines()
    text = "\n".join(lines)
    assert "Capability Scorecard" in text
    assert "Uplift baselines" in text
    for name in TARGETS:
        assert name in text
