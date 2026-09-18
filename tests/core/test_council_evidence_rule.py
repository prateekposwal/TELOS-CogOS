"""
Canonical rule regression: governance suppression is NOT evidence.

A council/firewall-blocked cycle yields `selected_action is None`, but counting
that as a "no-action outcome" for the intent type makes the council's own
suppression the evidence for the next suppression (a self-reinforcing
`low_integrity` loop). Only a genuinely unblocked no-action is evidence.
"""
import tempfile
from types import SimpleNamespace

from tests.core.test_loop_recovery import _build_pipeline


def _pipe():
    return _build_pipeline(tempfile.mkdtemp())


def _ctx(intent_type="blended_inquiry", blocked=False, no_action=False):
    return SimpleNamespace(
        selected_intent=SimpleNamespace(intent_type=intent_type),
        selected_action=None,
        firewall_blocked=blocked,
        council_blocked=False,
        no_action=no_action,
    )


def test_governance_suppressed_cycle_is_not_counted_as_evidence():
    p = _pipe()
    p._record_council_outcome(_ctx(blocked=True))
    assert p._council_total_no_action.get("blended_inquiry", 0) == 0
    assert p._council_recent_blocks == 1


def test_genuine_unblocked_no_action_is_counted():
    p = _pipe()
    p._record_council_outcome(_ctx(blocked=False, no_action=False))
    assert p._council_total_no_action["blended_inquiry"] == 1


def test_governor_hard_stop_is_not_counted():
    p = _pipe()
    p._record_council_outcome(_ctx(blocked=False, no_action=True))
    assert p._council_total_no_action.get("blended_inquiry", 0) == 0
