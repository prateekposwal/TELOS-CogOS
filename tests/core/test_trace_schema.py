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


# ═══════════════════════════════════════════════════════════════════════
# Audit Item 1 — decision-mode telemetry contract (ADDITIVE to the locked
# aliases above: only NEW fields, the canonical three aliases + carryover
# must stay byte-identical).
# ═══════════════════════════════════════════════════════════════════════

def test_to_dict_emits_decision_telemetry_fields():
    """decision_mode / blocked_by_gate / act_emitted_action must serialize —
    the WHY behind an approved no-op (the 93 silent cycles hid governor
    DEFER from the dashboard)."""
    t = _make_trace()
    t.act_emitted_action = True      # build_trace computes this at runtime
    d = t.to_dict()
    assert "decision_mode" in d and "blocked_by_gate" in d and "act_emitted_action" in d
    # Approved cycles with an action: mode ACT, no gate, action emitted.
    assert d["act_emitted_action"] is True
    # A DEFERed trace serializes its mode + gate honestly (Enum-safe too).
    from telos.core.governance.governor import DecisionMode
    defer_trace = _make_trace(with_action=False)
    defer_trace.decision_mode = DecisionMode.DEFER   # Enum survives serialization
    defer_trace.blocked_by_gate = "model_fidelity"
    defer_trace.act_emitted_action = False
    dd = defer_trace.to_dict()
    assert dd["decision_mode"] == "DEFER"
    assert dd["blocked_by_gate"] == "model_fidelity"
    assert dd["act_emitted_action"] is False
    assert dd["action_taken"] is None


def test_transparency_monitor_log_carries_decision_telemetry(tmp_path):
    """The persisted decision log (the artifact Aviku reads) must carry the
    WHY for non-acting cycles."""
    cfg = MonitorConfig(output_dir=str(tmp_path))
    mon = TransparencyMonitor(cfg)
    defer = _make_trace(with_action=False)
    defer.decision_mode = "DEFER"
    defer.blocked_by_gate = "risk_coverage,model_fidelity"
    defer.act_emitted_action = False
    mon.record(defer)
    data = json.loads(open(str(tmp_path / "decision_log.json")).read())
    t = data["traces"][0]
    assert t["decision_mode"] == "DEFER"
    assert t["blocked_by_gate"] == "risk_coverage,model_fidelity"
    assert t["act_emitted_action"] is False
    # Canonical aliases untouched (locked contract).
    assert t["intent"] == "goal_seek"
    assert t["discrimination_index"] == 0.97
    assert t["action_taken"] is None


def test_producer_broadcast_allowlist_includes_decision_telemetry():
    """The lean WebSocket frame + producer decision log must carry the
    telemetry fields (they are the first thing an observer sees)."""
    from telos.dashboard.producer import DashboardProducer
    fields = set(DashboardProducer.BROADCAST_TRACE_FIELDS)
    assert {"decision_mode", "blocked_by_gate", "act_emitted_action"} <= fields


def test_story_decision_names_defer_and_gate():
    """/api/overview recent_decisions must show "DEFER — model_fidelity",
    not a silent APP passthrough (the audit's exact complaint)."""
    from telos.dashboard.producer import DashboardProducer
    p = DashboardProducer.__new__(DashboardProducer)  # no init (statics only)
    trace = {
        "cycle_id": 5, "firewall_blocked": False, "council_validated": True,
        "decision_mode": "DEFER", "blocked_by_gate": "model_fidelity",
        "act_emitted_action": False,
    }
    sd = p._story_decision(trace)
    assert sd["status"] == "DEFER"
    assert sd["blocked_by_gate"] == "model_fidelity"
    assert sd["decision_mode"] == "DEFER"
    assert sd["act_emitted_action"] is False
    # Approved-noop (mode ACT, no action) stays APPROVED but is distinguishable.
    trace2 = {
        "cycle_id": 6, "firewall_blocked": False, "council_validated": True,
        "decision_mode": "ACT", "act_emitted_action": False,
    }
    sd2 = p._story_decision(trace2)
    assert sd2["status"] == "APPROVED"
    assert sd2["act_emitted_action"] is False
    # Legacy traces (pre-telemetry) keep pre-telemetry status behavior.
    trace3 = {"cycle_id": 7, "firewall_blocked": False, "council_validated": True}
    assert p._story_decision(trace3)["status"] == "APPROVED"
    trace4 = {"cycle_id": 8, "firewall_blocked": True}
    assert p._story_decision(trace4)["status"] == "BLOCKED"
