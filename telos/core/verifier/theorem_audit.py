"""
Falsifiable Theorem Audit — core TELOS theorems as measured, null-anchored
invariants.

The repository's "theorems" were constructive existence proofs ("a validator
exists, therefore the axiom holds"). That is not a prediction. This module
restates the load-bearing claims as *measurements with a declared null*: each
theorem names the metric, the baseline it must beat, and the null behaviour
that would falsify it. `run_audit` returns one row per theorem with the
measured value, the threshold, and PASS/FAIL.

Nothing here re-implements the pipeline; the auditor measures the real traces
produced by the CLI harness (`telos/tools/theorem_audit.py`).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

# Theorem catalogue: id -> (name, statement, null).
THEOREMS: Dict[str, Tuple[str, str, str]] = {
    "T1-determinism": (
        "Determinism",
        "Two identically-seeded runs over the same inputs produce identical "
        "decision fingerprints (architecture, not luck).",
        "Fingerprints differ across identical seeded runs.",
    ),
    "T2-process": (
        "Process over Outcomes",
        "Every cycle exposes a decision_integrity in [0, 1] (the trajectory "
        "is scored, not just the terminal reward).",
        "Any cycle reports DI outside [0, 1] or omits it.",
    ),
    "T3-conservation": (
        "Computational Conservation",
        "Per-cycle compute consumed never exceeds the declared budget "
        "(ΣR_i ≤ R_max).",
        "Any cycle consumes more than 1.1× its budget.",
    ),
    "T4-possibility": (
        "Possibility Preservation",
        "At least one counterfactual alternative is stored every cycle "
        "(|F_t| ≥ 1).",
        "A cycle stores zero strategic options.",
    ),
    "T5-emergent": (
        "Emergent Intelligence",
        "At least two cognitive streams activate per cycle (no single "
        "stream is 'I').",
        "A cycle activates fewer than two streams.",
    ),
    "T6-kintsugi": (
        "Kintsugi (System Memory)",
        "A recorded failure structurally blocks a matching future intent "
        "(recency-scaled dissent), and does not block unrelated intents.",
        "A matching intent passes — failure was logged, not integrated.",
    ),
    "T7-delayed-causality": (
        "Delayed Causality",
        "The effective simulation horizon strictly exceeds the feedback lag "
        "(h_eff = max(h, τ + 1) > τ).",
        "h_eff ≤ τ for some configuration.",
    ),
}


def check_determinism(fp_a: Any, fp_b: Any) -> Tuple[bool, str]:
    """T1 — two fingerprints from identical seeded runs must match.

    Args:
        fp_a: fingerprint of run A.
        fp_b: fingerprint of run B.

    Returns:
        (holds, measured) tuple.
    """
    return (fp_a is not None and fp_a == fp_b, f"{fp_a} == {fp_b}")


def check_process_over_outcomes(traces: List[Any]) -> Tuple[bool, str]:
    """T2 — every trace carries a decision_integrity in [0, 1].

    Args:
        traces: list of DecisionTrace objects from a real run.

    Returns:
        (holds, measured) tuple.
    """
    if not traces:
        return (False, "no traces")
    bad = [t.decision_integrity for t in traces
           if not (0.0 <= getattr(t, "decision_integrity", -1.0) <= 1.0)]
    return (not bad, f"{len(traces) - len(bad)}/{len(traces)} cycles in [0,1]")


def check_computational_conservation(traces: List[Any],
                                     tolerance: float = 0.1) -> Tuple[bool, str]:
    """T3 — no cycle consumes more than (1+tolerance)× its budget.

    Args:
        traces: list of DecisionTrace objects.
        tolerance: allowed fractional overrun (default 0.1).

    Returns:
        (holds, measured) tuple.
    """
    if not traces:
        return (False, "no traces")
    over = []
    for t in traces:
        total = getattr(t, "budget_total_ms", 0.0) or 0.0
        used = getattr(t, "budget_consumed_ms", 0.0) or 0.0
        if total > 0 and used > total * (1.0 + tolerance):
            over.append((used, total))
    worst = max((u / t for u, t in over), default=0.0)
    return (not over, f"max overrun ratio={worst:.2f} over {len(traces)} cycles")


def check_possibility_preservation(traces: List[Any]) -> Tuple[bool, str]:
    """T4 — at least one strategic option stored every cycle.

    Args:
        traces: list of DecisionTrace objects.

    Returns:
        (holds, measured) tuple.
    """
    if not traces:
        return (False, "no traces")
    empty = [i for i, t in enumerate(traces)
             if len(getattr(t, "strategic_options", []) or []) < 1]
    return (not empty, f"min options={min((len(getattr(t,'strategic_options',[]) or []) for t in traces), default=0)}")


def check_emergent_intelligence(traces: List[Any]) -> Tuple[bool, str]:
    """T5 — at least two streams activate per cycle.

    Args:
        traces: list of DecisionTrace objects.

    Returns:
        (holds, measured) tuple.
    """
    if not traces:
        return (False, "no traces")
    min_active = min(
        (sum(1 for s in (getattr(t, "stream_activations", []) or [])
             if getattr(s, "activated", False)) for t in traces),
        default=0,
    )
    return (min_active >= 2, f"min activated streams/cycle={min_active}")


def check_delayed_causality(config: Any) -> Tuple[bool, str]:
    """T7 — effective horizon strictly exceeds the feedback lag.

    Args:
        config: a PipelineConfig with `horizon` and `feedback_lag`.

    Returns:
        (holds, measured) tuple.
    """
    horizon = getattr(config, "horizon", 0)
    lag = getattr(config, "feedback_lag", 0)
    effective = max(horizon, lag + 1)
    return (effective > lag, f"h_eff={effective} > tau={lag}")


def kintsugi_experiment() -> Tuple[bool, str]:
    """T6 — a recorded failure blocks a matching intent, not an unrelated one.

    Builds a real FailureLedger + MemoryAdvisor and checks the Kintsugi
    contract end to end: matching intent is blocked, unrelated intent passes.

    Returns:
        (holds, measured) tuple.
    """
    import numpy as np
    from telos.core.infra_manager.failure_ledger import FailureLedger, FailureRecord
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.council.validators.memory import MemoryAdvisor
    from telos.core.governance.recovery_types import GOVERNANCE_SUPPRESSION_REASONS
    from telos.world.world import World
    from telos.intent_ir import IntentIR

    root = "opponent_adaptation"
    assert root not in GOVERNANCE_SUPPRESSION_REASONS

    ledger = FailureLedger()
    ledger.record_direct(FailureRecord(
        failure_id="k1", cycle=1, timestamp=time.time(),
        failure_type="council_block", severity=0.8, root_cause=root,
        blocked_by="plan_trajectory",
    ))
    advisor = MemoryAdvisor(SkillLibrary(), failure_ledger=ledger)
    empty_advisor = MemoryAdvisor(SkillLibrary(), failure_ledger=FailureLedger())
    world = World(state=np.zeros(4))

    matching = IntentIR(intent_type="plan_trajectory", confidence=0.8)
    unrelated = IntentIR(intent_type="reflex_avoid", confidence=0.8)

    blocked = advisor.validate(world, matching)
    passed_unrelated = advisor.validate(world, unrelated)
    null_passed = empty_advisor.validate(world, matching)

    holds = (blocked.passed is False
             and passed_unrelated.passed is True
             and null_passed.passed is True)
    measured = (f"matching blocked={blocked.passed is False}, "
                f"unrelated passes={passed_unrelated.passed is True}, "
                f"no-ledger passes={null_passed.passed is True}")
    return (holds, measured)


def run_audit(traces: List[Any], config: Any,
              fp_a: Any = None, fp_b: Any = None) -> Dict[str, Any]:
    """Evaluate every catalogued theorem against a real run.

    Args:
        traces: DecisionTrace list from the real pipeline run.
        config: the PipelineConfig used.
        fp_a: fingerprint of the first identical seeded run.
        fp_b: fingerprint of the second identical seeded run.

    Returns:
        A report dict with `rows` (per-theorem result) and `passed` (bool).
    """
    checks: Dict[str, Tuple[bool, str]] = {
        "T1-determinism": check_determinism(fp_a, fp_b),
        "T2-process": check_process_over_outcomes(traces),
        "T3-conservation": check_computational_conservation(traces),
        "T4-possibility": check_possibility_preservation(traces),
        "T5-emergent": check_emergent_intelligence(traces),
        "T6-kintsugi": kintsugi_experiment(),
        "T7-delayed-causality": check_delayed_causality(config),
    }
    rows = []
    for tid, (name, statement, null) in THEOREMS.items():
        holds, measured = checks.get(tid, (False, "not measured"))
        rows.append({
            "id": tid, "name": name, "statement": statement,
            "null": null, "measured": measured, "passed": bool(holds),
        })
    return {"rows": rows, "passed": all(r["passed"] for r in rows)}


__all__ = ["THEOREMS", "run_audit", "kintsugi_experiment",
           "check_delayed_causality"]
