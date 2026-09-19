"""
Item 9: the per-capability certification workflow (evidence -> decision).

PATTERN UNDER TEST (certification is earned, cited, and revocable): a
capability becomes CERTIFIED only from a bounded window of verified LIVE
outcomes with enough successes and no failure streak; a trailing failure streak
REVOKES it; no evidence HOLDs (fail-closed). The default registry remains EMPTY.
"""

from telos.core.actions.certification import (
    DEFAULT_CERTIFICATION_PATH, CapabilityCertification, CertificationAction,
    CertificationWorkflow, VerifiedOutcome,
)


def _outcomes(rows):
    """Build VerifiedOutcome rows for filesystem.write.

    Args:
        rows: iterable of (cycle, matched, gap) tuples.

    Returns:
        List of VerifiedOutcome.
    """
    return [VerifiedOutcome("filesystem.write", matched, gap, cycle=c,
                            source=f"run:{c}") for c, matched, gap in rows]


def test_default_registry_is_empty_and_evidence_is_required():
    """Fail-closed: the workflow HOLDs with no evidence; the default is empty."""
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    decision = wf.evaluate("filesystem.write", [])
    assert decision.action is CertificationAction.HOLD
    assert decision.certified is False
    assert decision.evidence["sample_size"] == 0
    assert decision.evidence["successes"] == 0
    # Applying a HOLD mutates nothing.
    reg = CapabilityCertification(records={})
    assert wf.apply(reg, decision) is None
    assert reg.is_certified("filesystem.write") is False
    assert CapabilityCertification(
        path="/nonexistent/cert.json").certified_names() == []
    assert DEFAULT_CERTIFICATION_PATH.endswith(
        "capability_certification.json")


def test_workflow_certifies_on_sustained_success():
    """Enough successful verified outcomes certify, with cited evidence."""
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    # Two successes is not enough (fail-closed), three is.
    two = wf.evaluate("filesystem.write", _outcomes(
        [(1, True, 0.0), (2, True, 0.05)]))
    assert two.action is CertificationAction.HOLD
    three = wf.evaluate("filesystem.write", _outcomes(
        [(1, True, 0.0), (2, True, 0.05), (3, True, 0.1)]))
    assert three.action is CertificationAction.CERTIFY
    assert three.certified is True
    assert three.evidence["successes"] == 3
    assert three.evidence["failure_streak"] == 0
    assert three.evidence["criteria"]["min_successes"] == 3
    assert three.evidence["criteria"]["max_gap"] == 0.2
    assert three.evidence["success_cycles"] == [1, 2, 3]
    # Applying writes an evidence-backed record.
    reg = CapabilityCertification(records={})
    rec = wf.apply(reg, three, cycle=99)
    assert rec is not None and rec.certified is True
    assert reg.is_certified("filesystem.write") is True
    assert rec.certified_by == "certification_workflow"
    assert rec.evidence_detail["successes"] == 3
    assert rec.certified_cycle == 99


def test_workflow_revokes_on_failure_streak():
    """A trailing failure streak revokes an existing certification."""
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    rows = [(1, True, 0.0), (2, True, 0.0), (3, True, 0.0),
            (4, False, 0.9), (5, False, 0.8)]
    decision = wf.evaluate("filesystem.write", _outcomes(rows))
    assert decision.action is CertificationAction.REVOKE
    assert decision.evidence["failure_streak"] == 2
    reg = CapabilityCertification.from_certified_set({"filesystem.write"})
    assert reg.is_certified("filesystem.write") is True
    wf.apply(reg, decision)
    assert reg.is_certified("filesystem.write") is False


def test_workflow_only_counts_recent_window():
    """Old successes fall out of the bounded window (recency matters)."""
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=3)
    rows = [(i, True, 0.0) for i in range(1, 6)]
    rows.append((6, True, 0.9))  # a miss, but streak < failure_streak
    decision = wf.evaluate("filesystem.write", _outcomes(rows))
    # Only the last 5 outcomes count: 4 successes, streak 1 -> HOLD.
    assert decision.evidence["sample_size"] == 5
    assert decision.evidence["successes"] == 4
    assert decision.action is CertificationAction.HOLD


def test_workflow_ignores_other_capabilities():
    """Outcomes for another capability do not certify this one."""
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    rows = [VerifiedOutcome("other.cap", True, 0.0, cycle=i)
            for i in range(5)]
    decision = wf.evaluate("filesystem.write", rows)
    assert decision.action is CertificationAction.HOLD
    assert decision.evidence["sample_size"] == 0
