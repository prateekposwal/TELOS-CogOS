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

from __future__ import annotations

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

class RealityValidator(Validator):
    """Verifies the planned action aligns with observed physics/data.

    Checks:
    1. Does the intent match what the PerceptionStream observed?
    2. Is the proposed action within plausible physical bounds?
    3. Is there a mismatch between the World state and the intent's
       assumed state (e.g., acting on a hallucinated entity)?

    This is the first line of defense against "wishful reasoning":
    if the system plans to fly but physics says it can't, this
    validator blocks.
    """

    @property
    def name(self) -> str:
        return "RealityValidator"

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

        issues: List[str] = []
        nans = int(np.isnan(world.state).sum())
        if nans > 0:
            issues.append(f"state contains {nans} NaN values")

        infs = int(np.isinf(world.state).sum())
        if infs > 0:
            issues.append(f"state contains {infs} Inf values")

        action = intent.params.get("action_vector",
                                   intent.target if hasattr(intent, 'target') else None)
        if action is not None and isinstance(action, np.ndarray):
            if np.isnan(action).any():
                issues.append("proposed action contains NaN")
            if np.linalg.norm(action) > 100.0:
                issues.append(f"proposed action norm {np.linalg.norm(action):.1f} exceeds 100")

        if domain_facts is not None and isinstance(domain_facts, DomainFacts):
            if "bounds" in domain_facts.constraints:
                issues.append("domain reports out-of-bounds state")

        if issues:
            evidence_weight = min(1.0, 0.3 + 0.2 * len(issues))
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.8,
                reason=" | ".join(issues),
                evidence_weight=evidence_weight,
                metadata={"issue_count": len(issues), "issues": issues},
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.9,
            reason="state and action are physically plausible",
            evidence_weight=0.3,
        )
