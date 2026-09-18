"""
NetworkSandbox — the ONE governed egress channel (Phase 1).

Every network request must pass the host/port/route allowlist and bounded
payload gates BEFORE any socket opens. These tests prove refusals happen
without sending anything, and that a legitimate loopback request works.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from telos.core.actions.sandbox import (
    NetworkSandbox, EgressRule, default_egress_rules,
    MAX_REQUEST_BYTES, NetworkRejected,
)


def test_default_rules_cover_known_providers():
    """The default allowlist covers Ollama + the cloud chat providers."""
    hosts = {r.host for r in default_egress_rules()}
    assert {"localhost", "127.0.0.1", "api.openai.com", "api.anthropic.com"} <= hosts


def test_https_required_for_non_loopback():
    """Plain http to a non-loopback host is refused with nothing sent."""
    sb = NetworkSandbox()
    result = sb.request("POST", "http://api.openai.com/v1/chat/completions", body="{}")
    assert result.allowed is False
    assert "loopback" in result.blocked_reason
    assert sb.blocked_count == 1


def test_unlisted_host_denied():
    """A host not in the allowlist is refused."""
    sb = NetworkSandbox()
    result = sb.request("POST", "https://evil.example.com/v1/chat", body="{}")
    assert result.allowed is False
    assert "egress denied" in result.blocked_reason


def test_unlisted_route_denied():
    """An allowlisted host on a non-allowlisted route is refused."""
    sb = NetworkSandbox()
    result = sb.request("POST", "https://api.openai.com/admin/keys", body="{}")
    assert result.allowed is False
    assert "egress denied" in result.blocked_reason


def test_unlisted_port_denied():
    """An allowlisted host on a non-allowlisted port is refused."""
    sb = NetworkSandbox()
    result = sb.request("POST", "https://api.openai.com:8443/v1/chat", body="{}")
    assert result.allowed is False
    assert "egress denied" in result.blocked_reason


def test_unsupported_scheme_denied():
    """A non-http(s) scheme is refused."""
    sb = NetworkSandbox()
    result = sb.request("POST", "ftp://api.openai.com/v1/x", body="{}")
    assert result.allowed is False
    assert "scheme" in result.blocked_reason


def test_oversized_body_denied_before_send():
    """A body over the bound is refused with a bound reason."""
    sb = NetworkSandbox()
    body = "x" * (MAX_REQUEST_BYTES + 1)
    result = sb.request("POST", "https://api.openai.com/v1/chat/completions", body=body)
    assert result.allowed is False
    assert "exceeds" in result.blocked_reason


def test_wildcard_rule_matches_suffix():
    """A *.suffix rule authorizes subdomains."""
    rule = EgressRule(host="*.example.com", ports=(443,), routes=("/v1/",))
    assert rule.host_matches("api.example.com") is True
    assert rule.host_matches("example.com") is True
    assert rule.host_matches("evil-example.com") is False


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args):
        pass


@pytest.fixture
def loopback_server():
    """A tiny loopback HTTP server for a real sanctioned request."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def test_loopback_request_succeeds_when_allowlisted(loopback_server):
    """A request matching an explicit loopback rule actually goes through."""
    port = loopback_server.server_address[1]
    rules = [EgressRule(host="127.0.0.1", ports=(port,), routes=("/api/",))]
    sb = NetworkSandbox(rules=rules)
    result = sb.request("POST", f"http://127.0.0.1:{port}/api/chat", body="{}")
    assert result.allowed is True
    assert result.status == 200
    assert '{"ok": true}' in result.body
    assert sb.allowed_count == 1


def test_audit_record_is_serializable(loopback_server):
    """The sandbox outcome serializes for the decision trace."""
    port = loopback_server.server_address[1]
    sb = NetworkSandbox(rules=[EgressRule(host="127.0.0.1", ports=(port,),
                                          routes=("/api/",))])
    result = sb.request("POST", f"http://127.0.0.1:{port}/api/chat", body="{}")
    d = result.to_dict()
    assert d["allowed"] is True and d["status"] == 200
    assert "url" in d


def test_stats_track_counts():
    """The sandbox counts allowed and blocked requests."""
    sb = NetworkSandbox()
    sb.request("POST", "https://evil.example.com/x", body="{}")
    stats = sb.stats()
    assert stats["blocked"] == 1
    assert stats["rules"] == len(sb.rules)
