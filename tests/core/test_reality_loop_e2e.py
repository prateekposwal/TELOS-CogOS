"""
The decisive end-to-end loop (items 6-9): observe -> gap -> authority -> cert.

Positive loop: propose -> authorization succeeds -> adapter executes ->
real-world result observed -> prediction vs observation -> Reality Gap ->
authority recalibrated -> skill admitted only when verified.

Negative loop: a planted mismatch yields a non-zero gap, REDUCES authority, and
admits no skill; a persistent failure streak drives authority to FAIL and blocks
the next ACT. Certification is earned from the REAL run outcomes, not seeded.
"""

import pathlib

from telos.core.actions.certification import (
    CapabilityCertification, CertificationAction, CertificationWorkflow,
    VerifiedOutcome,
)
from telos.core.actions.executor import ActionExecutor
from telos.core.actions.rate_limit import ToolRateLimiter
from telos.core.actions.reality_loop import CapabilityAuthority
from telos.core.actions.world_adapter import FilesystemWriteAdapter
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.capability_authorization import CapabilityStatus
from telos.core.governance.firewall import DecisionFirewall
from telos.core.learning.acquisition import SkillAcquisition
from telos.core.ledger.skill_library import SkillLibrary

CAP = "filesystem.write"
TARGET = "notes.md"
ORIGINAL = "alpha\nbeta\ngamma\n"
EDITED = "alpha\nbeta-edited\ngamma\n"


def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a workspace with one target file.

    Args:
        tmp_path: the pytest temp directory.

    Returns:
        The workspace root path as a string.
    """
    sb = tmp_path / "ws"
    sb.mkdir()
    (sb / TARGET).write_text(ORIGINAL)
    return str(sb)


def _reseed(sb: str) -> None:
    """Restore the target file's original content before each run.

    Args:
        sb: the workspace root.
    """
    pathlib.Path(sb, TARGET).write_text(ORIGINAL)


def _proposal(expected=EDITED) -> WorldActionProposal:
    """Build a canonical filesystem-write proposal.

    Args:
        expected: the predicted result content.

    Returns:
        The WorldActionProposal.
    """
    return WorldActionProposal(
        capability=CAP, operation="write_file", target=TARGET,
        expected_result=expected,
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "e2e:predicted"}, confidence=0.9, risk=0.1)


def _approval() -> LiveApproval:
    """A canonical per-action approval.

    Returns:
        The LiveApproval.
    """
    return LiveApproval(CAP, TARGET, "write_file", "operator", "e2e-1")


def _run(runner, proposal, cycle):
    """Run one LIVE action with an ISOLATED firewall.

    Each demonstration run is an independent supervised action; the firewall's
    action_loop guard (which correctly stops repeated identical actions inside a
    live loop) is reset so the loop's gap->authority mechanism is what is
    measured, not the loop guard.

    Args:
        runner: the WorldActionRunner.
        proposal: the proposal to run.
        cycle: the cycle stamp.

    Returns:
        The WorldActionResult.
    """
    runner.firewall = DecisionFirewall()
    return runner.run(proposal, ActionMode.LIVE, approval=_approval(), cycle=cycle)


def test_end_to_end_positive_and_negative_loop(tmp_path):
    """The full closed loop, positive and negative, on the sandboxed adapter."""
    sb = _workspace(tmp_path)
    # The demonstration runs several INDEPENDENT supervised actions in quick
    # succession; the production per-minute ceiling (6/min for write_file) would
    # block later runs and mask the gap->authority mechanism. Rate limiting is
    # exercised elsewhere; here the limiter is raised so each run is measured.
    ex = ActionExecutor(
        workspace_root=sb,
        rate_limiter=ToolRateLimiter(limits={"write_file": 1000},
                                     max_total=None),
    )
    ad = FilesystemWriteAdapter(ex, TARGET)
    fw = DecisionFirewall()

    # ── Phase 0 — fail-closed default: zero certified -> LIVE refused. ──────
    default_reg = CapabilityCertification(records={})
    runner0 = WorldActionRunner(ex, ad, certification=default_reg, firewall=fw)
    r0 = runner0.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r0.executed is False and "not CERTIFIED" in r0.blocked_reason

    # ── Phase 1 — operator bootstrap trial + REAL outcome collection. ───────
    bootstrap = CapabilityCertification.from_certified_set(
        {CAP}, certified_by="operator",
        evidence="supervised bounded trial (item 5 bootstrap)",
        reason="operator-authorized trial")
    authority = CapabilityAuthority()
    acq = SkillAcquisition(SkillLibrary())
    runner = WorldActionRunner(
        ex, ad, certification=bootstrap, firewall=fw, authority=authority,
        acquisition=acq)
    outcomes = []
    for cycle in range(3):
        _reseed(sb)
        r = _run(runner, _proposal(), cycle)
        assert r.executed is True and r.reality_gap == 0.0
        outcomes.append(VerifiedOutcome(
            CAP, matched=bool(r.verification["matched"]), gap=r.reality_gap,
            cycle=cycle, source=f"e2e:{cycle}"))
    assert authority.state(CAP).status is CapabilityStatus.PASS

    # ── Phase 2 — certify from the REAL outcomes (evidence-backed). ─────────
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    decision = wf.evaluate(CAP, outcomes)
    assert decision.action is CertificationAction.CERTIFY
    assert decision.evidence["successes"] == 3
    assert decision.evidence["success_cycles"] == [0, 1, 2]
    workflow_reg = CapabilityCertification(records={})
    wf.apply(workflow_reg, decision, cycle=10)
    assert workflow_reg.is_certified(CAP) is True

    # ── Phase 3 — POSITIVE loop on the workflow-certified registry. ─────────
    authority2 = CapabilityAuthority()
    acq2 = SkillAcquisition(SkillLibrary())
    runner2 = WorldActionRunner(
        ex, ad, certification=workflow_reg, firewall=fw, authority=authority2,
        acquisition=acq2)
    _reseed(sb)
    rp = _run(runner2, _proposal(), 20)
    assert rp.executed is True and rp.action_allowed is True
    assert rp.reality_gap == 0.0
    assert rp.post_observation["state"]["content"] == EDITED
    assert rp.authority_change["status_after"] == "PASS"
    assert rp.authority_change["fidelity_after"] == 1.0
    assert runner2.confirm_outcome(rp, cycle=21) is True
    assert rp.skill_admitted is True
    assert acq2.stats()["acquired"] == 1

    # ── Phase 4 — NEGATIVE loop: a planted mismatch reduces authority. ──────
    wrong = _proposal(expected="totally-different\n")
    _reseed(sb)
    rn = _run(runner2, wrong, 30)
    assert rn.action_allowed is True
    assert 0.0 < rn.reality_gap <= 1.0
    change = rn.authority_change
    assert change["fidelity_after"] < change["fidelity_before"]
    assert change["status_before"] == "PASS"
    assert change["status_after"] == "LIMITED"
    # The mismatch admits nothing (verification-before-admission holds).
    assert runner2.confirm_outcome(rn, cycle=31) is False
    assert rn.skill_admitted is False
    assert acq2.stats()["acquired"] == 1

    # ── Phase 5 — a persistent streak FAILs authority and BLOCKS the next ACT.
    for cycle in (32, 33, 34):
        _reseed(sb)
        _run(runner2, wrong, cycle)
    st = authority2.state(CAP)
    assert st.status is CapabilityStatus.FAIL
    assert st.recent_mean_gap is not None and st.recent_mean_gap > 0.5
    _reseed(sb)
    blocked = _run(runner2, _proposal(), 40)
    assert blocked.executed is False
    assert "capability gate failed" in blocked.blocked_reason
    assert "model_fidelity" in blocked.blocked_reason
    assert pathlib.Path(sb, TARGET).read_text() == ORIGINAL
