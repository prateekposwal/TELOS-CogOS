"""Contract tests for telos/core/council/validators/constraint.py.

Covers the opcode check factories (_make_check_*), the ConstraintScript
composable executor, and the ConstraintValidator council advisor.
"""
import hashlib

import numpy as np
import pytest

from telos.core.council.validators.constraint import (
    ConstraintOpcode,
    ConstraintScript,
    ConstraintValidator,
    _make_check_nan,
    _make_check_bounds,
    _make_check_safety,
    _make_check_drift,
    _make_check_history,
    _make_check_mission,
)
from telos.core.ledger.skill_library import SkillLibrary, Skill
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR


class TestConstraintOpcode:
    def test_enum_values(self):
        assert ConstraintOpcode.CHECK_NAN.value == "check_nan"
        assert ConstraintOpcode.CHECK_BOUNDS.value == "check_bounds"
        assert ConstraintOpcode.CHECK_SAFETY.value == "check_safety"
        assert ConstraintOpcode.CHECK_DRIFT.value == "check_drift"
        assert ConstraintOpcode.CHECK_HISTORY.value == "check_history"
        assert ConstraintOpcode.CHECK_MISSION.value == "check_mission"


class TestCheckNan:
    def test_clean_state_passes(self):
        check = _make_check_nan()
        passed, reason, weight = check(World(state=np.zeros(4)), None, None)
        assert passed is True
        assert "clean" in reason
        assert weight == 0.3

    def test_nan_state_fails(self):
        check = _make_check_nan()
        world = World(state=np.array([0.0, np.nan, 0.0, np.inf]))
        passed, reason, weight = check(world, None, None)
        assert passed is False
        assert "NaN" in reason
        assert "Inf" in reason
        assert weight == 0.7

    def test_action_vector_nan_fails(self):
        check = _make_check_nan()
        intent = IntentIR(params={"action_vector": np.array([0.0, np.nan])})
        passed, reason, _ = check(World(state=np.zeros(2)), intent, None)
        assert passed is False
        assert "action contains NaN" in reason


class TestCheckBounds:
    def test_clean_passes(self):
        check = _make_check_bounds()
        intent = IntentIR(params={"action_vector": np.array([1.0, 0.0])})
        passed, reason, weight = check(World(state=np.zeros(2)), intent, None)
        assert passed is True
        assert weight == 0.2

    def test_large_action_norm_fails(self):
        check = _make_check_bounds()
        intent = IntentIR(params={"action_vector": np.array([100.0, 100.0])})
        passed, reason, _ = check(World(state=np.zeros(2)), intent, None)
        assert passed is False
        assert "exceeds 100" in reason

    def test_domain_constraints_report_fails(self):
        check = _make_check_bounds()
        facts = DomainFacts(
            state=np.zeros(2), resources={}, constraints=["bounds"],
            events=[], metrics={},
        )
        passed, reason, _ = check(World(state=np.zeros(2)), None, facts)
        assert passed is False
        assert "out-of-bounds" in reason


class TestCheckSafety:
    def test_ok(self):
        check = _make_check_safety()
        passed, reason, weight = check(World(state=np.zeros(2), safety_score=0.9), None, None)
        assert passed is True
        assert weight == 0.2

    def test_low_safety_fails(self):
        check = _make_check_safety()
        passed, reason, weight = check(World(state=np.zeros(2), safety_score=0.2), None, None)
        assert passed is False
        assert "below 0.3" in reason
        assert weight == 0.6


class TestCheckDrift:
    def _traj_intent(self, predicted):
        traj = type("Traj", (), {"state": np.asarray(predicted, dtype=float)})()
        return IntentIR(intent_type="move", params={"trajectory": traj})

    def test_within_bounds(self):
        check = _make_check_drift()
        passed, reason, weight = check(
            World(state=np.array([0.0, 0.0])), self._traj_intent([1.0, 0.0]), None
        )
        assert passed is True
        assert "within bounds" in reason

    def test_exceeds_threshold(self):
        check = _make_check_drift()
        passed, reason, _ = check(
            World(state=np.array([0.0, 0.0])), self._traj_intent([0.0, 50.0]), None
        )
        assert passed is False
        assert "mission drift" in reason


class TestCheckHistory:
    def _index_skill(self, library, state, utility):
        fingerprint = hashlib.md5(state.tobytes()).hexdigest()[:12]
        library.index_skill(Skill(
            skill_id=f"s{len(library.skills)}", fingerprint=fingerprint,
            trajectory=None, utility_score=utility,
        ))

    def test_no_skill_library_passes(self):
        check = _make_check_history(None)
        passed, reason, _ = check(World(state=np.zeros(2)), IntentIR(), None)
        assert passed is True
        assert "no history check" in reason

    def test_low_utility_precedent_fails(self):
        library = SkillLibrary()
        state = np.array([1.0, 2.0])
        self._index_skill(library, state, 0.2)
        check = _make_check_history(library)
        passed, reason, _ = check(World(state=state), IntentIR(), None)
        assert passed is False
        assert "utility" in reason

    def test_positive_precedents_pass(self):
        library = SkillLibrary()
        state = np.array([1.0, 2.0])
        self._index_skill(library, state, 0.8)
        check = _make_check_history(library)
        passed, reason, _ = check(World(state=state), IntentIR(), None)
        assert passed is True
        assert "precedents positive" in reason


class TestCheckMission:
    def test_no_intent_passes(self):
        check = _make_check_mission()
        passed, reason, weight = check(World(state=np.zeros(2)), None, None)
        assert passed is True
        assert weight == 0.0

    def test_misaligned_explore_at_distance_fails(self):
        check = _make_check_mission()
        facts = DomainFacts(
            state=np.zeros(2), resources={"distance": 50.0}, constraints=[],
            events=[], metrics={},
        )
        intent = IntentIR(intent_type="explore", confidence=0.8)
        passed, reason, _ = check(World(state=np.zeros(2)), intent, facts)
        assert passed is False
        assert "mission misaligned" in reason

    def test_close_explore_passes(self):
        check = _make_check_mission()
        facts = DomainFacts(
            state=np.zeros(2), resources={"distance": 2.0}, constraints=[],
            events=[], metrics={},
        )
        intent = IntentIR(intent_type="explore", confidence=0.8)
        passed, reason, _ = check(World(state=np.zeros(2)), intent, facts)
        assert passed is True
        assert "mission aligned" in reason


class TestConstraintScript:
    def test_execute_clean(self):
        script = ConstraintScript([ConstraintOpcode.CHECK_NAN, ConstraintOpcode.CHECK_BOUNDS])
        passed, reason, weight = script.execute(
            World(state=np.zeros(4)),
            IntentIR(params={"action_vector": np.array([1.0, 0.0])}),
        )
        assert passed is True
        assert reason == "all checks passed"
        assert weight == pytest.approx(0.5)
        assert len(script.results) == 2

    def test_execute_reports_failure_reason(self):
        script = ConstraintScript([ConstraintOpcode.CHECK_NAN])
        passed, reason, _ = script.execute(
            World(state=np.array([np.nan, 0.0])), None
        )
        assert passed is False
        assert "NaN" in reason

    def test_results_records_opcodes(self):
        script = ConstraintScript([ConstraintOpcode.CHECK_NAN, ConstraintOpcode.CHECK_SAFETY])
        script.execute(World(state=np.zeros(2)), None)
        entries = script.results
        assert [e["opcode"] for e in entries] == ["check_nan", "check_safety"]
        assert all("passed" in e and "reason" in e and "weight" in e for e in entries)

    def test_from_opcode_names_filters_unknown(self):
        script = ConstraintScript.from_opcode_names(["CHECK_NAN", "NOT_A_REAL_OPCODE"])
        assert script.opcodes == [ConstraintOpcode.CHECK_NAN]

    def test_from_opcode_names_empty(self):
        script = ConstraintScript.from_opcode_names(["BOGUS"])
        assert script.opcodes == []
        passed, reason, _ = script.execute(World(state=np.zeros(2)), None)
        assert passed is True


class TestConstraintValidator:
    def test_name(self):
        assert ConstraintValidator().name == "ConstraintValidator"

    def test_no_intent_passes_neutral(self):
        sig = ConstraintValidator().validate(World(state=np.zeros(2)), None)
        assert sig.passed is True
        assert sig.confidence == 0.0
        assert sig.evidence_weight == 0.0

    def test_clean_intent_passes(self):
        world = World(state=np.zeros(2))
        intent = IntentIR(intent_type="move", confidence=0.8,
                          params={"action_vector": np.array([1.0, 0.0])})
        sig = ConstraintValidator().validate(world, intent)
        assert sig.passed is True
        assert sig.confidence == 0.95
        assert sig.evidence_weight == 0.2

    def test_low_safety_blocks(self):
        world = World(state=np.zeros(2), safety_score=0.1)
        intent = IntentIR(intent_type="move", confidence=0.8)
        sig = ConstraintValidator().validate(world, intent)
        assert sig.passed is False
        assert "below 0.3" in sig.reason
        assert sig.confidence == -0.9
        assert sig.metadata["violations"]

    def test_out_of_bounds_action_blocks(self):
        world = World(state=np.array([0.0, 0.0]))
        facts = DomainFacts(
            state=np.array([0.0, 0.0]), resources={},
            constraints=["world_bounds"], events=[], metrics={},
        )
        intent = IntentIR(intent_type="move", confidence=0.8,
                          params={"action_vector": np.array([-1.0, 0.0])})
        sig = ConstraintValidator().validate(world, intent, facts)
        assert sig.passed is False
        assert "out of bounds" in sig.reason

    def test_speed_violation_blocks(self):
        world = World(state=np.zeros(2))
        facts = DomainFacts(
            state=np.zeros(2), resources={},
            constraints=["max_velocity=2"], events=[], metrics={},
        )
        intent = IntentIR(intent_type="move", confidence=0.8,
                          params={"action_vector": np.array([5.0, 0.0])})
        sig = ConstraintValidator().validate(world, intent, facts)
        assert sig.passed is False
        assert "speed" in sig.reason

    def test_omega_other_widens_nothing_for_clean(self):
        # omega_vector only affects the drift path; a clean intent stays clean.
        sig = ConstraintValidator().validate(
            World(state=np.zeros(2)),
            IntentIR(intent_type="move", confidence=0.8),
            omega_vector={"other": 0.9},
        )
        assert sig.passed is True