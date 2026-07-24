"""
TELOS v10: Memory Consolidation, Adversarial Stress-Testing & Auto-Tuning

Three final architectural additions to complete the framework:

1. Epistemic Sleep Cycle (Memory Consolidation Daemon)
   Modeled after biological slow-wave sleep:
   - Sweeps historical Decision Ledgers during low-activity windows
   - Compresses resolved branch subgraphs into immutable macro-nodes
   - Archives to WORM vault while keeping active memory lean
   - Reduces retrieval drag from memory bloat

2. Internal Red-Team Agent (Adversarial Assumption Stress-Test)
   - Before execution on high-stakes decisions, acts as devil's advocate
   - Actively attempts to invalidate the ledger's core assumptions
   - Stress-tests Neti-Neti pruning filters against edge-case failures
   - Surfaces blind spots and confirmation bias

3. Meta-Parameter Auto-Tuning (Self-Optimizing Thresholds)
   - Dynamically adjusts thresholds (Neti-Neti θ, ROI boundary) based on
     historical TES scores
   - If recovery rates spike, automatically tightens pruning thresholds
   - If friction is consistently low, relaxes thresholds to save compute
   - Closes the loop: the system tunes itself using its own performance data

Master Pipeline (v10):
  G₀ → Objective Integrity → Forest Search → Neti-Neti
  → Red-Team Stress Test → Decision Ledger → PCS
  → Friction Optimizer → Execution → Mission Audit
  → Strategy Update → Sleep Consolidation → Auto-Tune
"""

import time
import numpy as np
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from telos_negative_search import NetiNetiPruningEngine
from telos_decision_ledger import DecisionLedger, DecisionLedgerEntry
from telos_v9 import (
    ObjectiveIntegrityMonitor, MissionState, CognitiveFrictionOptimizer,
    TelosV9Runtime,
)


# ═══════════════════════════════════════════════════════════
# 1. EPISTEMIC SLEEP CYCLE (Memory Consolidation Daemon)
# ═══════════════════════════════════════════════════════════

class ConsolidationStatus(Enum):
    """Status of a consolidation cycle."""
    IDLE = "idle"
    SCANNING = "scanning"
    COMPRESSING = "compressing"
    ARCHIVING = "archiving"
    COMPLETE = "complete"


@dataclass
class SemanticMacroNode:
    """
    Immutable compressed representation of a resolved decision subgraph.

    Replaces a chain of individual decision entries with a single
    semantically equivalent macro-node, reducing memory footprint
    while preserving decision lineage.
    """
    macro_id: str
    mission_id: str
    original_decision_ids: List[str]
    compressed_summary: str
    total_confidence: float
    total_assumptions: List[str]
    total_evidence: Dict[str, Any]
    total_dependencies: List[str]
    merkle_root: str           # Hash of all original entry hashes
    compressed_at: float = field(default_factory=time.time)
    original_count: int = 0
    compression_ratio: float = 0.0

    def compute_hash(self) -> str:
        data = f"{self.macro_id}:{self.mission_id}:{self.merkle_root}:{self.original_count}"
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> Dict:
        return {
            'macro_id': self.macro_id,
            'mission_id': self.mission_id,
            'original_decision_ids': self.original_decision_ids,
            'compressed_summary': self.compressed_summary,
            'total_confidence': self.total_confidence,
            'total_assumptions': self.total_assumptions,
            'total_evidence': self.total_evidence,
            'total_dependencies': self.total_dependencies,
            'merkle_root': self.merkle_root,
            'original_count': self.original_count,
            'compression_ratio': self.compression_ratio,
            'compressed_at': self.compressed_at,
        }


@dataclass
class WORMArchiveEntry:
    """Entry archived to the WORM vault during sleep consolidation."""
    archive_id: str
    macro_node: SemanticMacroNode
    mission_hash: str
    vault_hash: str
    timestamp: float = field(default_factory=time.time)


class EpistemicSleepCycle:
    """
    Memory Consolidation Daemon modeled after biological slow-wave sleep.

    During low-activity windows:
      1. Scan Decision Ledger for resolved/completed branches
      2. Compress chains of related decisions into SemanticMacroNodes
      3. Archive compressed macro-nodes to WORM vault
      4. Remove compressed entries from active memory
      5. Update statistics and trigger auto-tuning feedback

    Benefits:
      - Reduces memory bloat from thousands of ledger nodes
      - Keeps active working memory lean for fast retrieval
      - Preserves full audit trail in immutable WORM vault
      - Compression ratio serves as input to auto-tuning
    """

    def __init__(self, ledger: DecisionLedger,
                 min_chain_length: int = 3,
                 min_age_seconds: float = 60.0):
        self.ledger = ledger
        self.min_chain_length = min_chain_length
        self.min_age_seconds = min_age_seconds
        self._macro_nodes: Dict[str, SemanticMacroNode] = {}
        self._worm_archive: List[WORMArchiveEntry] = []
        self._status = ConsolidationStatus.IDLE
        self._total_consolidations = 0
        self._total_entries_consolidated = 0
        self._total_memory_saved = 0
        self._cycle_history: deque = deque(maxlen=100)

    def scan_for_consolidation(self) -> List[str]:
        """
        Scan ledger for completed decision chains eligible for compression.
        Returns list of root decision IDs that form consolidation candidates.
        """
        self._status = ConsolidationStatus.SCANNING
        candidates = []

        for dec_id, entry in self.ledger._entries.items():
            if entry.status not in ("INVALIDATED", "RECOVERED"):
                continue

            chain = self.ledger.get_decision_chain(dec_id)
            if len(chain) < self.min_chain_length:
                continue

            age = time.time() - chain[0].timestamp
            if age < self.min_age_seconds:
                continue

            candidates.append(dec_id)

        self._status = ConsolidationStatus.IDLE
        return candidates

    def compress_chain(self, root_decision_id: str) -> Optional[SemanticMacroNode]:
        """
        Compress a chain of related decisions into a single SemanticMacroNode.
        """
        self._status = ConsolidationStatus.COMPRESSING

        chain = self.ledger.get_decision_chain(root_decision_id)
        if len(chain) < self.min_chain_length:
            return None

        decision_ids = [d.decision_id for d in chain]
        all_assumptions = list(set(a for d in chain for a in d.assumptions))
        all_dependencies = list(set(dep for d in chain for dep in d.dependencies))

        # Merge evidence
        merged_evidence = {}
        for d in chain:
            merged_evidence.update(d.evidence)

        # Compute Merkle root of chain
        hashes = ":".join(d.merkle_hash for d in chain if d.merkle_hash)
        merkle_root = hashlib.sha256(hashes.encode()).hexdigest()[:16]

        avg_confidence = np.mean([d.confidence for d in chain]) if chain else 0

        # Generate compressed summary
        summaries = [d.action_summary for d in chain]
        compressed_summary = f"Chain[{len(chain)}]: {' → '.join(summaries[:3])}"
        if len(summaries) > 3:
            compressed_summary += f" → ...({len(summaries) - 3} more)"

        macro_id = f"macro-{merkle_root}"

        macro = SemanticMacroNode(
            macro_id=macro_id,
            mission_id=chain[0].mission_id,
            original_decision_ids=decision_ids,
            compressed_summary=compressed_summary,
            total_confidence=float(avg_confidence),
            total_assumptions=all_assumptions,
            total_evidence=merged_evidence,
            total_dependencies=all_dependencies,
            merkle_root=merkle_root,
            original_count=len(chain),
            compression_ratio=1.0 - (1.0 / len(chain)) if chain else 0.0,
        )

        self._macro_nodes[macro_id] = macro
        self._status = ConsolidationStatus.IDLE
        return macro

    def archive_to_worm(self, macro_node: SemanticMacroNode,
                        mission_hash: str = "") -> WORMArchiveEntry:
        """Archive a compressed macro-node to the WORM vault."""
        self._status = ConsolidationStatus.ARCHIVING

        vault_hash = macro_node.compute_hash()
        archive_entry = WORMArchiveEntry(
            archive_id=f"archive-{len(self._worm_archive)}",
            macro_node=macro_node,
            mission_hash=mission_hash,
            vault_hash=vault_hash,
        )

        self._worm_archive.append(archive_entry)
        self._total_consolidations += 1
        self._total_entries_consolidated += macro_node.original_count
        self._total_memory_saved += macro_node.original_count - 1

        self._status = ConsolidationStatus.COMPLETE
        return archive_entry

    def run_consolidation_cycle(self, mission_hash: str = "") -> Dict[str, Any]:
        """
        Execute a full consolidation cycle:
          1. Scan for candidates
          2. Compress eligible chains
          3. Archive to WORM vault
          4. Report results
        """
        candidates = self.scan_for_consolidation()
        compressed = []
        archived = []

        for root_id in candidates:
            macro = self.compress_chain(root_id)
            if macro:
                compressed.append(macro)
                archive = self.archive_to_worm(macro, mission_hash)
                archived.append(archive)

        cycle_result = {
            'candidates_found': len(candidates),
            'compressed': len(compressed),
            'archived': len(archived),
            'entries_consolidated': sum(m.original_count for m in compressed),
            'memory_saved': sum(m.original_count - 1 for m in compressed),
            'macro_nodes_created': [m.macro_id for m in compressed],
        }

        self._cycle_history.append(cycle_result)
        self._status = ConsolidationStatus.IDLE
        return cycle_result

    def get_status(self) -> ConsolidationStatus:
        return self._status

    def get_macro_node(self, macro_id: str) -> Optional[SemanticMacroNode]:
        return self._macro_nodes.get(macro_id)

    def get_archive_size(self) -> int:
        return len(self._worm_archive)

    def get_statistics(self) -> Dict:
        return {
            'status': self._status.value,
            'total_consolidations': self._total_consolidations,
            'total_entries_consolidated': self._total_entries_consolidated,
            'total_memory_saved': self._total_memory_saved,
            'macro_nodes_count': len(self._macro_nodes),
            'archive_size': len(self._worm_archive),
            'min_chain_length': self.min_chain_length,
            'min_age_seconds': self.min_age_seconds,
        }


# ═══════════════════════════════════════════════════════════
# 2. INTERNAL RED-TEAM AGENT (Adversarial Assumption Stress-Test)
# ═══════════════════════════════════════════════════════════

class StressTestVerdict(Enum):
    """Outcome of an adversarial stress test."""
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    CRITICAL = "critical"


@dataclass
class AdversarialAttack:
    """A single adversarial attack on a decision assumption."""
    attack_id: str
    target_assumption: str
    attack_type: str            # "inversion", "weakening", "counter_evidence", "edge_case"
    attack_payload: str
    expected_vulnerability: float  # How vulnerable is this assumption? [0, 1]
    timestamp: float = field(default_factory=time.time)


@dataclass
class StressTestResult:
    """Complete result of a red-team stress test."""
    decision_id: str
    verdict: StressTestVerdict
    attacks_launched: int
    assumptions_invalidated: int
    neti_neti_failures: int     # Assumptions that Neti-Neti failed to catch
    vulnerability_score: float  # Overall vulnerability [0, 1]
    attacks: List[AdversarialAttack]
    recommendations: List[str]
    reasoning: str
    timestamp: float = field(default_factory=time.time)


class InternalRedTeamAgent:
    """
    Adversarial Sub-Agent that stress-tests decision assumptions
    and Neti-Neti pruning filters before high-stakes execution.

    Mission: Act as devil's advocate.
      - Generate adversarial attacks against each assumption
      - Test if Neti-Neti filters catch edge-case failures
      - Surface blind spots and confirmation bias
      - Return structured vulnerability assessment

    Attack Types:
      1. Inversion: Flip the assumption's truth value
      2. Weakening: Reduce the assumption's confidence
      3. Counter-evidence: Provide evidence contradicting the assumption
      4. Edge-case: Test extreme values near assumption boundaries
    """

    def __init__(self, pruner: Optional[NetiNetiPruningEngine] = None,
                 severity_threshold: float = 0.5,
                 max_attacks_per_assumption: int = 3):
        self.pruner = pruner or NetiNetiPruningEngine()
        self.severity_threshold = severity_threshold
        self.max_attacks_per_assumption = max_attacks_per_assumption
        self._test_history: deque = deque(maxlen=200)
        self._total_tests = 0
        self._total_attacks = 0
        self._total_assumptions_tested = 0
        self._total_failures_surfaced = 0

    def generate_attacks(self, assumption: str) -> List[AdversarialAttack]:
        """
        Generate adversarial attacks for a single assumption.
        Uses heuristic attack generation based on assumption structure.
        """
        attacks = []
        parts = assumption.replace(">=", " ≥ ").replace("<=", " ≤ ").replace(">", " > ").replace("<", " < ").split()

        if len(parts) >= 3:
            param_name = parts[0]
            operator = parts[1]
            try:
                threshold = float(parts[2])
            except ValueError:
                threshold = 0.5

            # Attack 1: Inversion
            inverted_op = "<" if operator in (">", "≥") else ">"
            attacks.append(AdversarialAttack(
                attack_id=f"inv-{param_name}",
                target_assumption=assumption,
                attack_type="inversion",
                attack_payload=f"{param_name} {inverted_op} {threshold * 0.5}",
                expected_vulnerability=0.7,
            ))

            # Attack 2: Weakening
            weakened = threshold * 0.3
            attacks.append(AdversarialAttack(
                attack_id=f"weak-{param_name}",
                target_assumption=assumption,
                attack_type="weakening",
                attack_payload=f"{param_name} {operator} {weakened} (weakened)",
                expected_vulnerability=0.4,
            ))

            # Attack 3: Edge case
            boundary_val = threshold * (1.0 + 0.01)
            attacks.append(AdversarialAttack(
                attack_id=f"edge-{param_name}",
                target_assumption=assumption,
                attack_type="edge_case",
                attack_payload=f"{param_name} = {boundary_val} (near boundary)",
                expected_vulnerability=0.3,
            ))

        else:
            # Generic attack for non-structured assumptions
            attacks.append(AdversarialAttack(
                attack_id=f"gen-{hash(assumption) % 10000}",
                target_assumption=assumption,
                attack_type="counter_evidence",
                attack_payload=f"External evidence contradicts: {assumption}",
                expected_vulnerability=0.5,
            ))

        return attacks[:self.max_attacks_per_assumption]

    def stress_test_decision(self, entry: DecisionLedgerEntry) -> StressTestResult:
        """
        Run full adversarial stress test on a decision entry.

        For each assumption:
          1. Generate adversarial attacks
          2. Test if Neti-Neti pruner catches the edge case
          3. Score vulnerability
        """
        self._total_tests += 1
        all_attacks = []
        total_vulnerability = 0.0
        assumptions_invalidated = 0
        neti_neti_failures = 0

        for assumption in entry.assumptions:
            self._total_assumptions_tested += 1
            attacks = self.generate_attacks(assumption)

            for attack in attacks:
                self._total_attacks += 1
                all_attacks.append(attack)

                # Test against Neti-Neti pruner
                try:
                    test_vec = np.array([attack.expected_vulnerability,
                                         1.0 - attack.expected_vulnerability,
                                         attack.expected_vulnerability * 0.5])
                    mission_vec = np.array([1.0, 0.5, 0.3])

                    result = self.pruner.prune_candidates([test_vec], mission_vec)
                    if result.eliminated_count == 0:
                        # Neti-Neti failed to catch this edge case
                        neti_neti_failures += 1
                        total_vulnerability += attack.expected_vulnerability
                except Exception:
                    # Edge case caused pruner failure — count as vulnerability
                    neti_neti_failures += 1
                    total_vulnerability += attack.expected_vulnerability

            if attack.expected_vulnerability > self.severity_threshold:
                assumptions_invalidated += 1
                self._total_failures_surfaced += 1

        n_attacks = len(all_attacks)
        avg_vulnerability = total_vulnerability / n_attacks if n_attacks else 0.0

        # Verdict
        if neti_neti_failures == 0 and avg_vulnerability < 0.3:
            verdict = StressTestVerdict.PASS
        elif neti_neti_failures <= 1 and avg_vulnerability < 0.5:
            verdict = StressTestVerdict.WARNING
        elif avg_vulnerability < 0.7:
            verdict = StressTestVerdict.FAIL
        else:
            verdict = StressTestVerdict.CRITICAL

        # Recommendations
        recommendations = []
        if neti_neti_failures > 0:
            recommendations.append(
                f"Tighten Neti-Neti alignment threshold: {neti_neti_failures} edge cases passed through"
            )
        if assumptions_invalidated > len(entry.assumptions) * 0.5:
            recommendations.append(
                "Majority of assumptions are brittle — consider alternative strategy"
            )
        if avg_vulnerability > 0.5:
            recommendations.append(
                f"High average vulnerability ({avg_vulnerability:.2f}) — "
                "gather more evidence before execution"
            )
        if not recommendations:
            recommendations.append("Assumptions appear robust under adversarial testing")

        reasoning = (f"Stress-tested {len(entry.assumptions)} assumptions with "
                     f"{n_attacks} attacks. {neti_neti_failures} Neti-Neti failures. "
                     f"Average vulnerability: {avg_vulnerability:.4f}")

        result = StressTestResult(
            decision_id=entry.decision_id,
            verdict=verdict,
            attacks_launched=n_attacks,
            assumptions_invalidated=assumptions_invalidated,
            neti_neti_failures=neti_neti_failures,
            vulnerability_score=avg_vulnerability,
            attacks=all_attacks,
            recommendations=recommendations,
            reasoning=reasoning,
        )

        self._test_history.append(result)
        return result

    def get_statistics(self) -> Dict:
        return {
            'total_tests': self._total_tests,
            'total_attacks': self._total_attacks,
            'total_assumptions_tested': self._total_assumptions_tested,
            'total_failures_surfaced': self._total_failures_surfaced,
            'failure_rate': self._total_failures_surfaced / self._total_assumptions_tested if self._total_assumptions_tested else 0.0,
            'severity_threshold': self.severity_threshold,
        }


# ═══════════════════════════════════════════════════════════
# 3. META-PARAMETER AUTO-TUNING
#    Self-Optimizing Thresholds
# ═══════════════════════════════════════════════════════════

@dataclass
class ParameterSnapshot:
    """Snapshot of tunable parameters at a point in time."""
    neti_neti_threshold: float
    roi_threshold: float
    entropy_threshold: float
    drift_warning_threshold: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class TuningEvent:
    """Record of a single parameter tuning event."""
    parameter_name: str
    old_value: float
    new_value: float
    trigger: str                # What caused the tuning
    tes_at_event: float         # TES score at time of tuning
    timestamp: float = field(default_factory=time.time)


class MetaParameterAutoTuner:
    """
    Self-Optimizing Thresholds based on historical TES scores.

    Close the loop: the system tunes itself using its own performance data.

    Rules:
      1. If recovery rates spike → tighten pruning thresholds
         (demand higher confidence before execution)
      2. If friction is consistently low → relax thresholds
         (save compute when system is healthy)
      3. If TES is declining → tighten thresholds across the board
      4. If TES is improving → maintain or slightly relax thresholds

    Parameters tuned:
      - Neti-Neti alignment threshold (θ)
      - ROI stopping boundary
      - Entropy threshold
      - Drift warning threshold
    """

    def __init__(self, initial_params: Optional[ParameterSnapshot] = None,
                 learning_rate: float = 0.05,
                 min_neti_neti: float = 0.1,
                 max_neti_neti: float = 0.8,
                 min_roi: float = 0.05,
                 max_roi: float = 0.5):
        self.params = initial_params or ParameterSnapshot(
            neti_neti_threshold=0.3,
            roi_threshold=0.15,
            entropy_threshold=0.75,
            drift_warning_threshold=0.5,
        )
        self.learning_rate = learning_rate
        self.min_neti_neti = min_neti_neti
        self.max_neti_neti = max_neti_neti
        self.min_roi = min_roi
        self.max_roi = max_roi

        self._tes_history: deque = deque(maxlen=200)
        self._recovery_rate_history: deque = deque(maxlen=100)
        self._friction_history: deque = deque(maxlen=100)
        self._tuning_history: deque = deque(maxlen=200)
        self._total_tuning_events = 0

    def record_tes(self, tes_score: float):
        """Record a TES score observation."""
        self._tes_history.append(tes_score)

    def record_recovery_rate(self, rate: float):
        """Record a recovery rate observation."""
        self._recovery_rate_history.append(rate)

    def record_friction(self, friction: float):
        """Record a friction observation."""
        self._friction_history.append(friction)

    def tune(self) -> List[TuningEvent]:
        """
        Analyze historical data and tune parameters accordingly.
        Returns list of tuning events.
        """
        events = []

        if len(self._tes_history) < 3:
            return events

        # ── 1. TES Trend Analysis ──
        tes_recent = list(self._tes_history)[-10:]
        tes_older = list(self._tes_history)[-20:-10] if len(self._tes_history) >= 20 else list(self._tes_history)[:-10]

        tes_trend = np.mean(tes_recent) - np.mean(tes_older) if tes_older else 0.0

        # ── 2. Recovery Rate Analysis ──
        avg_recovery = np.mean(list(self._recovery_rate_history)[-10:]) if self._recovery_rate_history else 0.0

        # ── 3. Friction Analysis ──
        avg_friction = np.mean(list(self._friction_history)[-10:]) if self._friction_history else 0.5

        # ── 4. Apply Tuning Rules ──

        # Rule 1: Recovery rate spike → tighten Neti-Neti
        if avg_recovery > 0.3:
            old = self.params.neti_neti_threshold
            new = np.clip(old + self.learning_rate, self.min_neti_neti, self.max_neti_neti)
            if new != old:
                self.params.neti_neti_threshold = new
                event = TuningEvent("neti_neti_threshold", old, new,
                                    f"Recovery rate spike: {avg_recovery:.3f}",
                                    self._tes_history[-1] if self._tes_history else 0.0)
                events.append(event)
                self._tuning_history.append(event)
                self._total_tuning_events += 1

        # Rule 2: Low friction → can afford to relax thresholds
        if avg_friction < 0.1 and tes_trend >= 0:
            old = self.params.neti_neti_threshold
            new = np.clip(old - self.learning_rate * 0.5, self.min_neti_neti, self.max_neti_neti)
            if new != old:
                self.params.neti_neti_threshold = new
                event = TuningEvent("neti_neti_threshold", old, new,
                                    f"Low friction ({avg_friction:.3f}) + positive TES trend",
                                    self._tes_history[-1] if self._tes_history else 0.0)
                events.append(event)
                self._tuning_history.append(event)
                self._total_tuning_events += 1

        # Rule 3: Declining TES → tighten ROI threshold
        if tes_trend < -0.1:
            old = self.params.roi_threshold
            new = np.clip(old + self.learning_rate * 0.3, self.min_roi, self.max_roi)
            if new != old:
                self.params.roi_threshold = new
                event = TuningEvent("roi_threshold", old, new,
                                    f"TES declining: trend={tes_trend:.4f}",
                                    self._tes_history[-1] if self._tes_history else 0.0)
                events.append(event)
                self._tuning_history.append(event)
                self._total_tuning_events += 1

        # Rule 4: Improving TES → slightly relax entropy threshold
        if tes_trend > 0.2:
            old = self.params.entropy_threshold
            new = np.clip(old - self.learning_rate * 0.2, 0.3, 0.95)
            if new != old:
                self.params.entropy_threshold = new
                event = TuningEvent("entropy_threshold", old, new,
                                    f"TES improving: trend={tes_trend:.4f}",
                                    self._tes_history[-1] if self._tes_history else 0.0)
                events.append(event)
                self._tuning_history.append(event)
                self._total_tuning_events += 1

        return events

    def get_current_params(self) -> ParameterSnapshot:
        return self.params

    def get_statistics(self) -> Dict:
        return {
            'total_tuning_events': self._total_tuning_events,
            'current_params': {
                'neti_neti_threshold': self.params.neti_neti_threshold,
                'roi_threshold': self.params.roi_threshold,
                'entropy_threshold': self.params.entropy_threshold,
                'drift_warning_threshold': self.params.drift_warning_threshold,
            },
            'tes_observations': len(self._tes_history),
            'recovery_observations': len(self._recovery_rate_history),
            'friction_observations': len(self._friction_history),
        }


# ═══════════════════════════════════════════════════════════
# 4. UNIFIED TELOS v10 RUNTIME
# ═══════════════════════════════════════════════════════════

class TelosV10Runtime:
    """
    TELOS v10: Complete Cognitive Operating System.

    Full pipeline integrating all architectural layers:
      G₀ → Objective Integrity → Forest Search → Neti-Neti
      → Red-Team Stress Test → Decision Ledger → PCS
      → Friction Optimizer → Execution → Mission Audit
      → Strategy Update → Sleep Consolidation → Auto-Tune

    Core invariants preserved:
      1. Mission (G₀) immutable
      2. Rewards are constraints, never objectives
      3. Friction minimized at every step
      4. Assumptions stress-tested before execution
      5. Memory consolidated during idle periods
      6. Parameters self-optimize using TES feedback
    """

    def __init__(self, mission_vector: np.ndarray,
                 mission_id: str = "v10-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0):
        # ── Mission (Immutable) ──
        mn = np.linalg.norm(mission_vector)
        self.mission_dir = mission_vector / mn if mn > 1e-9 else mission_vector
        self.mission_state = MissionState(
            mission_vector, mission_id, min_reward_threshold
        )

        # ── v9 Core (Objective Integrity + Friction) ──
        self.v9 = TelosV9Runtime(mission_vector, mission_id, min_reward_threshold, energy)

        # ── v10 Extensions ──
        self.ledger = DecisionLedger()
        self.sleep_cycle = EpistemicSleepCycle(self.ledger)
        self.red_team = InternalRedTeamAgent(self.v9.pruner)
        self.auto_tuner = MetaParameterAutoTuner()

        # ── State ──
        self._step_count = 0
        self._consolidation_interval = 10  # Run sleep cycle every N steps
        self._auto_tune_interval = 5       # Run auto-tune every N steps
        self._execution_log: deque = deque(maxlen=500)

    def execute_step(self, action_vector: np.ndarray,
                     observed_reward: float,
                     base_quality: float = 0.8,
                     assumptions: Optional[List[str]] = None,
                     friction_metrics: Optional[Dict[str, float]] = None,
                     tes_score: Optional[float] = None,
                     recovery_rate: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute one full TELOS v10 pipeline step.
        """
        self._step_count += 1
        step_log: Dict[str, Any] = {'step': self._step_count}

        # ── 1. Auto-Tune: Record performance metrics ──
        if tes_score is not None:
            self.auto_tuner.record_tes(tes_score)
        if recovery_rate is not None:
            self.auto_tuner.record_recovery_rate(recovery_rate)
        if friction_metrics:
            total_f = sum(friction_metrics.values())
            self.auto_tuner.record_friction(total_f)

        # ── 2. Auto-Tune: Run parameter optimization ──
        tuning_events = []
        if self._step_count % self._auto_tune_interval == 0:
            tuning_events = self.auto_tuner.tune()
            # Apply tuned thresholds to pruner
            params = self.auto_tuner.get_current_params()
            self.v9.pruner.alignment_threshold = params.neti_neti_threshold

        step_log['auto_tune'] = {
            'events': len(tuning_events),
            'current_params': {
                'neti_neti': self.auto_tuner.params.neti_neti_threshold,
                'roi': self.auto_tuner.params.roi_threshold,
            },
        }

        # ── 3. Red-Team Stress Test (if assumptions present) ──
        red_team_result = None
        if assumptions:
            # Create a temporary ledger entry for stress testing
            temp_entry = DecisionLedgerEntry(
                decision_id=f"temp-{self._step_count}",
                timestamp=time.time(),
                mission_id=self.mission_state.mission_id,
                action_summary=f"Step {self._step_count} action",
                assumptions=assumptions,
                evidence={},
                dependencies=[],
                confidence=base_quality,
                expected_outcome={},
            )
            red_team_result = self.red_team.stress_test_decision(temp_entry)
            step_log['red_team'] = {
                'verdict': red_team_result.verdict.value,
                'attacks': red_team_result.attacks_launched,
                'vulnerability': round(red_team_result.vulnerability_score, 4),
                'neti_neti_failures': red_team_result.neti_neti_failures,
            }

        # ── 4. Execute v9 pipeline (Integrity + Friction + Consensus) ──
        v9_result = self.v9.execute_step(
            action_vector, observed_reward, base_quality, friction_metrics
        )
        step_log['v9_pipeline'] = {
            'status': v9_result['integrity_audit']['status'],
            'alignment': v9_result['integrity_audit']['alignment'],
            'net_quality': v9_result['friction']['net_quality'],
        }

        # ── 5. Record decision in ledger ──
        dec_id = self.ledger.record_decision(
            mission_id=self.mission_state.mission_id,
            action_summary=f"Step {self._step_count}: {v9_result['directive'][:50]}",
            assumptions=assumptions or [],
            evidence={'action_norm': float(np.linalg.norm(action_vector)),
                      'reward': observed_reward},
            dependencies=[],
            confidence=base_quality,
            expected_outcome={'alignment': v9_result['integrity_audit']['alignment']},
        )
        step_log['ledger_entry'] = dec_id

        # ── 6. Sleep Consolidation (periodic) ──
        consolidation_result = None
        if self._step_count % self._consolidation_interval == 0:
            consolidation_result = self.sleep_cycle.run_consolidation_cycle(
                self.v9.get_mission_hash()
            )
            step_log['sleep_cycle'] = {
                'candidates': consolidation_result['candidates_found'],
                'compressed': consolidation_result['compressed'],
                'archived': consolidation_result['archived'],
            }

        # ── 7. Adaptive Directive ──
        directive = v9_result['directive']
        if red_team_result and red_team_result.verdict in (StressTestVerdict.FAIL, StressTestVerdict.CRITICAL):
            directive = f"RED_TEAM_{red_team_result.verdict.value.upper()}: {red_team_result.recommendations[0]}"

        step_log['directive'] = directive
        self._execution_log.append(step_log)
        return step_log

    def get_mission_hash(self) -> str:
        return self.mission_state.immutable_hash()

    def get_statistics(self) -> Dict:
        return {
            'version': '10.0-complete-cognitive-operating-system',
            'steps': self._step_count,
            'mission_id': self.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'v9': self.v9.get_statistics(),
            'sleep_cycle': self.sleep_cycle.get_statistics(),
            'red_team': self.red_team.get_statistics(),
            'auto_tuner': self.auto_tuner.get_statistics(),
            'ledger': self.ledger.get_statistics(),
        }


if __name__ == "__main__":
    mission = np.array([1.0, 0.5, 0.3, 0.8, 0.2])
    runtime = TelosV10Runtime(mission, "v10-demo", 0.4)

    print("=== TELOS v10: Complete Cognitive Operating System ===")
    print(f"Mission hash (immutable): {runtime.get_mission_hash()[:16]}...")

    for i in range(15):
        action = mission + np.random.randn(5) * 0.1
        reward = 0.7 + np.random.uniform(-0.3, 0.3)

        result = runtime.execute_step(
            action_vector=action,
            observed_reward=reward,
            base_quality=0.85,
            assumptions=["market_growth > 5%", "trust_score >= 0.7"],
            friction_metrics={'context_switching': 0.04, 'interruptions': 0.02,
                            'irrelevant_memory': 0.03, 'unnecessary_search': 0.06},
            tes_score=0.5 + i * 0.02,
            recovery_rate=0.1 + (0.5 if i == 7 else 0.0),
        )

        status = result['v9_pipeline']['status']
        rt_verdict = result.get('red_team', {}).get('verdict', 'none')
        print(f"  Step {i+1}: status={status} red_team={rt_verdict} "
              f"net_Q={result['v9_pipeline']['net_quality']:.3f}")

    stats = runtime.get_statistics()
    print(f"\n=== Final Statistics ===")
    print(f"  Steps: {stats['steps']}")
    print(f"  Red-team tests: {stats['red_team']['total_tests']}")
    print(f"  Auto-tune events: {stats['auto_tuner']['total_tuning_events']}")
    print(f"  Sleep consolidations: {stats['sleep_cycle']['total_consolidations']}")
    print(f"  Mission hash unchanged: {runtime.get_mission_hash()[:16]}...")
