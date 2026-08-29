"""
Core data types for the TELOS pipeline — extracted from runtime.py
to reduce god-object complexity.

Contains: PipelinePhase, DecisionTrace, PipelineConfig, PipelineResult.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional
import numpy as np

from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR
from telos.core.phases.base import StreamActivation
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter


class PipelinePhase(Enum):
    INITIALIZE = "initialize"
    PERCEIVE = "perceive"
    STREAMS = "streams"
    SIMULATE = "simulate"
    EVALUATE = "evaluate"
    SYNTHESIZE = "synthesize"
    SELECT = "select"
    COUNCIL = "council"
    ACT = "act"
    REFLECT = "reflect"
    COMPLETE = "complete"


@dataclass
class DecisionTrace:
    """Complete audit trail for a single decision cycle."""
    cycle_id: int
    timestamp: float
    world_state_snapshot: np.ndarray
    domain_facts: Optional[DomainFacts]
    stream_activations: List[StreamActivation]
    selected_intent: Optional[IntentIR]
    selected_action: Optional[np.ndarray]
    representation: str
    budget_consumed_ms: float
    budget_total_ms: float
    worlds_simulated: int
    cycle_duration_ms: float
    budget_carryover_ms: float = 0.0  # carried-over credit from the previous cycle
    health_score: float = 1.0
    council_validated: bool = True
    decision_integrity: float = 1.0
    mission_drift: float = 0.0
    blocking_validator: Optional[str] = None
    council_signals: List[Dict] = field(default_factory=list)
    escalation_requested: bool = False
    escalation_reason: Optional[str] = None
    semantic_depths: List[Dict] = field(default_factory=list)
    governance_signals: List[Dict] = field(default_factory=list)
    firewall_blocked: bool = False
    firewall_blocked_by: Optional[str] = None
    strategic_options: List[Dict] = field(default_factory=list)
    perception_quality: Optional[Dict] = None
    gate_verdict: Optional[Dict] = None
    reflection: Optional[Dict] = None
    knowledge_report: Optional[Dict] = None
    perception_explanation: Optional[Dict] = None
    system_mood: Optional[str] = None
    local_optima_escape: Optional[Dict] = None
    attention_metrics: Optional[Dict] = None
    # P0 D9: Representation confidence from RepresentationSelector
    representation_confidence: float = 0.0
    # P1 D1: Causal annotations for the selected action
    causal_annotations: Optional[Dict] = None
    # P1 D4: Identity tuple (G_t, M_t, C_t, V_t)
    identity_state: Optional[Dict] = None
    # Distributed Council aggregate (advisory) for this cycle
    distributed_verdict: Optional[Dict] = None
    # P1 D3: Multi-resource budget tracking
    resource_budgets: Optional[Dict] = None
    # P0 D8: Meta-cognition state
    meta_cognition: Optional[Dict] = None
    # P2 D1: Handoff hash from axiom verification
    handoff_hash: Optional[str] = None    # Fix 1: Causal graph from SCM
    causal_graph: Optional[Dict] = None
    # Fix 2: Gamma discount used in commitment
    gamma_discount: float = 0.95
    # Fix 3: Terminal reward F(s_T)
    terminal_value: float = 0.0
    # Fix 4: Belief state B_t
    belief_state: Optional[Dict] = None
    # Fix 5: Capabilities K_t
    capabilities_k: Optional[Dict] = None
    # P1: Per-term breakdown of J(τ) commitment score
    j_term_breakdown: Optional[Dict[str, float]] = None

    # ── Inquiry Stream / Ω Operator trace fields ────────────────────────────
    inquiry_skipped: bool = False
    selected_question: Optional[Dict] = None
    inquiry_omega_value: float = 0.0
    # Fix 4: Multi-axis omega vector (world, identity, other)
    inquiry_omega_vector: Optional[Dict[str, float]] = None
    # Change 4: Continuous omega blend factor
    inquiry_blend: float = 0.0

    # Relational Reasoning scaffolding
    relational_coherence: float = 1.0

    # ── UTXO Chain fields (Bitcoin-inspired) ──────────────────────────────
    spent_ctx_id: Optional[str] = None   # Which previous trace this consumes
    produced_ctx_id: Optional[str] = None  # What this trace produces (links to next)
    # ── Merkle Proof of Reasoning (Bitcoin-inspired) ──────────────────────
    merkle_root: str = ""

    # ── PSDT: Partially Signed Decision Trace (Bitcoin-inspired) ──────────
    psdt: Optional[Dict] = None

    # ── Decision Timelock (Bitcoin-inspired) ──────────────────────────────
    intent_timelock: Optional[Dict] = None  # timelock state at decision time

    # ── SegWit-style Separation: Reasoning vs Output (Bitcoin-inspired) ──
    reasoning_witness: Optional[Dict] = None  # heavy reasoning data
    decision_core: Optional[Dict] = None      # lightweight output

    # ── Inquiry summary (alias used in decision_core) ─────────────────────
    inquiry_summary: Optional[Dict] = None

    # ── Curiosity Drive (intrinsic motivation) ─────────────────────────────
    curiosity_state: Optional[Dict] = None           # CuriosityDrive.get_report()
    curiosity_bonus: float = 1.0                     # CuriosityDrive.get_curiosity_bonus()

    # ── Real tool-use channel (ActionExecutor audit record) ────────────────
    # One ActionExecution.to_dict() per cycle that invoked a real allowlisted
    # command through ACT (or attempted one and was blocked). None when no
    # tool channel was configured/requested. Lambda 2.3: real command, real
    # output, or a real block — never fabricated.
    tool_audit: Optional[Dict] = None

    # ── Axiom Compliance Prover results ────────────────────────────────────
    axiom_results: Optional[Dict[str, Dict]] = None          # AxiomProver.verify() output

    # ── Research Amplification Gate verdict (Λ6.5, pre-PERCEIVE) ──────────
    # AmplificationReport.to_dict() when the pipeline ran the gate
    # (research_gate report/require modes), else None. passed=False with
    # run_status="LEFT" is the run's honest verdict: answering under a
    # coverage gap is the diagnosed bounded-evidence-mode failure, never
    # a silent pass and never fabricated grounding.
    amplification_report: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "world_state": self.world_state_snapshot.tolist(),
            "domain_facts": {
                "resources": self.domain_facts.resources if self.domain_facts else {},
                "constraints": self.domain_facts.constraints if self.domain_facts else [],
                "events": self.domain_facts.events if self.domain_facts else [],
                "metrics": self.domain_facts.metrics if self.domain_facts else {},
            } if self.domain_facts else None,
            "stream_activations": [
                {
                    "name": sa.stream_name,
                    "priority": sa.priority,
                    "activated": sa.activated,
                    "intent_type": sa.intent.intent_type if sa.intent else None,
                    "cost_ms": sa.cost_ms,
                    "budget_remaining_ms": sa.budget_remaining_ms,
                }
                for sa in self.stream_activations
            ],
            "selected_intent": {
                "type": self.selected_intent.intent_type,
                "confidence": self.selected_intent.confidence,
            } if self.selected_intent else None,
            "selected_action": self.selected_action.tolist() if self.selected_action is not None else None,
            # Canonical schema aliases (single source of truth for every
            # consumer — dashboard JS reads trace.intent, audit readers read
            # discrimination_index/action_taken): map onto the canonical
            # fields so no downstream code invents its own names (schema drift
            # pattern → locked by tests/core/test_trace_schema.py).
            "intent": self.selected_intent.intent_type if self.selected_intent else None,
            "discrimination_index": self.decision_integrity,
            "action_taken": self.selected_action.tolist() if self.selected_action is not None else None,
            "representation": self.representation,
            "budget_consumed_ms": self.budget_consumed_ms,
            "budget_total_ms": self.budget_total_ms,
            "budget_carryover_ms": self.budget_carryover_ms,
            "worlds_simulated": self.worlds_simulated,
            "cycle_duration_ms": self.cycle_duration_ms,
            "council_validated": self.council_validated,
            "decision_integrity": self.decision_integrity,
            "mission_drift": self.mission_drift,
            "blocking_validator": self.blocking_validator,
            "council_signals": self.council_signals,
            "escalation_requested": self.escalation_requested,
            "escalation_reason": self.escalation_reason,
            "semantic_depths": self.semantic_depths,
            "governance_signals": self.governance_signals,
            "firewall_blocked": self.firewall_blocked,
            "firewall_blocked_by": self.firewall_blocked_by,
            "strategic_options": self.strategic_options,
            "perception_quality": self.perception_quality,
            "gate_verdict": self.gate_verdict,
            "reflection": self.reflection,
            "knowledge_report": self.knowledge_report,
            "perception_explanation": self.perception_explanation,
            "system_mood": self.system_mood,
            "local_optima_escape": self.local_optima_escape,
            "attention_metrics": self.attention_metrics,
            "representation_confidence": self.representation_confidence,
            "causal_annotations": self.causal_annotations,
            "identity_state": self.identity_state,
            "distributed_verdict": self.distributed_verdict,
            "resource_budgets": self.resource_budgets,
            "meta_cognition": self.meta_cognition,
            "handoff_hash": self.handoff_hash,
            "causal_graph": self.causal_graph,
            "gamma_discount": self.gamma_discount,
            "terminal_value": self.terminal_value,
            "belief_state": self.belief_state,
            "capabilities_k": self.capabilities_k,
            "j_term_breakdown": self.j_term_breakdown,
            # Inquiry fields
            "inquiry_skipped": self.inquiry_skipped,
            "selected_question": self.selected_question,
            "inquiry_omega_value": self.inquiry_omega_value,
            "inquiry_omega_vector": self.inquiry_omega_vector,
            "inquiry_blend": self.inquiry_blend,
            "relational_coherence": self.relational_coherence,
            # UTXO chain
            "spent_ctx_id": self.spent_ctx_id,
            "produced_ctx_id": self.produced_ctx_id,
            "merkle_root": self.merkle_root,
            # PSDT
            "psdt": self.psdt,
            # Decision Timelock
            "intent_timelock": self.intent_timelock,
            # SegWit-style separation
            "reasoning_witness": self.reasoning_witness,
            "decision_core": self.decision_core,
            "inquiry_summary": self.inquiry_summary,
            "curiosity_state": self.curiosity_state,
            "curiosity_bonus": self.curiosity_bonus,
            "tool_audit": self.tool_audit,
            "axiom_results": self.axiom_results,
            "amplification_report": self.amplification_report,
        }

@dataclass
class PipelineConfig:
    simulator: Optional[DomainSimulator] = None
    adapter: Optional[DomainAdapter] = None
    compute_budget_ms: float = 50.0
    state_dim: int = 6
    n_worlds: int = 30
    horizon: int = 8
    feedback_lag: int = 0
    stream_skip_threshold: float = 0.2
    adaptive_worlds_enabled: bool = True
    memory_fast_path_enabled: bool = True
    budget_carryover_max_ratio: float = 0.5
    debug: bool = False
    checkpoint_path: Optional[str] = None
    checkpoint_max: int = 10
    # Checkpoint write cadence: save every N cycles (1 = every cycle, the
    # historical behavior). Long-lived producers throttle this (e.g. 20) so
    # a 20MB checkpoint is not written every 2s cycle; the shutdown/final
    # save is always unconditional and the hmac chain links saved checkpoints
    # (sparse numbering is chain-safe).
    checkpoint_every_n: int = 1
    knowledge_path: Optional[str] = None
    quality_threshold: float = 0.35
    pattern_path: Optional[str] = None
    identity_path: Optional[str] = None
    ledger_path: Optional[str] = None
    experience_max_skills: int = 100
    experience_utility_threshold: float = 0.5
    experience_index_interval: int = 1
    # Timelock configuration
    timelock_window_cycles: int = 3
    # Deterministic execution seed
    deterministic_seed: Optional[int] = None
    # Runtime mode (v7 K): "fast" skips expensive advisory layers (counter-
    # factual alternative generation, InternalDebate, DistributedCouncil,
    # knowledge consultation) — core reasoning + axioms + evidence +
    # governance + stagnation + essential trace stay. "standard" preserves
    # full behavior (default). "research"/"debug" add instrumentation. Set
    # via config or the TELOS_MODE env var (read at construction sites).
    mode: str = "standard"

    # Research Amplification Gate (Lambda 6.5, pre-PERCEIVE stage): a standing
    # evidence-enrichment gate that runs BEFORE any stream/simulation consumes
    # the brief. Modes: "off"/"legacy" = disabled (default — pipeline behavior
    # is byte-identical to pre-gate runs); "report" = run the gate when a
    # caller attaches an evidence base (named sources + claims mapped to the 7
    # mandatory dimensions) and attach the AmplificationReport verdict to the
    # decision context/trace (an evidence-less run carries an honest LEFT
    # report — the gate never fabricates grounding, and reporting never
    # blocks); "require" = a run arriving at the gate without 7/7-dimension
    # external grounding is LEFT before STREAMS (the bounded-evidence-mode
    # structural fix: DONE is only achievable through the amplification report).
    research_gate: str = "off"

    @property
    def is_fast_mode(self) -> bool:
        return self.mode == "fast"

    @property
    def skip_advisory_layers(self) -> bool:
        """Advisory (non-blocking) layers are the first thing fast mode
        skips: they consume time but never change the blocking verdict."""
        return self.is_fast_mode
    # Distributed Council (advisory crew layer on top of the blocking primary
    # council): enabled toggle + cadence (run every N cycles).
    distributed_council_enabled: bool = True
    distributed_council_interval: int = 1
    # Real tool-use channel (audited ActionExecutor). When set, the ACT phase
    # may invoke allowlisted, firewall-audited commands IF a tool intent is
    # council-selected AND the operator granted per-cycle permission
    # (operator_tool_permission=True) or a HumanGateway approval exists this
    # cycle. Default: NO executor -> NO real command can ever run.
    action_executor: Optional[Any] = None
    # Explicit operator grant for tool intents (HumanGateway discipline): the
    # operator configures the channel ON; an arbitrary shell command can never
    # self-authorize.
    operator_tool_permission: bool = False


@dataclass
class PipelineResult:
    selected_trajectory: Optional[Any]
    health_score: float
    pipeline_phase: PipelinePhase
    worlds_generated: int = 0
    council_blocked: bool = False
    decision_integrity: float = 1.0
    mission_drift: float = 0.0
    decision_trace: Optional[DecisionTrace] = None
    firewall_blocked: bool = False
    governance_blocked_by: Optional[str] = None
    alternatives_available: int = 0
    distributed_verdict: Optional[Dict] = None
