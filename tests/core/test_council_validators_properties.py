"""
Hypothesis property-based tests for Council validators (Λ2.1 / Λ6.5).

Properties:
  V1 (EvidenceProvenanceValidator): inquiry intent types always PASS — never
     penalised for not producing a world-changing action.
  V2 (EvidenceProvenanceValidator): stagnation-exempt recovery types always PASS
     — they are the designed escape from falsification.
  V3 (EvidenceProvenanceValidator): a non-inquiry, non-recovery intent type with
     consecutive_no_action ≥ FALSIFICATION_DISSENT_AFTER dissents (passed=False).
  V4 (RealityValidator): a state containing NaN/Inf ⇒ passed=False, confidence < 0.
  V5 (RealityValidator): a well-formed finite state/action ⇒ PASS.
  V6 (RealityValidator): huge action norm ⇒ passed=False.
"""
from unittest.mock import MagicMock

from hypothesis import given, strategies as st, settings, HealthCheck
import numpy as np
import pytest

from telos.core.council.base import ValidationSignal
from telos.core.council.validators.evidence import (
    EvidenceProvenanceValidator, FALSIFICATION_DISSENT_AFTER, _INQUIRY_TYPES,
)
from telos.core.council.validators.reality import RealityValidator
from telos.core.governance.recovery_types import STAGNATION_EXEMPT_RECOVERY_TYPES
from telos.intent_ir import IntentIR
from telos.world.world import World


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_tracker(falsified: bool, gap: float = 0.0, has_history: bool = True):
    m = MagicMock()
    m.currently_falsified.return_value = falsified
    if has_history:
        m.gap_history = [gap]
        m.recent_mean_gap = gap
    else:
        m.gap_history = []
        m.recent_mean_gap = 0.0
    tracker = MagicMock()
    tracker.model.return_value = m
    return tracker


def _make_ctx(intent_type, tracker, consecutive_no_action=0, total_no_action=0,
              recent_blocks=0, cycle_count=5):
    # Use dict so .get() works (as validator expects)
    return {
        "reality_gap_tracker": tracker,
        "cycle_count": cycle_count,
        "intent_history": {
            "consecutive_no_action": consecutive_no_action,
            "total_no_action": total_no_action,
            "recent_blocks": recent_blocks,
        },
    }


def _make_world(state=None):
    return World(state=np.zeros(3) if state is None else state)


def _make_intent(intent_type="navigate", blocked=False):
    return IntentIR(intent_type=intent_type, confidence=0.8,
                    params={"blocked": blocked} if blocked else {})


# ── EvidenceProvenanceValidator properties ────────────────────────────────

@settings(max_examples=150, suppress_health_check=list(HealthCheck))
@given(itype=st.sampled_from(sorted(_INQUIRY_TYPES)))
def test_inquiry_types_never_penalised(itype):
    """V1: inquiry intent types always PASS regardless of falsification record."""
    val = EvidenceProvenanceValidator()
    tracker = _make_tracker(falsified=True, gap=2.88)
    ctx = _make_ctx(itype, tracker, consecutive_no_action=10, total_no_action=50)
    sig = val.validate(_make_world(), _make_intent(itype), context=ctx)
    assert sig.passed is True
    assert sig.confidence > 0.0


@settings(max_examples=150, suppress_health_check=list(HealthCheck))
@given(itype=st.sampled_from(sorted(STAGNATION_EXEMPT_RECOVERY_TYPES)))
def test_recovery_types_never_penalised(itype):
    """V2: stagnation-exempt recovery types always PASS."""
    val = EvidenceProvenanceValidator()
    tracker = _make_tracker(falsified=True, gap=2.88)
    ctx = _make_ctx(itype, tracker, consecutive_no_action=10, total_no_action=50)
    sig = val.validate(_make_world(), _make_intent(itype), context=ctx)
    assert sig.passed is True
    assert sig.confidence > 0.0


@settings(max_examples=150, suppress_health_check=list(HealthCheck))
@given(
    itype=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in _INQUIRY_TYPES and s not in STAGNATION_EXEMPT_RECOVERY_TYPES
    ),
    consecutive=st.integers(min_value=0, max_value=10),
)
def test_falsified_loop_dissents(itype, consecutive):
    """V3: consecutive_no_action ≥ FALSIFICATION_DISSENT_AFTER ⇒ dissent (passed=False)."""
    val = EvidenceProvenanceValidator()
    tracker = _make_tracker(falsified=False)
    ctx = _make_ctx(itype, tracker, consecutive_no_action=consecutive)
    sig = val.validate(_make_world(), _make_intent(itype), context=ctx)
    if consecutive >= FALSIFICATION_DISSENT_AFTER:
        assert sig.passed is False
        assert sig.confidence < 0.0
        assert itype in sig.reason
    else:
        # not yet dissenting (unless other conditions trigger)
        assert sig.confidence > -1.0


@settings(max_examples=100, suppress_health_check=list(HealthCheck))
@given(
    falsified=st.booleans(),
    gap=st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=10.0),
)
def test_model_falsification_recorded_when_dissent(falsified, gap):
    """The model falsification flag flows into signal metadata when it causes dissent."""
    val = EvidenceProvenanceValidator()
    tracker = _make_tracker(falsified=falsified, gap=gap)
    # Need consecutive_no_action >= 3 to trigger dissent
    ctx = _make_ctx("navigate", tracker, consecutive_no_action=5)
    sig = val.validate(_make_world(), _make_intent("navigate"), context=ctx)
    if falsified:
        assert sig.metadata.get("model_falsified") is True
    else:
        # When not falsified, metadata only has intent_type (no model_falsified key)
        assert "model_falsified" not in sig.metadata or sig.metadata.get("model_falsified") is False


# ── RealityValidator properties ───────────────────────────────────────────

@settings(max_examples=150, suppress_health_check=list(HealthCheck))
@given(
    nan_count=st.integers(min_value=0, max_value=5),
    inf_count=st.integers(min_value=0, max_value=5),
)
def test_reality_validator_nan_inf_blocks(nan_count, inf_count):
    """V4: NaN/Inf in world state ⇒ passed=False, negative confidence."""
    state = np.zeros(6, dtype=float)
    total_bad = min(nan_count + inf_count, 6)
    for k in range(nan_count):
        if k < 6:
            state[k] = np.nan
    for k in range(nan_count, nan_count + inf_count):
        if k < 6:
            state[k] = np.inf
    val = RealityValidator()
    sig = val.validate(_make_world(state), _make_intent("navigate"))
    has_bad = total_bad > 0
    if has_bad:
        assert sig.passed is False
        assert sig.confidence < 0.0
        assert sig.evidence_weight > 0.0
    else:
        assert sig.passed is True


@settings(max_examples=150, suppress_health_check=list(HealthCheck))
@given(
    x=st.floats(allow_nan=False, allow_infinity=False, min_value=-100.0, max_value=100.0),
    y=st.floats(allow_nan=False, allow_infinity=False, min_value=-100.0, max_value=100.0),
    norm=st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=150.0),
)
def test_reality_validator_action_norm_bounds(x, y, norm):
    """V5/V6: finite state + small action ⇒ PASS; huge action norm ⇒ passed=False."""
    state = np.array([x, y, 0.0, 0.0, 0.0, 0.0])
    val = RealityValidator()
    intent = _make_intent("navigate")
    intent.params["action_vector"] = np.array([norm, 0.0])
    sig = val.validate(_make_world(state), intent)
    if norm > 100.0:
        assert sig.passed is False
        assert sig.confidence < 0.0
    else:
        assert sig.passed is True


def test_reality_validator_none_intent_passes():
    """RealityValidator with no intent abstains (passes)."""
    val = RealityValidator()
    sig = val.validate(_make_world(), None)
    assert sig.passed is True


def test_evidence_validator_none_intent_passes():
    """EvidenceProvenanceValidator with no intent abstains (passes)."""
    val = EvidenceProvenanceValidator()
    tracker = _make_tracker(falsified=False)
    ctx = _make_ctx("navigate", tracker)
    sig = val.validate(_make_world(), None, context=ctx)
    assert sig.passed is True