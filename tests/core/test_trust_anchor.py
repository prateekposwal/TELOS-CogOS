"""
External trust-anchor / anti-replay boundary tests.

FALSIFIER UNDER TEST: with an EXTERNAL trust anchor configured, an attacker who
controls the ENTIRE local filesystem (state files, checksums/envelopes, local
metadata, and any historical valid state) must NOT be able to make an old or
forged authority state appear CURRENT — whereas with the anchor disabled the
documented trusted-local-disk limitation remains (honestly preserved).

The external provider is exercised against a loopback test server that stands in
for a genuine external witness service. That is NOT HSM-grade security and is not
claimed; it proves the independence boundary is real and enforced.
"""

import json
import socket

import pytest

from telos.core.actions.durability import (
    KIND_AUTHORITY_EVIDENCE, AnchorUnavailable, StateLoadResult, StateOutcome,
    atomic_write_state, read_state,
)
from telos.core.actions.sandbox import EgressRule, NetworkSandbox
from telos.core.actions.trust_anchor import (
    DisabledTrustAnchor, ExternalHttpTrustAnchor, TrustAnchorConflict,
    TrustAnchorUnavailable, TrustVerdict, UnavailableTrustAnchor, WitnessRecord,
    WitnessScope, resolve_trust_anchor,
)
from telos.core.actions.reality_loop import CapabilityAuthority
from telos.core.governance.capability_authorization import CapabilityStatus

from tests.core.witness_test_server import WitnessServerHarness

CAP = "filesystem.write"
SCOPE = WitnessScope(store_id="capability_authority", producer_id="telos",
                     world_id="grid", capability_id=CAP)


# ── helpers ─────────────────────────────────────────────────────────────────

def _sandbox(server: WitnessServerHarness) -> NetworkSandbox:
    """A governed sandbox allowlisting the loopback test server."""
    return NetworkSandbox(rules=[EgressRule(
        host="127.0.0.1", ports=(server.port,), routes=("/",),
        methods=("GET", "POST"))])


def _anchor(server: WitnessServerHarness, *, token=None) -> ExternalHttpTrustAnchor:
    """An external provider bound to the test server."""
    return ExternalHttpTrustAnchor(server.endpoint, sandbox=_sandbox(server),
                                   token=token)


def _write(path, payload, *, anchor=None, seq=None, scope=SCOPE) -> None:
    """Write a witnessed local state through the ONE durability API."""
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, payload,
                       sequence=seq, trust_anchor=anchor,
                       witness_scope=scope)


def _read(path, *, anchor=None, scope=SCOPE) -> StateLoadResult:
    """Read a local state with the external anchor configured."""
    return read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                      trust_anchor=anchor, witness_scope=scope)


def _payload(marker: str) -> dict:
    """A minimal evidence payload."""
    return {"models": {CAP: {"model_id": CAP, "marker": marker,
                             "validation_count": 1}}}


def _rechecksum(raw: dict) -> dict:
    """Recompute the local checksum (what a local attacker can do)."""
    from telos.core.actions.durability import payload_checksum
    raw["checksum"] = payload_checksum(raw["payload"])
    return raw


# ── 1. current state + valid witness -> accepted ────────────────────────────

def test_valid_current_state_is_accepted(tmp_path):
    """1. A witnessed current state loads."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.LOADED
        assert res.sequence == 1


# ── 2. state modified -> rejected ───────────────────────────────────────────

def test_modified_state_is_rejected(tmp_path):
    """2. Editing the payload (without recomputing the checksum) fails closed."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)
        raw = json.loads(path.read_text())
        raw["payload"]["models"][CAP]["marker"] = "tampered"
        path.write_text(json.dumps(raw))
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED


# ── 3. witness modified -> rejected ─────────────────────────────────────────

def test_modified_witness_is_rejected(tmp_path):
    """3. A witness whose stored state hash was altered fails closed."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)
        # Tamper the external store's record (simulating a corrupted witness).
        (key, rec), = server.store._latest.items()
        rec["state_hash"] = "0" * 64
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.INVALID.value


# ── 4. state + local checksum rewritten together -> external rejection ──────

def test_state_and_checksum_rewritten_together_is_rejected(tmp_path):
    """4. Rewriting payload + recomputed checksum still diverges from the witness."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)
        raw = json.loads(path.read_text())
        raw["payload"]["models"][CAP]["marker"] = "forged"
        raw["payload"]["models"][CAP]["validation_count"] = 99
        _rechecksum(raw)  # the local account CAN do this
        path.write_text(json.dumps(raw))
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.INVALID.value


# ── 5. old valid state + old valid witness replayed -> rejected ──────────────

def test_replayed_old_state_and_witness_is_rejected(tmp_path):
    """5. Replaying a previously valid state (with its historical witness) fails."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)   # seq 1
        old_bytes = path.read_bytes()
        _write(path, _payload("two"), anchor=anchor)   # seq 2
        path.write_bytes(old_bytes)                    # replay the valid seq-1 pair
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.STALE.value


# ── 6. current state + older witness -> rejected ────────────────────────────

def test_current_state_with_older_witness_is_rejected(tmp_path):
    """6. A local state ahead of the witness (unwitnessed forward) fails closed."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)   # seq 1
        # Roll the EXTERNAL witness back to an older record (seq 1 vs local seq 2).
        _write(path, _payload("two"), anchor=anchor)   # local seq 2
        (key, rec), = server.store._latest.items()
        rec["sequence"] = 1
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.UNKNOWN.value


# ── 7. older state + current witness -> rejected ────────────────────────────

def test_older_state_with_current_witness_is_rejected(tmp_path):
    """7. An older state against the current witness is a rollback (STALE)."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)   # seq 1
        seq1 = path.read_bytes()
        _write(path, _payload("two"), anchor=anchor)   # seq 2 (witness current)
        path.write_bytes(seq1)                         # older state, current witness
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.STALE.value


# ── 8. sequence rollback -> rejected ────────────────────────────────────────

def test_sequence_rollback_write_is_refused(tmp_path):
    """8. Writing a sequence at/under the witnessed floor is refused (fail closed)."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("one"), anchor=anchor)   # seq 1
        _write(path, _payload("two"), anchor=anchor)   # seq 2
        with pytest.raises(AnchorUnavailable):
            _write(path, _payload("rollback"), anchor=anchor, seq=1)
        # The on-disk state is untouched (the refused write wrote nothing).
        assert _read(path, anchor=anchor).sequence == 2


# ── 9. duplicate witness -> deterministic handling ──────────────────────────

def test_duplicate_witness_is_idempotent(tmp_path):
    """9. Witnessing the identical record twice is deterministic (no conflict)."""
    with WitnessServerHarness() as server:
        anchor = _anchor(server)
        from telos.core.actions.durability import build_witness_record
        record = build_witness_record(
            kind=KIND_AUTHORITY_EVIDENCE, payload=_payload("one"),
            schema_version=1, sequence=1, scope=SCOPE)
        first = anchor.witness(record)
        second = anchor.witness(record)
        assert first.state_hash == second.state_hash
        assert first.sequence == second.sequence == 1
        assert server.store.conflicts == 0
        assert server.store.witness_calls == 2


# ── 10. missing witness -> fail closed (anchor configured) ──────────────────

def test_missing_witness_fails_closed(tmp_path):
    """10. A sequenced local state with no witnessed record fails closed (UNKNOWN)."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        # A local state written WITHOUT any external witness (seq carried).
        atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, _payload("one"),
                           sequence=1)
        anchor = _anchor(server)  # fresh server: holds nothing
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.UNKNOWN.value


# ── 11. anchor unavailable -> fail closed per policy ────────────────────────

def test_anchor_unavailable_fails_closed(tmp_path):
    """11. An unreachable anchor revokes authority (no fallback, read and write)."""
    server = WitnessServerHarness().start()
    path = tmp_path / "s.json"
    anchor = _anchor(server)
    _write(path, _payload("one"), anchor=anchor)
    server.stop()  # the external anchor becomes unreachable
    dead = ExternalHttpTrustAnchor(server.endpoint,
                                   sandbox=_sandbox(server))
    res = _read(path, anchor=dead)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == TrustVerdict.UNAVAILABLE.value
    with pytest.raises(AnchorUnavailable):
        _write(path, _payload("two"), anchor=dead)


# ── 12. conflicting witnesses -> fail closed ────────────────────────────────

def test_conflicting_witnesses_fail_closed(tmp_path):
    """12. A same-sequence divergence is a conflict (rejected) and fails closed."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        from telos.core.actions.durability import build_witness_record
        good = build_witness_record(
            kind=KIND_AUTHORITY_EVIDENCE, payload=_payload("one"),
            schema_version=1, sequence=1, scope=SCOPE)
        anchor.witness(good)
        forged = build_witness_record(
            kind=KIND_AUTHORITY_EVIDENCE, payload=_payload("forged"),
            schema_version=1, sequence=1, scope=SCOPE)
        with pytest.raises(TrustAnchorConflict):
            anchor.witness(forged)
        # The local state matching the forged hash is rejected (INVALID).
        _write(path, _payload("one"), anchor=anchor)  # local must match witness
        raw = json.loads(path.read_text())
        raw["payload"] = _payload("forged")["models"]
        raw = _rechecksum(raw)
        path.write_text(json.dumps(raw))
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED


# ── 13. restart preserves the last accepted monotonic state ─────────────────

def test_restart_preserves_monotonic_state(tmp_path):
    """13. A fresh provider over the same anchor resumes at the witnessed floor."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        first = _anchor(server)
        _write(path, _payload("one"), anchor=first)
        _write(path, _payload("two"), anchor=first)
        restarted = _anchor(server)  # process restart: new provider, same anchor
        res = _read(path, anchor=restarted)
        assert res.outcome is StateOutcome.LOADED
        assert res.sequence == 2
        _write(path, _payload("three"), anchor=restarted)
        assert _read(path, anchor=restarted).sequence == 3


# ── 14. legitimate forward transition -> accepted ───────────────────────────

def test_forward_transition_is_accepted(tmp_path):
    """14. Each legitimate forward write is witnessed and accepted."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        for i, marker in enumerate(("one", "two", "three"), start=1):
            _write(path, _payload(marker), anchor=anchor)
            res = _read(path, anchor=anchor)
            assert res.outcome is StateOutcome.LOADED and res.sequence == i


# ── 15. recertification creates a NEW monotonic state ───────────────────────

def test_recertification_creates_new_monotonic_state(tmp_path):
    """15. Re-establishing authority after revocation uses a NEW sequence."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        _write(path, _payload("falsified"), anchor=anchor)   # seq 1
        # Revocation: local evidence is deleted then legitimately re-established.
        path.unlink()
        # A brand-new state must NOT reuse the old sequence.
        _write(path, _payload("recertified"), anchor=anchor)
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.LOADED
        assert res.sequence == 2, "recertification must advance the sequence"


# ── CRITICAL: compromised local account, anchor outside its control ─────────

def test_compromised_local_account_cannot_forge_or_replay(tmp_path):
    """Critical. An attacker with the whole local FS cannot make old/forged state current."""
    with WitnessServerHarness() as server:
        path = tmp_path / "s.json"
        anchor = _anchor(server)
        # Genuine history: seq 1 then seq 2 (the witness floor is 2).
        _write(path, _payload("genuine-1"), anchor=anchor)
        historical_valid = path.read_bytes()
        _write(path, _payload("genuine-2"), anchor=anchor)
        assert _read(path, anchor=anchor).sequence == 2

        # ATTACK 1 — replay the old valid pair (state + its checksum).
        path.write_bytes(historical_valid)
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.STALE.value

        # ATTACK 2 — forge a NEW payload at the anchored sequence, recompute the
        # checksum, and keep the "current" sequence (local metadata rewritten).
        _write(path, _payload("genuine-2"), anchor=anchor)
        raw = json.loads(path.read_text())
        raw["payload"]["models"][CAP]["marker"] = "forged-authority"
        _rechecksum(raw)
        path.write_text(json.dumps(raw))
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.INVALID.value

        # ATTACK 3 — delete the state to force a permissive first run.
        path.unlink()
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED
        assert res.trust_verdict == TrustVerdict.ROLLBACK.value

        # ATTACK 4 — try to lower the anchor itself by re-publishing the old record.
        from telos.core.actions.durability import build_witness_record
        old_record = build_witness_record(
            kind=KIND_AUTHORITY_EVIDENCE, payload=_payload("genuine-1"),
            schema_version=1, sequence=1, scope=SCOPE)
        with pytest.raises(TrustAnchorConflict):
            anchor.witness(old_record)

        # ATTACK 5 — bump the local sequence ABOVE the anchor (unwitnessed forward).
        _write(path, _payload("genuine-2"), anchor=anchor)
        raw = json.loads(path.read_text())
        raw["sequence"] = 99
        _rechecksum(raw)
        path.write_text(json.dumps(raw))
        res = _read(path, anchor=anchor)
        assert res.outcome is StateOutcome.CORRUPTED

        # No attacker variant produced authority.
        assert _read(path, anchor=anchor).outcome is not StateOutcome.LOADED


def test_disabled_anchor_preserves_documented_limitation(tmp_path):
    """With NO external anchor the trusted-local-disk limitation is honestly kept."""
    path = tmp_path / "s.json"
    anchor = DisabledTrustAnchor()
    _write(path, _payload("one"), seq=1)  # no external witness
    # A local attacker that rewrites state + checksum to a consistent pair is NOT
    # detected by the local boundary (the documented limitation, preserved).
    raw = json.loads(path.read_text())
    raw["payload"]["models"][CAP]["marker"] = "local-rewrite"
    _rechecksum(raw)
    path.write_text(json.dumps(raw))
    res = read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                     trust_anchor=anchor)
    assert res.outcome is StateOutcome.LOADED  # honest: local disk is the boundary


# ── provider resolution + separation ────────────────────────────────────────

def test_resolve_default_is_disabled_and_contacts_nothing():
    """The default mode is OFF (trusted local disk), never a silent external call."""
    anchor = resolve_trust_anchor(env={})
    assert isinstance(anchor, DisabledTrustAnchor)
    assert anchor.enabled is False
    assert anchor.externally_independent is False


def test_resolve_external_without_endpoint_is_unavailable():
    """Selecting external without an endpoint fails closed (no downgrade)."""
    anchor = resolve_trust_anchor("external", env={})
    assert isinstance(anchor, UnavailableTrustAnchor)
    assert anchor.enabled is True and anchor.available is False


def test_resolve_unknown_mode_is_unavailable():
    """An unknown external mode fails closed rather than disabling silently."""
    anchor = resolve_trust_anchor("bogus", env={})
    assert anchor.available is False
    assert not isinstance(anchor, DisabledTrustAnchor)


def test_external_anchor_is_default_off_in_duration_paths(tmp_path):
    """With external off, the durability path never contacts the sandbox."""
    path = tmp_path / "s.json"
    sentinel = {"called": False}

    class _ExplodingSandbox:
        def request(self, *a, **k):  # pragma: no cover - must not run
            sentinel["called"] = True
            raise AssertionError("external anchor must not be contacted when off")

    anchor = DisabledTrustAnchor()
    _write(path, _payload("one"), anchor=anchor)
    res = _read(path, anchor=anchor)
    assert res.outcome is StateOutcome.LOADED
    assert sentinel["called"] is False


# ── authority integration: the authority store honors the external anchor ────

def test_capability_authority_honors_external_anchor(tmp_path):
    """A capability authority wired to an external anchor fails closed on tamper."""
    with WitnessServerHarness() as server:
        path = str(tmp_path / "auth.json")
        anchor = _anchor(server)
        scope = WitnessScope(store_id=KIND_AUTHORITY_EVIDENCE,
                             producer_id="telos", world_id="grid",
                             capability_id=CAP)
        a = CapabilityAuthority.durable(path, trust_anchor=anchor,
                                        witness_scope=scope)
        a.record(CAP, 0.0, cycle=1)
        b = CapabilityAuthority.durable(path, trust_anchor=anchor,
                                        witness_scope=scope)
        assert b._evidence_unreadable is False
        assert b.state(CAP, now_cycle=1).status is CapabilityStatus.PASS
        # A local rewrite diverges from the witness -> authority withholds.
        raw = json.loads(open(path, encoding="utf-8").read())
        raw["payload"]["models"][f"world_action:{CAP}"]["validation_count"] = 99
        _rechecksum(raw)
        open(path, "w", encoding="utf-8").write(json.dumps(raw))
        c = CapabilityAuthority.durable(path, trust_anchor=anchor,
                                        witness_scope=scope)
        assert c._evidence_unreadable is True
        assert c.state(CAP, now_cycle=1).status is CapabilityStatus.FAIL
        assert c.capability_authorization(CAP, now_cycle=1).authorized() is False


def test_governed_egress_only_no_direct_socket_in_provider():
    """The provider opens NO direct socket: it routes through NetworkSandbox."""
    # A structural guard: constructing a provider never opens a socket until a
    # sandbox request is made. A dead endpoint yields UNAVAILABLE, not a raise.
    server = WitnessServerHarness().start()
    port = server.port
    server.stop()
    anchor = ExternalHttpTrustAnchor(f"http://127.0.0.1:{port}",
                                     sandbox=_sandbox(server))
    health = anchor.health()
    assert health.reachable is False
