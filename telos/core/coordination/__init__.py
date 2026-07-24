"""
Coordination — Multi-agent Supervisor for TELOS.

The PipelineCoordinator distributes complex intents across sub-pipelines,
then aggregates their Council verdicts and results into a single
coherent action.
"""

from telos.core.coordination.coordinator import PipelineCoordinator, SubPipelineConfig, CoordinationResult

__all__ = [
    "PipelineCoordinator",
    "SubPipelineConfig",
    "CoordinationResult",
]
