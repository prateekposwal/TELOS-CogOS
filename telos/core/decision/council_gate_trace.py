"""
Council/firewall instrumentation — WHY the council/firewall suppressed a cycle.

The ACT-gate audit narrowed the remaining suppression to firewall governance
(`low_integrity`, `action_loop`). `low_integrity` fires when the council's DI is
below the applied threshold — and because a single validator BLOCK caps DI at
the DissentFloor (0.3), the real question is *which validator dissented and
why*. This module captures that, non-behaviorally, from ctx:

  - council verdict: DI, evidence-integrity, dissenters (name/reason/…);
  - firewall verdict: blocked_by, reason, and the check signals (which carry the
    applied DI threshold + domain for `low_integrity`).

`build_council_gate_record` only reads `ctx`.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _signal_dict(signal: Any) -> Dict[str, Any]:
    """Normalize a council ValidationSignal to a plain dict.

    Args:
        signal: a ValidationSignal.

    Returns:
        A JSON-ready dict.
    """
    return {
        "validator": getattr(signal, "validator_name", None),
        "passed": bool(getattr(signal, "passed", True)),
        "confidence": float(getattr(signal, "confidence", 0.0) or 0.0),
        "evidence_weight": float(getattr(signal, "evidence_weight", 0.0) or 0.0),
        "reason": getattr(signal, "reason", None),
        "verdict": getattr(signal, "verdict", None),
    }


def build_council_gate_record(ctx: Any) -> Dict[str, Any]:
    """Build the non-behavioral council/firewall record for the current cycle.

    Args:
        ctx: the PhaseContext after the council + firewall phases.

    Returns:
        A JSON-ready dict describing the council verdict, its dissenters, and
        the firewall's block decision + check signals.
    """
    verdict = getattr(ctx, "verdict", None)
    fw = getattr(ctx, "firewall_verdict", None)

    signals: List[Dict[str, Any]] = []
    if verdict is not None:
        for s in (getattr(verdict, "signals", None) or []):
            signals.append(_signal_dict(s))
    dissenters = [s for s in signals if not s["passed"]]

    fw_signals = []
    if fw is not None:
        for s in (getattr(fw, "governance_signals", None) or []):
            if isinstance(s, dict):
                fw_signals.append(s)

    applied_threshold = None
    domain = None
    for s in fw_signals:
        if s.get("applied_threshold") is not None:
            applied_threshold = s.get("applied_threshold")
            domain = s.get("domain")
            break

    return {
        "cycle": int(getattr(ctx, "cycle_count", 0) or 0),
        "council_validated": (bool(getattr(verdict, "validated", True))
                              if verdict is not None else None),
        "decision_integrity": (float(getattr(verdict, "decision_integrity", 1.0))
                               if verdict is not None else None),
        "evidence_integrity": (float(getattr(verdict, "evidence_integrity", 1.0))
                               if verdict is not None else None),
        "blocking_validator": (getattr(verdict, "blocking_validator", None)
                               if verdict is not None else None),
        "dissent_count": len(dissenters),
        "dissenters": dissenters,
        "firewall_passed": (bool(getattr(fw, "passed", True))
                            if fw is not None else None),
        "firewall_blocked_by": (getattr(fw, "blocked_by", None)
                                if fw is not None else None),
        "firewall_reason": (getattr(fw, "reason", None)
                            if fw is not None else None),
        "firewall_signals": fw_signals,
        "applied_di_threshold": applied_threshold,
        "di_domain": domain,
    }


__all__ = ["build_council_gate_record"]
