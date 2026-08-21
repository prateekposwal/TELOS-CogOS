"""
Honest contract tests for telos/core/governance/human_gateway.py (HumanGateway).

Covers the stdin / webhook / auto modes and the approval contract. Auto mode
is used (or direct invocation) so these tests never block on stdin.
"""

import pytest

from telos.core.governance.human_gateway import HumanGateway, HumanVerdict


def test_auto_mode_never_requests_review():
    gw = HumanGateway(mode="auto")
    assert gw.should_review(council_validated=False, decision_integrity=0.0) is False
    assert gw.should_review(council_validated=True, decision_integrity=1.0) is False


def test_auto_review_approves():
    gw = HumanGateway(mode="auto")
    verdict = gw.review("an_intent", [{"validator": "x", "passed": False}], decision_integrity=0.1)
    assert isinstance(verdict, HumanVerdict)
    assert verdict.approved is True
    assert verdict.reviewer == "auto"
    assert verdict.override_reason == "auto_approve"


def test_non_auto_review_requested_when_council_not_validated():
    gw = HumanGateway(mode="stdin")
    assert gw.should_review(council_validated=False, decision_integrity=1.0) is True


def test_review_requested_when_integrity_below_threshold():
    gw = HumanGateway(mode="stdin", auto_approve_threshold=0.3)
    assert gw.should_review(council_validated=True, decision_integrity=0.2) is True


def test_review_not_requested_when_validated_and_integrity_high():
    gw = HumanGateway(mode="stdin", auto_approve_threshold=0.3)
    assert gw.should_review(council_validated=True, decision_integrity=0.9) is False


def test_review_records_review_and_stats():
    gw = HumanGateway(mode="auto")
    gw.review("intent_a", [{"validator": "v", "passed": True, "reason": "ok"}], decision_integrity=0.8)
    gw.review("intent_b", [{"validator": "v", "passed": False}], decision_integrity=0.2)
    stats = gw.stats
    assert stats["total_reviews"] == 2
    assert stats["approved"] == 2
    assert stats["denied"] == 0
    assert stats["mode"] == "auto"


def test_review_data_is_rounded_and_context_defaults():
    gw = HumanGateway(mode="auto")
    gw.review("intent", [], decision_integrity=0.123456, mission_drift=0.987654)
    entry = gw._reviews[-1]
    assert entry["decision_integrity"] == 0.123
    assert entry["mission_drift"] == 0.988
    assert entry["context"] == {}
    assert entry["verdict"] is True


def test_review_data_roundtrips_supplied_fields():
    gw = HumanGateway(mode="auto")
    gw.review(
        "intent",
        [{"validator": "v", "passed": False}],
        decision_integrity=0.5,
        mission_drift=0.2,
        blocking_validator="low_integrity",
        context={"world": "gridworld"},
    )
    entry = gw._reviews[-1]
    assert entry["intent"] == "intent"
    assert entry["council_signals"] == [{"validator": "v", "passed": False}]
    assert entry["blocking_validator"] == "low_integrity"
    assert entry["context"] == {"world": "gridworld"}


def test_callback_is_invoked_per_review():
    gw = HumanGateway(mode="auto")
    seen = []
    gw.on_review(lambda verdict, data: seen.append((verdict, data)))
    gw.review("i", [], decision_integrity=0.5)
    assert len(seen) == 1
    verdict, data = seen[0]
    assert verdict.approved is True
    assert data["intent"] == "i"


def test_webhook_mode_without_url_falls_back_to_auto_approve():
    gw = HumanGateway(mode="webhook", webhook_url=None)
    verdict = gw.review("i", [], decision_integrity=0.5)
    assert verdict.approved is True
    assert verdict.reviewer == "auto"


def test_webhook_mode_with_unreachable_url_auto_approves():
    # No server on localhost:1, so the webhook call fails and the gateway
    # auto-approves with a webhook_fallback reason. This must not raise.
    gw = HumanGateway(mode="webhook", webhook_url="https://127.0.0.1:1/review")
    verdict = gw.review("i", [], decision_integrity=0.5)
    assert verdict.approved is True
    assert verdict.override_reason.startswith("webhook_fallback")


def test_humangateway_default_mode_is_auto_approve():
    # Default construction auto-approves, so a bare gateway never blocks.
    gw = HumanGateway()
    assert gw._mode == "auto"
    assert gw.should_review(council_validated=False, decision_integrity=0.0) is False


def test_stdin_mode_constructs_without_prompting():
    # Merely constructing with stdin mode should not block; only review() does,
    # which we deliberately do not call.
    gw = HumanGateway(mode="stdin")
    assert gw._mode == "stdin"
    assert gw.stats["total_reviews"] == 0
