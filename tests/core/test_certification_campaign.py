"""
Certification campaign — the loop must be correct UNDER VARIANCE, not by count.

PATTERN UNDER TEST (certification is earned from loop-correctness, never from a
pass count): the strengthened ``CertificationWorkflow`` HOLDs without variance
evidence, HOLDs on any failed loop invariant (I1-I8), HOLDs when the gap does not
discriminate (blind) or a large divergence is undetected, HOLDs on a false admit
or a fail-open, and REVOKEs on a failure streak. The campaign harness drives the
REAL loop across the variance matrix and every case must assert its outcome.
"""

import shutil

import pytest

from telos.core.actions.certification import (
    CERTIFICATION_INVARIANTS, CapabilityCertification, CertificationAction,
    CertificationWorkflow, VarianceEvidence, VerifiedOutcome,
)
from telos.core.actions.executor import ActionExecutor, ToolPermission
from telos.core.governance.firewall import DecisionFirewall
from telos.tools.certification_campaign import run_campaign

CAP = "filesystem.write"


def _successes(n: int = 3):
    """Build n successful verified outcomes for filesystem.write.

    Args:
        n: number of outcomes.

    Returns:
        List of VerifiedOutcome (matched, gap 0.0).
    """
    return [VerifiedOutcome(CAP, True, 0.0, cycle=i, source=f"test:{i}")
            for i in range(n)]


def _bad(n: int = 2):
    """Build n failed verified outcomes (mismatch, large gap).

    Args:
        n: number of outcomes.

    Returns:
        List of VerifiedOutcome (not matched, gap 0.8).
    """
    return [VerifiedOutcome(CAP, False, 0.8, cycle=100 + i, source=f"bad:{i}")
            for i in range(n)]


def _variance(**overrides):
    """Build a fully-satisfying VarianceEvidence, overriding given fields.

    Args:
        **overrides: fields to override.

    Returns:
        The VarianceEvidence.
    """
    base = dict(
        capability=CAP,
        families={"normal": 1, "near_match": 1, "adversarial": 4, "refusal": 2},
        invariants={k: True for k in CERTIFICATION_INVARIANTS},
        measured_gaps=[0.0, 0.06, 0.67, 1.0],
        normal_gap_max=0.0,
        adversarial_gap_min=0.06,
        adversarial_gap_max=0.67,
        false_admits=0,
        fail_open_count=0,
        revocation_demonstrated=True,
        source="test",
    )
    base.update(overrides)
    return VarianceEvidence(**base)


def test_require_variance_holds_without_evidence():
    """The strengthened workflow HOLDs on a pass count with no variance record."""
    wf = CertificationWorkflow(require_variance=True)
    decision = wf.evaluate(CAP, _successes(3))
    assert decision.action is CertificationAction.HOLD
    assert decision.certified is False
    assert decision.evidence["variance"]["failures"] == [
        "variance_evidence_missing"]


def test_variance_evidence_certifies():
    """Loop-correctness evidence + verified outcomes certifies."""
    wf = CertificationWorkflow(require_variance=True)
    decision = wf.evaluate(CAP, _successes(3), variance=_variance())
    assert decision.action is CertificationAction.CERTIFY
    assert decision.certified is True
    assert decision.evidence["variance"]["satisfied"] is True
    # Applying writes the structured evidence detail.
    reg = CapabilityCertification(records={})
    rec = wf.apply(reg, decision, cycle=7)
    assert rec is not None and reg.is_certified(CAP) is True
    assert rec.evidence_detail["variance"]["satisfied"] is True


@pytest.mark.parametrize("override,failing", [
    ({"invariants": {k: (k != "I3") for k in CERTIFICATION_INVARIANTS}},
     "invariant_I3"),
    ({"invariants": {k: (k != "I1") for k in CERTIFICATION_INVARIANTS}},
     "invariant_I1"),
    ({"false_admits": 1}, "false_admits"),
    ({"fail_open_count": 1}, "fail_open"),
    ({"adversarial_gap_min": 0.0}, "gap_not_discriminating"),
    ({"adversarial_gap_max": 0.4}, "gap_not_discriminating"),
    ({"revocation_demonstrated": False}, "revocation_not_demonstrated"),
    ({"families": {"normal": 1, "adversarial": 1, "refusal": 1}},
     "battery_adversarial_cases"),
    ({"families": {"normal": 0, "adversarial": 4, "refusal": 1}},
     "battery_normal_cases"),
    ({"families": {"normal": 1, "adversarial": 4, "refusal": 0}},
     "battery_refusal_cases"),
    ({"measured_gaps": [0.0, 2.0]}, "gaps_unbounded"),
])
def test_failed_variance_gate_holds(override, failing):
    """Any failed strengthened gate HOLDs with the failing gate named."""
    wf = CertificationWorkflow(require_variance=True)
    decision = wf.evaluate(CAP, _successes(3), variance=_variance(**override))
    assert decision.action is CertificationAction.HOLD
    assert failing in decision.evidence["variance"]["failures"]


def test_revocation_takes_priority_over_variance():
    """A trailing failure streak REVOKEs even with perfect variance evidence."""
    wf = CertificationWorkflow(require_variance=True, failure_streak=2)
    decision = wf.evaluate(
        CAP, _successes(3) + _bad(2), variance=_variance())
    assert decision.action is CertificationAction.REVOKE
    assert decision.certified is False


def test_legacy_pass_count_still_evaluates_without_variance():
    """Back-compat: the legacy evaluator still certifies on a pass count alone."""
    wf = CertificationWorkflow()  # require_variance defaults False
    decision = wf.evaluate(CAP, _successes(3))
    assert decision.action is CertificationAction.CERTIFY
    # But the legacy reason explicitly admits variance is absent.
    assert "WITHOUT variance evidence" in decision.reason


def test_campaign_battery_all_cases_and_invariants_hold():
    """The real battery: every case asserts its outcome and every invariant holds."""
    artifact = run_campaign(live=False, persist=False)
    assert all(c["passed"] for c in artifact["variance_matrix"])
    assert artifact["verdict"]["passed"] is True
    for name, rec in artifact["invariants"].items():
        assert rec["held"] is True, (name, rec["detail"])
    fam = artifact["variance_evidence"]["families"]
    assert fam["normal"] >= 1 and fam["adversarial"] >= 3 and fam["refusal"] >= 1
    assert artifact["certification"]["certified"] is True
    # Nothing is persisted and no LIVE exercise runs in the hermetic test path.
    assert artifact["certification"]["canonical_record_written"] is False
    assert artifact["live_exercise"] is None


def test_campaign_gap_discriminates_and_is_not_blind():
    """The measured gaps are bounded and discriminate exact/divergent."""
    ev = run_campaign(live=False, persist=False)["variance_evidence"]
    assert ev["normal_gap_max"] == 0.0
    assert ev["adversarial_gap_min"] > ev["normal_gap_max"]
    assert ev["adversarial_gap_max"] > 0.5
    assert ev["false_admits"] == 0
    assert ev["fail_open_count"] == 0
    assert ev["revocation_demonstrated"] is True


def test_campaign_has_no_false_admit_or_fail_open_case():
    """No mismatch case admits, and no refusal case produces an effect."""
    artifact = run_campaign(live=False, persist=False)
    for c in artifact["variance_matrix"]:
        m = c["measured"]
        if c["family"] == "refusal":
            assert m.get("action_allowed") is not True
            assert m.get("gap") is None
        if m.get("admitted") is True:
            assert m.get("matched") is True


def test_campaign_is_sandbox_confined():
    """No case touched the TELOS repo or the designated LIVE sandbox."""
    artifact = run_campaign(live=False, persist=False)
    assert artifact["sandbox_only"] is True
    assert artifact["live_exercise"] is None


@pytest.mark.skipif(shutil.which("make") is None, reason="make not available")
def test_executor_timeout_is_a_block(tmp_path):
    """A timed-out command is a recorded block, never an allowed execution."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "Makefile").write_text("hang:\n\tsleep 5\n")
    ex = ActionExecutor(workspace_root=str(ws), timeout=0.4)
    rec = ex.execute(
        ToolPermission(tool_name="make_target", args=["hang"], cwd=str(ws),
                       permitted_by="operator"),
        firewall=DecisionFirewall())
    assert rec.timed_out is True
    assert rec.allowed is False
    assert "timed out" in (rec.blocked_reason or "")
