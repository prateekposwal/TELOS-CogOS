"""Tests for PatternLibrary — cross-domain pattern storage, matching by
domain-independent signatures, and persistence."""

import numpy as np

from telos.core.pattern.core import (
    PatternLibrary,
    PatternSignature,
    PatternType,
)


def sig(intent="explore", drift="low", integrity="high",
        action="", state_hash=""):
    return PatternSignature(
        state_hash=state_hash,
        intent_type=intent,
        drift_bucket=drift,
        integrity_bucket=integrity,
        action_signature=action,
    )


class TestPatternSignature:
    def test_feature_vector_shape_and_norm(self):
        v = sig().to_feature_vector()
        assert v.shape == (10,)
        assert v.dtype == np.float32
        assert np.linalg.norm(v) == pytest_approx(1.0)

    def test_feature_vector_encodes_buckets(self):
        # vector is unit-normalized, so buckets show up as positional peaks
        v = sig(drift="high", integrity="low").to_feature_vector()
        assert np.argmax(v[:3]) == 2  # high drift bucket
        assert np.argmax(v[3:6]) == 0  # low integrity bucket
        v2 = sig(drift="medium", integrity="medium").to_feature_vector()
        assert np.argmax(v2[:3]) == 1
        assert np.argmax(v2[3:6]) == 1

    def test_empty_action_gives_zero_component(self):
        v = sig(action="").to_feature_vector()
        assert v[7] == 0.0

    def test_unknown_bucket_defaults_to_medium_encoding(self):
        s = sig(drift="extreme", integrity="extreme")
        v = s.to_feature_vector()
        assert np.argmax(v[:3]) == 1  # unknown drift -> medium
        assert np.argmax(v[3:6]) == 1  # unknown integrity -> medium


def pytest_approx(x, rel=1e-5):
    from pytest import approx
    return approx(x, rel=rel)


class TestRecordAndQuery:
    def test_record_returns_id_and_indexes(self):
        lib = PatternLibrary()
        pid = lib.record("grid", PatternType.SUCCESS, sig())
        assert pid.startswith("pat_")
        assert lib.stats()["total_patterns"] == 1
        assert lib.stats()["domains"] == ["grid"]
        assert lib.stats()["by_type"]["success"] == 1

    def test_exact_duplicate_increments_match_count(self):
        lib = PatternLibrary()
        pid1 = lib.record("grid", PatternType.SUCCESS, sig(), outcome_score=0.5)
        pid2 = lib.record("grid", PatternType.SUCCESS, sig(), outcome_score=0.9)
        assert pid1 == pid2
        pat = lib._patterns[pid1]
        assert pat.match_count == 2
        assert pat.outcome_score == pytest_approx(0.7 * 0.5 + 0.3 * 0.9)

    def test_identical_signature_queries_at_cosine_1(self):
        lib = PatternLibrary()
        s = sig()
        lib.record("grid", PatternType.SUCCESS, s)
        results = lib.query(s)
        assert len(results) == 1
        pat, sim = results[0]
        assert pat.action_taken is None
        assert sim == pytest_approx(1.0)

    def test_query_filters_by_domain(self):
        lib = PatternLibrary()
        s = sig()
        lib.record("grid", PatternType.SUCCESS, s)
        lib.record("robotics", PatternType.SUCCESS, s)
        assert len(lib.query(s, domain="grid")) == 1
        assert len(lib.query(s, domain="robotics")) == 1
        assert len(lib.query(s, domain="driving")) == 0

    def test_query_rejects_cosine_below_threshold(self):
        lib = PatternLibrary()
        lib.record("grid", PatternType.SUCCESS, sig())
        different = sig(intent="unrelated", drift="high", integrity="low",
                        state_hash="")
        assert lib.query(different) == []

    def test_query_top_k_limit(self):
        lib = PatternLibrary()
        s = sig()
        for domain in ("a", "b", "c", "d", "e"):
            lib.record(domain, PatternType.SUCCESS, s)
        assert len(lib.query(s, top_k=2)) == 2

    def test_cross_domain_query_excludes_source_domain(self):
        lib = PatternLibrary()
        s = sig()
        lib.record("grid", PatternType.SUCCESS, s)
        lib.record("robotics", PatternType.SUCCESS, s)
        results = lib.cross_domain_query(s, exclude_domain="grid")
        assert len(results) == 1
        assert results[0][0].domain == "robotics"


class TestPatternMetadata:
    def test_signature_from_decision_buckets(self):
        assert PatternLibrary.signature_from_decision(
            di=0.95, md=0.5, intent_type="explore").integrity_bucket == "high"
        assert PatternLibrary.signature_from_decision(
            di=0.6, md=0.5, intent_type="explore").integrity_bucket == "medium"
        assert PatternLibrary.signature_from_decision(
            di=0.2, md=0.5, intent_type="explore").integrity_bucket == "low"
        assert PatternLibrary.signature_from_decision(
            di=0.9, md=0.9, intent_type="explore").drift_bucket == "low"
        assert PatternLibrary.signature_from_decision(
            di=0.9, md=2.0, intent_type="explore").drift_bucket == "medium"
        assert PatternLibrary.signature_from_decision(
            di=0.9, md=4.0, intent_type="explore").drift_bucket == "high"

    def test_get_patterns_by_type(self):
        lib = PatternLibrary()
        lib.record("grid", PatternType.FAILURE, sig(intent="fallback"))
        lib.record("grid", PatternType.SUCCESS, sig())
        failures = lib.get_patterns_by_type(PatternType.FAILURE)
        assert len(failures) == 1
        assert failures[0].pattern_type == PatternType.FAILURE

    def test_domain_summary(self):
        lib = PatternLibrary()
        lib.record("grid", PatternType.SUCCESS, sig(), outcome_score=0.5)
        lib.record("grid", PatternType.FAILURE, sig(intent="other"), outcome_score=0.3)
        summary = lib.get_domain_summary("grid")
        assert summary["domain"] == "grid"
        assert summary["total_patterns"] == 2
        assert summary["by_type"]["success"] == 1
        assert summary["by_type"]["failure"] == 1
        assert summary["avg_outcome"] == pytest_approx(0.4)

    def test_unknown_domain_summary(self):
        lib = PatternLibrary()
        summary = lib.get_domain_summary("none")
        assert summary["total_patterns"] == 0
        assert summary["avg_outcome"] == 0.0


class TestEviction:
    def test_max_patterns_evicts_oldest(self):
        lib = PatternLibrary(max_patterns=3)
        for i, intent in enumerate(("a", "b", "c", "d")):
            lib.record("grid", PatternType.SUCCESS, sig(intent=intent))
        assert lib.stats()["total_patterns"] == 3


class TestPersistence:
    def test_save_load_round_trip(self, tmp_path):
        lib = PatternLibrary()
        lib.record("grid", PatternType.SUCCESS, sig(), action_taken="move",
                   outcome_score=0.8, metadata={"source": "unit"})
        path = str(tmp_path / "patterns.json")
        lib.save(path)
        restored = PatternLibrary(similarity_threshold=0.5)
        restored.load(path)
        assert restored.stats()["total_patterns"] == 1
        pat = restored.get_patterns_by_type(PatternType.SUCCESS)[0]
        assert pat.action_taken == "move"
        assert pat.outcome_score == 0.8
        assert pat.metadata == {"source": "unit"}
        assert pat.signature.intent_type == "explore"
        # load() does NOT restore the serialized threshold (real behavior)
        assert restored._similarity_threshold == 0.5

    def test_load_missing_file_is_noop(self, tmp_path):
        lib = PatternLibrary()
        lib.load(str(tmp_path / "missing.json"))
        assert lib.stats()["total_patterns"] == 0

    def test_loaded_patterns_queryable(self, tmp_path):
        lib = PatternLibrary()
        s = sig()
        lib.record("grid", PatternType.SUCCESS, s)
        path = str(tmp_path / "patterns.json")
        lib.save(path)
        restored = PatternLibrary()
        restored.load(path)
        assert len(restored.query(s)) == 1