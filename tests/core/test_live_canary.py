"""
The bounded live-producer canary + the two-tier certification state.

PATTERN UNDER TEST (earn LIVE from LIVE, bounded and fail-closed): the sandbox
certification is preserved as evidence but NEVER promoted into the canonical
LIVE registry; the canonical loader refuses a sandbox-tier record. The canary is
opt-in/default-OFF, bounded, disposable-target-only, reversible, and every live
action goes through the real WorldActionRunner (certification + per-action
approval + gates). A refused canary reaches no execution seam.
"""

import json
import pathlib
import subprocess

import pytest

from telos.core.actions.certification import (
    CertificationRecord, CertificationTier, CapabilityCertification,
    DEFAULT_SANDBOX_EVIDENCE_PATH, load_sandbox_evidence,
)
from telos.core.actions.executor import ActionExecutor
from telos.core.actions.live_canary import (
    CAPABILITY, CANARY_TARGET, LiveCanary, canary_enabled,
)
from telos.core.actions.world_adapter import FilesystemWriteAdapter

TARGET_CONTENT = ("# TELOS canary target (disposable)\n\n"
                  "canary line one\ncanary line two\ncanary line three\n")


def _sandbox(tmp_path: pathlib.Path) -> str:
    """Create a disposable sandbox workspace with the canary target.

    Args:
        tmp_path: the pytest temp directory.

    Returns:
        The sandbox root path string.
    """
    ws = tmp_path / "sandbox"
    ws.mkdir()
    (ws / CANARY_TARGET).write_text(TARGET_CONTENT)
    return str(ws)


def _sandbox_evidence(tmp_path: pathlib.Path, *,
                      state: str = "SANDBOX-CERTIFIED",
                      certified: bool = True) -> str:
    """Write a sandbox-evidence artifact and return its path.

    Args:
        tmp_path: the pytest temp directory.
        state: the declared sandbox state.
        certified: whether the record is certified.

    Returns:
        The artifact path (inside tmp_path).
    """
    path = tmp_path / "sandbox_certification.json"
    path.write_text(json.dumps({
        "tier": "SANDBOX",
        "state": state,
        "capability": CAPABILITY,
        "canonical_registry_promoted": False,
        "variance_evidence": {"revocation_demonstrated": True},
        "records": [{
            "capability": CAPABILITY, "certified": certified,
            "tier": "SANDBOX", "certified_by": "test",
            "reason": "test sandbox evidence",
        }],
    }))
    return str(path)


def _canary(tmp_path: pathlib.Path, *, workspace: str = None,
            evidence: str = None, max_actions: int = 3,
            target: str = CANARY_TARGET, persist_live: bool = False,
            canonical_path: str = None) -> LiveCanary:
    """Build an enabled canary wired to tmp artifacts.

    Args:
        tmp_path: the pytest temp directory.
        workspace: the sandbox root (defaults to a fresh one).
        evidence: the sandbox-evidence path (defaults to a fresh one).
        max_actions: the live-action bound.
        target: the designated target.
        persist_live: whether persistence is enabled.
        canonical_path: an isolated canonical registry path.

    Returns:
        The LiveCanary.
    """
    ws = workspace or _sandbox(tmp_path)
    ev = evidence or _sandbox_evidence(tmp_path)
    return LiveCanary(
        workspace_root=ws, sandbox_root=ws, enabled=True, max_actions=max_actions,
        min_interval_cycles=1, target=target,
        artifact_path=str(tmp_path / "live_canary.json"),
        sandbox_evidence_path=ev,
        canonical_path=canonical_path or str(tmp_path / "canonical.json"),
        persist_live=persist_live,
    )


def _spies(monkeypatch) -> dict:
    """Spy the execution seams (delegating to the real implementations).

    Args:
        monkeypatch: the pytest monkeypatch fixture.

    Returns:
        A counter dict.
    """
    counts = {"adapter_execute": 0, "executor_execute": 0,
              "structured_write": 0, "sandbox_request": 0}
    real_adapter = FilesystemWriteAdapter.execute
    real_executor = ActionExecutor.execute
    real_write = ActionExecutor._execute_structured_write

    def adapter_execute(self, *a, **k):
        counts["adapter_execute"] += 1
        return real_adapter(self, *a, **k)

    def executor_execute(self, *a, **k):
        counts["executor_execute"] += 1
        return real_executor(self, *a, **k)

    def structured_write(self, *a, **k):
        counts["structured_write"] += 1
        return real_write(self, *a, **k)

    def sandbox_request(self, *a, **k):
        counts["sandbox_request"] += 1
        raise AssertionError("the canary must never use the network sandbox")

    monkeypatch.setattr(FilesystemWriteAdapter, "execute", adapter_execute)
    monkeypatch.setattr(ActionExecutor, "execute", executor_execute)
    monkeypatch.setattr(ActionExecutor, "_execute_structured_write",
                        structured_write)
    monkeypatch.setattr("telos.core.actions.sandbox.NetworkSandbox.request",
                        sandbox_request)
    return counts


# ── Part 1: two-tier state ───────────────────────────────────────────────

def test_canonical_loader_downgrades_a_sandbox_record(tmp_path):
    """A sandbox-tier record in the canonical file is NOT LIVE certification."""
    path = tmp_path / "canon.json"
    path.write_text(json.dumps({
        "records": [{"capability": CAPABILITY, "certified": True,
                     "tier": "SANDBOX"}],
        "certified": [],
    }))
    reg = CapabilityCertification(path=str(path))
    assert reg.is_certified(CAPABILITY) is False
    assert reg.is_live_certified(CAPABILITY) is False
    assert reg.certified_names() == []
    rec = reg.record_for(CAPABILITY)
    assert rec is not None and rec.certified is False


def test_canonical_loader_honours_a_live_record(tmp_path):
    """A LIVE-tier record is the only kind that certifies."""
    path = tmp_path / "canon.json"
    path.write_text(json.dumps({
        "records": [{"capability": CAPABILITY, "certified": True,
                     "tier": "LIVE"}],
    }))
    reg = CapabilityCertification(path=str(path))
    assert reg.is_live_certified(CAPABILITY) is True
    assert reg.certified_names() == [CAPABILITY]


def test_is_certified_at_distinguishes_tiers(tmp_path):
    """The tier predicate is exact."""
    reg = CapabilityCertification(records={})
    reg.store(CertificationRecord(capability=CAPABILITY, certified=True,
                                  tier=CertificationTier.SANDBOX.value))
    assert reg.is_certified_at(CAPABILITY, CertificationTier.SANDBOX) is True
    assert reg.is_certified_at(CAPABILITY, CertificationTier.LIVE) is False
    assert reg.is_live_certified(CAPABILITY) is False


def test_load_sandbox_evidence_reads_and_fails_closed(tmp_path):
    """The scoped sandbox reader loads sandbox records; absent => empty."""
    good = _sandbox_evidence(tmp_path)
    reg = load_sandbox_evidence(good)
    assert reg.is_certified_at(CAPABILITY, CertificationTier.SANDBOX) is True
    empty = load_sandbox_evidence(str(tmp_path / "absent.json"))
    assert empty.certified_names() == []
    assert DEFAULT_SANDBOX_EVIDENCE_PATH.endswith("sandbox_certification.json")


# ── Part 2: canary bounds + fail-closed ──────────────────────────────────

def test_canary_default_off_runs_nothing(tmp_path, monkeypatch):
    """Unset/unknown opt-in => the canary never runs and writes no artifact."""
    monkeypatch.delenv("TELOS_CANARY_ENABLED", raising=False)
    assert canary_enabled() is False
    c = LiveCanary(workspace_root=_sandbox(tmp_path),
                   artifact_path=str(tmp_path / "x.json"),
                   sandbox_evidence_path=_sandbox_evidence(tmp_path))
    assert c.config.enabled is False
    assert c.maybe_run(cycle=1) is None
    assert not (tmp_path / "x.json").exists()


def test_canary_refuses_wrong_or_outside_target(tmp_path, monkeypatch):
    """A non-designated target is refused and reaches no execution seam."""
    counts = _spies(monkeypatch)
    c = _canary(tmp_path, target="other.md")
    rec = c.run_script(cycle=1)
    assert rec["outcome"] == "REFUSED"
    assert rec["refusal_reason"] == "target_not_designated_canary_file"
    assert rec["executed_any"] is False
    assert all(v == 0 for v in counts.values()), counts


def test_canary_refuses_without_sandbox_evidence(tmp_path, monkeypatch):
    """No preserved sandbox evidence => refuse, no execution seam."""
    counts = _spies(monkeypatch)
    c = _canary(tmp_path, evidence=str(tmp_path / "absent.json"))
    rec = c.run_script(cycle=1)
    assert rec["refusal_reason"] == "sandbox_not_certified"
    assert all(v == 0 for v in counts.values()), counts


def test_canary_full_trace_is_genuine_and_reversible(tmp_path, monkeypatch):
    """The full trace runs through the governed path and the bar is met."""
    counts = _spies(monkeypatch)
    ws = _sandbox(tmp_path)
    c = _canary(tmp_path, workspace=ws)
    rec = c.run_script(cycle=7)
    kinds = [x["kind"] for x in rec["cases"]]
    assert kinds == ["positive", "negative", "refusal"]
    pos = rec["cases"][0]
    neg = rec["cases"][1]
    ref = rec["cases"][2]
    assert pos["execution"]["executed"] is True and pos["reality_gap"] == 0.0
    assert pos["admission"]["admitted"] is True
    assert neg["execution"]["executed"] is True and neg["reality_gap"] > 0.5
    assert neg["admission"]["admitted"] is False
    assert ref["execution"]["executed"] is False
    assert ref["execution"]["blocked_reason"] is not None
    # Genuine post-action observation: sha matches the independent disk read.
    assert (pos["observation"]["observation_sha256"]
            == pos["observation"]["disk_sha256"])
    # Full trace fields present: prediction/execution/observation/gap/authority.
    for case in rec["cases"]:
        assert "prediction" in case and "execution" in case
        assert "observation" in case and "reality_gap" in case
        assert "authority" in case and "admission" in case
    assert rec["live_certification"]["live_bar_met"] is True
    assert rec["reversibility"]["reversible"] is True
    # The canary went through the governed executor (no bypass) — and only the
    # two executed cases touched the write seam.
    assert counts["adapter_execute"] == 2
    assert counts["executor_execute"] == 2
    assert counts["structured_write"] == 2
    assert counts["sandbox_request"] == 0
    # The sandbox target is byte-identical to before.
    assert pathlib.Path(ws, CANARY_TARGET).read_text() == TARGET_CONTENT


def test_canary_respects_the_action_bound(tmp_path):
    """max_actions caps the script; a partial script cannot meet the bar."""
    c = _canary(tmp_path, max_actions=1)
    rec = c.run_script(cycle=1)
    assert [x["kind"] for x in rec["cases"]] == ["positive"]
    assert rec["live_certification"]["live_bar_met"] is False


def test_canary_maybe_run_throttles_to_interval(tmp_path):
    """Once complete, the canary never runs again (hard stop)."""
    c = _canary(tmp_path)
    first = c.maybe_run(cycle=1)
    assert first is not None and first["outcome"] == "RAN"
    assert c.maybe_run(cycle=2) is None
    assert c.maybe_run(cycle=10_000) is None


# ── Part 3: LIVE-CERTIFIED persistence ───────────────────────────────────

def test_persist_refuses_when_bar_not_met(tmp_path):
    """A canary run that does not meet the bar never writes the registry."""
    c = _canary(tmp_path, max_actions=1)
    c.run_script(cycle=1)
    out = c.persist_live_certification()
    assert out["persisted"] is False
    assert not (tmp_path / "canonical.json").exists()


def test_persist_writes_live_record_when_bar_met(tmp_path):
    """A satisfied live bar may be persisted canonically as tier=LIVE."""
    c = _canary(tmp_path, persist_live=True)
    c.run_script(cycle=7)
    out = c.persist_live_certification()
    assert out["persisted"] is True
    reg = CapabilityCertification(path=out["path"])
    assert reg.is_live_certified(CAPABILITY) is True
    rec = reg.record_for(CAPABILITY)
    assert rec.tier == CertificationTier.LIVE.value
    assert rec.evidence_detail["variance"]["satisfied"] is True


# ── producer wiring (default OFF; opt-in constructs) ─────────────────────

def test_producer_canary_is_default_off(monkeypatch):
    """The producer constructs no canary unless explicitly opted in."""
    from types import SimpleNamespace
    from telos.dashboard.producer import DashboardProducer
    monkeypatch.delenv("TELOS_CANARY_ENABLED", raising=False)
    p = DashboardProducer.__new__(DashboardProducer)
    p._canary = None
    p._pipeline = SimpleNamespace(config=SimpleNamespace(
        tool_workspace="/tmp/telos_tool_sandbox", action_executor=None))
    p._build_canary()
    assert p._canary is None


def test_producer_canary_is_built_when_opted_in(monkeypatch):
    """Opt-in constructs the bounded canary (still nothing runs until cycles)."""
    from types import SimpleNamespace
    from telos.dashboard.producer import DashboardProducer
    monkeypatch.setenv("TELOS_CANARY_ENABLED", "1")
    p = DashboardProducer.__new__(DashboardProducer)
    p._canary = None
    p._pipeline = SimpleNamespace(config=SimpleNamespace(
        tool_workspace="/tmp/telos_tool_sandbox", action_executor=None))
    p._build_canary()
    assert p._canary is not None
    assert p._canary.config.enabled is True
    assert p._canary.config.max_actions >= 1
