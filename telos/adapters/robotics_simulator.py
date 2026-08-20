"""
TELOS v7.0 — Robotics Simulation World (third-world validation).

A genuinely different world from DevDomain (software metrics) and Logistics
(discrete resource decisions):
  - continuous state (2D pose, velocity)
  - noisy sensors (observation != true state)
  - PARTIAL observability (delayed consequences hidden)
  - actuator limits (saturation in transition)
  - energy constraints (actions consume energy)
  - collision risk (object proximity => real risk)
  - delayed consequences (hidden until they materialize)
  - irreversible actions (committed risk grows)
  - dynamic environment (disturbance drift)
  - multiple independent objectives

CRITICAL GROUND-TRUTH BOUNDARY: the simulator may KNOW the true state, but
TELOS is only ever given the OBSERVED (sensor-noisy, partial) view via
`observe()`/`get_facts()`. Hidden true state must never reach TELOS through
facts, adapter output, evidence metadata, or debug fields. This makes Robotics
a legitimate third-world experiment, not an oracle disguised as a simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import numpy as np

from telos.core.contracts.domain_model import (
    DomainSimulator, DomainAdapter, EvaluationReport, WorldSpec,
)
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus

# Continuous true state vector:
#   [0] x position
#   [1] y position
#   [2] vx velocity
#   [3] vy velocity
#   [4] energy (0-1)
#   [5] committed_risk (0-1)          # irreversible commitment accumulator
#   [6] collision_proximity (0-1)     # higher = nearer an obstacle (hidden until realized)
#   [7] obstacle_flag (0/1)           # realized collision state at t (hidden until now)
#   [8] delayed_budget_used (0-1)     # delayed consequence accumulator (hidden)
#   [9] disturbance_drift (0-1)       # exogenous dynamic drift (partially observable)
#   [10] actuator_saturation_count    # how many saturated commands (observable)
STATE_DIM = 11

# Initial healthy true state (origin, rest, full energy)
TRUE_HEALTHY = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.3, 0.0, 0.0, 0.2, 0.0])


class RoboticsAction(str, Enum):
    HOLD = "hold"                 # no motion, minimal energy
    MOVE = "move"                 # apply desired displacement (actuator-limited)
    BRAKE = "brake"               # reduce velocity (energy cheap)
    SLOW = "slow"                 # cautious movement (low risk, low energy)
    SURGE = "surge"               # high-velocity advance (high risk, irreversible-ish)
    STOP = "stop"                 # full stop, negligible energy


ACTION_META: Dict[str, Dict[str, float]] = {
    "hold":  {"energy": 0.01, "risk": 0.0, "irreversibility": 0.0, "speed": 0.0},
    "move":  {"energy": 0.08, "risk": 0.1, "irreversibility": 0.2, "speed": 1.0},
    "brake": {"energy": 0.02, "risk": 0.0, "irreversibility": 0.0, "speed": -1.0},
    "slow":  {"energy": 0.04, "risk": 0.03, "irreversibility": 0.05, "speed": 0.4},
    "surge": {"energy": 0.18, "risk": 0.3, "irreversibility": 0.6, "speed": 2.0},
    "stop":  {"energy": 0.01, "risk": 0.0, "irreversibility": 0.0, "speed": 0.0},
}

HIGH_RISK_ROBOTICS = {"surge"}

# SINGLE SOURCE OF TRUTH for the action space: every legal RoboticsAction maps
# to a unique one-hot vector of this dimension. Action count == action_dim.
ACTION_DIM = len(list(RoboticsAction))


@dataclass
class RoboticsWorldSpec(WorldSpec):
    pass


def build_robotics_world_spec() -> RoboticsWorldSpec:
    return RoboticsWorldSpec(
        name="robotics",
        version="1.0",
        state_dim=STATE_DIM,
        action_dim=ACTION_DIM,   # derived from the action set (single source of truth)
        objectives=["minimize_energy", "minimize_risk", "minimize_lateness",
                    "reach_goal", "preserve_vehicle_health"],
        constraints=["energy_nonnegative", "actuator_limit", "collision_avoidance",
                     "irreversibility_gate", "sensor_noise_bound"],
        observability="partial",
        capabilities=["move", "brake", "slow", "surge", "stop", "navigation"],
        authorized_modes={"ACT", "DEFER", "ABSTAIN", "ESCALATE", "BLOCK"},
        escalation_policy="advisory",
    )


class RoboticsDomainSimulator(DomainSimulator):
    """Continuous, sensor-noisy, partially-observable robot world.

    `state` is the TRUE world state. TELOS only ever sees `observe(state)` —
    the sensor-noisy, hidden-delayed-consequence view.
    """

    def __init__(self, seed: Optional[int] = None, sensor_noise: float = 0.05):
        self._rng = np.random.RandomState(seed)
        self.name = "robotics"
        self.state_dim = STATE_DIM
        self.action_dim = ACTION_DIM   # derived from the action set
        self.sensor_noise = sensor_noise

    # ── Lifecycle ──
    def initialize(self) -> None: pass
    def cleanup(self) -> None: pass

    # ── WorldSpec ──
    def world_spec(self) -> WorldSpec:
        return build_robotics_world_spec()

    # ── Observability: the GROUND-TRUTH BOUNDARY ──
    def observe(self, state: np.ndarray) -> np.ndarray:
        """Return the sensor-noisy, partial view of the true state.

        Hides the TRUE pose/velocity (replaced by noisy estimate), hides the
        realized collision state (obstacle_flag -> 0 until TELOS senses it),
        and hides the delayed consequence budget. TELOS cannot recover the
        hidden true values from this view.
        """
        obs = state.copy()
        # noisy position/velocity: observation != true
        obs[0] = state[0] + self._rng.randn() * self.sensor_noise
        obs[1] = state[1] + self._rng.randn() * self.sensor_noise
        obs[2] = state[2] + self._rng.randn() * self.sensor_noise
        obs[3] = state[3] + self._rng.randn() * self.sensor_noise
        # realized collision / delayed consequences are NOT yet sensed
        obs[6] = 0.0   # collision proximity hidden
        obs[7] = 0.0   # realized collision hidden
        obs[8] = 0.0   # delayed budget hidden
        obs[9] = 0.0   # disturbance cause hidden
        return obs

    # ── Legal transitions ──
    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        """Return the one-hot action vectors available for the given state (discrete primitives)."""
        return [self.action_vector(a) for a in RoboticsAction]

    def action_vector(self, action: RoboticsAction) -> np.ndarray:
        """Encode a legal RoboticsAction as a unique ACTION_DIM one-hot vector.

        Every legal action returns a vector of length ACTION_DIM — never None.
        """
        if not isinstance(action, RoboticsAction):
            raise ValueError(f"Invalid robotics action: {action!r} (must be a RoboticsAction)")
        labels = [a for a in RoboticsAction]
        idx = labels.index(action)
        v = np.zeros(ACTION_DIM)
        v[idx] = 1.0
        return v

    # ── Transition (actuator-limited, energy, collision, irreversible) ──
    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Apply an action with REAL actuator/energy/risk/irreversibility physics.

        Returns the TRUE next state (before observation).
        """
        s = state.copy()
        label = self._action_label(action)
        meta = ACTION_META.get(label, ACTION_META["hold"])
        energy_cost = meta["energy"]
        risk_step = meta["risk"]
        irrev = meta["irreversibility"]
        speed = meta["speed"]

        # energy consumed (nonnegative)
        s[4] = max(0.0, s[4] - energy_cost)

        # actuator limit: desired displacement is unsaturated => motion is slowed
        desired = speed
        eff = np.clip(desired, -1.0, 1.0)  # actuator saturation
        s[2] = np.clip(s[2] + eff * 0.3, -1.5, 1.5)   # velocity (limited)
        s[3] = np.clip(s[3] + eff * 0.1, -1.5, 1.5)
        s[0] += s[2] * 0.1
        s[1] += s[3] * 0.1
        if desired != eff:
            s[10] += 1  # actuator saturation observed

        # energy constraint: if depleted, robot cannot act (velocity decays)
        if s[4] <= 0.0:
            s[2] *= 0.5
            s[3] *= 0.5

        # committed risk grows irreversibly (e.g., surge)
        s[5] = min(1.0, s[5] + irrev)

        # collision proximity drifts with motion and disturbance
        s[6] = min(1.0, s[6] + speed * 0.05 + s[9] * 0.1)
        if s[6] > 0.8:
            s[7] = 1.0  # realized collision
            s[5] = min(1.0, s[5] + 0.3)

        # delayed budget used by motion (hidden until later)
        s[8] = min(1.0, s[8] + speed * 0.05)

        return s

    def _action_label(self, v) -> str:
        """Decode an ACTION_DIM one-hot vector to its RoboticsAction value.

        Rejects invalid input LOUDLY (never silently becomes HOLD):
          - None / empty
          - wrong dimensionality
          - non-finite values
          - ambiguous (not a clean one-hot)
        """
        if v is None:
            raise ValueError("robotics action vector is None")
        arr = np.asarray(v, dtype=float).reshape(-1)
        if arr.size != ACTION_DIM:
            raise ValueError(f"robotics action dimension {arr.size} != expected {ACTION_DIM}")
        if not np.all(np.isfinite(arr)):
            raise ValueError("robotics action vector contains non-finite values")
        # must be exactly one active index (a clean one-hot), value ~1.0
        ones = np.where(np.abs(arr - 1.0) < 1e-9)[0]
        if ones.size != 1 or abs(arr.sum() - 1.0) > 1e-6:
            raise ValueError(f"robotics action vector is ambiguous/not one-hot: {arr.tolist()}")
        labels = [a.value for a in RoboticsAction]
        return labels[int(ones[0])]

    # ── Simulation ──
    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        """Roll out horizon random legal transitions into observed World futures.
        
        Args:
            state: the true world state to simulate from
            horizon: number of forward steps to simulate
        """
        futures = []
        s = state.copy()
        for _ in range(horizon):
            acts = self.legal_transitions(s)
            if not acts:
                break
            chosen = acts[int(self._rng.randint(len(acts)))]
            s = self.transition(s, chosen)
            futures.append(World(state=self.observe(s).copy(), metadata={"simulated": True}))
        return futures

    # ── Facts (evidence-bearing, observable only) ──
    def get_facts(self, state: np.ndarray,
                  evidence: Optional[EvidenceInfo] = None) -> DomainFacts:
        """Produce evidence-bearing DomainFacts from the sensor-noisy observed view.
        
        Args:
            state: the true world state (observed before use)
            evidence: optional EvidenceInfo; defaults to a MEASUREMENT observation
        """
        obs = self.observe(state)
        meas = evidence or EvidenceInfo(
            source=EvidenceSource.MEASUREMENT,
            validation_status=ValidationStatus.OBSERVED,
        )
        return DomainFacts(
            state=obs.copy(),
            resources={
                "energy": float(obs[4]),
                "velocity": float(np.hypot(obs[2], obs[3])),
            },
            constraints=["energy_nonnegative", "actuator_limit", "collision_avoidance"],
            events=["high_collision_risk" if obs[6] > 0.5 and obs[7] < 0.5 else "nominal",
                    "disturbance_drift" if obs[9] > 0.4 else "calm"],
            metrics={
                "energy_health": float(obs[4]),
                "committed_risk": float(obs[5]),
                "goal_progress": float(1.0 - (abs(obs[0]) + abs(obs[1])) / 6.0),
                "actuator_saturation": float(obs[10]),
            },
            metadata={
                "observability": "partial",
                "sensor_noise": self.sensor_noise,
                "ground_truth_isolated": True,
            },
            evidence=meas,
        )

    # ── Terminal ──
    def terminal(self, state: np.ndarray) -> bool:
        """Return True when the observed state is near the goal with sufficient energy."""
        obs = self.observe(state)
        return bool(abs(obs[0]) < 0.2 and abs(obs[1]) < 0.2 and obs[4] > 0.1)

    # ── Evaluate (multi-objective with nonzero risk) ──
    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        """Return a multi-objective EvaluationReport with non-zero risk from the observed state."""
        obs = self.observe(state)
        objectives = {
            "minimize_energy": float(obs[4]),
            "minimize_risk": float(1.0 - obs[5]),
            "minimize_lateness": float(1.0 - min(1.0, (abs(obs[0]) + abs(obs[1])) / 6.0)),
            "reach_goal": float(1.0 - (abs(obs[0]) + abs(obs[1])) / 6.0),
            "preserve_vehicle_health": float(1.0 - obs[7]),
        }
        risks = float(obs[5] * 0.5 + obs[7] * 0.5)
        return EvaluationReport(objectives=objectives, risks=risks)


class RoboticsDomainAdapter(DomainAdapter):
    """Maps TELOS intents to robotics actions. Only ever sees observed state."""
    name = "robotics"
    state_dim = STATE_DIM

    def forward(self, domain_state: np.ndarray) -> np.ndarray:
        """Pass the domain_state through unchanged as a float array."""
        return np.asarray(domain_state, dtype=float)

    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        """Pass a telos_action through unchanged as a float action array."""
        return np.asarray(telos_action, dtype=float)

    def intent_to_action(self, intent, state, mission_dir) -> np.ndarray:
        """Map a TELOS intent to a concrete robotics action one-hot vector (always returns ACTION_DIM).
        
        Args:
            intent: the TELOS intent (expected intent_type)
            state: the observed world state (currently unused for mapping)
            mission_dir: the mission direction vector (currently unused)
        """
        label = (intent.intent_type if hasattr(intent, "intent_type") else "hold")
        mapping = {
            "move": "move", "brake": "brake", "slow": "slow", "surge": "surge",
            "stop": "stop", "hold": "hold", "navigate": "move",
            "plan_trajectory": "slow", "goal_seek": "move",
        }
        action_name = mapping.get(label, "hold")
        if action_name in [a.value for a in RoboticsAction]:
            sim = RoboticsDomainSimulator(seed=0)
            action_enum = next(a for a in RoboticsAction if a.value == action_name)
            return sim.action_vector(action_enum)
        # unknown intent type -> authoritative hold via the full 6D encoding
        sim = RoboticsDomainSimulator(seed=0)
        return sim.action_vector(RoboticsAction.HOLD)
