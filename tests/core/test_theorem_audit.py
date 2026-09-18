"""
Falsifiable Theorem Audit — the anti-tautology contract.

Each theorem has a declared null. These tests prove the auditor can actually
FAIL (the null is reachable) as well as pass on a healthy run.
"""
from types import SimpleNamespace

from telos.core.verifier.theorem_audit import (
    run_audit, kintsugi_experiment, check_delayed_causality,
    check_process_over_outcomes, check_computational_conservation,
    check_possibility_preservation, check_emergent_intelligence,
    check_determinism, NULL_REACHABILITY, THEOREMS,
    identity_projection_experiment, constraint_propagation_experiment,
    feedback_adaptation_experiment, path_dependency_experiment,
    recovery_threshold_experiment, option_decay_experiment,
    adaptive_capacity_experiment, structural_resilience_experiment,
)


def _trace(di=0.9, options=2, streams=3, used=10.0, total=100.0):
    acts = [SimpleNamespace(activated=True) for _ in range(streams)]
    return SimpleNamespace(
        decision_integrity=di, mission_drift=0.1,
        strategic_options=[object()] * options,
        stream_activations=acts,
        budget_consumed_ms=used, budget_total_ms=total,
    )


# --- T1–T7 (config-reachable nulls) ---------------------------------------

def test_kintsugi_experiment_holds():
    holds, measured = kintsugi_experiment()
    assert holds is True, measured


def test_delayed_causality_holds_and_is_strict():
    cfg = SimpleNamespace(horizon=1, feedback_lag=5)
    holds, measured = check_delayed_causality(cfg)
    assert holds is True and "6" in measured


def test_process_check_fails_on_out_of_range_di():
    assert check_process_over_outcomes([_trace(di=0.5)])[0] is True
    assert check_process_over_outcomes([_trace(di=1.5)])[0] is False


def test_conservation_check_fails_on_overrun():
    assert check_computational_conservation([_trace(used=100, total=100)])[0] is True
    assert check_computational_conservation([_trace(used=200, total=100)])[0] is False


def test_possibility_check_fails_on_zero_options():
    assert check_possibility_preservation([_trace(options=1)])[0] is True
    assert check_possibility_preservation([_trace(options=0)])[0] is False


def test_emergent_check_fails_on_single_stream():
    assert check_emergent_intelligence([_trace(streams=2)])[0] is True
    assert check_emergent_intelligence([_trace(streams=1)])[0] is False


def test_determinism_check():
    assert check_determinism("abc", "abc")[0] is True
    assert check_determinism("abc", "def")[0] is False


# --- T8–T15 (real-component experiments hold on a healthy system) ---------

def test_new_experiments_hold_on_healthy_components():
    assert identity_projection_experiment()[0] is True
    assert constraint_propagation_experiment()[0] is True
    assert feedback_adaptation_experiment()[0] is True
    assert path_dependency_experiment()[0] is True
    assert recovery_threshold_experiment()[0] is True
    assert option_decay_experiment()[0] is True
    assert adaptive_capacity_experiment()[0] is True
    assert structural_resilience_experiment()[0] is True


# --- T8–T15 null reachability (sabotaged components flip the row) ---------

class _PermissiveGate:
    def is_admissible(self, *args, **kwargs):
        return True

    def project_intents(self, intents, *args, **kwargs):
        return list(intents)


def test_identity_projection_null_is_reachable():
    holds, measured = identity_projection_experiment(_PermissiveGate())
    assert holds is False, measured


class _PermissiveValidator:
    name = "ConstraintValidator"

    def validate(self, world, intent, domain_facts=None, **kwargs):
        from telos.core.council.base import ValidationSignal
        return ValidationSignal(validator_name=self.name, passed=True,
                                confidence=0.95, reason="sabotaged",
                                evidence_weight=0.2)


def test_constraint_propagation_null_is_reachable():
    from telos.core.governance.firewall import DecisionFirewall
    holds, measured = constraint_propagation_experiment(
        validator=_PermissiveValidator(),
        firewall=DecisionFirewall(),
    )
    assert holds is False, measured


class _FrozenInfra:
    def __init__(self, recovery=False):
        self.policy = SimpleNamespace(current=SimpleNamespace(
            risk_tolerance=0.3, recovery_mode=recovery))

    def observe(self, result):
        return None


def test_feedback_adaptation_null_is_reachable():
    holds, measured = feedback_adaptation_experiment(_FrozenInfra())
    assert holds is False, measured


def test_recovery_threshold_null_is_reachable():
    holds, measured = recovery_threshold_experiment(_FrozenInfra(recovery=False))
    assert holds is False, measured


class _ConstantLedger:
    def enrich(self, world, cycle=0):
        from telos.world.world import World
        out = World(state=world.state)
        out.metadata["semantic_depths"] = [
            SimpleNamespace(semantic_identity="constant")]
        return out


def test_path_dependency_null_is_reachable():
    holds, measured = path_dependency_experiment(_ConstantLedger)
    assert holds is False, measured


class _DeletingLibrary:
    def __init__(self):
        self.skill_count = 3
        self.archived_count = 0
        self._cycle = 0

    def index_skill(self, skill):
        return None

    def prune(self):
        self.skill_count = 0

    def reset_cycle(self):
        return None


def test_option_decay_null_is_reachable():
    holds, measured = option_decay_experiment(_DeletingLibrary())
    assert holds is False, measured


class _DeafPolicyManager:
    def __init__(self):
        self.current = SimpleNamespace(mission_name="default",
                                       risk_tolerance=0.3)

    def set_policy(self, policy):
        return None

    @property
    def stats(self):
        return {"policy_changes": 0}


def test_adaptive_capacity_null_is_reachable():
    holds, measured = adaptive_capacity_experiment(_DeafPolicyManager())
    assert holds is False, measured


class _PermissiveFirewall:
    def inspect(self, *args, **kwargs):
        return SimpleNamespace(passed=True, blocked_by=None)


def test_structural_resilience_null_is_reachable():
    holds, measured = structural_resilience_experiment(_PermissiveFirewall())
    assert holds is False, measured


# --- report-level contract -------------------------------------------------

def test_run_audit_passes_on_healthy_traces():
    cfg = SimpleNamespace(horizon=5, feedback_lag=0)
    report = run_audit([_trace(), _trace()], cfg, "fp", "fp")
    assert report["passed"] is True
    assert len(report["rows"]) == len(THEOREMS)


def test_run_audit_fails_when_a_theorem_is_violated():
    cfg = SimpleNamespace(horizon=5, feedback_lag=0)
    report = run_audit([_trace(options=0)], cfg, "fp", "fp")
    assert report["passed"] is False
    failed = [r["id"] for r in report["rows"] if not r["passed"]]
    assert "T4-possibility" in failed


def test_every_theorem_declares_a_null_and_reachability():
    allowed = {"config", "component_injection", "implementation_mutation"}
    assert set(THEOREMS) == set(NULL_REACHABILITY)
    for tid, (name, statement, null) in THEOREMS.items():
        assert name and statement and null, tid
        assert NULL_REACHABILITY[tid] in allowed, tid


def test_t7_is_explicitly_implementation_mutation_only():
    assert NULL_REACHABILITY["T7-delayed-causality"] == "implementation_mutation"
