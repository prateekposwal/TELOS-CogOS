"""
Mission-policy instrumentation — the firewall DI threshold and its up-driver.

`MissionPolicy.firewall_di_threshold = 1 − risk_tolerance`, so the firewall's
strictness is driven entirely by `risk_tolerance`. This module records, per
cycle and non-behaviorally, the policy posture and the most recent policy
mutations (the PolicyChangeLog already records who/why — when callers fill it
in). It is the instrument for "who raised the threshold, on what evidence".

`build_policy_trace` only reads the pipeline's infra policy.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _recent_changes(policy: Any, n: int = 3) -> List[Dict[str, Any]]:
    """Read the newest policy change-log entries.

    Args:
        policy: a MissionPolicyManager (may expose `_change_log`).
        n: how many recent entries to return.

    Returns:
        A list of {component, old, new, reason, caller, cycle} dicts.
    """
    log = getattr(policy, "_change_log", None)
    changes = getattr(log, "_changes", None)
    if not changes:
        return []
    out = []
    for c in changes[-n:]:
        out.append({
            "component": getattr(c, "component", None),
            "old": getattr(c, "old_value", None),
            "new": getattr(c, "new_value", None),
            "reason": getattr(c, "reason", None),
            "caller": getattr(c, "caller", None),
            "cycle": getattr(c, "cycle", None),
        })
    return out


def build_policy_trace(pipeline: Any) -> Dict[str, Any]:
    """Build the non-behavioral mission-policy record for the current cycle.

    Args:
        pipeline: the pipeline (reads `_infra_manager.policy`).

    Returns:
        A JSON-ready dict with the policy posture, the derived firewall DI
        threshold, and the newest policy mutations.
    """
    infra = getattr(pipeline, "_infra_manager", None)
    policy = getattr(infra, "policy", None)
    if policy is None:
        return {"available": False}
    cur = getattr(policy, "current", None)
    if cur is None:
        return {"available": False}
    try:
        threshold = float(policy.firewall_di_threshold)
    except Exception:
        threshold = None
    log = getattr(policy, "_change_log", None)
    return {
        "available": True,
        "risk_tolerance": float(getattr(cur, "risk_tolerance", 0.0)),
        "exploration_budget": float(getattr(cur, "exploration_budget", 0.0)),
        "ambition_level": float(getattr(cur, "ambition_level", 0.0)),
        "drift_tolerance": float(getattr(cur, "drift_tolerance", 0.0)),
        "recovery_mode": bool(getattr(cur, "recovery_mode", False)),
        "firewall_di_threshold": threshold,
        "policy_changes": len(getattr(log, "_changes", []) or []),
        "recent_changes": _recent_changes(policy, 3),
    }


__all__ = ["build_policy_trace"]
