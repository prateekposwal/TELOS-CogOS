"""Coordination divergence eval — writer <-> reader schema linkage + the
decisive measurement: the advisory crew is not a monoculture.

The Λ4.11 boundary fix observed ``diversity = 0.0`` on all measured standard
mode cycles. These tests lock the honest conclusion: on uniformly-healthy
evidence the crew IS unanimous (diversity 0), but the role lenses genuinely
diverge when the evidence is marginal or the primary verdict is manipulated.
"""

import json

from telos.core.verifier.measurement import read_measurement
from telos.tools import coordination_divergence_eval as cde


def test_evaluate_measures_both_axes():
    """Healthy input is unanimous; adversarial input produces divergence."""
    result = cde.evaluate()
    assert all(result["criteria"].values()), result["criteria"]
    scenarios = result["scenarios"]
    # Healthy evidence: every role DI == 1.0 -> correctly unanimous.
    assert scenarios["healthy"]["diversity"] == 0.0
    assert scenarios["healthy"]["n_agents"] >= 5
    # All-pass evidence + high mission drift: DI spread is 0, but the crew
    # still disagrees on the validation axis (conservative md_cap).
    assert scenarios["validated_axis"]["diversity"] == 0.0
    assert scenarios["validated_axis"]["consensus"] < 1.0
    # The decisive evidence: the crew DOES diverge on marginal/adversarial input.
    assert scenarios["marginal"]["diversity"] > 0.0
    assert scenarios["manipulated_primary"]["diversity"] > 0.0


def test_writer_keys_match_declared_criteria():
    """The writer emits exactly the criteria it declares (drift fails loudly)."""
    result = cde.evaluate()
    assert set(result["criteria"]) == set(cde.CRITERIA)
    assert set(result["provenance"]["criteria"]) == set(cde.CRITERIA)
    assert result["verdict"]["total"] == len(cde.CRITERIA)


def test_writer_reader_schema_links(tmp_path):
    """The artifact the eval writes is readable under its declared schema."""
    result = cde.evaluate()
    audit = tmp_path / "telos" / "audit"
    audit.mkdir(parents=True)
    (audit / "coordination_divergence.json").write_text(
        json.dumps(result), encoding="utf-8")
    m = read_measurement(str(tmp_path), "telos/audit/coordination_divergence.json",
                         tuple(cde.CRITERIA))
    assert m is not None
    assert m.verdict_passed is True
    assert m.passed_count == len(cde.CRITERIA)
    assert m.artifact_backed is True


def test_reader_is_a_real_gate_when_divergence_is_not_measured(tmp_path):
    """A tampered artifact claiming no marginal divergence must not pass."""
    result = cde.evaluate()
    result["criteria"]["marginal_evidence_divergence"] = False
    result["verdict"] = {"passed": False, "passed_count": 6,
                         "total": len(cde.CRITERIA)}
    audit = tmp_path / "telos" / "audit"
    audit.mkdir(parents=True)
    (audit / "coordination_divergence.json").write_text(
        json.dumps(result), encoding="utf-8")
    m = read_measurement(str(tmp_path), "telos/audit/coordination_divergence.json",
                         tuple(cde.CRITERIA))
    assert m is not None
    assert m.verdict_passed is False
    assert m.criteria["marginal_evidence_divergence"] is False
