"""
Items 6-8: post-action observation -> Reality Gap -> authority recalibration.

PATTERN UNDER TEST (measure, then let the measurement change authority): after
a LIVE action the adapter takes a GENUINE post-action read (item 6); the read is
compared to the prediction with the canonical bounded metric (item 7); the gap
recalibrates the capability's authority, and a capability whose authority falls
below the FAIL threshold can no longer ACT (item 8) — through the existing
CapabilityAuthorization hard-gate machinery, not a parallel store.
"""

import hashlib
import pathlib

from telos.core.actions.certification import CapabilityCertification
from telos.core.actions.executor import ActionExecutor, ToolPermission
from telos.core.actions.reality_loop import (
    GAP_METRIC, AuthorityState, CapabilityAuthority, text_reality_gap,
)
from telos.core.actions.world_adapter import FilesystemWriteAdapter
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.capability_authorization import CapabilityStatus
from telos.core.governance.firewall import DecisionFirewall


def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a workspace with one target file.

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
        capability="filesystem.write", operation="write_file", target="notes.md",
        expected_result="alpha\nbeta-edited\ngamma\n",
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "unit:predicted"}, confidence=0.9, risk=0.1,
    )


def _certified() -> CapabilityCertification:
    """A registry certifying filesystem.write for these unit tests.

    Returns:
        The CapabilityCertification.
    """
    return CapabilityCertification.from_certified_set(
        {"filesystem.write"}, certified_by="test", evidence="unit",
        reason="unit certification")


def _approval() -> LiveApproval:
    """A canonical per-action approval.

    Returns:
        The LiveApproval.
    """
    return LiveApproval("filesystem.write", "notes.md", "write_file",
                        "operator", "a1")


def test_gap_metric_is_bounded_and_precise():
    """The canonical gap is 0 on exact match, 1 on absence, bounded otherwise."""
    assert text_reality_gap("abc", "abc") == 0.0
    assert text_reality_gap(None, "abc") == 1.0
    assert text_reality_gap("abc", None) == 1.0
    assert text_reality_gap("", "abc") == 1.0
    g = text_reality_gap("alpha\nbeta\ngamma\n", "alpha\nBETA\ngamma\n")
    assert 0.0 < g < 1.0
    assert text_reality_gap("a" * 50, "b" * 50) == 1.0
    assert text_reality_gap("abc", "abd") == text_reality_gap("abd", "abc")
    assert GAP_METRIC == "normalized_text_divergence"


def test_post_action_observation_is_a_fresh_read_with_fingerprint(tmp_path):
    """Item 6: the observation is read AFTER execute(), with a real hash."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(), cycle=3)
    assert r.executed is True
    expected_content = "alpha\nbeta-edited\ngamma\n"
    assert r.post_observation["state"]["content"] == expected_content
    assert r.post_observation["state"]["sha256"] == hashlib.sha256(
        expected_content.encode()).hexdigest()
    # The pre-action observer saw the ORIGINAL content — a genuine re-read.
    assert r.observer["state"]["content"] == "alpha\nbeta\ngamma\n"
    assert r.provenance["post_action_observation"]["read_after_execute"] is True


def test_authority_reinforced_by_zero_gap(tmp_path):
    """Item 8: repeated exact matches reinforce authority to PASS."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    authority = CapabilityAuthority()
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall(), authority=authority)
    assert authority.status("filesystem.write") is CapabilityStatus.UNKNOWN
    for cycle in range(3):
        # Re-create the target for each independent exact-match run.
        pathlib.Path(sb, "notes.md").write_text("alpha\nbeta\ngamma\n")
        r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(),
                       cycle=cycle)
        assert r.reality_gap == 0.0
    state = authority.state("filesystem.write")
    assert isinstance(state, AuthorityState)
    assert state.validations == 3
    assert state.status is CapabilityStatus.PASS
    assert state.fidelity == 1.0
    assert state.model_id == "world_action:filesystem.write"


def test_authority_reduced_then_blocks_act(tmp_path):
    """Item 8: a large measured gap FAILs authority, which blocks ACT."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    authority = CapabilityAuthority()
    # A measured, largely-divergent outcome (gap ~0.667) -> fidelity ~0.333.
    authority.record("filesystem.write", 0.9, cycle=1)
    state = authority.state("filesystem.write")
    assert state.status is CapabilityStatus.FAIL
    assert state.fidelity is not None and state.fidelity < 0.5
    cap = authority.capability_authorization("filesystem.write", now_cycle=1)
    assert cap.gate("model_fidelity").status is CapabilityStatus.FAIL
    # The runner derives the same authorization and refuses LIVE.
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall(), authority=authority)
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(), cycle=2)
    assert r.executed is False
    assert "capability gate failed" in r.blocked_reason
    assert "model_fidelity" in r.blocked_reason
    assert r.authority_state["status"] == "FAIL"
    # The executor's OWN per-tool gate also vetoes (no bypass through it).
    exe = ex.execute(
        ToolPermission(tool_name="write_file",
                       args=[{"path": "notes.md",
                              "old_lines": ["beta"],
                              "new_lines": ["beta-edited"]}],
                       cwd=sb, permitted_by="operator"),
        firewall=DecisionFirewall(), capability=cap)
    assert exe.allowed is False
    assert "capability gate vetoed" in exe.blocked_reason


def test_authority_recalibration_recorded_in_result(tmp_path):
    """The result records the measured gap and the authority before/after."""
    sb = _workspace(tmp_path)
    ex = ActionExecutor(workspace_root=sb)
    ad = FilesystemWriteAdapter(ex, "notes.md")
    authority = CapabilityAuthority()
    runner = WorldActionRunner(ex, ad, certification=_certified(),
                               firewall=DecisionFirewall(), authority=authority)
    wrong = _proposal()
    wrong.expected_result = "totally-different\n"
    r = runner.run(wrong, ActionMode.LIVE, approval=_approval(), cycle=7)
    assert r.action_allowed is True
    assert r.provenance["reality_gap"]["metric"] == GAP_METRIC
    change = r.authority_change
    assert change["status_before"] == "UNKNOWN"
    assert change["status_after"] == "FAIL"
    assert change["changed"] is True
    assert change["authority_after"]["validations"] == 1
