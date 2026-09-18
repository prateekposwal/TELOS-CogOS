"""
NetworkSandbox — the ONE governed egress channel (Phase 1).

PATTERN (one governed channel, extended to the network): TELOS already routes
every real-world *subprocess* through the audited ActionExecutor. Network access
had no equivalent — the chat providers opened `http.client` connections
directly. This sandbox is the network half of the same discipline: a request may
leave the process ONLY through this object, and only after passing hard,
non-tradeable bounds:

  1. scheme      — https (or http only for an explicit loopback host)
  2. host        — must be in the declared allowlist (exact or *.suffix)
  3. port        — must be in the declared port set (443/80 default)
  4. method/path — must be in the declared route allowlist for that host
  5. bounds      — request body, response body, and timeout are all capped

The sandbox performs the HTTP call itself (list-form, no shell, no dynamic
import tricks) and returns a bounded, audited ``NetworkResult``. It deliberately
does NOT retry, redirect, or follow Location headers: an unlisted host reached
via redirect would defeat the allowlist.

This module is the only network call site that the tool-channel scanner should
treat as governed (network half). Providers migrate onto it; until then their
existing sites remain documented bypasses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Hard bounds — a request outside these is rejected before any socket opens.
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0

# Loopback hosts may use plain http (local Ollama and similar dev services).
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class NetworkRejected(Exception):
    """Raised when a network request fails a sandbox gate (nothing is sent)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class EgressRule:
    """One host's allowed egress: ports + route prefixes.

    Attributes:
        host: exact host or a ``*.suffix`` wildcard.
        ports: permitted ports (default {443, 80}).
        routes: permitted path prefixes for this host.
        methods: permitted HTTP methods.
    """
    host: str
    ports: Tuple[int, ...] = (443, 80)
    routes: Tuple[str, ...] = ("/",)
    methods: Tuple[str, ...] = ("POST",)

    def host_matches(self, host: str) -> bool:
        """Whether a concrete hostname matches this rule.

        Args:
            host: the requested hostname (lowercase).

        Returns:
            True on exact match or wildcard suffix match.
        """
        if self.host.startswith("*."):
            return host.endswith(self.host[1:]) or host == self.host[2:]
        return host == self.host


def default_egress_rules() -> List[EgressRule]:
    """The declared egress allowlist for TELOS's known providers.

    Returns:
        List of EgressRule covering local Ollama + the cloud chat providers.
    """
    return [
        EgressRule(
            host="localhost", ports=(11434,), routes=("/api/",),
            methods=("POST",),
        ),
        EgressRule(
            host="127.0.0.1", ports=(11434,), routes=("/api/",),
            methods=("POST",),
        ),
        EgressRule(
            host="api.openai.com", ports=(443,), routes=("/v1/",),
            methods=("POST",),
        ),
        EgressRule(
            host="api.anthropic.com", ports=(443,), routes=("/v1/",),
            methods=("POST",),
        ),
    ]


@dataclass
class NetworkResult:
    """The audited outcome of one sandboxed request (allowed OR blocked).

    Attributes:
        url: the requested URL (sans query, which may carry secrets).
        allowed: True only when every gate passed and a response came back.
        blocked_reason: the failing gate when nothing was sent.
        status: HTTP status code (None when blocked).
        body: bounded response body text.
        duration_ms: wall time of the exchange.
        bytes_sent: request body size.
        bytes_received: response body size (pre-truncation).
    """
    url: str
    allowed: bool
    blocked_reason: Optional[str] = None
    status: Optional[int] = None
    body: str = ""
    duration_ms: float = 0.0
    bytes_sent: int = 0
    bytes_received: int = 0

    def to_dict(self) -> Dict:
        """Serializable audit record."""
        return {
            "url": self.url,
            "allowed": self.allowed,
            "blocked_reason": self.blocked_reason,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "body_head": self.body[:2000],
        }


class NetworkSandbox:
    """The single governed egress channel: allowlisted hosts, bounded payloads."""

    def __init__(self, rules: Optional[List[EgressRule]] = None,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 allow_loopback_http: bool = True):
        """Construct a sandbox over an egress allowlist.

        Args:
            rules: the egress rules (defaults to default_egress_rules()).
            timeout: per-request timeout in seconds.
            allow_loopback_http: permit plain http to loopback hosts only.
        """
        self.rules = list(default_egress_rules() if rules is None else rules)
        self.timeout = max(1.0, float(timeout))
        self.allow_loopback_http = bool(allow_loopback_http)
        self.allowed_count = 0
        self.blocked_count = 0

    def _match(self, host: str, port: int, method: str, path: str) -> Optional[EgressRule]:
        """Find a rule authorizing this request, or None.

        Args:
            host: requested hostname (lowercase).
            port: requested port.
            method: HTTP method (uppercase).
            path: request path.

        Returns:
            The authorizing EgressRule, or None.
        """
        for rule in self.rules:
            if not rule.host_matches(host):
                continue
            if port not in rule.ports:
                continue
            if method not in rule.methods:
                continue
            if any(path.startswith(prefix) for prefix in rule.routes):
                return rule
        return None

    def request(self, method: str, url: str, body: Optional[str] = None,
                headers: Optional[Dict[str, str]] = None) -> NetworkResult:
        """Validate and perform one sandboxed HTTP request.

        Args:
            method: HTTP method (e.g. "POST").
            url: the absolute URL to request.
            body: optional request body.
            headers: optional request headers.

        Returns:
            A NetworkResult: allowed=True only when every gate passed and a
            response was read; every other path is a block record.
        """
        parsed = urlparse(url)
        redacted = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        started = time.monotonic()
        result = NetworkResult(url=redacted, allowed=False)
        method_u = (method or "").upper()

        # Gate 1: scheme (loopback may use http; everything else must be https).
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if scheme not in ("http", "https"):
            result.blocked_reason = f"unsupported scheme {scheme!r}"
            self.blocked_count += 1
            return result
        if scheme == "http" and not (self.allow_loopback_http and host in LOOPBACK_HOSTS):
            result.blocked_reason = "plain http allowed only for loopback hosts"
            self.blocked_count += 1
            return result

        # Gate 2/3/4: host + port + route (one rule must authorize all three).
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"
        if self._match(host, port, method_u, path) is None:
            result.blocked_reason = (
                f"egress denied: {method_u} {host}:{port}{path} is not in the "
                "sandbox allowlist"
            )
            self.blocked_count += 1
            return result

        # Gate 5: request bound.
        body = body or ""
        if len(body.encode("utf-8")) > MAX_REQUEST_BYTES:
            result.blocked_reason = (
                f"request body exceeds {MAX_REQUEST_BYTES} bytes"
            )
            self.blocked_count += 1
            return result

        # All gates passed: perform the request with stdlib http.client, plain
        # list-form arguments, no redirects, bounded response.
        try:
            import http.client
            conn = (
                http.client.HTTPSConnection(host, port, timeout=self.timeout)
                if scheme == "https"
                else http.client.HTTPConnection(host, port, timeout=self.timeout)
            )
            try:
                send_headers = dict(headers or {})
                send_headers.setdefault("Content-Type", "application/json")
                conn.request(method_u, path, body=body, headers=send_headers)
                resp = conn.getresponse()
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
                result.status = resp.status
                result.bytes_received = len(raw)
                result.body = raw[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
            finally:
                conn.close()
        except Exception as e:  # network failures are recorded, never raised raw
            result.blocked_reason = f"network error: {type(e).__name__}: {e}"
            result.duration_ms = (time.monotonic() - started) * 1000.0
            self.blocked_count += 1
            return result

        result.bytes_sent = len(body.encode("utf-8"))
        result.allowed = True
        result.duration_ms = (time.monotonic() - started) * 1000.0
        self.allowed_count += 1
        return result

    def stats(self) -> Dict[str, int]:
        """Return the sandbox's lifetime counters.

        Returns:
            Dict with allowed/blocked counts and rule count.
        """
        return {
            "allowed": self.allowed_count,
            "blocked": self.blocked_count,
            "rules": len(self.rules),
        }


__all__ = [
    "NetworkSandbox", "NetworkResult", "NetworkRejected", "EgressRule",
    "default_egress_rules", "MAX_REQUEST_BYTES", "MAX_RESPONSE_BYTES",
    "LOOPBACK_HOSTS",
]
