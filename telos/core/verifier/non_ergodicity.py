"""
Non-ergodicity of self-referential evidence — theorem + executable witness.

THEOREM (informal)
------------------
Let a system record, as evidence about an approach, every time governance
suppresses that approach before it can be tested. Then the suppressed approach
accumulates "failure" evidence from its own suppression, which raises its
dissent score, which causes more suppression: the state is an absorbing
attractor with zero escape probability (non-ergodic). If instead governance
suppression is classified as *not evidence about the approach*, the same
suppression leaves the evidence unchanged, escape probability stays positive,
and the system is ergodic.

This is exactly the ~30k-cycle DI=0.3 plateau TELOS experienced; the fix was
the canonical rule in `telos/core/governance/recovery_types.py`
("governance suppression is not evidence"). This module makes the theorem
executable two ways:

  1. `simulate(...)` — the abstract two-regime dynamics (fast, deterministic).
  2. `run_regime(...)` — the REAL MemoryAdvisor + FailureLedger, showing that
     the same governance block poisons the approach iff it is recorded with a
     non-suppression root cause.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import numpy as np

from telos.core.governance.recovery_types import GOVERNANCE_SUPPRESSION_REASONS

# The designed escape type the plateau trapped (see runtime stagnation recovery).
TARGET_APPROACH = "goal_seek_recovery"


def simulate(separate_suppression: bool, cycles: int = 100,
             threshold: float = 0.5, inc: float = 0.2,
             decay: float = 0.15, e0: float = 0.6) -> Dict[str, object]:
    """Abstract two-regime evidence dynamics.

    Args:
        separate_suppression: True applies the canonical separation (suppression
            is not evidence about the approach); False misattributes it.
        cycles: max cycles to simulate.
        threshold: evidence level at/above which the approach stays blocked.
        inc: evidence increment per misattributed suppression.
        decay: evidence decay per separated cycle.
        e0: starting evidence level (the plateau state, above threshold).

    Returns:
        dict with `escaped` (cycle or None) and `final_evidence`.
    """
    e = e0
    for c in range(1, cycles + 1):
        if e < threshold:
            return {"escaped": c, "final_evidence": e, "non_ergodic": False}
        # The approach is suppressed by governance this cycle.
        e = min(1.0, e + inc) if not separate_suppression else max(0.0, e - decay)
    return {"escaped": None, "final_evidence": e, "non_ergodic": True}


def run_regime(separate_suppression: bool, cycles: int = 50) -> Optional[int]:
    """Real-code witness: MemoryAdvisor + FailureLedger, two root-cause regimes.

    Each cycle attempts TARGET_APPROACH. Governance suppresses it. The only
    difference between regimes is the recorded `root_cause`: the separated
    regime records it as a governance-suppression reason (the canonical set),
    the misattributed regime records it as an approach failure.

    Args:
        separate_suppression: True uses a suppression root cause; False uses a
            non-suppression root cause (the pre-fix misattribution).
        cycles: max cycles.

    Returns:
        The cycle the approach finally executes, or None if never (trapped).
    """
    from telos.core.infra_manager.failure_ledger import FailureLedger, FailureRecord
    from telos.core.ledger.skill_library import SkillLibrary
    from telos.core.council.validators.memory import MemoryAdvisor
    from telos.world.world import World
    from telos.intent_ir import IntentIR

    suppressed_root = "governance_intervention"
    misattributed_root = "opponent_adaptation"
    assert suppressed_root in GOVERNANCE_SUPPRESSION_REASONS
    assert misattributed_root not in GOVERNANCE_SUPPRESSION_REASONS

    ledger = FailureLedger()
    advisor = MemoryAdvisor(SkillLibrary(), failure_ledger=ledger)
    world = World(state=np.zeros(4))

    # Prime the trap with one governance suppression of the approach — this is
    # the plateau state the system enters after its first veto. Whether that
    # veto poisons the approach depends ONLY on the recorded root cause.
    ledger.record_direct(FailureRecord(
        failure_id="seed", cycle=0, timestamp=time.time(),
        failure_type="council_block", severity=0.7,
        root_cause=suppressed_root if separate_suppression else misattributed_root,
        blocked_by=TARGET_APPROACH,
    ))

    for c in range(1, cycles + 1):
        intent = IntentIR(intent_type=TARGET_APPROACH, confidence=0.8)
        signal = advisor.validate(world, intent)
        if signal.passed:
            return c
        ledger.record_direct(FailureRecord(
            failure_id=f"f{c}", cycle=c, timestamp=time.time(),
            failure_type="council_block", severity=0.7,
            root_cause=suppressed_root if separate_suppression else misattributed_root,
            blocked_by=TARGET_APPROACH,
        ))
    return None


def analyze(cycles: int = 100) -> Dict[str, object]:
    """Run both regimes (abstract + real) and report the contrast.

    Args:
        cycles: simulation horizon.

    Returns:
        dict with abstract and real-regime results for both settings.
    """
    return {
        "misattributed": {
            "abstract": simulate(False, cycles=cycles),
            "real_escape_cycle": run_regime(False, cycles=min(cycles, 50)),
        },
        "separated": {
            "abstract": simulate(True, cycles=cycles),
            "real_escape_cycle": run_regime(True, cycles=min(cycles, 50)),
        },
    }


__all__ = ["simulate", "run_regime", "analyze", "TARGET_APPROACH"]
