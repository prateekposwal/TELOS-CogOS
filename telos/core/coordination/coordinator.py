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
from typing import Dict, List, Optional, Any, Callable, Tuple

import numpy as np

from telos.core.runtime import (
    TelosV14Pipeline, PipelineConfig, PipelineResult, PipelinePhase,
)
from telos.core.council.base import CouncilVerdict
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.infra_manager.checkpoint_manager import CheckpointManager
from telos.core.scale.principle import ScaleInvariancePrinciple
from telos.core.scale.ledger import RecursionLedger
from telos.core.scale.verifier import ScaleVerifier
from telos.core.scale.factory import build_standard_pipeline

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
    scale: str = "micro"  # granularity label (macro | meso | micro) — recorded in the recursion ledger


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


def _build_subpipeline(config: SubPipelineConfig,
                       simulator=None, adapter=None) -> TelosV14Pipeline:
    """Factory: build a minimal Pipeline for a sub-task.

    Delegates to the scale-invariance factory (telos.core.scale.factory) so
    the coordinator's sub-pipelines are the canonical shape of the
    deliberation law — the same engine at a smaller granularity.

    Args:
        config: the sub-pipeline configuration (name, budget, state dim, worlds).
        simulator: optional domain simulator for the sub-pipeline.
        adapter: optional domain adapter for the sub-pipeline.
    """
    return build_standard_pipeline(
        name=config.name,
        budget_ms=config.budget_ms,
        state_dim=config.state_dim,
        n_worlds=config.n_worlds,
        horizon=config.horizon,
        streams=config.streams,
        simulator=simulator,
        adapter=adapter,
    )


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
        # Scale-Invariance Principle (deliberate recursion): the supervisor and
        # every sub-pipeline run the identical deliberation law. The ledger makes
        # the recursion observable; the verifier asserts structural identity.
        self._scale_principle = ScaleInvariancePrinciple()
        self._recursion_ledger = RecursionLedger(owner="PipelineCoordinator",
                                                 principle=self._scale_principle)
        self._scale_verifier = ScaleVerifier(
            simulator=default_simulator,
            adapter=default_adapter,
            principle=self._scale_principle,
        )

    def on_subresult(self, callback: Callable) -> None:
        """Register callback fired after each sub-pipeline completes."""
        self._callbacks.append(callback)

    @staticmethod
    def _phase_signature(pipeline: TelosV14Pipeline) -> Tuple[str, ...]:
        """Ordered phase names a pipeline runs — its deliberation law."""
        return tuple(p.name for p in getattr(pipeline, '_phases', []) or [])

    def spawn(self, config: SubPipelineConfig) -> TelosV14Pipeline:
        """Create and register a sub-pipeline.

        Args:
            config: the sub-pipeline configuration to spawn.
        """
        pipeline = _build_subpipeline(
            config,
            simulator=self._default_simulator,
            adapter=self._default_adapter,
        )
        self._sub_pipelines[config.name] = pipeline
        # Deliberate recursion: tag the sub-pipeline as a recursive scope and
        # record the invocation in the self-similarity ledger.
        pipeline._scale_scope = config.name
        pipeline._scale_parent = "PipelineCoordinator"
        self._recursion_ledger.record(
            parent_scope="coordinator:spawn",
            scope=f"sub:{config.name}",
            scale=getattr(config, 'scale', 'micro'),
            kind="spawn",
            phase_signature=self._phase_signature(pipeline),
            success=True,
        )
        logger.info(f"Coordinator: spawned sub-pipeline '{config.name}' "
                    f"(scale={getattr(config, 'scale', 'micro')})")
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
                # Scale-invariance ledger: record the recursive execution.
                self._recursion_ledger.record(
                    parent_scope="supervisor:orchestrate",
                    scope=f"sub:{sub.name}",
                    scale=getattr(sub, 'scale', 'micro'),
                    kind="execute",
                    phase_signature=self._phase_signature(sub_pipeline),
                    axiom_ids=self._trace_axiom_ids(sub_result),
                    success=True,
                    decision_integrity=s_result.di,
                    mission_drift=s_result.md,
                    duration_ms=s_result.duration_ms,
                )

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
                # Kintsugi: record the failed recursion too — structure is still
                # checked, and the failure is preserved as a ledger asset.
                self._recursion_ledger.record(
                    parent_scope="supervisor:orchestrate",
                    scope=f"sub:{sub.name}",
                    scale=getattr(sub, 'scale', 'micro'),
                    kind="execute",
                    phase_signature=self._phase_signature(sub_pipeline),
                    axiom_ids=(),
                    success=False,
                    decision_integrity=0.0,
                    mission_drift=1.0,
                    duration_ms=round(dur, 1),
                )

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
                # The supervisor is the macro scale of the same deliberation
                # law — record it so both granularities are observable.
                self._recursion_ledger.record(
                    parent_scope="system",
                    scope="supervisor",
                    scale="macro",
                    kind="execute",
                    phase_signature=self._phase_signature(self._supervisor),
                    axiom_ids=self._trace_axiom_ids(sup_result),
                    success=sup_trace.council_validated is not False,
                    decision_integrity=sup_trace.decision_integrity,
                    mission_drift=sup_trace.mission_drift,
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
        """Chain: run sub-pipelines sequentially, each feeding state forward.

        Args:
            subtasks: the ordered list of sub-pipeline configurations to run.
            user_name: optional user identity passed through to each sub-pipeline.
        """
        current_state = state.copy()
        results = []

        for sub in subtasks:
            sub_pipeline = self._sub_pipelines.get(sub.name) or self.spawn(sub)
            st0 = time.time()
            sub_result = None
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
            # Scale-invariance ledger: chain steps are recursive invocations too.
            self._recursion_ledger.record(
                parent_scope="supervisor:chain",
                scope=f"sub:{sub.name}",
                scale=getattr(sub, 'scale', 'micro'),
                kind="execute",
                phase_signature=self._phase_signature(sub_pipeline),
                axiom_ids=self._trace_axiom_ids(sub_result) if sub_result is not None else (),
                success=s_result.success,
                decision_integrity=s_result.di,
                mission_drift=s_result.md,
                duration_ms=s_result.duration_ms,
            )
            results.append(s_result)

        return CoordinationResult(
            success=all(r.success for r in results),
            sub_results=results,
            selected_action=results[-1].action if results else None,
        )

    @staticmethod
    def _trace_axiom_ids(result) -> Tuple[str, ...]:
        """Sorted axiom ids verified for a PipelineResult's trace."""
        trace = getattr(result, 'decision_trace', None)
        results = getattr(trace, 'axiom_results', None)
        if not results:
            return ()
        return tuple(sorted(results.keys()))

    # ── Scale-Invariance Principle: deliberate recursion ────────────────────

    @property
    def scale_principle(self) -> ScaleInvariancePrinciple:
        """The scale-invariance invariant this coordinator embodies."""
        return self._scale_principle

    @property
    def recursion_ledger(self) -> RecursionLedger:
        """Self-similarity ledger of every recursive invocation."""
        return self._recursion_ledger

    @property
    def scale_verifier(self) -> ScaleVerifier:
        """Verifier that asserts structural identity across scales."""
        return self._scale_verifier

    def verify_scale_invariance(self) -> Dict:
        """Audit the deliberate-recursion invariant over all recorded
        invocations.

        Returns:
            Dict with invariant_holds, self_similarity, canonical phases,
            entry count, and a per-scale summary.
        """
        ledger = self.recursion_ledger
        return {
            "principle": self.scale_principle.name,
            "formal": self.scale_principle.formal,
            "invariant_holds": ledger.invariant_holds(),
            "self_similarity": round(ledger.self_similarity(), 4),
            "canonical_phases": list(self.scale_principle.canonical_phases),
            "entries": len(ledger.entries),
            "summary": ledger.summary(),
            "verifier": self.scale_verifier.__class__.__name__,
        }

    @property
    def stats(self) -> Dict:
        return {
            "sub_pipelines": len(self._sub_pipelines),
            "names": list(self._sub_pipelines.keys()),
            "recursive_invocations": len(self.recursion_ledger.entries),
            "self_similarity": round(self.recursion_ledger.self_similarity(), 4),
        }
