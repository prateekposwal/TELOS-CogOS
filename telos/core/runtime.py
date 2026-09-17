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

from __future__ import annotations
import os

import time
import numpy as np
import logging
from typing import Dict, List, Any, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
    from telos.core.infra_manager.checkpoint_manager import CheckpointManager

logger = logging.getLogger('telos_pipeline')

from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter
from telos.core.attention import BudgetManager
from telos.core.attention.projection import AttentionProjectionEngine, AttentionAllocation
from telos.core.attention.identity_entropy import IdentityEntropyTracker
from telos.core.decision.commitment_optimizer import CommitmentOptimizer
from telos.core.decision.omega_threshold import OmegaThresholdLearner
from telos.core.decision.cognitive_momentum import CognitiveMomentum
from telos.core.accounting.resource_accounting import ResourceAccountingLayer, ResourceCost
from telos.core.pipeline_finalize import run_axiom_prover, run_v2_module_hooks, record_resource_accounting
from telos.core.council.distributed import DistributedCouncil, AgentRole
from telos.core.curiosity.exploration import AutonomousExplorer
from telos.core.session.persistence import save_learnings, load_learnings
from telos.core.reasoning.representation_search import RepresentationSearch, RepresentationType
from telos.core.timing.meta_time import MetaTime, TimeScale
from telos.core.session.agents_writer import write_handoff
from telos.core.session.agents_reader import inject_into_context
from telos.core.project.substrate import ProjectPortfolio
from telos.core.project.rational_abandonment import AbandonmentGate
from telos.core.project.strategic_coherence import StrategicCoherence
from telos.core.project.method import MethodRegistry
from telos.core.ecology.ecosystem import Ecosystem
from telos.core.research.amplification_gate import ResearchAmplificationGate
from telos.core.research.seasons import ResearchSeasons
from telos.core.research.discovery_rate import DiscoveryRateTracker
from telos.core.research.debt import ResearchDebtTracker
from telos.core.research.belief_capital import BeliefCapitalMarket
from telos.core.reasoning.genealogy import TheoryGenealogy
from telos.core.discovery.orchestrator import DiscoveryOrchestrator
from telos.core.identity.mission import MissionPortfolio
from telos.core.identity.mission_arbitration import MissionArbiter
from telos.core.identity.mission_lifecycle import MissionLifecycleEngine
from telos.core.identity.system_self import IdentityCore
from telos.core.identity.identity_bridge import IdentityBridge
from telos.core.streams.implementations import TheoryStream
from telos.core.accounting.resource_gradient import ResourceGradientTracker
from telos.core.streams.base import CognitiveStream
from telos.core.simulation import CounterfactualEngine, StrategicOption
from telos.core.planner import RepresentationPlanner
from telos.core.meta.meta_cognition import MetaCognitionModule, MetaState
from telos.core.uncertainty.tripartite import TripartiteUncertainty
from telos.core.reasoning.relational import RelationalContext
from telos.core.representation_selector import RepresentationSelector
from telos.core.council.base import Council, CouncilVerdict, ValidationSignal
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.governance.trust_manager import TrustManager
from telos.core.governance.timing import InformationReadinessEngine, ReadinessCondition
STAGNATION_RECOVERY_AFTER = 3  # consecutive no-action cycles before force-escape

# Ring size for the selection-level loop-family ledger (Λ3.1). Spans more
# than an episode of blocker alternation (two types ~2-3 cycles each) plus
# margin, so the alternation pair is always jointly visible — yet small
# enough that a genuinely novel intent (zero presence in this window) still
# reads as a natural escape. 12 covers 4+ full alternations of the full pair.
_RECENT_SELECTION_RING_SIZE = 12

# Intent types that are evidence-gathering by design — their no-action cycles
# are deliberate EXPLORATION, not a pathology. Mirrors the EvidenceProvenanceValidator's
# `_INQUIRY_TYPES`: inquiry is never penalised (Λ6.5). The stagnation armer must
# NOT force-escape these, or it would preempt the firewall's own action_loop
# recovery AND stomp legitimate curiosity. The governor-starvation escape is
# reserved for NON-inquiry types (e.g. plan_trajectory) stuck in no-action.
# Canonical intent-type sets (Λ6.5 — one source of truth; the council's
# evidence advisor reads the same module).
from telos.core.governance.recovery_types import (
    STAGNATION_EXEMPT_INQUIRY_TYPES,
    STAGNATION_EXEMPT_RECOVERY_TYPES,
    GOVERNANCE_SUPPRESSION_REASONS,
)


from telos.core.governance.firewall import (
    DecisionFirewall, FirewallConfig, RECOVERY_AFTER_LOOP_BLOCKS,
)
from telos.core.governance.human_gateway import HumanGateway
from telos.core.context.summarizer import ContextSummarizer
from telos.core.context.tiered import TieredContext
from telos.core.genesis import ANCHOR
from telos.core.attention.token_budget import TokenBudgetManager
from telos.core.ui.status import ThinkingDisplay
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
from telos.core.reasoning.energy.cognitive_energy import CognitiveEnergy
from telos.core.reasoning.confidence.dual_confidence import DualConfidence
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
        # Research Amplification Gate (Λ6.5): the standing pre-PERCEIVE stage.
        # Constructed ONLY when enabled (research_gate != off/legacy) so a
        # default pipeline carries zero new state — byte-identical behavior.
        gate_mode = getattr(self.config, 'research_gate', 'off')
        self._research_gate: Optional[ResearchAmplificationGate] = None
        if gate_mode not in ("off", "legacy"):
            self._research_gate = ResearchAmplificationGate()
        from telos.world.epistemic import RealityGapTracker
        # TELOS v6 Phase 4/7: per-model reality-gap tracker feeding model_fidelity
        # into capability authorization. Untested model -> fidelity None -> the
        # model_fidelity gate cannot claim PASS without validation.
        self._reality_gap_tracker = RealityGapTracker()
        self._pending_reality_gap: Optional[tuple] = None  # (one-step-prediction, cycle)
        self._council_intent_history: Dict[str, int] = {}
        self._council_total_no_action: Dict[str, int] = {}
        self._council_recent_blocks: int = 0
        self.budget_manager = BudgetManager(self.config.compute_budget_ms)
        self.streams: List[CognitiveStream] = []
        self.council = Council()
        self.ledger = WorldLedger()
        self.planning_horizon = PlanningHorizon()
        self._trust_manager = TrustManager()
        self._readiness = InformationReadinessEngine()
        self._firewall = DecisionFirewall()
        # Λ3.1 Recovery Mode: goal-seek escape from firewall loop traps.
        # Set when the firewall blocks the same intent type 2+ consecutive
        # cycles (action_loop); consumed by the select phase to inject a
        # differently-typed recovery intent next cycle. The firewall is
        # never overridden — the recovery intent passes every check.
        self._recovery_goal_seek_pending: bool = False
        self._recovery_looped_type: Optional[str] = None
        self._recovery_armed_cycle: Optional[int] = None
        self._recovery_reason: Optional[str] = None
        # Λ3.1 loop family ledger (selection-level): rolling ring of the most
        # recent SELECTED intent types — the canonical source
        # `_selection_in_loop_family` consults FIRST. Unlike the firewall's
        # `_action_history`, it records types that blocked BEFORE Check 5
        # (e.g. `blended_inquiry` at Check 2 low_integrity), which never
        # survive to the firewall window — the [4,1] lockout's exact blind
        # spot. Ring keeps the last RECENT_SELECTION_RING_SIZE selections.
        self._recent_selected_types: List[str] = []
        # Λ3.1 stagnation escape: consecutive cycles where NO action vector was
        # emitted (governor/firewall no-action loops, not just firewall
        # action_loop traps). Arms the same goal-seek escape with a recorded
        # reason; resets the moment an action flows. Per-family ledger:
        # `_stagnant_no_action` per intent type (a partner type's exempt
        # cycle must not reset the stalled type's accumulation — the [4,1]
        # counter-neutralization). `_stagnant_no_action_cycles` is the MAX
        # across families = the most-arrested type's dwell.
        self._stagnant_no_action: Dict[str, int] = {}
        self._stagnant_no_action_cycles: int = 0
        # Flag that records whether the CURRENTLY armed recovery was triggered
        # by no-action STAGNATION (governor-driven) rather than a firewall
        # action_loop trap. The injection guards must honour this independently
        # of the firewall counter — a governor no-action loop never increments
        # firewall.consecutive_loop_blocks, so gating injection on the firewall
        # counter would arm-but-never-inject the stagnation escape.
        self._recovery_stagnation_armed: bool = False
        from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
        # P1: no silent 'gridworld' default — the adapter MUST declare its name.
        # If an adapter is present it must expose `name` (now abstract on the
        # DomainAdapter ABC); a missing name fails loudly, never defaults.
        if self.config.adapter is not None:
            adapter_name = self.config.adapter.name
        else:
            adapter_name = "unconfigured"
        self._infra_manager = InfrastructureManager(domain=adapter_name)
        # B3: Register callbacks for council blocks and recovery events
        self._infra_manager.on_council_block(self._on_council_block)
        self._infra_manager.on_recovery_event(self._on_recovery_event)
        self._cycle_count: int = 0
        # Pattern: one RNG authority per engine — the pipeline owns a private
        # RandomState so phases (e.g. SelectPhase random-walk angles) never
        # read the shared global np.random stream.
        self._rng = np.random.RandomState(self.config.deterministic_seed)
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
        self._checkpointer = None
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
        from telos.core.pipeline_builder import build_pipeline_components
        comps = build_pipeline_components(self.config, self._infra_manager, self._skill_library)
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
        self._meta_time = MetaTime()
        self._representation_search = RepresentationSearch()
        # Insights 1-20: Ecology, Research, Genealogy, Discovery OS
        self._ecosystem = Ecosystem()
        self._research_seasons = ResearchSeasons()
        self._discovery_rate = DiscoveryRateTracker()
        self._research_debt = ResearchDebtTracker()
        self._belief_capital = BeliefCapitalMarket()
        self._theory_genealogy = TheoryGenealogy()
        # Live genealogy: TheoryBuilder registers promoted theories; the
        # knowledge linker resolves names and links nodes to theories.
        self._theory_builder.set_genealogy(self._theory_genealogy)
        km = getattr(self._infra_manager, 'knowledge_mgr', None)
        if km is not None:
            km.attach_genealogy(self._theory_genealogy)
            self._theory_builder.set_promotion_hook(km.link_promoted_theory)
        self._discovery_orchestrator = DiscoveryOrchestrator()
        self._identity_core = IdentityCore()
        # Identity↔Knowledge wiring (Gap 1): the IdentityBridge connects the
        # MUTABLE identity layers (IdentityNarrative/IdentityState) to the
        # KnowledgeGraph + KnowledgeLinker. IdentityCore stays frozen — the
        # bridge only reads it as a provenance anchor (system_self.py:44-45).
        _km = getattr(self._infra_manager, 'knowledge_mgr', None)
        self._identity_bridge = IdentityBridge(
            system_self=getattr(self._infra_manager, 'system_self', None),
            knowledge=getattr(_km, 'knowledge', None) if _km is not None else None,
            linker=getattr(_km, 'linker', None) if _km is not None else None,
            identity_core=self._identity_core,
        )
        self._mission_portfolio = MissionPortfolio()
        self._mission_arbiter = MissionArbiter()
        self._mission_lifecycle = MissionLifecycleEngine()
        self._distributed_council = DistributedCouncil()
        self._distributed_council.register_default_crew()
        self._autonomous_explorer = AutonomousExplorer(
            curiosity=self._curiosity_drive,
            unknown_unknown=self._unknown_unknown_detector,
        )

        if self.config.checkpoint_path:
            from telos.core.infra_manager.checkpoint_manager import CheckpointManager
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
                        except Exception as e:
                            logger.warning("runtime.py: swallowed error: %r", e)

        if self.config.knowledge_path:
            self._infra_manager.knowledge.load(self.config.knowledge_path)

        # Rebind identity nodes into the linker registry after any graph
        # reconstruction (checkpoint restore / knowledge load) — Λ4.10.
        try:
            if getattr(self, '_identity_bridge', None) is not None:
                self._identity_bridge.rebind_from_graph()
        except Exception as e:
            logger.warning("runtime.py: swallowed error: %r", e)

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

        # Cross-session learning: load previous session context and learnings
        inject_into_context(self)
        prev = load_learnings()
        if prev:
            logger.info(f"Loaded cross-session learnings from {prev.session_id}: "
                        f"{len(prev.top_skills)} skills, {len(prev.top_theories)} theories")

    def register_stream(self, stream: CognitiveStream) -> None:
        # v7 K: fast mode also halves the planning stream's world budget
        # (the stream's own default is 30 worlds/cycle) — the simulation
        # budget is a per-mode policy, not a per-stream constant.
        if self.config.is_fast_mode and hasattr(stream, "configure")                 and getattr(stream, "n_worlds", None):
            try:
                stream.configure(n_worlds=max(1, int(stream.n_worlds) // 2))
            except Exception as e:
                logger.warning("stream fast-mode configure failed: %r", e)
        self.streams.append(stream)
        self.streams.sort(key=lambda s: s.priority, reverse=True)
        # P1.4: Auto-register with trust manager so auth checks work
        bypass = stream.priority > 0.9
        self._trust_manager.register_stream(
            stream_name=stream.__class__.__name__,
            can_bypass_readiness=bypass,
        )

    def register_validator(self, validator) -> None:
        """Register a Council advisor.

        Args:
            validator: a Validator instance to add to the blocking council.
        """
        self.council.register(validator)

    @property
    def research_gate(self) -> Optional[ResearchAmplificationGate]:
        """The pipeline's ResearchAmplificationGate instance.

        None when the config knob is off/legacy (the default) — existing
        callers see no gate at all. When report/require is configured, a
        caller attaches its run's evidence base here (via
        attach_research_evidence) before execute() so the pre-PERCEIVE gate
        can judge 7/7-dimension external grounding (Λ6.5).

        Returns:
            The gate instance, or None when the knob is disabled.
        """
        return self._research_gate

    def attach_research_evidence(self, sources, claims) -> None:
        """Attach the run's external evidence base to the gate.

        Sources must be registered BEFORE the claims that reference them
        (Λ6.5: every claim needs a named source) and every claim dimension
        must be one of the 7 mandatory dimensions. Raises ValueError when the
        knob is off/legacy (no gate exists — evidence has nowhere to go and a
        silent no-op would be the diagnosed bounded-evidence-mode failure).

        Args:
            sources: iterable of EvidenceSource to register.
            claims: iterable of EvidenceClaim mapped to mandatory dimensions.

        Raises:
            ValueError: gate disabled, duplicate source_id, claim referencing
                an unknown source, or claim on a non-mandatory dimension.
        """
        gate = self._research_gate
        if gate is None:
            raise ValueError(
                "research_gate is off/legacy — set PipelineConfig("
                "research_gate='report'|'require') before attaching evidence"
            )
        for src in sources:
            gate.register_source(src)
        for claim in claims:
            gate.register_claim(claim)

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
        """Default no-op chat function when no LLM is configured.

        Args:
            messages: the prompt messages (ignored).

        Returns:
            An empty JSON object string.
        """
        return '{}'


    # ── Bitcoin-inspired Decision Timelocks ──────────────────────────────────
    def _apply_timelock_penalties(self, ctx) -> None:
        """Deprioritize intent types selected within the timelock window.

        Prevents flip-flopping between competing intents. Called during
        pipeline execution, after EVALUATE and before SELECT phase.

        Args:
            ctx: the phase context (reads ctx.intents, writes ctx.intents).
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
    
    def _update_loop_recovery_state(self, ctx) -> None:
        """Arm/disarm the goal-seek recovery after the act phase settles.

        Reads the REAL firewall verdict from this cycle: a block by
        'action_loop' with the firewall's own consecutive-block counter at
        the recovery threshold arms the next select phase to inject a
        differently-typed goal-seek intent. Any other outcome disarms it —
        recovery is only for genuine loop traps, never for other blocks.

        Args:
            ctx: the phase context (firewall verdict already computed).
        """
        fw = self._firewall
        verdict = getattr(ctx, 'firewall_verdict', None)
        blocked_by = getattr(verdict, 'blocked_by', None) if verdict is not None else None
        if (ctx.firewall_blocked and blocked_by == "action_loop"
                and getattr(fw, 'consecutive_loop_blocks', 0) >= RECOVERY_AFTER_LOOP_BLOCKS):
            self._recovery_goal_seek_pending = True
            self._recovery_armed_cycle = ctx.cycle_count
            self._recovery_looped_type = (
                ctx.selected_intent.intent_type if ctx.selected_intent else None
            )
            logger.info(
                f"Cycle {ctx.cycle_count}: firewall loop trap detected "
                f"({fw.consecutive_loop_blocks} consecutive action_loop blocks on "
                f"'{self._recovery_looped_type}') — goal-seek recovery armed (Λ3.1)"
            )
        else:
            self._recovery_goal_seek_pending = False

    def _intent_history_for_council(self, ctx) -> Dict[str, Any]:
        """Fold the system's falsification record into a per-cycle evidence
        context the council's EvidenceProvenanceValidator can read.

        Reports, for the SELECTED intent type: how many consecutive no-action
        cycles it has endured (the stagnation signal), its total no-action
        count, and its recent blocked cycles. Combined with the
        RealityGapTracker (passed separately) this is the decision-provenance-
        as-evidence record (Lambda 6.5).

        Args:
            ctx: the phase context for this cycle (selected intent etc.).
        """
        intent = ctx.selected_intent
        i_type = intent.intent_type if intent else "unknown"
        # Track per-cycle intent outcomes in a small rolling history.
        history = getattr(self, '_council_intent_history', {})
        total_no_action = getattr(self, '_council_total_no_action', {})
        total_no_action[i_type] = total_no_action.get(i_type, 0)
        recent_blocks = getattr(self, '_council_recent_blocks', 0)
        if ctx.cycle_count % 2 == 0:
            recent_blocks = max(0, recent_blocks - 1)
        return {
            "intent_history": {
                "intent_type": i_type,
                "consecutive_no_action": self._stagnant_no_action_cycles,
                "total_no_action": int(total_no_action.get(i_type, 0)),
                "recent_blocks": int(recent_blocks),
            },
            "reality_gap_tracker": self._reality_gap_tracker,
            "cycle_count": ctx.cycle_count,
        }

    def _update_stagnation_recovery_state(self, ctx) -> None:
        """Λ3.1 extension: arm goal-seek recovery for NO-ACTION stagnation.

        The firewall-based recovery (`_update_loop_recovery_state`) only arms
        on `action_loop` firewall blocks. A governor-driven no-action loop
        (DI floored / MD inflated by unexecutable predictions) never triggers
        it, so the agent can sit in `blended_inquiry` forever emitting
        `action_taken=null`. This tracks consecutive cycles where NO action
        vector was emitted; at the threshold it arms the SAME goal-seek escape
        with a recorded reason so the select phase injects a differently-typed,
        executable recovery intent. Genuine blocks are never overridden - the
        recovery intent passes the council/firewall/governor like any other.

        Args:
            ctx: the phase context to inspect for the cycle's action outcome.
        """
        cur_type = ctx.selected_intent.intent_type if ctx.selected_intent else None
        if ctx.selected_action is not None and not getattr(ctx, 'no_action', False):
            self._stagnant_no_action = {}
            self._stagnant_no_action_cycles = 0
            # An action flowed, so no stagnation loop is active — clear the
            # stagnation-armed flag (if a firewall trap were also active,
            # _update_loop_recovery_state manages its own arming).
            self._recovery_stagnation_armed = False
            return
        # Per-family no-action accumulation: this cycle belongs to `cur_type`
        # only. A partner type's no-action cycle (e.g. curiosity_explore's
        # action_loop block) must NOT reset a sibling stalled type's ledger
        # (blended_inquiry's low_integrity stall) — the [4,1] lockout was the
        # two escape paths resetting each other's counter FOREVER so neither
        # ever reached its arming threshold.
        if cur_type:
            self._stagnant_no_action[cur_type] = self._stagnant_no_action.get(cur_type, 0) + 1
        # Do NOT force-escape inquiry types nor recovery intents: their cycles
        # are deliberate exploration / an active escape, not a no-action
        # pathology (Λ6.5, mirrors the EvidenceProvenanceValidator exemption).
        # Force-escaping them would stomp curiosity, re-arm stagnation right
        # after a recovery, and preempt the firewall's own action_loop path.
        if cur_type in STAGNATION_EXEMPT_INQUIRY_TYPES or \
                cur_type in STAGNATION_EXEMPT_RECOVERY_TYPES:
            # Distinguish a DELIBERATE explore-pause from a BLOCKED retry
            # (Λ6.5): the exemption applies to a genuinely approved exploration
            # dwell, NOT to a cycle that was actively STALLED by a non-loop
            # firewall block (e.g. `low_integrity`). A `low_integrity` block
            # happens at Check 2, BEFORE the firewall's loop detection, so its
            # `_block` resets the action_loop recovery counter and the
            # action_loop recovery can NEVER arm — an inquiry type stalled
            # that way is a stuck retry with NO other escape path, so
            # stagnation must arm the goal-seek escape for it instead. Blocks
            # at `action_loop` (or genuine unblocked exploration) keep the
            # exemption: the firewall itself owns that escape path.
            verdict = getattr(ctx, 'firewall_verdict', None)
            blocked_by = getattr(verdict, 'blocked_by', None) if verdict is not None else None
            stalled_by_block = (
                getattr(ctx, 'firewall_blocked', False)
                and blocked_by is not None and blocked_by != "action_loop"
            )
            if not stalled_by_block:
                # This type's own exempt dwell is not a stagnation pathology —
                # reset ONLY its own ledger slot (a sibling's slot is theirs).
                if cur_type:
                    self._stagnant_no_action.pop(cur_type, None)
                self._stagnant_no_action_cycles = max(
                    self._stagnant_no_action.values(), default=0)
                return
        self._stagnant_no_action_cycles = max(
            self._stagnant_no_action.values(), default=0)
        if self._stagnant_no_action_cycles >= STAGNATION_RECOVERY_AFTER:
            self._recovery_goal_seek_pending = True
            self._recovery_stagnation_armed = True  # governor no-action loop (not firewall) armed the escape
            self._recovery_armed_cycle = ctx.cycle_count
            self._recovery_looped_type = (
                ctx.selected_intent.intent_type if ctx.selected_intent else None
            )
            self._recovery_reason = "no_action_stagnation"
            logger.warning(
                f"Cycle {ctx.cycle_count}: {self._stagnant_no_action_cycles} consecutive "
                f"no-action cycles on '{self._recovery_looped_type}' - goal-seek "
                f"recovery armed for stagnation (Λ3.1)"
            )

    @staticmethod
    def _option_intent_type(option: Any) -> Optional[str]:
        """Extract a real intent-type label from a simulated StrategicOption.

        StrategicOptions are dataclasses (no ``.get``), so any dict-style
        access raises AttributeError. Reads the option's world/metadata for a
        genuine intent label, and returns None (never a fabricated string)
        when none is present.

        Args:
            option: a StrategicOption (or any object with world/metadata).

        Returns:
            The intent type string if present, else None.
        """
        if option is None:
            return None
        world = getattr(option, 'world', None)
        wmd = getattr(world, 'metadata', None) or {}
        if isinstance(wmd, dict):
            it = wmd.get('intent') or wmd.get('intent_type')
            if it:
                return str(it)
        omd = getattr(option, 'metadata', None) or {}
        if isinstance(omd, dict):
            it = omd.get('intent') or omd.get('intent_type')
            if it:
                return str(it)
        return None

    def _run_research_amplification_gate(self, ctx) -> None:
        """Run the pre-PERCEIVE Research Amplification Gate for this cycle.

        The gate's verdict is attached to the context (and therefore the
        DecisionTrace via build_trace) truthfully in BOTH active modes:
        report and require. report never blocks — a run with zero or partial
        external grounding carries an honest LEFT verdict in its trace but
        still executes. require blocks the run BEFORE any stream or
        simulation consumes the brief when grounding is missing — the
        structural fix for bounded-evidence-mode: answering under a coverage
        gap is LEFT, never a silent pass and never fabricated grounding.

        Args:
            ctx: the phase context for this cycle (writes
                ctx.amplification_report and, in require mode on a gap,
                ctx.research_gate_left / ctx.governance_blocked /
                ctx.blocking_reason).
        """
        report = self._research_gate.run()
        ctx.amplification_report = report.to_dict()
        if report.passed:
            return
        logger.warning(
            f"Cycle {ctx.cycle_count}: ResearchAmplificationGate LEFT — "
            f"missing={report.missing_dimensions}"
        )
        if getattr(self.config, 'research_gate', 'off') == "require":
            ctx.research_gate_left = True
            ctx.governance_blocked = True
            ctx.blocking_reason = f"research_amplification_left:{report.reason}"

    def _selection_in_loop_family(self, intent_type: Optional[str]) -> bool:
        """Is this intent type part of the RECENTLY SELECTED trap family?

        The trap is a FAMILY of types the system recently SELECTED, not a
        single stored looped type: the alternation pair
        (curiosity_explore <-> blended_inquiry) each break the 4-same-type
        run, so gating on `current == looped` alone let the alternation
        consume the one-shot arming WITHOUT ever injecting the escape.

        PRIMARY source: the runtime's own recent-SELECTION ring
        (`_recent_selected_types`). `blended_inquiry` blocks at the
        firewall's Check 2 (low_integrity dissent) — BEFORE Check 5 appends
        to the firewall's `_action_history` — so it can NEVER appear in the
        firewall window even though it IS the cycle-to-cycle trap member.
        Judging it "a genuinely NEW type / natural escape" is the exact
        blind spot that let the arming consume without injecting (the
        [4,1] 100% lockout). The selection ring sees every selected type
        regardless of where it later blocked.

        SECONDARY source: the firewall's action-retention window (types that
        survived to an action_loop block) plus the stored looped type —
        defense in depth for the cases selection tracking spans.

        Replacing any family member with the designed escape is trap
        continuation, never stomping. Only a type with ZERO presence in the
        recent selection ring (and firewall window) is a genuine natural
        escape worth not stomping.

        Args:
            intent_type: the candidate selection's intent type.

        Returns:
            True when the type is in the recent-selection / loop family.
        """
        if not intent_type:
            return False
        # PRIMARY: the runtime's own recent-selection ring (per-cycle
        # appended in the select synthesis path). This is the ONE canonical
        # family ledger — recovery_types-style one truth.
        recent = list(getattr(self, '_recent_selected_types', []))
        if intent_type in recent:
            return True
        # SECONDARY: firewall window + stored looped type.
        history = list(getattr(self._firewall, '_action_history', []))
        if intent_type in history:
            return True
        # Defense in depth: the stored looped type is the trap's PRIMARY type
        # even if history currently lacks it (e.g. a recovery spell flushed the
        # window). Re-selecting the recorded looped type is trap continuation.
        return intent_type == self._recovery_looped_type

    def _maybe_inject_recovery_intent(self, ctx) -> None:

        """Select-phase recovery (Λ3.1): break a firewall action_loop trap.

        When the previous cycle ended on a loop block at the recovery
        threshold AND the streams are about to re-select the SAME looped
        intent type (or produced no intent), replace it with a
        'goal_seek_recovery' intent whose type differs from the looped one,
        so the firewall's same-intent detector history window breaks and
        the agent can move again. The recovery intent is validated by the
        council and the firewall like every other intent — legitimate
        blocks are never overridden.

        Args:
            ctx: the phase context (selected_intent already computed).
        """
        if not self._recovery_goal_seek_pending:
            return
        self._recovery_goal_seek_pending = False  # one-shot recovery
        fw = self._firewall
        # Escape when EITHER a firewall action_loop trap is at threshold OR the
        # escape was armed by no-action STAGNATION (governor-driven loop). The
        # firewall counter stays 0 for governor no-action loops, so gating on it
        # alone would arm-but-never-inject the stagnation escape.
        if not self._recovery_stagnation_armed and \
                getattr(fw, 'consecutive_loop_blocks', 0) < RECOVERY_AFTER_LOOP_BLOCKS:
            return  # authoritative counter says recovery is not needed
        self._recovery_stagnation_armed = False  # consumed one-shot
        looped = self._recovery_looped_type
        current = ctx.selected_intent.intent_type if ctx.selected_intent else None
        if current is not None and not self._selection_in_loop_family(current):
            # A genuinely NEW type (absent from the firewall's recent
            # retention window) is a natural escape — the trap broke on its
            # own; do not stomp it. NOTE: the council may still fall back to
            # a loop-family type afterwards (Λ4.3 alternative selection); the
            # post-council hook re-checks the FINAL intent and injects then.
            return
        from telos.intent_ir import IntentIR
        ctx.selected_intent = IntentIR(
            intent_type="goal_seek_recovery",
            confidence=0.6,
            params={
                "recovery_mode": True,
                "reason": getattr(self, "_recovery_reason", None) or "firewall_loop_recovery",
                "consecutive_loop_blocks": fw.consecutive_loop_blocks,
                "escaped_loop_type": looped,
                "stagnant_cycles": self._stagnant_no_action_cycles,
            },
            metadata={"stream": "recovery", "axiom": "3.1", "recovery": True},
        )
        ctx.recovery_goal_seek = True
        logger.info(
            f"Cycle {ctx.cycle_count}: injected goal_seek_recovery "
            f"(replacing '{looped or 'none'}', {fw.consecutive_loop_blocks} loop blocks)"
        )

    def _maybe_inject_recovery_intent_post_council(self, ctx) -> None:
        # Post-council recovery (Lambda 3.1): escape when the council's
        # Lambda 4.3 alternative fallback re-selected the looped intent type.
        # The select-phase hook sees the streams' pick, but the council can
        # swap ctx.selected_intent to a fallback alternative afterwards
        # (council.py Lambda 4.3). When the armed recovery is from the
        # PREVIOUS cycle and the FINAL intent is the looped type, replace it
        # with the goal-seek escape before act - the firewall still audits it
        # like any other action. If the final intent is genuinely different,
        # the trap already broke naturally and nothing is injected.
        armed = self._recovery_armed_cycle
        if armed is None or ctx.cycle_count - armed != 1:
            return  # recovery not armed in the immediately previous cycle
        looped = self._recovery_looped_type
        final = ctx.selected_intent.intent_type if ctx.selected_intent else None
        if final is not None and not self._selection_in_loop_family(final):
            return  # the system escaped naturally - no injection
        if final is None:
            return
        # Allow the post-council escape for BOTH armer types: a firewall
        # action_loop trap AT threshold, or a governor no-action STAGNATION
        # (firewall counter stays 0 for the latter, so gating on it alone would
        # arm-but-never-inject).
        if not self._recovery_stagnation_armed and \
                getattr(self._firewall, 'consecutive_loop_blocks', 0) < RECOVERY_AFTER_LOOP_BLOCKS:
            return  # authoritative counter says recovery is not needed
        self._recovery_stagnation_armed = False  # consumed one-shot
        from telos.intent_ir import IntentIR
        ctx.selected_intent = IntentIR(
            intent_type="goal_seek_recovery",
            confidence=0.6,
            params={
                "recovery_mode": True,
                "reason": f"{getattr(self, '_recovery_reason', None) or 'firewall_loop_recovery'}_post_council",
                "consecutive_loop_blocks": self._firewall.consecutive_loop_blocks,
                "escaped_loop_type": looped,
                "stagnant_cycles": self._stagnant_no_action_cycles,
            },
            metadata={"stream": "recovery", "axiom": "3.1", "recovery": True},
        )
        ctx.recovery_goal_seek = True
        logger.info(
            f"Cycle {ctx.cycle_count}: injected goal_seek_recovery post-council "
            f"(replacing '{looped}', {self._firewall.consecutive_loop_blocks} loop blocks)"
        )

    def _record_timelock(self, ctx, selected_intent) -> None:
        """Record the selected intent type for future timelock checks.

        Args:
            ctx: the phase context (reads ctx.cycle_count).
            selected_intent: the IntentIR that was selected this cycle.
        """
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
        """Compute resource budgets from available data (before Evaluate phase).

        Returns a dict with energy, memory, identity (partial), and recovery
        budgets. Fallback data is available early; full identity/recovery
        data is enriched later.

        Args:
            ctx: the phase context (for entropy/state data).

        Returns:
            Dict with energy/memory/identity/recovery budget sections.
        """
        identity_stability = 1.0 - getattr(self._identity_entropy, 'collapse_rate', 0.0)
        budgets = {
            "energy": {
                "consumed_ms": self.budget_manager.consumed_ms,
                "total_ms": self.budget_manager.total_budget_ms,
                "budget_carryover_ms": getattr(self.budget_manager, 'budget_carryover_ms', 0.0),
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
                 tiered_context: Optional['TieredContext'] = None,
                 episode_reset: bool = False) -> PipelineResult:
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
        # Episode reset signal (Λ6.5): the executor restarted the world at
        # origin after a goal. The previous cycle's prediction belongs to the
        # OLD world instance — comparing it against this new observation would
        # be a category error (a 5.66-step "gap" that permanently falsifies the
        # world model). Downstream (act phase) suppresses the cross-episode
        # deferred-gap record when this flag is set.
        ctx.episode_reset = bool(episode_reset)

        # ── Research Amplification Gate (Λ6.5): the standing pre-PERCEIVE
        #    stage. In report mode the verdict is attached to the context /
        #    DecisionTrace truthfully (a coverage-gapped run carries an honest
        #    LEFT report but still executes). In require mode a missing
        #    7/7-dimension external grounding marks the run LEFT BEFORE any
        #    stream or simulation consumes the brief — the phase loop below is
        #    skipped entirely, so streams/simulate never see the brief.
        if self._research_gate is not None:
            try:
                self._run_research_amplification_gate(ctx)
            except Exception as e:
                logger.warning("runtime.py: research amplification gate failed: %r", e)

        if getattr(ctx, 'research_gate_left', False):
            logger.warning(
                f"Cycle {self._cycle_count}: run LEFT at the research "
                f"amplification gate — no stream/simulation consumed the brief"
            )

        phases = self._phases if not getattr(ctx, 'research_gate_left', False) else []
        # ── Per-cycle watchdog: wall-clock deadline at every phase boundary ──
        # Catches slow-but-returning phases (serialization stalls, O(n²)
        # rescans) instead of letting them hang the producer thread. A
        # single wedged C-level call cannot be preempted from a Python
        # thread — this is documented as an honest limitation.
        # Env read hoisted: ONE lookup per cycle (was 3 per phase x 9 phases
        # for the watchdog's pre/post checks — env lookups are dict hits, but
        # per-cycle there is no reason to re-read a value that cannot change).
        _cycle_timeout_s = float(os.environ.get(
            'TELOS_CYCLE_TIMEOUT_MS', '5000')) / 1000.0
        _cycle_deadline = time.monotonic() + _cycle_timeout_s
        _cycle_timeout_ms = _cycle_timeout_s * 1000.0
        # v9: identity-tuple dump gate — ONE env lookup per cycle (same
        # hoist discipline as the watchdog reads above). Default 0 = never;
        # N > 0 dumps every Nth cycle (diagnostics opt-in).
        _identity_dump_every_n = int(os.environ.get(
            'TELOS_IDENTITY_TUPLE_EVERY_N', '0') or 0)
        for phase in phases:
            # Check deadline before each phase
            if time.monotonic() > _cycle_deadline:
                logger.error(
                    "Cycle %d: WATCHDOG triggered before phase '%s' — "
                    "deadline %sms exceeded (cycle_timeout)",
                    self._cycle_count, phase.name, _cycle_timeout_ms,
                )
                ctx.governance_blocked = True
                ctx.blocking_reason = f"cycle_timeout:before:{phase.name}"
                if hasattr(ctx, '_phase_timings'):
                    ctx._phase_timings['watchdog_interrupted'] = _cycle_timeout_ms
                break
            self._display.on_phase_start(phase.name)
            _phase_start = time.monotonic()
            try:
                phase.execute(self, ctx)
            except Exception as e:
                logger.critical(f"Phase '{phase.name}' crashed: {e}", exc_info=True)
                ctx.governance_blocked = True
                ctx.blocking_reason = f"phase_crash:{phase.name}:{str(e)[:50]}"
                if hasattr(self, '_telemetry'):
                    self._telemetry.record_phase_failure(phase.name, str(e))
                break
            _phase_elapsed = time.monotonic() - _phase_start
            if _phase_elapsed > _cycle_timeout_s:
                logger.error(
                    "Cycle %d: WATCHDOG triggered after phase '%s' (%.1fms) — "
                    "deadline exceeded (cycle_timeout)",
                    self._cycle_count, phase.name, _phase_elapsed * 1000,
                )
                ctx.governance_blocked = True
                ctx.blocking_reason = f"cycle_timeout:after:{phase.name}"
                if hasattr(ctx, '_phase_timings'):
                    ctx._phase_timings[phase.name] = _phase_elapsed * 1000
                    ctx._phase_timings['watchdog_interrupted'] = _phase_elapsed * 1000
                break

            if phase.name == "simulate":
                try:
                    if hasattr(ctx, 'sim_options') and ctx.sim_options:
                        tb = self._theory_builder
                        for opt in ctx.sim_options[:5]:
                            tb.observe_outcome(outcome=getattr(opt, 'score', 0.5),
                                               context=str(getattr(opt, 'trajectory', ''))[:80])
                except Exception as e:
                    logger.warning(f"TheoryBuilder.observe_outcome (simulate) failed: {e}")

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

                # Autonomous exploration goals from curiosity + unknown unknowns
                if self._autonomous_explorer.should_explore:
                    goals = self._autonomous_explorer.generate_goals(ctx.cycle_count)
                    if goals:
                        from telos.intent_ir import IntentIR
                        for g in goals[:2]:
                            exp_intent = IntentIR(
                                intent_type=f"explore_{g.source}",
                                confidence=g.priority,
                                params={"source": g.source, "description": g.description},
                                metadata={"stream": "curiosity", "autonomous": True},
                            )
                            ctx.intents.append((exp_intent, g.priority * 0.5))
                            logger.info(
                                f"AutonomousExplorer: '{g.description[:40]}'"
                            )

            if phase.name == "streams":
                try:
                    iu = self._identity_utility
                    profile = iu.active_profile
                    if profile is not None:
                        iu.compute_utility(dimension_scores={
                            "exploration": getattr(ctx, 'curiosity_bonus', 0.5),
                            "correctness": 0.5, "safety": 0.5,
                            "efficiency": 0.5, "coherence": 0.5,
                        }, identity_markers=list(profile.identity_markers)[:3] if hasattr(profile, 'identity_markers') else None)
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

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
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            # ── v2: UnknownUnknownDetector — find blind spots after perception ──
            if phase.name == "perceive":
                try:
                    observation = getattr(ctx, 'world', None)
                    if observation is not None:
                        novelty = self._unknown_unknown_detector.detect(observation, self._cycle_count)
                        if novelty:
                            logger.info(f"[v2] Novelty cluster detected: {novelty.get('question', '')[:60]}")
                            ctx._novelty_question = novelty.get("question")
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            if phase.name == "perceive":
                try:
                    self._assumption_auditor.auto_audit(
                        ctx.cycle_count,
                        curiosity_level=float(getattr(ctx, "curiosity_bonus", 0.5)),
                    )
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

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
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            if phase.name == "evaluate":
                try:
                    iu = self._identity_utility
                    profile = iu.active_profile
                    if profile is not None:
                        conf = ctx.selected_intent.confidence if ctx.selected_intent else 0.5
                        iu.compute_utility(dimension_scores={
                            "exploration": 0.5, "correctness": conf,
                            "safety": 0.6, "efficiency": 0.4, "coherence": 0.5,
                        }, identity_markers=list(profile.identity_markers)[:3] if hasattr(profile, 'identity_markers') else None)
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            # ── Project Context: wire cognitive processes into active project ──
            if phase.name == "select":
                try:
                    pp = self._project_portfolio
                    if pp:
                        active_proj = pp.active_project
                        if active_proj:
                            active_proj.set_cognitive_context(self)
                            ctx.project_context = {
                                "project_id": active_proj.id,
                                "name": active_proj.name,
                                "stagnation": active_proj.stagnation_cycles,
                            }
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            # ── Identity Modeling (parallel track): update identity before select ──
            if phase.name == "select":
                try:
                    # Root-cause fix: `self._system_self` was never assigned, so
                    # this whole block was dead code (AttributeError swallowed
                    # every cycle). The real SystemSelf lives on infra_manager;
                    # it has no update()/get_state() — use its actual API.
                    ss = getattr(self._infra_manager, 'system_self', None)
                    if ss is not None:
                        ctx.identity_state = ss.to_dict()
                    # IdentityBridge: record this cycle's self-state into the
                    # connected knowledge web (Λ4.1 × Λ4.10 × Λ6.7)
                    ib = getattr(self, '_identity_bridge', None)
                    if ib is not None and ss is not None:
                        di_v = getattr(ctx.verdict, 'decision_integrity', 1.0) if ctx.verdict else 1.0
                        md_v = getattr(ctx.verdict, 'mission_drift', 0.0) if ctx.verdict else 0.0
                        node_id = ib.sync(
                            cycle=ctx.cycle_count, di=di_v, md=md_v,
                            selected_intent=ctx.selected_intent.intent_type
                            if ctx.selected_intent else "none",
                        )
                        ib.link_markers_to_knowledge()
                        if node_id:
                            ctx._identity_knowledge_node = node_id
                    # Identity entropy refresh
                    ie = self._identity_entropy
                    if ie is not None:
                        n_options = len(getattr(ctx, 'sim_options', []) or [])
                        ie.record(max(1, n_options))
                        ctx.identity_entropy = ie.collapse_rate
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

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

            # ── Λ3.1 Recovery Mode: goal-seek escape (firewall loop trap) ──
            if phase.name == "select":
                try:
                    self._maybe_inject_recovery_intent(ctx)
                except Exception as e:
                    logger.warning("runtime.py: recovery intent injection failed: %r", e)

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

            if phase.name == "select":
                try:
                    if ctx.selected_intent:
                        alts = [
                            self._option_intent_type(o)
                            for o in getattr(ctx, 'sim_options', [])[:3]
                        ]
                        alts = [a for a in alts if a]
                        mean_regret, count = self._regret_memory.get_regret_by_type(
                            ctx.selected_intent.intent_type)
                        if count:
                            ctx.regret_scores = {
                                "chosen_intent": ctx.selected_intent.intent_type,
                                "mean_regret": mean_regret,
                                "n_records": count,
                                "alternatives": alts,
                            }
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            if phase.name == "select":
                try:
                    if ctx.selected_intent:
                        self._interpretation_engine.record_outcome(
                            conflict_id=f"cycle_{ctx.cycle_count}",
                            outcome_quality=ctx.selected_intent.confidence)
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            # ── Confirm/reject from mempool after council phase ──
            if phase.name == "council":
                intent_id = getattr(ctx, '_mempool_intent_id', None)
                if intent_id:
                    if getattr(ctx, 'verdict', None) and ctx.verdict.validated:
                        self._mempool.confirm(intent_id)
                    else:
                        reason = getattr(ctx.verdict, 'blocking_reason', 'council_blocked') if ctx.verdict else 'council_blocked'
                        self._mempool.reject(intent_id, reason=reason)

            if phase.name == "council":
                try:
                    signals = []
                    if ctx.verdict:
                        for s in ctx.verdict.signals:
                            signals.append({"validator_name": s.validator_name, "passed": s.passed,
                                            "confidence": s.confidence, "reason": s.reason,
                                            "evidence_weight": getattr(s, 'evidence_weight', 0.5)})
                    wb = getattr(ctx, 'council_blocked', False)
                    di = ctx.verdict.decision_integrity if ctx.verdict else 1.0
                    md = ctx.verdict.mission_drift if ctx.verdict else 0.0
                    # `reflect` is the CouncilReflector's real per-decision
                    # recording API (the old call used a method that only
                    # exists on the inner ValidatorTrackRecord, so it raised
                    # AttributeError and was swallowed every cycle).
                    reflection = self._council_reflector.reflect(
                        cycle=ctx.cycle_count,
                        selected_intent=(ctx.selected_intent.intent_type
                                         if ctx.selected_intent else "unknown"),
                        validator_signals=signals,
                        predicted_di=di, actual_di=di,
                        predicted_md=md, actual_md=md,
                        was_blocked=wb,
                        outcome_success=not wb,
                    )
                    ctx._council_reflection = reflection
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            if phase.name == "council":
                try:
                    self.council._evidence_context = self._intent_history_for_council(ctx)
                except Exception as e:
                    logger.warning("runtime.py: evidence-context threading failed: %r", e)

            # ── Λ3.1 Recovery Mode (post-council): the council's Λ4.3
            #    alternative fallback may have re-selected the looped intent
            #    type AFTER the select-phase injection hook ran. Re-check the
            #    FINAL intent here and inject the goal-seek escape when the
            #    trap is still in place — the firewall still audits it at act. ──
            if phase.name == "council":
                try:
                    self._maybe_inject_recovery_intent_post_council(ctx)
                except Exception as e:
                    logger.warning("runtime.py: post-council recovery injection failed: %r", e)
                # ── Loop-family ledger (Λ3.1, selection-level): record the
                #    FINAL selected intent for this cycle into the rolling
                #    recent-selection ring AFTER the post-council hook settles
                #    (so recovery swaps are captured too). This is the
                #    canonical family source `_selection_in_loop_family`
                #    consults first — it sees types that blocked before the
                #    firewall window (Check 2 low_integrity) and would
                #    otherwise be judged a "natural escape" (the [4,1]
                #    lockout blind spot). Ring is bounded: oldest-first.
                try:
                    final_type = ctx.selected_intent.intent_type if ctx.selected_intent else None
                    if final_type:
                        self._recent_selected_types.append(final_type)
                        if len(self._recent_selected_types) > _RECENT_SELECTION_RING_SIZE:
                            del self._recent_selected_types[0]
                except Exception as e:
                    logger.warning("runtime.py: loop-family ledger update failed: %r", e)

            # ── Distributed Council: advisory crew review after the council
            #    phase settles (mempool confirm/reject already done) ──
            if phase.name == "council":
                try:
                    if not self.config.skip_advisory_layers:
                        self._run_distributed_council(ctx)
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

            # ── Λ3.1 Recovery Mode: arm goal-seek escape when the firewall
            #    blocks the same intent twice in a row (action_loop). The
            #    block itself is NEVER overridden — this only informs the
            #    next cycle's selection. ──
            if phase.name == "act":
                try:
                    self._update_loop_recovery_state(ctx)
                except Exception as e:
                    logger.warning("runtime.py: loop-recovery state update failed: %r", e)
                    self._recovery_goal_seek_pending = False
                try:
                    self._update_stagnation_recovery_state(ctx)
                    # Fold the OUTCOME into the council's falsification ledger:
                    # only genuinely blocked cycles count as blocks; no-action
                    # cycles (action_taken==None) accumulate per intent type.
                    i_type = (ctx.selected_intent.intent_type
                              if ctx.selected_intent else "unknown")
                    total_na = self._council_total_no_action.setdefault(i_type, 0)
                    if ctx.selected_action is None and not getattr(ctx, 'no_action', False):
                        self._council_total_no_action[i_type] = total_na + 1
                    if ctx.firewall_blocked or ctx.council_blocked:
                        self._council_recent_blocks = getattr(self, '_council_recent_blocks', 0) + 1
                except Exception as e:
                    logger.warning("runtime.py: stagnation-recovery state update failed: %r", e)

            # ── Law of Attention: Record trajectory after ACT phase ──
            if phase.name == "act":
                # Record trajectory divergence (predicted vs actual state)
                predicted = getattr(ctx, 'predicted_state', None)
                if predicted is not None:
                    self._attention_engine.record_trajectory_divergence(predicted, ctx.state)

                # ── TELOS v6 Phase 4/7: record reality gap (predicted vs observed)
                #    per model so model_fidelity feeds capability authorization.
                #    Only record on a validated act cycle (an action was emitted),
                #    mirroring the trajectory-divergence recording above. ──
                # The canonical rule (Λ6.5): a prediction exists ONLY for an
                # executed action. `predicted_state` is set by the simulate
                # phase to a counterfactual horizon-end future even on cycles
                # the firewall/governor then BLOCK — storing that phantom as a
                # per-step prediction and comparing it next cycle fabricated a
                # 1.5-2.5 fake gap every blocked cycle, pinning model_fidelity
                # at 0 and governor-DEFERing ~65% of cycles (the leak that
                # turned a broken plateau into a permanent crawl). Gating on
                # `selected_action is not None` inverts the default: only an
                # action that genuinely executed can falsify anything; a
                # blocked cycle predicts nothing and stays quiet.
                try:
                    # Deferred one-cycle-ahead comparison: the reality gap is the
                    # model's prediction made LAST cycle for THIS cycle's
                    # observation — the true per-step prediction error. Comparing
                    # same-cycle horizon-end predictions against the pre-action
                    # observation would inflate the gap to ~horizon-distance in
                    # any moving world, permanently vetoing ACT (the no-action
                    # stagnation trap). A healthy model's per-step gap -> 0;
                    # a falsified model's gap stays high -> risk gate FAILs.
                    pending = getattr(self, '_pending_reality_gap', None)
                    if pending is not None:
                        prev_pred, prev_cycle = pending
                        if prev_cycle != ctx.cycle_count:
                            if getattr(ctx, 'episode_reset', False):
                                # Episode boundary: the prediction was made in
                                # the pre-reset world; the current observation
                                # is a NEW world instance at origin. Comparing
                                # across the reset is not a prediction failure
                                # (no causal link -> no evidence, Λ6.5).
                                # Suppress the record and clear the pending
                                # prediction so it cannot poison a later cycle.
                                self._pending_reality_gap = None
                            else:
                                self._reality_gap_tracker.record("world", prev_pred, ctx.state, cycle=ctx.cycle_count)
                    if predicted is not None and ctx.selected_action is not None:
                        self._pending_reality_gap = (predicted, ctx.cycle_count)
                    else:
                        self._pending_reality_gap = None
                except Exception as e:
                    logger.warning(f"RealityGapTracker.record failed: {e}")

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
                except Exception as e:
                    logger.warning(f"TheoryBuilder.observe_outcome (act) failed: {e}")

                try:
                    if ctx.selected_intent:
                        cf_opts: List[Dict] = []
                        for o in getattr(ctx, 'sim_options', [])[:3]:
                            cf_opts.append({
                                "intent_type": self._option_intent_type(o),
                                "score": float(getattr(o, 'score', 0.0)),
                                "metadata": dict(getattr(o, 'metadata', {}) or {}),
                            })
                        chosen_score = float(getattr(
                            ctx, 'sim_options', [None])[0].score) if getattr(
                            ctx, 'sim_options', []) else 0.0
                        self._regret_memory.record_decision(
                            cycle=ctx.cycle_count,
                            chosen_intent=ctx.selected_intent.intent_type,
                            chosen_score=chosen_score,
                            chosen_outcome=1.0 if outcome_success else 0.0,
                            counterfactual_options=cf_opts,
                            decision_type=ctx.selected_intent.intent_type,
                            context_hash=str(ctx.state)[:64],
                        )
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

                try:
                    wb = ctx.council_blocked or ctx.firewall_blocked
                    if wb:
                        council_signals = [
                            {"validator_name": s.validator_name, "passed": s.passed}
                            for s in (ctx.verdict.signals if ctx.verdict else [])
                        ]
                        predicted = getattr(ctx, 'predicted_state', None)
                        actual = getattr(ctx, 'state', None)
                        sim_error = 0.0
                        if predicted is not None and actual is not None:
                            try:
                                sim_error = float(np.linalg.norm(
                                    np.asarray(predicted, dtype=float)
                                    - np.asarray(actual, dtype=float)))
                            except Exception:
                                sim_error = 0.0
                        pq = getattr(ctx, 'perception_quality', None)
                        perception_quality = float(
                            pq.get('score', 0.5)) if isinstance(pq, dict) else 0.5
                        self._error_attribution.attribute(
                            cycle=ctx.cycle_count,
                            predicted_state=predicted,
                            actual_state=actual,
                            was_blocked=wb,
                            should_have_blocked=bool(outcome_success) is False,
                            council_signals=council_signals,
                            simulation_error=sim_error,
                            perception_quality=perception_quality,
                            action_error=0.0,
                            intent_type=ctx.selected_intent.intent_type
                            if ctx.selected_intent else "unknown",
                        )
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

                # ── v2: CognitiveMomentum — record decision inertia ──
                try:
                    intent_type = ctx.selected_intent.intent_type if ctx.selected_intent else "unknown"
                    self._cognitive_momentum.record_decision(
                        cycle=ctx.cycle_count,
                        intent_type=intent_type,
                    )
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

                # P1 D3: Multi-resource budget tracking — fallback if not already set
                # (primary budget computation happens after STREAMS phase)
                existing = getattr(ctx, 'resource_budgets', None)
                identity_stability = 1.0 - getattr(self._identity_entropy, 'collapse_rate', 0.0)
                if existing is None:
                    ctx.resource_budgets = {
                    "energy": {
                        "consumed_ms": self.budget_manager.consumed_ms,
                        "total_ms": self.budget_manager.total_budget_ms,
                        "budget_carryover_ms": getattr(self.budget_manager, 'budget_carryover_ms', 0.0),
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
                # (env-gated: TELOS_IDENTITY_TUPLE_EVERY_N, default 0 =
                # never — the per-cycle dump is a diagnostics opt-in now,
                # gated with the hoisted per-cycle value: one env read per
                # cycle, never per-phase).
                if _identity_dump_every_n > 0 and (
                        self._cycle_count % _identity_dump_every_n == 0):
                    try:
                        import json
                        with open('/tmp/telos_identity_tuple.json', 'w') as idf:
                            json.dump(ctx.identity_state, idf, indent=2, default=str)
                    except Exception as e:
                        logger.warning("runtime.py: swallowed error: %r", e)

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


            if phase.name == "reflect":
                try:
                    due = self._introspection_scheduler.get_due_tiers(ctx.cycle_count)
                    self._introspection_scheduler.introspect(ctx.cycle_count)
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)
                try:
                    di = ctx.verdict.decision_integrity if ctx.verdict else 0.0
                    md = ctx.verdict.mission_drift if ctx.verdict else 0.0
                    wb = getattr(ctx, 'council_blocked', False) or getattr(ctx, 'firewall_blocked', False)
                    self._axiom_evolution.observe(cycle=ctx.cycle_count, di=di, md=md,
                        was_blocked=wb, council_signals=[], stream_activations={}, identity_state={})
                except Exception as e:
                    logger.warning("runtime.py: swallowed error: %r", e)

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
            governance_blocked_by=(
                ctx.firewall_verdict.blocked_by
                if ctx.firewall_verdict else (
                    # Non-firewall governance reasons are surfaced honestly:
                    # (a) Research Amplification Gate LEFT (Λ6.5, require
                    # mode) — the run was LEFT pre-PERCEIVE so no firewall
                    # verdict exists; (b) watchdog cycle_timeout and
                    # phase_crash records (hardening fixes) so a wedged
                    # phase is visible as governance_blocked=cycle_timeout
                    # in every downstream consumer, never a silent None.
                    # Default runs (knob off / no watchdog trip / no crash)
                    # keep their exact pre-wiring mapping.
                    ctx.blocking_reason
                    if (getattr(ctx, 'research_gate_left', False)
                        or ctx.blocking_reason.startswith("cycle_timeout")
                        or ctx.blocking_reason.startswith("phase_crash"))
                    else None
                )
            ),
            decision_trace=trace,
            distributed_verdict=getattr(ctx, 'distributed_verdict', None),
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

        # Checkpoint cadence (checkpoint_every_n): the write is the expensive
        # part, not the cycle. Save on cycle 1 (fast restore seed) and every
        # N cycles after; sparse numbering is chain-safe (prev_checkpoint_hash
        # links the last SAVED checkpoint) and the shutdown final save below
        # is always unconditional. Λ4.7: persistence must not dominate the
        # cycle loop of a long-lived run.
        _checkpoint_due = (
            self._cycle_count == 1
            or (self.config.checkpoint_every_n > 1
                and self._cycle_count % self.config.checkpoint_every_n == 0)
        )
        if self._checkpointer and _checkpoint_due:
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


    @property
    def identity_bridge(self) -> Optional[IdentityBridge]:
        """The identity↔knowledge bridge (None only if wiring failed)."""
        return getattr(self, '_identity_bridge', None)

    def get_identity_knowledge(self) -> Dict:
        """'What do I know about my own state?' — the identity↔knowledge
        connected web: self-snapshot node, its neighborhood, and hot
        identity-relevant knowledge (Λ4.1 Identity Shapes Decisions)."""
        ib = getattr(self, '_identity_bridge', None)
        if ib is None:
            return {"error": "identity bridge not wired"}
        return ib.self_knowledge()

    def _run_distributed_council(self, ctx) -> None:
        """Run the advisory DistributedCouncil crew for this cycle.

        Advisory only — the primary council's verdict stays binding (Λ1.2).
        Cadence-controlled (every `distributed_council_interval` cycles) and
        fully disable-able via `distributed_council_enabled=False`.

        Args:
            ctx: the phase context (reads ctx.verdict / selected_intent;
                writes ctx.distributed_verdict).
        """
        if not getattr(self.config, 'distributed_council_enabled', True):
            return
        interval = max(1, getattr(self.config, 'distributed_council_interval', 1))
        if ctx.cycle_count % interval != 0:
            return
        if ctx.verdict is None or ctx.selected_intent is None:
            return
        context = {
            "intent_type": ctx.selected_intent.intent_type,
            "confidence": ctx.selected_intent.confidence,
            "alternatives": [i.intent_type for i, _ in getattr(ctx, 'intents', [])][:5],
            "uncertainty": getattr(ctx, 'inquiry_omega_value', 0.0),
            "curiosity_bonus": getattr(ctx, 'curiosity_bonus', 1.0),
            "criticality": getattr(ctx, 'decision_criticality', 'medium'),
            "n_sim_options": len(getattr(ctx, 'sim_options', []) or []),
            # v9 DOMAIN_EXPERT context: the domain string + the perceive
            # consultation report so the lens can dissent on avoid-listed
            # candidates. Throttled cycles carry approach=None/avoid=[] — the
            # lens stays neutral (and is not registered) on those cycles.
            "domain": (getattr(self.config.simulator, 'domain', 'unknown')
                       if getattr(self.config, 'simulator', None) else 'unknown'),
            "knowledge_report": (
                getattr(ctx.perceive, 'knowledge_report', None)
                if getattr(ctx, 'perceive', None) else None),
        }
        result = self._distributed_council.run_perspectives(ctx.verdict, context)
        ctx.distributed_verdict = {
            "enabled": True,
            "cycle": ctx.cycle_count,
            "aggregate": {
                "validated": result["validated"],
                "decision_integrity": round(result["decision_integrity"], 4),
                "mission_drift": round(result["mission_drift"], 4),
                "consensus": result["consensus"],
                "n_agents": result["n_agents"],
            },
            "agents": [a["agent_id"] + ":" + a["role"] for a in result["agents"]],
            "registered_agents": self._distributed_council.to_dict()["registered_agents"],
            "voting_agents": self._distributed_council.to_dict()["voting_agents"],
        }
        # Advisory disagreement escalation: only on low-confidence decisions,
        # and it NEVER blocks — the primary council remains binding.
        if ctx.verdict.validated != result["validated"] and ctx.verdict.decision_integrity < 0.7:
            ctx.distributed_verdict["escalated"] = True
            ctx.distributed_verdict["escalation_reason"] = (
                f"distributed crew disagrees with primary council "
                f"(primary DI={ctx.verdict.decision_integrity:.2f}, "
                f"crew validated={result['validated']})"
            )
            logger.warning(
                f"DistributedCouncil: crew disagrees with primary on low-confidence "
                f"decision (primary DI={ctx.verdict.decision_integrity:.2f}, "
                f"crew validated={result['validated']}) — advisory escalation"
            )

    def observe_conversation_outcome(self, message: str, reply: str,
                                     outcome: float,
                                     domain: str = "conversation") -> str:
        """Feed a conversation turn into theory formation (Λ6.5).

        The chat loop's user message / assistant reply never reaches
        TheoryBuilder through execute(); this is the explicit bridge so
        the conversation path contributes experiences, patterns, and
        theories like every other stream.

        Args:
            message: the user's message text.
            reply: the assistant's reply text.
            outcome: quality score in [0, 1].
            domain: knowledge domain to attribute the experience to.

        Returns:
            The experience id (or "" if TheoryBuilder is unavailable).
        """
        if getattr(self, '_theory_builder', None) is None:
            return ""
        return self._theory_builder.observe_outcome(
            outcome=float(outcome),
            context=f"user: {str(message)[:40]} -> telos: {str(reply)[:40]}",
            action="conversation",
            domain=domain,
        )

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
        # Cross-session learning: write session handoff + persist learnings
        try:
            save_learnings(self, {
                "di": getattr(self, '_last_trace', None).decision_integrity if hasattr(self, '_last_trace') else 1.0,
                "md": getattr(self, '_last_trace', None).mission_drift if hasattr(self, '_last_trace') else 0.0,
                "cycles": self._cycle_count,
            })
        except Exception as e:
            logger.warning("runtime.py: swallowed error: %r", e)
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