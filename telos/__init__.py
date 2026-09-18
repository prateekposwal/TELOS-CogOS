"""
TELOS — A Cognitive Operating System.

Domain-general, self-governing CogOS built on the Laws of Systemic Intelligence.
"""

__version__ = "0.1.0"

from telos.core.runtime import TelosV14Pipeline, PipelineConfig, PipelineResult, DecisionTrace, StreamActivation, PipelinePhase
from telos.core.attention import BudgetManager
from telos.core.simulation import CounterfactualEngine, StrategicOption
from telos.core.planner import RepresentationPlanner

from telos.core.streams.base import CognitiveStream
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream

from telos.core.council.base import Council, CouncilVerdict, ValidationSignal
from telos.core.council.validators import RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector

from telos.core.governance.trust_manager import TrustManager
from telos.core.governance.timing import InformationReadinessEngine
from telos.core.governance.firewall import DecisionFirewall, FirewallConfig
from telos.core.governance.human_gateway import HumanGateway, HumanVerdict

from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
from telos.core.infra_manager.checkpoint_manager import CheckpointManager, CheckpointData
from telos.core.infra_manager.stream_calibrator import StreamCalibrator
from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.core.infra_manager.mission_policy import MissionPolicy, MissionPolicyManager
from telos.core.infra_manager.audit_controller import AuditController

from telos.core.ledger.world_ledger import WorldLedger, EntityRecord, SemanticDepth, UserProfile
from telos.core.ledger.skill_library import SkillLibrary, Skill
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig

from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter
from telos.core.contracts.model_provider import ModelProvider, ModelResponse, OllamaProvider, OpenAIProvider, AnthropicProvider, RouterProvider
from telos.audit.monitor import TransparencyMonitor, MonitorConfig
from telos.core.observability.telemetry import TelemetryCollector, MetricPoint
from telos.core.coordination.coordinator import PipelineCoordinator, SubPipelineConfig, CoordinationResult
from telos.core.perception.quality import PerceptionQuality, QualityReport
from telos.core.perception.gate import ResolutionGate, GateVerdict
from telos.core.perception.proxy import ProxyStream
from telos.core.perception.explainer import PerceptionExplainer
from telos.core.perception.capabilities import CapabilityRegistry, DetectionCapability

from telos.core.knowledge.inference import KGInferenceEngine
from telos.core.planning_horizon import PlanningHorizon
from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.recommender import KnowledgeRecommender
from telos.core.knowledge.recorder import OutcomeRecorder
from telos.core.identity.system_self import SystemSelf, IdentityState
from telos.core.pattern import PatternLibrary, Pattern, PatternSignature, PatternType
from telos.adapters import MetaDomainSimulator, MetaDomainAdapter
from telos.intent_ir import IntentIR

# ── Session / Continuity Layer ──────────────────────────────────────────
from telos.core.session import (
    AgentsWriter, SessionSummary,
    SessionCheckpoint, CheckpointCLI,
    cmd_save, cmd_list, cmd_load, cmd_restore,
    checkpoint_cli_main,
)

__all__ = [
    "__version__",
    "TelosV14Pipeline", "PipelineConfig", "PipelineResult", "DecisionTrace", "StreamActivation", "PipelinePhase",
    "BudgetManager",
    "CounterfactualEngine",
    "RepresentationPlanner",
    "CognitiveStream",
    "ReflexStream", "PerceptionStream", "MemoryStream", "PlanningStream",
    "Council", "CouncilVerdict", "ValidationSignal",
    "RealityValidator", "ConstraintValidator", "MemoryAdvisor", "MissionDriftDetector",
    "TrustManager",
    "InformationReadinessEngine",
    "DecisionFirewall", "FirewallConfig",
    "HumanGateway", "HumanVerdict",
    "InfrastructureManager",
    "StreamCalibrator",
    "FailureLedger",
    "MissionPolicy", "MissionPolicyManager",
    "AuditController",
    "CheckpointManager", "CheckpointData",
    "TelemetryCollector", "MetricPoint",
    "PipelineCoordinator", "SubPipelineConfig", "CoordinationResult",
    "WorldLedger", "EntityRecord", "SemanticDepth", "UserProfile",
    "SkillLibrary", "Skill",
    "ExperienceManager", "ExperienceConfig",
    "World",
    "DomainFacts",
    "DomainSimulator", "DomainAdapter",
    "ModelProvider", "ModelResponse",
    "OllamaProvider", "OpenAIProvider", "AnthropicProvider", "RouterProvider",
    "TransparencyMonitor", "MonitorConfig",
    "KGInferenceEngine", "PlanningHorizon",
    "KnowledgeGraph", "KnowledgeRecommender", "OutcomeRecorder",
    "PerceptionQuality", "QualityReport",
    "ResolutionGate", "GateVerdict",
    "ProxyStream",
    "PerceptionExplainer",
    "CapabilityRegistry", "DetectionCapability",
    "SystemSelf", "IdentityState",
    "PatternLibrary", "Pattern", "PatternSignature", "PatternType",
    "MetaDomainSimulator", "MetaDomainAdapter",
    "IntentIR",
    # Session/Continuity
    "AgentsWriter", "SessionSummary",
    "SessionCheckpoint", "CheckpointCLI",
    "cmd_save", "cmd_list", "cmd_load", "cmd_restore",
    "checkpoint_cli_main",
]
