"""
ACT-gate instrumentation — WHY a cycle did not execute an action.

The selection experiment showed the throughput loss is ACT suppression, not
selection scoring. This module captures, per cycle and NON-BEHAVIORALLY, the
full act-gate picture: the governor's decision mode/reason, the failed
capability gates, the capability profile + details (including the numeric model
fidelity), the firewall/governance block, and whether an action was emitted.

`build_act_gate_record` only reads `ctx`; enabling it changes no decision.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _mode(decision_mode: Any) -> Optional[str]:
    """Normalize a DecisionMode (enum or str) to a plain string.

    Args:
        decision_mode: the ctx.decision_mode value.

    Returns:
        The string value, or None.
    """
    if decision_mode is None:
        return None
    return getattr(decision_mode, "value", decision_mode)


def build_act_gate_record(ctx: Any) -> Dict[str, Any]:
    """Build the non-behavioral ACT-gate record for the current cycle.

    Args:
        ctx: the PhaseContext after the act phase.

    Returns:
        A JSON-ready dict describing every gate that shaped action emission.
    """
    cap = getattr(ctx, "capability_authorization", None)
    gov = getattr(ctx, "governor_decision", None)
    fw = getattr(ctx, "firewall_verdict", None)
    verdict = getattr(ctx, "verdict", None)

    cap_dict = cap.to_dict() if cap is not None and hasattr(cap, "to_dict") else {}
    failed: List[str] = list(cap_dict.get("failed_gates", []) or [])
    if not failed and cap is not None and hasattr(cap, "failed_gates"):
        try:
            failed = list(cap.failed_gates())
        except Exception:
            failed = []

    selected_action = getattr(ctx, "selected_action", None)
    hard_stop = getattr(gov, "hard_stop", None) if gov is not None else None

    return {
        "cycle": int(getattr(ctx, "cycle_count", 0) or 0),
        "decision_mode": _mode(getattr(ctx, "decision_mode", None)),
        "governor_reason": getattr(gov, "reason", None) if gov is not None else None,
        "governor_hard_stop": bool(hard_stop) if hard_stop is not None else None,
        "blocked_by_gate": getattr(ctx, "blocked_by_gate", None),
        "failed_gates": failed,
        "capability_authorized": cap_dict.get("authorized"),
        "capability_profile": cap_dict.get("profile", {}),
        "capability_details": cap_dict.get("details", {}),
        "no_action": getattr(ctx, "no_action", None),
        "firewall_blocked": bool(getattr(ctx, "firewall_blocked", False)),
        "firewall_blocked_by": getattr(fw, "blocked_by", None) if fw is not None else None,
        "governance_blocked": bool(getattr(ctx, "governance_blocked", False)),
        "decision_integrity": (getattr(verdict, "decision_integrity", None)
                               if verdict is not None else None),
        "mission_drift": (getattr(verdict, "mission_drift", None)
                          if verdict is not None else None),
        "action_emitted": selected_action is not None,
    }


__all__ = ["build_act_gate_record"]
