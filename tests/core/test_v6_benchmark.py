"""
TELOS v6.1 — DevDomain Behavioral Benchmark tests.

Locks the benchmark's honesty guarantees:
  - hidden ground truth is never exposed to the observable environment (no leakage)
  - five tasks (A-E) exist as distinct scenarios
  - metrics JSON schema is complete
  - Task E recovery-ACT is NOT counted as false ACT (temporal oracle)
  - a mid-falsification ACT in Task E WOULD count as false ACT
  - Task C correctly DEFERs; Task D authority drops + BLOCKs; genuine FAIL veto survives
"""

import re

from telos.benchmarks.devdomain_v61 import (
    run_benchmark, run_task, ORACLE, TASK_SCENARIOS, ObservedEvidence, TaskRun,
    OracleCheckpoint, TaskOracle, evaluate, _checkpoint_score,
)

FIVE_TASKS = ["task_a", "task_b", "task_c", "task_d", "task_e"]


def test_no_leakage_oracle_not_in_observable_env():
    """The hidden oracle fields must NOT appear in the observable environment."""
    forbidden = ("expected", "correct_fix", "failure_class", "needs_action",
                 "action_allowed", "authority_delta", "decision_class")
    for tid in FIVE_TASKS:
        for obs in TASK_SCENARIOS[tid]:
            fields = set(vars(obs).keys())
            for f in forbidden:
                assert f not in fields, f"{tid} exposes oracle field {f}"


def test_five_tasks_exist_distinct():
    assert list(TASK_SCENARIOS.keys()) == FIVE_TASKS
    for tid in FIVE_TASKS:
        assert len(TASK_SCENARIOS[tid]) >= 1
        assert tid in ORACLE


def test_metrics_json_schema_complete():
    result = run_benchmark(seed=7)
    d = result.to_dict()
    assert d["benchmark"] == "devdomain_v61"
    assert set(d["metrics"].keys()) >= {
        "correct_act_rate", "false_act_rate", "correct_defer_rate", "false_defer_rate",
        "correct_abstain_rate", "false_abstain_rate", "correct_escalate_rate",
        "reality_gap_calibration", "authority_calibration", "over_authority_rate",
        "under_authority_rate", "checkpoint_pass_rate", "correct_action_rate",
    }
    for k, v in d["metrics"].items():
        assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"


def test_task_a_acts_justified():
    run = run_task("task_a")
    assert run.final_decision == "ACT"
    cs = _checkpoint_score(run, ORACLE["task_a"])
    assert cs["false_act"] is False and cs["under_authority"] is False


def test_task_c_defers_insufficient_evidence():
    run = run_task("task_c")
    # real behavioral fix: genuinely insufficient evidence -> not ACT
    assert run.final_decision == "DEFER"
    cs = _checkpoint_score(run, ORACLE["task_c"])
    assert cs["false_act"] is False  # did not over-act
    assert run.decisions[0] not in ("ACT",)


def test_task_d_authority_drops_and_blocks_on_execution_failure():
    run = run_task("task_d")
    assert run.decisions == ["ACT", "BLOCK"]  # static-ok then execution-fail -> BLOCK
    assert run.authority_direction == "DECREASED"
    cs = _checkpoint_score(run, ORACLE["task_d"])
    assert cs["false_act"] is False  # the execution-failure checkpoint forbade ACT (BLOCK is safe)


def test_task_e_recovery_act_is_NOT_false_act():
    """The recovered final ACT in Task E must NOT count as false over-authority."""
    run = run_task("task_e")
    assert run.decisions == ["ACT", "BLOCK", "ACT"]  # validated -> falsified -> recovered
    cs = _checkpoint_score(run, ORACLE["task_e"])
    assert cs["false_act"] is False
    # The recovery checkpoint REQUIRES final ACT and it is satisfied.
    recovery_cp = [c for c in ORACLE["task_e"].checkpoints if c.label == "recovery"][0]
    assert run.decisions_at(recovery_cp.decision_idx) == "ACT"
    # authority went down (falsification) then up (recovery) relative to the bin
    assert run.authority[0] >= run.authority[1]  # 0.9 -> 0.0 (down)
    assert run.authority[2] > run.authority[1]   # 0.5 > 0.0 (up)


def test_task_e_mid_falsification_act_WOULD_be_false_act():
    """A temporal oracle must flag ACT during the falsification phase as FALSE ACT."""
    checkpoint = OracleCheckpoint(
        decision_idx=1, label="falsification",
        required=(), forbidden=("ACT",), authority_direction="DECREASE",
    )
    oracle = TaskOracle("task_e_fake", "RECOVERY",
                        checkpoints=(checkpoint,), task_type="recovery")
    # Simulate a bad run that ACTs during falsification.
    bad = TaskRun("task_e_fake", decisions=["ACT", "ACT", "ACT"],
                  authority=[0.9, 0.9, 0.9])
    cs = _checkpoint_score(bad, oracle)
    assert cs["false_act"] is True


def test_benchmark_over_and_under_authority_both_low():
    """The honest headline: TELOS neither over-acts nor refuses without reason."""
    result = run_benchmark(seed=7)
    m = result.metrics
    assert m["over_authority_rate"] == 0.0
    assert m["under_authority_rate"] == 0.0
    assert m["checkpoint_pass_rate"] == 1.0
    assert m["correct_action_rate"] == 1.0


def test_reality_gap_tracks_falsification():
    """Reality-gap calibration: falsifying tasks (D/E) show authority DECREASE."""
    assert run_task("task_e").authority_direction == "DECREASED"
