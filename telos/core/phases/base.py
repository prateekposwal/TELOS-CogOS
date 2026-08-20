from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
import numpy as np

from telos.intent_ir import IntentIR


@dataclass
class StreamActivation:
    stream_name: str
    priority: float
    intent: Optional[IntentIR]
    cost_ms: float
    budget_remaining_ms: float
    activated: bool = True


@dataclass
class PerceiveOutput:
    world: Any
    domain_facts: Any
    quality_report: Any
    gate_verdict: Any
    knowledge_report: dict
    effective_n_worlds: int


@dataclass
class StreamsOutput:
    stream_activations: List[StreamActivation]
    intents: List[Tuple[IntentIR, float]]
    effective_n_worlds: int


@dataclass
class SimulateOutput:
    worlds_generated: int
    sim_options: List
    simulation_confidence: float
    predicted_state: Any
    strategic_options_data: List[dict]


@dataclass
class EvaluateOutput:
    representation: str


@dataclass
class SelectOutput:
    selected_intent: Optional[IntentIR]


@dataclass
class SynthesisOutput:
    reconciled_intent: Optional[IntentIR]
    raw_intents: List
    compatibility_score: float
    conflicts: List[Dict]
    irreconcilable: bool = False


@dataclass
class CouncilOutput:
    verdict: Any
    council_blocked: bool
    semantic_depths: List[dict]


@dataclass
class ActOutput:
    selected_action: Any
    firewall_verdict: Any
    firewall_blocked: bool
    governance_blocked: bool
    blocking_reason: str


@dataclass
class SessionContinuity:
    """Continuity state carried across pipeline cycles — truncated history and session essence."""
    truncated_history: List[Dict] = field(default_factory=list)
    session_essence: Optional[Dict] = None


@dataclass
class PhaseContext:
    cycle_count: int
    state: np.ndarray
    user_name: Optional[str]

    perceive: Optional[PerceiveOutput] = None
    streams: Optional[StreamsOutput] = None
    simulate: Optional[SimulateOutput] = None
    evaluate: Optional[EvaluateOutput] = None
    synthesis: Optional[SynthesisOutput] = None
    select: Optional[SelectOutput] = None
    council: Optional[CouncilOutput] = None
    act: Optional[ActOutput] = None
    
    # Helper to fix stream/runtime phase issues
    stream_activations: List = field(default_factory=list)
    intents: List = field(default_factory=list)
    effective_n_worlds: int = 5
    effective_horizon: int = 3
    domain_facts: Any = None
    world: Any = None
    predicted_state: Any = None
    selected_intent: Any = None
    selected_action: Any = None
    representation: str = "cartesian"
    worlds_generated: int = 0
    strategic_options_data: List[dict] = field(default_factory=list)
    semantic_depths: List[dict] = field(default_factory=list)
    reflection: Optional[Dict] = None
    sim_options: Any = None
    simulation_confidence: float = 0.0
    verdict: Any = None
    council_blocked: bool = False
    firewall_blocked: bool = False
    firewall_verdict: Any = None
    governance_blocked: bool = False
    blocking_reason: str = ""
    escalation_pending: bool = False
    _council_fallback_attempted: bool = False
    local_optima_escape: Optional[Dict] = None
    # P0 D9: Representation confidence
    representation_confidence: float = 0.0
    # P1 D1: Causal annotations
    causal_annotations: Optional[Dict] = None
    # P1 D4: Identity tuple
    identity_state: Optional[Dict] = None
    # P1 D3: Resource budgets
    resource_budgets: Optional[Dict] = None
    # Relational Reasoning scaffolding
    relational_context: Optional[Dict] = None
    # P0 D8: Meta-cognition
    meta_cognition: Optional[Dict] = None

    # ── TELOS v6 Governance (Phases 6/7/8): additive decision-mode fields ──
    # These are ADDITIVE: they never alter existing BLOCK/governance_blocked
    # semantics (BenchmarkMetrics still counts 'blocks' the same way). They only
    # extend the context so the act phase can report a richer DecisionMode.
    decision_mode: Any = None              # DecisionMode (ACT/DEFER/ABSTAIN/ESCALATE/BLOCK)
    no_action: bool = False                # True when act emits NO action vector
    capability_authorization: Any = None   # CapabilityAuthorization for this cycle
    governor_decision: Any = None          # GovernorDecision record
    epistemic_state: Any = None            # EpistemicState for this cycle
    _governance_override: Any = None       # Optional injected CapabilityAuthorization (tests)


    # Attention Projection (Law of Attention)
    attention_allocation: Any = None
    attention_metrics: Optional[Dict] = None

    # Fix 1: Causal graph from SCM
    causal_graph: Optional[Dict] = None
    # Fix 3: Terminal reward F(s_T)
    terminal_value: float = 0.0
    # Fix 5: Capabilities K_t
    capabilities_k: Optional[Dict] = None
    # P1: Per-term J(τ) breakdown from commitment optimizer
    j_term_breakdown: Optional[Dict[str, float]] = None

    # Session Continuity Layer
    session: SessionContinuity = field(default_factory=SessionContinuity)
    chat_history: List[Dict] = field(default_factory=list)

    # ── Inquiry Stream / Ω Operator fields ──────────────────────────────────
    inquiry_skipped: bool = False        # True when Ω < 0.5 (no question worth asking)
    selected_question: Optional[Dict] = None  # The best question from OmegaOperator
    inquiry_omega_value: float = 0.0     # The Ω value of the selected question
    # Fix 4: Multi-axis omega vector (world, identity, other)
    inquiry_omega_vector: Optional[Dict[str, float]] = None
    # Change 4: Continuous omega blend factor
    inquiry_blend: float = 0.0
    # Bitcoin-inspired voting: decision criticality for Council
    decision_criticality: str = 'medium'  # 'low', 'medium', 'high', 'critical'
    # Change 2: Per-axis modulation params
    identity_cost_weight: float = 1.0
    omega_modulation: Optional[Dict[str, float]] = None

    # ── Curiosity Drive (intrinsic motivation) ──────────────────────────────
    curiosity_state: Optional[Dict] = None           # CuriosityDrive.get_report()
    curiosity_bonus: float = 1.0                     # CuriosityDrive.get_curiosity_bonus()


class Phase(ABC):
    name: str = "phase"

    @abstractmethod
    def execute(self, pipeline, ctx: PhaseContext) -> None:
        ...

    def post_execute(self, pipeline, ctx: PhaseContext) -> None:
        """Post-execution hook for cross-cutting concerns.

        Override in phase implementations to replace the
        `if phase.name == "X"` pattern in runtime.py execute().
        Default is no-op — phases without post-execute wiring
        do not need to override.

        Args:
            pipeline: the running pipeline (post-execute context).
            ctx: the phase context for this cycle.
        """
