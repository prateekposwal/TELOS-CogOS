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


def test_webhook_without_url_falls_back_to_auto():
    gw = HumanGateway(mode="webhook", webhook_url=None)
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.1)
    assert v.approved is True and v.reviewer == "auto"


def test_webhook_failure_auto_approves():
    # An unreachable URL must not hang the pipeline — it falls back to auto.
    gw = HumanGateway(mode="webhook", webhook_url="https://127.0.0.1:9/nope")
    v = gw.review(intent="x", council_signals=[], decision_integrity=0.1)
    assert v.approved is True and v.reviewer == "auto"


def test_stats_counts_reviews():
    gw = HumanGateway(mode="auto")
    gw.review(intent="a", council_signals=[], decision_integrity=0.5)
    gw.review(intent="b", council_signals=[], decision_integrity=0.5)
    s = gw.stats
    assert s["total_reviews"] == 2 and s["approved"] == 2 and s["denied"] == 0
