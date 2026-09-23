"""
Calibration pressure test — evidence before authority.

Codifies the precondition for ever granting the CalibrationValidator blocking
authority in the canonical pipeline:

    A validator should first demonstrate that it can reliably detect a failure
    before it is given authority to stop the system.

These tests assert the controlled scenario matrix from
``telos/tools/calibration_pressure_test.py``: ``enforce=True`` blocks ONLY the
intended overconfidence case, ``enforce=False`` (canonical) blocks nothing, and
underconfidence — a *different* failure mode — is never punished.
"""

import numpy as np
import pytest

from telos.core.calibration import CalibrationTracker
from telos.core.council.base import Council
from telos.core.council.validators import CalibrationValidator
from telos.intent_ir import IntentIR
from telos.world.world import World
from telos.tools.calibration_pressure_test import (
    build_scenarios, evaluate_scenario, run_scenario_matrix, _tracker_for,
)


def test_scenario_matrix_expectations_hold():
    _, ok = run_scenario_matrix()
    assert ok is True


def test_enforce_blocks_only_overconfidence():
    for sc in build_scenarios():
        enf = evaluate_scenario(sc, enforce=True)
        assert enf["blocked"] is sc.expect_block_enforce, (
            f"{sc.name}: enforce blocked={enf['blocked']}, "
            f"expected={sc.expect_block_enforce}"
        )


def test_advisory_never_blocks():
    for sc in build_scenarios():
        adv = evaluate_scenario(sc, enforce=False)
        assert adv["blocked"] is False, f"{sc.name}: advisory must not block"
        assert adv["signal_passed"] is True


def test_underconfidence_is_not_punished():
    sc = next(s for s in build_scenarios() if s.name == "underconfident")
    enf = evaluate_scenario(sc, enforce=True)
    assert enf["blocked"] is False
    # The high claim recalibrates UP (toward the empirical accuracy), so the
    # overconfidence gap is ~0 even though ECE is high.
    assert enf["gap"] <= 0.05


def test_ece_gate_holds_when_gap_present():
    # gap > 0.2 but ECE below threshold -> the ECE gate must prevent a block.
    sc = next(s for s in build_scenarios() if s.name == "ece_below_threshold")
    enf = evaluate_scenario(sc, enforce=True)
    assert enf["gap"] > 0.2
    assert enf["ece"] < 0.25
    assert enf["blocked"] is False


def test_claim_gate_holds_when_ece_high():
    # ECE above threshold but the claim is not overconfident -> no block.
    sc = next(s for s in build_scenarios() if s.name == "high_ece_low_claim")
    enf = evaluate_scenario(sc, enforce=True)
    assert enf["ece"] > 0.25
    assert enf["blocked"] is False


def test_insufficient_samples_abstains_in_both_modes():
    sc = next(s for s in build_scenarios() if s.name == "insufficient_samples")
    for enforce in (False, True):
        r = evaluate_scenario(sc, enforce=enforce)
        assert r["blocked"] is False
        assert r["sample_count"] < 20


def test_council_effects_of_an_overconfident_block():
    sc = next(s for s in build_scenarios() if s.name == "overconfident")
    r = evaluate_scenario(sc, enforce=True)
    # A lone blocking validator (sole member) refuses validation, and the
    # DissentFloor caps reported DI at 0.3.
    assert r["blocked"] is True
    assert r["decision_integrity"] <= 0.3 + 1e-9
    # A BLOCK is not an ESCALATE.
    assert r["escalation_requested"] is False
