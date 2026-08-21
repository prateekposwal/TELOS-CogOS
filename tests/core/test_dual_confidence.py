"""Contract tests for DualConfidence — separating "what to do" (DC) from
"why" (EC), tracking the gap between them."""

import pytest

from telos.core.reasoning.confidence.dual_confidence import (
    DualConfidence, DecisionConfidence, ExplanationConfidence, ConfidenceReport,
)


class TestDecisionConfidence:
    def test_option_clarity_clear_winner(self):
        dc = DualConfidence().compute_decision_confidence(
            predictive_accuracy=0.9, option_scores=[0.9, 0.6, 0.3],
            familiarity=1.0, urgency=0.0,
        )
        # clarity = (0.9 - 0.6) / 0.9 = 0.333...
        assert pytest.approx(dc.option_clarity, abs=1e-3) == 0.3333
        expected = 0.9 * 0.35 + 0.3333 * 0.35 + 1.0 * 0.20
        assert pytest.approx(dc.score, abs=1e-3) == expected
        assert dc.sources["predictive_accuracy"] == 0.9

    def test_single_option_full_clarity(self):
        dc = DualConfidence().compute_decision_confidence(
            predictive_accuracy=0.5, option_scores=[0.8], familiarity=0.0,
        )
        assert dc.option_clarity == 1.0

    def test_no_options_zero_clarity(self):
        dc = DualConfidence().compute_decision_confidence(
            predictive_accuracy=0.5, option_scores=[], familiarity=0.0,
        )
        assert dc.option_clarity == 0.0

    def test_tied_options_zero_clarity(self):
        dc = DualConfidence().compute_decision_confidence(
            predictive_accuracy=0.5, option_scores=[0.7, 0.7], familiarity=0.0,
        )
        assert dc.option_clarity == 0.0

    def test_score_clamped_to_unit_interval(self):
        dc = DualConfidence().compute_decision_confidence(
            predictive_accuracy=1.0, option_scores=[1.0, 0.0],
            familiarity=1.0, urgency=1.0,
        )
        assert dc.score <= 1.0
        assert dc.is_high

    def test_threshold_properties(self):
        assert DecisionConfidence(score=0.8, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0).is_high
        assert DecisionConfidence(score=0.3, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0).is_low


class TestExplanationConfidence:
    def test_falsifiability_lowers_explanation_confidence(self):
        engine = DualConfidence()
        low_falsifiability = engine.compute_explanation_confidence(
            causal_coherence=0.8, evidence_completeness=0.9,
            theory_support=0.7, falsifiability=0.2,
        ).score
        high_falsifiability = engine.compute_explanation_confidence(
            causal_coherence=0.8, evidence_completeness=0.9,
            theory_support=0.7, falsifiability=0.9,
        ).score
        assert high_falsifiability < low_falsifiability
        # honesty term is (1 - falsifiability) * 0.15
        expected = 0.8 * 0.30 + 0.9 * 0.30 + 0.7 * 0.25 + 0.1 * 0.15
        assert pytest.approx(high_falsifiability, abs=1e-9) == expected

    def test_sources_filled(self):
        ec = DualConfidence().compute_explanation_confidence(
            causal_coherence=0.5, evidence_completeness=0.5,
            theory_support=0.5,
        )
        assert set(ec.sources) == {
            "causal_coherence", "evidence_completeness",
            "theory_support", "falsifiability",
        }
        assert ExplanationConfidence(score=0.7, causal_coherence=0, evidence_completeness=0, theory_support=0, falsifiability=0).is_high


class TestReportGapType:
    def _report(self, decision_id, dc_score, ec_score):
        dc = DecisionConfidence(score=dc_score, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0)
        ec = ExplanationConfidence(score=ec_score, causal_coherence=0, evidence_completeness=0, theory_support=0, falsifiability=0)
        return DualConfidence().report(decision_id, dc, ec)

    def test_aligned(self):
        report = self._report("d1", 0.5, 0.55)
        assert report.gap_type == "aligned"
        assert report.gap < 0.15

    def test_intuition_when_dc_beats_ec(self):
        report = self._report("d2", 0.9, 0.3)
        assert report.gap_type == "intuition"
        assert report.gap == pytest.approx(0.6)

    def test_analysis_paralysis_when_ec_beats_dc(self):
        report = self._report("d3", 0.3, 0.9)
        assert report.gap_type == "analysis_paralysis"

    def test_confusion_when_gap_exactly_threshold(self):
        # gap == 0.15 is not < 0.15 and neither side strictly exceeds by > 0.15
        report = self._report("d4", 0.65, 0.5)
        assert report.gap == pytest.approx(0.15)
        assert report.gap_type == "confusion"


class TestHistoryAndAverages:
    def test_report_appends_and_updates_averages(self):
        engine = DualConfidence()
        dc_c = lambda s: DecisionConfidence(score=s, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0)
        ec_c = lambda s: ExplanationConfidence(score=s, causal_coherence=0, evidence_completeness=0, theory_support=0, falsifiability=0)
        engine.report("a", dc_c(0.9), ec_c(0.9))
        engine.report("b", dc_c(0.3), ec_c(0.3))
        assert engine._total_reports == 2
        assert engine.average_decision_confidence == 0.6
        assert engine.average_gap == pytest.approx(0.0)
        assert engine.dominant_gap_type == "aligned"

    def test_history_capped(self):
        engine = DualConfidence()
        dc = DecisionConfidence(score=0.5, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0)
        ec = ExplanationConfidence(score=0.5, causal_coherence=0, evidence_completeness=0, theory_support=0, falsifiability=0)
        for i in range(250):
            engine.report(f"d{i}", dc, ec)
        assert len(engine._report_history) == 200

    def test_gap_trend_widening(self):
        engine = DualConfidence()
        dc_c = lambda s: DecisionConfidence(score=s, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0)
        ec_c = lambda s: ExplanationConfidence(score=s, causal_coherence=0, evidence_completeness=0, theory_support=0, falsifiability=0)
        for i in range(5):
            engine.report(f"early{i}", dc_c(0.5), ec_c(0.5))
        for i in range(5):
            engine.report(f"late{i}", dc_c(0.9), ec_c(0.1))
        assert engine.get_recent_gap_trend(window=10) == "widening"

    def test_gap_trend_insufficient_data(self):
        engine = DualConfidence()
        assert engine.get_recent_gap_trend(window=10) == "insufficient_data"


class TestSerialization:
    def test_to_dict_keys(self):
        engine = DualConfidence()
        d = engine.to_dict()
        assert d["total_reports"] == 0
        assert d["dominant_gap_type"] == "unknown"
        assert d["gap_trend"] == "insufficient_data"
        assert d["recent_reports"] == []
        assert set(d) == {
            "total_reports", "average_decision_confidence",
            "average_explanation_confidence", "average_gap",
            "dominant_gap_type", "gap_trend", "recent_reports",
        }

    def test_report_has_timestamp(self):
        dc = DecisionConfidence(score=0.5, predictive_accuracy=0, option_clarity=0, familiarity=0, urgency=0)
        ec = ExplanationConfidence(score=0.5, causal_coherence=0, evidence_completeness=0, theory_support=0, falsifiability=0)
        report = ConfidenceReport(decision_id="x", decision_confidence=dc, explanation_confidence=ec, gap=0.0, gap_type="aligned")
        assert report.timestamp > 0