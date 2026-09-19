"""
Durability trust-anchor tests — pluggable integrity + anti-rollback freshness.

Falsifier under test: the ONE durability contract must be able to escalate its
trust boundary beyond trusted-local-disk, so that (a) editing the state (and its
co-located checksum) WITHOUT the key fails verification, and (b) replaying an
older-but-valid state cannot silently resurrect authority. The default ``local``
mode must stay byte-identical, a configured-but-unusable anchor must fail
CLOSED, and there must be NO silent downgrade from ``hmac``/``witness`` to
``local``.

These are behavioral tests over the real envelope read/write path
(``telos/core/actions/durability.py`` + ``integrity.py``).
"""

import json

import numpy as np
import pytest

from telos.core.actions.durability import (
    KIND_AUTHORITY_EVIDENCE, SCHEMA_VERSION, AnchorUnavailable, HmacAnchor,
    IntegrityMode, LocalAnchor, StateOutcome, UnavailableAnchor, WitnessAnchor,
    atomic_write_state, build_envelope, read_state, resolve_anchor,
)
from telos.core.actions.reality_loop import CapabilityAuthority
from telos.core.governance.capability_authorization import CapabilityStatus

CAP = "filesystem.write"
MID = "world_action:filesystem.write"
KEY = b"a-distinctive-hmac-key-do-not-leak-4ce1a6f5"


# ── local default: unchanged + byte-identical ───────────────────────────────

def test_local_default_is_byte_identical(tmp_path):
    """An explicit local anchor writes exactly the historical four-key bytes."""
    legacy_path = tmp_path / "legacy.json"
    anchor_path = tmp_path / "anchor.json"
    payload = {"models": {MID: {"validation_count": 1}}}
    atomic_write_state(str(legacy_path), KIND_AUTHORITY_EVIDENCE, payload)
    atomic_write_state(str(anchor_path), KIND_AUTHORITY_EVIDENCE, payload,
                       anchor=LocalAnchor())
    assert legacy_path.read_bytes() == anchor_path.read_bytes()
    assert sorted(json.loads(legacy_path.read_text()).keys()) == [
        "checksum", "kind", "payload", "schema_version"]


def test_local_default_round_trips_and_classifies(tmp_path):
    """The default path still reports LOADED with the exact payload."""
    path = tmp_path / "s.json"
    payload = {"models": {}}
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, payload)
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=LocalAnchor())
    assert res.outcome is StateOutcome.LOADED
    assert res.payload == payload
    assert res.anchor_mode == "local"


def test_resolve_default_is_local(tmp_path):
    """With no configuration the resolver returns the byte-identical local mode."""
    anchor = resolve_anchor(env={})
    assert isinstance(anchor, LocalAnchor)
    assert anchor.mode is IntegrityMode.LOCAL
    assert anchor.requires_signature is False
    assert anchor.requires_sequence is False


# ── hmac: tamper detection with a key held outside the artifact ─────────────

def test_hmac_round_trip_and_key_absent_from_artifact(tmp_path):
    """A correct key loads; the raw key never appears in the state file bytes."""
    path = tmp_path / "h.json"
    payload = {"models": {}}
    anchor = HmacAnchor(KEY)
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, payload, anchor=anchor)
    raw = path.read_text()
    assert KEY.decode("utf-8") not in raw
    assert KEY not in path.read_bytes()
    env = json.loads(raw)
    assert env["anchor"] == "hmac"
    assert env["sequence"] == 1
    assert "mac" in env
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=HmacAnchor(KEY))
    assert res.outcome is StateOutcome.LOADED
    assert res.sequence == 1
    assert res.anchor_mode == "hmac"


def test_hmac_payload_edit_without_key_fails_closed(tmp_path):
    """Editing the payload (even recomputing the checksum) fails verification."""
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=HmacAnchor(KEY))
    env = json.loads(path.read_text())
    env["payload"]["models"]["forged"] = {"validation_count": 99}
    # Attacker recomputes the co-located sha256 checksum without the key.
    from telos.core.actions.durability import payload_checksum
    env["checksum"] = payload_checksum(env["payload"])
    path.write_text(json.dumps(env))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=HmacAnchor(KEY))
    assert res.outcome is StateOutcome.CORRUPTED
    assert "MAC" in res.reason or "mac" in res.reason


def test_hmac_sequence_edit_without_key_fails_closed(tmp_path):
    """The sequence is inside the authenticated core; decrementing it fails."""
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=HmacAnchor(KEY))
    env = json.loads(path.read_text())
    env["sequence"] = 0
    path.write_text(json.dumps(env))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=HmacAnchor(KEY))
    assert res.outcome is StateOutcome.CORRUPTED


def test_hmac_wrong_key_fails_closed(tmp_path):
    """A different key cannot verify the MAC (fail closed)."""
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=HmacAnchor(KEY))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=HmacAnchor(b"the-wrong-key"))
    assert res.outcome is StateOutcome.CORRUPTED


def test_key_file_is_supported_and_external_to_artifact(tmp_path):
    """A restricted key file resolves an HMAC anchor; the key stays external."""
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(KEY + b"\n")
    anchor = resolve_anchor("hmac", key_file=str(key_file), env={})
    assert anchor.available is True
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=anchor)
    assert KEY not in path.read_bytes()


# ── no silent downgrade ─────────────────────────────────────────────────────

def test_local_reader_refuses_hmac_envelope(tmp_path):
    """A local-only reader must not accept a stronger-anchored store."""
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=HmacAnchor(KEY))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=LocalAnchor())
    assert res.outcome is StateOutcome.CORRUPTED
    assert "downgrade" in res.reason


def test_default_reader_refuses_hmac_envelope(tmp_path):
    """With no configured anchor, an hmac store still fails closed."""
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=HmacAnchor(KEY))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.CORRUPTED


def test_hmac_reader_refuses_unsigned_envelope(tmp_path):
    """An hmac-configured reader must not accept an unsigned legacy store."""
    path = tmp_path / "legacy.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}})
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=HmacAnchor(KEY))
    assert res.outcome is StateOutcome.CORRUPTED


def test_resolve_hmac_without_key_is_unavailable_not_local():
    """Requesting hmac with no key yields an UNAVAILABLE anchor (never local)."""
    anchor = resolve_anchor("hmac", env={})
    assert isinstance(anchor, UnavailableAnchor)
    assert anchor.available is False
    assert not isinstance(anchor, LocalAnchor)


def test_resolve_unknown_mode_is_unavailable():
    """An unknown mode fails closed rather than falling back to local."""
    anchor = resolve_anchor("bogus-mode", env={})
    assert anchor.available is False
    assert not isinstance(anchor, LocalAnchor)


def test_unavailable_anchor_fails_closed_on_read_and_write(tmp_path):
    """A configured-but-unusable anchor fails closed and writes nothing."""
    path = tmp_path / "s.json"
    unavailable = resolve_anchor("hmac", env={})
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=unavailable)
    assert res.outcome is StateOutcome.CORRUPTED
    assert "unavailable" in res.reason
    with pytest.raises(AnchorUnavailable):
        atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                           anchor=unavailable)
    assert not path.exists()


# ── anti-rollback: monotonic sequence + freshness floor ─────────────────────

def test_local_in_process_rollback_is_rejected(tmp_path):
    """Persist seq 2, then restore the valid seq-1 bytes -> rejected."""
    path = tmp_path / "s.json"
    anchor = LocalAnchor()
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"x": 1},
                       sequence=1, anchor=anchor)
    seq1 = path.read_bytes()
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"x": 1},
                       sequence=2, anchor=anchor)
    assert read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                      anchor=anchor).sequence == 2
    path.write_bytes(seq1)  # replay the older valid state
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert "replay" in res.reason or "stale" in res.reason


def test_witness_detects_rollback_replay(tmp_path):
    """A witnessed seq-2 floor rejects replaying the valid seq-1 state."""
    state = tmp_path / "s.json"
    witness = tmp_path / "w.json"
    key = KEY

    def fresh():
        return WitnessAnchor(HmacAnchor(key), str(witness))

    payload = {"models": {}}
    atomic_write_state(str(state), KIND_AUTHORITY_EVIDENCE, payload,
                       anchor=fresh())  # seq 1
    seq1 = state.read_bytes()
    atomic_write_state(str(state), KIND_AUTHORITY_EVIDENCE, payload,
                       anchor=fresh())  # seq 2
    assert read_state(str(state), expected_kind=KIND_AUTHORITY_EVIDENCE,
                      anchor=fresh()).sequence == 2

    state.write_bytes(seq1)  # replay the older valid state
    res = read_state(str(state), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=fresh())
    assert res.outcome is StateOutcome.CORRUPTED
    assert "replay" in res.reason or "stale" in res.reason


def test_witness_missing_fails_closed(tmp_path):
    """A sequenced state with no witness store fails closed (rollback/deletion)."""
    state = tmp_path / "s.json"
    witness = tmp_path / "w.json"
    anchor = WitnessAnchor(HmacAnchor(KEY), str(witness))
    atomic_write_state(str(state), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=anchor)
    witness.unlink()
    res = read_state(str(state), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=WitnessAnchor(HmacAnchor(KEY), str(witness)))
    assert res.outcome is StateOutcome.CORRUPTED


def test_witness_tampered_store_fails_closed(tmp_path):
    """A witness entry with a forged keyed MAC fails closed."""
    state = tmp_path / "s.json"
    witness = tmp_path / "w.json"
    anchor = WitnessAnchor(HmacAnchor(KEY), str(witness))
    atomic_write_state(str(state), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=anchor)
    rec = json.loads(witness.read_text())
    rec["sequence"] = 0
    witness.write_text(json.dumps(rec))
    res = read_state(str(state), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=WitnessAnchor(HmacAnchor(KEY), str(witness)))
    assert res.outcome is StateOutcome.CORRUPTED


def test_sequence_absent_with_sequencing_anchor_is_corrupted(tmp_path):
    """An hmac store missing its sequence cannot be verified."""
    path = tmp_path / "h.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"models": {}},
                       anchor=HmacAnchor(KEY))
    env = json.loads(path.read_text())
    del env["sequence"]
    path.write_text(json.dumps(env))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=HmacAnchor(KEY))
    assert res.outcome is StateOutcome.CORRUPTED


def test_invalid_sequence_is_corrupted(tmp_path):
    """A non-integer / negative sequence is CORRUPTED."""
    path = tmp_path / "s.json"
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, {"x": 1},
                       sequence=1)
    env = json.loads(path.read_text())
    env["sequence"] = -3
    path.write_text(json.dumps(env))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE)
    assert res.outcome is StateOutcome.CORRUPTED


# ── existing failure semantics preserved ────────────────────────────────────

def test_corrupt_and_wrong_schema_preserved_with_anchor(tmp_path):
    """Truncation / wrong schema stay CORRUPTED even with an anchor configured."""
    anchor = HmacAnchor(KEY)
    bad = tmp_path / "bad.json"
    bad.write_text("{truncated")
    res = read_state(str(bad), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    env = build_envelope(KIND_AUTHORITY_EVIDENCE, {"models": {}},
                         schema_version=SCHEMA_VERSION + 1)
    new = tmp_path / "new.json"
    new.write_text(json.dumps(env))
    res = read_state(str(new), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     anchor=anchor)
    assert res.outcome is StateOutcome.CORRUPTED


# ── the store consumes the anchor (not just the envelope API) ────────────────

def test_capability_authority_uses_hmac_anchor(tmp_path):
    """A capability authority configured hmac persists/reloads tamper-resistant state."""
    path = str(tmp_path / "auth.json")
    anchor = HmacAnchor(KEY)
    a = CapabilityAuthority.durable(path, integrity=anchor)
    a.record(CAP, 0.9, cycle=1)
    raw = json.loads(open(path, encoding="utf-8").read())
    assert raw["anchor"] == "hmac"
    assert KEY not in open(path, "rb").read()

    b = CapabilityAuthority.durable(path, integrity=anchor)
    assert b._evidence_unreadable is False
    st = b.state(CAP, now_cycle=1)
    assert st.status is CapabilityStatus.FAIL
    assert st.ever_falsified is True

    raw["payload"]["models"][MID]["validation_count"] = 99
    open(path, "w", encoding="utf-8").write(json.dumps(raw))
    c = CapabilityAuthority.durable(path, integrity=anchor)
    assert c._evidence_unreadable is True
    assert c.state(CAP, now_cycle=1).status is CapabilityStatus.FAIL
    assert c.capability_authorization(CAP, now_cycle=1).authorized() is False


def test_capability_authority_hmac_refuses_legacy_store(tmp_path):
    """An hmac authority must not silently accept an unsigned local store."""
    path = str(tmp_path / "auth.json")
    atomic_write_state(path, KIND_AUTHORITY_EVIDENCE,
                       {"models": {MID: {"model_id": MID,
                                         "validation_count": 10}}})
    a = CapabilityAuthority.durable(path, integrity=HmacAnchor(KEY))
    assert a._evidence_unreadable is True


def test_pipeline_reality_gap_uses_configured_anchor(tmp_path, monkeypatch):
    """The runtime's Reality Gap store honors the configured hmac anchor."""
    monkeypatch.setenv("TELOS_DURABILITY_INTEGRITY", "hmac")
    monkeypatch.setenv("TELOS_DURABILITY_HMAC_KEY", KEY.decode("utf-8"))
    from telos_task import GridAdpt, GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
    from telos.core.runtime import PipelineConfig, TelosV14Pipeline

    def build(state_path):
        sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
        return TelosV14Pipeline(PipelineConfig(
            adapter=GridAdpt(), simulator=sim, state_dim=2, mode="fast",
            deterministic_seed=42, reality_gap_state_path=state_path))

    path = str(tmp_path / "rg.json")
    p1 = build(path)
    p1._reality_gap_tracker.record("world", np.array([1.0]), np.array([0.0]),
                                   cycle=7)
    p1._persist_reality_gap_state()
    raw = json.loads(open(path, encoding="utf-8").read())
    assert raw["anchor"] == "hmac"
    assert KEY not in open(path, "rb").read()

    p2 = build(path)
    assert p2._reality_gap_evidence_corrupt is False
    assert p2._reality_gap_tracker.model("world").validation_count == 1

    raw["payload"]["models"]["world"]["validation_count"] = 99
    open(path, "w", encoding="utf-8").write(json.dumps(raw))
    p3 = build(path)
    assert p3._reality_gap_evidence_corrupt is True
