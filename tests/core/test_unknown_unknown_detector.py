"""Contract tests for telos/core/curiosity/unknown_unknown_detector.py.

UnknownUnknownDetector observes prediction-vs-observation residuals, classifies
them against known error patterns, clusters persistent unknowns, and promotes
persistent novel clusters into New Questions. The detect() method is the
pipeline-facing entry point.
"""
import numpy as np

from telos.core.curiosity.unknown_unknown_detector import (
    UnknownUnknownDetector,
    NewQuestion,
    NoveltyCluster,
    Residual,
    ResidualClass,
)


class _Obs:
    def __init__(self, state):
        self.state = state


class TestDataclasses:
    def test_residual_defaults(self):
        r = Residual(cycle=1, feature_name="f", predicted=0.0, observed=1.0,
                     magnitude=1.0, residual_class=ResidualClass.UNKNOWN_UNKNOWN)
        assert r.cluster_id is None
        assert r.novelty_score == 0.0

    def test_novelty_cluster_mean_residual_and_age(self):
        c = NoveltyCluster(
            id="c",
            residuals=[
                Residual(1, "f", 0.0, 2.0, 2.0, ResidualClass.UNKNOWN_UNKNOWN),
                Residual(5, "f", 0.0, 4.0, 4.0, ResidualClass.UNKNOWN_UNKNOWN),
            ],
        )
        assert c.mean_residual == 3.0
        assert c.age_cycles == 4

    def test_empty_cluster_mean_residual_is_zero(self):
        c = NoveltyCluster(id="c")
        assert c.mean_residual == 0.0
        assert c.age_cycles == 0

    def test_new_question_defaults(self):
        q = NewQuestion(id="uq_1_0", source_cluster_id="c", question_text="q",
                        feature_names=["f"], residual_magnitude=1.0,
                        formed_at_cycle=1)
        assert q.answered is False
        assert q.answer_summary == ""
        assert q.dismissed is False


class TestResidualClassification:
    def test_unknown_feature_is_unknown_unknown(self):
        d = UnknownUnknownDetector()
        assert d._classify_residual("f", 1.0) == ResidualClass.UNKNOWN_UNKNOWN

    def test_learned_pattern_matches_known_known(self):
        d = UnknownUnknownDetector()
        d.learn_pattern("f", 1.0)
        assert d._classify_residual("f", 1.0) == ResidualClass.KNOWN_KNOWN

    def test_nearby_unknown_bucket_is_known_unknown(self):
        d = UnknownUnknownDetector()
        d.learn_pattern("f", 1.0)
        assert d._classify_residual("f", 1.2) == ResidualClass.KNOWN_UNKNOWN

    def test_far_residual_stays_unknown_unknown(self):
        d = UnknownUnknownDetector()
        d.learn_pattern("f", 1.0)
        assert d._classify_residual("f", 9.0) == ResidualClass.UNKNOWN_UNKNOWN

    def test_pattern_key_discretizes_to_one_decimal(self):
        d = UnknownUnknownDetector()
        assert d._make_pattern_key("f", 1.05) == "f:1.0"
        assert d._make_pattern_key("g", 3.47) == "g:3.5"


class TestNoveltyScore:
    def test_unknown_unknown_novelty_is_high(self):
        d = UnknownUnknownDetector()
        assert d._compute_novelty("f", 2.0, ResidualClass.UNKNOWN_UNKNOWN) >= 0.8

    def test_known_known_novelty_is_zero_after_feature_seen(self):
        d = UnknownUnknownDetector()
        # First sighting of a feature carries the +0.2 novelty boost.
        assert d._compute_novelty("f", 0.0, ResidualClass.KNOWN_KNOWN) == 0.2
        # Once the feature has been observed, a known-known residual adds none.
        d.record_observation(1, {"f": 0.0}, {"f": 0.0})
        assert d._compute_novelty("f", 0.0, ResidualClass.KNOWN_KNOWN) == 0.0

    def test_novelty_respects_class_base(self):
        d = UnknownUnknownDetector()
        assert d._compute_novelty("f", 1.0, ResidualClass.UNKNOWN_KNOWN) >= 0.5
        assert d._compute_novelty("f", 1.0, ResidualClass.KNOWN_UNKNOWN) >= 0.3


class TestRecordObservation:
    def test_missing_prediction_is_unknown_unknown(self):
        d = UnknownUnknownDetector()
        residuals = d.record_observation(1, {"a": 0.0}, {"b": 2.0})
        classes = {r.feature_name: r.residual_class for r in residuals}
        assert classes["b"] == ResidualClass.UNKNOWN_UNKNOWN
        assert classes["a"] == ResidualClass.KNOWN_UNKNOWN
        assert d._total_residuals == 2

    def test_unknown_unknowns_feed_clusters(self):
        d = UnknownUnknownDetector()
        d.record_observation(1, {"a": 0.0}, {"b": 2.0})
        clusters = list(d._clusters.values())
        assert len(clusters) == 1
        assert clusters[0].residuals[0].feature_name == "b"

    def test_history_is_bounded(self):
        d = UnknownUnknownDetector()
        for cycle in range(150):
            d.record_observation(cycle, {"a": 0.0}, {"b": 1.0})
        assert len(d._residual_history) <= d._max_history


class TestLearnPattern:
    def test_new_pattern_registered(self):
        d = UnknownUnknownDetector()
        d.learn_pattern("f", 1.0)
        assert d.known_pattern_count == 1
        assert "f:1.0" in d._known_patterns

    def test_relearn_updates_stats(self):
        d = UnknownUnknownDetector()
        d.learn_pattern("f", 1.0)
        d.learn_pattern("f", 1.0)
        pat = d._known_patterns["f:1.0"]
        assert pat["samples"] == 2
        assert d.known_pattern_count == 1


class TestPromotion:
    def test_promotes_persistent_cluster_to_question(self):
        d = UnknownUnknownDetector(persistence_threshold=3, novelty_threshold=0.7)
        promo = []
        for cycle in range(1, 6):
            d.record_observation(cycle, {"a": 0.0}, {"b": 2.0})
            promo.extend(d.promote_to_questions(cycle))
        assert len(promo) == 1
        q = promo[0]
        assert isinstance(q, NewQuestion)
        assert q.id == "uq_4_0"
        assert q.feature_names == ["b"]
        assert q.formed_at_cycle == 4
        assert d.unknown_unknown_count == 1
        assert d._total_new_questions == 1

    def test_cluster_is_elevated_after_promotion(self):
        d = UnknownUnknownDetector(persistence_threshold=3)
        for cycle in range(1, 6):
            d.record_observation(cycle, {"a": 0.0}, {"b": 2.0})
            d.promote_to_questions(cycle)
        cluster = next(iter(d._clusters.values()))
        assert cluster.elevated_to_question is True

    def test_persistent_cluster_question_wording(self):
        d = UnknownUnknownDetector(persistence_threshold=1)
        for cycle in range(1, 3):
            d.record_observation(cycle, {"a": 0.0}, {"b": 2.0})
            d.promote_to_questions(cycle)
        q = d.get_unanswered_questions()[0]
        assert q.question_text.startswith("Why does feature 'b'")

    def test_unanswered_questions_after_promotion(self):
        d = UnknownUnknownDetector(persistence_threshold=3)
        for cycle in range(1, 6):
            d.record_observation(cycle, {"a": 0.0}, {"b": 2.0})
            d.promote_to_questions(cycle)
        unanswered = d.get_unanswered_questions()
        assert len(unanswered) == 1
        assert unanswered[0].answered is False

    def test_no_promotion_below_persistence(self):
        d = UnknownUnknownDetector(persistence_threshold=5)
        for cycle in range(1, 4):
            d.record_observation(cycle, {"a": 0.0}, {"b": 2.0})
        assert d.promote_to_questions(3) == []


class TestDetect:
    def test_detect_returns_first_question_dict(self):
        d = UnknownUnknownDetector(persistence_threshold=2)
        result = None
        for cycle in range(1, 5):
            result = d.detect(_Obs(np.array([3.0, 0.0])), cycle)
            if result is not None:
                break
        assert result is not None
        assert set(result.keys()) == {"question", "id", "features", "residual_magnitude"}
        assert result["features"] in (["state_dim_0"], ["state_dim_1"])
        assert result["id"].startswith("uq_")
        assert result["question"].startswith("Why does feature 'state_dim_")
        assert result["residual_magnitude"] >= 0

    def test_detect_returns_none_without_state(self):
        d = UnknownUnknownDetector()
        assert d.detect(object(), 1) is None
        assert d.detect(_Obs(None), 1) is None

    def test_detect_noop_on_nonfinite_state(self):
        d = UnknownUnknownDetector()
        assert d.detect(_Obs(np.array([np.nan, np.inf])), 1) is None


class TestSerialization:
    def test_to_dict_shape(self):
        d = UnknownUnknownDetector()
        d.record_observation(1, {"a": 0.0}, {"b": 2.0})
        d.promote_to_questions(1)
        report = d.to_dict()
        assert report["total_residuals"] == 2
        assert report["known_patterns_count"] == 0
        assert "active_clusters" in report
        assert "unanswered_questions" in report
        assert "total_unknown_unknowns" in report