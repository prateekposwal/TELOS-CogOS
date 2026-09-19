"""
A minimal reference EXTERNAL witness service for the trust-anchor tests.

This is a STAND-IN for a genuine external service: it lives in-process on
loopback so the tests are deterministic. It implements the witnessed-record
contract the ``ExternalHttpTrustAnchor`` client speaks:

    POST /establish  -> bind a scope, return the witness identity
    GET  /health     -> liveness
    POST /witness    -> store a record; idempotent on an identical duplicate,
                        CONFLICT (409) on a same-sequence divergence or any
                        attempt to lower the stored freshness floor
    GET  /latest     -> the latest record for a scope (404 when none)

The server keeps the authoritative monotonic floor. An attacker who controls
the local filesystem but NOT this service cannot move the floor backward.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

WITNESS_ID = "test-external-witness"
WITNESS_VERSION = 1


def _scope_key(scope: Dict[str, str]) -> Tuple[str, str, str, str]:
    """The storage key for a scope.

    Args:
        scope: the scope mapping.

    Returns:
        A tuple key stable across requests.
    """
    return (str(scope.get("store_id", "")), str(scope.get("producer_id", "")),
            str(scope.get("world_id", "")), str(scope.get("capability_id", "")))


class WitnessStore:
    """Thread-safe in-memory witness store (the external authority)."""

    def __init__(self, token: Optional[str] = None):
        """Construct the store.

        Args:
            token: optional writer token required on writes.
        """
        self._lock = threading.Lock()
        self._latest: Dict[Tuple[str, str, str, str], Dict] = {}
        self.token = token
        self.witness_calls = 0
        self.conflicts = 0

    def get(self, scope: Dict[str, str]) -> Optional[Dict]:
        """The latest record for a scope.

        Args:
            scope: the scope mapping.

        Returns:
            The stored record, or None.
        """
        with self._lock:
            rec = self._latest.get(_scope_key(scope))
            return None if rec is None else json.loads(json.dumps(rec))

    def witness(self, record: Dict) -> Tuple[int, Dict]:
        """Store a record, enforcing the monotonic floor.

        Args:
            record: the record mapping.

        Returns:
            ``(status, body)``: 200 on accept/idempotent-duplicate, 409 on a
            same-sequence divergence or an attempted rollback of the floor.
        """
        with self._lock:
            self.witness_calls += 1
            scope = record.get("scope") or {}
            key = _scope_key(scope)
            stored = self._latest.get(key)
            seq = int(record.get("sequence", -1))
            if stored is not None:
                sseq = int(stored["sequence"])
                identical = (
                    seq == sseq
                    and record.get("state_hash") == stored.get("state_hash")
                    and record.get("evidence_hash") == stored.get("evidence_hash"))
                if identical:
                    return 200, {"ok": True, "record": stored, "duplicate": True}
                if seq <= sseq:
                    self.conflicts += 1
                    return 409, {"ok": False, "error": "conflict",
                                 "detail": f"sequence {seq} <= stored {sseq}"}
            self._latest[key] = json.loads(json.dumps(record))
            return 200, {"ok": True, "record": self._latest[key]}

    def dump(self) -> Dict:
        """A snapshot of the stored records (for assertions).

        Returns:
            Mapping of scope-key tuple (as a list) to record.
        """
        with self._lock:
            return {"|".join(k): json.loads(json.dumps(v))
                    for k, v in self._latest.items()}


def _make_handler(store: WitnessStore):
    """Build a request handler bound to a store.

    Args:
        store: the witness store.

    Returns:
        A BaseHTTPRequestHandler subclass.
    """

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # pragma: no cover - silence test logs
            """Suppress the default stderr access log.

            Args:
                *args: ignored.
            """
            return

        def _send(self, status: int, body: Dict) -> None:
            """Send a JSON response.

            Args:
                status: the HTTP status.
                body: the JSON-serializable body.
            """
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _authorized(self) -> bool:
            """Whether the request carries the writer token when required.

            Returns:
                True when writes are permitted.
            """
            if not store.token:
                return True
            return self.headers.get("Authorization") == f"Bearer {store.token}"

        def do_GET(self):  # noqa: N802 - http.server contract
            """Handle GET /health and /latest."""
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(200, {"ok": True, "detail": "ok"})
                return
            if parsed.path.startswith("/latest"):
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "unauthorized"})
                    return
                parts = [unquote(p) for p in parsed.path.strip("/").split("/")]
                fields = ("store_id", "producer_id", "world_id", "capability_id")
                scope = dict(zip(fields, parts[1:]))
                rec = store.get(scope)
                if rec is None:
                    self._send(404, {"ok": False, "error": "no record"})
                    return
                self._send(200, {"ok": True, "record": rec})
                return
            self._send(404, {"ok": False, "error": "unknown path"})

        def do_POST(self):  # noqa: N802 - http.server contract
            """Handle POST /establish and /witness."""
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                self._send(400, {"ok": False, "error": "bad json"})
                return
            if parsed.path == "/establish":
                self._send(200, {"ok": True, "identity": {
                    "witness_id": WITNESS_ID,
                    "witness_version": WITNESS_VERSION,
                    "externally_independent": True,
                }})
                return
            if parsed.path == "/witness":
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "unauthorized"})
                    return
                status, resp = store.witness(body)
                self._send(status, resp)
                return
            self._send(404, {"ok": False, "error": "unknown path"})

    return _Handler


class WitnessServerHarness:
    """A running loopback witness service (context manager)."""

    def __init__(self, token: Optional[str] = None):
        """Construct (not yet start) the server.

        Args:
            token: optional required writer token.
        """
        self.store = WitnessStore(token=token)
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0), _make_handler(self.store))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)

    @property
    def port(self) -> int:
        """The bound loopback port.

        Returns:
            The TCP port.
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
        """Start the server thread.

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
