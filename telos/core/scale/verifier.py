"""
ScaleVerifier — runs and verifies the deliberation law at multiple scales.

Mechanism half of the ScaleInvariancePrinciple: build a pipeline at each
granularity (macro / meso / micro), execute one deliberation cycle, and
assert that the same structure holds everywhere:

  - phase_sequence(P_s) is identical to the canonical law
  - axiom_set(P_s) is identical across scales (cross-scale equality)

Pipelines are built with the coordinator's own sub-pipeline factory
(_build_subpipeline) so verification exercises the exact construction the
PipelineCoordinator uses for deliberate recursion.
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from telos.core.runtime import TelosV14Pipeline
from telos.core.scale.principle import ScaleInvariancePrinciple, CANONICAL_PHASES
from telos.core.scale.factory import build_standard_pipeline

logger = logging.getLogger('telos_scale')


@dataclass
class ScaleConfig:
    """Configuration for one granularity of the deliberation law."""

    name: str                        # e.g. "macro" | "meso" | "micro"
    scale: str = "micro"             # granularity label recorded in the ledger
    budget_ms: float = 30.0
    n_worlds: int = 5
    horizon: int = 3
    streams: List[str] = field(default_factory=lambda: ["reflex", "perception", "memory", "planning"])


@dataclass
class ScaleReport:
    """Outcome of a multi-scale verification run."""

    scales: List[str]
    phase_signatures: Dict[str, Tuple[str, ...]]
    axiom_sets: Dict[str, Tuple[str, ...]]
    canonical_phases: Tuple[str, ...]
    invariant_holds: bool
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scales": self.scales,
            "phase_signatures": {k: list(v) for k, v in self.phase_signatures.items()},
            "axiom_sets": {k: list(v) for k, v in self.axiom_sets.items()},
            "canonical_phases": list(self.canonical_phases),
            "invariant_holds": self.invariant_holds,
            "violations": self.violations,
        }


class ScaleVerifier:
    """Runs pipelines at multiple scales and asserts structural identity.

    Usage:
        verifier = ScaleVerifier(simulator=sim, adapter=adapter)
        report = verifier.run([
            ScaleConfig(name="macro", scale="macro", budget_ms=60.0, n_worlds=8),
            ScaleConfig(name="meso",  scale="meso",  budget_ms=30.0, n_worlds=5),
            ScaleConfig(name="micro", scale="micro", budget_ms=12.0, n_worlds=3),
        ])
        assert report.invariant_holds
    """

    def __init__(self,
                 simulator=None,
                 adapter=None,
                 principle: Optional[ScaleInvariancePrinciple] = None,
                 pipeline_builder: Optional[Callable[[ScaleConfig], TelosV14Pipeline]] = None):
        self._simulator = simulator
        self._adapter = adapter
        self._principle = principle or ScaleInvariancePrinciple()
        self._pipeline_builder = pipeline_builder or self._default_builder

    # ── canonical structure helpers ────────────────────────────────────────

    @staticmethod
    def phase_signature(pipeline: TelosV14Pipeline) -> Tuple[str, ...]:
        """Ordered phase names executed by a pipeline (its deliberation law)."""
        return tuple(p.name for p in getattr(pipeline, '_phases', []) or [])

    @staticmethod
    def axiom_signature(trace) -> Tuple[str, ...]:
        """Sorted axiom ids verified for a cycle's trace (its axiom_set)."""
        results = getattr(trace, 'axiom_results', None)
        if not results:
            return ()
        return tuple(sorted(results.keys()))

    # ── construction ───────────────────────────────────────────────────────

    def _default_builder(self, config: ScaleConfig) -> TelosV14Pipeline:
        """Build the canonical deliberation engine via the scale factory —
        the exact factory the PipelineCoordinator uses for recursion.

        Args:
            config: the scale configuration to build the engine from.
        """
        return build_standard_pipeline(
            name=config.name,
            budget_ms=config.budget_ms,
            n_worlds=config.n_worlds,
            horizon=config.horizon,
            streams=config.streams,
            simulator=self._simulator,
            adapter=self._adapter,
        )

    def build(self, config: ScaleConfig) -> TelosV14Pipeline:
        return self._pipeline_builder(config)

    # ── verification ───────────────────────────────────────────────────────

    def verify_pipeline(self, pipeline: TelosV14Pipeline) -> Tuple[bool, str]:
        """Verify a single pipeline against the canonical law (structure only)."""
        sig = self.phase_signature(pipeline)
        if not self._principle.matches_phases(sig):
            return False, f"phase signature {sig} != canonical {CANONICAL_PHASES}"
        return True, "ok"

    def run(self, configs: List[ScaleConfig]) -> ScaleReport:
        """Execute one deliberation cycle at each scale and compare structure.

        Args:
            configs: the ordered list of scale configurations (macro/meso/micro)
                to build and verify.
        """
        signatures: Dict[str, Tuple[str, ...]] = {}
        axiom_sets: Dict[str, Tuple[str, ...]] = {}
        violations: List[str] = []

        for cfg in configs:
            pipeline = self.build(cfg)
            sig = self.phase_signature(pipeline)
            signatures[cfg.name] = sig
            ok, reason = self.verify_pipeline(pipeline)
            if not ok:
                violations.append(f"{cfg.name}: {reason}")

            # Execute one full cycle at this scale (state_dim 2 → simple state)
            state = np.array([1.0, 1.0])
            try:
                result = pipeline.execute(state.copy())
                trace = getattr(result, 'decision_trace', None)
                axiom_sets[cfg.name] = self.axiom_signature(trace)
            except Exception as e:  # noqa: BLE001 — report, don't crash verification
                logger.warning(f"Scale '{cfg.name}' execution failed: {e}")
                violations.append(f"{cfg.name}: execution failed: {e}")
                axiom_sets[cfg.name] = ()

        # Cross-scale axiom equality: every scale must verify the same axiom set
        axiom_scale_sets = [s for s in axiom_sets.values() if s]
        if axiom_scale_sets:
            reference = axiom_scale_sets[0]
            for name, a_set in axiom_sets.items():
                if a_set and a_set != reference:
                    violations.append(
                        f"{name}: axiom set differs from reference "
                        f"({len(a_set)} vs {len(reference)})"
                    )

        invariant_holds = len(violations) == 0
        return ScaleReport(
            scales=[c.name for c in configs],
            phase_signatures=signatures,
            axiom_sets=axiom_sets,
            canonical_phases=self._principle.canonical_phases,
            invariant_holds=invariant_holds,
            violations=violations,
        )


__all__ = ["ScaleConfig", "ScaleReport", "ScaleVerifier"]
