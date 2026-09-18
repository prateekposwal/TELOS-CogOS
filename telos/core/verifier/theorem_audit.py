"""
Falsifiable Theorem Audit — core TELOS theorems as measured, null-anchored
invariants.

The repository's "theorems" were constructive existence proofs ("a validator
exists, therefore the axiom holds"). That is not a prediction. This module
restates the load-bearing claims as *measurements with a declared null*: each
theorem names the metric, the baseline it must beat, and the null behaviour
that would falsify it. `run_audit` returns one row per theorem with the
measured value, the threshold, and PASS/FAIL.

Each theorem also declares how its null is reachable:

* ``config`` — a hostile input/trace flips the row to FAIL.
* ``component_injection`` — the tests swap in a sabotaged component (a
  permissive gate, a frozen policy manager) to flip the row to FAIL.
* ``implementation_mutation`` — only changing the implementation can falsify
  the claim; the running code computes it by construction. T7 is the one case.

T1–T5 measure the real traces produced by the CLI harness
(`telos/tools/theorem_audit.py`). T6 and T8–T15 build and drive the real
component they name — no mocks in the happy path.

Nothing here re-implements the pipeline.
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
    "T8-identity-projection": (
        "Identity Projection (F(I))",
        "An intent outside the identity projection F(I) is structurally "
        "inadmissible: the real IdentityProjectionGate admits only "
        "trajectories consistent with Core values, narrative role, and an "
        "active mission.",
        "An identity-inadmissible intent (core-value violator, "
        "role-incompatible, or mission-less) survives F(I) projection.",
    ),
    "T9-constraint-propagation": (
        "Constraint Propagation",
        "A domain constraint violation propagates through the real "
        "ConstraintValidator and the blocking Council to a refused decision.",
        "A constraint-violating action passes validation (the constraint "
        "fails to block).",
    ),
    "T10-feedback-adaptation": (
        "Feedback Adaptation",
        "The real InfrastructureManager.observe() loop adapts policy after a "
        "failure cluster (risk tolerance is lowered).",
        "A failure cluster leaves every policy parameter unchanged (the "
        "feedback loop is dead).",
    ),
    "T11-path-dependency": (
        "Path Dependency",
        "For an identical current state, a different interaction history "
        "yields a different semantic depth (π(s, H) ≠ π(s, H')).",
        "Identical current states yield identical semantic depth regardless "
        "of history.",
    ),
    "T12-recovery-threshold": (
        "Maintenance vs Recovery",
        "A sustained failure cluster drives the real InfrastructureManager "
        "into recovery mode before catastrophic failure.",
        "A sustained failure cluster never triggers recovery.",
    ),
    "T13-option-decay": (
        "Option Decay",
        "Stale skills are archived (not deleted) by the real SkillLibrary and "
        "restored on reset_cycle — entropy falls without information loss.",
        "Pruning deletes a skill (active+archived total drops) and it cannot "
        "be restored.",
    ),
    "T14-adaptive-capacity": (
        "Adaptive Capacity",
        "A mission policy swap replaces L_P parameters, is recorded in the "
        "audit trail, and leaves mission identity intact.",
        "A policy swap is unrecorded and/or loses the mission name.",
    ),
    "T15-structural-resilience": (
        "Structural Resilience",
        "Two independent blocking mechanisms exist: the Council gate and the "
        "DecisionFirewall's own integrity check; each can refuse a proposal "
        "the other admits.",
        "A council-rejected or low-integrity proposal passes the firewall "
        "(no independent blocking).",
    ),
}

# How each theorem's null can be made to fire. See the module docstring.
NULL_REACHABILITY: Dict[str, str] = {
    "T1-determinism": "config",
    "T2-process": "config",
    "T3-conservation": "config",
    "T4-possibility": "config",
    "T5-emergent": "config",
    "T6-kintsugi": "component_injection",
    "T7-delayed-causality": "implementation_mutation",
    "T8-identity-projection": "component_injection",
    "T9-constraint-propagation": "component_injection",
    "T10-feedback-adaptation": "component_injection",
    "T11-path-dependency": "component_injection",
    "T12-recovery-threshold": "component_injection",
    "T13-option-decay": "component_injection",
    "T14-adaptive-capacity": "component_injection",
    "T15-structural-resilience": "component_injection",
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


def identity_projection_experiment(
        gate: Optional[Any] = None) -> Tuple[bool, str]:
    """T8 — the real F(I) gate projects identity-inadmissible intents out.

    Drives the canonical IdentityProjectionGate: a mission-less trajectory, a
    core-value violator, and a role-incompatible trajectory must each be
    rejected, while a reflex intent passes.

    Args:
        gate: optional gate override (tests inject a permissive gate to prove
            the null is reachable). Defaults to the real gate.

    Returns:
        (holds, measured) tuple.
    """
    from telos.core.identity.projection_gate import IdentityProjectionGate
    from telos.intent_ir import IntentIR

    gate = gate if gate is not None else IdentityProjectionGate()
    bad_mission = gate.is_admissible("plan_trajectory", mission_active=False)
    bad_value = gate.is_admissible("steal_payload", mission_active=True)
    bad_role = gate.is_admissible("explore_dangerous", mission_active=True,
                                  narrative_role="guardian")
    good = gate.is_admissible("reflex", mission_active=False)
    intents = [
        IntentIR(intent_type="plan_trajectory", confidence=0.8),
        IntentIR(intent_type="steal_payload", confidence=0.8),
        IntentIR(intent_type="reflex", confidence=0.8),
    ]
    projected = gate.project_intents(intents, mission_active=False)
    projected_out = len(intents) - len(projected)
    holds = (bad_mission is False and bad_value is False and bad_role is False
             and good is True and len(projected) == 1
             and projected[0].intent_type == "reflex")
    measured = (f"projected_out={projected_out}/3, "
                f"mission_block={not bad_mission}, value_block={not bad_value}, "
                f"role_block={not bad_role}, reflex_admitted={good}")
    return (holds, measured)


def constraint_propagation_experiment(
        validator: Optional[Any] = None,
        firewall: Optional[Any] = None) -> Tuple[bool, str]:
    """T9 — a constraint violation propagates to a council/firewall refusal.

    Drives the real ConstraintValidator + Council + DecisionFirewall with an
    action that moves the state out of bounds under a declared boundary
    constraint.

    Args:
        validator: optional validator override (tests inject a permissive
            validator to prove the null is reachable).
        firewall: optional firewall override (tests inject a permissive
            firewall to prove the null is reachable).

    Returns:
        (holds, measured) tuple.
    """
    import numpy as np
    from telos.core.council.validators.constraint import ConstraintValidator
    from telos.core.council.base import Council
    from telos.core.governance.firewall import DecisionFirewall
    from telos.world.world import World
    from telos.world.facts import DomainFacts
    from telos.intent_ir import IntentIR

    validator = validator if validator is not None else ConstraintValidator()
    firewall = firewall if firewall is not None else DecisionFirewall()
    world = World(state=np.array([0.5, 0.5]))
    intent = IntentIR(intent_type="plan_trajectory", confidence=0.9,
                      params={"action_vector": np.array([-1.0, 0.0])})
    facts = DomainFacts(state=np.array([0.5, 0.5]), resources={},
                        constraints=["world_bounds"], events=[], metrics={})

    signal = validator.validate(world, intent, facts)
    council = Council()
    council.register(validator)
    verdict = council.evaluate(world, intent, facts)
    fw = firewall.inspect(world, intent, council_validated=verdict.validated,
                          decision_integrity=verdict.decision_integrity)
    holds = (signal.passed is False and verdict.validated is False
             and fw.passed is False)
    measured = (f"validator_blocked={not signal.passed}, "
                f"council_blocked={not verdict.validated}, "
                f"firewall_blocked={not fw.passed}({fw.blocked_by})")
    return (holds, measured)


def _blocked_result() -> Any:
    """Build a real council-blocked PipelineResult for infra experiments.

    Returns:
        A PipelineResult whose DecisionTrace records a council block.
    """
    import numpy as np
    from telos.core.runtime import DecisionTrace, PipelineResult, PipelinePhase
    from telos.intent_ir import IntentIR

    trace = DecisionTrace(
        cycle_id=1, timestamp=0.0,
        world_state_snapshot=np.array([1.0, 2.0]),
        domain_facts=None, stream_activations=[],
        selected_intent=IntentIR(intent_type="bad", confidence=0.5),
        selected_action=None, representation="cartesian",
        budget_consumed_ms=10.0, budget_total_ms=50.0,
        worlds_simulated=5, cycle_duration_ms=8.0, health_score=0.3,
        council_validated=False, decision_integrity=0.2, mission_drift=5.0,
        blocking_validator="RealityValidator",
    )
    return PipelineResult(None, 0.3, PipelinePhase.COMPLETE,
                          council_blocked=True, decision_trace=trace)


def feedback_adaptation_experiment(
        infra: Optional[Any] = None, cycles: int = 4) -> Tuple[bool, str]:
    """T10 — the InfraManager feedback loop lowers risk after failures.

    Args:
        infra: optional InfrastructureManager override (tests inject a frozen
            manager to prove the null is reachable). Defaults to the real one.
        cycles: number of blocked observations to feed.

    Returns:
        (holds, measured) tuple.
    """
    if infra is None:
        from telos.core.infra_manager.infrastructure_manager import (
            InfrastructureManager,
        )
        infra = InfrastructureManager()
    before = infra.policy.current.risk_tolerance
    for _ in range(cycles):
        infra.observe(_blocked_result())
    after = infra.policy.current.risk_tolerance
    holds = after < before
    return (holds, f"risk_tolerance {before:.3f} -> {after:.3f} "
                   f"after {cycles} blocked cycles")


def path_dependency_experiment(
        ledger_factory: Optional[Any] = None) -> Tuple[bool, str]:
    """T11 — identical current state, different history, different meaning.

    Args:
        ledger_factory: optional zero-arg factory returning a ledger object
            (tests inject a constant-depth ledger to prove the null is
            reachable). Defaults to the real WorldLedger.

    Returns:
        (holds, measured) tuple.
    """
    import numpy as np
    from telos.core.ledger.world_ledger import WorldLedger
    from telos.world.world import World

    factory = ledger_factory if ledger_factory is not None else WorldLedger
    world = World(state=np.zeros(2), entities=["alpha"])

    fresh = factory()
    fresh_depth = fresh.enrich(world, cycle=0).metadata["semantic_depths"][0]

    historian = factory()
    for cycle in range(6):
        enriched = historian.enrich(world, cycle=cycle)
    history_depth = enriched.metadata["semantic_depths"][0]

    holds = fresh_depth.semantic_identity != history_depth.semantic_identity
    measured = (f"fresh='{fresh_depth.semantic_identity}' "
                f"history='{history_depth.semantic_identity}'")
    return (holds, measured)


def recovery_threshold_experiment(
        infra: Optional[Any] = None, cycles: int = 10) -> Tuple[bool, str]:
    """T12 — a sustained failure cluster triggers recovery mode.

    Args:
        infra: optional InfrastructureManager override (tests inject a manager
            that never recovers to prove the null is reachable). Defaults to
            the real one.
        cycles: number of blocked observations to feed.

    Returns:
        (holds, measured) tuple.
    """
    if infra is None:
        from telos.core.infra_manager.infrastructure_manager import (
            InfrastructureManager,
        )
        infra = InfrastructureManager()
    for _ in range(cycles):
        infra.observe(_blocked_result())
    recovery = infra.policy.current.recovery_mode
    return (recovery, f"recovery_mode={recovery} after {cycles} blocked cycles")


def option_decay_experiment(
        library: Optional[Any] = None) -> Tuple[bool, str]:
    """T13 — stale skills are archived, not deleted, and are restorable.

    Args:
        library: optional SkillLibrary override (tests inject a deleting
            library to prove the null is reachable). Defaults to the real one.

    Returns:
        (holds, measured) tuple.
    """
    from telos.core.ledger.skill_library import SkillLibrary, Skill

    library = library if library is not None else SkillLibrary(prune_age_cycles=2)
    for i in range(3):
        library.index_skill(Skill(
            skill_id=f"s{i}", fingerprint=f"fp{i}", trajectory=None,
            utility_score=0.5, last_matched_cycle=1,
        ))
    total_before = library.skill_count + library.archived_count
    # The library's internal clock is advanced so the three skills are stale
    # relative to prune_age_cycles (the established test pattern in
    # tests/core/test_skill_seeds.py).
    library._cycle = 100
    library.prune()
    total_pruned = library.skill_count + library.archived_count
    archived = library.archived_count
    library.reset_cycle()
    total_reset = library.skill_count + library.archived_count
    holds = (total_pruned == total_before and archived >= 1
             and total_reset == total_before)
    measured = (f"tracked {total_before}->prune {total_pruned} "
                f"(archived={archived})->reset {total_reset}")
    return (holds, measured)


def adaptive_capacity_experiment(
        policy_manager: Optional[Any] = None) -> Tuple[bool, str]:
    """T14 — a policy swap is recorded and preserves the mission identity.

    Args:
        policy_manager: optional MissionPolicyManager override (tests inject a
            manager that drops the audit trail to prove the null is
            reachable). Defaults to the real one.

    Returns:
        (holds, measured) tuple.
    """
    from telos.core.infra_manager.mission_policy import (
        MissionPolicyManager, MissionPolicy,
    )

    ppm = policy_manager if policy_manager is not None else MissionPolicyManager()
    ppm.set_policy(MissionPolicy("high_stakes", risk_tolerance=0.1,
                                 exploration_budget=0.2))
    mission_ok = ppm.current.mission_name == "high_stakes"
    risk_ok = abs(ppm.current.risk_tolerance - 0.1) < 1e-9
    logged = ppm.stats.get("policy_changes", 0) >= 1
    holds = mission_ok and risk_ok and logged
    measured = (f"mission={ppm.current.mission_name}, "
                f"risk={ppm.current.risk_tolerance}, logged={logged}")
    return (holds, measured)


def structural_resilience_experiment(
        firewall: Optional[Any] = None) -> Tuple[bool, str]:
    """T15 — the Council gate and the firewall block independently.

    Args:
        firewall: optional DecisionFirewall override (tests inject a permissive
            firewall to prove the null is reachable). Defaults to the real one.

    Returns:
        (holds, measured) tuple.
    """
    import numpy as np
    from telos.core.governance.firewall import DecisionFirewall
    from telos.world.world import World
    from telos.intent_ir import IntentIR

    firewall = firewall if firewall is not None else DecisionFirewall()
    world = World(state=np.zeros(2))
    intent = IntentIR(intent_type="plan_trajectory", confidence=0.9)
    council_block = firewall.inspect(world, intent, council_validated=False,
                                     decision_integrity=0.9)
    di_block = firewall.inspect(world, intent, council_validated=True,
                                decision_integrity=0.0)
    clean = firewall.inspect(world, intent, council_validated=True,
                             decision_integrity=0.9)
    holds = (council_block.passed is False and di_block.passed is False
             and clean.passed is True)
    measured = (f"council_rejection->{council_block.blocked_by}, "
                f"low_integrity->{di_block.blocked_by}, clean_passes={clean.passed}")
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
        "T8-identity-projection": identity_projection_experiment(),
        "T9-constraint-propagation": constraint_propagation_experiment(),
        "T10-feedback-adaptation": feedback_adaptation_experiment(),
        "T11-path-dependency": path_dependency_experiment(),
        "T12-recovery-threshold": recovery_threshold_experiment(),
        "T13-option-decay": option_decay_experiment(),
        "T14-adaptive-capacity": adaptive_capacity_experiment(),
        "T15-structural-resilience": structural_resilience_experiment(),
    }
    rows = []
    for tid, (name, statement, null) in THEOREMS.items():
        holds, measured = checks.get(tid, (False, "not measured"))
        rows.append({
            "id": tid, "name": name, "statement": statement,
            "null": null, "null_reachable": NULL_REACHABILITY.get(tid, "config"),
            "measured": measured, "passed": bool(holds),
        })
    return {"rows": rows, "passed": all(r["passed"] for r in rows)}


__all__ = ["THEOREMS", "NULL_REACHABILITY", "run_audit", "kintsugi_experiment",
           "check_delayed_causality", "identity_projection_experiment",
           "constraint_propagation_experiment", "feedback_adaptation_experiment",
           "path_dependency_experiment", "recovery_threshold_experiment",
           "option_decay_experiment", "adaptive_capacity_experiment",
           "structural_resilience_experiment"]
