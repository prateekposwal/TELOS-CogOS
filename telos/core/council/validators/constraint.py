import numpy as np
import logging
from enum import Enum
from typing import Optional, Any, List, Callable, Tuple
from telos.core.council.base import Validator, ValidationSignal
from telos.world.world import World
from telos.intent_ir import IntentIR
from telos.world.facts import DomainFacts

CheckFn = Callable[[World, Optional[IntentIR], Optional[DomainFacts]], Tuple[bool, str, float]]

class ConstraintOpcode(Enum):
    """Composable constraint opcodes for validator definitions."""
    CHECK_NAN = "check_nan"
    CHECK_BOUNDS = "check_bounds"
    CHECK_SAFETY = "check_safety"
    CHECK_DRIFT = "check_drift"
    CHECK_HISTORY = "check_history"
    CHECK_MISSION = "check_mission"


def _make_check_nan() -> CheckFn:
    def check(world, intent, domain_facts):
        issues = []
        state = getattr(world, 'state', None)
        if state is not None:
            nans = int(np.isnan(state).sum())
            if nans > 0:
                issues.append(f"state contains {nans} NaN values")
            infs = int(np.isinf(state).sum())
            if infs > 0:
                issues.append(f"state contains {infs} Inf values")
        action = None
        if intent is not None and hasattr(intent, 'params') and intent.params:
            action = intent.params.get("action_vector", None)
        if action is not None and isinstance(action, np.ndarray):
            if np.isnan(action).any():
                issues.append("proposed action contains NaN")
        if issues:
            return (False, " | ".join(issues), min(1.0, 0.3 + 0.2 * len(issues)))
        return (True, "state is clean (no NaN/Inf)", 0.3)
    return check


def _make_check_bounds() -> CheckFn:
    def check(world, intent, domain_facts):
        issues = []
        action = None
        if intent is not None and hasattr(intent, 'params') and intent.params:
            action = intent.params.get("action_vector", None)
        if action is not None and isinstance(action, np.ndarray):
            if np.linalg.norm(action) > 100.0:
                issues.append(f"proposed action norm {np.linalg.norm(action):.1f} exceeds 100")
        if domain_facts is not None and hasattr(domain_facts, 'constraints'):
            if "bounds" in domain_facts.constraints:
                issues.append("domain reports out-of-bounds state")
        if issues:
            return (False, " | ".join(issues), 0.5)
        return (True, "all bounds satisfied", 0.2)
    return check


def _make_check_safety() -> CheckFn:
    def check(world, intent, domain_facts):
        safety = getattr(world, 'safety_score', 1.0)
        if safety < 0.3:
            return (False, f"safety score {safety:.2f} below 0.3 threshold", 0.6)
        return (True, f"safety OK ({safety:.2f})", 0.2)
    return check


def _make_check_drift() -> CheckFn:
    def check(world, intent, domain_facts):
        drift = 0.0
        predicted = None
        if intent is not None and hasattr(intent, 'params') and intent.params:
            traj = intent.params.get("trajectory", None)
            if traj is not None:
                predicted = getattr(traj, 'state', None)
        observed = getattr(world, 'state', None)
        if predicted is not None and observed is not None:
            drift = float(np.linalg.norm(predicted - observed))
        if drift > 5.0:
            return (False, f"mission drift {drift:.2f} exceeds threshold", min(0.9, drift / 5.0))
        return (True, f"drift within bounds ({drift:.2f})", drift / 10.0)
    return check


def _make_check_history(skill_library=None) -> CheckFn:
    def check(world, intent, domain_facts):
        if skill_library is None or intent is None:
            return (True, "no history check (no skill library)", 0.1)
        relevant = []
        if hasattr(skill_library, 'find_relevant_skills'):
            relevant = skill_library.find_relevant_skills(
                getattr(world, 'state', None), threshold=0.3
            )
        if not relevant:
            return (True, "no contradictory historical evidence", 0.1)
        worst = min(relevant, key=lambda s: s.utility_score) if relevant else None
        if worst is not None and worst.utility_score < 0.3:
            return (False, f"historical skill {worst.skill_id} had utility {worst.utility_score:.2f}", 0.5)
        return (True, f"historical precedents positive (best utility={worst.utility_score:.2f})", 0.1)
    return check


def _make_check_mission() -> CheckFn:
    def check(world, intent, domain_facts):
        if intent is None:
            return (True, "no intent to check", 0.0)
        if domain_facts is not None and hasattr(domain_facts, 'resources'):
            distance = domain_facts.resources.get("distance", 0)
            if distance > 10 and getattr(intent, 'intent_type', '') == 'explore':
                return (False, f"mission misaligned: exploring at distance {distance:.1f}", 0.4)
        return (True, "mission aligned", 0.2)
    return check


# Opcode registry: maps opcode -> factory function
_OPCODE_REGISTRY = {
    ConstraintOpcode.CHECK_NAN: _make_check_nan,
    ConstraintOpcode.CHECK_BOUNDS: _make_check_bounds,
    ConstraintOpcode.CHECK_SAFETY: _make_check_safety,
    ConstraintOpcode.CHECK_DRIFT: _make_check_drift,
    ConstraintOpcode.CHECK_HISTORY: _make_check_history,
    ConstraintOpcode.CHECK_MISSION: _make_check_mission,
}


class ConstraintScript:
    """A composable list of constraint opcodes that can be executed as a validator.

    Instead of writing arbitrary Python code for each validator, define them
    as a list of opcodes. This provides:
      - Auditability: exactly which checks were run
      - Composability: mix and match opcodes
      - Safety: no arbitrary code execution

    Usage:
        script = ConstraintScript([CHECK_NAN, CHECK_BOUNDS])
        passed, reason, weight = script.execute(world, intent, domain_facts)
    """

    def __init__(self, opcodes: List, skill_library=None):
        self.opcodes = list(opcodes)
        self._skill_library = skill_library
        self._results = []

    def execute(self, world, intent, domain_facts=None):
        """Execute all opcodes in order. Returns (passed, combined_reason, combined_weight)."""
        self._results = []
        all_passed = True
        reasons = []
        total_weight = 0.0

        for opcode in self.opcodes:
            factory = _OPCODE_REGISTRY.get(opcode)
            if factory is None:
                reasons.append(f"unknown opcode {opcode}")
                continue

            if opcode == ConstraintOpcode.CHECK_HISTORY:
                check_fn = _make_check_history(self._skill_library)
            else:
                check_fn = factory()

            try:
                passed, reason, weight = check_fn(world, intent, domain_facts)
            except Exception as e:
                passed, reason, weight = False, f"opcode {opcode.value} error: {e}", 0.5

            self._results.append({
                "opcode": opcode.value,
                "passed": passed,
                "reason": reason,
                "weight": weight,
            })

            if not passed:
                all_passed = False
                reasons.append(reason)
            total_weight += weight

        combined_reason = " | ".join(reasons) if reasons else "all checks passed"
        return (all_passed, combined_reason, min(1.0, total_weight))

    @property
    def results(self):
        return list(self._results)

    @classmethod
    def from_opcode_names(cls, names, skill_library=None):
        """Create a script from string opcode names."""
        opcodes = []
        for name in names:
            try:
                opcodes.append(ConstraintOpcode[name])
            except KeyError:
                pass
        return cls(opcodes, skill_library=skill_library)





"""
Concrete Council Validators — Truth-Anchored Advisors

Each validator is a specialized cognitive process that performs one
kind of truth-check. They are NOT agents — they have no goals, no
autonomy, and no ability to act. They only output ValidationSignals.

If any validator returns passed=False, the Council blocks the
Decision Integrator from acting. This is how TELOS ensures
Epistemic Integrity: the system refuses to pursue a mission
when reality contradicts it.
"""


import numpy as np
import logging
from enum import Enum
from collections import Counter
from typing import Optional, Any, List, TYPE_CHECKING

from telos.core.council.base import Validator, ValidationSignal

if TYPE_CHECKING:
    from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR
from telos.core.ledger.skill_library import SkillLibrary

from typing import Callable, List as ListType

# Type alias for constraint check functions
CheckFn = Callable[[Any, Any, Any], tuple]

logger = logging.getLogger('telos_council_validators')

# ═══════════════════════════════════════════════════════════════════════════
# Bitcoin-inspired Limited Constraint Language for Validators
# ═══════════════════════════════════════════════════════════════════════════
#
# Instead of arbitrary Python code, validators can be defined as a list of
# composable constraint opcodes. Each opcode performs a single check.
#
# Opcodes:
#   CHECK_NAN      - Check for NaN/Inf values in state
#   CHECK_BOUNDS   - Check state/action bounds
#   CHECK_SAFETY   - Check safety thresholds
#   CHECK_DRIFT    - Check mission drift
#   CHECK_HISTORY  - Check historical precedents
#   CHECK_MISSION  - Check mission alignment
# ═══════════════════════════════════════════════════════════════════════════

class ConstraintValidator(Validator):
    """Verifies the planned action does not violate system constraints.

    Checks:
    1. Are there domain-specific constraints that block this action?
    2. Does the action respect safety thresholds?
    3. Does the action respect ethical boundaries (if defined)?

    This is the system's "conscience" — it enforces the rules
    that cannot be broken even for mission success.
    """

    @property
    def name(self) -> str:
        return "ConstraintValidator"

    def _check_action_against_constraints(
        self, world: World, intent: IntentIR, constraints: List[str]
    ) -> List[str]:
        violations = []
        action = intent.params.get("action_vector") if intent.params else None
        if action is None:
            return violations
        for c in constraints:
            if c.startswith("_"):
                continue
            next_state = world.state + action
            geometry_keywords = ("boundary", "bounds", "world_bounds", "wall")
            if any(kw in c.lower() for kw in geometry_keywords):
                if np.any(next_state < 0):
                    violations.append(f"domain constraint: {c} (action moves out of bounds)")
            elif "speed" in c.lower() or "velocity" in c.lower():
                speed = float(np.linalg.norm(action))
                limit = float(c.split("=")[-1]) if "=" in c else float("inf")
                if speed > limit:
                    violations.append(f"domain constraint: {c} (speed {speed:.2f} > limit {limit})")
            elif "energy" in c.lower() or "resource" in c.lower():
                violations.append(f"domain constraint: {c}")
        return violations

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O, widen drift tolerance during investigation
        drift_tolerance_mult = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            drift_tolerance_mult = 1.0 + 0.2 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        violations: List[str] = []

        if world.safety_score < 0.3:
            violations.append(f"safety score {world.safety_score:.2f} below 0.3 threshold")

        if domain_facts is not None and isinstance(domain_facts, DomainFacts):
            if domain_facts.constraints:
                violations.extend(
                    self._check_action_against_constraints(world, intent, domain_facts.constraints)
                )

        if violations:
            evidence_weight = min(1.0, 0.4 + 0.2 * len(violations))
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.9,
                reason=" | ".join(violations),
                evidence_weight=evidence_weight,
                metadata={"violations": violations},
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.95,
            reason="all constraints satisfied",
            evidence_weight=0.2,
        )
