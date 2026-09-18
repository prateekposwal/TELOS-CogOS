"""
Governed network tool family (Phase 1).

http_get/http_post are registry tools whose egress goes ONLY through the
NetworkSandbox. An unlisted destination is a block record with no socket, and
the capability profile requires more than observability for network access.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from telos.core.actions.executor import ActionExecutor, ToolPermission
from telos.core.actions.registry import DEFAULT_REGISTRY, capability_profile_for
from telos.core.actions.sandbox import EgressRule, NetworkSandbox
from telos.core.governance.capability_authorization import (
    CapabilityStatus, from_dimensions,
)
from telos.core.governance.firewall import DecisionFirewall


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"answer": 42}')

    def log_message(self, *args):
        pass


@pytest.fixture
def loopback():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def test_network_tools_are_registered():
    """The network family is on the canonical registry."""
    assert DEFAULT_REGISTRY.get("http_post") is not None
    assert DEFAULT_REGISTRY.get("http_get") is not None
    assert "http_post" in DEFAULT_REGISTRY.families().get("network_read", [])


def test_network_profile_requires_more_than_observability():
    """A network tool requires causal_confidence, not just observability."""
    profile = capability_profile_for(DEFAULT_REGISTRY.get("http_post"))
    assert "causal_confidence" in profile
    assert "observability" in profile


def test_unlisted_host_blocked_no_socket(tmp_path, loopback):
    """An unlisted destination blocks with an egress reason and no connection."""
    ex = ActionExecutor(workspace_root=str(tmp_path))
    result = ex.execute(
        ToolPermission(tool_name="http_post", args=["https://evil.example.com/v1/x", "{}"],
                       permitted_by="operator"),
        firewall=DecisionFirewall(),
    )
    assert result.allowed is False
    assert "egress denied" in result.blocked_reason


def test_allowlisted_loopback_post_succeeds(tmp_path, loopback):
    """An explicitly allowlisted loopback POST actually returns a body."""
    port = loopback.server_address[1]
    sandbox = NetworkSandbox(
        rules=[EgressRule(host="127.0.0.1", ports=(port,), routes=("/api/",))]
    )
    ex = ActionExecutor(workspace_root=str(tmp_path), sandbox=sandbox)
    result = ex.execute(
        ToolPermission(tool_name="http_post",
                       args=[f"http://127.0.0.1:{port}/api/chat", "{}"],
                       permitted_by="operator"),
        firewall=DecisionFirewall(),
    )
    assert result.allowed is True
    assert result.returncode == 200
    assert '{"answer": 42}' in result.stdout


def test_network_tool_capability_veto(tmp_path, loopback):
    """A FAIL on causal_confidence vetoes the network tool."""
    port = loopback.server_address[1]
    sandbox = NetworkSandbox(
        rules=[EgressRule(host="127.0.0.1", ports=(port,), routes=("/api/",))]
    )
    ex = ActionExecutor(workspace_root=str(tmp_path), sandbox=sandbox)
    cap = from_dimensions({"causal_confidence": CapabilityStatus.FAIL})
    result = ex.execute(
        ToolPermission(tool_name="http_post",
                       args=[f"http://127.0.0.1:{port}/api/chat", "{}"],
                       permitted_by="operator"),
        firewall=DecisionFirewall(), capability=cap,
    )
    assert result.allowed is False
    assert "capability gate vetoed" in result.blocked_reason


def test_oversized_network_body_rejected(tmp_path):
    """An over-bound body is rejected during validation (no sandbox call)."""
    ex = ActionExecutor(workspace_root=str(tmp_path))
    result = ex.execute(
        ToolPermission(tool_name="http_post",
                       args=["https://api.openai.com/v1/chat/completions",
                             "x" * (256 * 1024 + 10)],
                       permitted_by="operator"),
        firewall=DecisionFirewall(),
    )
    assert result.allowed is False
    assert "exceeds" in result.blocked_reason


def test_non_absolute_url_rejected(tmp_path):
    """A relative URL fails {url} validation."""
    ex = ActionExecutor(workspace_root=str(tmp_path))
    result = ex.execute(
        ToolPermission(tool_name="http_get", args=["/v1/x"],
                       permitted_by="operator"),
        firewall=DecisionFirewall(),
    )
    assert result.allowed is False
    assert "absolute" in result.blocked_reason
