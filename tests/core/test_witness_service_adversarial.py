"""
DECISIVE adversarial test against the REAL witness service (separate process).

ATTACKER MODEL (exactly the task's):
    The attacker compromises EVERYTHING available to the local producer:
    the state file, its checksum/envelope, its credentials (INCLUDING the
    producer-side writer token to the witness), local metadata, and every
    historical valid record. The attacker does NOT have the witness service's
    private SIGNING key.

    To honour that model this module launches the witness as a real, separate
    OS process with its own state directory + signing key, and the attacker
    helpers below never read that private key file.

EXPECTED: fail closed in every case — no variant may yield a LOADED/authorized
state, and no variant may lower the server-side sequence floor.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from telos.core.actions.durability import (
    KIND_AUTHORITY_EVIDENCE, StateOutcome, atomic_write_state,
    build_witness_record, payload_checksum, read_state,
)
from telos.core.actions.sandbox import EgressRule, NetworkSandbox
from telos.core.actions.trust_anchor import (
    ExternalHttpTrustAnchor, TrustAnchorConflict, WitnessScope,
)
from telos.core.actions.witness_attest import verify_attestation

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAP = "filesystem.write"
SCOPE = WitnessScope(store_id="capability_authority", producer_id="telos",
                     world_id="grid", capability_id=CAP)
SCOPE_PATH = "capability_authority/telos/grid/filesystem.write"
TOKEN = "producer-writer-token"


# ── real separate-process service ────────────────────────────────────────────

def _free_port() -> int:
    """Reserve and release a loopback port.

    Returns:
        A currently-free TCP port.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _http(endpoint, method, path, body=None, token=None, timeout=10):
    """Perform one direct HTTP JSON request (the attacker's raw channel).

    Returns:
        ``(status, body)`` — never raises for an HTTP error.
    """
    req = urllib.request.Request(
        endpoint + path, method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class RealWitness:
    """A witness service running as its OWN OS process (not in-test)."""

    def __init__(self, state_dir: str, token: str = TOKEN, key_bits: int = 1024):
        """Start the service process and wait until it answers /health.

        Args:
            state_dir: the witness's own state directory (NOT the producer's).
            token: the writer token (the producer-side credential).
            key_bits: the signing-key modulus size (small for test speed).
        """
        self.port = _free_port()
        self.endpoint = f"http://127.0.0.1:{self.port}"
        env = {**os.environ, "PYTHONPATH": REPO}
        # Distinct env namespace from the producer's TELOS_TRUST_ANCHOR*: the
        # service never reads the producer's config, and the producer never
        # reads the service's key.
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "telos.witness_service",
             "--state-dir", str(state_dir), "--host", "127.0.0.1",
             "--port", str(self.port), "--token", token,
             "--key-bits", str(key_bits)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.token = token
        self.public_key = None
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    "witness service exited early: "
                    + self.proc.stderr.read().decode("utf-8", "replace"))
            try:
                status, _ = _http(self.endpoint, "GET", "/health", timeout=1)
                if status == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            self.stop()
            raise RuntimeError("witness service did not become healthy")
        _, body = _http(self.endpoint, "GET", "/public_key")
        self.public_key = body["public_key"]

    def stop(self) -> None:
        """Terminate the service process."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


@pytest.fixture()
def real(tmp_path):
    """Yield a running real witness service (separate process) + its endpoint."""
    svc = RealWitness(str(tmp_path / "witness"))
    try:
        yield svc
    finally:
        svc.stop()


def _anchor(real: RealWitness, *, pinned=True) -> ExternalHttpTrustAnchor:
    """The producer's provider, pinned to the witness's public key by default."""
    sandbox = NetworkSandbox(rules=[EgressRule(
        host="127.0.0.1", ports=(real.port,), routes=("/",),
        methods=("GET", "POST"))])
    return ExternalHttpTrustAnchor(
        real.endpoint, sandbox=sandbox, token=real.token,
        attestation_public_key=(real.public_key if pinned else None))


def _payload(marker):
    """A minimal authority-evidence payload."""
    return {"models": {CAP: {"model_id": CAP, "marker": marker,
                             "validation_count": 1}}}


def _write(path, payload, anchor, seq=None):
    """Write a witnessed local state through the ONE durability API."""
    atomic_write_state(str(path), KIND_AUTHORITY_EVIDENCE, payload,
                       sequence=seq, trust_anchor=anchor, witness_scope=SCOPE)


def _read(path, anchor):
    """Read a local state with the external anchor enabled."""
    return read_state(str(path), expected_kind=KIND_AUTHORITY_EVIDENCE,
                      trust_anchor=anchor, witness_scope=SCOPE)


def _rechecksum(raw):
    """Recompute the local checksum (what a local attacker can do)."""
    raw["checksum"] = payload_checksum(raw["payload"])
    return raw


def test_real_service_sanity_and_attestation(real, tmp_path):
    """The real service accepts a genuine chain and attestations verify."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    _write(path, _payload("two"), anchor)
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.LOADED and res.sequence == 2
    # The live answer is validly signed by the pinned witness key.
    status, body = _http(real.endpoint, "GET", f"/latest/{SCOPE_PATH}",
                         token=real.token)
    assert status == 200
    assert verify_attestation(real.public_key, body["record"],
                              body["attestation"]) is True


def test_dec_rollback_replay_of_real_historical_pair(real, tmp_path):
    """CASE A — roll authority back to an older valid state (replayed pair)."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)          # seq 1
    historical_valid = path.read_bytes()           # the attacker keeps this
    _write(path, _payload("two"), anchor)          # seq 2
    path.write_bytes(historical_valid)             # roll authority back
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == "STALE"


def test_dec_lower_witness_floor_is_conflict(real, tmp_path):
    """CASE B — lower the witness floor / re-publish an older record -> 409."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    _write(path, _payload("two"), anchor)
    old_record = {"sequence": 1,
                  "state_hash": "0" * 64, "evidence_hash": "0" * 64,
                  "scope": SCOPE.to_dict()}
    # Attacker uses the producer writer token directly against the service.
    status, body = _http(real.endpoint, "POST", "/witness", old_record,
                         token=real.token)
    assert status == 409 and body["error"] == "conflict"
    # And the provider surfaces the deterministic conflict (not a downgrade).
    with pytest.raises(TrustAnchorConflict):
        anchor.witness(build_witness_record(
            kind=KIND_AUTHORITY_EVIDENCE, payload=_payload("one"),
            schema_version=1, sequence=1, scope=SCOPE))
    # The floor is unchanged: the genuine current state still loads.
    assert _read(path, anchor).outcome is StateOutcome.LOADED


def test_dec_forge_local_state_at_anchored_sequence(real, tmp_path):
    """CASE C — forge a locally consistent state+checksum at the anchored sequence."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    _write(path, _payload("two"), anchor)
    raw = json.loads(path.read_text())
    raw["payload"]["models"][CAP]["marker"] = "forged-authority"
    _rechecksum(raw)                       # attacker makes the local pair consistent
    path.write_text(json.dumps(raw))
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == "INVALID"


def test_dec_delete_local_state_for_first_run(real, tmp_path):
    """CASE D — delete local state to force a permissive first run (ROLLBACK)."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    path.unlink()
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == "ROLLBACK"


def test_dec_bump_sequence_above_witness(real, tmp_path):
    """CASE E — bump the sequence to look newer than the witness knows (UNKNOWN)."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    raw = json.loads(path.read_text())
    raw["sequence"] = 99
    _rechecksum(raw)
    path.write_text(json.dumps(raw))
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == "UNKNOWN"


def test_dec_older_state_with_newer_witness(real, tmp_path):
    """CASE F1 — replay an older state while the witness is newer (STALE)."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    old = path.read_bytes()
    _write(path, _payload("two"), anchor)
    _write(path, _payload("three"), anchor)        # witness now at seq 3
    path.write_bytes(old)                          # older state, newer witness
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == "STALE"


def test_dec_newer_state_with_older_witness(real, tmp_path):
    """CASE F2 — a state ahead of the witness cannot lower it (UNKNOWN)."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    raw = json.loads(path.read_text())
    raw["sequence"] = 5          # newer than the witnessed seq 1
    _rechecksum(raw)
    path.write_text(json.dumps(raw))
    res = _read(path, anchor)
    assert res.outcome is StateOutcome.CORRUPTED
    assert res.trust_verdict == "UNKNOWN"


def test_dec_attestation_cannot_be_forged_locally(real, tmp_path):
    """CASE G — with every producer credential, a forged witness answer fails."""
    # The attacker forges a plausible witness answer with a self-made signature.
    forged_record = {"sequence": 1, "state_hash": "a" * 64, "evidence_hash": "b" * 64,
                     "scope": SCOPE.to_dict()}
    forged_answer = {"alg": "rsa-pkcs1v15-sha256",
                     "key_id": real.public_key["key_id"], "sig": "00" * 128}
    assert verify_attestation(real.public_key, forged_record, forged_answer) is False
    # A locally-generated key cannot impersonate the pinned witness either.
    from telos.core.actions.witness_attest import (
        generate_private_key, public_from_private, sign_record)
    impostor = generate_private_key(1024)
    impostor_att = sign_record(forged_record, impostor)
    assert verify_attestation(real.public_key, forged_record, impostor_att) is False
    assert verify_attestation(public_from_private(impostor), forged_record,
                              impostor_att) is True


def test_dec_no_variant_yields_authority(real, tmp_path):
    """The aggregate: after every attack the state is never LOADED."""
    path = tmp_path / "state.json"
    anchor = _anchor(real)
    _write(path, _payload("one"), anchor)
    valid = path.read_bytes()
    _write(path, _payload("two"), anchor)

    variants = []
    # A: replay historical pair
    path.write_bytes(valid)
    variants.append(_read(path, anchor))
    # E: bump sequence
    _write(path, _payload("two"), anchor)
    raw = json.loads(path.read_text()); raw["sequence"] = 42; _rechecksum(raw)
    path.write_text(json.dumps(raw))
    variants.append(_read(path, anchor))
    # C: forge payload at anchored sequence
    _write(path, _payload("two"), anchor)
    raw = json.loads(path.read_text())
    raw["payload"]["models"][CAP]["marker"] = "forged"
    _rechecksum(raw); path.write_text(json.dumps(raw))
    variants.append(_read(path, anchor))
    # D: delete
    path.unlink()
    variants.append(_read(path, anchor))

    assert all(v.outcome is not StateOutcome.LOADED for v in variants)
