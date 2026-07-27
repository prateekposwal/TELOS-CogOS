"""
CognitiveEnergy — Mental Fatigue and Its Effect on Decision Quality.

Prateek's insight: "Cognitive energy — mental fatigue. After many hard
decisions, exploration decreases, confidence calibration shifts. Agents
shouldn't be unrealistically perfect."

Most systems make every decision with the same "freshness." Cognitive Energy
models mental fatigue: after many difficult decisions, the system's decision
quality degrades realistically. This makes the system more human-like and
prevents unrealistically perfect operation at all times.

Energy model:
  - Each decision consumes energy proportional to its difficulty
  - Energy regenerates over time (cycles of low-difficulty)
  - Low energy → reduced exploration, higher noise, confidence distortion
  - Calibration shift: tired system is either overconfident or underconfident

Effects of low cognitive energy:
  1. Exploration decreases (default to exploitation)
  2. Confidence calibration shifts (miscalibration)
  3. Decision noise increases (less precise evaluations)
  4. Preference for default/safe options
  5. Reduced novelty seeking
  6. Slower processing (increased response time)

Architecture:
  - Energy reservoir: current/max energy with recharge rate
  - Fatigue accumulator: tracks recent decision difficulty
  - Energy effects: modulates exploration, confidence, noise
  - Recovery: easy decisions and rest restore energy
"""

from __future__ import annotations

import logging
import math
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field

logger = logging.getLogger('telos_cognitive_energy')


@dataclass
class EnergyState:
    """Current cognitive energy state of the system."""
    current_energy: float       # Current energy level [0, max_energy]
    max_energy: float           # Maximum energy capacity
    recharge_rate: float        # Energy recovered per cycle of rest
    fatigue_level: float        # 0.0 (fresh) to 1.0 (exhausted)
    recent_difficulty: List[float] = field(default_factory=list)

    @property
    def energy_ratio(self) -> float:
        """Current energy as fraction of max."""
        if self.max_energy <= 0:
            return 0.5
        return self.current_energy / self.max_energy

    @property
    def is_fatigued(self) -> bool:
        return self.energy_ratio < 0.3

    @property
    def is_rested(self) -> bool:
        return self.energy_ratio > 0.8


@dataclass
class EnergyEffects:
    """How cognitive energy affects decision making this cycle."""
    exploration_modifier: float    # Multiplier on exploration tendency [0, 1]
    confidence_bias: float         # Bias in confidence estimates [-1, 1]
    decision_noise: float          # Added noise to evaluations [0, 1]
    default_bias: float            # Preference for default options [0, 1]
    novelty_modifier: float        # Multiplier on novelty seeking [0, 1]
    speed_modifier: float          # Processing speed multiplier [0.5, 1.5]


class CognitiveEnergy:
    """Models mental fatigue and its effects on decision making.

    The energy model:
    1. Starts each day/cycle with full energy
    2. Each decision consumes energy based on difficulty
    3. Energy recharges during easy decisions or rest cycles
    4. Low energy produces realistic decision quality degradation
    5. Effects are applied to pipeline behavior

    Difficulty factors:
      - Number of options evaluated (more = harder)
      - Uncertainty level (higher = harder)
      - Conflict/council disagreement (more = harder)
      - Novelty (new situations are harder)
      - Consecutive hard decisions (accumulation)
    """

    def __init__(self, max_energy: float = 100.0,
                 recharge_rate: float = 5.0,
                 base_cost: float = 2.0,
                 difficulty_scale: float = 10.0):
        self._state = EnergyState(
            current_energy=max_energy,
            max_energy=max_energy,
            recharge_rate=recharge_rate,
            fatigue_level=0.0,
        )
        self._base_cost = base_cost
        self._difficulty_scale = difficulty_scale
        self._max_history = 100
        self._effects_history: List[Dict] = []
        self._hard_decision_streak: int = 0
        self._total_decisions: int = 0
        self._rest_cycles: int = 0

    @property
    def energy_ratio(self) -> float:
        return self._state.energy_ratio

    @property
    def is_fatigued(self) -> bool:
        return self._state.is_fatigued

    def compute_difficulty(self, n_options: int, uncertainty: float,
                            council_disagreement: float = 0.0,
                            novelty: float = 0.0) -> float:
        """Compute the difficulty of a decision.

        Args:
            n_options: Number of options being evaluated
            uncertainty: Current uncertainty level [0, 1]
            council_disagreement: Level of council disagreement [0, 1]
            novelty: How novel this situation is [0, 1]

        Returns:
            Difficulty score [0, 1]
        """
        # More options = harder
        option_factor = min(1.0, n_options / 20.0)

        # Blend factors
        difficulty = (
            option_factor * 0.3 +
            uncertainty * 0.3 +
            council_disagreement * 0.2 +
            novelty * 0.2
        )

        # Streak multiplier: consecutive hard decisions accumulate
        if difficulty > 0.5:
            self._hard_decision_streak += 1
        else:
            self._hard_decision_streak = max(0, self._hard_decision_streak - 1)

        streak_mult = 1.0 + min(1.0, self._hard_decision_streak / 10.0) * 0.5

        return min(1.0, difficulty * streak_mult)

    def consume(self, difficulty: float) -> EnergyEffects:
        """Consume energy for a decision and return the effects.

        Args:
            difficulty: How difficult the decision was [0, 1]

        Returns:
            EnergyEffects describing how fatigue affects behavior
        """
        # Energy cost scales with difficulty
        cost = self._base_cost + difficulty * self._difficulty_scale
        self._state.current_energy = max(0.0, self._state.current_energy - cost)

        # Track recent difficulty
        self._state.recent_difficulty.append(difficulty)
        if len(self._state.recent_difficulty) > 20:
            self._state.recent_difficulty.pop(0)

        # Compute fatigue level (exponential moving average of difficulty)
        if self._state.recent_difficulty:
            avg_difficulty = np.mean(self._state.recent_difficulty)
        else:
            avg_difficulty = 0.0

        self._state.fatigue_level = 1.0 - min(1.0, self._state.energy_ratio + 0.2)
        fatigue = self._state.fatigue_level

        # Compute effects based on fatigue
        effects = EnergyEffects(
            exploration_modifier=max(0.1, 1.0 - fatigue * 0.8),
            confidence_bias=-0.3 + fatigue * 0.6,  # Tired → overconfident
            decision_noise=min(0.5, fatigue * 0.4),
            default_bias=min(0.6, fatigue * 0.5),
            novelty_modifier=max(0.1, 1.0 - fatigue * 0.7),
            speed_modifier=max(0.5, 1.0 - fatigue * 0.3),
        )

        self._state.current_energy = max(0.0, self._state.current_energy)
        self._hard_decision_streak = max(0, self._hard_decision_streak)
        self._total_decisions += 1

        # Record
        self._effects_history.append({
            "cycle": self._total_decisions,
            "difficulty": round(difficulty, 3),
            "energy_after": round(self._state.current_energy, 1),
            "fatigue": round(fatigue, 3),
            "exploration_mod": round(effects.exploration_modifier, 3),
        })
        if len(self._effects_history) > self._max_history:
            self._effects_history.pop(0)

        if fatigue > 0.7:
            logger.info(
                f"CognitiveEnergy: high fatigue ({fatigue:.2f}), energy={self._state.current_energy:.0f}/{self._state.max_energy:.0f}, "
                f"exploration ↓ ({effects.exploration_modifier:.2f}), noise ↑ ({effects.decision_noise:.2f})"
            )

        return effects

    def rest(self, cycles: int = 1) -> None:
        """Rest and recover energy.

        Args:
            cycles: Number of rest cycles
        """
        recovery = self._state.recharge_rate * cycles
        self._state.current_energy = min(self._state.max_energy,
                                         self._state.current_energy + recovery)
        self._rest_cycles += cycles
        self._hard_decision_streak = max(0, self._hard_decision_streak - cycles)

        if recovery > 0:
            logger.debug(f"CognitiveEnergy: rested for {cycles} cycles, "
                        f"recovered {recovery:.1f} energy")

    def recharge(self, amount: Optional[float] = None) -> None:
        """Recharge energy by a specific amount (or fully)."""
        if amount is None:
            self._state.current_energy = self._state.max_energy
        else:
            self._state.current_energy = min(self._state.max_energy,
                                             self._state.current_energy + amount)
        self._state.fatigue_level = 1.0 - self._state.energy_ratio

    def apply_effects(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply energy effects to a configuration dict.

        Modifies exploration, confidence, noise parameters based on fatigue.
        Returns the modified config.
        """
        if self._state.energy_ratio > 0.5:
            return config  # Not tired enough to matter

        effects = self._get_current_effects()
        modified = dict(config)

        # Scale down exploration
        if 'exploration_budget' in modified:
            modified['exploration_budget'] *= effects.exploration_modifier
        if 'curiosity_threshold' in modified:
            modified['curiosity_threshold'] = min(1.0,
                modified['curiosity_threshold'] / max(effects.exploration_modifier, 0.1))

        # Add decision noise
        if 'evaluation_noise' in modified:
            modified['evaluation_noise'] += effects.decision_noise

        # Default bias
        if 'default_bias' in modified:
            modified['default_bias'] = min(1.0,
                modified['default_bias'] + effects.default_bias)

        return modified

    def _get_current_effects(self) -> EnergyEffects:
        """Get the current energy effects without consuming energy."""
        fatigue = self._state.fatigue_level
        return EnergyEffects(
            exploration_modifier=max(0.1, 1.0 - fatigue * 0.8),
            confidence_bias=-0.3 + fatigue * 0.6,
            decision_noise=min(0.5, fatigue * 0.4),
            default_bias=min(0.6, fatigue * 0.5),
            novelty_modifier=max(0.1, 1.0 - fatigue * 0.7),
            speed_modifier=max(0.5, 1.0 - fatigue * 0.3),
        )

    @property
    def fatigue_level(self) -> float:
        return self._state.fatigue_level

    @property
    def hard_decision_streak(self) -> int:
        return self._hard_decision_streak

    def to_dict(self) -> Dict:
        effects = self._get_current_effects()
        return {
            "current_energy": round(self._state.current_energy, 1),
            "max_energy": self._state.max_energy,
            "energy_ratio": round(self.energy_ratio, 3),
            "fatigue_level": round(self._state.fatigue_level, 3),
            "is_fatigued": self._state.is_fatigued,
            "recharge_rate": self._state.recharge_rate,
            "hard_decision_streak": self._hard_decision_streak,
            "total_decisions": self._total_decisions,
            "rest_cycles": self._rest_cycles,
            "current_effects": {
                "exploration_modifier": round(effects.exploration_modifier, 3),
                "confidence_bias": round(effects.confidence_bias, 3),
                "decision_noise": round(effects.decision_noise, 3),
                "default_bias": round(effects.default_bias, 3),
                "novelty_modifier": round(effects.novelty_modifier, 3),
                "speed_modifier": round(effects.speed_modifier, 3),
            },
            "recent_difficulty": [round(d, 3) for d in self._state.recent_difficulty[-10:]],
            "recent_effects": self._effects_history[-10:],
        }
