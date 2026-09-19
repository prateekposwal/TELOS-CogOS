"""
Durability contract tests — ONE integrity-verifiable authority/evidence boundary.

Pins the Λ6.7 durability contract (`telos/core/actions/durability.py`):
  * the envelope classifies FIRST_RUN / LOADED / CORRUPTED honestly;
  * corruption and tampering never collapse into a clean first run;
  * capability authority and the pipeline's Reality Gap evidence survive a
    restart when (and only when) durability is explicitly configured;
  * production construction cannot be accidentally ephemeral.

Falsifier under test: safety-critical authority/evidence state must be durable,
integrity-verifiable, restart-safe and fail-closed, while tests and intentional
ephemeral contexts stay lightweight.
"""

import json
import pathlib
from unittest.mock import MagicMock

import numpy as np
import pytest

from telos.core.actions.durability import (
    KIND_AUTHORITY_EVIDENCE, SCHEMA_VERSION, DurabilityMode, StateOutcome,
    atomic_write_state, build_envelope, payload_checksum, read_state,
)
from telos.core.actions.reality_loop import CapabilityAuthority
from telos.core.governance.capability_authorization import CapabilityStatus
from telos.core.phases.act import ActPhase
from telos.core.phases.base import PhaseContext
from telos.intent_ir import IntentIR
from telos.world.epistemic import RealityGapTracker

CAP = "filesystem.write"
MID = "world_action:filesystem.write"


# ── minimal act-phase doubles (mirror tests/core/test_act.py) ───────────────

class _Verdict:
    validated = True
    decision_integrity = 0.9
    mission_drift = 0.1
    escalation_requested = False
    escalation_reason = None
    blocking_validator = None
    signals = []


class _FirewallVerdict:
    blocked = False
    blocked_by = None
    blocker_validators = []
    governance_signals = []
    passed = True


def _run_act(pipeline, ctx):
    """Run the real ActPhase over a pipeline + context.

    Args:
        pipeline: the (real or mock) pipeline.
        ctx: the phase context.

    Returns:
        The context after ActPhase.execute().
    """
    ActPhase().execute(pipeline, ctx)
    return ctx


# ── envelope: classification is first-class ─────────────────────────────────

def test_envelope_round_trip_is_loaded(tmp_path):
    """A written envelope reads back LOADED with the exact payload."""
    path = tmp_path / "state.json"
    payload = {"models": {MID: {"validation_count": 1}}}
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, payload)
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.LOADED
    assert res.payload == payload


def test_missing_store_is_first_run(tmp_path):
    """An absent store is an honest cold start, NOT corrupted."""
    res = read_state(str(tmp_path / "absent.json"),
                     expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.FIRST_RUN
    assert res.payload is None


def test_malformed_store_is_corrupted(tmp_path):
    """Unparseable bytes are CORRUPTED (fail closed), never first run."""
    path = tmp_path / "state.json"
    path.write_text("{not-json")
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.CORRUPTED
    assert "unreadable" in res.reason or "malformed" in res.reason


def test_checksum_tamper_is_corrupted(tmp_path):
    """Editing the payload without updating the checksum is detected."""
    path = tmp_path / "state.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}})
    raw = json.loads(path.read_text())
    raw["payload"]["models"][MID] = {"validation_count": 9,
                                     "gap_history": [0.0]}
    path.write_text(json.dumps(raw))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.CORRUPTED
    assert "checksum" in res.reason


def test_schema_version_mismatch_is_corrupted(tmp_path):
    """A newer, unsupported schema version is CORRUPTED — never guessed."""
    path = tmp_path / "state.json"
    env = build_envelope(KIND_AUTHORITY_EVIDENCE, {"models": {}},
                         schema_version=SCHEMA_VERSION + 1)
    path.write_text(json.dumps(env))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.CORRUPTED
    assert "schema_version" in res.reason


def test_kind_mismatch_is_corrupted(tmp_path):
    """A valid envelope of the WRONG kind is CORRUPTED for this reader."""
    path = tmp_path / "state.json"
    atomic_write_state(str(path), "some_other_state", {"x": 1})
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.CORRUPTED
    assert "kind" in res.reason


# ── CapabilityAuthority: explicit durability ────────────────────────────────

def test_durable_classmethod_is_durable(tmp_path):
    """``durable(path)`` is explicit DURABLE and persists evidence."""
    path = tmp_path / "auth.json"
    a = CapabilityAuthority.durable(str(path))
    assert a.is_durable is True
    assert a.durability is DurabilityMode.DURABLE
    a.record(CAP, 0.9, cycle=1)
    assert path.exists()
    raw = json.loads(path.read_text())
    assert raw["kind"] == KIND_AUTHORITY_EVIDENCE
    assert raw["checksum"] == payload_checksum(raw["payload"])


def test_durable_without_path_is_a_configuration_error():
    """DURABLE without a path raises — production must not be silently ephemeral."""
    with pytest.raises(ValueError):
        CapabilityAuthority(durability=DurabilityMode.DURABLE)


def test_ephemeral_classmethod_is_ephemeral():
    """``ephemeral()`` is explicitly in-memory and writes nothing."""
    a = CapabilityAuthority.ephemeral()
    assert a.is_durable is False
    assert a.durability is DurabilityMode.EPHEMERAL


def test_restart_preserves_falsification_with_integrity_envelope(tmp_path):
    """persist -> restart -> load -> evaluate keeps a falsified capability FAIL."""
    path = tmp_path / "auth.json"
    pre = CapabilityAuthority.durable(str(path))
    pre.record(CAP, 0.9, cycle=100)
    assert pre.state(CAP, now_cycle=100).status is CapabilityStatus.FAIL

    post = CapabilityAuthority.durable(str(path))
    st = post.state(CAP, now_cycle=100)
    assert st.status is CapabilityStatus.FAIL
    assert st.ever_falsified is True
    # Identity: the persisted evidence is keyed to the correct model id.
    assert MID in post.tracker.models
    assert "world" not in post.tracker.models


def test_stale_persisted_state_cannot_overwrite_newer_live_state(tmp_path):
    """Loading an older store never downgrades a newer falsification."""
    path = tmp_path / "auth.json"
    old = RealityGapTracker()
    old.record(MID, np.array([1.0]), np.array([1.0]), cycle=100)  # PASS
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE,
                       {"models": old.to_state()})
    live = CapabilityAuthority.durable(str(path))  # loads the old PASS
    live.record(CAP, 0.9, cycle=200)               # newer FAIL
    live._load_state()                             # re-merge the old store
    m = live.tracker.model(MID)
    assert m.last_validation_cycle == 200
    assert m.ever_falsified is True


def test_corrupt_store_fails_closed_not_first_run(tmp_path):
    """A corrupt store withholds authority and is NOT treated as a clean run."""
    path = tmp_path / "auth.json"
    path.write_text("{not-json")
    a = CapabilityAuthority.durable(str(path))
    st = a.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.FAIL
    assert "unreadable" in st.reason or "malformed" in st.reason
    assert a.capability_authorization(CAP, now_cycle=1).authorized() is False


def test_unenveloped_positive_state_fails_closed(tmp_path):
    """Stripping the envelope to forge a clean PASS cannot grant authority.

    A legacy/unenveloped payload (a downgrade attempt) has no checksum, so it
    is CORRUPTED — never silently accepted as trusted positive evidence.
    """
    path = tmp_path / "auth.json"
    forging = {"models": {MID: {
        "model_id": MID, "validation_count": 10, "total_gap": 0.0,
        "gap_history": [0.0] * 10, "ever_falsified": False,
        "last_validation_cycle": 50, "falsification_threshold": 0.6}}}
    path.write_text(json.dumps(forging))
    a = CapabilityAuthority.durable(str(path))
    assert a.state(CAP, now_cycle=50).status is CapabilityStatus.FAIL


def test_deleting_store_cannot_manufacture_authority(tmp_path):
    """Deletion yields an honest first run that GRANTS no authority either.

    Deleting persistence cannot behave like a clean certification: the
    never-validated capability is UNKNOWN (not ok), and canonical LIVE
    certification lives elsewhere and is untouched.
    """
    path = tmp_path / "auth.json"
    a = CapabilityAuthority.durable(str(path))
    a.record(CAP, 0.9, cycle=1)  # falsify + persist
    path.unlink()
    fresh = CapabilityAuthority.durable(str(path))
    assert fresh._evidence_unreadable is False
    st = fresh.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.UNKNOWN
    assert fresh.capability_authorization(CAP, now_cycle=1).authorized() is False


# ── pipeline Reality Gap durability ─────────────────────────────────────────

def _pipeline(state_path: str):
    """Build a minimal real pipeline with durable Reality Gap evidence.

    Args:
        state_path: the durable Reality Gap store path.

    Returns:
        A constructed TelosV14Pipeline (streams not required for this test).
    """
    from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline
    sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
    return TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim, state_dim=2, mode="fast",
        deterministic_seed=42, reality_gap_state_path=state_path))


def test_pipeline_reality_gap_survives_restart(tmp_path):
    """The pipeline's per-model Reality Gap evidence survives a restart."""
    path = str(tmp_path / "rg.json")
    p1 = _pipeline(path)
    p1._reality_gap_tracker.record("world", np.array([1.0]), np.array([0.0]),
                                   cycle=7)
    p1._persist_reality_gap_state()
    p2 = _pipeline(path)
    assert p2._reality_gap_evidence_corrupt is False
    m = p2._reality_gap_tracker.model("world")
    assert m.validation_count == 1
    assert m.ever_falsified is True
    assert m.last_validation_cycle == 7


def test_pipeline_reality_gap_corrupt_fails_closed_in_act(tmp_path):
    """A corrupt Reality Gap store forces the act-phase fidelity gate FAIL."""
    path = tmp_path / "rg.json"
    path.write_text("{tampered")
    pipe = _pipeline(str(path))
    assert pipe._reality_gap_evidence_corrupt is True

    pipeline = MagicMock()
    pipeline._firewall.inspect.return_value = _FirewallVerdict()
    pipeline.config.adapter = MagicMock()
    pipeline._reality_gap_tracker = pipe._reality_gap_tracker
    pipeline._reality_gap_evidence_corrupt = True
    ctx = PhaseContext(cycle_count=3, state=np.zeros(2), user_name=None)
    ctx.selected_intent = IntentIR(intent_type="navigate", confidence=0.8)
    ctx.verdict = _Verdict()
    _run_act(pipeline, ctx)
    # model_fidelity FAILED -> the governor cannot authorize ACT.
    assert ctx.selected_action is None
    assert ctx.no_action is True
    assert getattr(ctx, "blocked_by_gate", None) == "model_fidelity"


def test_pipeline_reality_gap_deletion_is_first_run(tmp_path):
    """An absent store is an honest first run (no prior evidence), not corruption."""
    path = str(tmp_path / "rg.json")
    p1 = _pipeline(path)
    p1._reality_gap_tracker.record("world", np.array([1.0]), np.array([0.0]))
    p1._persist_reality_gap_state()
    pathlib.Path(path).unlink()
    p2 = _pipeline(path)
    assert p2._reality_gap_evidence_corrupt is False
    assert p2._reality_gap_tracker.model("world").validation_count == 0


# ── production construction audit ───────────────────────────────────────────

def test_production_construction_audit_passes():
    """Every production CapabilityAuthority site is explicitly classified."""
    from telos.tools.durability_audit import scan
    res = scan()
    assert res["verdict"] == "PASS"
    counts = res["counts"]
    assert counts["unclassified"] == 0
    assert counts["durable_production"] >= 1
    # The durable production site is the canary's authority construction.
    durable = [s for s in res["sites"]
               if s["classification"] == "DURABLE_PRODUCTION"]
    assert any(s["path"].endswith("live_canary.py") for s in durable)


def test_audit_classifier_flags_unclassified():
    """The classifier flags a bare construction and accepts explicit modes."""
    from telos.tools.durability_audit import _classify
    import ast
    bare = ast.parse("a = CapabilityAuthority()").body[0].value
    marked = ast.parse(
        "a = CapabilityAuthority()  # durability: ephemeral (test)").body[0].value
    durable = ast.parse(
        "a = CapabilityAuthority(state_path='/x')").body[0].value
    explicit = ast.parse(
        "a = CapabilityAuthority.durable('/x')").body[0].value
    assert _classify(bare, "a = CapabilityAuthority()") == "UNCLASSIFIED"
    assert _classify(marked, "a = CapabilityAuthority()  "
                             "# durability: ephemeral (test)") == "EPHEMERAL"
    assert _classify(durable, "a = CapabilityAuthority(state_path='/x')") \
        == "DURABLE_PRODUCTION"
    assert _classify(explicit, "a = CapabilityAuthority.durable('/x')") \
        == "DURABLE_PRODUCTION"


def test_producer_canary_without_authority_path_refuses():
    """A PRODUCER-origin canary with no durable authority path fails closed."""
    from telos.core.actions.live_canary import CanaryOrigin, LiveCanary
    canary = LiveCanary(workspace_root=None, enabled=True,
                        origin=CanaryOrigin.for_producer())
    assert canary.guard_refusal(cycle=1) == "authority_durability_unconfigured"
    # A runner-origin one-shot is intentionally ephemeral and unaffected.
    runner = LiveCanary(workspace_root=None, enabled=True,
                        origin=CanaryOrigin.for_runner())
    assert runner.guard_refusal(cycle=1) != "authority_durability_unconfigured"
