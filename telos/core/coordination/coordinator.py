"""
PipelineCoordinator — Multi-agent Supervisor pattern.

Distributes a complex intent into sub-tasks, spawns isolated sub-pipelines
for each, collects results, and aggregates Council verdicts.

Usage:
    coordinator = PipelineCoordinator(supervisor_pipeline)
    result = coordinator.orchestrate(
        intent="Play rock paper scissors against user",
        subtasks=[
            SubPipelineConfig(name="analyst", budget_ms=20.0),
            SubPipelineConfig(name="strategist", budget_ms=30.0),
        ],
        state=current_state,
    )
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

import numpy as np

from telos.core.runtime import (
    TelosV14Pipeline, PipelineConfig, PipelineResult, PipelinePhase,
)
from telos.core.council.base import CouncilVerdict
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.infra_manager.checkpoint_manager import CheckpointManager

logger = logging.getLogger('telos_coordinator')


@dataclass
class SubPipelineConfig:
    """Configuration for a single sub-pipeline."""
    name: str
    budget_ms: float = 30.0
    state_dim: int = 6
    n_worlds: int = 5
    horizon: int = 3
    streams: List[str] = field(default_factory=lambda: ["reflex", "perception", "memory", "planning"])
    user_name: Optional[str] = None


@dataclass
class SubResult:
    """Result from a single sub-pipeline execution."""
    name: str
    success: bool
    intent: Optional[str]
    action: Optional[np.ndarray]
    di: float
    md: float
    council_validated: bool
    duration_ms: float
    world_count: int
    error: Optional[str] = None


@dataclass
class CoordinationResult:
    """Aggregated result from all sub-pipelines."""
    success: bool
    sub_results: List[SubResult] = field(default_factory=list)
    aggregate_di: float = 1.0
    aggregate_md: float = 0.0
    all_council_validated: bool = True
    selected_action: Optional[np.ndarray] = None
    total_duration_ms: float = 0.0
    coordinator_verdict: Optional[CouncilVerdict] = None
    error: Optional[str] = None


def _default_subtask_splitter(intent: str) -> List[Dict]:
    """Default splitter: each word is a subtask (simple fallback)."""
    words = intent.strip().split()
    if len(words) <= 3:
        return [{"name": "primary", "prompt": intent}]
    chunk_size = max(1, len(words) // 2)
    return [
        {"name": f"part_{i}", "prompt": " ".join(words[i:i + chunk_size])}
        for i in range(0, len(words), chunk_size)
    ]


def _build_subpipeline(config: SubPipelineConfig,
                       simulator=None, adapter=None) -> TelosV14Pipeline:
    """Factory: build a minimal Pipeline for a sub-task."""
    p_config = PipelineConfig(
        simulator=simulator,
        adapter=adapter,
        compute_budget_ms=config.budget_ms,
        state_dim=config.state_dim,
        n_worlds=config.n_worlds,
        horizon=config.horizon,
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
    for s_name in config.streams:
        factory = stream_map.get(s_name)
        if factory:
            pipeline.register_stream(factory())

    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    return pipeline


class PipelineCoordinator:
    """Supervisor that distributes work across sub-pipelines.

    The coordinator owns the top-level Pipeline (which provides the
    meta-cognitive layer) and spawns isolated sub-pipelines for
    each sub-task.

    Patterns supported:
      - Fan-out: all sub-pipelines run in parallel (conceptually)
      - Chain: sub-pipelines run sequentially, feeding state forward
      - Supervisor: coordinator reviews and aggregates sub-results
    """

    def __init__(self,
                 supervisor: Optional[TelosV14Pipeline] = None,
                 default_simulator=None,
                 default_adapter=None,
                 checkpoint_path: Optional[str] = None):
        self._supervisor = supervisor
        self._default_simulator = default_simulator
        self._default_adapter = default_adapter
        self._checkpointer = CheckpointManager(
            path=checkpoint_path or ".telos_coord_checkpoints",
        ) if checkpoint_path else None
        self._sub_pipelines: Dict[str, TelosV14Pipeline] = {}
        self._callbacks: List[Callable] = []

    def on_subresult(self, callback: Callable) -> None:
        """Register callback fired after each sub-pipeline completes."""
        self._callbacks.append(callback)

    def spawn(self, config: SubPipelineConfig) -> TelosV14Pipeline:
        """Create and register a sub-pipeline."""
        pipeline = _build_subpipeline(
            config,
            simulator=self._default_simulator,
            adapter=self._default_adapter,
        )
        self._sub_pipelines[config.name] = pipeline
        logger.info(f"Coordinator: spawned sub-pipeline '{config.name}'")
        return pipeline

    def orchestrate(self,
                    state: np.ndarray,
                    subtasks: List[SubPipelineConfig],
                    user_name: Optional[str] = None) -> CoordinationResult:
        """Fan-out: run all sub-pipelines and aggregate results.

        Args:
            state: Current world state to distribute to all sub-pipelines
            subtasks: List of sub-pipeline configurations
            user_name: Optional user identity for identity memory

        Returns:
            Aggregated CoordinationResult with all sub-results.
        """
        t0 = time.time()
        results: List[SubResult] = []
        all_di = []
        all_md = []
        all_validated = True

        for sub in subtasks:
            # Get or create sub-pipeline
            sub_pipeline = self._sub_pipelines.get(sub.name)
            if not sub_pipeline:
                sub_pipeline = self.spawn(sub)

            # Run sub-pipeline
            st0 = time.time()
            try:
                sub_result = sub_pipeline.execute(
                    state.copy(), user_name=sub.user_name or user_name,
                )
                dur = (time.time() - st0) * 1000

                trace = sub_result.decision_trace
                s_result = SubResult(
                    name=sub.name,
                    success=True,
                    intent=trace.selected_intent.intent_type if trace and trace.selected_intent else None,
                    action=trace.selected_action if trace else None,
                    di=trace.decision_integrity if trace else 1.0,
                    md=trace.mission_drift if trace else 0.0,
                    council_validated=trace.council_validated if trace else True,
                    duration_ms=round(dur, 1),
                    world_count=trace.worlds_simulated if trace else 0,
                )
                all_di.append(s_result.di)
                all_md.append(s_result.md)
                if not s_result.council_validated:
                    all_validated = False

            except Exception as e:
                dur = (time.time() - st0) * 1000
                s_result = SubResult(
                    name=sub.name,
                    success=False,
                    intent=None,
                    action=None,
                    di=0.0,
                    md=1.0,
                    council_validated=False,
                    duration_ms=round(dur, 1),
                    world_count=0,
                    error=str(e),
                )
                all_validated = False
                logger.error(f"Coordinator: sub-pipeline '{sub.name}' failed: {e}")

            results.append(s_result)
            for cb in self._callbacks:
                try:
                    cb(s_result)
                except Exception:
                    logger.exception("Coordinator callback failed")

        # Aggregate: pick best action (highest DI sub), average DI/MD
        agg_di = sum(all_di) / len(all_di) if all_di else 0.0
        agg_md = sum(all_md) / len(all_md) if all_md else 0.0
        best_result = max(results, key=lambda r: r.di if r.success else -1) if results else None
        best_action = best_result.action if best_result and best_result.success else None

        total_dur = (time.time() - t0) * 1000

        # Supervisor verdict (if supervisor pipeline exists)
        supervisor_verdict = None
        if self._supervisor:
            sup_result = self._supervisor.execute(state.copy())
            sup_trace = sup_result.decision_trace
            if sup_trace:
                supervisor_verdict = CouncilVerdict(
                    validated=all_validated and sup_trace.council_validated,
                    decision_integrity=agg_di,
                    mission_drift=agg_md,
                )

        result = CoordinationResult(
            success=all_validated and best_action is not None,
            sub_results=results,
            aggregate_di=round(agg_di, 3),
            aggregate_md=round(agg_md, 3),
            all_council_validated=all_validated,
            selected_action=best_action,
            total_duration_ms=round(total_dur, 1),
            coordinator_verdict=supervisor_verdict,
        )

        # Checkpoint coordinator state — serialize real sub-pipeline data
        if self._checkpointer:
            try:
                # Serialize actual sub-pipeline state from all sub-pipelines
                sub_states = {}
                for name, sub in self._sub_pipelines.items():
                    sub_states[name] = {
                        "ledger": {
                            "user_profiles": {
                                pname: {
                                    "confidence": getattr(p, 'confidence', 0.5),
                                    "last_intent": getattr(p, 'last_intent', ''),
                                }
                                for pname, p in getattr(sub.ledger, '_user_profiles', {}).items()
                            },
                        },
                        "failures": {
                            "failures": [
                                {
                                    "cycle": getattr(f, 'cycle', 0),
                                    "type": getattr(f, 'failure_type', 'unknown'),
                                    "cause": getattr(f, 'root_cause', ''),
                                }
                                for f in getattr(getattr(sub, '_infra_manager', None), 'failures', getattr(sub, 'failures', type('obj', (), {'_failures': []})()))._failures[-50:]
                            ],
                        },
                        "policy": {
                            "risk_tolerance": sub._infra_manager.policy.current.risk_tolerance,
                            "exploration_budget": sub._infra_manager.policy.current.exploration_budget,
                            "ambition_level": sub._infra_manager.policy.current.ambition_level,
                            "drift_tolerance": sub._infra_manager.policy.current.drift_tolerance,
                            "recovery_mode": sub._infra_manager.policy.current.recovery_mode,
                        } if hasattr(sub, '_infra_manager') and hasattr(sub._infra_manager, 'policy') else {},
                        "cycle_count": getattr(sub, '_cycle_count', 0),
                    }
                cp_data = {
                    "sub_pipelines": sub_states,
                    "cycle_count": 0,
                }
                # Use first available ledger for world_ledger checkpoint
                first_sub = next(iter(self._sub_pipelines.values()), None)
                world_ledger = first_sub.ledger if first_sub else type('obj', (object,), {'_user_profiles': {}})()
                self._checkpointer.save(
                    cycle=0,
                    world_ledger=world_ledger,
                    skill_library=SkillLibrary(),
                    stream_calibrator=first_sub._infra_manager.calibrator if first_sub and hasattr(first_sub, '_infra_manager') else type('obj', (object,), {'_weights': {}, '_accuracy': {}, '_total_calls': {}})(),
                    failure_ledger=first_sub._infra_manager.failures if first_sub and hasattr(first_sub, '_infra_manager') else type('obj', (object,), {'_records': []})(),
                    mission_policy=first_sub._infra_manager.policy if first_sub and hasattr(first_sub, '_infra_manager') else type('obj', (object,), {'_risk_tolerance': 0.5, '_exploration_budget': 0.3, '_ambition': 0.7})(),
                    decision_trace=None,
                )
                # Also write sub-pipeline states to a sidecar file
                import json as _json
                cp_path = self._checkpointer._path / "sub_pipeline_states.json" if hasattr(self._checkpointer, '_path') else None
                if cp_path:
                    with open(str(cp_path), 'w') as _f:
                        _json.dump(cp_data, _f, indent=2, default=str)
            except Exception as e:
                logger.warning(f"Coordinator checkpoint failed: {e}")

        return result

    def chain(self,
              state: np.ndarray,
              subtasks: List[SubPipelineConfig],
              user_name: Optional[str] = None) -> CoordinationResult:
        """Chain: run sub-pipelines sequentially, each feeding state forward."""
        current_state = state.copy()
        results = []

        for sub in subtasks:
            sub_pipeline = self._sub_pipelines.get(sub.name) or self.spawn(sub)
            st0 = time.time()
            try:
                sub_result = sub_pipeline.execute(current_state, user_name=sub.user_name or user_name)
                dur = (time.time() - st0) * 1000
                trace = sub_result.decision_trace
                s_result = SubResult(
                    name=sub.name,
                    success=True,
                    intent=trace.selected_intent.intent_type if trace and trace.selected_intent else None,
                    action=trace.selected_action if trace else None,
                    di=trace.decision_integrity if trace else 1.0,
                    md=trace.mission_drift if trace else 0.0,
                    council_validated=trace.council_validated if trace else True,
                    duration_ms=round(dur, 1),
                    world_count=trace.worlds_simulated if trace else 0,
                )
                # Feed action forward as next state
                if s_result.action is not None:
                    current_state = current_state + s_result.action * 0.1
            except Exception as e:
                dur = (time.time() - st0) * 1000
                s_result = SubResult(
                    name=sub.name, success=False, intent=None,
                    action=None, di=0.0, md=1.0,
                    council_validated=False, duration_ms=round(dur, 1),
                    world_count=0, error=str(e),
                )
            results.append(s_result)

        return CoordinationResult(
            success=all(r.success for r in results),
            sub_results=results,
            selected_action=results[-1].action if results else None,
        )

    @property
    def stats(self) -> Dict:
        return {
            "sub_pipelines": len(self._sub_pipelines),
            "names": list(self._sub_pipelines.keys()),
        }
