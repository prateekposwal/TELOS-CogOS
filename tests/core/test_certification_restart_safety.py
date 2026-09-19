"""
Restart safety + revocation/recovery semantics for capability authority.

FALSIFIER UNDER TEST: a capability whose model has been FALSIFIED must not regain
effective authority through a process restart, a stale canonical LIVE-CERTIFIED
record, the passage of time, evidence ordering, or the disappearance of negative
state — only through legitimate NEW recertification evidence.

The runtime authority (measured Reality Gap) is automatic and fail-closed; the
canonical certification registry is operator-gated. This suite pins the asymmetry:
the RUNTIME falsification state is durable across restart (evidence), while the
CANONICAL registry mutation remains an explicit operator act. Certification is
never activation.
"""

import json
import pathlib
import subprocess

import numpy as np

from telos.core.actions.certification import (
    CapabilityCertification, CertificationAction, CertificationTier,
    CertificationWorkflow, VerifiedOutcome,
)
from telos.core.actions.executor import ActionExecutor
from telos.core.actions.live_canary import LiveCanary
from telos.core.actions.rate_limit import ToolRateLimiter
from telos.core.actions.reality_loop import CapabilityAuthority
from telos.core.actions.world_adapter import FilesystemWriteAdapter
from telos.core.actions.world_action import (
    ActionMode, LiveApproval, WorldActionProposal, WorldActionRunner,
)
from telos.core.governance.capability_authorization import CapabilityStatus
from telos.core.governance.firewall import DecisionFirewall
from telos.world.epistemic import RealityGapTracker

CAP = "filesystem.write"
TARGET = "notes.md"
ORIGINAL = "alpha\nbeta\ngamma\n"
EDITED = "alpha\nbeta-edited\ngamma\n"
SEAMS = ("adapter_execute", "executor_execute", "structured_write",
         "subprocess_run", "sandbox_request")


# ── fixtures ────────────────────────────────────────────────────────────────

def _workspace(tmp_path: pathlib.Path) -> str:
    """Create a sandbox workspace with one target file."""
    sb = tmp_path / "ws"
    sb.mkdir()
    (sb / TARGET).write_text(ORIGINAL)
    return str(sb)


def _canonical(tmp_path: pathlib.Path, *, certified: bool = True,
               revoke_reason: str = "") -> str:
    """Write a canonical registry (optionally LIVE-certified) and return its path."""
    reg = CapabilityCertification.from_certified_set(
        {CAP} if certified else set(), certified_by="operator",
        evidence="earned LIVE", reason="canonical",
        tier=CertificationTier.LIVE.value)
    if revoke_reason:
        reg.revoke(CAP, reason=revoke_reason)
    path = tmp_path / "canonical.json"
    reg.save(str(path))
    return str(path)


def _proposal() -> WorldActionProposal:
    """A canonical filesystem-write proposal with the correct prediction."""
    return WorldActionProposal(
        capability=CAP, operation="write_file", target=TARGET,
        expected_result=EDITED,
        params={"old_lines": ["beta"], "new_lines": ["beta-edited"]},
        evidence={"source": "restart-safety"}, confidence=0.9, risk=0.1)


def _approval(ident: str = "rs-1") -> LiveApproval:
    """A canonical per-action approval."""
    return LiveApproval(CAP, TARGET, "write_file", "operator", ident)


def _runner(sb: str, canonical_path: str, authority) -> WorldActionRunner:
    """Build a runner over the sandbox with the given registry + authority."""
    ex = ActionExecutor(workspace_root=sb, rate_limiter=ToolRateLimiter(
        limits={"write_file": 1000}, max_total=None))
    adapter = FilesystemWriteAdapter(ex, TARGET)
    return WorldActionRunner(ex, adapter,
                             certification=CapabilityCertification(
                                 path=canonical_path),
                             firewall=DecisionFirewall(), authority=authority)


def _dry(runner: WorldActionRunner, cycle: int):
    """A side-effect-free authorization decision (DRY_RUN never executes)."""
    return runner.run(_proposal(), ActionMode.DRY_RUN, approval=_approval(),
                      cycle=cycle)


def _install_seam_spies(monkeypatch) -> dict:
    """Spy every real execution seam so structural refusal is provable."""
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
        raise AssertionError("a refused action must never use the network sandbox")

    monkeypatch.setattr(FilesystemWriteAdapter, "execute", adapter_execute)
    monkeypatch.setattr(ActionExecutor, "execute", executor_execute)
    monkeypatch.setattr(ActionExecutor, "_execute_structured_write",
                        structured_write)
    monkeypatch.setattr(subprocess, "run", subprocess_run)
    monkeypatch.setattr("telos.core.actions.sandbox.NetworkSandbox.request",
                        sandbox_request)
    return counts


# ── A. Falsification immediately removes effective authority ────────────────

def test_falsifying_evidence_immediately_removes_authority(tmp_path):
    """A. One measured divergence -> FAIL -> the next ACT is refused."""
    authority = CapabilityAuthority()
    authority.record(CAP, 0.9, cycle=1)
    st = authority.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.FAIL
    assert st.ever_falsified is True
    r = _dry(_runner(_workspace(tmp_path), _canonical(tmp_path), authority), 1)
    assert r.authorized is False
    assert "model_fidelity" in r.authorization_reason


# ── B. ACT refusal does not depend on canonical registry mutation ────────────

def test_act_refusal_does_not_depend_on_canonical_registry_mutation(
        tmp_path, monkeypatch):
    """B. Canonical registry UNCHANGED (LIVE-CERTIFIED) yet ACT is refused."""
    counts = _install_seam_spies(monkeypatch)
    sb = _workspace(tmp_path)
    canonical = _canonical(tmp_path)
    assert CapabilityCertification(path=canonical).is_live_certified(CAP) is True
    authority = CapabilityAuthority()
    authority.record(CAP, 0.9, cycle=1)
    runner = _runner(sb, canonical, authority)
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval(), cycle=1)
    assert r.executed is False and r.action_allowed is False
    assert "model_fidelity" in r.blocked_reason
    assert counts["executor_execute"] == 0 and counts["structured_write"] == 0
    assert pathlib.Path(sb, TARGET).read_text() == ORIGINAL
    # The canonical registry was never mutated by the runtime withholding.
    assert CapabilityCertification(path=canonical).is_live_certified(CAP) is True


# ── C. Restart cannot resurrect falsified authority ─────────────────────────

def test_restart_cannot_resurrect_falsified_authority(tmp_path):
    """C. Falsify -> withhold -> restart -> authority still withheld."""
    sb = _workspace(tmp_path)
    canonical = _canonical(tmp_path)
    ev = tmp_path / "authority_evidence.json"

    pre = CapabilityAuthority(state_path=str(ev))
    pre.record(CAP, 0.9, cycle=100)
    assert pre.state(CAP, now_cycle=100).status is CapabilityStatus.FAIL
    r_pre = _dry(_runner(sb, canonical, pre), 100)
    assert r_pre.authorized is False

    # Process restart: a FRESH authority over the SAME durable evidence path.
    post = CapabilityAuthority(state_path=str(ev))
    st = post.state(CAP, now_cycle=100)
    assert st.status is CapabilityStatus.FAIL
    assert st.ever_falsified is True
    r_post = _dry(_runner(sb, canonical, post), 100)
    assert r_post.authorized is False, "restart resurrected falsified authority"
    # The canonical registry still says LIVE-CERTIFIED — authority is separate.
    assert CapabilityCertification(path=canonical).is_live_certified(CAP) is True


def test_restart_between_degradation_and_canonical_persistence(tmp_path):
    """Restart AFTER runtime degradation but BEFORE any canonical revocation."""
    sb = _workspace(tmp_path)
    canonical = _canonical(tmp_path)  # never revoked: the operator has not acted
    ev = tmp_path / "authority_evidence.json"

    a1 = CapabilityAuthority(state_path=str(ev))
    for cycle in range(1, 4):
        a1.record(CAP, 0.9, cycle=cycle)
    assert a1.state(CAP, now_cycle=3).status is CapabilityStatus.FAIL

    a2 = CapabilityAuthority(state_path=str(ev))  # restart
    assert a2.state(CAP, now_cycle=3).status is CapabilityStatus.FAIL
    assert _dry(_runner(sb, canonical, a2), 3).authorized is False
    assert CapabilityCertification(path=canonical).is_live_certified(CAP) is True


# ── D. Time alone cannot restore falsified authority ────────────────────────

def test_time_alone_cannot_restore_falsified_authority(tmp_path):
    """D. Far beyond the staleness window, a falsified authority stays FAIL."""
    ev = tmp_path / "authority_evidence.json"
    a = CapabilityAuthority(state_path=str(ev))
    a.record(CAP, 0.9, cycle=10)
    restarted = CapabilityAuthority(state_path=str(ev))
    far = restarted.state(CAP, now_cycle=10 + 10_000)
    assert far.status is CapabilityStatus.FAIL
    assert far.fidelity is None
    assert "stale" in far.reason.lower()


# ── E. Stale positive evidence cannot outrank newer falsification ───────────

def _tracker_with(model_id: str, gap: float, cycle: int) -> RealityGapTracker:
    """A tracker holding one encoded measurement for a model."""
    t = RealityGapTracker()
    t.record(model_id, np.array([1.0]), np.array([1.0 - gap]), cycle=cycle)
    return t


def test_newer_falsification_outranks_stale_positive_persisted_evidence():
    """E. Merge is recency-first: an older PASS cannot overwrite newer FAIL."""
    mid = "world_action:filesystem.write"
    persisted = _tracker_with(mid, 0.0, cycle=100)     # old PASS
    live = _tracker_with(mid, 0.9, cycle=200)          # newer FAIL
    live.load_state(persisted.to_state())
    m = live.model(mid)
    assert m.last_validation_cycle == 200
    assert m.ever_falsified is True
    assert m.recent_mean_gap > 0.6


def test_newer_falsification_is_adopted_over_stale_positive():
    """E. The inverse order: newer persisted FAIL is adopted over old PASS."""
    mid = "world_action:filesystem.write"
    live = _tracker_with(mid, 0.0, cycle=100)          # old PASS
    persisted = _tracker_with(mid, 0.9, cycle=200)     # newer FAIL on disk
    live.load_state(persisted.to_state())
    m = live.model(mid)
    assert m.last_validation_cycle == 200
    assert m.ever_falsified is True


def test_equal_timestamp_ambiguity_resolves_more_restrictive():
    """E/I. Equal timestamps -> the state that withholds MORE authority wins."""
    mid = "world_action:filesystem.write"
    live = _tracker_with(mid, 0.9, cycle=200)          # falsified
    stored_positive = _tracker_with(mid, 0.0, cycle=200)  # PASS, same cycle
    live.load_state(stored_positive.to_state())
    assert live.model(mid).ever_falsified is True, (
        "ambiguous ordering must fail closed, never toward more authority")


# ── F. Canonical revocation persistence only maintains/reduces authority ────

def test_canonical_revocation_persistence_only_maintains_or_reduces(tmp_path):
    """F. A revoked registry reloads revoked; save never invents certification."""
    canonical = _canonical(tmp_path, revoke_reason="reality disproved the model")
    reloaded = CapabilityCertification(path=canonical)
    assert reloaded.is_live_certified(CAP) is False
    assert reloaded.is_certified(CAP) is False
    # Re-saving a revoked registry cannot increase authority.
    again = tmp_path / "again.json"
    reloaded.save(str(again))
    assert CapabilityCertification(path=str(again)).is_certified(CAP) is False
    raw = json.loads(pathlib.Path(again).read_text())
    assert all(r["certified"] is False for r in raw["records"])


def test_persisted_revocation_beats_stale_positive_authority(tmp_path):
    """F. Canonical revocation withholds LIVE even when authority reads PASS."""
    sb = _workspace(tmp_path)
    canonical = _canonical(tmp_path, revoke_reason="reality disproved the model")
    authority = CapabilityAuthority()
    authority.record(CAP, 0.0, cycle=1)  # a matching (stale positive) outcome
    assert authority.state(CAP, now_cycle=1).status is CapabilityStatus.PASS
    # Canonical revocation is the operator gate; it holds regardless of authority.
    # (DRY_RUN reports the would-be decision before certification; LIVE enforces.)
    live = _runner(sb, canonical, authority).run(
        _proposal(), ActionMode.LIVE, approval=_approval(), cycle=1)
    assert live.executed is False and "not CERTIFIED" in live.blocked_reason
    assert pathlib.Path(sb, TARGET).read_text() == ORIGINAL


# ── G. Certification alone cannot activate execution ────────────────────────

def test_certification_alone_cannot_activate_execution(tmp_path, monkeypatch):
    """G. LIVE-CERTIFIED + approval but channel OFF -> no seam is touched."""
    counts = _install_seam_spies(monkeypatch)
    sb = _workspace(tmp_path)
    adapter = FilesystemWriteAdapter(ActionExecutor(workspace_root=sb), TARGET)
    runner = WorldActionRunner(None, adapter,
                               certification=CapabilityCertification(
                                   path=_canonical(tmp_path)),
                               firewall=DecisionFirewall())
    r = runner.run(_proposal(), ActionMode.LIVE, approval=_approval())
    assert r.executed is False and r.action_allowed is False
    assert all(counts[s] == 0 for s in SEAMS)
    assert pathlib.Path(sb, TARGET).read_text() == ORIGINAL


# ── H. Recovery requires new evidence, not disappearance of negative state ──

def test_recovery_requires_new_evidence_not_disappearance(tmp_path):
    """H. No clock/restart/old-success restores; fresh verified evidence does."""
    ev = tmp_path / "authority_evidence.json"
    a = CapabilityAuthority(state_path=str(ev))
    for cycle in range(1, 4):
        a.record(CAP, 0.9, cycle=cycle)
    assert a.state(CAP, now_cycle=3).status is CapabilityStatus.FAIL
    # Time + restart: negative state does not "disappear".
    restarted = CapabilityAuthority(state_path=str(ev))
    assert restarted.state(CAP, now_cycle=5_000).status is CapabilityStatus.FAIL
    # Legitimate recovery: FRESH verified successes fill the recent window.
    for i in range(20):
        restarted.record(CAP, 0.0, cycle=6_000 + i)
    recovered = restarted.state(CAP, now_cycle=6_019)
    assert recovered.status in (CapabilityStatus.LIMITED, CapabilityStatus.PASS)
    assert recovered.fidelity is not None and recovered.fidelity >= 0.5


def test_recovery_never_automatic_from_canonical_still_certified(tmp_path):
    """H. A still-certified canonical registry is not evidence of recovery."""
    canonical = _canonical(tmp_path)
    ev = tmp_path / "authority_evidence.json"
    a = CapabilityAuthority(state_path=str(ev))
    a.record(CAP, 0.9, cycle=1)
    assert CapabilityCertification(path=canonical).is_live_certified(CAP) is True
    # No new evidence is supplied; certification alone does not re-authorize.
    assert a.state(CAP, now_cycle=100).status is CapabilityStatus.FAIL


# ── I. Ambiguous/corrupt/missing state resolves fail-closed ─────────────────

def test_corrupt_authority_store_fails_closed(tmp_path):
    """I. An unreadable configured store withholds authority (FAIL), not bootstrap."""
    ev = tmp_path / "authority_evidence.json"
    ev.write_text("{not-json")
    a = CapabilityAuthority(state_path=str(ev))
    st = a.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.FAIL
    assert "unreadable" in st.reason or "malformed" in st.reason
    r = _dry(_runner(_workspace(tmp_path), _canonical(tmp_path), a), 1)
    assert r.authorized is False


def test_incomplete_revocation_record_fails_closed(tmp_path):
    """I. count>0 with no measured gaps is malformed -> fail closed."""
    ev = tmp_path / "authority_evidence.json"
    ev.write_text(json.dumps({"models": {
        "world_action:filesystem.write": {
            "validation_count": 5, "total_gap": 4.5, "gap_history": [],
            "ever_falsified": True, "last_validation_cycle": 9,
        }}}))
    a = CapabilityAuthority(state_path=str(ev))
    assert a.state(CAP, now_cycle=9).status is CapabilityStatus.FAIL


def test_missing_authority_store_is_first_run_bootstrap(tmp_path):
    """I. An ABSENT store is a genuine first run (UNKNOWN), not recovery."""
    ev = tmp_path / "does_not_exist.json"
    a = CapabilityAuthority(state_path=str(ev))
    st = a.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.UNKNOWN
    assert st.fidelity is None


def test_duplicate_and_reordered_evidence_survive_restart(tmp_path):
    """I/3. Duplicate + out-of-order measurements persist and stay restrictive."""
    ev = tmp_path / "authority_evidence.json"
    a = CapabilityAuthority(state_path=str(ev))
    a.record(CAP, 0.9, cycle=5)   # out of order
    a.record(CAP, 0.9, cycle=3)
    a.record(CAP, 0.9, cycle=5)   # duplicate
    restarted = CapabilityAuthority(state_path=str(ev))
    st = restarted.state(CAP, now_cycle=5)
    assert st.status is CapabilityStatus.FAIL
    assert st.validations == 3
    assert st.ever_falsified is True


# ── Operator persistence: explicit revocation survives restart ──────────────

def test_explicit_canonical_revocation_survives_restart_and_is_auditable(tmp_path):
    """Operator persistence: revocation is recorded, durable, and fail-closed."""
    canonical = _canonical(tmp_path)
    reg = CapabilityCertification(path=canonical)
    assert reg.is_live_certified(CAP) is True
    rec = reg.revoke(CAP, reason="operator: reality disproved the model",
                     certified_by="operator:prateek")
    reg.save(canonical)
    reloaded = CapabilityCertification(path=canonical)
    assert reloaded.is_live_certified(CAP) is False
    written = reloaded.record_for(CAP)
    assert written is not None and written.certified is False
    assert written.certified_by == "operator:prateek"
    assert "operator" in written.reason
    # Deterministic recertification path: an operator can explicitly re-certify.
    wf = CertificationWorkflow(min_successes=1, max_gap=0.2, window=1,
                               failure_streak=2)
    good = [VerifiedOutcome(CAP, True, 0.0, cycle=10)]
    dec = wf.evaluate(CAP, good)
    assert dec.action is CertificationAction.CERTIFY
    wf.apply(reloaded, dec, cycle=10)
    assert reloaded.is_live_certified(CAP) is True


# ── LiveCanary wiring: production authority is durable ──────────────────────

def test_live_canary_wires_durable_authority_state(tmp_path):
    """The canary's authority persists evidence at the configured path."""
    ev = tmp_path / "authority_evidence.json"
    canary = LiveCanary(workspace_root=None, authority_state_path=str(ev))
    assert canary.config.authority_state_path == str(ev)
    canary._authority.record(CAP, 0.9, cycle=1)
    assert ev.exists()
    reloaded = CapabilityAuthority(state_path=str(ev))
    assert reloaded.state(CAP, now_cycle=1).status is CapabilityStatus.FAIL
