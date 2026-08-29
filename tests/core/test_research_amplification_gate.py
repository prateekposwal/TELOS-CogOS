"""Contract tests for the Research Amplification Gate (Λ6.5, pre-PERCEIVE stage).

Locks the bounded-evidence-mode structural fix:
  - a run with zero external evidence is FAIL/LEFT, never DONE;
  - a run with a gap in ANY mandatory dimension is FAIL/LEFT;
  - a run with all mandatory dimensions externally covered is PASS/DONE;
  - internal-reasoning-only sources never count as enrichment;
  - every claim must name a registered source (Λ6.5).
"""

import pytest

from telos.core.research.amplification_gate import (
    MANDATORY_DIMENSIONS,
    AmplificationReport,
    EvidenceClaim,
    EvidenceSource,
    ResearchAmplificationGate,
    SourceClassification,
)


def _sample_gate() -> ResearchAmplificationGate:
    """Gate with external coverage across every mandatory dimension."""
    gate = ResearchAmplificationGate()
    gate.register_source(EvidenceSource(
        source_id="A",
        name="LI News — Buying Time: Longevity Moves Into Real Estate",
        venue="Longevity Investors",
        classification=SourceClassification.SECONDARY,
    ))
    gate.register_source(EvidenceSource(
        source_id="B",
        name="Longevity Book / Deep Knowledge Group",
        venue="longevity-book.com",
        classification=SourceClassification.PRIMARY,
    ))
    for i, dim in enumerate(MANDATORY_DIMENSIONS):
        gate.register_claim(EvidenceClaim(
            source_id="A" if i % 2 == 0 else "B",
            claim=f"grounded claim covering {dim}",
            dimension=dim,
        ))
    return gate


def test_full_coverage_is_pass_done():
    gate = _sample_gate()
    report = gate.run()
    assert report.passed is True
    assert report.run_status == "DONE"
    assert report.missing_dimensions == []
    assert report.total_external_sources == 2
    assert report.total_claims == len(MANDATORY_DIMENSIONS)


def test_zero_evidence_is_left_not_done():
    gate = ResearchAmplificationGate()
    report = gate.run()  # no sources registered at all
    assert report.passed is False
    assert report.run_status == "LEFT"
    assert set(report.missing_dimensions) == set(MANDATORY_DIMENSIONS)


def test_internal_source_never_counts_as_enrichment():
    """The model's own priors are NOT external enrichment (bounded-evidence-mode)."""
    gate = ResearchAmplificationGate()
    gate.register_source(EvidenceSource(
        source_id="M", name="model prior", venue="internal",
        classification=SourceClassification.INTERNAL,
    ))
    for dim in MANDATORY_DIMENSIONS:
        gate.register_claim(EvidenceClaim(
            source_id="M", claim=f"model's own prior on {dim}", dimension=dim,
        ))
    report = gate.run()
    assert report.passed is False
    assert report.run_status == "LEFT"
    assert report.total_external_sources == 0


def test_single_dimension_gap_is_left():
    gate = _sample_gate()
    # remove every claim on the LAST dimension -> that dimension goes uncovered
    gate._claims = [c for c in gate._claims if c.dimension != MANDATORY_DIMENSIONS[-1]]
    report = gate.run()
    assert report.passed is False
    assert report.run_status == "LEFT"
    assert report.missing_dimensions == [MANDATORY_DIMENSIONS[-1]]


def test_claim_requires_registered_source():
    gate = _sample_gate()
    with pytest.raises(ValueError):
        gate.register_claim(EvidenceClaim(
            source_id="UNREGISTERED", claim="orphan claim", dimension="regulation_licensing",
        ))


def test_claim_dimension_must_be_mandatory():
    gate = _sample_gate()
    with pytest.raises(ValueError):
        gate.register_claim(EvidenceClaim(
            source_id="A", claim="not a category dimension",
            dimension="my_hobby",
        ))


def test_duplicate_source_id_rejected():
    gate = ResearchAmplificationGate()
    src = EvidenceSource(source_id="A", name="x", venue="y")
    gate.register_source(src)
    with pytest.raises(ValueError):
        gate.register_source(src)


def test_report_serialization_roundtrip():
    report = _sample_gate().run()
    d = report.to_dict()
    assert d["passed"] is True
    assert d["run_status"] == "DONE"
    assert set(d["covered_dimensions"].keys()) == set(MANDATORY_DIMENSIONS)
    assert isinstance(report, AmplificationReport)
    assert d["total_claims"] == len(MANDATORY_DIMENSIONS)


def test_gate_skipped_run_flag():
    """A run that never executes the gate carries no PASS — answering anyway is LEFT."""
    gate = ResearchAmplificationGate()
    assert gate.last_report is None
    # This mirrors the diagnosed failure: streams/simulate consumed the brief
    # with no amplification pass -> the run must be marked LEFT by the caller.
    assert gate.last_report is None  # no report = no license to claim DONE
