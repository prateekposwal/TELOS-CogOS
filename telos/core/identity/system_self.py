"""
SystemSelf — The Cognitive Identity Model (Lambda1.x)

The system's model of itself: a persistent, evolving identity that
shapes decisions and records the system's own history.

Self-model dimensions:
- mood: current operational disposition (curious, cautious, confident, uncertain, fatigued)
- confidence_trend: whether self-confidence is rising, stable, or falling
- dominant_streak: how many cycles the same stream configuration has dominated
- exploration_appetite: willingness to try untested approaches (0.0=never, 1.0=always)
- resilience: ability to absorb failures before changing mood (high = patient, low = reactive)
- identity_markers: set of tags the system uses to describe itself
- belief_state: (Fix 4 / C3) probability distribution over possible system states

Fix 4 (C3): Added belief_state B_t — a dict mapping domain → probability
distribution. Initialized as uniform. Updated via Bayesian inference:
  P(s | o) ∝ P(o | s) * P(s)

Fix 6 (C3): Added formal_identity_update() — the ψ operator:
  I_{t+1} = ψ(I_t, a_t, s_t, o_t)
Updates (G, M, B, C, K, V) as a unified formal transformation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
import time
import logging
import json
import numpy as np

MOOD_CHANGE_COOLDOWN: int = 20
GENESIS_MOOD: str = "curious"
MOOD_STEPS = ["curious", "confident", "stable", "cautious", "uncertain", "fatigued"]
MOOD_MAX_STEPS_FROM_GENESIS: int = 5

logger = logging.getLogger('telos_identity')


@dataclass
class IdentityState:
    mood: str = "curious"           # curious, cautious, confident, uncertain, fatigued
    confidence_trend: str = "stable" # rising, stable, falling
    dominant_streak: int = 0
    exploration_appetite: float = 0.5
    resilience: float = 0.5
    identity_markers: Set[str] = field(default_factory=lambda: {"nascent", "exploring"})
    cycles_since_mood_change: int = 0
    # Fix 4 (C3): Belief state B_t
    belief_state: Dict[str, Dict[str, float]] = field(default_factory=dict)


class SystemSelf:
    """The persistent self-model of the TELOS system.

    This is the "I" that persists across cycles, domains, and restarts.
    It records how the system feels about its own performance and
    adjusts decision parameters accordingly.

    The self-model satisfies Lambda1.x by ensuring that:
    1. Identity is persistent (saved/loaded with checkpoints)
    2. Identity evolves with experience (mood changes based on DI/MD trends)
    3. Identity shapes decisions (mood influences exploration, risk tolerance)

    Fix 4 (C3): Now includes belief_state B_t — Bayesian belief tracking.
    Fix 6 (C3): Now includes formal_identity_update() — the ψ operator.
    """

    def __init__(self):
        self._state = IdentityState()
        self._genesis_mood = GENESIS_MOOD
        self._last_mood_change_cycle: int = 0
        self._history: List[Dict] = []
        self._di_window: List[float] = []
        self._md_window: List[float] = []
        self._block_window: List[bool] = []
        self._max_history = 100
        # Fix 4: Initialize belief_state with standard domains as uniform distributions
        self._init_beliefs()

    def _init_beliefs(self) -> None:
        """Fix 4: Initialize beliefs as uniform distributions over possible states."""
        self._state.belief_state = {
            "decision_quality": {
                "high": 0.33,
                "medium": 0.34,
                "low": 0.33,
            },
            "environment_stability": {
                "stable": 0.25,
                "changing": 0.25,
                "unpredictable": 0.25,
                "unknown": 0.25,
            },
            "resource_availability": {
                "abundant": 0.25,
                "sufficient": 0.25,
                "limited": 0.25,
                "critical": 0.25,
            },
        }

    @property
    def mood(self) -> str:
        return self._state.mood

    @property
    def state(self) -> IdentityState:
        return self._state

    # ── Fix 4 (C3): Belief state methods ──

    def get_belief_state(self) -> Dict[str, Dict[str, float]]:
        """Fix 4: Return current belief state B_t."""
        return dict(self._state.belief_state)

    def update_belief(self, domain: str, observation: str,
                      likelihood: float = 0.7) -> None:
        """Fix 4: Bayesian belief update.

        P(s | o) ∝ P(o | s) * P(s)

        Updates the belief distribution for a given domain based on a
        noisy observation. The likelihood parameter controls how much
        weight the observation carries.

        Args:
            domain: The belief domain to update (e.g., "decision_quality")
            observation: The observed state value (e.g., "high")
            likelihood: P(observation | state) — observation reliability
        """
        beliefs = self._state.belief_state.get(domain)
        if beliefs is None:
            return

        if observation not in beliefs:
            return

        total = 0.0
        new_beliefs = {}

        for state_val, prob in beliefs.items():
            # Probability of this observation given each possible state
            if state_val == observation:
                obs_prob = likelihood
            else:
                # Uniform error distribution across alternative states
                remaining = len(beliefs) - 1
                obs_prob = (1.0 - likelihood) / max(remaining, 1)

            # Bayes: P(s|o) ∝ P(o|s) * P(s)
            unnormalized = obs_prob * prob
            new_beliefs[state_val] = unnormalized
            total += unnormalized

        # Normalize
        if total > 0:
            for state_val in new_beliefs:
                new_beliefs[state_val] /= total

        self._state.belief_state[domain] = new_beliefs

        logger.debug(
            f"Belief update [{domain}]: observed={observation}, "            f"likely={likelihood:.2f}"
        )

    def bayesian_belief_update(self, observation: str,
                                domain: str = "decision_quality") -> None:
        """Fix 4: Convenience wrapper around update_belief.

        Derives likelihood from current mood: confident mood = higher
        likelihood (trusts observations more), uncertain = lower.

        Args:
            observation: Observed state value
            domain: Belief domain to update
        """
        mood_likelihood_map = {
            "confident": 0.85,
            "curious": 0.75,
            "stable": 0.70,
            "cautious": 0.60,
            "uncertain": 0.45,
            "fatigued": 0.40,
        }
        likelihood = mood_likelihood_map.get(self._state.mood, 0.7)
        self.update_belief(domain, observation, likelihood)

    # ── Fix 6 (C3): Formal identity update operator ──

    def formal_identity_update(self, action: str, state: Any,
                                observation: str) -> Dict:
        """Fix 6: Formal ψ operator.

        I_{t+1} = ψ(I_t, a_t, s_t, o_t)

        Transforms the full identity tuple (G_t, M_t, B_t, C_t, K_t, V_t)
        as a function of the action taken, resulting state, and new observation.

        This operator is the formal core of Lambda1.x identity evolution:
          - G: Goals updated based on action outcome (progress toward target)
          - M: Memory extended with observation (history grows)
          - B: Belief state updated via Bayesian inference (Fix 4)
          - C: Constraints adjusted based on action consequences
          - K: Capabilities updated (tracked externally, flagged here)
          - V: Values refined (identity markers evolve)

        Args:
            action: The action taken (string identifier)
            state: The resulting world state
            observation: The observation received after the action

        Returns:
            Updated identity state components as dict
        """
        # ── G: Update goals ──
        # Track progress: if action moved toward goal, record it
        goals_updated = {
            "last_action": action,
            "progress_indicator": observation,
        }

        # ── M: Update memory ──
        # Append observation to history
        memory_entry = {
            "time": time.time(),
            "action": action,
            "observation": observation,
            "mood": self._state.mood,
        }
        self._history.append(memory_entry)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # ── B: Update belief state ──
        # Derive observation quality from action/state
        obs_domain = "decision_quality"
        if "fail" in observation.lower() or "block" in observation.lower():
            self.bayesian_belief_update("low", obs_domain)
        elif "success" in observation.lower() or "reward" in observation.lower():
            self.bayesian_belief_update("high", obs_domain)
        else:
            self.bayesian_belief_update("medium", obs_domain)

        # ── C: Update constraints ──
        # If action was blocked, tighten constraints
        # If action succeeded, relax constraints slightly
        constraints_updated = {"action": action}

        # ── K: Update capabilities ──
        capabilities_updated = {
            "last_action": action,
            "skill_relevant": observation not in ["blocked", "failed"],
        }

        # ── V: Update values ──
        # Integrate markers based on observation
        if observation == "blocked" or observation == "failed" or observation == "error":
            self._state.identity_markers.add("cautious_experience")
        elif observation == "reward" or "success" in observation:
            self._state.identity_markers.add("effective_actor")

        values_updated = {
            "identity_markers": sorted(self._state.identity_markers),
        }

        result = {
            "G_t": goals_updated,
            "M_t": {k: v for k, v in memory_entry.items() if k != "time"},
            "B_t": dict(self._state.belief_state),
            "C_t": constraints_updated,
            "K_t": capabilities_updated,
            "V_t": values_updated,
        }

        logger.debug(
            f"Identity update ψ: action={action}, obs={observation}, "            f"mood={self._state.mood}"
        )

        return result

    def observe(self, di: float, md: float, was_blocked: bool,
                 identity_markers_to_add: Optional[Set[str]] = None,
                 cycle_number: int = 0) -> None:
        """Record a decision cycle outcome and update self-model.
        
        Fix 4: Also updates belief_state based on observed DI/MD values.
        
        Args:
            identity_markers_to_add: Optional markers from Kintsugi failure integration.
            cycle_number: Current pipeline cycle (for mood cooldown enforcement).
        """
        self._di_window.append(di)
        self._md_window.append(md)
        self._block_window.append(was_blocked)
        if len(self._di_window) > 20:
            self._di_window.pop(0)
            self._md_window.pop(0)
            self._block_window.pop(0)

        self._update_mood(cycle_number)
        self._update_trend()
        self._update_appetite()
        self._state.cycles_since_mood_change += 1

        # Kintsugi: integrate failure-derived markers into identity
        if identity_markers_to_add:
            self._state.identity_markers.update(identity_markers_to_add)
            logger.info(
                f"SystemSelf: integrated identity markers: {identity_markers_to_add}"
            )

        # ── Fix 4: Update belief_state from observed DI/MD ──
        if len(self._di_window) >= 3:
            recent_di = np.mean(self._di_window[-3:]) if hasattr(np, 'mean') else (
                sum(self._di_window[-3:]) / 3
            )
            if recent_di > 0.7:
                self.bayesian_belief_update("high", "decision_quality")
            elif recent_di > 0.4:
                self.bayesian_belief_update("medium", "decision_quality")
            else:
                self.bayesian_belief_update("low", "decision_quality")

        self._history.append({
            "time": time.time(),
            "mood": self._state.mood,
            "di": di,
            "md": md,
            "blocked": was_blocked,
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def _update_mood(self, current_cycle: int = 0) -> None:
        """Update mood based on recent DI/MD trends.
        
        Enforces MOOD_CHANGE_COOLDOWN: mood can only change every N cycles.
        Resilience modulates thresholds: higher resilience means more failures
        needed to trigger negative mood changes.
        """
        if len(self._di_window) < 3:
            return

        # Cooldown check — prevent fast mood oscillation
        if current_cycle > 0 and current_cycle - self._last_mood_change_cycle < MOOD_CHANGE_COOLDOWN:
            return

        recent_di = self._di_window[-5:]
        recent_md = self._md_window[-5:]
        recent_blocked = self._block_window[-5:]

        avg_di = sum(recent_di) / len(recent_di)
        avg_md = sum(recent_md) / len(recent_md)
        block_rate = sum(recent_blocked) / len(recent_blocked)

        # Resilience modulates thresholds:
        #   resilience=0.0 → thresholds are tight (easy to trigger mood change)
        #   resilience=1.0 → thresholds are loose (hard to trigger mood change)
        r = self._state.resilience
        block_threshold = 0.6 * (1.0 + r)  # 0.6 at r=0, 1.2 at r=1 (never triggers at 1.0)
        di_high_threshold = 0.85 * (1.0 - r * 0.2)  # 0.85 at r=0, 0.68 at r=1
        di_low_threshold = 0.4 * (1.0 - r * 0.3)  # 0.40 at r=0, 0.28 at r=1
        md_high_threshold = 3.0 * (1.0 + r * 0.5)  # 3.0 at r=0, 4.5 at r=1

        new_mood = self._state.mood

        if block_rate > block_threshold:
            new_mood = "uncertain"
        elif avg_di > di_high_threshold and avg_md < 0.5:
            if self._state.mood != "confident" and self._state.cycles_since_mood_change > 3:
                new_mood = "confident"
        elif avg_di < di_low_threshold or avg_md > md_high_threshold:
            new_mood = "cautious"
        elif avg_di > 0.7 and avg_md < 1.0:
            if self._state.mood == "uncertain" and self._state.cycles_since_mood_change > 3:
                new_mood = "curious"

        if new_mood != self._state.mood:
            logger.info(
                "SystemSelf: mood %s -> %s (di=%.2f, md=%.2f, blocks=%.1f)",
                self._state.mood, new_mood, avg_di, avg_md, block_rate
            )
            self._state.mood = new_mood
            self._last_mood_change_cycle = current_cycle
            self._state.cycles_since_mood_change = 0

    def _update_trend(self) -> None:
        """Update confidence trend (rising/stable/falling)."""
        if len(self._di_window) < 10:
            self._state.confidence_trend = "stable"
            return
        first5 = sum(self._di_window[:5]) / 5
        last5 = sum(self._di_window[-5:]) / 5
        diff = last5 - first5
        if diff > 0.05:
            self._state.confidence_trend = "rising"
        elif diff < -0.05:
            self._state.confidence_trend = "falling"
        else:
            self._state.confidence_trend = "stable"

    def _update_appetite(self) -> None:
        """Update exploration appetite based on mood and trend."""
        mood_map = {
            "curious": 0.7, "confident": 0.6, "cautious": 0.3,
            "uncertain": 0.2, "fatigued": 0.1,
        }
        trend_map = {"rising": 0.1, "stable": 0.0, "falling": -0.1}
        self._state.exploration_appetite = max(
            0.0, min(1.0, mood_map.get(self._state.mood, 0.5) + trend_map.get(self._state.confidence_trend, 0.0))
        )

    def get_risk_adjustment(self) -> float:
        """How much to adjust risk tolerance based on current identity.

        Returns a value in [-0.2, 0.2]:
        - Positive -> more risk-tolerant (confident, curious)
        - Negative -> more risk-averse (uncertain, fatigued)

        Cautious mood returns 0 — it's a watchful state, not a failure state.
        Negative adjustments require evidence of actual blocked decisions.
        """
        mood_map = {"confident": 0.1, "curious": 0.05, "stable": 0.0, "cautious": 0.0, "uncertain": -0.08, "fatigued": -0.12}
        base = mood_map.get(self._state.mood, 0.0)
        # Scale by exploration appetite but cap magnitude
        return base * min(self._state.exploration_appetite, 0.5)

    def get_exploration_adjustment(self) -> float:
        """How much to adjust exploration budget based on current identity."""
        mood_map = {"curious": 0.1, "confident": 0.05, "stable": 0.0, "cautious": -0.05, "uncertain": -0.1, "fatigued": -0.15}
        return mood_map.get(self._state.mood, 0.0)

    def save(self, path: str) -> None:
        data = {
            "state": {
                "mood": self._state.mood,
                "confidence_trend": self._state.confidence_trend,
                "dominant_streak": self._state.dominant_streak,
                "exploration_appetite": self._state.exploration_appetite,
                "resilience": self._state.resilience,
                "identity_markers": sorted(self._state.identity_markers),
                "cycles_since_mood_change": self._state.cycles_since_mood_change,
                "belief_state": self._state.belief_state,  # Fix 4
            },
            "history": self._history[:],
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        sd = data.get("state", {})
        # Genesis anchor: on restore, reject moods more than 2 steps from genesis
        loaded_mood = sd.get("mood", GENESIS_MOOD)
        if GENESIS_MOOD in MOOD_STEPS and loaded_mood in MOOD_STEPS:
            g_idx = MOOD_STEPS.index(GENESIS_MOOD)
            l_idx = MOOD_STEPS.index(loaded_mood)
            if abs(l_idx - g_idx) > MOOD_MAX_STEPS_FROM_GENESIS:
                logger.warning(
                    f"SystemSelf: checkpoint mood '{loaded_mood}' too far from genesis "                    f"'{GENESIS_MOOD}' ({abs(l_idx - g_idx)} steps) — reverting to genesis"
                )
                self._state.mood = GENESIS_MOOD
            else:
                self._state.mood = loaded_mood
        else:
            self._state.mood = loaded_mood
        self._state.confidence_trend = sd.get("confidence_trend", "stable")
        self._state.dominant_streak = sd.get("dominant_streak", 0)
        self._state.exploration_appetite = sd.get("exploration_appetite", 0.5)
        self._state.resilience = sd.get("resilience", 0.5)
        self._state.identity_markers = set(sd.get("identity_markers", ["nascent", "exploring"]))
        self._state.cycles_since_mood_change = sd.get("cycles_since_mood_change", 0)
        # Fix 4: Restore belief_state
        loaded_beliefs = sd.get("belief_state", None)
        if loaded_beliefs:
            self._state.belief_state = loaded_beliefs
        else:
            self._init_beliefs()
        self._history = data.get("history", [])

    def to_dict(self) -> Dict:
        return {
            "mood": self._state.mood,
            "confidence_trend": self._state.confidence_trend,
            "dominant_streak": self._state.dominant_streak,
            "exploration_appetite": round(self._state.exploration_appetite, 3),
            "resilience": round(self._state.resilience, 3),
            "identity_markers": sorted(self._state.identity_markers),
            "belief_state": self._state.belief_state,  # Fix 4
        }

    @property
    def stats(self) -> Dict:
        return self.to_dict()
