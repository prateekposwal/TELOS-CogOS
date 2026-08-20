"""
TELOS v6 — Phases 2/4/5 tests: EvidenceSource, Reality Gap, Epistemic State.

Phase 2  — EvidenceSource envelope; simulated evidence must NOT equal measured.
Phase 4  — Reality Gap reuses MD per-model; unfalsified != validated; repeated
           failure can reduce fidelity (learning changes authority).
Phase 5  — Epistemic state KNOWN/UNCERTAIN/UNKNOWN/UNMODELED derived from
           existing signals.
"""

import numpy as np

from telos.world.evidence import (
    EvidenceSource, ValidationStatus, EvidenceInfo, measured, assumed,
)
from telos.world.epistemic import (
    EpistemicState, ModelRealityGap, RealityGapTracker, derive_epistemic_state,
)


# ─── Phase 2: EvidenceSource ───────────────────────────────────────────────────

def test_simulated_never_equals_measured():
    sim = assumed(source=EvidenceSource.SIMULATION)   # test_health=1.0, ASSUMED
    mes = measured(source=EvidenceSource.EXTERNAL_SOLVER)  # test_health=1.0, MEASURED
    assert sim.is_assumed and not sim.is_measured
    assert mes.is_measured and not mes.is_assumed
    # The whole point: structurally distinguishable, never conflated.
    assert sim.validation_status != mes.validation_status


def test_evidence_info_defaults():
    e = EvidenceInfo()
    assert e.validation_status == ValidationStatus.UNVALIDATED
    assert not e.is_measured and not e.is_assumed and not e.is_falsified


def test_measured_flag_true_only_for_measured_statuses():
    for st in (ValidationStatus.MEASURED, ValidationStatus.VALIDATED, ValidationStatus.OBSERVED):
        assert EvidenceInfo(source=EvidenceSource.MEASUREMENT, validation_status=st).is_measured
    assert not EvidenceInfo(source=EvidenceSource.SIMULATION, validation_status=ValidationStatus.ASSUMED).is_measured


def test_evidence_to_dict_serializable():
    d = measured().to_dict()
    assert d["source"] == "EXTERNAL_SOLVER"
    assert d["validation_status"] == "MEASURED"
    assert d["is_measured"] is True


# ─── Phase 4: Reality Gap ──────────────────────────────────────────────────────

def test_reality_gap_reuses_md_arithmetic():
    t = RealityGapTracker()
    # predicted != observed exactly as MD = ||pred - obs||
    gap = t.record("m", np.array([0.0, 0.0]), np.array([3.0, 4.0]))
    assert abs(gap - 5.0) < 1e-9
    m = t.model("m")
    assert m.validation_count == 1
    assert abs(m.mean_gap - 5.0) < 1e-9


def test_unfalsified_model_has_no_fidelity():
    t = RealityGapTracker()
    # never tested -> fidelity None (you cannot claim reliability without validation)
    assert t.model_fidelity("untested") is None


def test_validated_model_fidelity():
    t = RealityGapTracker()
    t.record("m", np.array([0.0, 0.0]), np.array([0.1, 0.0]))  # gap=0.1
    t.record("m", np.array([0.0, 0.0]), np.array([0.0, 0.1]))  # gap=0.1
    f = t.model_fidelity("m")
    assert f is not None
    assert abs(f - 0.9) < 1e-6


def test_repeated_failure_reduces_fidelity():
    t = RealityGapTracker()
    # model that keeps predicting wrong -> mean_gap grows -> fidelity falls
    for i in range(10):
        t.record("m", np.array([0.0, 0.0]), np.array([2.0, 2.0]))  # gap ~2.83 each
    low = t.model_fidelity("m")
    assert low is not None
    assert low < 0.2  # clearly low fidelity after repeated failures


def test_falsification_flag_on_large_gap():
    m = ModelRealityGap(model_id="m")
    m.record(np.array([0.0]), np.array([10.0]))  # gap >> threshold
    assert m.is_falsified
    assert m.ever_falsified


def test_reality_gap_tracker_registry():
    t = RealityGapTracker()
    t.record("a", np.array([0.0]), np.array([1.0]))
    t.record("b", np.array([0.0]), np.array([0.0]))
    assert set(t.models.keys()) == {"a", "b"}


# ─── Phase 5: Epistemic State ──────────────────────────────────────────────────

def test_unmodeled_when_no_model():
    assert derive_epistemic_state(
        model_fidelity=None, tested=False, composite_uncertainty=0.0, has_model=False
    ) == EpistemicState.UNMODELED


def test_known_when_validated_and_low_uncertainty():
    assert derive_epistemic_state(
        model_fidelity=0.9, tested=True, composite_uncertainty=0.1
    ) == EpistemicState.KNOWN


def test_unknown_when_missing_info():
    assert derive_epistemic_state(
        model_fidelity=0.9, tested=True, composite_uncertainty=0.1, missing_info=True
    ) == EpistemicState.UNKNOWN


def test_uncertain_when_untested():
    # model exists but untested -> cannot be KNOWN
    assert derive_epistemic_state(
        model_fidelity=None, tested=False, composite_uncertainty=0.2
    ) == EpistemicState.UNCERTAIN


def test_uncertain_when_low_fidelity_or_high_uncertainty():
    assert derive_epistemic_state(
        model_fidelity=0.3, tested=True, composite_uncertainty=0.1
    ) == EpistemicState.UNCERTAIN
    assert derive_epistemic_state(
        model_fidelity=0.9, tested=True, composite_uncertainty=0.8
    ) == EpistemicState.UNCERTAIN


def test_epistemic_enum_no_unknowable():
    names = {e.value for e in EpistemicState}
    assert "UNKNOWABLE" not in names
    assert names == {"KNOWN", "UNCERTAIN", "UNKNOWN", "UNMODELED"}
