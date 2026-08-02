"""
Standard pipeline factory — the canonical shape of the deliberation engine.

The Scale-Invariance Principle claims one deliberation law at every
granularity. This factory is the *shape* of that law: the exact pipeline
configuration used for any sub-task (micro), project (meso), or
meta-cognitive (macro) decision. Both the PipelineCoordinator (deliberate
recursion) and the ScaleVerifier (multi-scale verification) build from
this single factory, so the structure they verify is the structure they
run.
"""

from typing import List, Optional

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine


def build_standard_pipeline(name: str,
                            budget_ms: float = 30.0,
                            state_dim: int = 6,
                            n_worlds: int = 5,
                            horizon: int = 3,
                            streams: Optional[List[str]] = None,
                            simulator=None,
                            adapter=None) -> TelosV14Pipeline:
    """Build the canonical deliberation engine (same law at any scale).

    Args:
        name: Scope label for the pipeline.
        budget_ms: Compute budget — the scale knob (macro spends more).
        state_dim: Dimensionality of the state space.
        n_worlds: Counterfactual worlds per cycle.
        horizon: Planning horizon.
        streams: Which cognitive streams to register (reflex, perception,
                 memory, planning).
        simulator: Domain simulator (optional).
        adapter: Domain adapter (optional).

    Returns:
        A fully-assembled TelosV14Pipeline governed by the 9-phase law and
        the standard council constitution.
    """
    p_config = PipelineConfig(
        simulator=simulator,
        adapter=adapter,
        compute_budget_ms=budget_ms,
        state_dim=state_dim,
        n_worlds=n_worlds,
        horizon=horizon,
    )
    pipeline = TelosV14Pipeline(p_config)
    skill_lib = SkillLibrary()

    stream_map = {
        "reflex": lambda: ReflexStream(skill_lib),
        "perception": lambda: PerceptionStream(skill_lib),
        "memory": lambda: MemoryStream(skill_lib),
        "planning": lambda: PlanningStream(
            skill_lib,
            sim_engine=CounterfactualEngine(simulator) if simulator else None,
        ),
    }
    for s_name in (streams or ["reflex", "perception", "memory", "planning"]):
        factory = stream_map.get(s_name)
        if factory:
            pipeline.register_stream(factory())

    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    pipeline._scale_scope = name
    pipeline._scale_parent = "standard_factory"
    return pipeline


__all__ = ["build_standard_pipeline"]
