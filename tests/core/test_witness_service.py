"""
The standalone witness service: monotonic floor, idempotence, attestation.

These exercise the service IN-PROCESS (a thread) for speed. The decisive
adversarial test runs the SAME service as a real separate PROCESS
(``tests/core/test_witness_service_adversarial.py``).
"""

import json
import urllib.error
import urllib.request

import pytest

from telos.core.actions.witness_attest import verify_attestation
from telos.witness_service import (
    WitnessLedger, WitnessLedgerError, WitnessServerHarness,
)

SCOPE = {"store_id": "capability_authority", "producer_id": "telos",
         "world_id": "grid", "capability_id": "filesystem.write"}
SCOPE_PATH = "capability_authority/telos/grid/filesystem.write"
TOKEN = "test-writer-token"


def _record(seq, *, state="a"):
    """A minimal witnessed record for the fixed scope."""
    return {"sequence": seq, "state_hash": state * 64, "evidence_hash": "b" * 64,
            "scope": dict(SCOPE)}


def _call(endpoint, method, path, body=None, token=None):
    """Perform one JSON request, returning ``(status, body)`` (never raises)."""
    req = urllib.request.Request(
        endpoint + path, method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_and_public_key(tmp_path):
    """Health is live and the public key is published."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        st, body = _call(s.endpoint, "GET", "/health")
        assert st == 200 and body["ok"] is True
        st, body = _call(s.endpoint, "GET", "/public_key")
        assert st == 200 and "n" in body["public_key"]


def test_witness_accepts_new_and_attests(tmp_path):
    """A new sequence is accepted and validly attested."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        pub = s.ledger.public_key
        st, body = _call(s.endpoint, "POST", "/witness", _record(1), TOKEN)
        assert st == 200 and body["ok"] is True
        assert verify_attestation(pub, body["record"], body["attestation"])


def test_witness_rejects_rollback_and_divergence(tmp_path):
    """A lower sequence and a same-sequence divergence both return 409."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        _call(s.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
        st, _ = _call(s.endpoint, "POST", "/witness", _record(2, state="b"), TOKEN)
        assert st == 200
        # rollback
        st, body = _call(s.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
        assert st == 409 and body["error"] == "conflict"
        # same-sequence divergence
        st, _ = _call(s.endpoint, "POST", "/witness", _record(2, state="c"), TOKEN)
        assert st == 409


def test_witness_duplicate_is_idempotent(tmp_path):
    """An identical duplicate of the current latest is a no-op 200."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        _call(s.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
        st, body = _call(s.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
        assert st == 200 and body["duplicate"] is True
        assert s.ledger.conflicts == 0


def test_latest_returns_record_and_attestation(tmp_path):
    """Latest returns the current record with a valid attestation."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        pub = s.ledger.public_key
        _call(s.endpoint, "POST", "/witness", _record(3, state="d"), TOKEN)
        st, body = _call(s.endpoint, "GET", f"/latest/{SCOPE_PATH}", token=TOKEN)
        assert st == 200 and body["record"]["sequence"] == 3
        assert verify_attestation(pub, body["record"], body["attestation"])


def test_latest_missing_is_404(tmp_path):
    """An unwitnessed scope is an honest 404."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        st, _ = _call(s.endpoint, "GET", f"/latest/{SCOPE_PATH}", token=TOKEN)
        assert st == 404


def test_writes_and_reads_require_token(tmp_path):
    """With a token configured, unauthenticated writes/reads are 401."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        st, _ = _call(s.endpoint, "POST", "/witness", _record(1))
        assert st == 401
        st, _ = _call(s.endpoint, "GET", f"/latest/{SCOPE_PATH}")
        assert st == 401
        st, _ = _call(s.endpoint, "POST", "/witness", _record(1), "wrong")
        assert st == 401


def test_invalid_record_is_400(tmp_path):
    """A malformed record is rejected before touching the floor."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        st, _ = _call(s.endpoint, "POST", "/witness", {"sequence": -1}, TOKEN)
        assert st == 400


def test_floor_survives_restart(tmp_path):
    """A restarted service rebuilds the floor from the append-only log."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        _call(s.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
        _call(s.endpoint, "POST", "/witness", _record(2, state="b"), TOKEN)
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s2:
        assert s2.ledger.floor()
        st, _ = _call(s2.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
        assert st == 409, "restart must NOT lower the server-side floor"


def test_tampered_log_refuses_to_start(tmp_path):
    """A log line whose attestation no longer verifies fails the service closed."""
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        _call(s.endpoint, "POST", "/witness", _record(1, state="a"), TOKEN)
    log = tmp_path / "witness_log.jsonl"
    entry = json.loads(log.read_text().strip())
    entry["record"]["state_hash"] = "f" * 64  # local tamper of the witness store
    log.write_text(json.dumps(entry) + "\n")
    with pytest.raises(WitnessLedgerError):
        WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024).stop()


def test_attestation_is_key_specific(tmp_path):
    """An answer attested by a different witness key fails the pinned key."""
    from telos.core.actions.witness_attest import (
        generate_private_key, public_from_private)
    with WitnessServerHarness(str(tmp_path), token=TOKEN, key_bits=1024) as s:
        _, body = _call(s.endpoint, "POST", "/witness", _record(1), TOKEN)
        other = public_from_private(generate_private_key(1024))
        assert verify_attestation(other, body["record"], body["attestation"]) is False


def test_ledger_floor_never_decreases_in_memory(tmp_path):
    """The ledger floor monotonically increases across accepted writes."""
    key = __import__("telos.core.actions.witness_attest",
                     fromlist=["generate_private_key"]).generate_private_key(1024)
    ledger = WitnessLedger(str(tmp_path / "log.jsonl"), key)
    ledger.witness(_record(1, state="a"))
    ledger.witness(_record(2, state="b"))
    floor_after_two = ledger.floor()
    st, _ = ledger.witness(_record(1, state="a"))
    assert st == 409
    assert ledger.floor() == floor_after_two
