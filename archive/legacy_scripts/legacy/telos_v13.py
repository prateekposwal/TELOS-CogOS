"""
TELOS v13: Self-Maintaining Intelligence Architecture

Shifts from a reactive decision runtime to a self-maintaining
intelligence architecture. Six maintenance operators formalize
systemic health into computational operations:

  1. Historical StateCompression (Forgive Your Past)
  2. Active Resource Rotation (Move Your Body)
  3. Pre-Mission Synchronization (Wake Up Early)
  4. Continuous Runtime Audit (Reflect Your Mindset)
  5. Neti-Neti Nutrition Engine (Cut Off the Noise)
  6. Spider Web Knowledge Graph (Build Meaningful Work)

System Health:
  H = w1*M + w2*K + w3*E + w4*T + w5*A + w6*R

Definitive Axiom:
  Intelligence is not about producing the next token.
  It is about preserving the conditions under which good
  answers continue to emerge over long periods of time.
"""

import time
import hashlib
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum

from telos_v12 import (
    TelosV12Runtime, MissionState, DecisionBasis,
    SystemConservationMonitor, ConservationState,
    ConservationSeverity, MeritFlowMonitor,
    CumulativeOpportunityCostTracker,
)


# ═══════════════════════════════════════════════════════════
# 1. HISTORICAL STATE COMPRESSION
#    "Forgive Your Past"
#    Discards obsolete assumptions while retaining causal lessons
# ═══════════════════════════════════════════════════════════

@dataclass
class CompressionResult:
    """Result of a compression cycle."""
    entries_before: int
    entries_after: int
    entries_compressed: int
    dead_variables_removed: int
    assumptions_pruned: int
    causal_lessons_retained: int
    compression_ratio: float
    elapsed_ms: float


class HistoricalStateCompressor:
    """
    Compresses historical state by:
      1. Merging near-duplicate decision ledger entries
      2. Removing dead variables (unused for > threshold steps)
      3. Pruning stale assumptions (last validated > threshold steps ago)
      4. Retaining causal lessons as compressed semantic macros
    """

    def __init__(self, similarity_threshold: float = 0.9,
                 staleness_threshold: int = 50,
                 max_macros: int = 200):
        self.similarity_threshold = similarity_threshold
        self.staleness_threshold = staleness_threshold
        self.max_macros = max_macros
        self._macros: deque = deque(maxlen=max_macros)
        self._dead_variables: deque = deque(maxlen=500)
        self._pruned_assumptions: deque = deque(maxlen=500)
        self._total_compressions = 0
        self._total_entries_compressed = 0
        self._total_dead_removed = 0
        self._total_lessons_retained = 0

    def _hash_entry(self, entry: Dict[str, Any]) -> str:
        """Create a hash fingerprint for near-duplicate detection."""
        key_parts = [
            str(entry.get('directive', ''))[:80],
            str(entry.get('mission_drift', 0))[:6],
        ]
        return hashlib.md5('|'.join(key_parts).encode()).hexdigest()[:12]

    def _compute_similarity(self, a: Dict[str, Any],
                            b: Dict[str, Any]) -> float:
        """Compute similarity between two step entries."""
        keys = set(a.keys()) | set(b.keys())
        if not keys:
            return 1.0
        matches = sum(1 for k in keys if a.get(k) == b.get(k))
        return matches / len(keys)

    def detect_dead_variables(self, variable_usage: Dict[str, int],
                              current_step: int) -> List[str]:
        """Identify variables not accessed for staleness_threshold steps."""
        dead = []
        for var_name, last_used_step in variable_usage.items():
            if current_step - last_used_step > self.staleness_threshold:
                dead.append(var_name)
                self._dead_variables.append({
                    'variable': var_name,
                    'last_used': last_used_step,
                    'removed_at': current_step,
                })
        return dead

    def detect_stale_assumptions(self, assumptions: List[Dict[str, Any]],
                                 current_step: int) -> List[str]:
        """Identify assumptions not validated recently."""
        stale = []
        for assumption in assumptions:
            last_validated = assumption.get('last_validated', 0)
            if current_step - last_validated > self.staleness_threshold:
                stale.append(assumption.get('assumption_id', 'unknown'))
                self._pruned_assumptions.append({
                    'assumption_id': assumption.get('assumption_id'),
                    'last_validated': last_validated,
                    'pruned_at': current_step,
                })
        return stale

    def compress_ledger(self, entries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], CompressionResult]:
        """
        Compress a list of step entries by merging near-duplicates
        and extracting causal lessons.
        """
        start_time = time.time()

        if not entries:
            return [], CompressionResult(
                entries_before=0, entries_after=0, entries_compressed=0,
                dead_variables_removed=0, assumptions_pruned=0,
                causal_lessons_retained=0, compression_ratio=1.0,
                elapsed_ms=0.0,
            )

        # Identify near-duplicate groups
        seen_hashes: Dict[str, List[int]] = defaultdict(list)
        for i, entry in enumerate(entries):
            h = self._hash_entry(entry)
            seen_hashes[h].append(i)

        # Merge duplicates
        compressed = []
        compressed_indices: Set[int] = set()
        lessons_retained = 0

        for h, indices in seen_hashes.items():
            if len(indices) > 1:
                # Merge the group into one representative entry
                representative = entries[indices[0]].copy()
                representative['compression_group_size'] = len(indices)
                representative['compressed_from'] = indices
                compressed.append(representative)
                compressed_indices.update(indices)
                lessons_retained += 1
            else:
                if indices[0] not in compressed_indices:
                    compressed.append(entries[indices[0]])
                    compressed_indices.add(indices[0])

        # Sort by step number
        compressed.sort(key=lambda e: e.get('step', 0))

        elapsed_ms = (time.time() - start_time) * 1000
        result = CompressionResult(
            entries_before=len(entries),
            entries_after=len(compressed),
            entries_compressed=len(entries) - len(compressed),
            dead_variables_removed=0,
            assumptions_pruned=0,
            causal_lessons_retained=lessons_retained,
            compression_ratio=len(compressed) / max(len(entries), 1),
            elapsed_ms=elapsed_ms,
        )

        self._total_compressions += 1
        self._total_entries_compressed += result.entries_compressed
        self._total_lessons_retained += lessons_retained

        return compressed, result

    def create_macro(self, compressed_entries: List[Dict[str, Any]],
                     macro_id: str) -> Optional[Dict[str, Any]]:
        """Create a SemanticMacroNode from compressed entries."""
        if not compressed_entries:
            return None

        directives = [e.get('directive', '') for e in compressed_entries
                      if e.get('directive')]
        avg_health = np.mean([
            e.get('conservation', {}).get('overall_health', 0.5)
            for e in compressed_entries
        ])

        macro = {
            'macro_id': macro_id,
            'source_entries': len(compressed_entries),
            'merged_directive': directives[-1] if directives else '',
            'avg_health_at_compression': round(float(avg_health), 4),
            'causal_lessons': directives[:3],
            'created_at': time.time(),
            'hash': hashlib.md5(
                macro_id.encode() + str(len(compressed_entries)).encode()
            ).hexdigest()[:16],
        }
        self._macros.append(macro)
        return macro

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_compressions': self._total_compressions,
            'total_entries_compressed': self._total_entries_compressed,
            'total_dead_removed': self._total_dead_removed,
            'total_lessons_retained': self._total_lessons_retained,
            'active_macros': len(self._macros),
            'dead_variables_tracked': len(self._dead_variables),
            'pruned_assumptions_tracked': len(self._pruned_assumptions),
        }


# ═══════════════════════════════════════════════════════════
# 2. ACTIVE RESOURCE ROTATION
#    "Move Your Body"
#    Dynamic activation/deactivation to prevent congestion
# ═══════════════════════════════════════════════════════════

class ModuleStatus(Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DORMANT = "dormant"
    OVERHEATED = "overheated"


@dataclass
class ResourceModule:
    """A computable module that can be activated/deactivated."""
    module_id: str
    name: str
    status: ModuleStatus = ModuleStatus.ACTIVE
    utilization: float = 0.0
    memory_mb: float = 0.0
    activation_count: int = 0
    last_activated: float = field(default_factory=time.time)
    cooldown_until: float = 0.0
    priority: float = 0.5


@dataclass
class RotationEvent:
    """Record of a resource rotation."""
    module_id: str
    from_status: ModuleStatus
    to_status: ModuleStatus
    reason: str
    step: int


class ActiveResourceRotation:
    """
    Manages dynamic module activation/deactivation to prevent:
      - Thermal congestion (too many active modules)
      - Memory bloat (accumulated state)
      - Attention fragmentation (too many concurrent focuses)
    """

    def __init__(self, max_active: int = 5,
                 utilization_threshold: float = 0.85,
                 cooldown_steps: int = 3):
        self.max_active = max_active
        self.utilization_threshold = utilization_threshold
        self.cooldown_steps = cooldown_steps
        self._modules: Dict[str, ResourceModule] = {}
        self._rotation_history: deque = deque(maxlen=500)
        self._total_rotations = 0
        self._total_congestion_events = 0

    def register_module(self, module_id: str, name: str,
                        priority: float = 0.5,
                        memory_mb: float = 0.0) -> ResourceModule:
        """Register a new resource module."""
        module = ResourceModule(
            module_id=module_id, name=name,
            priority=priority, memory_mb=memory_mb,
        )
        self._modules[module_id] = module
        return module

    def update_utilization(self, module_id: str,
                           utilization: float) -> None:
        """Update a module's current utilization."""
        if module_id in self._modules:
            self._modules[module_id].utilization = utilization
            if utilization > self.utilization_threshold:
                self._overheat_module(module_id)

    def _overheat_module(self, module_id: str) -> None:
        """Transition a module to overheat state."""
        module = self._modules[module_id]
        if module.status == ModuleStatus.ACTIVE:
            event = RotationEvent(
                module_id=module_id,
                from_status=module.status,
                to_status=ModuleStatus.OVERHEATED,
                reason=f"utilization {module.utilization:.2f} > {self.utilization_threshold}",
                step=0,
            )
            module.status = ModuleStatus.OVERHEATED
            module.cooldown_until = time.time() + (self.cooldown_steps * 0.1)
            self._rotation_history.append(event)
            self._total_rotations += 1
            self._total_congestion_events += 1

    def rotate(self, current_step: int) -> List[RotationEvent]:
        """
        Perform a rotation pass:
          1. Move overheated modules to cooldown
          2. Reactivate cooled-down modules
          3. Deactivate low-priority modules if over capacity
        """
        events = []
        now = time.time()

        # Check overheated → cooldown
        for mod in self._modules.values():
            if mod.status == ModuleStatus.OVERHEATED:
                if now >= mod.cooldown_until:
                    event = RotationEvent(
                        module_id=mod.module_id,
                        from_status=mod.status,
                        to_status=ModuleStatus.COOLDOWN,
                        reason="cooldown elapsed",
                        step=current_step,
                    )
                    mod.status = ModuleStatus.COOLDOWN
                    self._rotation_history.append(event)
                    self._total_rotations += 1
                    events.append(event)

        # Reactivate cooled modules
        for mod in self._modules.values():
            if mod.status == ModuleStatus.COOLDOWN:
                mod.status = ModuleStatus.ACTIVE
                event = RotationEvent(
                    module_id=mod.module_id,
                    from_status=ModuleStatus.COOLDOWN,
                    to_status=ModuleStatus.ACTIVE,
                    reason="reactivated after cooldown",
                    step=current_step,
                )
                self._rotation_history.append(event)
                self._total_rotations += 1
                events.append(event)

        # Enforce max_active: deactivate lowest-priority if over
        active = [m for m in self._modules.values()
                  if m.status == ModuleStatus.ACTIVE]
        if len(active) > self.max_active:
            active.sort(key=lambda m: m.priority)
            excess = active[:len(active) - self.max_active]
            for mod in excess:
                event = RotationEvent(
                    module_id=mod.module_id,
                    from_status=mod.status,
                    to_status=ModuleStatus.DORMANT,
                    reason="capacity exceeded, low priority",
                    step=current_step,
                )
                mod.status = ModuleStatus.DORMANT
                self._rotation_history.append(event)
                self._total_rotations += 1
                events.append(event)

        return events

    def get_active_count(self) -> int:
        return sum(1 for m in self._modules.values()
                   if m.status == ModuleStatus.ACTIVE)

    def get_statistics(self) -> Dict[str, Any]:
        status_counts = {}
        for mod in self._modules.values():
            s = mod.status.value
            status_counts[s] = status_counts.get(s, 0) + 1
        return {
            'total_modules': len(self._modules),
            'active': status_counts.get('active', 0),
            'cooldown': status_counts.get('cooldown', 0),
            'dormant': status_counts.get('dormant', 0),
            'overheated': status_counts.get('overheated', 0),
            'total_rotations': self._total_rotations,
            'total_congestion_events': self._total_congestion_events,
        }


# ═══════════════════════════════════════════════════════════
# 3. PRE-MISSION SYNCHRONIZATION
#    "Wake Up Early"
#    Boot sequence: cleanup → verify → identity → scan
# ═══════════════════════════════════════════════════════════

class SyncPhase(Enum):
    MEMORY_CLEANUP = "memory_cleanup"
    CONTEXT_VERIFICATION = "context_verification"
    IDENTITY_CHECK = "identity_check"
    CORRUPTION_SCAN = "corruption_scan"
    COMPLETE = "complete"


@dataclass
class SyncResult:
    """Result of a pre-mission synchronization."""
    phases_completed: List[str]
    memory_freed_mb: float
    context_valid: bool
    identity_verified: bool
    corruption_detected: bool
    overall_ready: bool
    elapsed_ms: float


class PreMissionSync:
    """
    Boot sequence that runs before each computation:
      Phase 1: Memory Cleanup   — purge dead variables, compress state
      Phase 2: Context Verify   — check context window integrity
      Phase 3: Identity Check   — verify mission hash unchanged
      Phase 4: Corruption Scan  — scan for anomalies in recent state
    """

    def __init__(self, compressor: Optional[HistoricalStateCompressor] = None):
        self.compressor = compressor or HistoricalStateCompressor()
        self._sync_history: deque = deque(maxlen=200)
        self._total_syncs = 0
        self._total_corruption_detections = 0

    def _phase_memory_cleanup(self, variable_usage: Dict[str, int],
                              current_step: int) -> Tuple[float, int]:
        """Phase 1: Remove dead variables and compress."""
        dead = self.compressor.detect_dead_variables(
            variable_usage, current_step
        )
        # Simulate memory freed: each dead var ~ 0.5 MB
        memory_freed = len(dead) * 0.5
        return memory_freed, len(dead)

    def _phase_context_verification(self,
                                    context_window: Optional[List[Any]]) -> bool:
        """Phase 2: Verify context window is not corrupted."""
        if context_window is None:
            return True
        if len(context_window) == 0:
            return True
        # Check for None entries
        for entry in context_window:
            if entry is None:
                return False
        return True

    def _phase_identity_check(self,
                              mission_hash: str,
                              current_hash: str) -> bool:
        """Phase 3: Verify mission identity is unchanged."""
        return mission_hash == current_hash

    def _phase_corruption_scan(self,
                               recent_state: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """Phase 4: Scan for anomalies."""
        anomalies = []
        for entry in recent_state:
            health = entry.get('conservation', {}).get('overall_health', 1.0)
            if health < 0.2:
                anomalies.append(
                    f"Critical health at step {entry.get('step', '?')}: {health:.3f}"
                )
            mf = entry.get('merit_flow', {}).get('current_mf', 1.0)
            if isinstance(mf, (int, float)) and mf < 0.1:
                anomalies.append(
                    f"Near-zero merit flow at step {entry.get('step', '?')}"
                )
        return len(anomalies) > 0, anomalies

    def synchronize(self, current_step: int,
                    variable_usage: Dict[str, int],
                    mission_hash: str,
                    current_mission_hash: str,
                    context_window: Optional[List[Any]] = None,
                    recent_state: Optional[List[Dict[str, Any]]] = None) -> SyncResult:
        """Execute the full pre-mission synchronization."""
        start_time = time.time()
        phases_completed = []

        # Phase 1
        memory_freed, _ = self._phase_memory_cleanup(
            variable_usage, current_step
        )
        phases_completed.append(SyncPhase.MEMORY_CLEANUP.value)

        # Phase 2
        context_valid = self._phase_context_verification(context_window)
        phases_completed.append(SyncPhase.CONTEXT_VERIFICATION.value)

        # Phase 3
        identity_verified = self._phase_identity_check(
            mission_hash, current_mission_hash
        )
        phases_completed.append(SyncPhase.IDENTITY_CHECK.value)

        # Phase 4
        corruption_detected, _ = self._phase_corruption_scan(
            recent_state or []
        )
        phases_completed.append(SyncPhase.CORRUPTION_SCAN.value)
        phases_completed.append(SyncPhase.COMPLETE.value)

        if corruption_detected:
            self._total_corruption_detections += 1

        elapsed_ms = (time.time() - start_time) * 1000

        result = SyncResult(
            phases_completed=phases_completed,
            memory_freed_mb=memory_freed,
            context_valid=context_valid,
            identity_verified=identity_verified,
            corruption_detected=corruption_detected,
            overall_ready=context_valid and identity_verified and not corruption_detected,
            elapsed_ms=elapsed_ms,
        )

        self._sync_history.append(result)
        self._total_syncs += 1
        return result

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._sync_history)[-50:]
        readiness_rate = (
            sum(1 for r in recent if r.overall_ready) / max(len(recent), 1)
        )
        return {
            'total_syncs': self._total_syncs,
            'total_corruption_detections': self._total_corruption_detections,
            'readiness_rate': round(readiness_rate, 4),
        }


# ═══════════════════════════════════════════════════════════
# 4. CONTINUOUS RUNTIME AUDIT
#    "Reflect Your Mindset"
#    Automated diagnostics for system health
# ═══════════════════════════════════════════════════════════

class AuditSeverity(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class DiagnosticReport:
    """Result of a runtime health audit."""
    timestamp: float
    mission_drift: float
    identity_entropy: float
    error_rate: float
    attention_spread: float
    overall_severity: AuditSeverity
    recommendations: List[str]
    dimension_scores: Dict[str, float]


class ContinuousRuntimeAudit:
    """
    Evaluates:
      - Mission drift (how far current state is from G₀)
      - Identity entropy (diversity of recent decisions vs mission)
      - Error rate (frequency of corrections/recoveries)
      - Attention spread (how many concurrent focuses)
    """

    def __init__(self, drift_threshold: float = 0.5,
                 entropy_threshold: float = 0.7,
                 error_threshold: float = 0.3,
                 spread_threshold: float = 0.6):
        self.drift_threshold = drift_threshold
        self.entropy_threshold = entropy_threshold
        self.error_threshold = error_threshold
        self.spread_threshold = spread_threshold
        self._audit_history: deque = deque(maxlen=500)
        self._total_audits = 0

    def _compute_identity_entropy(self,
                                   recent_decisions: List[str],
                                   mission_direction: np.ndarray) -> float:
        """
        Compute entropy of recent decision directions relative
        to mission. High entropy = decisions scattered away from mission.
        """
        if not recent_decisions:
            return 0.0
        # Simplified: use length variance as proxy for entropy
        lengths = [len(d) for d in recent_decisions if d]
        if not lengths:
            return 0.0
        mean_len = np.mean(lengths)
        std_len = np.std(lengths)
        normalized = min(1.0, std_len / max(mean_len, 1.0))
        return float(normalized)

    def _compute_error_rate(self, total_steps: int,
                            corrections: int) -> float:
        """Fraction of steps requiring correction."""
        if total_steps == 0:
            return 0.0
        return min(1.0, corrections / total_steps)

    def _compute_attention_spread(self,
                                   active_focuses: int,
                                   max_focuses: int = 10) -> float:
        """Normalized measure of attention fragmentation."""
        if max_focuses == 0:
            return 0.0
        return min(1.0, active_focuses / max_focuses)

    def audit(self, current_step: int,
              mission_vector: np.ndarray,
              current_state: np.ndarray,
              recent_decisions: List[str],
              total_steps: int,
              corrections: int,
              active_focuses: int,
              conservation_state: Optional[ConservationState] = None) -> DiagnosticReport:
        """Run full diagnostic audit."""
        # Mission drift
        mn = np.linalg.norm(mission_vector)
        if mn > 1e-9:
            mission_drift = float(np.linalg.norm(current_state - mission_vector) / mn)
        else:
            mission_drift = 0.0
        mission_drift = min(2.0, mission_drift)

        # Identity entropy
        identity_entropy = self._compute_identity_entropy(
            recent_decisions, mission_vector
        )

        # Error rate
        error_rate = self._compute_error_rate(total_steps, corrections)

        # Attention spread
        attention_spread = self._compute_attention_spread(active_focuses)

        # Dimension scores
        dimension_scores = {
            'mission_drift': round(1.0 - min(1.0, mission_drift), 4),
            'identity_focus': round(1.0 - identity_entropy, 4),
            'error_free': round(1.0 - error_rate, 4),
            'attention_focus': round(1.0 - attention_spread, 4),
        }

        if conservation_state:
            dimension_scores['conservation_health'] = round(
                conservation_state.overall_health, 4
            )

        # Severity classification
        avg_score = np.mean(list(dimension_scores.values()))
        if avg_score >= 0.7:
            severity = AuditSeverity.HEALTHY
        elif avg_score >= 0.5:
            severity = AuditSeverity.WARNING
        elif avg_score >= 0.3:
            severity = AuditSeverity.CRITICAL
        else:
            severity = AuditSeverity.EMERGENCY

        # Recommendations
        recommendations = []
        if mission_drift > self.drift_threshold:
            recommendations.append(
                f"Mission drift {mission_drift:.2f} exceeds threshold "
                f"{self.drift_threshold} — re-anchor to G₀"
            )
        if identity_entropy > self.entropy_threshold:
            recommendations.append(
                "High identity entropy — decisions diverging from mission character"
            )
        if error_rate > self.error_threshold:
            recommendations.append(
                f"Error rate {error_rate:.2%} exceeds threshold — "
                "consider reducing complexity"
            )
        if attention_spread > self.spread_threshold:
            recommendations.append(
                f"Attention spread {attention_spread:.2f} — "
                "consolidate focus to fewer concurrent tasks"
            )

        report = DiagnosticReport(
            timestamp=time.time(),
            mission_drift=round(mission_drift, 6),
            identity_entropy=round(identity_entropy, 6),
            error_rate=round(error_rate, 6),
            attention_spread=round(attention_spread, 6),
            overall_severity=severity,
            recommendations=recommendations,
            dimension_scores=dimension_scores,
        )

        self._audit_history.append(report)
        self._total_audits += 1
        return report

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._audit_history)[-50:]
        if not recent:
            return {'total_audits': 0, 'avg_health': 1.0}
        severity_counts = {}
        for r in recent:
            s = r.overall_severity.value
            severity_counts[s] = severity_counts.get(s, 0) + 1
        avg_drift = np.mean([r.mission_drift for r in recent])
        return {
            'total_audits': self._total_audits,
            'severity_distribution': severity_counts,
            'avg_mission_drift': round(float(avg_drift), 4),
        }


# ═══════════════════════════════════════════════════════════
# 5. NETI-NETI NUTRITION ENGINE
#    "Cut Off the Noise"
#    Information nutrition scoring: Mission × Evidence × Trust × Novelty
# ═══════════════════════════════════════════════════════════

@dataclass
class NutritionScore:
    """Multi-factor nutrition score for an information chunk."""
    mission_score: float
    evidence_score: float
    trust_score: float
    novelty_score: float
    composite: float
    is_sub_threshold: bool


class NutritionEngine:
    """
    Enhanced information filtering with four-factor nutrition scoring:
      - Mission alignment (cosine similarity to mission vector)
      - Evidence support (has empirical backing)
      - Trust level (source credibility)
      - Novelty (new information vs known knowledge)

    Sub-threshold inputs are pruned immediately.
    """

    def __init__(self, mission_vector: np.ndarray,
                 novelty_threshold: float = 0.1,
                 composite_threshold: float = 0.3,
                 weights: Optional[Dict[str, float]] = None):
        mn = np.linalg.norm(mission_vector)
        self.mission_vector = mission_vector / mn if mn > 1e-9 else mission_vector
        self.novelty_threshold = novelty_threshold
        self.composite_threshold = composite_threshold
        self.weights = weights or {
            'mission': 0.4,
            'evidence': 0.25,
            'trust': 0.2,
            'novelty': 0.15,
        }
        self._seen_hashes: Set[str] = set()
        self._score_history: deque = deque(maxlen=1000)
        self._total_scored = 0
        self._total_pruned = 0

    def _hash_content(self, content: np.ndarray) -> str:
        return hashlib.md5(content.tobytes()).hexdigest()[:12]

    def score(self, content: np.ndarray,
              has_evidence: bool = False,
              trust_level: float = 0.5) -> NutritionScore:
        """Compute four-factor nutrition score."""
        # Mission alignment
        cn = np.linalg.norm(content)
        if cn > 1e-9 and np.linalg.norm(self.mission_vector) > 1e-9:
            mission_score = float(np.dot(
                content / cn, self.mission_vector
            ))
            mission_score = max(0.0, min(1.0, mission_score))
        else:
            mission_score = 0.0

        # Evidence support
        evidence_score = 1.0 if has_evidence else 0.3

        # Trust level
        trust_score = max(0.0, min(1.0, trust_level))

        # Novelty
        content_hash = self._hash_content(content)
        is_novel = content_hash not in self._seen_hashes
        novelty_score = 1.0 if is_novel else 0.1
        self._seen_hashes.add(content_hash)

        # Composite
        composite = (
            self.weights['mission'] * mission_score +
            self.weights['evidence'] * evidence_score +
            self.weights['trust'] * trust_score +
            self.weights['novelty'] * novelty_score
        )

        is_sub = composite < self.composite_threshold

        result = NutritionScore(
            mission_score=round(mission_score, 4),
            evidence_score=round(evidence_score, 4),
            trust_score=round(trust_score, 4),
            novelty_score=round(novelty_score, 4),
            composite=round(composite, 4),
            is_sub_threshold=is_sub,
        )

        self._score_history.append(result)
        self._total_scored += 1
        if is_sub:
            self._total_pruned += 1

        return result

    def filter_batch(self, items: List[Tuple[np.ndarray, bool, float]]
                     ) -> List[Tuple[NutritionScore, np.ndarray]]:
        """Score and filter a batch of items."""
        results = []
        for content, has_evidence, trust in items:
            score = self.score(content, has_evidence, trust)
            results.append((score, content))
        return [(s, c) for s, c in results if not s.is_sub_threshold]

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._score_history)[-200:]
        if not recent:
            return {'total_scored': 0, 'prune_rate': 0.0}
        avg_composite = np.mean([s.composite for s in recent])
        return {
            'total_scored': self._total_scored,
            'total_pruned': self._total_pruned,
            'prune_rate': round(self._total_pruned / max(self._total_scored, 1), 4),
            'avg_composite_score': round(float(avg_composite), 4),
        }


# ═══════════════════════════════════════════════════════════
# 6. SPIDER WEB KNOWLEDGE GRAPH
#    "Build Meaningful Work"
#    Task → Knowledge → Capability → Future Tasks
# ═══════════════════════════════════════════════════════════

class NodeType(Enum):
    TASK = "task"
    KNOWLEDGE = "knowledge"
    CAPABILITY = "capability"


class NodeStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    PRUNED = "pruned"


@dataclass
class SpiderNode:
    """A node in the Spider Web knowledge graph."""
    node_id: str
    node_type: NodeType
    label: str
    embedding: np.ndarray
    status: NodeStatus = NodeStatus.ACTIVE
    confidence: float = 1.0
    connections: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


@dataclass
class SpiderEdge:
    """An edge in the Spider Web knowledge graph."""
    source_id: str
    target_id: str
    weight: float
    edge_type: str  # "derived_from", "enables", "contradicts"
    created_at: float = field(default_factory=time.time)


class SpiderWebGraph:
    """
    Compounding capability growth graph:
      Task → Knowledge → Capability → Future Tasks

    Tracks the spider web of accumulated intelligence.
    """

    def __init__(self, max_nodes: int = 5000,
                 decay_rate: float = 0.01):
        self.max_nodes = max_nodes
        self.decay_rate = decay_rate
        self._nodes: Dict[str, SpiderNode] = {}
        self._edges: List[SpiderEdge] = []
        self._total_tasks_completed = 0
        self._total_knowledge_gained = 0
        self._total_capabilities_formed = 0

    def add_node(self, node_id: str, node_type: NodeType,
                 label: str, embedding: np.ndarray,
                 metadata: Optional[Dict[str, Any]] = None) -> SpiderNode:
        """Add a node to the knowledge graph."""
        node = SpiderNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            embedding=embedding.copy(),
            metadata=metadata or {},
        )
        if len(self._nodes) >= self.max_nodes:
            self._prune_lowest_confidence()
        self._nodes[node_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str,
                 weight: float, edge_type: str) -> Optional[SpiderEdge]:
        """Add a directed edge between two nodes."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        edge = SpiderEdge(
            source_id=source_id,
            target_id=target_id,
            weight=weight,
            edge_type=edge_type,
        )
        self._edges.append(edge)
        self._nodes[source_id].connections.append(target_id)
        return edge

    def complete_task(self, task_id: str, knowledge_gained: str,
                      embedding: np.ndarray) -> SpiderNode:
        """Record a completed task and extract knowledge."""
        self._total_tasks_completed += 1
        k_id = f"knowledge-{task_id}"
        k_node = self.add_node(
            k_id, NodeType.KNOWLEDGE,
            knowledge_gained, embedding,
        )
        self._total_knowledge_gained += 1

        # Connect task → knowledge
        self.add_edge(task_id, k_id, 0.9, "produced")

        # Check if enough knowledge forms a capability
        connected_knowledge = [
            e for e in self._edges
            if e.target_id.startswith("knowledge-")
            and e.source_id == task_id
        ]
        if len(connected_knowledge) >= 3:
            cap_id = f"capability-{task_id}"
            self.add_node(
                cap_id, NodeType.CAPABILITY,
                f"Capability from {task_id}",
                embedding,
            )
            self.add_edge(k_id, cap_id, 0.8, "enables")
            self._total_capabilities_formed += 1

        return k_node

    def decay_confidence(self) -> int:
        """Apply time-based confidence decay across all nodes."""
        pruned_count = 0
        for node in list(self._nodes.values()):
            if node.status == NodeStatus.ACTIVE:
                node.confidence *= (1.0 - self.decay_rate)
                if node.confidence < 0.1:
                    node.status = NodeStatus.PRUNED
                    pruned_count += 1
        return pruned_count

    def _prune_lowest_confidence(self) -> None:
        """Remove the lowest-confidence active node from the graph."""
        active = [n for n in self._nodes.values()
                  if n.status == NodeStatus.ACTIVE]
        if active:
            lowest = min(active, key=lambda n: n.confidence)
            del self._nodes[lowest.node_id]

    def get_node(self, node_id: str) -> Optional[SpiderNode]:
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str) -> List[str]:
        """Get IDs of all connected nodes."""
        if node_id not in self._nodes:
            return []
        return self._nodes[node_id].connections.copy()

    def get_subgraph(self, root_id: str,
                     depth: int = 2) -> Dict[str, SpiderNode]:
        """Get nodes reachable within depth hops."""
        visited: Set[str] = set()
        frontier = [root_id]
        for _ in range(depth):
            next_frontier = []
            for nid in frontier:
                if nid in visited or nid not in self._nodes:
                    continue
                visited.add(nid)
                next_frontier.extend(self._nodes[nid].connections)
            frontier = next_frontier
        return {nid: self._nodes[nid] for nid in visited if nid in self._nodes}

    def get_statistics(self) -> Dict[str, Any]:
        type_counts = {}
        for node in self._nodes.values():
            t = node.node_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            'total_nodes': len(self._nodes),
            'total_edges': len(self._edges),
            'node_types': type_counts,
            'total_tasks_completed': self._total_tasks_completed,
            'total_knowledge_gained': self._total_knowledge_gained,
            'total_capabilities_formed': self._total_capabilities_formed,
        }


# ═══════════════════════════════════════════════════════════
# 7. SYSTEM HEALTH MONITOR
#    H = w1*M + w2*K + w3*E + w4*T + w5*A + w6*R
# ═══════════════════════════════════════════════════════════

@dataclass
class HealthState:
    """Six-dimensional system health state."""
    mission_integrity: float = 1.0
    knowledge_quality: float = 1.0
    energy_efficiency: float = 1.0
    trust_merit: float = 1.0
    attention_focus: float = 1.0
    recovery_capacity: float = 1.0

    @property
    def overall_health(self) -> float:
        return float(np.mean([
            self.mission_integrity,
            self.knowledge_quality,
            self.energy_efficiency,
            self.trust_merit,
            self.attention_focus,
            self.recovery_capacity,
        ]))

    def to_vector(self) -> np.ndarray:
        return np.array([
            self.mission_integrity,
            self.knowledge_quality,
            self.energy_efficiency,
            self.trust_merit,
            self.attention_focus,
            self.recovery_capacity,
        ])


class SystemHealthMonitor:
    """
    Tracks system health across six weighted dimensions.
    H = w₁M + w₂K + w₃E + w₄T + w₅A + w₆R
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or {
            'M': 0.20, 'K': 0.18, 'E': 0.15,
            'T': 0.20, 'A': 0.15, 'R': 0.12,
        }
        self._state = HealthState()
        self._history: deque = deque(maxlen=500)
        self._total_updates = 0

    def update_mission_integrity(self, drift: float,
                                  max_drift: float = 1.0) -> float:
        normalized = min(1.0, drift / max(max_drift, 1e-9))
        self._state.mission_integrity = max(0.0, 1.0 - normalized)
        return self._state.mission_integrity

    def update_knowledge_quality(self, compression_ratio: float) -> float:
        """Higher compression = better knowledge quality."""
        self._state.knowledge_quality = max(0.0, min(1.0, compression_ratio))
        return self._state.knowledge_quality

    def update_energy_efficiency(self, base_quality: float,
                                  target: float = 0.7) -> float:
        deviation = abs(base_quality - target)
        self._state.energy_efficiency = max(0.0, 1.0 - deviation)
        return self._state.energy_efficiency

    def update_trust_merit(self, merit_flow: float) -> float:
        if merit_flow == float('inf'):
            self._state.trust_merit = 1.0
        else:
            self._state.trust_merit = min(1.0, max(0.0, merit_flow))
        return self._state.trust_merit

    def update_attention_focus(self, spread: float) -> float:
        """Lower spread = better focus."""
        self._state.attention_focus = max(0.0, 1.0 - spread)
        return self._state.attention_focus

    def update_recovery_capacity(self, debt: float,
                                  max_debt: float = 1.0) -> float:
        normalized = min(1.0, debt / max(max_debt, 1e-9))
        self._state.recovery_capacity = max(0.0, 1.0 - normalized)
        return self._state.recovery_capacity

    def compute_weighted_health(self) -> float:
        """Compute H = w₁M + w₂K + w₃E + w₄T + w₅A + w₆R."""
        return float(np.dot(
            self._state.to_vector(),
            np.array([
                self.weights['M'],
                self.weights['K'],
                self.weights['E'],
                self.weights['T'],
                self.weights['A'],
                self.weights['R'],
            ])
        ))

    def snapshot(self) -> HealthState:
        """Take a snapshot and record."""
        state = HealthState(
            mission_integrity=self._state.mission_integrity,
            knowledge_quality=self._state.knowledge_quality,
            energy_efficiency=self._state.energy_efficiency,
            trust_merit=self._state.trust_merit,
            attention_focus=self._state.attention_focus,
            recovery_capacity=self._state.recovery_capacity,
        )
        self._history.append(state)
        self._total_updates += 1
        return state

    def get_trajectory(self, window: int = 50) -> List[float]:
        """Return recent health trajectory."""
        recent = list(self._history)[-window:]
        return [s.overall_health for s in recent]

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._history)[-50:]
        if not recent:
            return {'total_updates': 0, 'avg_health': 1.0}
        avg = np.mean([s.overall_health for s in recent])
        return {
            'total_updates': self._total_updates,
            'current_health': round(self._state.overall_health, 4),
            'avg_health': round(float(avg), 4),
            'weighted_health': round(self.compute_weighted_health(), 4),
        }


# ═══════════════════════════════════════════════════════════
# 8. TELOS v13 RUNTIME
#    Self-Maintaining Intelligence Architecture
# ═══════════════════════════════════════════════════════════

class TelosV13Runtime:
    """
    TELOS v13: Self-Maintaining Intelligence Architecture.

    Chains all six maintenance operators with the v12 pipeline:

      Pre-computation:
        1. Nutrition Engine (Cut Off the Noise)
        2. Pre-Mission Synchronization (Wake Up Early)
        3. Runtime Health Audit (Reflect Your Mindset)
        4. Historical State Compression (Forgive Your Past)

      Core computation:
        5. Spider Web Knowledge Expansion (Build Meaningful Work)
        6. v12 Pipeline (Decision Engine)

      Post-computation:
        7. Active Resource Rotation (Move Your Body)
        8. Recovery & Feedback
    """

    def __init__(self, mission_vector: np.ndarray,
                 goal_vector: np.ndarray,
                 mission_id: str = "v13-mission",
                 min_reward_threshold: float = 0.4,
                 energy: float = 100.0,
                 planning_horizon: int = 10,
                 health_weights: Optional[Dict[str, float]] = None,
                 nutrition_weights: Optional[Dict[str, float]] = None):
        mn = np.linalg.norm(mission_vector)
        self.mission_dir = mission_vector / mn if mn > 1e-9 else mission_vector
        self.mission_state = MissionState(
            mission_vector, mission_id, min_reward_threshold
        )

        # ── v12 Pipeline ──
        self.v12 = TelosV12Runtime(
            mission_vector, goal_vector, mission_id,
            min_reward_threshold, energy, planning_horizon,
        )

        # ── v13 Maintenance Operators ──
        self.compressor = HistoricalStateCompressor()
        self.resource_rotation = ActiveResourceRotation()
        self.pre_mission_sync = PreMissionSync(self.compressor)
        self.runtime_audit = ContinuousRuntimeAudit()
        self.nutrition_engine = NutritionEngine(
            mission_vector, weights=nutrition_weights
        )
        self.knowledge_graph = SpiderWebGraph()
        self.health_monitor = SystemHealthMonitor(health_weights)

        # ── State ──
        self._step_count = 0
        self._execution_log: deque = deque(maxlen=500)
        self._current_state = mission_vector.copy()
        self._variable_usage: Dict[str, int] = {}
        self._recent_decisions: deque = deque(maxlen=100)
        self._corrections: int = 0
        self._knowledge_id_counter = 0

    def _update_variable_usage(self, key: str) -> None:
        self._variable_usage[key] = self._step_count

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
                     foregone_value: float = 0.0,
                     foregone_description: str = "",
                     decision_basis: str = "evidence",
                     evidence_weight: float = 0.8,
                     has_evidence: bool = False,
                     trust_level: float = 0.5,
                     active_focuses: int = 1,
                     friction_metrics: Optional[Dict[str, float]] = None,
                     tes_score: Optional[float] = None,
                     recovery_rate: Optional[float] = None,
                     recovery_debt: float = 0.0,
                     evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute one full TELOS v13 pipeline step with maintenance operators.
        """
        self._step_count += 1
        self._current_state = action_vector.copy()
        step_log: Dict[str, Any] = {'step': self._step_count}

        # ═══ PRE-COMPUTATION MAINTENANCE ═══

        # ── 1. Nutrition Engine: Filter incoming signal ──
        nutrition = self.nutrition_engine.score(
            action_vector, has_evidence, trust_level
        )
        step_log['nutrition'] = {
            'mission_score': nutrition.mission_score,
            'evidence_score': nutrition.evidence_score,
            'trust_score': nutrition.trust_score,
            'novelty_score': nutrition.novelty_score,
            'composite': nutrition.composite,
            'is_sub_threshold': nutrition.is_sub_threshold,
        }

        # If sub-threshold, flag but continue (do not block runtime)
        if nutrition.is_sub_threshold:
            step_log['nutrition_warning'] = (
                "Sub-threshold information detected — "
                "information quality below nutrition cutoff"
            )

        # ── 2. Pre-Mission Synchronization ──
        mission_hash = self.mission_state.immutable_hash()
        sync_result = self.pre_mission_sync.synchronize(
            current_step=self._step_count,
            variable_usage=self._variable_usage,
            mission_hash=mission_hash,
            current_mission_hash=mission_hash,
            recent_state=list(self._execution_log)[-10:],
        )
        step_log['pre_sync'] = {
            'phases': sync_result.phases_completed,
            'memory_freed_mb': round(sync_result.memory_freed_mb, 2),
            'context_valid': sync_result.context_valid,
            'identity_verified': sync_result.identity_verified,
            'corruption_detected': sync_result.corruption_detected,
            'ready': sync_result.overall_ready,
        }

        # ── 3. Runtime Health Audit ──
        v12_stats = self.v12.get_statistics()
        conservation_snap = self.v12.conservation.snapshot()
        audit_report = self.runtime_audit.audit(
            current_step=self._step_count,
            mission_vector=self.mission_state.mission_vector,
            current_state=self._current_state,
            recent_decisions=list(self._recent_decisions),
            total_steps=self._step_count,
            corrections=self._corrections,
            active_focuses=active_focuses,
            conservation_state=conservation_snap,
        )
        step_log['runtime_audit'] = {
            'severity': audit_report.overall_severity.value,
            'mission_drift': audit_report.mission_drift,
            'identity_entropy': audit_report.identity_entropy,
            'error_rate': audit_report.error_rate,
            'attention_spread': audit_report.attention_spread,
            'recommendations': audit_report.recommendations,
        }

        # ── 4. Historical State Compression ──
        if self._step_count > 0 and self._step_count % 10 == 0:
            # Compress every 10 steps
            old_entries = list(self._execution_log)
            compressed, comp_result = self.compressor.compress_ledger(
                old_entries
            )
            step_log['compression'] = {
                'entries_before': comp_result.entries_before,
                'entries_after': comp_result.entries_after,
                'compression_ratio': round(comp_result.compression_ratio, 4),
                'lessons_retained': comp_result.causal_lessons_retained,
            }
        else:
            step_log['compression'] = {'status': 'skipped (not a 10-step boundary)'}

        # ═══ CORE COMPUTATION ═══

        # ── 5. Spider Web Knowledge Expansion ──
        self._knowledge_id_counter += 1
        knowledge_label = claimed_reason or actual_objective or f"step-{self._step_count}"
        k_node = self.knowledge_graph.add_node(
            node_id=f"kn-{self._step_count}",
            node_type=NodeType.KNOWLEDGE,
            label=knowledge_label,
            embedding=action_vector.copy(),
        )

        # Connect to previous knowledge node if exists
        if self._step_count > 1:
            prev_id = f"kn-{self._step_count - 1}"
            prev_node = self.knowledge_graph.get_node(prev_id)
            if prev_node:
                self.knowledge_graph.add_edge(
                    prev_id, f"kn-{self._step_count}",
                    weight=0.7, edge_type="follows"
                )

        kg_stats = self.knowledge_graph.get_statistics()
        step_log['knowledge_graph'] = {
            'total_nodes': kg_stats['total_nodes'],
            'total_edges': kg_stats['total_edges'],
            'new_node': k_node.node_id,
        }

        # ── 6. v12 Pipeline (Decision Engine) ──
        v12_result = self.v12.execute_step(
            action_vector, observed_reward, base_quality,
            claimed_reason, actual_objective,
            belief_constraints, hidden_constraints,
            assumptions, alternative_values, chosen_path_value,
            foregone_value, foregone_description,
            decision_basis, evidence_weight,
            friction_metrics, tes_score, recovery_rate,
            recovery_debt, evidence,
        )
        step_log['v12_pipeline'] = {
            'truth_status': v12_result.get('v11_pipeline', {}).get('truth_status', 'N/A'),
            'conservation_health': v12_result.get('conservation', {}).get('overall_health', 0),
            'merit_flow': v12_result.get('merit_flow', {}).get('current_mf', 0),
            'directive': v12_result.get('directive', ''),
        }

        # ═══ POST-COMPUTATION MAINTENANCE ═══

        # ── 7. Active Resource Rotation ──
        rotation_events = self.resource_rotation.rotate(self._step_count)
        step_log['resource_rotation'] = {
            'events': len(rotation_events),
            'active_modules': self.resource_rotation.get_active_count(),
        }

        # ── 8. System Health Update ──
        mission_drift = v12_result.get('mission_drift', 0)
        mf_value = v12_result.get('merit_flow', {}).get('current_mf', 1.0)
        if mf_value == float('inf'):
            mf_value = 1.0

        self.health_monitor.update_mission_integrity(mission_drift)
        self.health_monitor.update_knowledge_quality(
            step_log.get('compression', {}).get('compression_ratio', 1.0)
        )
        self.health_monitor.update_energy_efficiency(base_quality)
        self.health_monitor.update_trust_merit(mf_value)
        self.health_monitor.update_attention_focus(
            audit_report.attention_spread
        )
        self.health_monitor.update_recovery_capacity(recovery_debt)

        health_state = self.health_monitor.snapshot()
        weighted_health = self.health_monitor.compute_weighted_health()

        step_log['system_health'] = {
            'overall': round(health_state.overall_health, 4),
            'weighted': round(weighted_health, 4),
            'mission_integrity': round(health_state.mission_integrity, 4),
            'knowledge_quality': round(health_state.knowledge_quality, 4),
            'energy_efficiency': round(health_state.energy_efficiency, 4),
            'trust_merit': round(health_state.trust_merit, 4),
            'attention_focus': round(health_state.attention_focus, 4),
            'recovery_capacity': round(health_state.recovery_capacity, 4),
        }

        # ── Track decisions ──
        self._recent_decisions.append(claimed_reason or actual_objective)
        if v12_result.get('conservation', {}).get('alerts', 0) > 0:
            self._corrections += 1

        # ── Composite Directive ──
        directives = []
        if v12_result.get('directive'):
            directives.append(v12_result['directive'])

        if audit_report.overall_severity.value in ('critical', 'emergency'):
            directives.append(
                f"RUNTIME_AUDIT: {audit_report.overall_severity.value.upper()} "
                f"— {len(audit_report.recommendations)} recommendations"
            )

        if nutrition.is_sub_threshold:
            directives.append(
                "NUTRITION: Sub-threshold information quality detected"
            )

        if not sync_result.overall_ready:
            directives.append(
                "PRE_SYNC: System not ready — "
                f"corruption={'detected' if sync_result.corruption_detected else 'none'}"
            )

        if weighted_health < 0.4:
            directives.append(
                f"HEALTH: System health critical ({weighted_health:.2f}) — "
                "immediate maintenance required"
            )

        step_log['directive'] = " | ".join(d for d in directives if d)

        self._execution_log.append(step_log)
        return step_log

    def get_mission_hash(self) -> str:
        return self.mission_state.immutable_hash()

    def get_statistics(self) -> Dict[str, Any]:
        health_stats = self.health_monitor.get_statistics()
        return {
            'version': '13.0-self-maintaining-intelligence',
            'steps': self._step_count,
            'mission_id': self.mission_state.mission_id,
            'mission_hash': self.get_mission_hash(),
            'v12_pipeline': self.v12.get_statistics(),
            'maintenance': {
                'compressor': self.compressor.get_statistics(),
                'resource_rotation': self.resource_rotation.get_statistics(),
                'pre_sync': self.pre_mission_sync.get_statistics(),
                'runtime_audit': self.runtime_audit.get_statistics(),
                'nutrition': self.nutrition_engine.get_statistics(),
                'knowledge_graph': self.knowledge_graph.get_statistics(),
                'health': health_stats,
            },
        }
