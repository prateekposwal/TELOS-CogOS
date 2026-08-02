"""
Coordination — Multi-agent Supervisor for TELOS.

The PipelineCoordinator distributes complex intents across sub-pipelines,
then aggregates their Council verdicts and results into a single
coherent action.

Deliberate recursion: the supervisor and every sub-pipeline run the
identical deliberation law (same 7-phase engine + axiom constitution).
Each recursive invocation is recorded in the coordinator's RecursionLedger
and audited by verify_scale_invariance() — the Scale-Invariance Principle
(telos.core.scale).
"""

from telos.core.coordination.coordinator import PipelineCoordinator, SubPipelineConfig, CoordinationResult

__all__ = [
    "PipelineCoordinator",
    "SubPipelineConfig",
    "CoordinationResult",
]
