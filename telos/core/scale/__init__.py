"""
Scale — deliberate recursion (Scale-Invariance Principle).

TELOS applies the same deliberation law at every granularity: a sub-task
decision (micro), a project decision (meso), and the meta-cognitive
"which project next" decision (macro) all run the identical pipeline
phases governed by the identical axiom constitution.

Modules:
  - principle.py: ScaleInvariancePrinciple — the formal invariant
  - ledger.py:    RecursionLedger — records recursive invocations so
                  recursion is deliberate and observable
  - factory.py:   build_standard_pipeline — the canonical shape of the
                  deliberation engine at any scale (used by the coordinator)
  - verifier.py:  ScaleVerifier — runs the pipeline at multiple scales
                  and asserts the same structure holds

This package is the deliberate-recursion embodiment of Axiom 1.1
(Architecture Produces Outcomes), wired into the PipelineCoordinator.
"""

from telos.core.scale.principle import (
    ScaleInvariancePrinciple,
    CANONICAL_PHASES,
    CANONICAL_AXIOM_COUNT,
)
from telos.core.scale.ledger import RecursionLedger, RecursionEntry
from telos.core.scale.factory import build_standard_pipeline
from telos.core.scale.verifier import ScaleVerifier, ScaleConfig, ScaleReport

__all__ = [
    "ScaleInvariancePrinciple",
    "CANONICAL_PHASES",
    "CANONICAL_AXIOM_COUNT",
    "RecursionLedger",
    "RecursionEntry",
    "build_standard_pipeline",
    "ScaleVerifier",
    "ScaleConfig",
    "ScaleReport",
]
