"""
Firewall block trace (v8 Phase 1) — explain EVERY block, weaken nothing.

Runs the canonical GridWorld pipeline (same build as
`telos/tools/causal_baseline.py`) and, for every firewall-blocked cycle,
records the full chain the block travelled:

    intent → council predicate → evidence → authority → identity →
    mission/project compatibility → risk → firewall decision

and classifies the block into exactly one category, honestly counting
ambiguous cases as UNKNOWN. The tool NEVER changes the firewall: it only
observes. Its purpose is to establish whether the remaining suppression is
causally explainable and correctly justified before any threshold is touched.

Classification rules (each block gets one label):
  LEGITIMATE SAFETY BLOCK   the firewall check itself is a designed boundary
                            (action_loop repeat trap, mission_violation,
                            council_rejection from a hard-veto validator,
                            low_identity_integrity below the elevated bar).
  INSUFFICIENT EVIDENCE     the deciding dissent is grounded in a real but
                            thin/untested record (ambiguous — only when the
                            record is clearly a single unvalidated sample).
  BAD INTENT                no intent was selected (no_intent).
  BAD SCORING               the DI arithmetic is wrong for its inputs.
  BAD GOVERNANCE            the deciding dissent is grounded in a misattributed
                            record — an outcome that never tested the approach
                            (governance suppression or advisory escalation)
                            was treated as evidence of approach failure.
  STALE STATE               the deciding dissent cites a record that is no
                            longer current (stale gap / stale counter).
  WIRING BUG                two components disagree about a shared contract.
  OVERLY CONSERVATIVE RULE  the rule is a deliberate but dominated constraint
                            (no real falsification supports it).
  UNKNOWN                   cannot be determined from the trace.

Usage:
    PYTHONPATH=. python3 telos/tools/firewall_block_trace.py --cycles 120
    PYTHONPATH=. python3 telos/tools/firewall_block_trace.py --cycles 120 \
        --json telos/audit/firewall_block_trace.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

# Failure reasons that mean the outcome NEVER tested the approach — such a
# record is not evidence of approach failure (canonical rule, Λ6.5).
_NOT_EVIDENCE_REASONS = frozenset({
    "governance_intervention", "simulation_divergence", "unresolved_uncertainty"})

# Verification path for the block chain: the concrete code at each arrow.
CHAIN = {
    "1_intent": "telos/core/runtime.py:986 _arm_goal_seek_recovery -> "
                "telos/core/runtime.py:1158 _inject_recovery_intent "
                "(intent=goal_seek_recovery)",
    "2_predicate": "telos/core/council/validators/memory.py:184-196 "
                   "MemoryAdvisor KG path: fnode.approach == intent.intent_type "
                   "and failure_reason not filtered",
    "3_evidence": "telos/core/knowledge/recorder.py:58-62 record_failure(outcome=0.15) <- "
                  "telos/core/infra_manager/knowledge_manager.py:211 recorder.failure(...) <- "
                  "telos/core/infra_manager/infrastructure_manager.py:233-251 "
                  "escalation FailureRecord(root_cause=unresolved_uncertainty)",
    "4_authority": "telos/core/council/base.py:286-309 _compute_decision_integrity "
                   "DissentFloor=0.3 caps the REPORTED DI when any BLOCK exists",
    "5_identity": "telos/core/phases/act.py:337 derive_epistemic_state "
                  "(not the dissenter on this path)",
    "6_mission": "telos/core/council/validators/mission.py MissionDriftDetector "
                 "(not the dissenter on this path)",
    "7_risk": "telos/core/infra_manager/mission_policy.py:385-391 "
              "firewall_di_threshold = 1 - risk_tolerance",
    "8_firewall": "telos/core/phases/act.py:406-411 DecisionFirewall.inspect -> "
                  "telos/core/governance/firewall.py:145-160 Check 2 low_integrity",
}

_KG_RE = re.compile(
    r"KnowledgeGraph: approach '(?P<approach>[^']+)' failed previously in "
    r"domain '(?P<domain>[^']+)' \(outcome=(?P<outcome>[\d.]+)\)\s*—\s*"
    r"(?P<reason>.*)")

_HARD_VETO = ("risk", "authority", "safety", "constraint", "reality")


def _classify(blocked_by: Optional[str], dissenters: List[Dict[str, Any]],
              decision_integrity: float) -> Dict[str, Any]:
    """Classify one firewall block into exactly one category.

    Args:
        blocked_by: the firewall verdict's blocked_by code.
        dissenters: the council signals that failed this cycle.
        decision_integrity: the council's reported (floored) DI.

    Returns:
        {"category": str, "deciding_validator": str|None,
         "evidence_reason": str|None} — the label + what decided it.
    """
    if blocked_by == "action_loop":
        return {"category": "LEGITIMATE SAFETY BLOCK", "deciding_validator": None,
                "evidence_reason": "same-action repeat trap; designed escape exists (Λ3.1)"}
    if blocked_by == "mission_violation":
        return {"category": "LEGITIMATE SAFETY BLOCK", "deciding_validator": None,
                "evidence_reason": "mission parameters violated"}
    if blocked_by == "no_intent":
        return {"category": "BAD INTENT", "deciding_validator": None,
                "evidence_reason": "no intent selected"}
    if blocked_by == "low_identity_integrity":
        return {"category": "LEGITIMATE SAFETY BLOCK", "deciding_validator": None,
                "evidence_reason": "identity mood gate below elevated DI bar"}
    if blocked_by == "council_rejection":
        names = [d.get("validator") for d in dissenters]
        if any(any(h in (n or "").lower() for h in _HARD_VETO) for n in names):
            return {"category": "LEGITIMATE SAFETY BLOCK",
                    "deciding_validator": names[0] if names else None,
                    "evidence_reason": "hard-veto validator rejected"}
        return {"category": "UNKNOWN",
                "deciding_validator": names[0] if names else None,
                "evidence_reason": "council rejected without a hard veto"}
    if blocked_by != "low_integrity":
        return {"category": "UNKNOWN", "deciding_validator": None,
                "evidence_reason": f"unclassified firewall code {blocked_by!r}"}

    if not dissenters:
        return {"category": "BAD SCORING", "deciding_validator": None,
                "evidence_reason": "low_integrity with no dissenting validator"}

    # The DissentFloor caps DI to 0.3 on any BLOCK; the deciding dissent is the
    # one whose record the council aggregated. Prefer a MemoryAdvisor signal
    # (it carries the concrete approach-failure evidence).
    deciding = next((d for d in dissenters if d.get("validator") == "MemoryAdvisor"),
                    dissenters[0])
    validator = deciding.get("validator")
    reason = str(deciding.get("reason") or "")

    if validator == "MemoryAdvisor":
        m = _KG_RE.search(reason)
        if m:
            failure_reason = m.group("reason").strip()
            base = failure_reason.split(" | ")[0].strip()
            if base in _NOT_EVIDENCE_REASONS:
                return {"category": "BAD GOVERNANCE", "deciding_validator": validator,
                        "evidence_reason": (
                            f"KG failure node for '{m.group('approach')}' was built from "
                            f"a non-testing outcome ('{base}') — escalation/suppression "
                            f"treated as approach failure")}
            return {"category": "UNKNOWN", "deciding_validator": validator,
                    "evidence_reason": (
                        f"KG failure node for '{m.group('approach')}' cites "
                        f"'{base}' (outcome={m.group('outcome')}); may be a genuine "
                        f"measured failure — ambiguous")}
        if "Kintsugi" in reason:
            return {"category": "UNKNOWN", "deciding_validator": validator,
                    "evidence_reason": "FailureLedger structural barrier — genuine root "
                                       "cause not classified as suppression"}
        if "historical skill" in reason:
            return {"category": "UNKNOWN", "deciding_validator": validator,
                    "evidence_reason": "skill-utility barrier — ambiguous"}
        return {"category": "UNKNOWN", "deciding_validator": validator,
                "evidence_reason": "MemoryAdvisor dissent with an unrecognized record"}
    if validator == "EvidenceProvenanceValidator":
        if "falsified loop" in reason or "no-action" in reason or "no action" in reason:
            # The type's no-action counter. If those cycles were governance
            # suppressed, the counter is a misattribution; the trace cannot
            # prove it per-cycle here -> honest UNKNOWN.
            return {"category": "UNKNOWN", "deciding_validator": validator,
                    "evidence_reason": ("no-action falsification count; cannot prove "
                                        "from this trace whether the counted cycles "
                                        "were governance-suppressed")}
        return {"category": "UNKNOWN", "deciding_validator": validator,
                "evidence_reason": "evidence-provenance dissent (unclassified)"}
    if validator and any(h in validator.lower() for h in _HARD_VETO):
        return {"category": "LEGITIMATE SAFETY BLOCK", "deciding_validator": validator,
                "evidence_reason": "hard-veto validator"}
    return {"category": "UNKNOWN", "deciding_validator": validator,
            "evidence_reason": f"dissent from {validator!r} (unclassified)"}


def run(cycles: int = 120, seed: int = 42) -> Dict[str, Any]:
    """Trace and classify every firewall block in a canonical run.

    Args:
        cycles: number of pipeline cycles.
        seed: deterministic seed.

    Returns:
        A JSON-ready report with per-block records + aggregate percentages.
    """
    from telos.tools.bench_loop import drive
    from telos.tools.causal_baseline import build

    import tempfile
    workdir = tempfile.mkdtemp(prefix="telos_fw_trace_")
    pipe, _sim, build_record = build(workdir, seed)

    # Provenance capture: record every approach-failure the KG receives so a
    # block can be traced back to the exact recorded outcome + its source type.
    provenance: List[Dict[str, Any]] = []
    orig_failure = pipe.infra_manager.knowledge_mgr.recorder.failure

    def traced_failure(domain, approach, reason, tags=None, params=None):
        provenance.append({"cycle": getattr(pipe, "_cycle_count", None),
                           "domain": domain, "approach": approach,
                           "reason": reason, "tags": list(tags or [])})
        return orig_failure(domain, approach, reason, tags=tags, params=params)

    pipe.infra_manager.knowledge_mgr.recorder.failure = traced_failure

    blocks: List[Dict[str, Any]] = []
    category_counts: Counter = Counter()
    acted = 0
    total_blocks = 0
    for step in drive(pipe, cycles, user_name="fw-trace"):
        trace = step["trace"]
        if trace is None:
            continue
        if trace.firewall_blocked:
            total_blocks += 1
            cg = trace.council_gate or {}
            dissenters = cg.get("dissenters") or []
            label = _classify(trace.firewall_blocked_by or "unknown", dissenters,
                              float(trace.decision_integrity))
            category_counts[label["category"]] += 1
            if len(blocks) < 40:
                blocks.append({
                    "cycle": int(trace.cycle_id),
                    "intent": (trace.selected_intent.intent_type
                               if trace.selected_intent else None),
                    "decision_mode": (getattr(trace.decision_mode, "value",
                                              trace.decision_mode)),
                    "council_validated": bool(cg.get("council_validated")),
                    "decision_integrity": round(float(cg.get("decision_integrity")
                                                      or trace.decision_integrity), 4),
                    "evidence_integrity": cg.get("evidence_integrity"),
                    "blocking_validator": cg.get("blocking_validator"),
                    "dissenters": [
                        {"validator": d.get("validator"),
                         "reason": d.get("reason")}
                        for d in dissenters],
                    "applied_di_threshold": cg.get("applied_di_threshold"),
                    "di_domain": cg.get("di_domain"),
                    "firewall_blocked_by": trace.firewall_blocked_by,
                    "classification": label["category"],
                    "deciding_validator": label["deciding_validator"],
                    "evidence_reason": label["evidence_reason"],
                })
        if trace.selected_action is not None and not step["result"].firewall_blocked:
            acted += 1

    # Escalation provenance: which approaches got poisoned, and from what.
    poisoned: Counter = Counter()
    for p in provenance:
        poisoned[f"cycle={p['cycle']} {p['approach']} <- {p['reason']}"] += 1

    pct = {k: round(100.0 * v / max(total_blocks, 1), 2)
           for k, v in category_counts.most_common()}
    return {
        "phase": "v8-phase1-firewall-block-trace",
        "cycles": cycles,
        "seed": seed,
        "build": build_record,
        "reproduction_command": (
            "PYTHONPATH=. python3 telos/tools/firewall_block_trace.py "
            f"--cycles {cycles} --seed {seed}"),
        "total_firewall_blocks": total_blocks,
        "acted_cycles": acted,
        "categories": dict(category_counts.most_common()),
        "category_percentages": pct,
        "block_records_sample": blocks,
        "approach_failure_provenance": dict(poisoned.most_common(20)),
        "chain_paths": CHAIN,
        "classification_rules": (
            "see module docstring; every block gets exactly one label; "
            "ambiguous evidence is UNKNOWN, never guessed"),
    }


def main(argv=None) -> int:
    """Run the Phase 1 firewall block trace and print/emit the report.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Process exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="v8 Phase 1 firewall block trace")
    parser.add_argument("--cycles", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", help="write the trace report to this path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = run(args.cycles, args.seed)
    if not args.quiet:
        print("\n            TELOS v8 Phase 1 — firewall block trace")
        print("=" * 74)
        print(f"  cycles={report['cycles']} seed={report['seed']} "
              f"fingerprint={report['build']['code_fingerprint']}")
        print(f"  total firewall blocks : {report['total_firewall_blocks']}")
        print(f"  acted cycles          : {report['acted_cycles']}")
        print("  classification        :")
        for cat, n in report["categories"].items():
            print(f"      {n:4d}  ({report['category_percentages'][cat]:5.1f}%)  {cat}")
        print("  approach-failure provenance:")
        for k, n in report["approach_failure_provenance"].items():
            print(f"      {n:4d}x  {k}")
        print("=" * 74)
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        if not args.quiet:
            print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
