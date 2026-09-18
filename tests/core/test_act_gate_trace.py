"""
ACT-gate instrumentation — non-behavioral record of WHY a cycle did not act.

Covers the governor mode/reason, failed capability gates, and action-emission
flag; plus the benchmark loop's episode-reset protocol (the subtle signal whose
absence corrupts model fidelity).
"""
from types import SimpleNamespace

from telos.core.decision.act_gate_trace import build_act_gate_record
from telos.core.governance.capability_authorization import (
    CapabilityAuthorization, CapabilityStatus,
)


def _ctx(cap, mode="DEFER", selected_action=None, blocked_by_gate="model_fidelity"):
    return SimpleNamespace(
        cycle_count=3,
        decision_mode=SimpleNamespace(value=mode),
        governor_decision=SimpleNamespace(reason="Capability insufficient", hard_stop=True),
        capability_authorization=cap,
        firewall_verdict=SimpleNamespace(blocked_by=None),
        verdict=SimpleNamespace(decision_integrity=0.3, mission_drift=0.1),
        selected_action=selected_action,
        blocked_by_gate=blocked_by_gate,
        no_action=True, firewall_blocked=False, governance_blocked=False,
    )


def test_record_captures_failed_gate_and_no_action():
    cap = CapabilityAuthorization(
        model_fidelity=CapabilityStatus.FAIL,
        details={"model_fidelity": "value=0.3, tested=True"})
    rec = build_act_gate_record(_ctx(cap))
    assert rec["decision_mode"] == "DEFER"
    assert "model_fidelity" in rec["failed_gates"]
    assert rec["action_emitted"] is False
    assert rec["capability_details"]["model_fidelity"].startswith("value=0.3")
    assert rec["capability_profile"]["model_fidelity"] == "FAIL"


def test_record_captures_emitted_action():
    cap = CapabilityAuthorization()
    rec = build_act_gate_record(
        _ctx(cap, mode="ACT", selected_action="move", blocked_by_gate=None))
    assert rec["action_emitted"] is True
    assert rec["failed_gates"] == []
    assert rec["governor_hard_stop"] is True


def test_record_tolerates_missing_ctx_fields():
    rec = build_act_gate_record(SimpleNamespace(cycle_count=1))
    assert rec["cycle"] == 1
    assert rec["failed_gates"] == []
    assert rec["action_emitted"] is False


# ── Bench loop: episode reset protocol ───────────────────────────────────────

def test_bench_loop_signals_episode_reset_after_terminal():
    from telos.tools.bench_loop import drive

    class _Sim:
        def transition(self, s, a):
            return s

        def terminal(self, s):
            return True  # terminal every cycle → reset must be signalled

    calls = []

    class _Pipe:
        config = SimpleNamespace(simulator=_Sim())

        def execute(self, state, user_name=None, episode_reset=False):
            calls.append(episode_reset)
            return SimpleNamespace(firewall_blocked=False,
                                   decision_trace=SimpleNamespace(selected_action=None))

    list(drive(_Pipe(), 3))
    assert calls == [False, True, True], calls
