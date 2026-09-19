"""
Controlled LIVE execution (item 5) — certification + per-action approval + mode.

PATTERN UNDER TEST (LIVE is earned, never implicit): a LIVE world action
requires ALL of: mode=LIVE, an individually CERTIFIED capability, an explicit
PER-ACTION approval, passing capability gates, and a matching adapter. The
outcome captures predicted/actual/Reality-Gap/authority-change and routes
through verification-before-admission. Default remains OFF/DRY-RUN.
"""

import pathlib

from telos.core.actions.certification import (
    CapabilityCertification, CertificationRecord,
)
from telos.core.actions.executor import ActionExecutor
from telos.core.actions.world_adapter import FilesystemWriteAdapter
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.capability_authorization import (
    CapabilityStatus, from_dimensions,
)
from telos.core.governance.firewall import DecisionFirewall
from telos.core.governance.human_gateway import HumanVerdict
from telos.core.learning.acquisition import SkillAcquisition
from telos.core.ledger.skill_library import SkillLibrary
from telos.world.epistemic import RealityGapTracker


def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a harmless workspace with one target file.

    Args:
        tmp_path: the pytest temp directory.

    Returns:
        The workspace root path as a string.
    """
    sb = tmp_path / "ws"
    sb.mkdir()
    (sb / "notes.md").write_text("alpha\nbeta\ngamma\n")
    return str(sb)


def _proposal() -> WorldActionProposal:
    """Build a canonical filesystem-write proposal.

    Returns:
        The WorldActionProposal.
    """
    return WorldActionProposal(
        capability="filesystem.write", operation="write_file",
        target="notes.md",
        expected_result="alpha\nbeta-edited\ngamma\n",
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "unit:predicted"}, confidence=0.9, risk=0.1,
    )


def _certified() -> CapabilityCertification:
    """A certification registry certifying filesystem.write.

    Returns:
        The CapabilityCertification.
    """
    return CapabilityCertification.from_certified_set(
        {"filesystem.write"}, certified_by="test", evidence="unit",
        reason="unit certification")


def _approval(**overrides) -> LiveApproval:
    """A canonical per-action approval for the write proposal.

    Args:
        **overrides: fields to override.

    Returns:
        The LiveApproval.
    """
    base = dict(capability="filesystem.write", target="notes.md",
                operation="write_file", approver="operator", approval_id="a1")
    base.update(overrides)
    return LiveApproval(**base)


def test_live_refused_without_certification(tmp_path):
    """An uncertified capability at mode=LIVE is refused with a reason."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is False and r.action_allowed is False
    assert "not CERTIFIED" in r.blocked_reason
    assert pathlib.Path(sb, "notes.md").read_text() == "alpha\nbeta\ngamma\n"


def test_live_refused_without_approval(tmp_path):
    """Certified but no approval -> refused (no self-authorization)."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE)
    assert r.executed is False
    assert "per-action approval" in r.blocked_reason


def test_live_refused_with_standing_boolean_approval(tmp_path):
    """A standing boolean is not a per-action approval -> refused."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=True)
    assert r.executed is False
    assert "standing boolean" in r.blocked_reason


def test_live_refused_with_mismatched_approval(tmp_path):
    """An approval bound to another target/operation is refused."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE,
                   approval=_approval(target="other.md"))
    assert r.executed is False
    assert "not bound to this target/operation" in r.blocked_reason


def test_live_refused_on_capability_gate_fail(tmp_path):
    """A FAIL capability gate vetoes LIVE (conjunctive hard gate)."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    cap = from_dimensions({"observability": CapabilityStatus.FAIL})
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(),
                   capability_authorization=cap)
    assert r.executed is False
    assert "capability gate failed" in r.blocked_reason


def test_live_refused_with_no_adapter(tmp_path):
    """No adapter -> LIVE refused even with certification + approval."""
    ex = ActionExecutor(workspace_root=_workspace(tmp_path))
    runner = WorldActionRunner(ex, None, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.blocked_reason == "no_adapter_configured"


def test_live_success_captures_predicted_actual_gap(tmp_path):
    """Certified + approved LIVE writes the file and captures the gap."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    tracker = RealityGapTracker()
    runner = WorldActionRunner(
        ex, ad, certification=_certified(), firewall=DecisionFirewall(),
        reality_gap_tracker=tracker, model_id="world:filesystem.write")
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(), cycle=5)
    assert r.executed is True and r.action_allowed is True
    assert pathlib.Path(sb, "notes.md").read_text() == "alpha\nbeta-edited\ngamma\n"
    assert r.reality_gap == 0.0
    assert r.verification["matched"] is True
    assert r.actual_result["state"]["content"] == "alpha\nbeta-edited\ngamma\n"
    assert r.provenance["execution"]["permitted_by"] == "operator"
    assert r.authority_change["changed"] is True
    assert r.authority_change["fidelity_after"] == 1.0


def test_live_gap_nonzero_on_prediction_miss(tmp_path):
    """A wrong prediction still executes but records a non-zero Reality Gap."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    wrong = _proposal()
    wrong.expected_result = "totally-different\n"
    r = runner.run(wrong, ActionMode.LIVE, approval=_approval())
    assert r.action_allowed is True
    assert r.verification["matched"] is False
    assert r.reality_gap == 1.0


def test_verification_before_admission(tmp_path):
    """LIVE proposes a skill candidate; admission waits for a later hold."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    acq = SkillAcquisition(SkillLibrary())
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall(), acquisition=acq)
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(), cycle=5)
    assert r.skill_candidate_id is not None
    assert r.skill_admitted is False
    assert acq.stats()["acquired"] == 0 and acq.stats()["candidates"] == 1
    assert runner.confirm_outcome(r, cycle=9) is True
    assert r.skill_admitted is True
    assert acq.stats()["acquired"] == 1 and acq.stats()["candidates"] == 0


def test_verification_before_admission_mismatch_does_not_admit(tmp_path):
    """A later verification that does not hold admits nothing."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    acq = SkillAcquisition(SkillLibrary())
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall(), acquisition=acq)
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(), cycle=5)
    # A later observation that does NOT match the prediction.
    from telos.core.actions.world_adapter import WorldObservation
    mismatch = WorldObservation(source="file:notes.md",
                                state={"exists": True, "content": "different\n"})
    assert runner.confirm_outcome(r, observation=mismatch, cycle=9) is False
    assert acq.stats()["acquired"] == 0
    assert r.skill_admitted is False


def test_human_gateway_verdict_becomes_per_action_approval(tmp_path):
    """A genuine HumanGateway approval authorizes; a fail-closed one does not."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    approved = HumanVerdict(approved=True, reviewer="human",
                            decision_source="explicit")
    r = runner.run(_proposal(), ActionMode.LIVE, approval=approved)
    assert r.action_allowed is True
    assert r.approval["approver"] == "human_gateway"

    # fail_closed is never an approval, even if approved were somehow True.
    fc = HumanVerdict(approved=True, reviewer="fail_closed",
                      decision_source="fail_closed")
    runner2 = WorldActionRunner(
        ex, FilesystemWriteAdapter(ex, "notes.md"),
        certification=_certified(), firewall=DecisionFirewall())
    r2 = runner2.run(_proposal(), ActionMode.LIVE, approval=fc)
    assert r2.executed is False


def test_certification_default_is_empty_and_fail_closed(tmp_path):
    """The default registry certifies nothing; a malformed file fails closed."""
    reg = CapabilityCertification(records={})
    assert reg.is_certified("filesystem.write") is False
    assert reg.certified_names() == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json")
    loaded = CapabilityCertification(path=str(bad))
    assert loaded.certified_names() == []
    assert loaded.record_for("filesystem.write") is None


def test_certification_certify_and_revoke(tmp_path):
    """Certify then revoke flips the per-capability LIVE gate."""
    reg = CapabilityCertification(records={})
    assert reg.is_certified("filesystem.write") is False
    rec = reg.certify("filesystem.write", certified_by="op",
                      evidence="eval:tool_governance", reason="reviewed")
    assert isinstance(rec, CertificationRecord)
    assert reg.is_certified("filesystem.write") is True
    assert reg.certified_names() == ["filesystem.write"]
    reg.revoke("filesystem.write", reason="drift detected")
    assert reg.is_certified("filesystem.write") is False
