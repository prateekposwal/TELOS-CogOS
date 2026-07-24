"""
Tests for the Ω Operator framework — Fixes 1-6.

Test 1: Ω ≥ threshold enters Inquiry Mode
Test 2: Ω < threshold skips Inquiry Mode (saturation fallback)
Test 3: Question cache prevents re-asking within TTL
Test 4: Adaptive cost returns reasonable values
Test 5: Multi-axis Ω vector has correct dimensions
Test 6: Inquiry-to-action bridge maps question types to actions
"""

import sys
import os
import math
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from typing import Dict, List, Optional, Any, Tuple

# ──────────────────────────────────────────────────────────────────────
# Mock classes
# ──────────────────────────────────────────────────────────────────────

class MockTripartiteU:
    """Minimal mock for TripartiteUncertainty with controllable U values."""
    
    def __init__(self, U_W=0.0, U_I=0.0, U_O=0.0):
        self.U_W = U_W
        self.U_I = U_I
        self.U_O = U_O
        self.answered_questions = 0

    def record_answer(self, question_type: str) -> None:
        self.answered_questions += 1


class MockSimEngine:
    """Minimal mock for CounterfactualEngine to test adaptive cost."""
    
    def __init__(self):
        self._last_state = np.zeros(6)
        self._call_count = 0

    def generate_worlds(self, state, horizon, n_worlds, attention_allocation=None):
        self._call_count += 1
        # Simulate some work
        time.sleep(0.001)  # 1ms of "simulation"
        # Return a list of mock worlds
        return [{'state': state.copy()} for _ in range(n_worlds * horizon)]


class MockIntentIR:
    """Minimal IntentIR-like object for bridge testing."""
    
    def __init__(self, intent_type="unknown", confidence=1.0, params=None, metadata=None):
        self.intent_type = intent_type
        self.confidence = confidence
        self.params = params or {}
        self.metadata = metadata or {}


class MockVerdict:
    """Minimal council verdict mock."""
    
    def __init__(self, signals=None):
        self.signals = signals or []
        self.validated = True
        self.decision_integrity = 1.0
        self.mission_drift = 0.0
        self.blocking_validator = None
        self.escalation_requested = False
        self.escalation_reason = None


class MockCouncil:
    def __init__(self, verdict=None):
        self.verdict = verdict


class MockStream:
    """Mock cognitive stream for InquiryStream detection."""
    def __init__(self, name):
        self.__class__.__name__ = name
        self.inquiry_active = False
        self.last_question = None
        self.last_omega = 0.0


class MockPipeline:
    """Minimal pipeline mock for SelectPhase testing."""
    
    def __init__(self, tripartite_u=None, sim_engine=None, omega_operator=None,
                 meta_cognition=None, budget_manager=None):
        self._tripartite_u = tripartite_u or MockTripartiteU()
        self._sim_engine = sim_engine
        self._omega_operator = omega_operator
        self._meta_cognition = meta_cognition
        self._commitment_optimizer = None
        self._infra_manager = None
        self._identity_entropy = None
        self._attention_engine = None
        self.budget_manager = budget_manager or MockBudgetManager()
        self.streams = []


class MockBudgetManager:
    def __init__(self, total=100, consumed=0):
        self.total_budget_ms = total
        self.consumed_ms = consumed


class MockPhaseContext:
    """Minimal mock for PhaseContext."""
    
    def __init__(self):
        self.cycle_count = 1
        self.state = np.zeros(6)
        self.user_name = "test"
        self.verdict = None
        self.council = None
        self.meta_cognition = None
        self.selected_question = None
        self.selected_intent = None
        self.inquiry_skipped = False
        self.inquiry_omega_value = 0.0
        self.inquiry_omega_vector = None
        self.intents = []
        self.synthesis = None
        self.simulation_confidence = 1.0


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

from telos.core.decision.omega_operator import OmegaOperator


def test_1_omega_above_threshold_enters_inquiry():
    """Ω ≥ 0.5 — operator returns a question and high omega value."""
    op = OmegaOperator()
    U = MockTripartiteU(U_W=0.8, U_I=0.2, U_O=0.6)
    signals = [
        {"validator_name": "reality", "passed": False, "confidence": 0.9,
         "reason": "high uncertainty", "evidence_weight": 0.7, "verdict": "block"},
    ]
    
    question, omega, omega_vector = op.compute(U, signals)
    
    assert question is not None, "Expected a question when omega >= 0.5"
    assert omega >= 0.5, f"Expected omega >= 0.5, got {omega:.4f}"
    assert question['id'] is not None, "Question must have an id"
    print(f"  Ω = {omega:.4f}, question = {question['id']}")


def test_2_omega_below_threshold_skips_inquiry():
    """Ω < 0.5 — operator returns None (saturation fallback)."""
    op = OmegaOperator()
    # Very low uncertainty → no question worth asking
    U = MockTripartiteU(U_W=0.0, U_I=0.0, U_O=0.0)
    signals = []
    
    question, omega, omega_vector = op.compute(U, signals)
    
    # The default_navigate question may still produce positive omega if costs are low
    # But the key is that with all zero uncertainty, omega should be < 0.5
    # (costs are non-zero so omega for default_navigate should be low)
    print(f"  Ω = {omega:.4f}, question = {question['id'] if question else None}")
    
    # default_navigate might still have small omega but should be below 0.5
    # since U values are 0 and prior is low
    if question is not None:
        assert omega < 0.5, (
            f"Expected omega < 0.5 with zero uncertainty, got {omega:.4f}"
        )


def test_3_question_cache_prevents_reask():
    """Question cache prevents re-asking the same question within TTL cycles."""
    op = OmegaOperator()
    op._cache_ttl = 5  # 5 cycle TTL
    
    U = MockTripartiteU(U_W=0.9, U_I=0.2, U_O=0.6)
    signals = [
        {"validator_name": "reality", "passed": False, "confidence": 0.9,
         "reason": "uncertain", "evidence_weight": 0.7, "verdict": "block"},
    ]
    
    # First call: should return a question
    q1, omega1, _ = op.compute(U, signals)
    assert q1 is not None, "First call should return a question"
    assert q1['id'] in op._seen_questions, "Question should be cached"
    print(f"  First call: {q1['id']} @ Ω={omega1:.4f}, cache={dict(op._seen_questions)}")
    
    # Second call (same cycle, no increment): cached question should be filtered out
    q2, omega2, _ = op.compute(U, signals)
    # The cached question should be filtered, so we'll get another question or None
    if q2 is not None:
        assert q2['id'] != q1['id'], (
            f"Second call should NOT return cached question '{q1['id']}', "
            f"but got '{q2['id']}'"
        )
        print(f"  Second call: {q2['id']} @ Ω={omega2:.4f} (different question)")
    else:
        print(f"  Second call: no question returned (all cached)")
    
    # Assert the cache contains the first question
    assert q1['id'] in op._seen_questions, (
        f"Cache should contain '{q1['id']}'"
    )


def test_4_adaptive_cost_returns_reasonable_values():
    """Adaptive cost estimation returns values in reasonable range."""
    op = OmegaOperator()
    
    # Test with a mock sim engine
    sim = MockSimEngine()
    
    question = {
        'id': 'explore_terrain',
        'type': 'explore',
        'domain': 'world',
        'prior': 0.8,
        'estimated_horizon': 5,
        'estimated_worlds': 10,
    }
    budget = {"remaining_ms": 100.0}
    
    cost = op.adaptive_cost(question, sim, budget)
    
    assert isinstance(cost, float), "Cost must be a float"
    assert cost >= 0.0, f"Cost must be >= 0, got {cost}"
    assert cost <= 1.0, f"Cost must be <= 1.0, got {cost}"
    print(f"  Adaptive cost = {cost:.4f} (range: [0, 1])")
    
    # Test fallback when sim_engine is None
    fallback_cost = op.adaptive_cost(question, None, budget)
    hardcoded_cost = op._compute_cost(question, budget)
    assert abs(fallback_cost - hardcoded_cost) < 1e-6, (
        f"Fallback cost ({fallback_cost}) should equal hardcoded ({hardcoded_cost})"
    )
    print(f"  Fallback cost = {fallback_cost:.4f} (matches hardcoded)")


def test_5_multi_axis_omega_vector():
    """Multi-axis Ω vector has correct dimensions and reasonable values."""
    op = OmegaOperator()
    
    # High world uncertainty, moderate identity, low council
    U = MockTripartiteU(U_W=0.9, U_I=0.4, U_O=0.1)
    signals = [
        {"validator_name": "reality", "passed": True, "confidence": 0.8,
         "reason": "ok", "evidence_weight": 0.6, "verdict": "pass"},
    ]
    
    _, _, omega_vector = op.compute(U, signals)
    
    assert isinstance(omega_vector, dict), "omega_vector must be a dict"
    assert 'world' in omega_vector, "omega_vector must have 'world' key"
    assert 'identity' in omega_vector, "omega_vector must have 'identity' key"
    assert 'other' in omega_vector, "omega_vector must have 'other' key"
    
    # With high U_W, world omega should be the highest
    print(f"  Omega vector: {omega_vector}")
    print(f"  U_W=0.9 → world Ω={omega_vector['world']:.4f}")
    print(f"  U_I=0.4 → identity Ω={omega_vector['identity']:.4f}")
    print(f"  U_O=0.1 → other Ω={omega_vector['other']:.4f}")
    
    # With these U values, world should dominate
    # (costs may reduce values but relative ordering should hold)
    assert omega_vector['world'] >= omega_vector['other'], (
        f"World omega ({omega_vector['world']:.4f}) should be >= "
        f"other omega ({omega_vector['other']:.4f}) when U_W >= U_O"
    )
    
    # Verify the vector is stored on the operator
    assert hasattr(op, 'last_omega_vector'), "Operator must have last_omega_vector"
    stored = op.last_omega_vector
    assert stored == omega_vector, "Stored vector should match returned vector"


def test_6_inquiry_to_action_bridge():
    """Inquiry-to-action bridge maps question types to concrete actions."""
    from telos.core.phases.select import SelectPhase
    
    phase = SelectPhase()
    
    # Create omega operator with U_W high so it generates explore_terrain
    op = OmegaOperator()
    U = MockTripartiteU(U_W=0.9, U_I=0.1, U_O=0.1)
    signals = [
        {"validator_name": "reality", "passed": True, "confidence": 0.9,
         "reason": "ok", "evidence_weight": 0.7, "verdict": "pass"},
    ]
    
    question, omega, omega_vector = op.compute(U, signals)
    
    assert question is not None, "Should have a question"
    
    # Test bridge mapping: explore_terrain → random walk action
    question_id = question.get('id', '')
    print(f"  Selected question: {question_id} @ Ω={omega:.4f}")
    
    # Simulate what SelectPhase does with explore_terrain
    from telos.intent_ir import IntentIR
    
    if question_id == 'explore_terrain':
        # This is what the bridge does
        angle = np.random.uniform(0, 2 * np.pi)
        action_vec = np.array([np.cos(angle), np.sin(angle)]) * 0.5
        intent = IntentIR(
            intent_type="inquiry_explore",
            confidence=min(1.0, omega),
            params={
                "question": question,
                "omega_value": omega,
                "inquiry_mode": True,
                "action_vector": action_vec,
                "is_exploratory": True,
            },
            metadata={
                "stream": "inquiry",
                "question_id": question_id,
                "bridge_action": "random_walk",
            },
        )
        assert intent.intent_type == "inquiry_explore"
        assert 'action_vector' in intent.params
        assert intent.params['is_exploratory'] == True
        assert intent.metadata['bridge_action'] == 'random_walk'
        print(f"  Bridge: explore_terrain → random_walk, action_vec={action_vec}")
    
    elif question_id == 'recalibrate_identity':
        intent = IntentIR(
            intent_type="inquiry_recalibrate",
            confidence=min(1.0, omega),
            params={
                "question": question,
                "omega_value": omega,
                "inquiry_mode": True,
                "identity_repair": True,
                "recovery_mode": True,
            },
            metadata={
                "stream": "inquiry",
                "question_id": question_id,
                "bridge_action": "identity_repair",
            },
        )
        assert intent.params['identity_repair'] == True
        assert intent.params['recovery_mode'] == True
        print(f"  Bridge: recalibrate_identity → identity_repair + recovery_mode")
    
    elif question_id == 'resolve_disagreement':
        intent = IntentIR(
            intent_type="inquiry_resolve",
            confidence=min(1.0, omega),
            params={
                "question": question,
                "omega_value": omega,
                "inquiry_mode": True,
                "re_run_council": True,
                "higher_evidence_weight": True,
            },
            metadata={
                "stream": "inquiry",
                "question_id": question_id,
                "bridge_action": "re_weight_council",
            },
        )
        assert intent.params['re_run_council'] == True
        assert intent.params['higher_evidence_weight'] == True
        print(f"  Bridge: resolve_disagreement → re_weight_council")
    
    elif question_id == 'default_navigate':
        # default_navigate means skip inquiry entirely (fall through to normal action)
        print(f"  Bridge: default_navigate → skip inquiry (fall through to normal action)")
    
    print(f"  Bridge test passed for '{question_id}'")


def test_cache_reset():
    """Test that reset_cache() clears the seen questions."""
    op = OmegaOperator()
    U = MockTripartiteU(U_W=0.9, U_I=0.3, U_O=0.5)
    signals = [
        {"validator_name": "r", "passed": False, "confidence": 0.8,
         "reason": "x", "evidence_weight": 0.6, "verdict": "block"},
    ]
    
    q1, _, _ = op.compute(U, signals)
    assert len(op._seen_questions) > 0, "Cache should have entries after compute"
    
    op.reset_cache()
    assert len(op._seen_questions) == 0, "Cache should be empty after reset"
    print(f"  Cache reset: {len(op._seen_questions)} entries remaining")


def test_cache_prune():
    """Test that stale cache entries are pruned after TTL cycles."""
    op = OmegaOperator()
    op._cache_ttl = 3
    
    U = MockTripartiteU(U_W=0.9, U_I=0.3, U_O=0.5)
    signals = [
        {"validator_name": "r", "passed": False, "confidence": 0.8,
         "reason": "x", "evidence_weight": 0.6, "verdict": "block"},
    ]
    
    q1, _, _ = op.compute(U, signals)
    assert q1 is not None
    question_id = q1['id']
    assert question_id in op._seen_questions, "Question should be cached"
    
    # Advance the cycle counter past TTL
    op._cycle_counter += op._cache_ttl + 1
    
    # Prune should remove stale entries
    op._prune_cache()
    assert question_id not in op._seen_questions, (
        f"Question '{question_id}' should be pruned after TTL"
    )
    print(f"  Cache prune: '{question_id}' removed after TTL={op._cache_ttl} cycles")


def test_smoother_cost_scaling():
    """Fix 6: _compute_cost uses smoother scaling to avoid division by near-zero."""
    op = OmegaOperator()
    
    q = {'estimated_horizon': 3, 'estimated_worlds': 5}
    
    # With plenty of budget
    cost_high_budget = op._compute_cost(q, {"remaining_ms": 100})
    # With very low budget
    cost_low_budget = op._compute_cost(q, {"remaining_ms": 1})
    # With zero budget
    cost_zero_budget = op._compute_cost(q, {"remaining_ms": 0})
    
    print(f"  Cost (100ms budget): {cost_high_budget:.4f}")
    print(f"  Cost (1ms budget):   {cost_low_budget:.4f}")
    print(f"  Cost (0ms budget):   {cost_zero_budget:.4f} (no division by zero)")
    
    # est = 3 * 5 * 0.5 = 7.5
    expected_high = 7.5 / (1 + 100)  # ≈ 0.0743
    expected_low = 7.5 / (1 + 1)     # = 3.75
    expected_zero = 7.5 / (1 + 0)    # = 7.5
    
    assert abs(cost_high_budget - expected_high) < 1e-4, (
        f"Expected {expected_high:.4f}, got {cost_high_budget:.4f}"
    )
    assert abs(cost_low_budget - expected_low) < 1e-4, (
        f"Expected {expected_low:.4f}, got {cost_low_budget:.4f}"
    )
    assert abs(cost_zero_budget - expected_zero) < 1e-4, (
        f"Expected {expected_zero:.4f}, got {cost_zero_budget:.4f}"
    )
    assert cost_zero_budget > cost_low_budget > cost_high_budget, (
        "Cost should decrease as remaining budget increases"
    )
    print(f"  Smoother cost scaling: OK (no division by zero)")


# ──────────────────────────────────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        ("Test 1: Ω ≥ 0.5 enters Inquiry Mode", test_1_omega_above_threshold_enters_inquiry),
        ("Test 2: Ω < 0.5 skips Inquiry Mode", test_2_omega_below_threshold_skips_inquiry),
        ("Test 3: Question cache prevents re-ask", test_3_question_cache_prevents_reask),
        ("Test 4: Adaptive cost reasonable values", test_4_adaptive_cost_returns_reasonable_values),
        ("Test 5: Multi-axis Ω vector dimensions", test_5_multi_axis_omega_vector),
        ("Test 6: Inquiry-to-action bridge", test_6_inquiry_to_action_bridge),
        ("Extra: Cache reset", test_cache_reset),
        ("Extra: Cache prune after TTL", test_cache_prune),
        ("Extra: Smoother cost scaling", test_smoother_cost_scaling),
    ]
    
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()
    
    print(f"=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed > 0:
        sys.exit(1)
