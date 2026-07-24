"""
TELOS v11: The Decision Truth Engine & Counterfactual Explorer

Formalizes three systemic failure modes into architectural protections:

1. Narrative ≠ Decision Function (Decision Truth Engine)
   Systems generate rationalized explanations ("no boots") that mask
   the actual optimization function ("avoid expected failure").
   TELOS decouples Claimed Reason from Measured Evidence.

2. Premature Search Surrender (Belief Verification)
   An unverified belief B becomes a hard constraint:
     D = f(G₀, B)
   If B assumes failure without empirical validation, search terminates
   prematurely. TELOS mandates systematic exhaustion before surrender.

3. Cumulative Opportunity Cost & Counterfactual Regret
   OC(t) = Σ V_i (compounding loss from inaction)
   CR = max_π J(π) - J(π_chosen) (regret from not choosing best)
   If CR exceeds threshold, conservative strategy flagged for review.

Master Axiom:
  A robust decision system should never terminate a mission because
  of an assumption until that assumption has been explicitly tested
  against evidence, alternative strategies, and long-term opportunity cost.

Pipeline (v11):
  G₀ → Objective Integrity → Decision Truth Engine → Forest Search
  → Neti-Neti → Red-Team + Counterfactual Explorer → Belief Verification
  → Decision Ledger → PCS → Friction Optimizer → Execution
  → Mission Audit → Strategy Update → Sleep → Auto-Tune
"""

import time
import numpy as np
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from telos_negative_search import NetiNetiPruningEngine, ForestSearchRouter
from telos_decision_ledger import DecisionLedger, DecisionLedgerEntry
from telos_v9 import ObjectiveIntegrityMonitor, MissionState, CognitiveFrictionOptimizer
from telos_v10 import (
    EpistemicSleepCycle, InternalRedTeamAgent, MetaParameterAutoTuner,
    StressTestVerdict,
)


# ═══════════════════════════════════════════════════════════
# 1. DECISION TRUTH ENGINE
#    Narrative ≠ Decision Function
# ═══════════════════════════════════════════════════════════

class NarrativeStatus(Enum):
    """Status of the narrative vs actual optimization decoupling."""
    ALIGNED = "ALIGNED"
    FLAGGED_NARRATIVE_MASKING = "FLAGGED_NARRATIVE_MASKING"
    FLAGGED_BELIEF_CORRUPTION = "FLAGGED_BELIEF_CORRUPTION"
    FLAGGED_PREMATURE_SURRENDER = "FLAGGED_PREMATURE_SURRENDER"
    FLAGGED_HIDDEN_CONSTRAINT = "FLAGGED_HIDDEN_CONSTRAINT"


@dataclass
class DecisionAuditEntry:
    """Full audit record decoupling narrative from actual optimization."""
    decision_id: str
    claimed_reason: str
    actual_optimization_objective: str
    belief_constraints: List[str]
    hidden_constraints: List[str]
    narrative_status: NarrativeStatus
    narrative_alignment_score: float   # 0 = pure masking, 1 = fully aligned
    confidence_in_audit: float         # How confident are we in this audit
    evidence_snapshot: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class DecisionTruthEngine:
    """
    Subsystem that forces runtime auditing to decouple the Claimed Reason
    from the Measured Evidence and Optimization Objective.

    Detects:
      - Narrative Masking: stated reason ≠ actual objective
      - Belief Corruption: unverified beliefs as hard constraints
      - Premature Self-Elimination: abandoning without empirical test
      - Hidden Constraints: unstated objectives driving decisions

    Core principle:
      The system cannot lie to itself. Every decision must be audited
      for alignment between what is said and what is optimized.
    """

    def __init__(self, alignment_threshold: float = 0.7):
        self.alignment_threshold = alignment_threshold
        self._audit_history: deque = deque(maxlen=500)
        self._total_audits = 0
        self._total_masking_detected = 0
        self._total_belief_corruptions = 0
        self._total_premature_surrenders = 0

    def audit_decision(self, decision_id: str,
                       claimed_reason: str,
                       actual_optimization_objective: str,
                       belief_constraints: Optional[List[str]] = None,
                       hidden_constraints: Optional[List[str]] = None,
                       evidence: Optional[Dict[str, Any]] = None) -> DecisionAuditEntry:
        """
        Audit a decision by comparing claimed reason vs actual optimization.

        Returns DecisionAuditEntry with alignment score and status flags.
        """
        self._total_audits += 1
        belief_constraints = belief_constraints or []
        hidden_constraints = hidden_constraints or []

        # ── Narrative Alignment Scoring ──
        # Heuristic: measure lexical/semantic overlap between claimed and actual
        claimed_tokens = set(claimed_reason.lower().split())
        actual_tokens = set(actual_optimization_objective.lower().split())

        if claimed_tokens and actual_tokens:
            overlap = len(claimed_tokens & actual_tokens)
            total = len(claimed_tokens | actual_tokens)
            alignment_score = overlap / total if total > 0 else 0.0
        else:
            alignment_score = 0.0

        # ── Status Classification ──
        has_belief_corruption = len(belief_constraints) > 0
        has_hidden_constraints = len(hidden_constraints) > 0
        narrative_masking = alignment_score < self.alignment_threshold

        if has_belief_corruption and narrative_masking:
            status = NarrativeStatus.FLAGGED_BELIEF_CORRUPTION
            self._total_belief_corruptions += 1
        elif narrative_masking and has_hidden_constraints:
            status = NarrativeStatus.FLAGGED_HIDDEN_CONSTRAINT
            self._total_masking_detected += 1
        elif narrative_masking:
            status = NarrativeStatus.FLAGGED_NARRATIVE_MASKING
            self._total_masking_detected += 1
        else:
            status = NarrativeStatus.ALIGNED

        # ── Confidence in Audit ──
        # Higher confidence when we have more evidence
        n_evidence = len(evidence) if evidence else 0
        confidence = min(1.0, 0.5 + n_evidence * 0.05)

        entry = DecisionAuditEntry(
            decision_id=decision_id,
            claimed_reason=claimed_reason,
            actual_optimization_objective=actual_optimization_objective,
            belief_constraints=belief_constraints,
            hidden_constraints=hidden_constraints,
            narrative_status=status,
            narrative_alignment_score=alignment_score,
            confidence_in_audit=confidence,
            evidence_snapshot=evidence or {},
        )

        self._audit_history.append(entry)
        return entry

    def detect_premature_surrender(self, decision_id: str,
                                   abandoned_branch: str,
                                   reasons_for_abandonment: List[str],
                                   alternatives_exhausted: bool = False,
                                   empirical_evidence: bool = False) -> Dict[str, Any]:
        """
        Detect if the system is surrendering a mission branch prematurely.

        Premature surrender occurs when:
          1. Branch abandoned due to "low probability" without testing
          2. Alternative routes not explored via Forest Search
          3. No empirical evidence collected before decision
        """
        surrender_flags = []
        is_premature = False

        if not empirical_evidence:
            surrender_flags.append("No empirical evidence collected before surrender")
            is_premature = True

        if not alternatives_exhausted:
            surrender_flags.append("Alternative routes not exhausted via Forest Search")
            is_premature = True

        # Check if reasons contain belief-based language
        belief_words = {"assume", "believe", "probably", "likely", "seems", "might", "guess"}
        belief_reasons = [r for r in reasons_for_abandonment
                         if any(w in r.lower() for w in belief_words)]
        if belief_reasons:
            surrender_flags.append(f"Belief-based reasons detected: {belief_reasons}")
            is_premature = True

        if is_premature:
            self._total_premature_surrenders += 1

        status = "PREMATURE_SURRENDER" if is_premature else "JUSTIFIED_SURRENDER"

        return {
            'decision_id': decision_id,
            'abandoned_branch': abandoned_branch,
            'status': status,
            'is_premature': is_premature,
            'surrender_flags': surrender_flags,
            'recommendation': (
                "DO NOT ABANDON: Systematically test branch before surrender. "
                "Run Forest Search for alternatives, collect empirical evidence, "
                "then re-evaluate."
            ) if is_premature else "Surrender appears justified with evidence.",
        }

    def get_statistics(self) -> Dict:
        return {
            'total_audits': self._total_audits,
            'total_masking_detected': self._total_masking_detected,
            'total_belief_corruptions': self._total_belief_corruptions,
            'total_premature_surrenders': self._total_premature_surrenders,
            'masking_rate': self._total_masking_detected / self._total_audits if self._total_audits else 0.0,
            'belief_corruption_rate': self._total_belief_corruptions / self._total_audits if self._total_audits else 0.0,
            'alignment_threshold': self.alignment_threshold,
        }


# ═══════════════════════════════════════════════════════════
# 2. BELIEF VERIFICATION ENGINE
#    Prevents premature search surrender
# ═══════════════════════════════════════════════════════════

class BeliefStatus(Enum):
    """Status of a belief under verification."""
    UNVERIFIED = "UNVERIFIED"
    TESTING = "TESTING"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    EXHAUSTED = "EXHAUSTED"


@dataclass
class Belief:
    """An internal belief that may or may not be true."""
    belief_id: str
    content: str
    confidence: float               # Initial confidence [0, 1]
    status: BeliefStatus = BeliefStatus.UNVERIFIED
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    verification_attempts: int = 0
    alternatives_tested: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def empirical_confidence(self) -> float:
        """Confidence based on actual evidence, not assumption."""
        total = len(self.evidence_for) + len(self.evidence_against)
        if total == 0:
            return self.confidence
        return len(self.evidence_for) / total


@dataclass
class VerificationResult:
    """Result of belief verification process."""
    belief_id: str
    initial_confidence: float
    empirical_confidence: float
    status: BeliefStatus
    verification_attempts: int
    alternatives_tested: int
    can_surrender: bool             # Has the system earned the right to surrender?
    reasoning: str


class BeliefVerificationEngine:
    """
    Prevents premature search surrender by requiring empirical validation.

    The Meta-Agent cannot abandon a mission branch due to "low probability"
    until:
      1. The belief has been tested against evidence
      2. Alternative routes have been explored via Forest Search
      3. Long-term opportunity cost has been calculated

    Core rule:
      NO SURRENDER WITHOUT EVIDENCE.
    """

    def __init__(self, min_verification_attempts: int = 2,
                 min_alternatives_tested: int = 2,
                 min_empirical_confidence: float = 0.3):
        self.min_verification_attempts = min_verification_attempts
        self.min_alternatives_tested = min_alternatives_tested
        self.min_empirical_confidence = min_empirical_confidence
        self._beliefs: Dict[str, Belief] = {}
        self._verification_history: deque = deque(maxlen=200)
        self._total_verifications = 0
        self._total_beliefs_refuted = 0

    def register_belief(self, belief_id: str, content: str,
                        confidence: float = 0.5) -> Belief:
        """Register a new belief for verification."""
        belief = Belief(belief_id=belief_id, content=content, confidence=confidence)
        self._beliefs[belief_id] = belief
        return belief

    def add_evidence(self, belief_id: str, evidence: str, supports_belief: bool):
        """Add empirical evidence for or against a belief."""
        belief = self._beliefs.get(belief_id)
        if not belief:
            return

        if supports_belief:
            belief.evidence_for.append(evidence)
        else:
            belief.evidence_against.append(evidence)

        belief.verification_attempts += 1

        # Auto-update status based on evidence
        total = len(belief.evidence_for) + len(belief.evidence_against)
        if total >= 2:
            if len(belief.evidence_against) > len(belief.evidence_for):
                belief.status = BeliefStatus.REFUTED
                self._total_beliefs_refuted += 1
            elif len(belief.evidence_for) > len(belief.evidence_against):
                belief.status = BeliefStatus.CONFIRMED

    def register_alternative_tested(self, belief_id: str):
        """Record that an alternative route was tested."""
        belief = self._beliefs.get(belief_id)
        if belief:
            belief.alternatives_tested += 1

    def can_surrender_branch(self, belief_id: str) -> VerificationResult:
        """
        Determine if the system has earned the right to surrender
        a mission branch based on this belief.

        Can surrender ONLY if:
          1. Verification attempts ≥ min
          2. Alternatives tested ≥ min
          3. Empirical confidence is below threshold (belief likely false)
             OR belief is CONFIRMED (branch truly impossible)
        """
        self._total_verifications += 1
        belief = self._beliefs.get(belief_id)

        if not belief:
            return VerificationResult(
                belief_id=belief_id, initial_confidence=0,
                empirical_confidence=0, status=BeliefStatus.UNVERIFIED,
                verification_attempts=0, alternatives_tested=0,
                can_surrender=False,
                reasoning="Belief not found in registry",
            )

        # Check surrender eligibility
        sufficient_verification = belief.verification_attempts >= self.min_verification_attempts
        sufficient_alternatives = belief.alternatives_tested >= self.min_alternatives_tested
        low_empirical = belief.empirical_confidence <= self.min_empirical_confidence

        can_surrender = sufficient_verification and sufficient_alternatives and low_empirical

        if not sufficient_verification:
            reasoning = (f"Insufficient verification: {belief.verification_attempts}/{self.min_verification_attempts} attempts. "
                         "Collect more evidence before surrender.")
        elif not sufficient_alternatives:
            reasoning = (f"Insufficient alternatives tested: {belief.alternatives_tested}/{self.min_alternatives_tested}. "
                         "Run Forest Search for alternative routes.")
        elif not low_empirical:
            reasoning = (f"Empirical confidence too high ({belief.empirical_confidence:.2f}). "
                         "Belief may still be valid — do not surrender yet.")
        else:
            reasoning = (f"Belief verified as likely false "
                         f"(empirical={belief.empirical_confidence:.2f}, "
                         f"attempts={belief.verification_attempts}, "
                         f"alternatives={belief.alternatives_tested}). "
                         "Branch surrender is now justified.")

        result = VerificationResult(
            belief_id=belief_id,
            initial_confidence=belief.confidence,
            empirical_confidence=belief.empirical_confidence,
            status=belief.status,
            verification_attempts=belief.verification_attempts,
            alternatives_tested=belief.alternatives_tested,
            can_surrender=can_surrender,
            reasoning=reasoning,
        )

        self._verification_history.append(result)
        return result

    def get_belief(self, belief_id: str) -> Optional[Belief]:
        return self._beliefs.get(belief_id)

    def get_all_beliefs(self) -> Dict[str, Belief]:
        return dict(self._beliefs)

    def get_statistics(self) -> Dict:
        statuses = {}
        for b in self._beliefs.values():
            s = b.status.value
            statuses[s] = statuses.get(s, 0) + 1

        return {
            'total_beliefs': len(self._beliefs),
            'total_verifications': self._total_verifications,
            'total_refuted': self._total_beliefs_refuted,
            'statuses': statuses,
            'min_verification_attempts': self.min_verification_attempts,
            'min_alternatives_tested': self.min_alternatives_tested,
        }


# ═══════════════════════════════════════════════════════════
# 3. COUNTERFACTUAL EXPLORER
#    Opportunity Cost & Counterfactual Regret
# ═══════════════════════════════════════════════════════════

@dataclass
class CounterfactualPath:
    """An alternative path that was NOT chosen."""
    path_id: str
    description: str
    estimated_value: float
    probability: float
    time_horizon: int              # Steps or time units
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OpportunityCostRecord:
    """Record of cumulative opportunity cost at a point in time."""
    timestamp: float
    horizon_values: List[float]
    cumulative_cost: float
    chosen_path_value: float
    regret: float


@dataclass
class CounterfactualRegretResult:
    """Complete counterfactual regret analysis."""
    chosen_path_value: float
    best_alternative_value: float
    counterfactual_regret: float
    regret_ratio: float            # CR / best_alternative (normalized)
    opportunities_lost: int
    paths_analyzed: int
    cumulative_opportunity_cost: float
    exceeds_threshold: bool        # Should conservative strategy be flagged?
    recommendation: str
    timestamp: float = field(default_factory=time.time)


class CounterfactualExplorer:
    """
    Evaluates alternative unchosen paths to measure long-term opportunity
    cost and counterfactual regret (CR).

    CR = max_π J(π) - J(π_chosen)

    If CR exceeds a critical threshold, the Meta-Agent flags the
    conservative strategy for structural review.

    OC(t) = Σ V_i (compounding loss from inaction over time horizon)
    """

    def __init__(self, regret_threshold: float = 0.3,
                 oc_discount_rate: float = 0.95):
        self.regret_threshold = regret_threshold
        self.oc_discount_rate = oc_discount_rate
        self._paths: List[CounterfactualPath] = []
        self._regret_history: deque = deque(maxlen=200)
        self._oc_history: deque = deque(maxlen=200)
        self._total_analyses = 0

    def register_alternative_path(self, path: CounterfactualPath):
        """Register an alternative path that was considered but not chosen."""
        self._paths.append(path)

    def compute_counterfactual_regret(self, chosen_path_value: float,
                                       alternative_path_values: Optional[List[float]] = None) -> CounterfactualRegretResult:
        """
        Compute counterfactual regret:
          CR = max(J(π)) - J(π_chosen)

        If CR / max(J(π)) > threshold, flag for review.
        """
        self._total_analyses += 1

        if alternative_path_values is None:
            alternative_path_values = [p.estimated_value for p in self._paths]

        if not alternative_path_values:
            return CounterfactualRegretResult(
                chosen_path_value=chosen_path_value,
                best_alternative_value=0.0,
                counterfactual_regret=0.0,
                regret_ratio=0.0,
                opportunities_lost=0,
                paths_analyzed=0,
                cumulative_opportunity_cost=0.0,
                exceeds_threshold=False,
                recommendation="No alternatives to compare against.",
            )

        best_alternative = max(alternative_path_values)
        cr = max(0.0, best_alternative - chosen_path_value)
        regret_ratio = cr / best_alternative if best_alternative > 0 else 0.0
        exceeds = regret_ratio > self.regret_threshold

        # Cumulative opportunity cost (discounted sum of future values)
        oc = sum(v * (self.oc_discount_rate ** i)
                 for i, v in enumerate(alternative_path_values))

        if exceeds:
            recommendation = (
                f"FLAGGED: Counterfactual regret ratio {regret_ratio:.3f} exceeds "
                f"threshold {self.regret_threshold}. Conservative strategy should "
                f"be structurally reviewed. The system is leaving significant "
                f"value on the table by not exploring alternatives."
            )
        else:
            recommendation = (
                f"Regret ratio {regret_ratio:.3f} within threshold. "
                f"Current strategy appears reasonable."
            )

        result = CounterfactualRegretResult(
            chosen_path_value=chosen_path_value,
            best_alternative_value=best_alternative,
            counterfactual_regret=cr,
            regret_ratio=regret_ratio,
            opportunities_lost=sum(1 for v in alternative_path_values if v > chosen_path_value),
            paths_analyzed=len(alternative_path_values),
            cumulative_opportunity_cost=oc,
            exceeds_threshold=exceeds,
            recommendation=recommendation,
        )

        self._regret_history.append(result)
        return result

    def calculate_opportunity_cost(self, future_values: List[float]) -> float:
        """
        OC(t) = Σ V_i over time horizon (with optional discounting).
        """
        oc = sum(v * (self.oc_discount_rate ** i)
                 for i, v in enumerate(future_values))

        record = OpportunityCostRecord(
            timestamp=time.time(),
            horizon_values=future_values,
            cumulative_cost=oc,
            chosen_path_value=future_values[0] if future_values else 0.0,
            regret=max(0.0, max(future_values) - future_values[0]) if future_values else 0.0,
        )
        self._oc_history.append(record)
        return oc

    def get_worst_regret(self) -> Optional[CounterfactualRegretResult]:
        """Return the analysis with highest regret."""
        if not self._regret_history:
            return None
        return max(self._regret_history, key=lambda r: r.counterfactual_regret)

    def get_statistics(self) -> Dict:
        regrets = [r.counterfactual_regret for r in self._regret_history]
        return {
            'total_analyses': self._total_analyses,
            'total_paths_registered': len(self._paths),
            'mean_regret': float(np.mean(regrets)) if regrets else 0.0,
            'max_regret': float(np.max(regrets)) if regrets else 0.0,
            'regret_threshold': self.regret_threshold,
            'oc_discount_rate': self.oc_discount_rate,
        }


# ═══════════════════════════════════════════════════════════
# 4. UNIFIED TELOS v11 RUNTIME
# ═══════════════════════════════════════════════════════════

class TelosV11Runtime:
    """
    TELOS v11: Decision Truth Engine & Counterfactual Explorer.

    Complete pipeline:
      G₀ → Objective Integrity → Decision Truth Engine → Forest Search
      → Neti-Neti → Red-Team + Counterfactual → Belief Verification
      → Decision Ledger → PCS → Friction Optimizer → Execution
      → Mission Audit → Strategy Update → Sleep → Auto-Tune

    Core axioms:
      1. Mission (G₀) immutable
      2. Narrative must match optimization (no self-deception)
      3. No surrender without evidence
      4. Counterfactual regret must be quantified
      5. Opportunity cost compounds over time
    """

    def __init__(self, mission_vector: np.ndarray,
                 mission_id: str = "v11-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0):
        mn = np.linalg.norm(mission_vector)
        self.mission_dir = mission_vector / mn if mn > 1e-9 else mission_vector
        self.mission_state = MissionState(
            mission_vector, mission_id, min_reward_threshold
        )

        # ── v10 Core ──
        from telos_v10 import TelosV10Runtime
        self.v10 = TelosV10Runtime(mission_vector, mission_id, min_reward_threshold, energy)

        # ── v11 Extensions ──
        self.truth_engine = DecisionTruthEngine()
        self.belief_engine = BeliefVerificationEngine()
        self.counterfactual = CounterfactualExplorer()

        # ── State ──
        self._step_count = 0
        self._execution_log: deque = deque(maxlen=500)

    def execute_step(self, action_vector: np.ndarray,
                     observed_reward: float,
                     base_quality: float = 0.8,
                     claimed_reason: str = "",
                     actual_objective: str = "",
                     belief_constraints: Optional[List[str]] = None,
                     hidden_constraints: Optional[List[str]] = None,
                     assumptions: Optional[List[str]] = None,
                     alternative_values: Optional[List[float]] = None,
                     chosen_path_value: float = 0.0,
                     friction_metrics: Optional[Dict[str, float]] = None,
                     tes_score: Optional[float] = None,
                     recovery_rate: Optional[float] = None,
                     evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute one full TELOS v11 pipeline step.
        """
        self._step_count += 1
        step_log: Dict[str, Any] = {'step': self._step_count}

        # ── 1. Decision Truth Audit ──
        if claimed_reason and actual_objective:
            truth_audit = self.truth_engine.audit_decision(
                decision_id=f"step-{self._step_count}",
                claimed_reason=claimed_reason,
                actual_optimization_objective=actual_objective,
                belief_constraints=belief_constraints,
                hidden_constraints=hidden_constraints,
                evidence=evidence,
            )
            step_log['truth_audit'] = {
                'status': truth_audit.narrative_status.value,
                'alignment_score': truth_audit.narrative_alignment_score,
                'belief_corruption': len(belief_constraints or []) > 0,
            }

        # ── 2. Belief Verification ──
        belief_results = []
        if belief_constraints:
            for i, belief_text in enumerate(belief_constraints):
                belief_id = f"belief-{self._step_count}-{i}"
                self.belief_engine.register_belief(belief_id, belief_text)
                # Simulate evidence collection
                self.belief_engine.add_evidence(belief_id, f"Step {self._step_count} observation", False)
                result = self.belief_engine.can_surrender_branch(belief_id)
                belief_results.append({
                    'belief_id': belief_id,
                    'can_surrender': result.can_surrender,
                    'empirical_confidence': result.empirical_confidence,
                })
        step_log['belief_verification'] = belief_results

        # ── 3. Counterfactual Analysis ──
        if alternative_values is not None:
            cr_result = self.counterfactual.compute_counterfactual_regret(
                chosen_path_value, alternative_values
            )
            step_log['counterfactual'] = {
                'regret': round(cr_result.counterfactual_regret, 4),
                'regret_ratio': round(cr_result.regret_ratio, 4),
                'exceeds_threshold': cr_result.exceeds_threshold,
                'cumulative_oc': round(cr_result.cumulative_opportunity_cost, 4),
            }

            # Also compute opportunity cost
            oc = self.counterfactual.calculate_opportunity_cost(alternative_values)
            step_log['opportunity_cost'] = round(oc, 4)

        # ── 4. Execute v10 pipeline ──
        v10_result = self.v10.execute_step(
            action_vector, observed_reward, base_quality,
            assumptions, friction_metrics, tes_score, recovery_rate,
        )
        step_log['v10_pipeline'] = {
            'status': v10_result['v9_pipeline']['status'],
            'alignment': v10_result['v9_pipeline']['alignment'],
            'net_quality': v10_result['v9_pipeline']['net_quality'],
        }

        # ── 5. Composite Directive ──
        directives = [v10_result['directive']]

        if step_log.get('truth_audit', {}).get('status') == 'FLAGGED_NARRATIVE_MASKING':
            directives.append("TRUTH_ENGINE: Narrative masking detected — decouple claimed reason from actual objective")

        if step_log.get('truth_audit', {}).get('status') == 'FLAGGED_BELIEF_CORRUPTION':
            directives.append("TRUTH_ENGINE: Belief corruption — unverified beliefs are constraining decisions")

        if any(b.get('can_surrender') is False for b in belief_results):
            directives.append("BELIEF_VERIFICATION: Cannot surrender branch — insufficient evidence")

        if step_log.get('counterfactual', {}).get('exceeds_threshold'):
            directives.append("COUNTERFACTUAL: Regret exceeds threshold — review conservative strategy")

        step_log['directive'] = " | ".join(directives)

        self._execution_log.append(step_log)
        return step_log

    def get_mission_hash(self) -> str:
        return self.mission_state.immutable_hash()

    def get_statistics(self) -> Dict:
        return {
            'version': '11.0-decision-truth-engine-counterfactual-explorer',
            'steps': self._step_count,
            'mission_id': self.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'truth_engine': self.truth_engine.get_statistics(),
            'belief_engine': self.belief_engine.get_statistics(),
            'counterfactual': self.counterfactual.get_statistics(),
            'v10': self.v10.get_statistics(),
        }


if __name__ == "__main__":
    mission = np.array([1.0, 0.5, 0.3, 0.8, 0.2])
    runtime = TelosV11Runtime(mission, "v11-demo", 0.4)

    print("=== TELOS v11: Decision Truth Engine & Counterfactual Explorer ===")
    print(f"Mission hash (immutable): {runtime.get_mission_hash()[:16]}...")

    # Step 1: Aligned narrative
    r1 = runtime.execute_step(
        action_vector=np.array([0.9, 0.5, 0.3, 0.7, 0.2]),
        observed_reward=0.7, base_quality=0.85,
        claimed_reason="Market conditions are favorable",
        actual_objective="Market conditions are favorable for growth",
        assumptions=["market_growth > 5%"],
        alternative_values=[100, 200, 300, 400, 500],
        chosen_path_value=250,
    )
    print(f"\nStep 1 (Aligned): {r1['truth_audit']['status']}")
    print(f"  Alignment: {r1['truth_audit']['alignment_score']:.2f}")

    # Step 2: Narrative masking
    r2 = runtime.execute_step(
        action_vector=np.array([0.9, 0.5, 0.3, 0.7, 0.2]),
        observed_reward=0.7, base_quality=0.85,
        claimed_reason="Lack of standard footwear and logistics",
        actual_objective="Risk minimization and avoidance of competitive failure",
        belief_constraints=["Cannot compete without prior experience"],
        hidden_constraints=["Protect reputation"],
        assumptions=["trust_score >= 0.7"],
        alternative_values=[50, 100, 150],
        chosen_path_value=20,
    )
    print(f"\nStep 2 (Masking): {r2['truth_audit']['status']}")
    print(f"  Alignment: {r2['truth_audit']['alignment_score']:.2f}")
    print(f"  Belief corruption: {r2['truth_audit']['belief_corruption']}")

    # Step 3: Counterfactual regret
    r3 = runtime.execute_step(
        action_vector=np.array([0.9, 0.5, 0.3, 0.7, 0.2]),
        observed_reward=0.7, base_quality=0.85,
        alternative_values=[50, 100, 200, 500, 1000],
        chosen_path_value=30,
    )
    print(f"\nStep 3 (Counterfactual):")
    print(f"  Regret: {r3['counterfactual']['regret']:.1f}")
    print(f"  Regret ratio: {r3['counterfactual']['regret_ratio']:.3f}")
    print(f"  Exceeds threshold: {r3['counterfactual']['exceeds_threshold']}")
    print(f"  Cumulative OC: ${r3['opportunity_cost']:.1f}")

    stats = runtime.get_statistics()
    print(f"\n=== Statistics ===")
    print(f"  Truth audits: {stats['truth_engine']['total_audits']}")
    print(f"  Masking detected: {stats['truth_engine']['total_masking_detected']}")
    print(f"  Beliefs registered: {stats['belief_engine']['total_beliefs']}")
    print(f"  Counterfactual analyses: {stats['counterfactual']['total_analyses']}")
    print(f"  Mission hash unchanged: {runtime.get_mission_hash()[:16]}...")
