"""
TELOS v6 — Phases 9 & 10 tests.

Phase 9 — DevDomain real ground-truth loop: measured evidence never lies.
Phase 10 — Experiment reuse of TheoryBuilder falsification with EXPERIMENT
           evidence + Reality Gap.
"""

import json
import os
import tempfile

import numpy as np

from telos.adapters import dev_validation as dv
from telos.adapters.dev_validation import (
    RunClass, discover_commands, _safe_run, validate_project, _extract_pass_ratio,
)
from telos.world.evidence import EvidenceSource, ValidationStatus
from telos.core.reasoning.theory.dataclasses import Hypothesis
from telos.core.reasoning.theory.experiment import (
    Experiment, ExperimentOutcome, run_experiment,
)


# ─── Phase 9: evidence must not lie ────────────────────────────────────────────

def _make_project(scripts=None, name="proj"):
    pkg = {"name": name, "scripts": scripts or {}}
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "package.json"), "w") as f:
        json.dump(pkg, f)
    return d


def test_assumed_value_never_reported_measured():
    # A project with a test script but where the tool cannot run (no node)
    # must produce evidence stamped UNVALIDATED/SIMULATION, never MEASURED.
    d = _make_project(scripts={"test": "echo hi"})
    # force an INFRA error by pointing at a nonexistent binary path
    ratio, _, _, runs, evidence = validate_project(d, timeout=0.1)
    # Whatever happened, the stamping invariant must hold:
    if evidence.validation_status == ValidationStatus.MEASURED:
        assert evidence.source in (EvidenceSource.EXTERNAL_SOLVER,
                                   EvidenceSource.MEASUREMENT)
    if evidence.source == EvidenceSource.SIMULATION:
        assert evidence.validation_status == ValidationStatus.UNVALIDATED
        assert not evidence.is_measured
    # consistency: if no test ran successfully, NEVER claim measured
    any_test_ran = any(r.name in ("test", "test:ci", "pytest", "go-test")
                       and r.classification == RunClass.SUCCESS for r in runs)
    assert evidence.is_measured == any_test_ran
    assert ratio is None or (0.0 <= ratio <= 1.0)


def test_safe_run_bounded_and_classified():
    # INFRA_ERROR when binary missing
    run = _safe_run(["definitely_not_a_real_binary_xyz"], cwd="/tmp", timeout=2)
    assert run.classification == RunClass.INFRA_ERROR
    assert run.timed_out is False


def test_safe_run_success_classification():
    run = _safe_run(["/bin/echo", "ok"], cwd="/tmp", timeout=5)
    assert run.classification == RunClass.SUCCESS
    assert run.returncode == 0


def test_timeout_classification():
    run = _safe_run(["/bin/sleep", "5"], cwd="/tmp", timeout=0.2)
    assert run.classification == RunClass.TIMEOUT
    assert run.timed_out is True


def test_command_discovery_detects_npm_test():
    d = _make_project(scripts={"test": "jest"})
    names = [n for n, _ in discover_commands(d)]
    assert "test" in names


def test_command_discovery_detects_typecheck_with_tsconfig():
    d = _make_project(scripts={})
    with open(os.path.join(d, "tsconfig.json"), "w") as f:
        json.dump({"compilerOptions": {"strict": True}}, f)
    names = [n for n, _ in discover_commands(d)]
    assert any(n.startswith("typecheck") for n in names)


def test_parse_pass_ratio():
    class R:
        stdout = "2 passed, 1 failed in 0.1s"
        stderr = ""
    ratio = _extract_pass_ratio(R())
    assert abs(ratio - (2.0 / 3.0)) < 1e-9


# ─── Phase 10: Experiment ──────────────────────────────────────────────────────

def _hypothesis(predicted=0.5):
    return Hypothesis(
        id="h1", description="test", context_signature={}, action="act",
        predicted_outcome=predicted, confidence=0.8, supporting_patterns=[],
    )


def test_experiment_confirmed():
    h = _hypothesis(predicted=0.5)
    exp = run_experiment(h, predicted=0.5, observed=0.52, tolerance=0.2)
    assert exp.outcome == ExperimentOutcome.CONFIRMED
    assert exp.hypothesis_survived is True
    assert exp.hypothesis_id == "h1"
    assert exp.evidence.source == EvidenceSource.EXPERIMENT
    assert exp.evidence.validation_status == ValidationStatus.VALIDATED
    assert h.tests_passed == 1


def test_experiment_falsified():
    h = _hypothesis(predicted=0.5)
    exp = run_experiment(h, predicted=0.5, observed=1.9, tolerance=0.2)
    assert exp.outcome == ExperimentOutcome.FALSIFIED
    assert exp.hypothesis_survived is False
    assert exp.evidence.validation_status == ValidationStatus.FALSIFIED
    assert h.tests_failed == 1
    assert exp.reality_gap > 0.2


def test_experiment_reality_gap_measured():
    h = _hypothesis(predicted=0.0)
    exp = run_experiment(h, predicted=0.0, observed=3.0, tolerance=0.2)
    assert abs(exp.reality_gap - 3.0) < 1e-9


def test_experiment_to_dict_serializable():
    h = _hypothesis()
    exp = run_experiment(h, predicted=0.5, observed=0.5)
    d = exp.to_dict()
    assert d["outcome"] == "CONFIRMED"
    assert d["evidence"]["source"] == "EXPERIMENT"


def test_confirming_raises_confidence_and_falsifying_falsifies():
    h = _hypothesis(predicted=0.5)
    for _ in range(5):
        run_experiment(h, predicted=0.5, observed=0.5)
    assert h.confidence > 0.8
    # then repeatedly falsify until falsified
    f = _hypothesis(predicted=0.5)
    for _ in range(20):
        run_experiment(f, predicted=0.5, observed=2.0)
    assert f.falsified


# ─── Phase 0 regression: a rc=0 test run IS a measurement (honest invariant) ──

def _stub_validate(discovered, runs_by_name):
    """Run validate_project with stubbed discovery + runner (full control).

    Args:
        discovered: list of (name, args) discover_commands returns.
        runs_by_name: dict name -> CommandRun the stubbed _safe_run returns.

    Returns:
        validate_project(...) tuple via monkeypatched module globals.
    """
    import telos.adapters.dev_validation as dv

    orig_discover = dv.discover_commands
    orig_run = dv._safe_run
    # a fake project path that discover_commands would never touch directly
    import tempfile
    proj = tempfile.mkdtemp()
    try:
        dv.discover_commands = lambda _p: list(discovered)
        dv._safe_run = lambda args, cwd, timeout=30.0: runs_by_name[args[0]] \
            if args and args[0] in runs_by_name else None
        return dv.validate_project(proj, timeout=1.0)
    finally:
        dv.discover_commands = orig_discover
        dv._safe_run = orig_run


def test_rc_zero_test_run_stamps_measured_even_with_unparseable_output():
    """A test command that EXITS 0 is a measurement — garbage/empty output
    must NOT downgrade the stamp to SIMULATION/UNVALIDATED (was the old
    load-dependent flake: `echo hi` with rc=0 -> is_measured=False)."""
    run = dv.CommandRun(
        name="test", args=["fake", "test"], returncode=0,
        stdout="", stderr="", classification=dv.RunClass.SUCCESS,
    )
    ratio, _, _, runs, evidence = _stub_validate(
        [("test", ["fake", "test"])], {"fake": run})
    assert ratio == 1.0, "rc=0 unparseable output truthfully means all green"
    assert evidence.is_measured is True, \
        "a successfully run test is a measurement (honest invariant)"
    assert evidence.validation_status == ValidationStatus.MEASURED


def test_rc_zero_measured_with_parseable_ratio_stays_numeric():
    """SUCCESS with parseable output keeps the truthful numeric ratio."""
    run = dv.CommandRun(
        name="test", args=["fake", "test"], returncode=0,
        stdout="7 passed, 3 failed in 0.5s", stderr="",
        classification=dv.RunClass.SUCCESS,
    )
    ratio, _, _, runs, evidence = _stub_validate(
        [("test", ["fake", "test"])], {"fake": run})
    assert abs(ratio - 0.7) < 1e-9
    assert evidence.is_measured is True


def test_failed_test_run_keeps_numeric_ratio_and_measured_stamp():
    """A GENUINELY failing test run (rc != 0) keeps its numeric ratio and is
    MEASURED — measured is about the run HAPPENING, not about passing."""
    run = dv.CommandRun(
        name="pytest", args=["python3", "-m", "pytest", "-q"], returncode=1,
        stdout="3 passed, 2 failed in 0.4s", stderr="",
        classification=dv.RunClass.TEST_FAILURE,
    )
    ratio, _, _, runs, evidence = _stub_validate(
        [("pytest", ["python3", "-m", "pytest", "-q"])], {"python3": run})
    assert abs(ratio - 0.6) < 1e-9
    assert evidence.is_measured is True, \
        "a genuinely-failed run is still a measurement (a real failed value)"


def test_unrunnable_test_still_never_measured():
    """The OTHER side of the invariant: a command that could NOT run
    (INFRA_ERROR) must never be painted measured."""
    run = dv.CommandRun(
        name="test", args=["nope"], returncode=None,
        stdout="", stderr="", classification=dv.RunClass.INFRA_ERROR,
    )
    ratio, _, _, runs, evidence = _stub_validate(
        [("test", ["nope"])], {"nope": run})
    assert ratio is None
    assert evidence.is_measured is False
    assert evidence.validation_status == ValidationStatus.UNVALIDATED
