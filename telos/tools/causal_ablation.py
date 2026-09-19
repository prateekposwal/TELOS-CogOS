"""Causal ablation matrix (v8 Phase 2) — one-variable-at-a-time on the Phase-1 baseline.

For each decision term, hold everything else constant (same seed, same config,
same driver) and neutralise ONLY that term, then compare the behavioural
fingerprint and outcome metrics against the untouched baseline. This is the
evidence that classifies a term as CAUSALLY ACTIVE / DOMINATED / DECORATIVE /
UNWIRED — no term is kept merely because it is computed.

The tool changes nothing in the kernel: every ablation is a scoped monkeypatch
restored after the run. It is additive and opt-in (a diagnostic, never imported
by the runtime).

Usage:
    PYTHONPATH=. python3 telos/tools/causal_ablation.py --cycles 120 --seed 42
    PYTHONPATH=. python3 telos/tools/causal_ablation.py --cycles 120 \
        --json telos/audit/causal_ablation.json
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import statistics
import sys
import tempfile
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

SEQ_HASH_KEYS = ("selected_action", "firewall_blocked", "terminal")


def _seq_digest(rows: List[Tuple]) -> str:
    """Hash a behavioural sequence (action, blocked, terminal) per cycle.

    Args:
        rows: per-cycle tuples in order.

    Returns:
        A 16-hex-char digest; identical code paths with identical behaviour
        produce identical digests, so a variant that changes nothing is
        provably behaviour-neutral at the action level.
    """
    h = hashlib.sha256()
    for action, blocked, terminal in rows:
        a = "none" if action is None else ",".join(f"{float(x):.4f}" for x in action)
        h.update(f"{a}|{bool(blocked)}|{bool(terminal)};".encode())
    return h.hexdigest()[:16]


def _stats(vals: List[float]) -> Dict[str, Any]:
    """Summarize a numeric series (empty -> {"n": 0}).

    Args:
        vals: the numeric values.

    Returns:
        Dict with n/min/mean/max.
    """
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": round(min(vals), 4),
            "mean": round(statistics.fmean(vals), 4),
            "max": round(max(vals), 4)}


def _run_once(cycles: int, seed: int, patches: List[Callable],
              config_overrides: Optional[Dict[str, Any]] = None):
    """Run the canonical baseline once under a set of scoped patches.

    Args:
        cycles: pipeline cycles to drive.
        seed: deterministic seed.
        patches: zero-arg callables returning context managers.
        config_overrides: optional PipelineConfig keyword overrides applied at
            build time (e.g. {"distributed_council_enabled": False}).

    Returns:
        Aggregated metrics dict for the variant.
    """
    from telos.tools.bench_loop import drive
    from telos.tools.causal_baseline import build

    workdir = tempfile.mkdtemp(prefix="telos_causal_ablation_")
    with contextlib.ExitStack() as stack:
        for cm in patches:
            stack.enter_context(cm)
        pipe, sim, build_record = build(workdir, seed,
                                        config_overrides=config_overrides)
        rows: List[Tuple] = []
        di_vals: List[float] = []
        md_vals: List[float] = []
        acted = episodes = 0
        fw_blocks: Counter = Counter()
        intents: Counter = Counter()
        actions: Counter = Counter()
        gates: Counter = Counter()
        modes: Counter = Counter()
        projected = rejected = 0
        j_mean: Dict[str, float] = {}
        j_n = 0
        commitment_sum = 0.0
        axiom_: Counter = Counter()
        escalations = 0
        last_state = None
        for step in drive(pipe, cycles, user_name="causal-ablation"):
            trace = step["trace"]
            if trace is None:
                continue
            di_vals.append(float(trace.decision_integrity))
            md_vals.append(float(trace.mission_drift))
            intent_type = (trace.selected_intent.intent_type
                           if trace.selected_intent else None)
            intents[intent_type] += 1
            action = trace.selected_action
            if action is not None:
                actions[tuple(round(float(x), 3) for x in action)] += 1
            rows.append((action, trace.firewall_blocked, step["terminal"]))
            if trace.firewall_blocked:
                fw_blocks[trace.firewall_blocked_by or "unknown"] += 1
            if getattr(trace, "blocked_by_gate", None):
                gates[trace.blocked_by_gate] += 1
            mode = getattr(trace, "decision_mode", None)
            modes[getattr(mode, "value", mode) or "none"] += 1
            if getattr(trace, "escalation_requested", False):
                escalations += 1
            ip = getattr(trace, "identity_projection", None) or {}
            if ip.get("projected_out"):
                projected += 1
            if ip.get("rejected_selected"):
                rejected += 1
            jb = getattr(trace, "j_term_breakdown", None)
            if isinstance(jb, dict) and jb:
                j_n += 1
                commitment_sum += float(jb.get("commitment", 0.0) or 0.0)
                for k, v in jb.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        j_mean[k] = j_mean.get(k, 0.0) + float(v)
            ax = getattr(trace, "axiom_results", None) or {}
            for aid in ("5.1", "5.3", "4.11"):
                row = ax.get(aid)
                if isinstance(row, dict):
                    axiom_[f"{aid}_{'pass' if row.get('passed') else 'fail'}"] += 1
            if action is not None and not trace.firewall_blocked:
                acted += 1
            if step["terminal"]:
                episodes += 1
            last_state = step["state_after"]
        for k in list(j_mean):
            j_mean[k] = round(j_mean[k] / j_n, 4) if j_n else 0.0
        return {
            "cycles": cycles,
            "seed": seed,
            "fingerprint": build_record["code_fingerprint"],
            "behavior_digest": _seq_digest(rows),
            "acted_cycles": acted,
            "firewall_blocks": dict(fw_blocks.most_common()),
            "firewall_block_count": sum(fw_blocks.values()),
            "episodes": episodes,
            "final_state": (last_state.tolist() if last_state is not None else None),
            "DI": _stats(di_vals),
            "MD": _stats(md_vals),
            "intents": dict(intents.most_common()),
            "action_kinds": len(actions),
            "top_actions": [
                {"action": list(a), "n": n} for a, n in actions.most_common(5)
            ],
            "blocked_by_gate": dict(gates.most_common()),
            "decision_modes": dict(modes.most_common()),
            "escalations": escalations,
            "identity_projection": {"projected_cycles": projected,
                                    "rejected_cycles": rejected},
            "j_cycles": j_n,
            "j_mean_commitment": round(commitment_sum / j_n, 4) if j_n else None,
            "j_term_means": j_mean,
            "axioms": dict(axiom_),
        }


# ── Ablation patch factories ────────────────────────────────────────────────

def _patch_j_constant(value: float) -> Callable:
    """Force CommitmentScore.commitment to a constant (whole-UCF ablation).

    Args:
        value: the constant commitment in [0, 1].

    Returns:
        A patch context-manager factory.
    """
    def factory():
        from unittest import mock
        from telos.core.decision.commitment_optimizer import CommitmentScore
        return mock.patch.object(CommitmentScore, "commitment",
                                 property(lambda self: float(value)))
    return factory


def _patch_identity_off() -> Callable:
    """Make the F(I) projection gate admit every trajectory."""
    def factory():
        from unittest import mock
        from telos.core.identity.projection_gate import IdentityProjectionGate
        return mock.patch.object(IdentityProjectionGate, "is_admissible",
                                 lambda self, *a, **k: True)
    return factory


def _patch_validator_pass(name: str) -> Callable:
    """Neutralise a council validator (always returns a passing signal).

    Args:
        name: validator class name in telos.core.council.validators.

    Returns:
        A patch context-manager factory.
    """
    def factory():
        from unittest import mock
        from telos.core.council import validators as V
        from telos.core.council.base import ValidationSignal
        cls = getattr(V, name)

        def _passthrough(self, *a, **k):
            return ValidationSignal(validator_name=self.name, passed=True,
                                    confidence=0.7, reason="ablated",
                                    evidence_weight=0.0)

        return mock.patch.object(cls, "validate", _passthrough)
    return factory


def _patch_gate_pass(gate: str) -> Callable:
    """Force one capability gate to PASS at construction time.

    The governor is evaluated after CapabilityAuthorization is built, so
    overriding one keyword argument here isolates that gate's contribution to
    the act decision.

    Args:
        gate: gate name (e.g. "risk_coverage", "model_fidelity").

    Returns:
        A patch context-manager factory.
    """
    def factory():
        from unittest import mock
        from telos.core.governance.capability_authorization import (
            CapabilityAuthorization, CapabilityStatus,
        )
        orig = CapabilityAuthorization.__init__

        def patched(self, *a, **k):
            k[gate] = CapabilityStatus.PASS
            return orig(self, *a, **k)

        return mock.patch.object(CapabilityAuthorization, "__init__", patched)
    return factory


# The five registered council advisors (canonical GridWorld crew).
ADVISORS: Tuple[str, ...] = (
    "RealityValidator", "ConstraintValidator", "MemoryAdvisor",
    "MissionDriftDetector", "EvidenceProvenanceValidator",
)


def _ablate(name: str) -> Callable:
    """Factory: neutralise exactly one advisor (all others untouched).

    Args:
        name: validator class name.

    Returns:
        A context-manager factory.
    """
    return _patch_validator_pass(name)


def _only(name: str) -> Callable:
    """Factory: leave ONLY `name` active, neutralise the other four advisors.

    This is the leave-one-out diagnostic — it isolates whether a single
    advisor alone carries the council's causal effect (the original
    connectivity audit's MemoryAdvisor finding).

    Args:
        name: the advisor to keep active.

    Returns:
        A context-manager factory producing all four ablation patches.
    """
    def factory():
        return [_patch_validator_pass(n)()
                for n in ADVISORS if n != name]
    return factory


VARIANTS: List[Tuple[str, Callable]] = [
    ("baseline", lambda: []),
    ("J_commitment_zero", lambda: [_patch_j_constant(0.0)()]),
    ("J_commitment_one", lambda: [_patch_j_constant(1.0)()]),
    ("identity_gate_off", lambda: [_patch_identity_off()()]),
    ("evidence_validator_off", lambda: [_patch_validator_pass("EvidenceProvenanceValidator")()]),
    ("mission_drift_validator_off", lambda: [_patch_validator_pass("MissionDriftDetector")()]),
    ("gate_model_fidelity_off", lambda: [_patch_gate_pass("model_fidelity")()]),
    ("gate_risk_coverage_off", lambda: [_patch_gate_pass("risk_coverage")()]),
    ("gate_causal_confidence_off", lambda: [_patch_gate_pass("causal_confidence")()]),
    ("gate_recovery_off", lambda: [_patch_gate_pass("recovery")()]),
    ("gate_authority_off", lambda: [_patch_gate_pass("authority")()]),
    ("gate_observability_off", lambda: [_patch_gate_pass("observability")()]),
    # ── v8 Phase 3: per-advisor independence + leave-one-out + crew ──
    ("ablate_RealityValidator", lambda: [_ablate("RealityValidator")()]),
    ("ablate_ConstraintValidator", lambda: [_ablate("ConstraintValidator")()]),
    ("ablate_MemoryAdvisor", lambda: [_ablate("MemoryAdvisor")()]),
    ("ablate_MissionDriftDetector", lambda: [_ablate("MissionDriftDetector")()]),
    ("ablate_EvidenceProvenanceValidator", lambda: [_ablate("EvidenceProvenanceValidator")()]),
    ("only_RealityValidator", _only("RealityValidator")),
    ("only_ConstraintValidator", _only("ConstraintValidator")),
    ("only_MemoryAdvisor", _only("MemoryAdvisor")),
    ("only_MissionDriftDetector", _only("MissionDriftDetector")),
    ("only_EvidenceProvenanceValidator", _only("EvidenceProvenanceValidator")),
    ("council_advisors_all_off", lambda: [_ablate(n)() for n in ADVISORS]),
    ("distributed_council_off",
     lambda: {"patches": [], "config": {"distributed_council_enabled": False}}),
]


def run(cycles: int = 120, seed: int = 42,
        only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run every variant and aggregate the ablation matrix.

    Args:
        cycles: pipeline cycles per variant.
        seed: deterministic seed.
        only: optional subset of variant names.

    Returns:
        The matrix report (JSON-ready).
    """
    results: Dict[str, Any] = {}
    base_digest = None
    for name, factory in VARIANTS:
        if only and name not in only:
            continue
        spec = factory()
        if isinstance(spec, dict):
            patches = spec.get("patches", [])
            overrides = spec.get("config")
        else:
            patches, overrides = spec, None
        res = _run_once(cycles, seed, patches, config_overrides=overrides)
        if name == "baseline":
            base_digest = res["behavior_digest"]
        res["behavior_changed_vs_baseline"] = (
            None if base_digest is None else res["behavior_digest"] != base_digest
        )
        results[name] = res
    return {"phase": "v8-phase2-causal-ablation", "cycles": cycles, "seed": seed,
            "baseline_digest": base_digest, "variants": results}


def _row(name: str, r: Dict[str, Any]) -> str:
    """Format one matrix row.

    Args:
        name: variant name.
        r: variant result dict.

    Returns:
        A single aligned text row.
    """
    changed = r.get("behavior_changed_vs_baseline")
    tag = "SAME" if changed is False else ("CHANGED" if changed is True else "BASE")
    return (f"  {name:32s} {tag:8s} acted={r['acted_cycles']:3d} "
            f"blocks={r['firewall_block_count']:3d} ep={r['episodes']:2d} "
            f"DI={r['DI'].get('mean', 0):.3f} MD={r['MD'].get('mean', 0):.3f} "
            f"gate-cycles={sum(r['blocked_by_gate'].values()):3d} "
            f"idproj={r['identity_projection']['projected_cycles']:3d} "
            f"digest={r['behavior_digest']}")


def main(argv=None) -> int:
    """Run the ablation matrix and print/serialize it.

    Args:
        argv: optional argv list (defaults to sys.argv).

    Returns:
        Process exit code (0 — informational).
    """
    parser = argparse.ArgumentParser(description="v8 Phase 2 causal ablation matrix")
    parser.add_argument("--cycles", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", help="write the matrix to this path")
    parser.add_argument("--only", help="comma-separated variant subset")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    only = [s for s in (args.only or "").split(",") if s] or None
    report = run(args.cycles, args.seed, only)
    print("\n            TELOS v8 Phase 2 — causal ablation matrix")
    print("=" * 96)
    print(f"  cycles={report['cycles']} seed={report['seed']} "
          f"baseline_digest={report['baseline_digest']}")
    for name, r in report["variants"].items():
        print(_row(name, r))
    print("=" * 96)
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
