"""
Verified skill acquisition (Phase 3) — no skill enters the library unverified.

Mirrors the write-side fix loop's rule (Λ2.3): "done" requires a verification
signal, not a self-reported score.
"""

import pytest

from telos.core.learning.acquisition import SkillAcquisition, SkillCandidate
from telos.core.ledger.skill_library import SkillLibrary


def _acq(**kwargs):
    lib = SkillLibrary(max_skills=50)
    return SkillAcquisition(lib, **kwargs), lib


def test_propose_does_not_acquire():
    """Proposing a candidate alone never indexes a skill."""
    acq, lib = _acq()
    acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    assert lib.skill_count == 0
    assert acq.acquired == 0
    assert acq.stats()["candidates"] == 1


def test_verify_below_floor_does_not_acquire():
    """An outcome below the verification floor does not acquire the skill."""
    acq, lib = _acq(min_outcome=0.6)
    c = acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    assert acq.verify(c.candidate_id, 0.4, cycle=2) is False
    assert lib.skill_count == 0
    assert acq.acquired == 0


def test_verify_at_or_above_floor_acquires():
    """An outcome at the floor acquires the skill into the library."""
    acq, lib = _acq(min_outcome=0.6)
    c = acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    assert acq.verify(c.candidate_id, 0.6, cycle=2) is True
    assert lib.skill_count == 1
    assert acq.acquired == 1
    assert acq.stats()["candidates"] == 0


def test_double_verify_is_idempotent():
    """A verified candidate cannot be acquired twice."""
    acq, lib = _acq()
    c = acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    assert acq.verify(c.candidate_id, 0.9, cycle=2) is True
    assert acq.verify(c.candidate_id, 0.9, cycle=3) is False
    assert lib.skill_count == 1


def test_custom_verifier_overrides_floor():
    """A custom verifier is consulted instead of the outcome floor."""
    acq, lib = _acq(verifier=lambda cand, outcome: outcome == 0.42)
    c = acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    assert acq.verify(c.candidate_id, 0.9, cycle=2) is False
    assert acq.verify(c.candidate_id, 0.42, cycle=3) is True
    assert lib.skill_count == 1


def test_unverified_candidates_retire_on_ttl():
    """Unverified candidates past their TTL are retired, not promoted."""
    acq, lib = _acq(candidate_ttl_cycles=5)
    acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    acq.retire(cycle=10)
    assert acq.stats()["candidates"] == 0
    assert acq.retired >= 1
    assert lib.skill_count == 0


def test_candidates_are_bounded():
    """Retained unverified candidates never exceed the bound."""
    acq, lib = _acq(max_candidates=10, candidate_ttl_cycles=10_000)
    for i in range(100):
        acq.propose(f"fp_{i}", {"intent": "navigate"}, cycle=i)
    assert acq.stats()["candidates"] <= 10


def test_verify_matching_by_fingerprint():
    """verify_matching verifies every candidate matching a fingerprint prefix."""
    acq, lib = _acq()
    acq.propose("fp_grid_a", {"intent": "navigate"}, cycle=1)
    acq.propose("fp_grid_b", {"intent": "collect"}, cycle=1)
    acq.propose("fp_other", {"intent": "wait"}, cycle=1)
    n = acq.verify_matching("fp_grid_", 0.9, cycle=2)
    assert n == 2
    assert lib.skill_count == 2


def test_verified_skill_carries_provenance():
    """The acquired skill records that it was verified, and when."""
    acq, lib = _acq()
    c = acq.propose("fp_a", {"intent": "navigate"}, cycle=1)
    acq.verify(c.candidate_id, 0.8, cycle=7)
    skill = next(iter(lib.skills.values()))
    assert skill.metadata["source"] == "verified_acquisition"
    assert skill.metadata["verified_cycle"] == 7
