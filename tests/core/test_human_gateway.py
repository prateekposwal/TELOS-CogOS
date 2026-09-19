"""
HumanGateway (core/governance/human_gateway.py) — human-in-the-loop review.

Covers the trigger predicate, the three modes (auto/stdin/webhook), the
callback fan-out, and the review statistics.
"""
import pytest

from telos.core.governance.human_gateway import HumanGateway


def test_auto_mode_never_reviews_and_auto_approves():
    gw = HumanGateway(mode="auto")
    assert gw.should_review(council_validated=False, decision_integrity=0.0) is False
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.1)
    assert v.approved is True and v.reviewer == "auto"


def test_should_review_triggers_on_block_or_low_di():
    gw = HumanGateway(mode="stdin", auto_approve_threshold=0.3)
    assert gw.should_review(True, 0.9) is False
    assert gw.should_review(False, 0.9) is True
    assert gw.should_review(True, 0.1) is True


def test_stdin_approve(monkeypatch):
    gw = HumanGateway(mode="stdin")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")
    v = gw.review(intent="x", council_signals=[{"passed": False, "validator": "Reality", "reason": "nan"}],
                  decision_integrity=0.2, blocking_validator="Reality")
    assert v.approved is True and v.reviewer == "human"
    assert "approved" in v.override_reason


def test_stdin_deny(monkeypatch):
    gw = HumanGateway(mode="stdin")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "n")
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.2)
    assert v.approved is False and "denied" in v.override_reason


def test_stdin_modify(monkeypatch):
    gw = HumanGateway(mode="stdin")
    replies = iter(["modify", "do it differently"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(replies))
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.2)
    assert v.approved is True
    assert v.modified_intent == {"note": "do it differently"}
    assert "modified" in v.override_reason


def test_review_callback_fires_and_survives_errors():
    gw = HumanGateway(mode="auto")
    seen = []
    gw.on_review(lambda verdict, data: seen.append(verdict.approved))

    def boom(verdict, data):
        raise RuntimeError("callback blew up")

    gw.on_review(boom)
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.5)
    assert v.approved is True
    assert seen == [True]


def test_webhook_without_url_fails_closed():
    # CHANGE (fail-closed): a webhook mode with no endpoint is a
    # misconfiguration and DENIES — it no longer falls through to auto-approve.
    gw = HumanGateway(mode="webhook", webhook_url=None)
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.1)
    assert v.approved is False
    assert v.reviewer == "fail_closed"
    assert v.decision_source == "fail_closed"
    assert "fail_closed" in v.override_reason


def test_webhook_failure_fails_closed():
    # CHANGE (fail-closed): an unreachable URL must not hang the pipeline AND
    # must not approve. No evidence is never "yes".
    gw = HumanGateway(mode="webhook", webhook_url="https://127.0.0.1:9/nope")
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.1)
    assert v.approved is False
    assert v.reviewer == "fail_closed"
    assert v.decision_source == "fail_closed"


# ── Fail-closed webhook contract (tool-authorization safety) ────────────────
# (a) explicit APPROVE -> approved; (b) explicit DENY -> denied; (c) no answer /
# error / timeout / malformed -> DENIED, never approved.

class _Result:
    def __init__(self, allowed=True, body="", blocked_reason=None, status=200):
        self.allowed = allowed
        self.body = body
        self.blocked_reason = blocked_reason
        self.status = status


class _FakeEgress:
    """Deterministic stand-in for the NetworkSandbox egress channel."""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def request(self, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._result


def _webhook_gw(sandbox):
    gw = HumanGateway(mode="webhook", webhook_url="https://example.test/review")
    gw._sandbox = sandbox  # injected egress wins in _egress()
    return gw


def _review(gw):
    return gw.review(intent="tool:git_status", council_signals=[],
                     decision_integrity=0.1)


def test_webhook_explicit_approve_is_approved():
    gw = _webhook_gw(_FakeEgress(
        result=_Result(body='{"approved": true, "reason": "ok"}')))
    v = _review(gw)
    assert v.approved is True
    assert v.reviewer == "webhook"
    assert v.decision_source == "approve"
    assert v.override_reason == "ok"


def test_webhook_explicit_deny_is_denied():
    gw = _webhook_gw(_FakeEgress(
        result=_Result(body='{"approved": false, "reason": "no"}')))
    v = _review(gw)
    assert v.approved is False
    assert v.decision_source == "deny"


def test_webhook_error_fails_closed():
    for exc in (RuntimeError("boom"), OSError("unreachable"),
                TimeoutError("timed out")):
        gw = _webhook_gw(_FakeEgress(exc=exc))
        v = _review(gw)
        assert v.approved is False, f"{exc!r} must NOT approve"
        assert v.reviewer == "fail_closed"
        assert v.decision_source == "fail_closed"
        assert "fail_closed" in v.override_reason


def test_webhook_malformed_response_fails_closed():
    for body in ("not-json", "", "[1, 2, 3]", "null"):
        gw = _webhook_gw(_FakeEgress(result=_Result(body=body)))
        v = _review(gw)
        assert v.approved is False, f"body {body!r} must NOT approve"
        assert v.decision_source == "fail_closed"


def test_webhook_missing_or_non_bool_approved_fails_closed():
    for body in ('{"reason": "silent"}', '{"approved": "yes"}',
                 '{"approved": 1}', '{"approved": null}'):
        gw = _webhook_gw(_FakeEgress(result=_Result(body=body)))
        v = _review(gw)
        assert v.approved is False, f"body {body!r} must NOT approve"
        assert v.decision_source == "fail_closed"


def test_webhook_egress_blocked_fails_closed():
    gw = _webhook_gw(_FakeEgress(
        result=_Result(allowed=False, blocked_reason="host not allowlisted")))
    v = _review(gw)
    assert v.approved is False
    assert v.decision_source == "fail_closed"
    assert "egress blocked" in v.override_reason


def test_review_crash_in_approval_logic_fails_closed(monkeypatch):
    # A crash in the verdict/approval logic must DENY, never approve.
    gw = HumanGateway(mode="webhook", webhook_url="https://example.test/review")

    def boom(self, data):
        raise RuntimeError("approval logic crashed")

    monkeypatch.setattr(HumanGateway, "_get_verdict", boom)
    v = gw.review(intent="tool:git_status", council_signals=[],
                  decision_integrity=0.1)
    assert v.approved is False
    assert v.reviewer == "fail_closed"
    assert v.decision_source == "fail_closed"


def test_stdin_eof_fails_closed(monkeypatch):
    # CHANGE (fail-closed): no answer on stdin (EOF) DENIES rather than raising.
    def eof(*args, **kwargs):
        raise EOFError("no input")

    monkeypatch.setattr("builtins.input", eof)
    gw = HumanGateway(mode="stdin")
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.1)
    assert v.approved is False
    assert v.decision_source == "fail_closed"


def test_stats_counts_reviews():
    gw = HumanGateway(mode="auto")
    gw.review(intent="a", council_signals=[], decision_integrity=0.5)
    gw.review(intent="b", council_signals=[], decision_integrity=0.5)
    s = gw.stats
    assert s["total_reviews"] == 2 and s["approved"] == 2 and s["denied"] == 0


def test_webhook_routes_through_governed_sandbox_with_parity():
    """The webhook POST now leaves via NetworkSandbox — same body, same parse.

    Parity proof: the exact review payload (`intent`, `decision_integrity`,
    `council_signals`) is POSTed to the operator-configured endpoint and the
    same `{approved, reason}` response is honoured (reviewer == "webhook").
    """
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from telos.core.actions.sandbox import EgressRule, NetworkSandbox

    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            captured["body"] = _json.loads(self.rfile.read(n))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_json.dumps(
                {"approved": False, "reason": "human says no"}).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        sb = NetworkSandbox(rules=[EgressRule(
            host="127.0.0.1", ports=(port,), routes=("/review",),
            methods=("POST",))])
        gw = HumanGateway(mode="webhook",
                          webhook_url=f"http://127.0.0.1:{port}/review",
                          sandbox=sb)
        v = gw.review(intent="do thing",
                      council_signals=[{"validator": "x", "passed": False}],
                      decision_integrity=0.2)
        assert v.approved is False
        assert v.reviewer == "webhook"
        assert v.override_reason == "human says no"
        assert captured["body"]["intent"] == "do thing"
        assert captured["body"]["decision_integrity"] == 0.2
    finally:
        server.shutdown()
