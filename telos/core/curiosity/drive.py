"""Curiosity Drive — intrinsic motivation to reduce uncertainty and seek novelty.

Instead of "intrinsic desire" (philosophical), this is "intrinsic inquiry" (computational).
The system seeks to maximize learning progress, not just reward.

Architecture:
  Each cycle, learning_rate = |uncertainty_before - uncertainty_after|.
  Learning is intrinsically rewarding: high learning rate → curiosity grows.
  Boredom (low learning for 5+ cycles) → curiosity spikes to seek novelty.
  Natural decay prevents curiosity from permanently saturating.

  When curiosity > 0.6, the system generates a self-originating intent to
  explore unfamiliar regions — proactive inquiry without external stimulus.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import logging

logger = logging.getLogger('telos_curiosity')


@dataclass
class CuriosityState:
    """Mutable state of the curiosity drive at a given cycle."""
    curiosity_level: float = 0.3       # 0–1, baseline curiosity
    project_id: str = "default"        # which project this curiosity serves
    learning_rate: float = 0.0         # how much learned this cycle
    boredom_count: int = 0             # consecutive cycles below boredom threshold
    novelty_seeking: bool = False      # actively seeking novelty?
    self_intent_generated: bool = False
    exploration_cycles: int = 0
    exploitation_cycles: int = 0


class CuriosityDrive:
    """Computational curiosity — drives exploration without external stimulus.

    Key insight: learning is intrinsically rewarding.
    The system seeks situations where it can learn the most, not just where
    external rewards are highest.

    Integrates with:
      - PhaseContext.curiosity_state (read by select / mission_policy)
      - DecisionTrace.curiosity_state (persisted in audit trail)
      - Pipeline._curiosity_drive (called every cycle after act phase)
    """

    def __init__(self, base_curiosity: float = 0.3,
                 learning_rate_weight: float = 0.5):
        self.state = CuriosityState(curiosity_level=base_curiosity)
        self._uncertainty_history: List[float] = []
        self._learning_history: List[float] = []
        self._compression_history: List[float] = []
        self._max_history = 20
        self.learning_rate_weight = learning_rate_weight

        # ── Tunable thresholds ──────────────────────────────────────────
        self.learning_rate_threshold: float = 0.1    # above this → "learning happened"
        self.boredom_threshold: float = 0.02         # below this → "boring"
        self.boredom_cycles_to_spike: int = 5        # consecutive boring cycles → spike
        self.curiosity_decay: float = 0.05           # natural fade per cycle
        self.curiosity_gain_on_learn: float = 0.1    # reward for learning
        self.curiosity_gain_on_boredom: float = 0.2  # spike when bored
        self.self_intent_threshold: float = 0.6      # generate self-intent above this
        self.min_curiosity: float = 0.1              # floor to prevent permanent apathy
        # Insight 5: Compression-seeking curiosity
        self.compression_reward: float = 0.15        # extra reward for compression
        self.compression_threshold: float = 0.2      # minimum compression to reward

    # ── Public API ──────────────────────────────────────────────────────

    def update(self, uncertainty_before: float, uncertainty_after: float,
               was_blocked: bool, council_disagreement: float) -> Dict:
        """Update curiosity state based on learning progress this cycle.

        Args:
            uncertainty_before: Total uncertainty before this cycle
                (from previous cycle's tripartite U composite).
            uncertainty_after: Total uncertainty after this cycle
                (current cycle's tripartite U composite).
            was_blocked: Whether the Council or governance blocked the action.
            council_disagreement: Disagreement fraction among council validators [0-1].

        Returns:
            Dict report of the new curiosity state (see get_report()).
        """
        # 1. Measure learning rate — how much did uncertainty change?
        self.state.learning_rate = abs(uncertainty_before - uncertainty_after)
        self._learning_history.append(self.state.learning_rate)
        if len(self._learning_history) > self._max_history:
            self._learning_history = self._learning_history[-self._max_history:]

        # 2. Learning is intrinsically rewarding
        if self.state.learning_rate > self.learning_rate_threshold:
            self.state.curiosity_level = min(
                1.0, self.state.curiosity_level + self.curiosity_gain_on_learn
            )
            self.state.boredom_count = 0
            self.state.novelty_seeking = False
            logger.debug(
                f"Curiosity +{self.curiosity_gain_on_learn} "
                f"(learned Δ={self.state.learning_rate:.4f}) "
                f"→ {self.state.curiosity_level:.3f}"
            )
        else:
            self.state.boredom_count += 1

        # 3. Boredom detection — too predictable → spike curiosity
        if (self.state.boredom_count >= self.boredom_cycles_to_spike
                and self.state.learning_rate < self.boredom_threshold):
            self.state.curiosity_level = min(
                1.0, self.state.curiosity_level + self.curiosity_gain_on_boredom
            )
            self.state.novelty_seeking = True
            logger.debug(
                f"Curiosity BOREDOM SPIKE +{self.curiosity_gain_on_boredom} "
                f"(bored {self.state.boredom_count} cycles) "
                f"→ {self.state.curiosity_level:.3f}"
            )
        elif self.state.boredom_count >= self.boredom_cycles_to_spike * 2:
            self.state.novelty_seeking = True  # strongly bored

        # 4. Natural decay — curiosity fades without reinforcement
        self.state.curiosity_level = max(
            self.min_curiosity,
            self.state.curiosity_level - self.curiosity_decay
        )

        # 5. Council disagreement also drives curiosity
        if council_disagreement > 0.5:
            self.state.curiosity_level = min(
                1.0, self.state.curiosity_level + 0.15
            )
            logger.debug(
                f"Curiosity +0.15 (council Δ={council_disagreement:.2f}) "
                f"→ {self.state.curiosity_level:.3f}"
            )

        # 6. Compression-seeking: reward compression rate changes
        compression_input = getattr(self, '_current_compression', 0.0)
        if compression_input > 0:
            self._compression_history.append(compression_input)
            if len(self._compression_history) > self._max_history:
                self._compression_history = self._compression_history[-self._max_history:]
            if len(self._compression_history) >= 2:
                compression_delta = self._compression_history[-1] - self._compression_history[-2]
                if compression_delta > self.compression_threshold:
                    self.state.curiosity_level = min(
                        1.0, self.state.curiosity_level + self.compression_reward
                    )
                    self.state.boredom_count = 0
                    logger.debug(
                        f"Curiosity COMPRESSION +{self.compression_reward} "
                        f"(Δ={compression_delta:.3f}) → {self.state.curiosity_level:.3f}"
                    )

        # 7. Track exploration vs exploitation balance
        if self.state.curiosity_level > self.self_intent_threshold:
            self.state.exploration_cycles += 1
            self.state.self_intent_generated = True
        else:
            self.state.exploitation_cycles += 1
            self.state.self_intent_generated = False

        # 7. Trigger assumption auditing when boredom or high curiosity
        aa = getattr(self, '_assumption_auditor', None)
        if aa is not None and (self.state.novelty_seeking or self.state.curiosity_level > 0.7):
            try:
                aa.auto_audit(cycle=0, curiosity_level=self.state.curiosity_level)
            except Exception:
                pass

        return self.get_report()

    def set_compression(self, compression_rate: float) -> None:
        """Inject current compression rate for compression-seeking curiosity.
            Args:
                compression_rate: the compression_rate argument for this call.
        """
        self._current_compression = compression_rate

    def set_assumption_auditor(self, auditor) -> None:
        """Inject AssumptionAuditor for curiosity-triggered audits."""
        self._assumption_auditor = auditor

    def should_generate_self_intent(self) -> bool:
        """Should the system generate its own intent without external stimulus?

        Returns True when curiosity is high enough that the system should
        proactively explore rather than waiting for the user or environment.
        """
        return (self.state.curiosity_level > self.self_intent_threshold
                or self.state.novelty_seeking)

    def get_curiosity_bonus(self) -> float:
        """Modifier for exploration budget based on curiosity.

        At high curiosity the exploration budget is amplified so the
        system can afford to simulate more counterfactual worlds.
        Base = 1.0, max = 1.0 + 1.0 * 0.5 = 1.5x at full curiosity.
        """
        return 1.0 + self.state.curiosity_level * 0.5

    def get_report(self) -> Dict:
        """Return a snapshot of current curiosity state for audit / trace."""
        total = self.state.exploration_cycles + self.state.exploitation_cycles
        return {
            "curiosity_level": round(self.state.curiosity_level, 3),
            "learning_rate": round(self.state.learning_rate, 4),
            "boredom_count": self.state.boredom_count,
            "novelty_seeking": self.state.novelty_seeking,
            "self_intent_active": self.state.self_intent_generated,
            "exploration_cycles": self.state.exploration_cycles,
            "exploitation_cycles": self.state.exploitation_cycles,
            "balance": (
                f"{self.state.exploration_cycles / max(total, 1):.0%} explore"
            ),
        }
