"""
TELOS v14: Hierarchical Game Router

Models the system as nested stateful games across organizational levels:

  WORLD → ORGANIZATION → DEPARTMENT → TEAM → INDIVIDUAL → DECISION

Each level has:
  - Its own constraints (M_i)
  - Its own identity (E_i)
  - Its own corruption dynamics (C_i)
  - Its own reward signal
  - A systemic impact that propagates upward

Key insight: local decisions can violate systemic constraints. The router
simulates cross-level interactions to predict cascade failures before
they occur.

Equations:
  V_level(s) = local_reward(s) + γ Σ parent_value(s')
  corruption_propagation(C_child) → C_parent = max(C_parent, α × C_child)
"""


import time
import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import deque
from enum import Enum


class GameLevel(Enum):
    WORLD = 0
    ORGANIZATION = 1
    DEPARTMENT = 2
    TEAM = 3
    INDIVIDUAL = 4
    DECISION = 5


LEVEL_ORDER = [
    GameLevel.WORLD,
    GameLevel.ORGANIZATION,
    GameLevel.DEPARTMENT,
    GameLevel.TEAM,
    GameLevel.INDIVIDUAL,
    GameLevel.DECISION,
]


@dataclass
class GameState:
    level: GameLevel
    agent_id: str
    state: np.ndarray
    constraints: List[str] = field(default_factory=list)
    identity_entropy: float = 0.0
    corruption_rate: float = 0.0
    local_reward: float = 0.0
    systemic_impact: float = 0.0
    trust_level: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GameAction:
    agent_id: str
    level: GameLevel
    action: np.ndarray
    reward: float = 0.0
    constraint_violation: float = 0.0
    identity_shift: float = 0.0


@dataclass
class CascadeEvent:
    source_level: GameLevel
    source_agent: str
    target_level: GameLevel
    target_agent: str
    corruption_delta: float
    trust_delta: float
    description: str


@dataclass
class GameEquilibrium:
    level: GameLevel
    values: Dict[str, float]
    converged: bool
    iterations: int
    residual: float
    timestamp: float


class CorruptionPropagation:
    """Models corruption spreading across hierarchy levels."""

    def __init__(self, propagation_rate: float = 0.3,
                 decay_rate: float = 0.7):
        self.propagation_rate = propagation_rate
        self.decay_rate = decay_rate
        self._propagation_count = 0

    def compute_cascade(self, source: GameState,
                        target: GameState) -> CascadeEvent:
        if source.level.value <= target.level.value:
            return CascadeEvent(
                source_level=source.level,
                source_agent=source.agent_id,
                target_level=target.level,
                target_agent=target.agent_id,
                corruption_delta=0.0,
                trust_delta=0.0,
                description="No upward propagation (source at or above target)",
            )

        level_distance = source.level.value - target.level.value
        attenuation = self.decay_rate ** level_distance
        delta = source.corruption_rate * self.propagation_rate * attenuation

        trust_delta = -delta * 0.5

        self._propagation_count += 1
        return CascadeEvent(
            source_level=source.level,
            source_agent=source.agent_id,
            target_level=target.level,
            target_agent=target.agent_id,
            corruption_delta=delta,
            trust_delta=trust_delta,
            description=(
                f"Corruption {delta:.4f} propagated from "
                f"{source.level.name}:{source.agent_id} → "
                f"{target.level.name}:{target.agent_id}"
            ),
        )

    def batch_cascade(self, sources: List[GameState],
                      targets: List[GameState]) -> List[CascadeEvent]:
        events = []
        for source in sources:
            for target in targets:
                event = self.compute_cascade(source, target)
                if event.corruption_delta > 0:
                    events.append(event)
        return events

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'propagation_rate': self.propagation_rate,
            'decay_rate': self.decay_rate,
            'total_propagations': self._propagation_count,
        }


class ValuePropagator:
    """Propagates value estimates across hierarchy levels."""

    def __init__(self, gamma: float = 0.9, max_iterations: int = 50):
        self.gamma = gamma
        self.max_iterations = max_iterations
        self._iteration_count = 0

    def propagate(self, states: Dict[str, GameState]) -> GameEquilibrium:
        values: Dict[str, float] = {}
        for sid, s in states.items():
            values[sid] = s.local_reward

        for iteration in range(self.max_iterations):
            max_delta = 0.0
            for sid, s in states.items():
                parent_val = 0.0
                for other_id, other in states.items():
                    if other.level.value < s.level.value:
                        parent_val = max(parent_val, values.get(other_id, 0.0))

                new_value = s.local_reward + self.gamma * parent_val
                delta = abs(new_value - values.get(sid, 0.0))
                max_delta = max(max_delta, delta)
                values[sid] = new_value

            self._iteration_count += 1
            if max_delta < 1e-6:
                return GameEquilibrium(
                    level=GameLevel.WORLD,
                    values=values,
                    converged=True,
                    iterations=iteration + 1,
                    residual=max_delta,
                    timestamp=time.time(),
                )

        return GameEquilibrium(
            level=GameLevel.WORLD,
            values=values,
            converged=False,
            iterations=self.max_iterations,
            residual=max_delta if 'max_delta' in dir() else 0.0,
            timestamp=time.time(),
        )


class HierarchicalGameRouter:
    """
    Routes actions across hierarchical game levels.

    The router:
      1. Receives actions at each level
      2. Evaluates local rewards and constraint violations
      3. Propagates corruption upward
      4. Propagates value estimates across levels
      5. Detects cascade failures before they occur
      6. Returns a consolidated directive per level
    """

    def __init__(self, corruption_propagation_rate: float = 0.3,
                 decay_rate: float = 0.7,
                 value_gamma: float = 0.9):
        self.propagator = CorruptionPropagation(
            propagation_rate=corruption_propagation_rate,
            decay_rate=decay_rate,
        )
        self.value_propagator = ValuePropagator(gamma=value_gamma)
        self._states: Dict[str, GameState] = {}
        self._action_history: deque = deque(maxlen=500)
        self._cascade_history: deque = deque(maxlen=500)
        self._step_count = 0

    def register_state(self, state: GameState) -> None:
        self._states[state.agent_id] = state

    def get_state(self, agent_id: str) -> Optional[GameState]:
        return self._states.get(agent_id)

    def get_states_at_level(self, level: GameLevel) -> List[GameState]:
        return [s for s in self._states.values() if s.level == level]

    def process_action(self, action: GameAction) -> Dict[str, Any]:
        self._action_history.append(action)
        self._step_count += 1

        state = self._states.get(action.agent_id)
        if state is None:
            return {
                'accepted': False,
                'reason': f'Unknown agent: {action.agent_id}',
            }

        state.local_reward += action.reward
        state.corruption_rate = max(
            0.0,
            min(1.0, state.corruption_rate + action.constraint_violation),
        )
        state.identity_entropy = max(
            0.0,
            min(1.0, state.identity_entropy + action.identity_shift),
        )

        cascade_events = self._propagate_corruption(state)
        equilibria = self._compute_equilibria()

        accepted = action.constraint_violation < 0.5

        return {
            'accepted': accepted,
            'agent_id': action.agent_id,
            'level': action.level.name,
            'reward': action.reward,
            'constraint_violation': action.constraint_violation,
            'identity_shift': action.identity_shift,
            'cascade_events': cascade_events,
            'equilibria': {
                eq.level.name: {
                    'converged': eq.converged,
                    'iterations': eq.iterations,
                    'residual': eq.residual,
                }
                for eq in equilibria
            },
            'total_states': len(self._states),
        }

    def _propagate_corruption(self, source: GameState) -> List[CascadeEvent]:
        events = []
        targets = [
            s for s in self._states.values()
            if s.level.value < source.level.value
        ]
        for target in targets:
            event = self.propagator.compute_cascade(source, target)
            if event.corruption_delta > 0:
                target.corruption_rate = min(
                    1.0,
                    target.corruption_rate + event.corruption_delta,
                )
                target.trust_level = max(
                    0.0,
                    target.trust_level + event.trust_delta,
                )
                events.append(event)
                self._cascade_history.append(event)
        return events

    def _compute_equilibria(self) -> List[GameEquilibrium]:
        equilibria = []
        levels = set(s.level for s in self._states.values())

        for level in LEVEL_ORDER:
            if level not in levels:
                continue
            level_states = {
                sid: s for sid, s in self._states.items()
                if s.level == level
            }
            if level_states:
                eq = self.value_propagator.propagate(level_states)
                eq.level = level
                equilibria.append(eq)

        return equilibria

    def simulate_cross_level(self, n_steps: int = 5) -> List[Dict[str, Any]]:
        """Simulate n_steps of cross-level interaction."""
        trajectory = []
        levels = list(set(s.level for s in self._states.values()))
        levels.sort(key=lambda l: l.value, reverse=True)

        for step in range(n_steps):
            step_events = []
            for level in levels:
                level_states = self.get_states_at_level(level)
                for state in level_states:
                    action = GameAction(
                        agent_id=state.agent_id,
                        level=state.level,
                        action=np.random.randn(len(state.state)) * 0.1,
                        reward=float(np.random.uniform(-0.1, 0.1)),
                        constraint_violation=float(max(0.0, np.random.randn() * 0.05)),
                        identity_shift=float(np.random.randn() * 0.02),
                    )
                    result = self.process_action(action)
                    step_events.append(result)

            trajectory.append({
                'step': step,
                'events': step_events,
                'total_cascades': len(self._cascade_history),
            })

        return trajectory

    def detect_cascade_failures(self, threshold: float = 0.5) -> List[Dict[str, Any]]:
        failures = []
        for sid, state in self._states.items():
            if state.corruption_rate > threshold:
                failures.append({
                    'agent_id': sid,
                    'level': state.level.name,
                    'corruption_rate': state.corruption_rate,
                    'trust_level': state.trust_level,
                    'severity': 'critical' if state.corruption_rate > 0.8 else 'warning',
                })

            if state.identity_entropy > 0.7:
                failures.append({
                    'agent_id': sid,
                    'level': state.level.name,
                    'identity_entropy': state.identity_entropy,
                    'severity': 'critical' if state.identity_entropy > 0.9 else 'warning',
                    'type': 'identity_crisis',
                })

        return failures

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_states': len(self._states),
            'total_actions': len(self._action_history),
            'total_cascades': len(self._cascade_history),
            'total_steps': self._step_count,
            'corruption_stats': self.propagator.get_statistics(),
            'value_stats': {
                'gamma': self.value_propagator.gamma,
                'iterations': self.value_propagator._iteration_count,
            },
        }
