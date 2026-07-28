"""
Stream Calibrator — Evidence-Weighted Influence Tracking

No cognitive stream possesses a priori authority. Influence must be
earned through evidence-backed confidence calibrated by experience.

Influence = Evidence . Confidence . HistoricalReliability

The Calibrator tracks each stream's historical accuracy and adjusts
its influence weight dynamically. A stream that consistently reports
high confidence but produces high MissionDrift sees its influence
automatically reduced.

Lambda4.5 (Local vs Global Optima): The Calibrator detects when the
system is stuck on a dominant stream and provides forced exploration
mechanisms to escape local optima.
"""

from __future__ import annotations

import hashlib
import math
import time
import numpy as np
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger('telos_infra')

# Lambda4.5: Thresholds for stuck detection
_STUCK_DOMINANCE_CYCLES = 10
_STUCK_PLATEAU_CYCLES = 5


@dataclass
class StreamCalibration:
    """Calibration state for a single cognitive stream."""
    stream_name: str
    total_calls: int = 0
    accurate_calls: int = 0
    confidence_history: List[float] = field(default_factory=list)
    drift_history: List[float] = field(default_factory=list)
    historical_reliability: float = 0.5
    influence_weight: float = 1.0
    evidence_score: float = 0.0
    last_calibrated: float = 0.0
    waste_cost_ms: float = 0.0       # P2.10: Total budget wasted (low-confidence intents)
    total_cost_ms: float = 0.0       # P2.10: Total budget consumed
    # Lambda4.5: Track consecutive non-selection cycles
    consecutive_not_selected: int = 0
    council_blocks: int = 0

    @property
    def accuracy(self) -> float:
        return self.accurate_calls / max(self.total_calls, 1)


@dataclass
class ExperienceEntry:
    """Experience-calibrated confidence for a stream in a specific context."""
    confidence_mean: float = 0.5
    confidence_std: float = 0.2
    n_observations: int = 0
    last_updated: float = 0.0

    @property
    def uncertainty(self) -> float:
        return self.confidence_std / max(1.0, math.sqrt(self.n_observations))


@dataclass
class ExperienceMap:
    """Per-stream experience map: context → calibrated confidence.
    
    Each stream maintains a map of context fingerprints to its observed
    confidence distribution. A stream that has seen a context 50 times
    speaks with higher certainty than one seeing it for the first time.
    
    Security: bounded by MAX_ENTRIES with LRU eviction, context keys
    are hashed to prevent long-string denial of service.
    """
    stream_name: str
    context_map: OrderedDict = field(default_factory=OrderedDict)
    MAX_ENTRIES: int = 1000
    _eviction_count: int = 0

    @staticmethod
    def _hash_key(context: str) -> str:
        return hashlib.sha256(context.encode()).hexdigest()[:16]

    def update(self, context: str, confidence: float) -> None:
        key = self._hash_key(context)
        if key in self.context_map:
            entry = self.context_map[key]
            self.context_map.move_to_end(key)
        else:
            if len(self.context_map) >= self.MAX_ENTRIES:
                self.context_map.popitem(last=False)
                self._eviction_count += 1
            entry = ExperienceEntry()
            self.context_map[key] = entry
        n = entry.n_observations
        old_mean = entry.confidence_mean
        entry.confidence_mean = (old_mean * n + confidence) / (n + 1)
        entry.confidence_std = math.sqrt(
            ((n * (entry.confidence_std ** 2 + (old_mean - entry.confidence_mean) ** 2)
              + (confidence - entry.confidence_mean) ** 2) / (n + 1))
            if n > 0 else 0.2 ** 2
        )
        entry.n_observations = n + 1
        entry.last_updated = time.time()

    def get_confidence(self, context: str) -> Tuple[float, float]:
        key = self._hash_key(context)
        entry = self.context_map.get(key)
        if entry is None or entry.n_observations == 0:
            return (0.5, 1.0)
        return (entry.confidence_mean, entry.uncertainty)


class StreamCalibrator:
    """Tracks and adjusts stream influence weights based on historical reliability.

    The Calibrator observes each cycle's PipelineResult and updates
    each stream's calibration:
      - If a stream's intent was selected and the cycle had low MD -> accurate
      - If a stream's intent was selected and the cycle had high MD -> inaccurate
      - If a stream was never selected -> no update (insufficient data)

    Influence weight is computed as:
      weight = accuracy * avg_confidence * (1 - avg_drift)

    Lambda4.5: Tracks selection history to detect when the system is stuck
    on a local optimum (one stream always wins) and provides forced
    exploration mechanisms.
    """

    def __init__(self):
        self._calibrations: Dict[str, StreamCalibration] = {}
        self._experience_maps: Dict[str, ExperienceMap] = {}
        self._total_calibrations: int = 0
        # Lambda4.5: Track which stream was selected each cycle
        self._selection_history: List[str] = []
        self._max_selection_history = 50
        # Lambda4.5: Escape event tracking for telemetry
        self._escape_count: int = 0
        self._last_escape_cycle: int = 0
        self._last_escape_from: Optional[str] = None
        self._last_escape_to: Optional[str] = None

    def observe(self, result: Any) -> None:
        """Update stream calibrations from a single decision cycle."""
        trace = result.decision_trace
        if trace is None:
            return

        selected_stream = None
        for sa in trace.stream_activations:
            if not sa.activated or sa.intent is None:
                continue

            cal = self._get_or_create(sa.stream_name)

            was_selected = (trace.selected_intent is not None
                            and sa.intent.intent_type == trace.selected_intent.intent_type
                            and sa.intent.confidence == trace.selected_intent.confidence)

            if was_selected:
                selected_stream = sa.stream_name
                cal.total_calls += 1
                cal.consecutive_not_selected = 0
                cal.confidence_history.append(sa.intent.confidence)

                drift = trace.mission_drift or 0.0
                cal.drift_history.append(drift)

                if drift < 1.0:
                    cal.accurate_calls += 1

                self._recompute(cal)

                # Phase 0: Update ExperienceMap for the selected stream
                context = str(trace.world_state_snapshot.tolist() if hasattr(trace, 'world_state_snapshot') and trace.world_state_snapshot is not None else '')
                self.update_experience_map(sa.stream_name, context, sa.intent.confidence)

                # Track council blocks per stream
                if trace.council_signals:
                    has_block = any(s.get("passed") == False for s in trace.council_signals)
                    if has_block:
                        cal.council_blocks += 1
            else:
                # Lambda3.5 — Structural Inertia: non-selected streams get a small
                # influence boost each cycle so they can eventually compete
                # with high-priority streams. Prevents permanent lock-out:
                # "the stream that never gets chosen never proves itself."
                cal.influence_weight = min(2.0, cal.influence_weight * 1.08)
                cal.consecutive_not_selected += 1

        # Lambda4.5: Record selection history
        if selected_stream:
            self._selection_history.append(selected_stream)
            if len(self._selection_history) > self._max_selection_history:
                self._selection_history.pop(0)

    def _get_or_create(self, stream_name: str) -> StreamCalibration:
        if stream_name not in self._calibrations:
            self._calibrations[stream_name] = StreamCalibration(stream_name=stream_name)
        return self._calibrations[stream_name]

    def _recompute(self, cal: StreamCalibration) -> None:
        """Recompute evidence score, reliability, and influence weight.
        
        Influence = Evidence × Confidence × HistoricalReliability
        
        Evidence: how many observations the stream has (saturates at 50)
        Confidence: mean confidence over last 20 cycles
        Reliability: accuracy × confidence — how trustworthy the stream has been
        """
        avg_conf = np.mean(cal.confidence_history[-20:]) if cal.confidence_history else 0.5
        avg_drift = np.mean(cal.drift_history[-20:]) if cal.drift_history else 0.5
        accuracy = cal.accuracy

        EVIDENCE_SATURATION = 50
        cal.evidence_score = min(1.0, cal.total_calls / EVIDENCE_SATURATION)
        cal.historical_reliability = float(np.clip(accuracy * avg_conf, 0.0, 1.0))
        cal.influence_weight = float(np.clip(
            cal.evidence_score * avg_conf * cal.historical_reliability, 0.0, 2.0
        ))
        cal.last_calibrated = time.time()
        self._total_calibrations += 1

    # ── Lambda4.5: Stuck Detection and Forced Exploration ──────────────

    @property
    def dominant_stream(self) -> Optional[str]:
        """The stream with highest influence weight that has been
        selected for STUCK_DOMINANCE_CYCLES+ consecutive cycles."""
        if len(self._selection_history) < _STUCK_DOMINANCE_CYCLES:
            return None
        recent = self._selection_history[-_STUCK_DOMINANCE_CYCLES:]
        if len(set(recent)) == 1:
            return recent[0]
        return None

    def is_stuck(self) -> bool:
        """Returns True if the dominant stream has been selected for
        10+ consecutive cycles while its confidence has been decreasing
        (plateau or decline)."""
        dom = self.dominant_stream
        if dom is None:
            return False
        cal = self._calibrations.get(dom)
        if cal is None or len(cal.confidence_history) < _STUCK_PLATEAU_CYCLES:
            return False
        # Check if confidence is plateauing or declining
        recent_conf = cal.confidence_history[-_STUCK_PLATEAU_CYCLES:]
        if len(recent_conf) >= 2:
            # Check if confidence is declining or flat
            declining = all(recent_conf[i] >= recent_conf[i+1] for i in range(len(recent_conf)-1))
            flat = max(recent_conf) - min(recent_conf) < 0.05
            if declining or flat:
                return True
        return False

    def forced_exploration_stream(self) -> Optional[str]:
        """Returns the non-dominant stream with the highest potential
        (highest unused influence weight x confidence)."""
        if not self.dominant_stream:
            return None
        dom = self.dominant_stream
        best_stream = None
        best_potential = -1.0
        for name, cal in self._calibrations.items():
            if name == dom:
                continue
            # Compute potential: influence_weight * (1 - consecutive_not_selected / max_history)
            recency_boost = 1.0 - (cal.consecutive_not_selected / self._max_selection_history)
            potential = cal.influence_weight * recency_boost
            if potential > best_potential:
                best_potential = potential
                best_stream = name
        return best_stream

    def record_escape(self, cycle: int, escaped_from: str, escaped_to: str) -> None:
        """Λ4.5: Record a local-optima-escape event for telemetry."""
        self._escape_count += 1
        self._last_escape_cycle = cycle
        self._last_escape_from = escaped_from
        self._last_escape_to = escaped_to
        logger.info(
            "Lambda4.5: Local-optima escape #%d — broke free from '%s' to '%s' "
            "(cycle %d)",
            self._escape_count, escaped_from, escaped_to, cycle
        )

    def get_influence_weight(self, stream_name: str) -> float:
        """Get the evidence-weighted influence for a stream.

        Influence = Evidence . Confidence . HistoricalReliability
        Used by the Pipeline to weight stream intents during selection.
        """
        cal = self._calibrations.get(stream_name)
        return cal.influence_weight if cal else 1.0

    def get_calibration(self, stream_name: str) -> Optional[StreamCalibration]:
        return self._calibrations.get(stream_name)

    def record_waste(self, stream_name: str, cost_ms: float) -> None:
        """P2.10: Record budget waste for a low-confidence intent.

        A stream that consistently produces low-confidence intents (waste ratio > 0.5)
        has its influence weight reduced, creating natural selection pressure.
        """
        cal = self._get_or_create(stream_name)
        cal.total_cost_ms += cost_ms
        cal.waste_cost_ms += cost_ms

        # Compute waste ratio and reduce influence if excessive
        waste_ratio = cal.waste_cost_ms / max(cal.total_cost_ms, 1e-9)
        if waste_ratio > 0.5 and cal.total_cost_ms > 20.0:
            # Graduated penalty: ~0.01 at 51%, ~0.1 at 60%, ~0.2 at 70%, ~0.3 at 80%+
            reduction = max(0.05, min(0.3, (waste_ratio - 0.5) * 1.0))
            old_weight = cal.influence_weight
            cal.influence_weight = max(0.1, cal.influence_weight - reduction)
            logger.info(
                f"StreamCalibrator: {stream_name} waste_ratio={waste_ratio:.2f} — "
                f"reduced influence {old_weight:.2f} -> {cal.influence_weight:.2f}"
            )
            self._total_calibrations += 1
        elif waste_ratio > 0.3:
            logger.debug(
                f"StreamCalibrator: {stream_name} waste_ratio={waste_ratio:.2f} — "
                f"approaching reduction threshold"
            )

    def get_experience_map(self, stream_name: str) -> ExperienceMap:
        if stream_name not in self._experience_maps:
            self._experience_maps[stream_name] = ExperienceMap(stream_name=stream_name)
        return self._experience_maps[stream_name]

    def update_experience_map(self, stream_name: str, context: str, confidence: float) -> None:
        em = self.get_experience_map(stream_name)
        em.update(context, confidence)

    def get_calibrated_confidence(self, stream_name: str, context: str) -> Tuple[float, float]:
        em = self.get_experience_map(stream_name)
        return em.get_confidence(context)

    def get_evidence_weighted_influence(self, stream_name: str) -> Dict[str, float]:
        """Returns the full evidence-weighted influence triplet for a stream.
        
        Returns:
            {evidence, confidence, reliability, influence_weight}
            Defaults to neutral values if stream not yet calibrated.
        """
        cal = self._calibrations.get(stream_name)
        if not cal:
            return {"evidence": 0.0, "confidence": 0.5, "reliability": 0.5, "influence_weight": 1.0}
        avg_conf = np.mean(cal.confidence_history[-20:]) if cal.confidence_history else 0.5
        return {
            "evidence": cal.evidence_score,
            "confidence": float(avg_conf),
            "reliability": cal.historical_reliability,
            "influence_weight": cal.influence_weight,
        }

    def get_stream_uncertainties(self) -> Dict[str, float]:
        result = {}
        for name, em in self._experience_maps.items():
            if em.context_map:
                latest = next(reversed(em.context_map.values()))
                result[name] = latest.uncertainty
            else:
                result[name] = 1.0
        return result

    def apply_council_block_penalty(self) -> None:
        """Reduce influence weight for streams with high council-block rate.
        
        When a stream's intents are consistently Council-blocked, its
        influence should be reduced — the stream is producing low-quality
        intents that don't pass governance.
        """
        for cal in self._calibrations.values():
            if cal.total_calls < 3:
                continue
            block_rate = cal.council_blocks / max(cal.total_calls, 1)
            if block_rate > 0.3:
                reduction = min(0.3, (block_rate - 0.3) * 0.5)
                old = cal.influence_weight
                cal.influence_weight = max(0.1, cal.influence_weight - reduction)
                logger.info(
                    f"StreamCalibrator: {cal.stream_name} council_block_rate={block_rate:.2f} "
                    f"— reduced influence {old:.2f} → {cal.influence_weight:.2f}"
                )

    @property
    def stats(self) -> Dict:
        return {
            "calibrated_streams": len(self._calibrations),
            "total_calibrations": self._total_calibrations,
            "dominant_stream": self.dominant_stream,
            "is_stuck": self.is_stuck(),
            "local_optima_escapes": self._escape_count,
            "last_escape": {
                "cycle": self._last_escape_cycle,
                "from": self._last_escape_from,
                "to": self._last_escape_to,
            } if self._last_escape_from else None,
            "selection_history": self._selection_history[-20:],
            "calibrations": {
                name: {
                    "accuracy": c.accuracy,
                    "reliability": c.historical_reliability,
                    "influence": c.influence_weight,
                    "evidence": c.evidence_score,
                    "observations": c.total_calls,
                    "waste_cost_ms": c.waste_cost_ms,
                    "total_cost_ms": c.total_cost_ms,
                    "waste_ratio": c.waste_cost_ms / max(c.total_cost_ms, 1e-9),
                    "consecutive_not_selected": c.consecutive_not_selected,
                }
                for name, c in self._calibrations.items()
            },
        }
