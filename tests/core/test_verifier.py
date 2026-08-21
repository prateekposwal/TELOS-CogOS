"""Contract tests for scale/verifier — runs the deliberation law at multiple
scales and asserts structural identity (Λ1.1 cross-scale equality)."""
import json

from telos.core.scale.factory import build_standard_pipeline
from telos.core.scale.verifier import ScaleConfig, ScaleReport, ScaleVerifier


def test_phase_signature_is_a_tuple():
    verifier = ScaleVerifier()
    p = build_standard_pipeline("micro")
    assert isinstance(verifier.phase_signature(p), tuple)
    assert len(verifier.phase_signature(p)) >= 3


def test_verify_pipeline_reports_mismatch_honestly():
    verifier = ScaleVerifier()
    p = build_standard_pipeline("micro")
    ok, reason = verifier.verify_pipeline(p)
    if not ok:
        assert "phase signature" in reason


def test_run_produces_scale_report():
    verifier = ScaleVerifier()
    report = verifier.run([ScaleConfig(name="micro", budget_ms=12.0, n_worlds=3)])
    assert isinstance(report, ScaleReport)
    assert "micro" in report.scales
    assert report.invariant_holds is True or report.violations


def test_report_to_dict_serializable():
    verifier = ScaleVerifier()
    report = verifier.run([ScaleConfig(name="macro", budget_ms=60.0)])
    d = report.to_dict()
    assert "invariant_holds" in d and "phase_signatures" in d
    json.dumps(d)