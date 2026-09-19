"""
Degradation / revocation under UNEXPECTED real-world variance.

PATTERN UNDER TEST (losing authority correctly — the other half of the learning
loop): a capability that was LIVE-CERTIFIED and believed correct meets a real
observation that CONTRADICTS its prediction. The full chain must run through the
real machinery, in the safe direction, with no human in the loop:

  1. DETECTION      the unexpected non-match is a measured fidelity failure
                    (prediction vs observation gap), never silently absorbed;
  2. DEGRADATION    the capability's authority moves PASS -> LIMITED -> FAIL as
                    evidence accumulates;
  3. ACT BLOCKING   a FAIL authority structurally blocks the next ACT (no
                    execution seam is reached), through the conjunctive gate;
  4. REVOCATION     a trailing failure streak revokes the certification
                    (LIVE -> not-certified), fail-closed;
  5. READ PATH      revocation is reflected wherever the canonical registry is
                    read; a stale, previously-FALSIFIED authority is NOT
                    silently re-authorized by time alone;
  6. RE-EARNING     recovery requires FRESH verified evidence, not the clock or
                    the same stale record;
  7. FAIL-CLOSED    malformed/missing/sandbox-tier evidence is not certified and
                    not authorized.

The variance here is genuine divergence (the world's actual content differs from
the prediction after the write), not a pre-planted adversarial mismatch.
"""

import json
import pathlib
import subprocess

from telos.core.actions.certification import (
    CapabilityCertification, CertificationAction, CertificationTier,
    CertificationWorkflow, VerifiedOutcome,
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

CAP = "filesystem.write"
TARGET = "notes.md"
ORIGINAL = "alpha\nbeta\ngamma\n"
EDITED = "alpha\nbeta-edited\ngamma\n"
# A disjoint post-write state: an external actor changed the target between the
# write and the post-action observation (unexpected real-world variance).
VARIANCE = "zzzzzzzzzz\n"

SEAMS = ("adapter_execute", "executor_execute", "structured_write",
         "subprocess_run", "sandbox_request")


class _UnexpectedVarianceAdapter(FilesystemWriteAdapter):
    """A real write adapter whose world diverges after the write when armed.

    The write itself succeeds (the prediction is applied), then an EXTERNAL
    actor changes the target before the runner's post-action observation — the
    genuine "reality disproved the model" case. ``divergence`` is toggled so the
    same authority can first be primed with a matching action.

    Attributes:
        divergence: when True, overwrite the target after a successful write.
    """

    def __init__(self, executor: ActionExecutor, target: str, variance: str):
        """Bind the adapter.

        Args:
            executor: the governed ActionExecutor (workspace root = sandbox).
            target: the target file path.
            variance: the divergent content an external actor writes.
        """
        super().__init__(executor, target)
        self.variance = variance
        self.divergence = False

    def execute(self, proposal, *, firewall, capability=None,
                permitted_by="operator"):
        """Execute, then inject external divergence when armed.

        Args:
            proposal: the WorldActionProposal to execute.
            firewall: the DecisionFirewall the executor audits through.
            capability: optional CapabilityAuthorization for the per-tool gate.
            permitted_by: the authorization source.

        Returns:
            The ActionExecution audit record.
        """
        result = super().execute(proposal, firewall=firewall,
                                 capability=capability,
                                 permitted_by=permitted_by)
        if getattr(result, "allowed", False) and self.divergence:
            self._resolved_target().write_text(self.variance, encoding="utf-8")
        return result


def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a workspace with one original target file.

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
    """Restore the original target content.

    Args:
        sb: the workspace root.
    """
    pathlib.Path(sb, TARGET).write_text(ORIGINAL)


def _executor(sb: str) -> ActionExecutor:
    """A high-rate executor so the gap->authority mechanism is what is measured.

    Args:
        sb: the workspace root.

    Returns:
        The ActionExecutor.
    """
    return ActionExecutor(
        workspace_root=sb,
        rate_limiter=ToolRateLimiter(limits={"write_file": 1000},
                                     max_total=None))


def _proposal() -> WorldActionProposal:
    """A canonical filesystem-write proposal with the correct prediction.

    Returns:
        The WorldActionProposal.
    """
    return WorldActionProposal(
        capability=CAP, operation="write_file", target=TARGET,
        expected_result=EDITED,
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "degradation"}, confidence=0.9, risk=0.1)


def _approval(ident: str = "deg-1") -> LiveApproval:
    """A canonical per-action approval.

    Args:
        ident: the approval id.

    Returns:
        The LiveApproval.
    """
    return LiveApproval(CAP, TARGET, "write_file", "operator", ident)


def _certified() -> CapabilityCertification:
    """A LIVE-tier registry certifying filesystem.write.

    Returns:
        The CapabilityCertification.
    """
    return CapabilityCertification.from_certified_set(
        {CAP}, certified_by="test", evidence="unit",
        reason="unit certification", tier=CertificationTier.LIVE.value)


def _run(runner: WorldActionRunner, proposal: WorldActionProposal, cycle: int,
         ident: str = "deg") -> object:
    """Run one LIVE action with an isolated firewall (a supervised action).

    Args:
        runner: the WorldActionRunner.
        proposal: the proposal to run.
        cycle: the cycle stamp.
        ident: the approval id.

    Returns:
        The WorldActionResult.
    """
    runner.firewall = DecisionFirewall()
    return runner.run(proposal, ActionMode.LIVE, approval=_approval(ident),
                      cycle=cycle)


def _seam_counts(monkeypatch) -> dict:
    """Spy every execution seam so structural blocking is provable.

    Args:
        monkeypatch: the pytest monkeypatch fixture.

    Returns:
        A counter dict keyed by seam name.
    """
    counts = {name: 0 for name in SEAMS}
    real_adapter = FilesystemWriteAdapter.execute
    real_executor = ActionExecutor.execute
    real_write = ActionExecutor._execute_structured_write
    real_subprocess = subprocess.run

    def adapter_execute(self, *a, **k):
        counts["adapter_execute"] += 1
        return real_adapter(self, *a, **k)

    def executor_execute(self, *a, **k):
        counts["executor_execute"] += 1
        return real_executor(self, *a, **k)

    def structured_write(self, *a, **k):
        counts["structured_write"] += 1
        return real_write(self, *a, **k)

    def subprocess_run(*a, **k):
        counts["subprocess_run"] += 1
        return real_subprocess(*a, **k)

    def sandbox_request(self, *a, **k):
        raise AssertionError("a blocked action must never use the network sandbox")

    monkeypatch.setattr(FilesystemWriteAdapter, "execute", adapter_execute)
    monkeypatch.setattr(ActionExecutor, "execute", executor_execute)
    monkeypatch.setattr(ActionExecutor, "_execute_structured_write",
                        structured_write)
    monkeypatch.setattr(subprocess, "run", subprocess_run)
    monkeypatch.setattr("telos.core.actions.sandbox.NetworkSandbox.request",
                        sandbox_request)
    return counts


# ── 1. Detection ─────────────────────────────────────────────────────────────

def test_unexpected_variance_is_detected_as_fidelity_failure(tmp_path):
    """A reality/prediction contradiction is measured, not absorbed."""
    sb = _workspace(tmp_path)
    adapter = _UnexpectedVarianceAdapter(_executor(sb), TARGET, VARIANCE)
    authority = CapabilityAuthority()
    runner = WorldActionRunner(_executor(sb), adapter,
                               certification=_certified(),
                               firewall=DecisionFirewall(), authority=authority)
    adapter.divergence = True
    _reseed(sb)
    r = _run(runner, _proposal(), cycle=1)
    assert r.executed is True and r.action_allowed is True
    assert r.verification["matched"] is False
    assert r.reality_gap is not None and r.reality_gap > 0.5
    assert r.verification["observed"] == VARIANCE
    # The contradiction recalibrated authority downward (not ignored).
    change = r.authority_change
    assert change["changed"] is True
    assert change["status_before"] == "UNKNOWN"
    assert change["status_after"] in ("LIMITED", "FAIL")
    assert change["fidelity_after"] is not None
    assert change["fidelity_after"] < 0.5, (
        "a large divergence must reduce authority below the FAIL band")


# ── 2 + 3. Authority degradation and structural ACT blocking ─────────────────

def test_authority_degrades_pass_limited_fail_then_blocks_act(tmp_path,
                                                              monkeypatch):
    """PASS -> LIMITED -> FAIL as variance accumulates; FAIL blocks the ACT."""
    sb = _workspace(tmp_path)
    counts = _seam_counts(monkeypatch)
    adapter = _UnexpectedVarianceAdapter(_executor(sb), TARGET, VARIANCE)
    authority = CapabilityAuthority()
    runner = WorldActionRunner(_executor(sb), adapter,
                               certification=_certified(),
                               firewall=DecisionFirewall(), authority=authority)
    # Prime with one matching, non-divergent action -> PASS.
    _reseed(sb)
    prime = _run(runner, _proposal(), cycle=1, ident="prime")
    assert prime.reality_gap == 0.0
    st = authority.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.PASS and st.fidelity == 1.0
    # Now the world diverges every time. Each EXECUTED divergent action is one
    # step of the degradation; once authority FAILs the next action is blocked,
    # so no further evidence accumulates (the structural stop).
    adapter.divergence = True
    sequence = []
    blocked_at = None
    for cycle in (2, 3, 4, 5):
        _reseed(sb)
        rr = _run(runner, _proposal(), cycle=cycle, ident=f"v{cycle}")
        if rr.executed:
            sequence.append(authority.state(CAP, now_cycle=cycle).status)
        else:
            blocked_at = cycle
            break
    assert sequence == [CapabilityStatus.LIMITED, CapabilityStatus.FAIL]
    assert blocked_at == 4, (
        "divergence is recorded while authority holds, then ACT is blocked")
    # A FAIL authority structurally blocks the NEXT ACT: no NEW seam is reached
    # and the target keeps its pre-action bytes.
    before = pathlib.Path(sb, TARGET).read_text()
    baseline = dict(counts)
    blocked = _run(runner, _proposal(), cycle=10, ident="blocked")
    assert blocked.executed is False
    assert blocked.action_allowed is False
    assert "capability gate failed" in blocked.blocked_reason
    assert "model_fidelity" in blocked.blocked_reason
    assert blocked.authority_state["status"] == "FAIL"
    assert pathlib.Path(sb, TARGET).read_text() == before
    for seam in SEAMS:
        assert counts[seam] == baseline[seam], (
            f"blocked ACT must not touch seam {seam}")


# ── 4 + 5. Revocation and the read path ──────────────────────────────────────

def test_failure_streak_revokes_and_the_read_path_withholds(tmp_path):
    """A trailing failure streak revokes; the persisted read path honours it."""
    wf = CertificationWorkflow(min_successes=3, max_gap=0.2, window=5,
                               failure_streak=2)
    failures = [VerifiedOutcome(CAP, False, 0.9, cycle=4),
                VerifiedOutcome(CAP, False, 0.9, cycle=5)]
    decision = wf.evaluate(CAP, failures)
    assert decision.action is CertificationAction.REVOKE
    assert decision.evidence["failure_streak"] == 2
    registry = _certified()
    assert registry.is_live_certified(CAP) is True
    wf.apply(registry, decision)
    assert registry.is_live_certified(CAP) is False
    assert registry.is_certified(CAP) is False
    # Persist to a canonical file and read it back: the revocation holds on the
    # canonical read path (no stale record re-authorizes).
    canon = tmp_path / "canonical.json"
    registry.save(str(canon))
    reloaded = CapabilityCertification(path=str(canon))
    assert reloaded.is_live_certified(CAP) is False
    assert reloaded.certified_names() == []
    # A runner over the reloaded registry refuses LIVE (channel ON, approved).
    sb = _workspace(tmp_path)
    ex = _executor(sb)
    adapter = FilesystemWriteAdapter(ex, TARGET)
    runner = WorldActionRunner(ex, adapter, certification=reloaded,
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is False and "not CERTIFIED" in r.blocked_reason


def test_stale_falsified_authority_does_not_reauthorize(tmp_path, monkeypatch):
    """A FAILED authority must not silently pass by time alone."""
    counts = _seam_counts(monkeypatch)
    sb = _workspace(tmp_path)
    authority = CapabilityAuthority()
    authority.record(CAP, 0.9, cycle=100)  # one large divergence -> FAIL
    at_100 = authority.state(CAP, now_cycle=100)
    assert at_100.status is CapabilityStatus.FAIL
    # 301 cycles later the evidence is stale. A falsified window must stay
    # non-authorizing rather than decaying to the passing UNKNOWN bootstrap.
    stale = authority.state(CAP, now_cycle=401)
    assert stale.status is CapabilityStatus.FAIL, (
        "time alone must not restore a falsified capability's authority")
    assert stale.fidelity is None
    assert "stale after a falsified window" in stale.reason
    adapter = FilesystemWriteAdapter(_executor(sb), TARGET)
    runner = WorldActionRunner(_executor(sb), adapter,
                               certification=_certified(),
                               firewall=DecisionFirewall(), authority=authority)
    blocked = _run(runner, _proposal(), cycle=401, ident="stale")
    assert blocked.executed is False
    assert "model_fidelity" in blocked.blocked_reason
    assert counts["executor_execute"] == 0 and counts["structured_write"] == 0


def test_stale_never_falsified_authority_stays_act_then_learn(tmp_path):
    """A stale, never-falsified model stays UNKNOWN (act-then-learn preserved)."""
    authority = CapabilityAuthority()
    authority.record(CAP, 0.1, cycle=100)  # a good window -> PASS
    assert authority.state(CAP, now_cycle=100).status is CapabilityStatus.PASS
    stale = authority.state(CAP, now_cycle=401)
    assert stale.status is CapabilityStatus.UNKNOWN, (
        "a never-falsified model must remain able to act-then-learn")
    assert authority.capability_authorization(
        CAP, now_cycle=401).gate("model_fidelity").status is \
        CapabilityStatus.UNKNOWN


# ── 6. Re-earning requires fresh evidence ────────────────────────────────────

def test_recovery_requires_fresh_verified_evidence():
    """Authority is re-earned by fresh records, not by the clock."""
    authority = CapabilityAuthority()
    for cycle in range(1, 5):
        authority.record(CAP, 0.9, cycle=cycle)
    assert authority.state(CAP, now_cycle=4).status is CapabilityStatus.FAIL
    # Fresh verified successes fill the recent window -> authority recovers.
    seen_limited = False
    for i in range(12):
        authority.record(CAP, 0.0, cycle=10 + i)
        status = authority.state(CAP, now_cycle=10 + i).status
        if status is CapabilityStatus.LIMITED:
            seen_limited = True
    final = authority.state(CAP, now_cycle=30)
    assert seen_limited, "recovery passes through LIMITED"
    assert final.status is CapabilityStatus.PASS
    assert final.fidelity is not None and final.fidelity >= 0.7


# ── 7. Fail-closed on ambiguity ──────────────────────────────────────────────

def test_fail_closed_on_malformed_missing_and_sandbox_tier(tmp_path):
    """Malformed/missing/sandbox-tier evidence is never certification."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json")
    assert CapabilityCertification(path=str(bad)).certified_names() == []
    absent = CapabilityCertification(path=str(tmp_path / "absent.json"))
    assert absent.is_live_certified(CAP) is False
    # A sandbox-tier record written into the canonical file is downgraded.
    sandbox_reg = CapabilityCertification.from_certified_set(
        {CAP}, certified_by="campaign", evidence="sandbox",
        tier=CertificationTier.SANDBOX.value)
    canon = tmp_path / "canon_sandbox.json"
    sandbox_reg.save(str(canon))
    reloaded = CapabilityCertification(path=str(canon))
    assert reloaded.is_certified(CAP) is False
    assert reloaded.is_live_certified(CAP) is False
    # An untested authority claims no fidelity (UNKNOWN, not PASS).
    fresh = CapabilityAuthority().state(CAP)
    assert fresh.status is CapabilityStatus.UNKNOWN
    assert fresh.fidelity is None
    assert json.loads(json.dumps(fresh.to_dict()))["status"] == "UNKNOWN"
