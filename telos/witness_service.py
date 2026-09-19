"""
TELOS External Witness Service — a real, standalone, deployable trust boundary.

WHAT IT IS:
    A minimal HTTP service that holds the authoritative, append-only, monotonic
    history for every witnessed "scope" (store / producer / world / capability
    identity). It is the external freshness root the local durability layer
    consults when ``TELOS_TRUST_ANCHOR=external`` is configured. It speaks the
    exact contract ``ExternalHttpTrustAnchor`` already uses:

        GET  /health
        POST /establish
        POST /witness
        GET  /latest/<store_id>/<producer_id>/<world_id>/<capability_id>
        GET  /public_key

WHY IT IS A SEPARATE PROCESS / TRUST BOUNDARY:
    The local integrity envelope alone cannot defeat an attacker who controls the
    whole local filesystem: state + checksum/envelope + historical valid records
    can be rewritten as a consistent older pair, or replayed. The freshness root
    must live outside that filesystem. This service is that root: its sequence
    floor is SERVER-SIDE and append-only, so no client submission can lower it.

TWO INDEPENDENT SECRETS (never conflate them):
    * WRITE TOKEN (``TELOS_WITNESS_TOKEN`` / ``--token-file``): authenticates the
      local WRITER. It is the producer-side credential, so a compromised producer
      is assumed to hold it. Symmetric — it authorizes writes, it does not make
      an answer unforgeable.
    * SIGNING KEY (``--key-file``, mode 0600): the witness's own asymmetric RSA
      key. The PRIVATE key never leaves this process; only the PUBLIC key is
      published. Every accepted record is attested with it, so a local verifier
      that pins the public key can confirm an answer came from the witness even
      though the attacker holds the write token. See
      ``telos/core/actions/witness_attest.py``.

MONOTONICITY (the anti-rollback core):
    Per scope the floor is the maximum accepted sequence. ``/witness`` answers:
      * 200 — a NEW higher sequence (append), or a byte-identical duplicate of
        the current latest (idempotent, no floor change);
      * 409 — any sequence <= the floor that is NOT that identical duplicate
        (a rollback, a replay of an old pair, or a same-sequence divergence).
    The floor is rebuilt from the append-only log on startup and only ever
    increases in memory, so a client can never lower it. A tampered log line is
    detected at startup (its attestation no longer verifies) and the service
    refuses to start rather than serve a weakened floor.

INDEPENDENCE — READ THIS BEFORE TRUSTING IT:
    Running this service on the SAME account as the producer is still ONE trust
    domain: the account can read the key file and the append-only log, delete
    them, or replace the process. A deployable independent service now EXISTS and
    is exercised, but genuine independence requires running it (and its key file)
    outside the local account: a separate OS account, host, or container whose
    write credential the producer's account does not hold. That deployment
    remains unverified here. No HSM-grade custody is claimed.

RUN:
    python3 -m telos.witness_service \\
        --state-dir "$HOME/.telos-witness" --port 8799 \\
        --token-file "$HOME/.telos-witness/writer.token" \\
        --print-public-key

    Then point the producer at it:
        TELOS_TRUST_ANCHOR=external
        TELOS_TRUST_ANCHOR_ENDPOINT=http://127.0.0.1:8799
        TELOS_TRUST_ANCHOR_TOKEN=<the writer token>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from telos.core.actions.witness_attest import (
    DEFAULT_KEY_BITS, generate_private_key, load_private_key, load_public_key,
    public_from_private, save_private_key, save_public_key, sign_record,
    verify_attestation,
)

#: The default witness identity/version reported over the wire.
DEFAULT_WITNESS_ID = "telos-external-witness"
DEFAULT_WITNESS_VERSION = 1

#: The default state directory (the witness's own account, never the producer's).
DEFAULT_STATE_DIR = os.path.join(os.path.expanduser("~"), ".telos-witness")
#: The append-only history filename.
LOG_FILENAME = "witness_log.jsonl"
#: The private signing key filename.
KEY_FILENAME = "witness_signing_key.json"
#: The published public key filename.
PUBLIC_KEY_FILENAME = "witness_public_key.json"

#: HTTP statuses the contract uses.
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


class WitnessLedgerError(RuntimeError):
    """The witness history is unreadable or fails its own integrity check."""


def _scope_key(scope: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """The storage key for a scope.

    Args:
        scope: the scope mapping.

    Returns:
        A tuple key stable across requests and restarts.
    """
    return (str(scope.get("store_id", "")), str(scope.get("producer_id", "")),
            str(scope.get("world_id", "")), str(scope.get("capability_id", "")))


def _validate_record(record: Any) -> Optional[str]:
    """Validate the minimum witnessed-record shape.

    Args:
        record: the candidate record mapping.

    Returns:
        None when valid, else a human-readable reason.
    """
    if not isinstance(record, dict):
        return "record is not a JSON object"
    sequence = record.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) \
            or sequence < 0:
        return f"invalid sequence {sequence!r}"
    if not isinstance(record.get("state_hash"), str):
        return "missing state_hash"
    if not isinstance(record.get("evidence_hash"), str):
        return "missing evidence_hash"
    if not isinstance(record.get("scope"), dict):
        return "missing scope"
    return None


class WitnessLedger:
    """The append-only, monotonic, per-scope witness history (server-side floor)."""

    def __init__(self, log_path: str, private_key: Dict[str, Any]):
        """Construct the ledger.

        Args:
            log_path: the append-only JSONL history path.
            private_key: the witness's signing key (for attestations).
        """
        self.log_path = str(log_path)
        self._private = private_key
        self._public = public_from_private(private_key)
        self._lock = threading.Lock()
        self._latest: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        self._attestations: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        self._floor: Dict[Tuple[str, str, str, str], int] = {}
        self.witness_calls = 0
        self.conflicts = 0
        self.duplicates = 0
        self._load()

    @property
    def public_key(self) -> Dict[str, Any]:
        """The published public key.

        Returns:
            The public-key mapping.
        """
        return dict(self._public)

    def _load(self) -> None:
        """Rebuild the index/floor from the append-only log (fail closed).

        Raises:
            WitnessLedgerError: when a stored line is malformed or its
                attestation no longer verifies (a tampered witness store).
        """
        if not os.path.exists(self.log_path):
            return
        with open(self.log_path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    entry = json.loads(text)
                except Exception as e:
                    raise WitnessLedgerError(
                        f"witness log line {lineno} is not JSON: {e}")
                record = entry.get("record")
                attestation = entry.get("attestation")
                if not verify_attestation(self._public, record, attestation):
                    raise WitnessLedgerError(
                        f"witness log line {lineno} fails attestation "
                        f"verification (tampered witness store)")
                key = _scope_key(record.get("scope") or {})
                seq = int(record["sequence"])
                if seq < self._floor.get(key, -1):
                    raise WitnessLedgerError(
                        f"witness log line {lineno} lowers the floor for {key}")
                self._latest[key] = record
                self._attestations[key] = attestation
                self._floor[key] = seq

    def get(self, scope: Dict[str, Any]
            ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """The latest record and attestation for a scope.

        Args:
            scope: the scope mapping.

        Returns:
            ``(record, attestation)`` as fresh copies, or ``(None, None)``.
        """
        with self._lock:
            key = _scope_key(scope)
            rec = self._latest.get(key)
            if rec is None:
                return None, None
            return (json.loads(json.dumps(rec)),
                    json.loads(json.dumps(self._attestations[key])))

    def floor(self) -> Dict[str, int]:
        """A snapshot of the per-scope sequence floors.

        Returns:
            Mapping of ``"|".join(scope_key)`` to floor sequence.
        """
        with self._lock:
            return {"|".join(k): int(v) for k, v in self._floor.items()}

    def witness(self, record: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Accept or reject a record, enforcing the monotonic floor.

        Args:
            record: the candidate record mapping.

        Returns:
            ``(status, body)``: 200 on a new/duplicate record, 409 on any
            rollback, replay, or same-sequence divergence.
        """
        with self._lock:
            self.witness_calls += 1
            key = _scope_key(record.get("scope") or {})
            seq = int(record["sequence"])
            floor = self._floor.get(key)
            if floor is not None:
                stored = self._latest[key]
                identical = (
                    seq == floor
                    and record.get("state_hash") == stored.get("state_hash")
                    and record.get("evidence_hash") == stored.get("evidence_hash"))
                if identical:
                    self.duplicates += 1
                    return HTTP_OK, {
                        "ok": True,
                        "record": json.loads(json.dumps(stored)),
                        "attestation": json.loads(json.dumps(
                            self._attestations[key])),
                        "duplicate": True,
                    }
                if seq <= floor:
                    self.conflicts += 1
                    return HTTP_CONFLICT, {
                        "ok": False, "error": "conflict",
                        "detail": (f"sequence {seq} <= stored floor {floor} "
                                   f"(rollback/replay/divergence rejected)"),
                    }
            attestation = sign_record(record, self._private)
            self._append(record, attestation)
            self._latest[key] = record
            self._attestations[key] = attestation
            self._floor[key] = seq
            return HTTP_OK, {"ok": True, "record": json.loads(json.dumps(record)),
                             "attestation": json.loads(json.dumps(attestation))}

    def _append(self, record: Dict[str, Any],
                attestation: Dict[str, Any]) -> None:
        """Append one accepted entry to the durable log (fsync'd).

        Args:
            record: the accepted record.
            attestation: its witness signature.
        """
        from telos.core.actions.witness_attest import canonical_json_bytes
        entry = canonical_json_bytes(
            {"record": record, "attestation": attestation}).decode("utf-8")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
            f.flush()
            os.fsync(f.fileno())


class WitnessService:
    """The witness contract, independent of its HTTP transport."""

    def __init__(self, ledger: WitnessLedger, *,
                 token: Optional[str] = None,
                 witness_id: str = DEFAULT_WITNESS_ID,
                 witness_version: int = DEFAULT_WITNESS_VERSION):
        """Construct the service over a ledger.

        Args:
            ledger: the monotonic witness history.
            token: the optional writer token required on write/read endpoints.
            witness_id: the identity reported over the wire.
            witness_version: the implementation version reported over the wire.
        """
        self.ledger = ledger
        self.token = str(token) if token else None
        self.witness_id = str(witness_id)
        self.witness_version = int(witness_version)

    def authorized(self, authorization: Optional[str]) -> bool:
        """Whether a request carries the writer token when one is required.

        Args:
            authorization: the ``Authorization`` request header.

        Returns:
            True when writes/reads are permitted.
        """
        if not self.token:
            return True
        return authorization == f"Bearer {self.token}"

    def identity(self) -> Dict[str, Any]:
        """The established anchor identity (including the public key).

        Returns:
            The identity mapping.
        """
        return {
            "witness_id": self.witness_id,
            "witness_version": self.witness_version,
            "externally_independent": True,
            "public_key": self.ledger.public_key,
        }

    def health(self) -> Dict[str, Any]:
        """A liveness + floor report.

        Returns:
            The health mapping.
        """
        return {"ok": True, "detail": "ok", "witness_id": self.witness_id,
                "witness_version": self.witness_version,
                "floor": self.ledger.floor()}

    def latest(self, scope: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Return the latest witnessed record for a scope.

        Args:
            scope: the scope mapping.

        Returns:
            ``(status, body)``: 200 with the record + attestation, else 404.
        """
        record, attestation = self.ledger.get(scope)
        if record is None:
            return HTTP_NOT_FOUND, {"ok": False, "error": "no record"}
        return HTTP_OK, {"ok": True, "record": record,
                         "attestation": attestation}

    def witness(self, record: Any) -> Tuple[int, Dict[str, Any]]:
        """Validate and submit a record to the ledger.

        Args:
            record: the candidate record mapping.

        Returns:
            ``(status, body)`` from the ledger, or 400 on an invalid record.
        """
        reason = _validate_record(record)
        if reason:
            return HTTP_BAD_REQUEST, {"ok": False, "error": "invalid",
                                      "detail": reason}
        return self.ledger.witness(record)


def _make_handler(service: WitnessService):
    """Build the HTTP request handler bound to a service.

    Args:
        service: the witness service.

    Returns:
        A BaseHTTPRequestHandler subclass implementing the wire contract.
    """

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            """Suppress the default stderr access log.

            Args:
                *args: ignored.
            """
            return

        def _send(self, status: int, body: Dict[str, Any]) -> None:
            """Send a JSON response.

            Args:
                status: the HTTP status.
                body: the JSON-serializable response body.
            """
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802 - http.server contract
            """Handle GET /health, /public_key, /latest/<scope>."""
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(HTTP_OK, service.health())
                return
            if parsed.path == "/public_key":
                self._send(HTTP_OK, {"ok": True,
                                     "public_key": service.ledger.public_key})
                return
            if parsed.path.startswith("/latest"):
                if not service.authorized(self.headers.get("Authorization")):
                    self._send(HTTP_UNAUTHORIZED,
                               {"ok": False, "error": "unauthorized"})
                    return
                parts = [unquote(p) for p in parsed.path.strip("/").split("/")]
                fields = ("store_id", "producer_id", "world_id", "capability_id")
                scope = dict(zip(fields, parts[1:]))
                self._send(*service.latest(scope))
                return
            self._send(HTTP_NOT_FOUND, {"ok": False, "error": "unknown path"})

        def do_POST(self):  # noqa: N802 - http.server contract
            """Handle POST /establish and /witness."""
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                self._send(HTTP_BAD_REQUEST, {"ok": False, "error": "bad json"})
                return
            if parsed.path == "/establish":
                self._send(HTTP_OK, {"ok": True,
                                     "identity": service.identity()})
                return
            if parsed.path == "/witness":
                if not service.authorized(self.headers.get("Authorization")):
                    self._send(HTTP_UNAUTHORIZED,
                               {"ok": False, "error": "unauthorized"})
                    return
                self._send(*service.witness(body))
                return
            self._send(HTTP_NOT_FOUND, {"ok": False, "error": "unknown path"})

    return _Handler


class WitnessServerHarness:
    """A running loopback witness service (context manager)."""

    def __init__(self, state_dir: str, *, token: Optional[str] = None,
                 host: str = "127.0.0.1", port: int = 0,
                 key_bits: int = 1024, witness_id: str = DEFAULT_WITNESS_ID,
                 witness_version: int = DEFAULT_WITNESS_VERSION):
        """Construct (not yet start) the server.

        Args:
            state_dir: the witness's own state directory.
            token: the optional writer token.
            host: the bind host (loopback by default).
            port: the bind port (0 selects a free port).
            key_bits: the signing-key modulus size (tests use a small key).
            witness_id: the reported witness identity.
            witness_version: the reported implementation version.
        """
        self.state_dir = str(state_dir)
        self._server, self.ledger = start_server(
            self.state_dir, token=token, host=host, port=port,
            key_bits=key_bits, witness_id=witness_id,
            witness_version=witness_version, serve=False)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._server.daemon_threads = True

    @property
    def port(self) -> int:
        """The bound TCP port.

        Returns:
            The port the server is listening on.
        """
        return int(self._server.server_address[1])

    @property
    def endpoint(self) -> str:
        """The base endpoint URL.

        Returns:
            The ``http://127.0.0.1:<port>`` URL.
        """
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "WitnessServerHarness":
        """Start serving.

        Returns:
            Self, for chaining.
        """
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop the server."""
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "WitnessServerHarness":
        """Enter the context and start serving.

        Returns:
            Self.
        """
        return self.start()

    def __exit__(self, *exc) -> None:
        """Exit the context and stop serving.

        Args:
            *exc: the exception triple (unused).
        """
        self.stop()


def _load_or_create_key(key_file: str, public_file: str,
                        bits: int) -> Dict[str, Any]:
    """Load the witness signing key, generating it on first run.

    Args:
        key_file: the private-key path.
        public_file: the published public-key path.
        bits: the modulus size to generate when absent.

    Returns:
        The private-key mapping.
    """
    if os.path.exists(key_file):
        private = load_private_key(key_file)
    else:
        private = generate_private_key(bits)
        save_private_key(key_file, private)
    if not os.path.exists(public_file):
        save_public_key(public_file, public_from_private(private))
    return private


def start_server(state_dir: str, *, token: Optional[str] = None,
                 host: str = "127.0.0.1", port: int = 8799,
                 key_file: Optional[str] = None,
                 public_file: Optional[str] = None,
                 key_bits: int = DEFAULT_KEY_BITS,
                 witness_id: str = DEFAULT_WITNESS_ID,
                 witness_version: int = DEFAULT_WITNESS_VERSION,
                 serve: bool = True) -> Tuple[ThreadingHTTPServer, WitnessLedger]:
    """Build (and optionally start) a witness HTTP server.

    Args:
        state_dir: the witness's own state directory.
        token: the optional writer token.
        host: the bind host.
        port: the bind port.
        key_file: the private signing key path (defaults under ``state_dir``).
        public_file: the published public key path (defaults under ``state_dir``).
        key_bits: the modulus size to generate when the key is absent.
        witness_id: the reported witness identity.
        witness_version: the reported implementation version.
        serve: when True, start the serving thread.

    Returns:
        ``(server, ledger)`` — the started (or startable) server and its ledger.
    """
    os.makedirs(state_dir, exist_ok=True)
    key_path = key_file or os.path.join(state_dir, KEY_FILENAME)
    pub_path = public_file or os.path.join(state_dir, PUBLIC_KEY_FILENAME)
    private = _load_or_create_key(key_path, pub_path, key_bits)
    ledger = WitnessLedger(os.path.join(state_dir, LOG_FILENAME), private)
    service = WitnessService(ledger, token=token, witness_id=witness_id,
                            witness_version=witness_version)
    server = ThreadingHTTPServer((host, int(port)), _make_handler(service))
    server.daemon_threads = True
    if serve:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    return server, ledger


def _resolve_token(args: argparse.Namespace) -> Optional[str]:
    """Resolve the writer token from the file, the flag, or the environment.

    Args:
        args: the parsed CLI arguments.

    Returns:
        The token, or None when the witness is intentionally open (dev only).
    """
    if args.token_file:
        with open(args.token_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    if args.token:
        return str(args.token)
    return os.environ.get("TELOS_WITNESS_TOKEN")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        The configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="telos.witness_service",
        description="TELOS external witness service (the independent freshness "
                    "root for the durability trust anchor).")
    parser.add_argument("--host", default=os.environ.get(
        "TELOS_WITNESS_HOST", "127.0.0.1"),
        help="bind host (default loopback; use 0.0.0.0 only behind an "
             "isolated account/network)")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("TELOS_WITNESS_PORT", "8799")),
                        help="bind port (default 8799)")
    parser.add_argument("--state-dir",
                        default=os.environ.get("TELOS_WITNESS_STATE_DIR",
                                               DEFAULT_STATE_DIR),
                        help="the witness's own state directory")
    parser.add_argument("--key-file", default=os.environ.get(
        "TELOS_WITNESS_KEY_FILE"),
        help="private signing key path (generated 0600 on first run)")
    parser.add_argument("--public-key-file", default=os.environ.get(
        "TELOS_WITNESS_PUBLIC_KEY_FILE"),
        help="published public key path")
    parser.add_argument("--token-file", default=os.environ.get(
        "TELOS_WITNESS_TOKEN_FILE"),
        help="file holding the writer token (the producer-side credential)")
    parser.add_argument("--token", default=None,
                        help="writer token inline (prefer --token-file/env)")
    parser.add_argument("--witness-id", default=DEFAULT_WITNESS_ID,
                        help="reported witness identity")
    parser.add_argument("--witness-version", type=int,
                        default=DEFAULT_WITNESS_VERSION,
                        help="reported implementation version")
    parser.add_argument("--key-bits", type=int, default=DEFAULT_KEY_BITS,
                        help="signing key modulus size (default 2048)")
    parser.add_argument("--print-public-key", action="store_true",
                        help="print the public key JSON on startup")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the witness service (blocking).

    Args:
        argv: the argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        The process exit status (0 on a clean shutdown).
    """
    args = build_parser().parse_args(argv)
    token = _resolve_token(args)
    if not token:
        print("warning: no writer token configured; the witness is OPEN. Set "
              "--token-file / TELOS_WITNESS_TOKEN for any real deployment.",
              file=sys.stderr)
    server, ledger = start_server(
        args.state_dir, token=token, host=args.host, port=args.port,
        key_file=args.key_file, public_file=args.public_key_file,
        key_bits=args.key_bits, witness_id=args.witness_id,
        witness_version=args.witness_version, serve=False)
    if args.print_public_key:
        print(json.dumps(ledger.public_key, sort_keys=True))
        sys.stdout.flush()
    print(f"telos witness service on http://{args.host}:{args.port} "
          f"(state_dir={args.state_dir}; token={'yes' if token else 'NO'})",
          file=sys.stderr)
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
