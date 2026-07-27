"""
TELOS v14: Pure Reasoning Pipeline with Council + Governance

The Runtime is the stateless orchestration engine. It coordinates
Cognitive Streams, Counterfactual Simulation, Representation Planning,
the Council of Cognitive Advisors, and the Governance Layer to produce
coherent, truth-anchored, governed decisions.

Governance Integration:
  Between the World (knowledge) and Streams (consumers), the Governance
  Layer filters what information is exposed based on mission context,
  timing readiness, and stream authorization. After the Council validates,
  the Decision Firewall performs a final reality audit before action.
"""

import time
import numpy as np
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('telos_pipeline')

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter
from telos.core.attention import BudgetManager
from telos.core.attention.projection import AttentionProjectionEngine, AttentionAllocation
from telos.core.attention.identity_entropy import IdentityEntropyTracker
from telos.core.decision.commitment_optimizer import CommitmentOptimizer
from telos.core.decision.omega_threshold import OmegaThresholdLearner
from telos.core.decision.cognitive_momentum import CognitiveMomentum
from telos.core.accounting.resource_accounting import ResourceAccountingLayer, ResourceCost
from telos.core.pipeline_builder import build_components
from telos.core.pipeline_finalize import run_axiom_prover, run_v2_module_hooks, record_resource_accounting
from telos.core.session.agents_writer import write_handoff
from telos.core.session.agents_reader import inject_into_context
from telos.core.project.substrate import ProjectPortfolio
from telos.core.project.rational_abandonment import AbandonmentGate
from telos.core.project.strategic_coherence import StrategicCoherence
from telos.core.project.method import MethodRegistry
from telos.core.identity.mission import MissionPortfolio
from telos.core.identity.mission_arbitration import MissionArbiter
from telos.core.identity.mission_lifecycle import MissionLifecycleEngine
from telos.core.identity.system_self import IdentityCore
from telos.core.streams.implementations import TheoryStream
from telos.core.resource.gradient import ResourceGradientTracker
from telos.core.streams.base import CognitiveStream
from telos.core.simulation import CounterfactualEngine, StrategicOption
from telos.core.planner import RepresentationPlanner
from telos.core.meta_cognition import MetaCognitionModule, MetaState
from telos.core.uncertainty.tripartite import TripartiteUncertainty
from telos.core.reasoning.relational import RelationalContext
from telos.core.representation_selector import RepresentationSelector
from telos.core.council.base import Council, CouncilVerdict, ValidationSignal
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.governance.trust_manager import TrustManager
from telos.core.governance.timing import InformationReadinessEngine, ReadinessCondition
from telos.core.governance.firewall import DecisionFirewall, FirewallConfig
from telos.core.governance.human_gateway import HumanGateway
from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
from telos.core.context.summarizer import ContextSummarizer
from telos.core.context.tiered import TieredContext
from telos.core.genesis import ANCHOR
from telos.core.attention.token_budget import TokenBudgetManager
from telos.core.ui.status import ThinkingDisplay
from telos.core.infra_manager.checkpoint_manager import CheckpointManager
from telos.core.observability.telemetry import TelemetryCollector
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
from telos.core.perception.quality import PerceptionQuality, QualityReport
from telos.core.perception.gate import ResolutionGate, GateVerdict
from telos.core.perception.proxy import ProxyStream
from telos.core.perception.explainer import PerceptionExplainer
from telos.core.perception.capabilities import CapabilityRegistry
from telos.core.phases.base import Phase, PhaseContext, StreamActivation
from telos.core.phases import (
    PerceivePhase, StreamPhase, SimulatePhase,
    EvaluatePhase, SynthesisPhase, SelectPhase, CouncilPhase, ActPhase,
)
from telos.core.mempool import DecisionMempool
from telos.core.types import (
    PipelinePhase, PipelineConfig, PipelineResult, DecisionTrace,
)
from telos.core.trace_builder import build_trace
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.planning_horizon import PlanningHorizon
from telos.core.curiosity.drive import CuriosityDrive
from telos.intent_ir import IntentIR


# ── Telos v2: New architectural components (July 2026) ──
from telos.core.council.reflector import CouncilReflector
from telos.core.meta.error_attribution import ErrorAttributionEngine
from telos.core.verifier.axiom_prover import AxiomProver
from telos.core.curiosity.assumption_auditor import AssumptionAuditor
from telos.core.identity.utility_profiles import IdentityUtilityEngine
from telos.core.introspection.scheduler import IntrospectionScheduler, IntrospectionTier
from telos.core.memory.regret_memory import RegretMemory
from telos.core.reasoning.theory_builder import TheoryBuilder
from telos.core.axioms.evolution import AxiomEvolutionEngine
from telos.core.reasoning.interpretation_engine import InterpretationEngine
# ── Telos v2.5: New architectural components (Prateek feedback — July 2026) ──
from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector
from telos.core.reasoning.model_competition import ModelCompetition
from telos.core.decision.time_horizon import TimeHorizonSeparator
from telos.core.attention.surprise_budget import SurpriseBudget
from telos.core.memory.active_forgetting import ActiveForgetting
from telos.core.council.internal_debate import InternalDebate
from telos.core.energy.cognitive_energy import CognitiveEnergy
from telos.core.confidence.dual_confidence import DualConfidence
from telos.core.identity.identity_compression import IdentityCompression
from telos.core.knowledge.explanation_compression import ExplanationCompression



class TelosV14Pipeline:
    """The TELOS Pure Reasoning Pipeline with Epistemic Integrity.

    Architecture:
        1. Perceive:   Ingest raw state → build World → extract DomainFacts
        2. Streams:    Each CognitiveStream processes World → produces IntentIR
        3. Simulate:   CounterfactualEngine generates and evaluates futures
        4. Evaluate:   Rank intents by utility + budget feasibility
        5. Select:     Choose best intent
        6. COUNCIL:    Route through Council of Advisors — may BLOCK action
        7. Act:        Convert selected intent to action via adapter

    The Council is BLOCKING: if any validator returns passed=False, the
    Pipeline refuses to act. The dissent is not just "heard" — it prevents
    action until the system can resolve the contradiction.

    Learning is NOT here. An external ExperienceManager observes
    PipelineResult and handles skill indexing / memory promotion.
    """

    def __init__(self, config: Optional[PipelineConfig] = None,
                 human_gateway: Optional[HumanGateway] = None):
        self.config = config or PipelineConfig()
        self._human_gateway = human_gateway
        self.budget_manager = BudgetManager(self.config.compute_budget_ms)
        self.streams: List[CognitiveStream] = []
        self.council = Council()
        self.ledger = WorldLedger()
        self.planning_horizon = PlanningHorizon()
        self._trust_manager = TrustManager()
        self._readiness = InformationReadinessEngine()
        self._firewall = DecisionFirewall()
        self._infra_manager = InfrastructureManager(domain=getattr(self.config.adapter, 'name', 'gridworld'))
        # B3: Register callbacks for council blocks and recovery events
        self._infra_manager.on_council_block(self._on_council_block)
        self._infra_manager.on_recovery_event(self._on_recovery_event)
        self._cycle_count: int = 0
        self._creator_present: bool = False
        self._perception_quality = PerceptionQuality()
        self._resolution_gate = ResolutionGate(threshold=self.config.quality_threshold)
        self._perception_explainer = PerceptionExplainer()
        self._capability_registry = CapabilityRegistry()
        self._last_quality_report: Optional[QualityReport] = None
        # P0 D8: Meta-cognition module
        self._meta_cognition = MetaCognitionModule()
        # P0 D9: Dynamic representation selector (also in evaluate phase)
        self._rep_selector = RepresentationSelector()

        self._sim_engine: Optional[CounterfactualEngine] = None
        self._planner: Optional[RepresentationPlanner] = None
        self._checkpointer: Optional[CheckpointManager] = None
        self._telemetry = TelemetryCollector()
        self._skill_library = SkillLibrary(
            max_skills=self.config.experience_max_skills,
        )
        self._experience_manager = ExperienceManager(
            self._skill_library,
            ExperienceConfig(
                utility_threshold=self.config.experience_utility_threshold,
                index_interval=self.config.experience_index_interval,
                max_skills=self.config.experience_max_skills,
            ),
        )
        self._prev_uncertainty: float = 0.0
        self._last_sim_score: float = 0.0
        self._last_predicted_state = None
        self._carryover_budget: float = 0.0
        self._context_summarizer = ContextSummarizer(ollama_chat_fn=self._default_ollama_chat)
        self._token_budget = TokenBudgetManager()
        self._display = ThinkingDisplay(enabled=self.config.debug)

        self._mempool = DecisionMempool(max_pending=100)
        self._prev_trace_id: Optional[str] = None
        self._decision_timelocks: Dict[str, int] = {}
        self._phases = self._build_phases()

        # ── Build all components via pipeline_builder ──
        comps = build_components(self.config, self._infra_manager, self._skill_library)
        self._attention_engine = comps['attention_engine']
        self._identity_entropy = comps['identity_entropy']
        self._tripartite_u = comps['tripartite_u']
        self._commitment_optimizer = comps['commitment_optimizer']
        self._resource_gradient_tracker = comps['resource_gradient_tracker']
        self._omega_threshold_learner = comps['omega_threshold_learner']
        self._curiosity_drive = comps['curiosity_drive']
        self._axiom_prover = comps['axiom_prover']

        # v2 modules
        self._interpretation_engine = comps['interpretation_engine']
        self._axiom_evolution = comps['axiom_evolution']
        self._theory_builder = comps['theory_builder']
        self._cognitive_momentum = comps['cognitive_momentum']
        self._regret_memory = comps['regret_memory']
        self._introspection_scheduler = comps['introspection_scheduler']
        self._identity_utility = comps['identity_utility']
        self._assumption_auditor = comps['assumption_auditor']
        self._error_attribution = comps['error_attribution']
        self._council_reflector = comps['council_reflector']
        self._internal_debate = comps['internal_debate']

        # v2.5 modules
        self._unknown_unknown_detector = comps['unknown_unknown_detector']
        self._model_competition = comps['model_competition']
        self._time_horizon = comps['time_horizon']
        self._surprise_budget = comps['surprise_budget']
        self._active_forgetting = comps['active_forgetting']
        self._cognitive_energy = comps['cognitive_energy']
        self._dual_confidence = comps['dual_confidence']
        self._identity_compression = comps['identity_compression']
        self._explanation_compression = comps['explanation_compression']
        self._resource_accounting = comps['resource_accounting']
        self._project_portfolio = ProjectPortfolio()
        self._abandonment_gate = AbandonmentGate()
        self._strategic_coherence = StrategicCoherence()
        self._method_registry = MethodRegistry()
        self._identity_core = IdentityCore()
        self._mission_portfolio = MissionPortfolio()
        self._mission_arbiter = MissionArbiter()
        self._mission_lifecycle = MissionLifecycleEngine()

        if self.config.checkpoint_path:
            self._checkpointer = CheckpointManager(
                path=self.config.checkpoint_path,
                max_checkpoints=self.config.checkpoint_max,
            )

        if self.config.simulator:
            self._sim_engine = CounterfactualEngine(
                self.config.simulator,
                seed=self.config.deterministic_seed,
            )
            self._planner = RepresentationPlanner(self.budget_manager)

        if self.config.checkpoint_path and self._checkpointer:
            cp = self._checkpointer.load()
            if cp:
                self._checkpointer.restore(self, cp)
                if hasattr(cp, 'omega_threshold_learner_data') and cp.omega_threshold_learner_data:
                    try:
                        self._omega_threshold_learner = OmegaThresholdLearner.from_dict(
                            cp.omega_threshold_learner_data
                        )
                        logger.info(f"OmegaThresholdLearner restored from checkpoint "
                                     f"({len(self._omega_threshold_learner.buckets)} buckets)")
                    except Exception as e:
                        logger.warning(f"OmegaThresholdLearner restore failed: {e}")
                else:
                    raw_dict = getattr(cp, '_raw', None) or {}
                    otl_data = raw_dict.get('omega_threshold_learner')
                    if otl_data:
                        try:
                            self._omega_threshold_learner = OmegaThresholdLearner.from_dict(otl_data)
                        except Exception:
                            pass

        if self.config.knowledge_path:
            self._infra_manager.knowledge.load(self.config.knowledge_path)

        if self.config.identity_path:
            self._infra_manager.system_self.load(self.config.identity_path)

        if self.config.ledger_path:
            self.ledger.load(self.config.ledger_path)

        if self.config.pattern_path:
            from telos.core.phases.reflect import ReflectPhase
            for phase in self._phases:
                if isinstance(phase, ReflectPhase):
                    try:
                        phase.pattern_library.load(self.config.pattern_path)
                    except Exception as e:
                        logger.warning(f"PatternLibrary load failed: {e}")

        if self.config.adapter and hasattr(self.config.adapter, 'initialize'):
            self.config.adapter.initialize()

        # Cross-session learning: load previous session context
        inject_into_context(self)

    def register_stream(self, stream: CognitiveStream) -> None:
        self.streams.append(stream)
        self.streams.sort(key=lambda s: s.priority, reverse=True)
        # P1.4: Auto-register with trust manager so auth checks work
        bypass = stream.priority > 0.9
        self._trust_manager.register_stream(
            stream_name=stream.__class__.__name__,
            can_bypass_readiness=bypass,
        )

    def register_validator(self, validator) -> None:
        """Register a Council advisor."""
        self.council.register(validator)

    def configure_governance(self, trust_manager: Optional[TrustManager] = None,
                              readiness: Optional[InformationReadinessEngine] = None,
                              firewall: Optional[DecisionFirewall] = None) -> None:
        """Inject governance components. If None, defaults are used."""
        if trust_manager is not None:
            self._trust_manager = trust_manager
        if readiness is not None:
            self._readiness = readiness
        if firewall is not None:
            self._firewall = firewall

    def _build_phases(self) -> List[Phase]:
        from telos.core.phases.reflect import ReflectPhase
        return [
            PerceivePhase(),
            StreamPhase(),
            SimulatePhase(),
            EvaluatePhase(),
            SynthesisPhase(),
            SelectPhase(),
            CouncilPhase(),
            ActPhase(),
            ReflectPhase(),
        ]

    @property
    def trust_manager(self) -> TrustManager:
        return self._trust_manager

    @property
    def readiness_engine(self) -> InformationReadinessEngine:
        return self._readiness

    @property
    def firewall(self) -> DecisionFirewall:
        return self._firewall

    @property
    def infra_manager(self) -> 'InfrastructureManager':
        return self._infra_manager

    @property
    def human_gateway(self) -> Optional[HumanGateway]:
        return self._human_gateway

    @property
    def telemetry(self) -> TelemetryCollector:
        return self._telemetry

    @property
    def pattern_library(self):
        """Access the ReflectPhase's PatternLibrary for cross-domain queries."""
        from telos.core.phases.reflect import ReflectPhase
        for phase in self._phases:
            if isinstance(phase, ReflectPhase):
                return phase.pattern_library
        return None

    @property
    def checkpointer(self) -> Optional[CheckpointManager]:
        return self._checkpointer

    def query_options(self, min_score: Optional[float] = None,
                      top_k: Optional[int] = None) -> List[StrategicOption]:
        """Query alternative future trajectories (Axiom 4.3: Possibility Preservation).

        Args:
            min_score: Only return options with score >= min_score
            top_k: Only return the top-k options

        Returns:
            List of StrategicOptions from the last simulation cycle.
        """
        if self._sim_engine is None:
            return []
        return self._sim_engine.query_options(min_score=min_score, top_k=top_k)

    def _default_ollama_chat(self, messages) -> str:
        """Default no-op chat function when no LLM is configured."""
        return '{}'


    # ── Bitcoin-inspired Decision Timelocks ──────────────────────────────────
    def _apply_timelock_penalties(self, ctx) -> None:
        """Deprioritize intent types that were selected within the timelock window.
        
        Prevents flip-flopping between competing intents.
        Called during pipeline execution, after EVALUATE and before SELECT phase.
        """
        timelock_window = getattr(self.config, 'timelock_window_cycles', 3)
        now = ctx.cycle_count
        new_intents = []
        for intent, weight in ctx.intents:
            intent_type = intent.intent_type
            last_selected = self._decision_timelocks.get(intent_type)
            if last_selected is not None:
                cycles_since = now - last_selected
                if cycles_since < timelock_window:
                    # Linear penalty: more recent = stronger penalty
                    penalty = 1.0 - (1.0 - cycles_since / timelock_window) * 0.5
                    new_weight = weight * max(0.1, penalty)
                    logger.info(
                        f"Timelock active for {intent_type} — {cycles_since} cycles since last selection, "
                        f"penalty={penalty:.3f}, weight: {weight:.3f}→{new_weight:.3f}"
                    )
                    new_intents.append((intent, new_weight))
                    continue
            new_intents.append((intent, weight))
        ctx.intents = new_intents
    
    def _record_timelock(self, ctx, selected_intent) -> None:
        """Record the selected intent type for future timelock checks."""
        intent_type = selected_intent.intent_type
        self._decision_timelocks[intent_type] = ctx.cycle_count
        # Store timelock state for DecisionTrace
        ctx._intent_timelock_state = {
            'intent_type': intent_type,
            'cycles_since_last_selection': 0,
            'timelock_active': False,
            'all_timelocks': dict(self._decision_timelocks),
        }

    def _compute_resource_budgets(self, ctx) -> dict:
        """Compute resource budgets from available data (called before Evaluate phase).
        
        Returns a dict with energy, memory, identity (partial), and recovery budgets.
        Fallback data is available early; full identity/recovery data is enriched later.
        """
        identity_stability = 1.0 - getattr(self._identity_entropy, 'collapse_rate', 0.0)
        budgets = {
            "energy": {
                "consumed_ms": self.budget_manager.consumed_ms,
                "total_ms": self.budget_manager.total_budget_ms,
                "utilization": self.budget_manager.consumed_ms / max(self.budget_manager.total_budget_ms, 1),
                "description": "compute_budget_ms consumed this cycle",
            },
            "memory": {
                "trace_history_length": ctx.cycle_count,
                "description": "trace_history length (number of stored traces)",
            },
            "identity": {
                "identity_entropy": 1.0 - identity_stability,
                "identity_stability": identity_stability,
                "description": "identity entropy (1 - identity_stability)",
            },
            "recovery": {
                "recovery_mode_cycles": 0,
                "current_state": "unknown",
                "description": "number of recovery_mode cycles active (populated post-Act)",
            },
        }
        return budgets

    def _ensure_proxy_stream(self, has_visual_input: bool = False) -> None:
        if not has_visual_input:
            return
        has_proxy = any(isinstance(s, ProxyStream) for s in self.streams)
        if not has_proxy:
            from telos.core.ledger.skill_library import SkillLibrary
            skill_lib = SkillLibrary()
            proxy = ProxyStream(skill_lib)
            self.register_stream(proxy)
            logger.info("[Proxy] Auto-registered ProxyStream — quality below threshold")

    def _on_council_block(self, block_info: dict) -> None:
        logger.warning(
            f"[Callback] Council blocked by {block_info.get('blocking_validator', 'unknown')} "
            f"— DI={block_info.get('di', 0):.3f}"
        )

    def _on_recovery_event(self, event_type: str) -> None:
        logger.info(f"[Callback] Recovery event: {event_type}")

    def assess_perception(self, frame_width: int, frame_height: int,
                           target_px: Optional[float] = None,
                           detection_streams: Optional[List[str]] = None
                           ) -> dict:
        """Run perception quality assessment without full pipeline execution.

        Returns a complete perception report with quality, gate verdict,
        human-readable explanation, and capability analysis.

        Args:
            frame_width: Input frame width in pixels
            frame_height: Input frame height in pixels
            target_px: Estimated size of the target object in pixels (if known)
            detection_streams: Names of detection streams that would be blocked
                               if quality is insufficient

        Returns:
            dict with keys:
              - quality_report: QualityReport.to_dict()
              - gate_verdict: GateVerdict as dict
              - explanation: PerceptionExplainer.explain() dict
              - capabilities: CapabilityRegistry.check() list
              - best_capability: best matching capability
        """
        report = self._perception_quality.assess(frame_width, frame_height, target_px)
        verdict = self._resolution_gate.evaluate(report, target_streams=detection_streams or [])

        if verdict.proxy_activated:
            self._ensure_proxy_stream(has_visual_input=frame_width > 0 and frame_height > 0)

        explanation = self._perception_explainer.explain(report, verdict)
        capabilities = self._capability_registry.check(frame_width, frame_height, target_px)
        best = self._capability_registry.best(frame_width, frame_height, target_px)
        return {
            "quality_report": report.to_dict(),
            "gate_verdict": {
                "passed": verdict.passed,
                "reason": verdict.reason,
                "proxy_activated": verdict.proxy_activated,
                "blocked_streams": verdict.blocked_streams,
            },
            "explanation": explanation,
            "capabilities": capabilities,
            "best_capability": best,
        }

    @property
    def quality_threshold(self) -> float:
        return self._resolution_gate.threshold

    @quality_threshold.setter
    def quality_threshold(self, value: float) -> None:
        self._resolution_gate.threshold = value

    def execute(self, state: np.ndarray,  # Axiom 1.1 — Architecture Produces Outcomes
                 user_name: Optional[str] = None,
                 chat_history: Optional[List[Dict]] = None,
                 tiered_context: Optional['TieredContext'] = None) -> PipelineResult:
        # ── Genesis recognition — bind creator identity ──
        if user_name and ANCHOR.recognize(user_name):
            self._creator_present = True
        else:
            self._creator_present = False
        cycle_start = time.time()
        self._cycle_count += 1
        self._display.on_cycle_start(self._cycle_count)
        self.budget_manager.reset(carryover_ms=self._carryover_budget)

        # ── Tiered Context Initialization ──
        if tiered_context is None:
            if chat_history:
                tiered_context = TieredContext.from_chat_history(chat_history)
            else:
                tiered_context = TieredContext()
        else:
            # Append any new messages from this cycle not yet in tiered context
            if chat_history:
                for msg in chat_history:
                    tiered_context.add_message(msg)

        # Phase context sees the tiered view for session awareness
        tiered_view = tiered_context.get_context()
        ctx = PhaseContext(
            cycle_count=self._cycle_count,
            state=state,
            user_name=ANCHOR.creator if self._creator_present else (user_name or "unknown"),
            world=World(state=state.copy(), metadata={"cycle": self._cycle_count, "creator_present": self._creator_present}),
            domain_facts=self.config.simulator.get_facts(state) if self.config.simulator else None,
            chat_history=tiered_view,
        )
        # Store tiered context on ctx for downstream use
        ctx._tiered_context = tiered_context

        for phase in self._phases:
            self._display.on_phase_start(phase.name)
            try:
                phase.execute(self, ctx)
            except Exception as e:
                logger.critical(f"Phase '{phase.name}' crashed: {e}", exc_info=True)
                ctx.governance_blocked = True
                ctx.blocking_reason = f"phase_crash:{phase.name}:{str(e)[:50]}"
                if hasattr(self, '_telemetry'):
                    self._telemetry.record_phase_failure(phase.name, str(e))
                break

            # ── Compute resource budgets after STREAMS phase (before Evaluate) ──
            if phase.name == "streams":
                ctx.resource_budgets = self._compute_resource_budgets(ctx)

            # ── Curiosity Drive: Inject self-intent and modulate exploration ──
            if phase.name == "streams":
                # Inject self-originating intent if curiosity is high enough
                if self._curiosity_drive.should_generate_self_intent():
                    from telos.intent_ir import IntentIR
                    curiosity_intent = IntentIR(
                        intent_type="curiosity_explore",
                        confidence=min(1.0, self._curiosity_drive.state.curiosity_level),
                        params={
                            "curiosity_level": self._curiosity_drive.state.curiosity_level,
                            "self_initiated": True,
                            "reason": "curiosity_drive_intrinsic_inquiry",
                        },
                        metadata={
                            "stream": "curiosity",
                            "curiosity_level": self._curiosity_drive.state.curiosity_level,
                            "novelty_seeking": self._curiosity_drive.state.novelty_seeking,
                        },
                    )
                    ctx.intents.append((curiosity_intent, self._curiosity_drive.state.curiosity_level))
                    logger.info(
                        f"Curiosity Drive: injected self-intent "
                        f"(curiosity={self._curiosity_drive.state.curiosity_level:.2f})"
                    )
                
                # Modulate exploration budget by curiosity bonus
                curiosity_bonus = self._curiosity_drive.get_curiosity_bonus()
                ctx.curiosity_bonus = curiosity_bonus
                if hasattr(self, '_infra_manager') and hasattr(self._infra_manager, 'policy'):
                    self._infra_manager.policy.apply_curiosity_modulation(curiosity_bonus)
                # Scale effective_n_worlds by curiosity
                if curiosity_bonus > 1.0:
                    ctx.effective_n_worlds = max(
                        1, int(ctx.effective_n_worlds * curiosity_bonus)
                    )
                    logger.debug(
                        f"Curiosity bonus: n_worlds scaled by x{curiosity_bonus:.2f} "
                        f"-> {ctx.effective_n_worlds}"
                    )


            # ── Law of Attention: Project attention after PERCEIVE phase ──
            if phase.name == "perceive":
                alloc = getattr(ctx, 'attention_allocation', None)
                if alloc is not None:
                    self._attention_engine.record_allocation(alloc)

                # B1: Run perception quality assessment — wire Ghost Components
                try:
                    frame_w = ctx.world.metadata.get("frame_width", 0)
                    frame_h = ctx.world.metadata.get("frame_height", 0)
                    target = ctx.world.metadata.get("target_px", None)
                    if frame_w > 0 and frame_h > 0:
                        perception_result = self.assess_perception(frame_w, frame_h, target)
                        ctx.perception_report = perception_result
                except Exception:
                    pass

            # ── v2: UnknownUnknownDetector — find blind spots after perception ──
            if phase.name == "perceive":
                try:
                    observation = getattr(ctx, 'world', None)
                    if observation is not None:
                        novelty = self._unknown_unknown_detector.detect(observation, self._cycle_count)
                        if novelty:
                            logger.info(f"[v2] Novelty cluster detected: {novelty.get('question', '')[:60]}")
                            ctx._novelty_question = novelty.get("question")
                except Exception:
                    pass

            # ── Bitcoin-inspired Decision Timelock: Apply penalties after EVALUATE ──
            if phase.name == "evaluate":
                self._apply_timelock_penalties(ctx)

            # ── v2: ModelCompetition — update competing hypotheses after evaluation ──
            if phase.name == "evaluate":
                try:
                    if ctx.selected_intent and ctx.selected_intent.confidence:
                        self._model_competition.add_evidence(
                            intent_type=ctx.selected_intent.intent_type,
                            confidence=ctx.selected_intent.confidence,
                            outcome=not (ctx.council_blocked or ctx.firewall_blocked),
                        )
                except Exception:
                    pass

            # ── Identity Modeling (parallel track): update identity before select ──
            if phase.name == "select":
                try:
                    ss = self._system_self
                    if ss is not None:
                        outcome_success = not (getattr(ctx, 'council_blocked', False)
                                               or getattr(ctx, 'firewall_blocked', False))
                        ss.update(ctx.state if hasattr(ctx, 'state') else None,
                                  ctx.selected_intent.intent_type if ctx.selected_intent else "none",
                                  outcome_success,
                                  {"cycle": ctx.cycle_count})
                        ctx.identity_state = ss.get_state()
                    # Identity entropy refresh
                    ie = self._identity_entropy
                    if ie is not None:
                        n_options = len(getattr(ctx, 'sim_options', []) or [])
                        ie.record(max(1, n_options))
                        ctx.identity_entropy = ie.collapse_rate
                except Exception:
                    pass

            # ── v2: InternalDebate — multi-perspective analysis before decision ──
            if phase.name == "select":
                try:
                    if ctx.selected_intent:
                        debate_result = self._internal_debate.debate(
                            context=str(ctx.state)[:100],
                            intent_type=ctx.selected_intent.intent_type,
                        )
                        if debate_result:
                            ctx._debate_result = debate_result
                except Exception:
                    pass

            # ── Bitcoin-inspired Decision Timelock: Record after SELECT ──
            if phase.name == "select":
                selected_intent = getattr(ctx, 'selected_intent', None)
                if selected_intent is not None:
                    self._record_timelock(ctx, selected_intent)

            # ── Store plan in PlanningHorizon after SELECT phase ──
            if phase.name == "select":
                selected = getattr(ctx, 'selected_intent', None)
                if selected is not None:
                    self.planning_horizon.set_plan([selected])

            # ── Submit selected intent to Decision Mempool before council ──
            if phase.name == "select":
                selected = getattr(ctx, 'selected_intent', None)
                if selected is not None:
                    stream_name = ""
                    for sa in getattr(ctx, 'stream_activations', []):
                        if sa.activated and sa.intent is selected:
                            stream_name = sa.stream_name
                            break
                    intent_id = self._mempool.submit(selected, stream_name=stream_name)
                    ctx._mempool_intent_id = intent_id
                    logger.debug(f"Mempool: submitted intent {intent_id} for council review")

            # ── Confirm/reject from mempool after council phase ──
            if phase.name == "council":
                intent_id = getattr(ctx, '_mempool_intent_id', None)
                if intent_id:
                    if getattr(ctx, 'verdict', None) and ctx.verdict.validated:
                        self._mempool.confirm(intent_id)
                    else:
                        reason = getattr(ctx.verdict, 'blocking_reason', 'council_blocked') if ctx.verdict else 'council_blocked'
                        self._mempool.reject(intent_id, reason=reason)

            # ── Law of Attention: Record trajectory after ACT phase ──
            if phase.name == "act":
                # Record trajectory divergence (predicted vs actual state)
                predicted = getattr(ctx, 'predicted_state', None)
                if predicted is not None:
                    self._attention_engine.record_trajectory_divergence(predicted, ctx.state)

                # Record identity entropy: action-space size = number of sim options
                n_options = len(getattr(ctx, 'sim_options', []) or [])
                self._attention_engine.record_action_space(max(1, n_options))
                self._identity_entropy.record(max(1, n_options))

                # Record counterfactual diversity from sim engine
                if self._sim_engine is not None:
                    div = self._sim_engine.rolling_diversity
                    self._attention_engine.record_counterfactual_variance(div)

                # ── v2: TheoryBuilder + RegretMemory — share outcome_success ──
                outcome_success = not (ctx.council_blocked or ctx.firewall_blocked)
                try:
                    self._theory_builder.observe_outcome(
                        outcome=outcome_success,
                        context=str(ctx.state)[:80],
                    )
                except Exception:
                    pass

                try:
                    if ctx.selected_intent:
                        self._regret_memory.record_decision(
                            chosen_intent=ctx.selected_intent.intent_type,
                            alternatives=[o.get("intent_type", "unknown") for o in getattr(ctx, 'sim_options', [])[:3]],
                            outcome=outcome_success,
                        )
                except Exception:
                    pass

                # ── v2: CognitiveMomentum — record decision inertia ──
                try:
                    intent_type = ctx.selected_intent.intent_type if ctx.selected_intent else "unknown"
                    self._cognitive_momentum.record_decision(
                        cycle=ctx.cycle_count,
                        intent_type=intent_type,
                    )
                except Exception:
                    pass

                # P1 D3: Multi-resource budget tracking — fallback if not already set
                # (primary budget computation happens after STREAMS phase)
                existing = getattr(ctx, 'resource_budgets', None)
                identity_stability = 1.0 - getattr(self._identity_entropy, 'collapse_rate', 0.0)
                if existing is None:
                    ctx.resource_budgets = {
                    "energy": {
                        "consumed_ms": self.budget_manager.consumed_ms,
                        "total_ms": self.budget_manager.total_budget_ms,
                        "utilization": self.budget_manager.consumed_ms / max(self.budget_manager.total_budget_ms, 1),
                        "description": "compute_budget_ms consumed this cycle",
                    },
                    "memory": {
                        "trace_history_length": ctx.cycle_count,
                        "description": "trace_history length (number of stored traces)",
                    },
                    "identity": {
                        "identity_entropy": 1.0 - identity_stability,
                        "identity_stability": identity_stability,
                        "description": "identity entropy (1 - identity_stability)",
                    },
                    "recovery": {
                        "recovery_mode_cycles": self._meta_cognition.get_stats()["recovery_cycles"],
                        "current_state": self._meta_cognition.get_stats()["current_state"],
                        "description": "number of recovery_mode cycles active",
                    },
                }
                else:
                    # Enrich existing budgets with post-execution data
                    ctx.resource_budgets["energy"]["consumed_ms"] = self.budget_manager.consumed_ms
                    ctx.resource_budgets["energy"]["utilization"] = self.budget_manager.consumed_ms / max(self.budget_manager.total_budget_ms, 1)
                    ctx.resource_budgets["identity"]["identity_entropy"] = 1.0 - identity_stability
                    ctx.resource_budgets["identity"]["identity_stability"] = identity_stability
                    ctx.resource_budgets["recovery"] = {
                        "recovery_mode_cycles": self._meta_cognition.get_stats()["recovery_cycles"],
                        "current_state": self._meta_cognition.get_stats()["current_state"],
                        "description": "number of recovery_mode cycles active",
                    }

                # ── Fix 2: Compute resource gradients and reallocate ──
                if hasattr(self, '_resource_gradient_tracker'):
                    budgets = ctx.resource_budgets
                    commitment_opt = getattr(self, '_commitment_optimizer', None)
                    gradients = self._resource_gradient_tracker.compute_gradients(commitment_opt, budgets)
                    new_alloc = self._resource_gradient_tracker.reallocate(budgets, gradients)
                    ctx.resource_gradients = gradients
                    ctx.resource_reallocated = new_alloc

                # P1 D4: Build identity tuple (G_t, M_t, C_t, V_t)
                domain_facts = getattr(ctx, 'domain_facts', None)
                goals = {}
                memory_summary = {}
                constraints_list = []
                values = {}

                if domain_facts:
                    # G_t: Goals from DomainFacts
                    goals = {
                        "position": getattr(domain_facts, 'state', None).tolist() if hasattr(getattr(domain_facts, 'state', None), 'tolist') else getattr(domain_facts, 'state', None),
                        "distance": domain_facts.resources.get("distance", 0),
                        "near_reward": domain_facts.resources.get("reward_near", 0),
                    }
                    # C_t: Active constraints
                    constraints_list = list(domain_facts.constraints)
                    # Also add some mission-derived constraints
                    if getattr(self, '_infra_manager', None) and hasattr(self._infra_manager, 'policy'):
                        policy = self._infra_manager.policy
                        constraints_list.append(f"risk_tolerance={getattr(policy, 'risk_tolerance', 0.5):.2f}")
                        constraints_list.append(f"exploration_budget={getattr(policy, 'exploration_budget', 0.3):.2f}")

                if getattr(self, '_infra_manager', None) and hasattr(self._infra_manager, 'system_self'):
                    ss = self._infra_manager.system_self
                    # M_t: Recent decision traces summary
                    memory_summary = {
                        "mood": ss.mood,
                        "confidence_trend": ss.state.confidence_trend,
                        "dominant_streak": ss.state.dominant_streak,
                        "exploration_appetite": ss.state.exploration_appetite,
                        "resilience": ss.state.resilience,
                        "recent_di": getattr(ss, '_di_window', [])[-5:] if hasattr(ss, '_di_window') else [],
                        "recent_md": getattr(ss, '_md_window', [])[-5:] if hasattr(ss, '_md_window') else [],
                    }
                    # V_t: Core values from identity markers
                    markers = ss.state.identity_markers
                    values = {
                        "identity_markers": sorted(markers),
                        "epistemic_integrity": "truth_anchored" if "exploring" in markers else "default",
                        "adaptability": "high" if "adaptive" in markers else "medium",
                        "resilience_value": ss.state.resilience,
                    }
                else:
                    # Fallback system self
                    memory_summary = {"mood": "unknown", "confidence_trend": "stable"}

                # ── Fix 5 (C3): Extract K_t from SkillLibrary ──
                skill_lib = getattr(self, '_skill_library', None)
                capabilities = {}
                if skill_lib is not None and hasattr(skill_lib, 'skills'):
                    skills_data = skill_lib.skills
                    capabilities = {
                        "available_skills": list(skills_data.keys())[:20],
                        "skill_count": len(skills_data),
                        "top_utility_skills": sorted(
                            [(sid, s.utility_score) for sid, s in skills_data.items()],
                            key=lambda x: -x[1]
                        )[:5] if skills_data else [],
                    }

                # ── Fix 1: Wire ψ operator — formal identity update ──
                if hasattr(self, '_infra_manager') and self._infra_manager and hasattr(self._infra_manager, 'system_self'):
                    ss_op = self._infra_manager.system_self
                    if hasattr(ss_op, 'formal_identity_update'):
                        action_str = str(ctx.selected_intent.intent_type) if ctx.selected_intent else 'none'
                        obs_state = getattr(ctx, 'state', np.array([0,0]))
                        # Build observation string from domain facts
                        if ctx.domain_facts:
                            events = getattr(ctx.domain_facts, 'events', [])
                            dist = ctx.domain_facts.resources.get('distance', 999)
                            obs_str = ','.join(events) if events else ('success' if dist < 1 else 'moving')
                        else:
                            obs_str = 'unknown'
                        identity_result = ss_op.formal_identity_update(action_str, obs_state, obs_str)
                    else:
                        identity_result = None
                else:
                    identity_result = None

                if identity_result:
                    ctx.identity_state = {
                        "G_t": identity_result.get("G_t", goals),
                        "M_t": identity_result.get("M_t", memory_summary),
                        "B_t": identity_result.get("B_t", getattr(self._infra_manager.system_self, 'get_belief_state', lambda: {})()),
                        "C_t": {"active_constraints": constraints_list, **{k: v for k, v in identity_result.get("C_t", {}).items() if k != 'action'}},
                        "K_t": identity_result.get("K_t", capabilities),
                        "V_t": identity_result.get("V_t", values),
                        "Res_t": ctx.resource_budgets,
                        "R_t": RelationalContext().to_dict(),
                    }
                else:
                    ctx.identity_state = {
                        "G_t": goals,
                        "M_t": memory_summary,
                        "B_t": getattr(self._infra_manager.system_self, 'get_belief_state', lambda: {})(),
                        "C_t": {"active_constraints": constraints_list},
                        "K_t": capabilities,
                        "V_t": values,
                        "Res_t": ctx.resource_budgets,
                        "R_t": RelationalContext().to_dict(),
                    }

                # ── Backward compat: normalize old checkpoint identity_state keys ──
                # Old checkpoints used "R_t" for resource_budgets; now "Res_t" is used.
                # If we find an old-style key, migrate it.
                if "R_t" in ctx.identity_state and "Res_t" not in ctx.identity_state:
                    ctx.identity_state["Res_t"] = ctx.identity_state.pop("R_t")
                    logger.debug("Checkpoint compat: migrated old R_t → Res_t for resource budgets")
                if "Res_t" not in ctx.identity_state:
                    ctx.identity_state["Res_t"] = ctx.resource_budgets
                if "R_t" not in ctx.identity_state:
                    ctx.identity_state["R_t"] = RelationalContext().to_dict()

                # ── Fix 4: Compute d(I_t, I_{t-1}) using marker set diff + belief KL-divergence ──
                if hasattr(self, '_prev_identity_state') and self._prev_identity_state:
                    prev = self._prev_identity_state
                    curr = ctx.identity_state
                    try:
                        prev_markers = set(prev.get('V_t', {}).get('identity_markers', []))
                        curr_markers = set(curr.get('V_t', {}).get('identity_markers', []))
                        marker_jaccard = 1 - (len(prev_markers & curr_markers) / max(len(prev_markers | curr_markers), 1))
                        prev_beliefs = prev.get('B_t', {})
                        curr_beliefs = curr.get('B_t', {})
                        all_b_keys = set(list(prev_beliefs.keys()) + list(curr_beliefs.keys()))
                        belief_diff = sum(
                            abs(prev_beliefs.get(k, {}) if isinstance(prev_beliefs.get(k), dict) else 0 - 
                                curr_beliefs.get(k, {}) if isinstance(curr_beliefs.get(k), dict) else 0)
                            for k in all_b_keys
                        ) / max(len(all_b_keys), 1)
                        # If belief values are dicts, compute inner jaccard
                        inner_diffs = []
                        for k in all_b_keys:
                            pv = prev_beliefs.get(k, {})
                            cv = curr_beliefs.get(k, {})
                            if isinstance(pv, dict) and isinstance(cv, dict):
                                p_set = set(str(f'{sk}:{sv}') for sk, sv in pv.items())
                                c_set = set(str(f'{sk}:{sv}') for sk, sv in cv.items())
                                inner_diffs.append(1 - len(p_set & c_set) / max(len(p_set | c_set), 1))
                        if inner_diffs:
                            belief_diff = sum(inner_diffs) / len(inner_diffs)
                        ctx.identity_distance = (marker_jaccard + belief_diff) / 2.0
                    except Exception:
                        ctx.identity_distance = 0.0
                else:
                    ctx.identity_distance = 0.0
                self._prev_identity_state = dict(ctx.identity_state)

                # Write identity tuple to /tmp/telos_identity_tuple.json
                try:
                    import json
                    with open('/tmp/telos_identity_tuple.json', 'w') as idf:
                        json.dump(ctx.identity_state, idf, indent=2, default=str)
                except Exception:
                    pass

                # P0 D8: Run meta-cognition check + P0: Tripartite Uncertainty
                infra = getattr(self, '_infra_manager', None)
                calibrator = getattr(infra, 'calibrator', None) if infra else None
                stream_uncertainties = calibrator.get_stream_uncertainties() if calibrator else {}
                council_signals = ctx.verdict.signals if ctx.verdict else []
                council_signal_dicts = [
                    {
                        "validator_name": s.validator_name,
                        "passed": s.passed,
                        "confidence": s.confidence,
                        "reason": s.reason,
                        "evidence_weight": s.evidence_weight,
                        "verdict": s.verdict,
                    }
                    for s in council_signals
                ] if council_signals else []
                di = ctx.verdict.decision_integrity if ctx.verdict else 1.0
                # Compute resource_depletion and time_pressure from budgets
                rb = getattr(ctx, 'resource_budgets', None) or {}
                energy = rb.get('energy', {})
                resource_depletion = energy.get('utilization', 0.0)
                # time_pressure: how much of the budget has been consumed (0-1)
                time_pressure = min(1.0, self.budget_manager.consumed_ms / max(self.budget_manager.total_budget_ms, 1))

                meta_cog_report = self._meta_cognition.observe(
                    stream_uncertainties=stream_uncertainties,
                    council_signals=council_signal_dicts,
                    tripartite_u=self._tripartite_u.to_dict(),
                    decision_integrity=di,
                    cycle_count=ctx.cycle_count,
                    inquiry_active=getattr(ctx, 'inquiry_skipped', False) == False,
                    inquiry_omega_value=getattr(ctx, 'inquiry_omega_value', 0.0),
                    resource_depletion=resource_depletion,
                    time_pressure=time_pressure,
                )

                # P0: Compute tripartite uncertainty U = (U_W, U_I, U_O)
                # U_W: observation_noise + prediction_error_clipped
                obs_noise = float(np.mean(list(stream_uncertainties.values()))) if stream_uncertainties else 0.0
                pred_err = getattr(ctx, 'prediction_error', 0.0)
                if pred_err == 0.0 and hasattr(self, '_attention_engine'):
                    recent_divs = getattr(self._attention_engine, '_trajectory_divergences', [])[-3:]
                    pred_err = min(1.0, sum(recent_divs) / max(len(recent_divs), 1)) if recent_divs else 0.0

                # U_I: identity entropy trajectory
                id_entropy_val = getattr(self._identity_entropy, 'collapse_rate', 0.0)
                if id_entropy_val == 0.0 and hasattr(self._identity_entropy, 'assess'):
                    id_entropy_val = getattr(self._identity_entropy.assess(), 'entropy_rate', 0.0)

                # U_O: council signal disagreement
                if council_signal_dicts:
                    passed_vals = [s.get('passed', True) for s in council_signal_dicts]
                    confidence_vals = [s.get('confidence', 0.5) for s in council_signal_dicts]
                    if passed_vals:
                        n_total = len(passed_vals)
                        n_blocked = sum(1 for p in passed_vals if not p)
                        disagreement = n_blocked / max(n_total, 1)
                        # Weight by confidence variance
                        if len(confidence_vals) > 1:
                            import numpy as np_import
                            confidence_var = float(np_import.var(confidence_vals))
                            disagreement = min(1.0, disagreement + confidence_var * 0.5)
                    else:
                        disagreement = 0.0
                else:
                    disagreement = 0.0

                self._tripartite_u.update(
                    observation_noise=obs_noise,
                    prediction_error=pred_err,
                    identity_entropy=id_entropy_val,
                    council_disagreement=disagreement,
                )

                # ── Gap 1: Record omega threshold outcome ──
                inquiry_omega_val = getattr(ctx, 'inquiry_omega_value', 0.0)
                if hasattr(self, '_omega_threshold_learner') and inquiry_omega_val > 0:
                    prev_di = getattr(self, '_last_di_for_omega', None)
                    curr_di = di
                    di_improved = (prev_di is not None and curr_di > prev_di)
                    was_blocked = getattr(ctx, 'governance_blocked', False) or getattr(ctx, 'council_blocked', False)
                    self._omega_threshold_learner.record_outcome(
                        inquiry_omega_val, di_improved, was_blocked
                    )
                self._last_di_for_omega = di

                ctx.meta_cognition = {
                    "current_state": meta_cog_report.current_state.value,
                    "exploration_mode": meta_cog_report.exploration_mode_active,
                    "recovery_mode": meta_cog_report.recovery_mode_active,
                    "epistemic_repair": meta_cog_report.epistemic_repair_active,
                    "trigger_reason": meta_cog_report.trigger_reason,
                    "stream_uncertainties": stream_uncertainties,
                    "consecutive_council_blocks": meta_cog_report.consecutive_council_blocks,
                    "mode": meta_cog_report.mode,
                    # P0: Tripartite uncertainty
                    "tripartite_u": self._tripartite_u.to_dict(),
                    "U_W": self._tripartite_u.U_W,
                    "U_I": self._tripartite_u.U_I,
                    "U_O": self._tripartite_u.U_O,
                }
                # Package attention metrics for DecisionTrace
                ctx.attention_metrics = {
                    **self._attention_engine.stats,
                    "identity_entropy_assessment": self._identity_entropy.assess().recommended_action,
                    "identity_entropy_signal": {
                        "collapse_rate": self._identity_entropy.collapse_rate,
                        "is_critical": self._identity_entropy.is_critical,
                        "projected_size": self._identity_entropy.project_size(horizon=3),
                    },
                    "current_allocation": {
                        "threat_ratio": alloc.threat_ratio,
                        "opportunity_ratio": alloc.opportunity_ratio,
                        "maintenance_ratio": alloc.maintenance_ratio,
                    } if (alloc := getattr(ctx, 'attention_allocation', None)) else None,
                    # Maintenance vs Recovery cost telemetry from infra_manager
                    "cost_tracker": self._infra_manager.cost_tracker.stats,
                }
                # ── Curiosity Drive: Update learning progress after act phase ──
                if phase.name == "act":
                    # Compute total uncertainty composite from tripartite U
                    total_uncertainty = (
                        getattr(self._tripartite_u, 'U_W', 0.0)
                        + getattr(self._tripartite_u, 'U_I', 0.0)
                        + getattr(self._tripartite_u, 'U_O', 0.0)
                    ) / 3.0
                    
                    # was_blocked from governance or council
                    was_blocked = (
                        getattr(ctx, 'governance_blocked', False)
                        or getattr(ctx, 'council_blocked', False)
                    )
                    
                    # council_disagreement from computation above
                    council_disagreement = getattr(self._tripartite_u, 'U_O', 0.0)
                    
                    # Update curiosity drive with learning progress
                    curiosity_report = self._curiosity_drive.update(
                        uncertainty_before=self._prev_uncertainty,
                        uncertainty_after=total_uncertainty,
                        was_blocked=was_blocked,
                        council_disagreement=council_disagreement,
                    )
                    self._prev_uncertainty = total_uncertainty
                    
                    # Store on context for trace
                    ctx.curiosity_state = curiosity_report
                    if not hasattr(ctx, 'curiosity_bonus') or ctx.curiosity_bonus <= 1.0:
                        ctx.curiosity_bonus = self._curiosity_drive.get_curiosity_bonus()
                    
                    logger.debug(
                        f"Curiosity: level={curiosity_report['curiosity_level']:.3f}, "
                        f"learned={curiosity_report['learning_rate']:.4f}, "
                        f"bored={curiosity_report['boredom_count']}, "
                        f"self_intent={curiosity_report['self_intent_active']}"
                    )


            if getattr(ctx, 'governance_blocked', False) and phase.name not in ("act", "reflect"):
                continue

        cycle_duration = (time.time() - cycle_start) * 1000

        # P2.9: Run perception explainer and capability check, attach to trace
        perception_explanation = None
        if ctx.perceive and ctx.perceive.quality_report is not None and ctx.perceive.gate_verdict is not None:
            try:
                explanation = self._perception_explainer.explain(
                    ctx.perceive.quality_report, ctx.perceive.gate_verdict
                )
                # Use frame dimensions from world metadata if available (visual pipeline)
                frame_w = ctx.world.metadata.get("frame_width", 0) if ctx.world else 0
                frame_h = ctx.world.metadata.get("frame_height", 0) if ctx.world else 0
                if frame_w > 0 and frame_h > 0:
                    capabilities = self._capability_registry.check(frame_w, frame_h)
                    best_cap = self._capability_registry.best(frame_w, frame_h)
                else:
                    capabilities = []
                    best_cap = None
                perception_explanation = {
                    "explanation": explanation,
                    "capabilities": capabilities,
                    "best_capability": best_cap,
                }
            except Exception as e:
                logger.debug(f"Perception explanation skipped: {e}")

        # ── Session Continuity Layer ──
        # Tiered context provides automatic compression across HOT/WARM/COLD tiers.
        # TokenBudgetManager and ContextSummarizer run as supplementary analysis.
        tc = getattr(ctx, '_tiered_context', None)
        if tc is not None:
            # Store tiered context state for checkpointing
            ctx.session.tiered_context = tc.to_dict()
            ctx.session.context_pressure = tc.get_pressure()
            # The tiered view is already in ctx.chat_history

        # Embed tiered context data in session_essence for checkpointing
        if tc is not None and ctx.session:
            if ctx.session.session_essence is None:
                ctx.session.session_essence = {}
            ctx.session.session_essence['_tiered_context'] = tc.to_dict()
            ctx.session.session_essence['_context_pressure'] = tc.get_pressure()

        # Legacy token budget optimization on the tiered view (supplementary)
        if ctx.chat_history:
            try:
                traces: Dict[int, Dict] = {}
                di_val = ctx.verdict.decision_integrity if ctx.verdict else 1.0
                md_val = ctx.verdict.mission_drift if ctx.verdict else 0.0
                blocked = ctx.council_blocked or ctx.firewall_blocked
                escalated = ctx.verdict.escalation_requested if ctx.verdict else False
                for i in range(len(ctx.chat_history)):
                    traces[i] = TokenBudgetManager.make_trace(
                        di=di_val, md=md_val, blocked=blocked, escalated=escalated,
                    )
                ctx.session.truncated_history = self._token_budget.optimize(
                    ctx.chat_history, traces=traces,
                )
            except Exception as e:
                logger.warning(f"Token budget optimization failed: {e}")
                ctx.session.truncated_history = ctx.chat_history[-20:]

            # Session essence summarization (periodic, supplementary)
            try:
                essence = self._context_summarizer.maybe_summarize(
                    self._cycle_count, ctx.chat_history,
                )
                if essence is not None:
                    ctx.session.session_essence = essence.to_dict()
            except Exception as e:
                logger.warning(f"Context summarization failed: {e}")

        health = max(0.0, min(1.0, 1.0 - (self.budget_manager.consumed_ms / self.budget_manager.total_budget_ms
                         if self.budget_manager.total_budget_ms > 0 else 0.0)))

        trace = build_trace(
            ctx=ctx, state=state,
            cycle_count=self._cycle_count,
            budget_manager=self.budget_manager,
            cycle_duration=cycle_duration,
            infra_manager=self._infra_manager,
            last_quality_report=self._last_quality_report,
            perception_explanation=perception_explanation,
            prev_trace_id=self._prev_trace_id,
        )
        self._prev_trace_id = trace.produced_ctx_id

        # ── pipeline_finalize: axiom verification + v2 module hooks + resource accounting ──
        run_axiom_prover(self, trace, ctx)
        run_v2_module_hooks(self, ctx, trace)
        record_resource_accounting(self, ctx)

        status = "BLOCKED" if ctx.governance_blocked else "APPROVED"
        escalation_tag = f" [ESCALATED: {ctx.verdict.escalation_reason}]" if (ctx.verdict and ctx.verdict.escalation_requested) else ""
        reflection_tag = ""
        if ctx.reflection:
            parts = []
            if ctx.reflection.get("cross_domain_hits", 0) > 0:
                parts.append(f"X-domain={ctx.reflection['cross_domain_hits']}")
            if ctx.reflection.get("recurring_blocks"):
                parts.append(f"recur={ctx.reflection['recurring_blocks']}")
            if ctx.reflection.get("adaptive_horizon") is not None:
                parts.append(f"horizon={ctx.reflection['adaptive_horizon']}")
            if parts:
                reflection_tag = f" [{', '.join(parts)}]"
        logger.info(
            f"Cycle {self._cycle_count}: streams={len([a for a in ctx.stream_activations if a.activated])}, "
            f"worlds={ctx.worlds_generated}, intent={ctx.selected_intent.intent_type if ctx.selected_intent else 'none'}, "
            f"governance={status}{escalation_tag}{reflection_tag}, DI={trace.decision_integrity:.3f}, "
            f"MD={trace.mission_drift:.3f}, "
            f"budget={self.budget_manager.consumed_ms:.1f}/{self.budget_manager.total_budget_ms:.1f}ms"
        )

        result = PipelineResult(
            selected_trajectory=ctx.selected_intent if not ctx.governance_blocked else None,
            health_score=health,
            pipeline_phase=PipelinePhase.COMPLETE,
            worlds_generated=ctx.worlds_generated,
            council_blocked=ctx.council_blocked,
            decision_integrity=trace.decision_integrity,
            mission_drift=trace.mission_drift,
            firewall_blocked=ctx.firewall_blocked,
            governance_blocked_by=ctx.firewall_verdict.blocked_by if ctx.firewall_verdict else None,
            decision_trace=trace,
            alternatives_available=self._sim_engine.alternative_count if self._sim_engine else 0,
        )

        self._telemetry.record_cycle(self._cycle_count, trace)

        self._experience_manager.observe(result)

        # Record user interaction BEFORE checkpoint save so it's captured
        if ctx.user_name and ctx.selected_intent:
            self.ledger.record_user_interaction(
                ctx.user_name, ctx.selected_intent.intent_type,
                ctx.selected_intent.confidence, self._cycle_count,
            )

        if self._checkpointer:
            try:
                self._checkpointer.save(
                    cycle=self._cycle_count,
                    world_ledger=self.ledger,
                    skill_library=getattr(self, '_skill_library', None),
                    stream_calibrator=self._infra_manager.calibrator,
                    failure_ledger=self._infra_manager.failures,
                    mission_policy=self._infra_manager.policy,
                    decision_trace=trace,
                    knowledge_graph=self._infra_manager.knowledge,
                    sim_engine=self._sim_engine,
                    planning_horizon=self.planning_horizon,
                    infrastructure_manager=self._infra_manager,
                    session_essence=ctx.session.session_essence if ctx.session else None,
                    truncated_history=ctx.session.truncated_history if ctx.session else None,
                    omega_threshold_learner=getattr(self, '_omega_threshold_learner', None),
                )
            except Exception as e:
                logger.warning(f"Checkpoint save failed: {e}")

        self._infra_manager.observe(result, total_streams=len(self.streams))
        self._last_trace = trace

        # Reset MissionDriftDetector cumulative drift every 50 cycles
        if self._cycle_count % 50 == 0 and hasattr(self, 'council'):
            for v in self.council._validators:
                if hasattr(v, 'reset_drift'):
                    v.reset_drift()
                    logger.debug(f"Cycle {self._cycle_count}: Reset drift for {v.name}")

        if ctx.worlds_generated > 0 and ctx.sim_options:
            self._last_sim_score = ctx.sim_options[0].score

        if self.config.budget_carryover_max_ratio > 0:
            unused = max(0, self.budget_manager.total_budget_ms - self.budget_manager.consumed_ms)
            self._carryover_budget = min(unused, self.config.compute_budget_ms * self.config.budget_carryover_max_ratio)
        else:
            self._carryover_budget = 0.0

        self._display.freeze()
        return result

    def shutdown(self) -> None:
        if self.config.ledger_path:
            try:
                self.ledger.save(self.config.ledger_path)
                logger.info(f"WorldLedger saved to {self.config.ledger_path}")
            except Exception as e:
                logger.warning(f"WorldLedger save failed: {e}")
        if self.config.identity_path:
            try:
                self._infra_manager.system_self.save(self.config.identity_path)
                logger.info(f"SystemSelf saved to {self.config.identity_path}")
            except Exception as e:
                logger.warning(f"SystemSelf save failed: {e}")
        if self.config.pattern_path:
            pl = self.pattern_library
            if pl is not None:
                try:
                    pl.save(self.config.pattern_path)
                    logger.info(f"PatternLibrary saved to {self.config.pattern_path}")
                except Exception as e:
                    logger.warning(f"PatternLibrary save failed: {e}")
        if self.config.knowledge_path:
            try:
                self._infra_manager.knowledge.save(self.config.knowledge_path)
                logger.info(f"KnowledgeGraph saved to {self.config.knowledge_path}")
            except Exception as e:
                logger.warning(f"KnowledgeGraph save failed: {e}")
        if self._checkpointer:
            try:
                final_trace = getattr(self, '_last_trace', None)
                self._checkpointer.save(
                    cycle=self._cycle_count,
                    world_ledger=self.ledger,
                    skill_library=getattr(self, '_skill_library', None),
                    stream_calibrator=self._infra_manager.calibrator,
                    failure_ledger=self._infra_manager.failures,
                    mission_policy=self._infra_manager.policy,
                    decision_trace=final_trace,
                    knowledge_graph=self._infra_manager.knowledge,
                    sim_engine=self._sim_engine,
                    planning_horizon=self.planning_horizon,
                    infrastructure_manager=self._infra_manager,
                    session_essence=None,
                    truncated_history=None,
                    omega_threshold_learner=getattr(self, '_omega_threshold_learner', None),
                )
                logger.info(f"Final checkpoint saved (cycle {self._cycle_count})")
            except Exception as e:
                logger.warning(f"Final checkpoint save failed: {e}")
        # Cross-session learning: write session handoff
        try:
            write_handoff(self, {
                "di": getattr(self, '_last_trace', None).decision_integrity if hasattr(self, '_last_trace') else 1.0,
                "md": getattr(self, '_last_trace', None).mission_drift if hasattr(self, '_last_trace') else 0.0,
                "cycles": self._cycle_count,
                "mood": getattr(getattr(self, '_system_self', None), '_state', None).mood if hasattr(getattr(self, '_system_self', None), '_state') else 'neutral',
            })
        except Exception as e:
            logger.warning(f"AgentsWriter handoff failed: {e}")
        if self.config.adapter and hasattr(self.config.adapter, 'cleanup'):
            self.config.adapter.cleanup()
