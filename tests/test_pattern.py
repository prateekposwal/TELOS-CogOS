"""Tests for PatternLibrary, meta-cognitive ReflectPhase, and adaptive horizon."""

import numpy as np
from telos.core.pattern import PatternLibrary, PatternType, PatternSignature, Pattern
from telos.core.phases.reflect import ReflectPhase


class TestPatternSignature:
    def test_from_decision_high_di_low_md(self):
        sig = PatternLibrary.signature_from_decision(di=0.95, md=0.3, intent_type='move')
        assert sig.drift_bucket == 'low'
        assert sig.integrity_bucket == 'high'
        assert sig.intent_type == 'move'

    def test_from_decision_low_di_high_md(self):
        sig = PatternLibrary.signature_from_decision(di=0.2, md=6.0, intent_type='stop')
        assert sig.drift_bucket == 'high'
        assert sig.integrity_bucket == 'low'

    def test_from_decision_medium(self):
        sig = PatternLibrary.signature_from_decision(di=0.6, md=2.0, intent_type='wait')
        assert sig.drift_bucket == 'medium'
        assert sig.integrity_bucket == 'medium'

    def test_feature_vector_normalized(self):
        sig = PatternSignature(state_hash='test', intent_type='move',
                               drift_bucket='low', integrity_bucket='high')
        vec = sig.to_feature_vector()
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


class TestPatternLibrary:
    def test_record_and_query(self):
        pl = PatternLibrary()
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        pl.record('grid', PatternType.SUCCESS, s1, action_taken='move')
        assert pl.stats()['total_patterns'] == 1

    def test_cross_domain_match(self):
        pl = PatternLibrary(similarity_threshold=0.5)
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        s2 = PatternSignature(state_hash='b', intent_type='track',
                              drift_bucket='low', integrity_bucket='high')
        s3 = PatternSignature(state_hash='c', intent_type='reach',
                              drift_bucket='low', integrity_bucket='high')
        pl.record('grid', PatternType.SUCCESS, s1, action_taken='move', outcome_score=0.9)
        pl.record('football', PatternType.SUCCESS, s2, action_taken='track', outcome_score=0.85)

        # Query from third domain should match both
        hits = pl.cross_domain_query(s3, exclude_domain='robot_arm')
        assert len(hits) == 2

    def test_cross_domain_no_match_for_dissimilar(self):
        pl = PatternLibrary(similarity_threshold=0.5)
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        s4 = PatternSignature(state_hash='d', intent_type='stop',
                              drift_bucket='high', integrity_bucket='low')
        pl.record('grid', PatternType.SUCCESS, s1)
        hits = pl.cross_domain_query(s4, exclude_domain='safety')
        assert len(hits) == 0

    def test_dedup_exact_match(self):
        pl = PatternLibrary()
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        pid1 = pl.record('grid', PatternType.SUCCESS, s1, action_taken='move', outcome_score=0.9)
        pid2 = pl.record('grid', PatternType.SUCCESS, s1, action_taken='move', outcome_score=0.95)
        assert pid1 == pid2
        assert pl.stats()['total_patterns'] == 1
        assert pl._patterns[pid1].match_count == 2

    def test_different_domains_separate(self):
        pl = PatternLibrary()
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        s2 = PatternSignature(state_hash='b', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        pid1 = pl.record('grid', PatternType.SUCCESS, s1)
        pid2 = pl.record('football', PatternType.SUCCESS, s2)
        assert pid1 != pid2
        assert pl.stats()['total_patterns'] == 2

    def test_max_patterns_eviction(self):
        pl = PatternLibrary(max_patterns=3)
        for i in range(5):
            s = PatternSignature(state_hash=str(i), intent_type=f'action_{i}',
                                 drift_bucket='low', integrity_bucket='high')
            pl.record(f'domain_{i}', PatternType.SUCCESS, s)
        assert pl.stats()['total_patterns'] <= 3

    def test_get_domain_summary(self):
        pl = PatternLibrary()
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        s2 = PatternSignature(state_hash='b', intent_type='stop',
                              drift_bucket='high', integrity_bucket='low')
        pl.record('grid', PatternType.SUCCESS, s1, outcome_score=0.9)
        pl.record('grid', PatternType.COUNCIL_BLOCK, s2, outcome_score=0.1)
        summary = pl.get_domain_summary('grid')
        assert summary['total_patterns'] == 2
        assert summary['avg_outcome'] == 0.5

    def test_get_patterns_by_type(self):
        pl = PatternLibrary()
        s1 = PatternSignature(state_hash='a', intent_type='move',
                              drift_bucket='low', integrity_bucket='high')
        s2 = PatternSignature(state_hash='b', intent_type='stop',
                              drift_bucket='high', integrity_bucket='low')
        pl.record('grid', PatternType.SUCCESS, s1)
        pl.record('grid', PatternType.COUNCIL_BLOCK, s2)
        successes = pl.get_patterns_by_type(PatternType.SUCCESS)
        blocks = pl.get_patterns_by_type(PatternType.COUNCIL_BLOCK)
        assert len(successes) == 1
        assert len(blocks) == 1

    def test_all_pattern_types_covered(self):
        expected = {'success', 'failure', 'council_block', 'high_drift',
                    'low_integrity', 'escalation', 'recovery'}
        actual = {t.value for t in PatternType}
        assert actual == expected


class TestReflectPhase:
    def test_name(self):
        rp = ReflectPhase()
        assert rp.name == 'reflect'

    def test_pattern_library_accessible(self):
        rp = ReflectPhase()
        assert rp.pattern_library is not None
        assert rp.pattern_library.stats()['total_patterns'] == 0

    def test_stability_detection_insufficient_data(self):
        rp = ReflectPhase()
        assert rp._detect_stability() == False

    def test_stability_detection_stable(self):
        rp = ReflectPhase()
        rp._di_history = [0.85, 0.86, 0.87, 0.88, 0.89]
        rp._md_history = [0.1, 0.15, 0.12, 0.11, 0.13]
        assert rp._detect_stability() == True

    def test_stability_detection_unstable(self):
        rp = ReflectPhase()
        rp._di_history = [0.9, 0.7, 0.5, 0.3, 0.1]
        rp._md_history = [0.1, 1.0, 2.0, 3.0, 4.0]
        assert rp._detect_stability() == False
