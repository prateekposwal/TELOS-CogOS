"""Canonical recovery/attribution sets (telos/core/governance/recovery_types.py).

Single source of truth for the v7 attribution rule: governance suppression is
not evidence. Every consumer (stagnation armer, MemoryAdvisor, evidence
advisor) must read THESE sets, never local copies.
"""
from telos.core.governance.recovery_types import (
    STAGNATION_EXEMPT_INQUIRY_TYPES,
    STAGNATION_EXEMPT_RECOVERY_TYPES,
    GOVERNANCE_SUPPRESSION_REASONS,
)


def test_inquiry_set_contains_dwell_types():
    assert "blended_inquiry" in STAGNATION_EXEMPT_INQUIRY_TYPES
    assert "curiosity_explore" in STAGNATION_EXEMPT_INQUIRY_TYPES
    assert "perceive" in STAGNATION_EXEMPT_INQUIRY_TYPES


def test_recovery_set_contains_designed_escape():
    assert "goal_seek_recovery" in STAGNATION_EXEMPT_RECOVERY_TYPES


def test_suppression_reasons_complete():
    assert "governance_intervention" in GOVERNANCE_SUPPRESSION_REASONS
    assert "simulation_divergence" in GOVERNANCE_SUPPRESSION_REASONS


def test_consumers_share_the_canonical_sets():
    import telos.core.runtime as rt
    from telos.core.council.validators import evidence as ev
    from telos.core.council.validators import memory as mem
    # stagnation armer reads the canonical module
    assert rt.STAGNATION_EXEMPT_RECOVERY_TYPES == STAGNATION_EXEMPT_RECOVERY_TYPES
    # evidence advisor imports the same canonical set
    assert ev.STAGNATION_EXEMPT_RECOVERY_TYPES == STAGNATION_EXEMPT_RECOVERY_TYPES
    # memory advisor filters on the same suppression reasons
    assert mem.GOVERNANCE_SUPPRESSION_REASONS == GOVERNANCE_SUPPRESSION_REASONS
