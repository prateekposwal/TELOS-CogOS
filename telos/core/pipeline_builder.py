"""PipelineBuilder — constructs a fully configured TelosV14Pipeline.

Extracts the 172-line __init__ from runtime.py into a dedicated builder.
"""

import logging
from typing import Optional

from telos.core.decision.omega_threshold import OmegaThresholdLearner
from telos.core.decision.cognitive_momentum import CognitiveMomentum
from telos.core.decision.commitment_optimizer import CommitmentOptimizer
from telos.core.attention.identity_entropy import IdentityEntropyTracker
from telos.core.resource.gradient import ResourceGradientTracker
from telos.core.curiosity.drive import CuriosityDrive
from telos.core.council.base import Council
from telos.core.governance.firewall import DecisionFirewall
from telos.core.governance.trust_manager import TrustManager
from telos.core.meta_cognition import MetaCognitionModule
from telos.core.uncertainty.tripartite import TripartiteUncertainty
from telos.core.reasoning.relational import RelationalContext
from telos.core.representation_selector import RepresentationSelector
from telos.core.planning_horizon import PlanningHorizon
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.world_ledger import WorldLedger
from telos.core.ledger.experience_manager import ExperienceManager
from telos.core.pattern import PatternLibrary
from telos.core.trace.utxo import UTXOWallet
from telos.core.trace.mempool import Mempool
from telos.core.trace.checkpoint import CheckpointManager
from telos.core.attention.projection import AttentionProjectionEngine
from telos.core.verifier.axiom_prover import AxiomProver
from telos.core.reasoning.theory_builder import TheoryBuilder
from telos.core.reasoning.interpretation_engine import InterpretationEngine
from telos.core.reasoning.model_competition import ModelCompetition
from telos.core.axioms.evolution import AxiomEvolutionEngine
from telos.core.council.reflector import CouncilReflector
from telos.core.council.internal_debate import InternalDebate
from telos.core.meta.error_attribution import ErrorAttributionEngine
from telos.core.curiosity.assumption_auditor import AssumptionAuditor
from telos.core.curiosity.unknown_unknown_detector import UnknownUnknownDetector
from telos.core.identity.utility_profiles import IdentityUtilityEngine
from telos.core.identity.identity_compression import IdentityCompression
from telos.core.introspection.scheduler import IntrospectionScheduler
from telos.core.memory.regret_memory import RegretMemory
from telos.core.memory.active_forgetting import ActiveForgetting
from telos.core.decision.time_horizon import TimeHorizonSeparator
from telos.core.attention.surprise_budget import SurpriseBudget
from telos.core.energy.cognitive_energy import CognitiveEnergy
from telos.core.confidence.dual_confidence import DualConfidence
from telos.core.knowledge.explanation_compression import ExplanationCompression
from telos.core.accounting.resource_accounting import ResourceAccountingLayer
from telos.core.context.summarizer import ContextSummarizer
from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
from telos.core.governance.human_gateway import HumanGateway
from telos.core.session.memory import SessionManager
from telos.core.council.validators import ConstraintValidator

logger = logging.getLogger('telos_pipeline_builder')


def build_components(config, infra_manager=None, skill_library=None):
    """Build all pipeline component instances from config.

    Returns a dict of component_name -> instance for use by TelosV14Pipeline.
    """
    components = {}

    components['omega_threshold_learner'] = OmegaThresholdLearner()
    components['commitment_optimizer'] = CommitmentOptimizer()
    components['resource_gradient_tracker'] = ResourceGradientTracker()
    components['curiosity_drive'] = CuriosityDrive()
    components['identity_entropy'] = IdentityEntropyTracker(
        window_size=config.identity_entropy_window if hasattr(config, 'identity_entropy_window') else 10,
    )
    components['attention_engine'] = AttentionProjectionEngine()
    components['pattern_library'] = PatternLibrary()
    components['planner'] = PlanningHorizon(
        default_horizon=config.horizon if hasattr(config, 'horizon') else 3,
    )
    components['representation_selector'] = RepresentationSelector()
    components['utxo_wallet'] = UTXOWallet()
    components['mempool'] = Mempool()
    components['axiom_prover'] = AxiomProver(
        infra_manager=infra_manager,
        skill_library=skill_library,
    )
    components['tripartite_u'] = TripartiteUncertainty()
    components['relational_context'] = RelationalContext()
    components['meta_cognition'] = MetaCognitionModule()
    components['context_summarizer'] = ContextSummarizer()
    components['session_manager'] = SessionManager()
    components['experience_manager'] = ExperienceManager(persistence_path="checkpoints")

    # Security
    components['trust_manager'] = TrustManager()
    components['human_gateway'] = HumanGateway(
        mode="auto",
        auto_approve_threshold=0.3,
    )

    # Governance
    firewall = DecisionFirewall()
    firewall.register_validator(ConstraintValidator())
    components['firewall'] = firewall

    # v2 modules
    components['theory_builder'] = TheoryBuilder()
    components['interpretation_engine'] = InterpretationEngine()
    components['axiom_evolution'] = AxiomEvolutionEngine()
    components['council_reflector'] = CouncilReflector()
    components['internal_debate'] = InternalDebate()
    components['error_attribution'] = ErrorAttributionEngine()
    components['assumption_auditor'] = AssumptionAuditor()
    components['unknown_unknown_detector'] = UnknownUnknownDetector()
    components['identity_utility'] = IdentityUtilityEngine()
    components['introspection_scheduler'] = IntrospectionScheduler()
    components['regret_memory'] = RegretMemory()
    components['model_competition'] = ModelCompetition()
    components['time_horizon'] = TimeHorizonSeparator()
    components['surprise_budget'] = SurpriseBudget(
        base_budget_ms=config.compute_budget_ms,
    )
    components['active_forgetting'] = ActiveForgetting()
    components['cognitive_energy'] = CognitiveEnergy()
    components['dual_confidence'] = DualConfidence()
    components['identity_compression'] = IdentityCompression()
    components['explanation_compression'] = ExplanationCompression()
    components['cognitive_momentum'] = CognitiveMomentum()
    components['resource_accounting'] = ResourceAccountingLayer()

    # Wire curiosity drive to assumption auditor
    if 'assumption_auditor' in components:
        components['curiosity_drive'].set_assumption_auditor(
            components['assumption_auditor']
        )

    return components
