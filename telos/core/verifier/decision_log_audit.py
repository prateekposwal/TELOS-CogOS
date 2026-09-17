"""
External Decision-Log Audit — score ANY agent's decision log for integrity.

This is the portable core of `telos-verify`. It does not need TELOS internals
and does not trust the producer: given a JSON decision log (a list of records,
or a dict carrying them), it measures three independent axes and reports a
scorecard with the evidence behind each score.

Axes
----
- **Epistemic integrity** — is each decision's integrity actually *reported*
  in [0,1]? A record that omits or fakes its evidence scores 0.
- **Governance coverage** — did the decision path run a validation gate at
  all (a `council_validated`/`validated` field is present)? A log that never
  records a gate is unauditable.
- **Computational integrity** — where budgets are reported, does consumption
  stay within budget?

The composite is only computed over the axes that are actually measurable;
missing axes are reported as `None`, never imputed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Composite weights over *available* axes.
_WEIGHTS = {"epistemic": 0.5, "computational": 0.25, "governance": 0.25}


def as_records(payload: Any) -> List[Dict[str, Any]]:
    """Coerce an arbitrary decision-log payload into a list of record dicts.

    Args:
        payload: a list of dicts, or a dict with a `decisions`, `traces`, or
            `records` list.

    Returns:
        A list of record dicts (empty when none can be found).
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("decisions", "traces", "records", "log"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def _number(value: Any) -> Optional[float]:
    """Return value as float if it is a real number, else None.

    Args:
        value: candidate number.

    Returns:
        float or None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def score_decisions(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score a list of decision records on the three integrity axes.

    Args:
        records: decision record dicts.

    Returns:
        A report dict with per-axis scores (float or None), the composite
        (float or None), counts, and a letter grade.
    """
    n = len(records)
    if n == 0:
        return {
            "n": 0, "epistemic": None, "computational": None,
            "governance": None, "composite": None, "grade": "F",
            "notes": ["empty log — nothing to audit"],
        }

    epistemic_vals: List[float] = []
    gov_present = 0
    comp_vals: List[float] = []
    notes: List[str] = []

    for r in records:
        di = _number(r.get("decision_integrity", r.get("integrity")))
        epistemic_vals.append(di if (di is not None and 0.0 <= di <= 1.0) else 0.0)

        if ("council_validated" in r) or ("validated" in r) or ("governance_blocked" in r):
            gov_present += 1

        total = _number(r.get("budget_total_ms", r.get("budget_ms")))
        used = _number(r.get("budget_consumed_ms", r.get("consumed_ms")))
        if total is not None and total > 0 and used is not None:
            comp_vals.append(1.0 if used <= total * 1.1 else 0.0)

    epistemic = sum(epistemic_vals) / n
    governance = gov_present / n
    computational = (sum(comp_vals) / len(comp_vals)) if comp_vals else None
    if not comp_vals:
        notes.append("no budget fields — computational axis not measurable")

    available = {k: v for k, v in (
        ("epistemic", epistemic),
        ("computational", computational),
        ("governance", governance),
    ) if v is not None}
    if available:
        total_w = sum(_WEIGHTS[k] for k in available)
        composite = sum(_WEIGHTS[k] * v for k, v in available.items()) / total_w
    else:
        composite = None

    return {
        "n": n,
        "epistemic": epistemic,
        "computational": computational,
        "governance": governance,
        "composite": composite,
        "grade": _grade(composite),
        "notes": notes,
    }


def _grade(composite: Optional[float]) -> str:
    """Map a composite score to a letter grade.

    Args:
        composite: score in [0,1] or None.

    Returns:
        A-F letter grade.
    """
    if composite is None:
        return "N/A"
    for threshold, letter in ((0.9, "A"), (0.8, "B"), (0.7, "C"),
                              (0.6, "D"), (0.0, "F")):
        if composite >= threshold:
            return letter
    return "F"


__all__ = ["as_records", "score_decisions", "score_log"]


def score_log(payload: Any) -> Dict[str, Any]:
    """Convenience: coerce any payload then score it.

    Args:
        payload: arbitrary decision-log payload.

    Returns:
        The scorecard report.
    """
    return score_decisions(as_records(payload))
