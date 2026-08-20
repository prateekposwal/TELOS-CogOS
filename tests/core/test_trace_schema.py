"""Trace schema contract — canonical alias keys for every consumer.

PATTERN FIX (schema drift): consumers historically invented their own field
names (intent / discrimination_index / action_taken) while the producer only
emitted selected_intent / decision_integrity / selected_action. Dashboard
hero/story JS silently fell back to placeholders ("a decision") and audit
readers saw nulls. This test LOCKS the canonical contract so the drift cannot
recur without a red test.
"""

import json
import numpy as np
import pytest

from telos.core.types import DecisionTrace, DomainFacts
from telos.audit.monitor import TransparencyMonitor, MonitorConfig


def _make_trace(with_action=True, tmp_path=None):
    facts = DomainFacts(
        state=np.zeros(2),
        resources={"energy": 1.0},
        constraints=[], events=[], metrics={},
    )
    from telos.intent_ir import IntentIR
    si = IntentIR(intent_type="goal_seek", confidence=0.9)
    action = np.array([0.6, -0.4]) if with_action else None
    return DecisionTrace(
        cycle_id=3,
        timestamp=0.0,
        world_state_snapshot=np.zeros(2),
        domain_facts=facts,
        stream_activations=[],
        selected_intent=si,
        selected_action=action,
        representation="spatial",
        budget_consumed_ms=10.0,
        budget_total_ms=100.0,
        worlds_simulated=2,
        cycle_duration_ms=5.0,
        decision_integrity=0.97,
        mission_drift=0.12,
    )


def test_to_dict_emits_canonical_aliases():
    d = _make_trace().to_dict()
    # The three aliases every consumer queries MUST exist at top level...
    assert "intent" in d and "discrimination_index" in d and "action_taken" in d
    # ...and MUST equal the canonical fields (single source of truth).
    assert d["intent"] == d["selected_intent"]["type"] == "goal_seek"
    assert d["discrimination_index"] == d["decision_integrity"] == 0.97
    assert list(d["action_taken"]) == list(d["selected_action"])


def test_aliases_are_null_when_action_missing():
    """Perceive-only cycles (no action emitted) must serialize honest nulls,
    not fabricated values — the log's current gap exactly."""
    d = _make_trace(with_action=False).to_dict()
    assert d["intent"] == "goal_seek"       # intent still known
    assert d["action_taken"] is None        # action genuinely absent
    assert d["selected_action"] is None
    assert d["discrimination_index"] == d["decision_integrity"]


def test_transparency_monitor_log_contains_aliases(tmp_path):
    """The persisted decision log must carry the aliases — the actual artifact
    the handoff/dashboard audit reads.

    Args:
        tmp_path: pytest tmp dir where the monitor writes its log.
    """
    cfg = MonitorConfig(output_dir=str(tmp_path))
    mon = TransparencyMonitor(cfg)
    mon.record(_make_trace())
    data = json.loads(open(str(tmp_path / "decision_log.json")).read())
    t = data["traces"][0]
    assert t["intent"] == "goal_seek"
    assert t["discrimination_index"] == 0.97
    assert t["action_taken"] is not None


def test_producer_broadcast_allowlist_includes_aliases():
    """The WebSocket frame the live dashboard receives must carry the aliases
    (hero.js/story.js read trace.intent)."""
    from telos.dashboard.producer import DashboardProducer
    fields = set(DashboardProducer.BROADCAST_TRACE_FIELDS)
    assert {"intent", "discrimination_index", "action_taken"} <= fields
