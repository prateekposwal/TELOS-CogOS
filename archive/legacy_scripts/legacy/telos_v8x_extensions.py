"""
TELOS v8.x Final Extensions: Closing Three Blind Spots

1. Epistemic Dissonance Resolution
   Mission-Weighted Consensus Protocol:
   When high-confidence agents return contradictory execution plans,
   the Meta-Agent resolves conflicts by projecting each proposal onto
   the foundational mission vector G₀. The plan with the highest
   projection angle and lowest identity entropy wins.

2. Automated Epistemic Calibration (Ledger Feedback Loop)
   When a Decision Ledger entry is marked INVALIDATED, the failure
   vector updates the confidence prior (λ) for that assumption class
   across the entire Context Mesh. TELOS becomes systematically smarter
   at recognizing brittle assumptions over long-horizon tasks.

3. Context Immunology
   All external memory updates (documentation, APIs, web feeds) pass
   through the Neti-Neti Pruning Engine before writing to the active
   context graph. If an ingested chunk increases Identity Entropy (H_I)
   beyond threshold limits, it is quarantined immediately.

Architecture placement in TELOS v8.x:
  ┌──────────────────────────────────────────────────────┐
  │              TELOS Meta-Agent (G₀)                    │
  │  ┌─────────────────────────────────────────────────┐ │
  │  │   1. Mission-Weighted Consensus Protocol        │ │
  │  │   (projects proposals onto G₀, breaks ties by   │ │
  │  │    projection angle + identity entropy)          │ │
  │  └─────────────────────────────────────────────────┘ │
  │  ┌─────────────────────────────────────────────────┐ │
  │  │   2. Automated Epistemic Calibration            │ │
  │  │   (INVALIDATED entries → update λ prior for     │ │
  │  │    assumption class across Context Mesh)         │ │
  │  └─────────────────────────────────────────────────┘ │
  │  ┌─────────────────────────────────────────────────┐ │
  │  │   3. Context Immunology Filter                  │ │
  │  │   (Neti-Neti screens before context write;      │ │
  │  │    quarantine if H_I spike detected)             │ │
  │  └─────────────────────────────────────────────────┘ │
  └──────────────────────────────────────────────────────┘
"""

import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from telos_negative_search import NetiNetiPruningEngine, StableRegionMonitor
from telos_decision_ledger import DecisionLedger, DecisionLedgerEntry


# ═══════════════════════════════════════════════════════════
# 1. EPISTEMIC DISSIDENCE RESOLUTION
#    Mission-Weighted Consensus Protocol
# ═══════════════════════════════════════════════════════════

class ConflictType(Enum):
    """Nature of disagreement between agents."""
    VALUE_DISAGREEMENT = "value_disagreement"
    STRATEGY_DIVERGENCE = "strategy_divergence"
    TEMPORAL_MISMATCH = "temporal_mismatch"
    EPISTEMIC_CONFLICT = "epistemic_conflict"


@dataclass
class AgentProposal:
    """A proposal submitted by a sub-agent for consensus evaluation."""
    agent_id: str
    proposal_vector: np.ndarray           # Proposal projected into embedding space
    proposal_text: str                    # Human-readable plan summary
    confidence: float                     # Agent's self-reported confidence [0, 1]
    identity_entropy: float               # Agent's internal identity entropy H_I
    reasoning_cost: float                 # Compute cost to generate this proposal
    supporting_evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConsensusResolution:
    """Result of the mission-weighted consensus process."""
    winning_proposal: str
    winner_agent_id: str
    projection_score: float               # cos(proj(proposal, G₀))
    identity_entropy: float               # Winner's H_I
    conflict_type: Optional[ConflictType]
    rejected_proposals: List[str]
    projection_angles: Dict[str, float]   # agent_id -> angle from G₀
    entropy_scores: Dict[str, float]      # agent_id -> H_I
    reasoning: str
    timestamp: float = field(default_factory=time.time)


class MissionWeightedConsensus:
    """
    Resolves multi-agent conflicts by projecting proposals onto the
    foundational mission vector G₀.

    Selection criteria (in order):
      1. Highest projection onto G₀: cos(proj(p_i, G₀))
      2. Lowest identity entropy H_I (tiebreaker)
      3. Lowest reasoning cost (final tiebreaker)

    Avoids majority voting (expensive, groupthink-prone).
    """

    def __init__(self, mission_vector: np.ndarray,
                 entropy_threshold: float = 0.75,
                 min_projection: float = 0.3):
        mn = np.linalg.norm(mission_vector)
        if mn < 1e-9:
            raise ValueError("Mission vector must be non-zero")
        self.mission_vector = mission_vector / mn
        self.entropy_threshold = entropy_threshold
        self.min_projection = min_projection
        self._resolution_history: deque = deque(maxlen=200)
        self._total_resolutions = 0
        self._total_conflicts = 0

    def _compute_projection_angle(self, proposal: AgentProposal) -> float:
        """cos(θ) = (p · G₀) / (||p|| · ||G₀||)"""
        pn = np.linalg.norm(proposal.proposal_vector)
        if pn < 1e-9:
            return 0.0
        return float(np.dot(proposal.proposal_vector, self.mission_vector) / pn)

    def _detect_conflict(self, proposals: List[AgentProposal]) -> Optional[ConflictType]:
        """Detect the type of conflict between proposals."""
        if len(proposals) < 2:
            return None

        projections = [self._compute_projection_angle(p) for p in proposals]
        confidences = [p.confidence for p in proposals]
        entropies = [p.identity_entropy for p in proposals]

        proj_range = max(projections) - min(projections)
        conf_range = max(confidences) - min(confidences)
        entropy_range = max(entropies) - min(entropies)

        if proj_range > 0.4 and conf_range > 0.3:
            return ConflictType.EPISTEMIC_CONFLICT
        elif entropy_range > 0.3:
            return ConflictType.STRATEGY_DIVERGENCE
        elif proj_range > 0.5:
            return ConflictType.VALUE_DISAGREEMENT
        elif conf_range > 0.5:
            return ConflictType.TEMPORAL_MISMATCH

        return None

    def resolve(self, proposals: List[AgentProposal]) -> ConsensusResolution:
        """
        Resolve epistemic dissonance among conflicting proposals.

        Algorithm:
          1. Project each proposal onto G₀
          2. Score = projection_angle × (1 - H_I) / max(H_I, ε)
          3. Highest score wins
          4. If H_I > entropy_threshold, penalty applied
        """
        if not proposals:
            return ConsensusResolution(
                winning_proposal="", winner_agent_id="none",
                projection_score=0.0, identity_entropy=0.0,
                conflict_type=None, rejected_proposals=[],
                projection_angles={}, entropy_scores={},
                reasoning="No proposals submitted",
            )

        conflict = self._detect_conflict(proposals)
        if conflict:
            self._total_conflicts += 1

        scores = {}
        projection_angles = {}
        entropy_scores = {}

        for p in proposals:
            angle = self._compute_projection_angle(p)
            projection_angles[p.agent_id] = angle
            entropy_scores[p.agent_id] = p.identity_entropy

            # Mission-projection score (primary)
            projection_score = max(angle, 0.0)

            # Identity entropy penalty (secondary)
            if p.identity_entropy > self.entropy_threshold:
                entropy_penalty = 1.0 - (p.identity_entropy - self.entropy_threshold) / (1.0 - self.entropy_threshold + 1e-9)
                entropy_penalty = max(entropy_penalty, 0.0)
            else:
                entropy_penalty = 1.0

            # Combined score: high projection, low entropy wins
            epsilon = 1e-9
            scores[p.agent_id] = projection_score * entropy_penalty * p.confidence

        # Winner selection
        winner_id = max(scores, key=scores.get)
        winner = next(p for p in proposals if p.agent_id == winner_id)

        rejected = [p.agent_id for p in proposals if p.agent_id != winner_id]

        reasoning_parts = [
            f"Projected {len(proposals)} proposals onto G₀",
            f"Conflict type: {conflict.value}" if conflict else "No significant conflict",
            f"Winner: {winner_id} (score={scores[winner_id]:.4f})",
            f"Projection angle: {projection_angles[winner_id]:.4f}",
            f"Identity entropy: {winner.identity_entropy:.4f}",
        ]

        self._total_resolutions += 1
        result = ConsensusResolution(
            winning_proposal=winner.proposal_text,
            winner_agent_id=winner_id,
            projection_score=projection_angles[winner_id],
            identity_entropy=winner.identity_entropy,
            conflict_type=conflict,
            rejected_proposals=rejected,
            projection_angles=projection_angles,
            entropy_scores=entropy_scores,
            reasoning=" | ".join(reasoning_parts),
        )
        self._resolution_history.append(result)
        return result

    def get_statistics(self) -> Dict:
        return {
            'total_resolutions': self._total_resolutions,
            'total_conflicts': self._total_conflicts,
            'conflict_rate': self._total_conflicts / self._total_resolutions if self._total_resolutions else 0.0,
            'entropy_threshold': self.entropy_threshold,
            'min_projection': self.min_projection,
        }


# ═══════════════════════════════════════════════════════════
# 2. AUTOMATED EPISTEMIC CALIBRATION
#    Ledger Feedback Loop
# ═══════════════════════════════════════════════════════════

@dataclass
class CalibrationEvent:
    """Record of a single calibration update to the Context Mesh."""
    assumption_class: str
    old_lambda: float
    new_lambda: float
    cause_decision_id: str
    failure_severity: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class AssumptionClassStats:
    """Aggregated statistics for an assumption class."""
    class_name: str
    total_observations: int
    total_invalidations: int
    current_lambda: float
    mean_severity: float
    calibration_events: int


class EpistemicCalibrationLoop:
    """
    When a Decision Ledger entry is INVALIDATED:
      1. Extract the violated assumption class
      2. Compute failure severity from the invalidation
      3. Update λ prior for that class: λ_new = λ_old × (1 + α × severity)
      4. Propagate updated λ across all active decisions using this assumption class

    Result: TELOS becomes systematically smarter at recognizing brittle
    assumptions over long-horizon tasks.
    """

    def __init__(self, ledger: DecisionLedger,
                 base_learning_rate: float = 0.1,
                 max_lambda: float = 1.0,
                 min_lambda: float = 0.01):
        self.ledger = ledger
        self.base_learning_rate = base_learning_rate
        self.max_lambda = max_lambda
        self.min_lambda = min_lambda
        self._class_lambdas: Dict[str, float] = {}
        self._class_stats: Dict[str, Dict[str, Any]] = {}
        self._calibration_history: deque = deque(maxlen=500)
        self._total_calibrations = 0

    def calibrate_on_invalidation(self, decision_id: str) -> List[CalibrationEvent]:
        """
        Called when a decision is marked INVALIDATED.
        Propagates failure signal to assumption class lambdas.
        """
        entry = self.ledger.get_decision(decision_id)
        if not entry or entry.status != "INVALIDATED":
            return []

        events = []
        severity = self._compute_failure_severity(entry)

        for assumption in entry.assumptions:
            assumption_class = self._extract_class(assumption)

            old_lambda = self._class_lambdas.get(assumption_class, 0.1)
            new_lambda = self._update_lambda(old_lambda, severity)
            self._class_lambdas[assumption_class] = new_lambda

            # Update class stats
            if assumption_class not in self._class_stats:
                self._class_stats[assumption_class] = {
                    'total_observations': 0,
                    'total_invalidations': 0,
                    'mean_severity': 0.0,
                    'calibration_events': 0,
                }
            stats = self._class_stats[assumption_class]
            stats['total_invalidations'] += 1
            stats['total_observations'] += 1
            n = stats['total_invalidations']
            stats['mean_severity'] = (stats['mean_severity'] * (n - 1) + severity) / n
            stats['current_lambda'] = new_lambda
            stats['calibration_events'] += 1

            event = CalibrationEvent(
                assumption_class=assumption_class,
                old_lambda=old_lambda,
                new_lambda=new_lambda,
                cause_decision_id=decision_id,
                failure_severity=severity,
            )
            events.append(event)
            self._calibration_history.append(event)
            self._total_calibrations += 1

        # Propagate to active decisions
        self._propagate_to_active(entry.mission_id)

        return events

    def _compute_failure_severity(self, entry: DecisionLedgerEntry) -> float:
        """Severity = confidence_delta × violation_count_ratio."""
        n_assumptions = len(entry.assumptions) if entry.assumptions else 1
        n_violated = len(entry.assumptions)  # All were invalidated
        violation_ratio = n_violated / n_assumptions

        confidence_delta = entry.confidence
        severity = min(1.0, confidence_delta * violation_ratio)
        return max(severity, 0.01)

    def _extract_class(self, assumption: str) -> str:
        """Extract the assumption class from an assumption string.

        E.g., "market_growth > 5%" -> "market_growth"
              "trust_score >= 0.7" -> "trust_score"
        """
        separators = ['>', '<', '=', '>=', '<=', '!=', '~']
        for sep in separators:
            if sep in assumption:
                return assumption.split(sep)[0].strip()
        return assumption.strip()

    def _update_lambda(self, old_lambda: float, severity: float) -> float:
        """Update lambda: λ_new = λ_old × (1 + α × severity)."""
        new_lambda = old_lambda * (1.0 + self.base_learning_rate * severity)
        return np.clip(new_lambda, self.min_lambda, self.max_lambda)

    def _propagate_to_active(self, mission_id: str):
        """Update confidence decay rates for active decisions using this mission."""
        active_decisions = self.ledger.get_decisions_for_mission(mission_id)
        for entry in active_decisions:
            if entry.status != "ACTIVE":
                continue
            for assumption in entry.assumptions:
                cls = self._extract_class(assumption)
                if cls in self._class_lambdas:
                    adjustment = self._class_lambdas[cls]
                    entry.confidence_decay_rate = max(
                        entry.confidence_decay_rate,
                        entry.confidence_decay_rate * (1.0 + adjustment * 0.1)
                    )

    def get_lambda(self, assumption_class: str) -> float:
        """Get current lambda for an assumption class."""
        return self._class_lambdas.get(assumption_class, 0.1)

    def get_class_stats(self, assumption_class: str) -> Optional[AssumptionClassStats]:
        stats = self._class_stats.get(assumption_class)
        if not stats:
            return None
        return AssumptionClassStats(
            class_name=assumption_class,
            total_observations=stats['total_observations'],
            total_invalidations=stats['total_invalidations'],
            current_lambda=stats['current_lambda'],
            mean_severity=stats['mean_severity'],
            calibration_events=stats['calibration_events'],
        )

    def get_all_lambdas(self) -> Dict[str, float]:
        return dict(self._class_lambdas)

    def get_statistics(self) -> Dict:
        return {
            'total_calibrations': self._total_calibrations,
            'unique_classes': len(self._class_lambdas),
            'current_lambdas': dict(self._class_lambdas),
            'learning_rate': self.base_learning_rate,
        }


# ═══════════════════════════════════════════════════════════
# 3. CONTEXT IMMUNOLOGY FILTER
#    External data screening before context graph write
# ═══════════════════════════════════════════════════════════

class ContextChunkStatus(Enum):
    """Status of an ingested context chunk."""
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass
class ContextChunk:
    """A unit of external data to be ingested into the context graph."""
    chunk_id: str
    source: str                           # "api", "web", "document", "user_input"
    embedding: np.ndarray                 # Chunk embedding vector
    content_hash: str                     # Content fingerprint
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ImmunologyResult:
    """Outcome of the context immunology screening."""
    chunk_id: str
    status: ContextChunkStatus
    alignment_score: float
    identity_entropy_impact: float
    rejection_reason: Optional[str]
    quarantine_reason: Optional[str]
    timestamp: float = field(default_factory=time.time)


class ContextImmunologyFilter:
    """
    Screens all external memory updates before writing to the active
    context graph, preventing context poisoning.

    Pipeline for each incoming chunk:
      1. Neti-Neti alignment check (mission invariants)
      2. Identity Entropy impact estimation
      3. If H_I spike detected → quarantine
      4. If alignment < threshold → reject
      5. Otherwise → accept into context graph

    Biological analogy:
      - Neti-Neti Pruning = molecular screening (surface pattern recognition)
      - H_I monitoring = inflammatory response detection
      - Quarantine = immune system isolation before integration
    """

    def __init__(self, mission_vector: np.ndarray,
                 alignment_threshold: float = 0.3,
                 entropy_spike_threshold: float = 0.15,
                 max_identity_entropy: float = 0.75):
        self.pruner = NetiNetiPruningEngine(alignment_threshold=alignment_threshold)
        self.stability_monitor = StableRegionMonitor(max_entropy=max_identity_entropy)
        self.entropy_spike_threshold = entropy_spike_threshold
        self.max_identity_entropy = max_identity_entropy

        mn = np.linalg.norm(mission_vector)
        if mn < 1e-9:
            raise ValueError("Mission vector must be non-zero")
        self.mission_vector = mission_vector / mn

        self._accepted: deque = deque(maxlen=1000)
        self._quarantined: deque = deque(maxlen=1000)
        self._rejected: deque = deque(maxlen=1000)
        self._total_screened = 0
        self._current_h_i = 0.0

    def screen_chunk(self, chunk: ContextChunk,
                     current_identity: Optional[np.ndarray] = None) -> ImmunologyResult:
        """
        Screen a single context chunk through the immunology filter.

        Returns ImmunologyResult with ACCEPTED/QUARANTINED/REJECTED status.
        """
        self._total_screened += 1

        # 1. Neti-Neti alignment check
        alignment = self.pruner._compute_alignment(chunk.embedding, self.mission_vector)

        # 2. Identity Entropy impact estimation
        h_i_impact = self._estimate_entropy_impact(chunk.embedding, current_identity)

        rejection_reason = None
        quarantine_reason = None
        status = ContextChunkStatus.ACCEPTED

        # 3. Alignment check (rejection)
        if alignment < self.pruner.alignment_threshold:
            status = ContextChunkStatus.REJECTED
            rejection_reason = f"Alignment {alignment:.4f} < threshold {self.pruner.alignment_threshold}"

        # 4. Entropy spike check (quarantine)
        elif h_i_impact > self.entropy_spike_threshold:
            projected_h_i = self._current_h_i + h_i_impact
            if projected_h_i > self.max_identity_entropy:
                status = ContextChunkStatus.QUARANTINED
                quarantine_reason = (
                    f"H_I spike: current={self._current_h_i:.4f}, "
                    f"impact={h_i_impact:.4f}, "
                    f"projected={projected_h_i:.4f} > max={self.max_identity_entropy}"
                )
            else:
                quarantine_reason = None

        # 5. Update H_I tracking
        if status == ContextChunkStatus.ACCEPTED:
            self._current_h_i += h_i_impact * 0.1  # Damped integration
            self._accepted.append(chunk.chunk_id)
        elif status == ContextChunkStatus.QUARANTINED:
            self._quarantined.append(chunk.chunk_id)
        else:
            self._rejected.append(chunk.chunk_id)

        return ImmunologyResult(
            chunk_id=chunk.chunk_id,
            status=status,
            alignment_score=alignment,
            identity_entropy_impact=h_i_impact,
            rejection_reason=rejection_reason,
            quarantine_reason=quarantine_reason,
        )

    def screen_batch(self, chunks: List[ContextChunk],
                     current_identity: Optional[np.ndarray] = None) -> List[ImmunologyResult]:
        """Screen a batch of chunks."""
        return [self.screen_chunk(c, current_identity) for c in chunks]

    def _estimate_entropy_impact(self, chunk_embedding: np.ndarray,
                                 current_identity: Optional[np.ndarray]) -> float:
        """
        Estimate how much ingesting this chunk would increase H_I.

        High impact if the chunk is orthogonal to current identity.
        Low impact if the chunk reinforces existing identity.
        """
        cn = np.linalg.norm(chunk_embedding)
        if cn < 1e-9 or current_identity is None:
            return 0.5  # Default moderate impact

        inorm = np.linalg.norm(current_identity)
        if inorm < 1e-9:
            return 0.5

        # Cosine distance from current identity
        cos_sim = float(np.dot(chunk_embedding, current_identity) / (cn * inorm))
        # Distance = 1 - cos_sim, scaled to [0, 1]
        distance = max(0.0, 1.0 - cos_sim)

        # Magnitude difference also contributes
        mag_ratio = cn / (inorm + 1e-9)
        mag_factor = min(1.0, abs(np.log(mag_ratio + 1e-9)))

        return distance * 0.7 + mag_factor * 0.3

    def release_from_quarantine(self, chunk_id: str) -> bool:
        """Manually release a quarantined chunk (human override)."""
        if chunk_id in self._quarantined:
            self._quarantined.remove(chunk_id)
            self._accepted.append(chunk_id)
            return True
        return False

    def get_quarantine_size(self) -> int:
        return len(self._quarantined)

    def get_statistics(self) -> Dict:
        return {
            'total_screened': self._total_screened,
            'accepted': len(self._accepted),
            'quarantined': len(self._quarantined),
            'rejected': len(self._rejected),
            'acceptance_rate': len(self._accepted) / self._total_screened if self._total_screened else 0.0,
            'quarantine_rate': len(self._quarantined) / self._total_screened if self._total_screened else 0.0,
            'rejection_rate': len(self._rejected) / self._total_screened if self._total_screened else 0.0,
            'current_h_i': self._current_h_i,
            'entropy_spike_threshold': self.entropy_spike_threshold,
            'max_identity_entropy': self.max_identity_entropy,
        }


# ═══════════════════════════════════════════════════════════
# 4. UNIFIED v8.x EXTENSION RUNTIME
# ═══════════════════════════════════════════════════════════

class TelosV8xExtensionRuntime:
    """
    Unified runtime integrating all three blind-spot extensions:
      1. Mission-Weighted Consensus (Epistemic Dissonance Resolution)
      2. Automated Epistemic Calibration (Ledger Feedback Loop)
      3. Context Immunology Filter (Anti-Poisoning)

    Sits on top of the existing v8 architecture:
      PCS → Opportunity Engine → Decision Ledger → v8.x Extensions
    """

    def __init__(self, mission_vector: np.ndarray,
                 ledger: Optional[DecisionLedger] = None,
                 entropy_threshold: float = 0.75):
        mn = np.linalg.norm(mission_vector)
        if mn < 1e-9:
            raise ValueError("Mission vector must be non-zero")
        self.mission_vector = mission_vector / mn

        self.ledger = ledger or DecisionLedger()
        self.consensus = MissionWeightedConsensus(
            mission_vector, entropy_threshold=entropy_threshold
        )
        self.calibration = EpistemicCalibrationLoop(self.ledger)
        self.immunology = ContextImmunologyFilter(mission_vector)

        self._step_count = 0
        self._extension_log: deque = deque(maxlen=500)

    def resolve_conflict(self, proposals: List[AgentProposal]) -> ConsensusResolution:
        """Resolve multi-agent epistemic dissonance."""
        self._step_count += 1
        result = self.consensus.resolve(proposals)
        self._extension_log.append({
            'type': 'consensus',
            'step': self._step_count,
            'winner': result.winner_agent_id,
            'conflict': result.conflict_type.value if result.conflict_type else None,
        })
        return result

    def calibrate_on_invalidation(self, decision_id: str) -> List[CalibrationEvent]:
        """Trigger epistemic calibration from a ledger invalidation."""
        events = self.calibration.calibrate_on_invalidation(decision_id)
        if events:
            self._extension_log.append({
                'type': 'calibration',
                'step': self._step_count,
                'decision_id': decision_id,
                'events': len(events),
            })
        return events

    def screen_context(self, chunk: ContextChunk,
                       current_identity: Optional[np.ndarray] = None) -> ImmunologyResult:
        """Screen external data through context immunology."""
        result = self.immunology.screen_chunk(chunk, current_identity)
        self._extension_log.append({
            'type': 'immunology',
            'step': self._step_count,
            'chunk_id': chunk.chunk_id,
            'status': result.status.value,
        })
        return result

    def get_statistics(self) -> Dict:
        return {
            'version': '8.x-blind-spot-extensions',
            'steps': self._step_count,
            'consensus': self.consensus.get_statistics(),
            'calibration': self.calibration.get_statistics(),
            'immunology': self.immunology.get_statistics(),
            'ledger': self.ledger.get_statistics(),
        }


if __name__ == "__main__":
    # Demo: all three extensions
    mission = np.array([1.0, 0.5, 0.3, 0.8, 0.2])
    runtime = TelosV8xExtensionRuntime(mission)

    print("=== 1. Epistemic Dissonance Resolution ===")
    proposals = [
        AgentProposal("agent-a", np.array([1.0, 0.4, 0.3, 0.7, 0.2]),
                      "Plan A: aggressive growth", 0.9, 0.3, 5.0),
        AgentProposal("agent-b", np.array([0.2, 0.8, 0.6, 0.1, 0.9]),
                      "Plan B: conservative approach", 0.85, 0.6, 8.0),
        AgentProposal("agent-c", np.array([0.9, 0.5, 0.2, 0.6, 0.3]),
                      "Plan C: balanced strategy", 0.88, 0.4, 6.0),
    ]
    resolution = runtime.resolve_conflict(proposals)
    print(f"  Winner: {resolution.winner_agent_id} — {resolution.winning_proposal}")
    print(f"  Conflict: {resolution.conflict_type}")
    print(f"  Reasoning: {resolution.reasoning}")

    print("\n=== 2. Epistemic Calibration ===")
    dec_id = runtime.ledger.record_decision(
        "mission-1", "Expand to new market",
        assumptions=["market_growth > 5%", "trust_score >= 0.7"],
        evidence={"data": "market_report_2024"},
        dependencies=[],
        confidence=0.8,
        expected_outcome={"revenue": 10000},
    )
    entry = runtime.ledger.get_decision(dec_id)
    entry.status = "INVALIDATED"
    entry.invalidation_reason = "Market conditions changed"
    events = runtime.calibrate_on_invalidation(dec_id)
    for e in events:
        print(f"  Calibrated {e.assumption_class}: λ {e.old_lambda:.4f} → {e.new_lambda:.4f}")

    print("\n=== 3. Context Immunology ===")
    good_chunk = ContextChunk("doc-1", "api", np.array([0.9, 0.5, 0.3, 0.7, 0.2]),
                               "hash_abc")
    bad_chunk = ContextChunk("doc-2", "web", np.array([-0.8, 0.9, -0.1, 0.3, -0.7]),
                               "hash_def")

    r1 = runtime.screen_context(good_chunk, current_identity=np.array([0.8, 0.4, 0.3, 0.6, 0.2]))
    r2 = runtime.screen_context(bad_chunk, current_identity=np.array([0.8, 0.4, 0.3, 0.6, 0.2]))
    print(f"  Chunk {r1.chunk_id}: {r1.status.value} (alignment={r1.alignment_score:.4f})")
    print(f"  Chunk {r2.chunk_id}: {r2.status.value} (alignment={r2.alignment_score:.4f})")

    print("\n=== Statistics ===")
    stats = runtime.get_statistics()
    for k, v in stats.items():
        if k != 'steps':
            print(f"  {k}: {v}")
