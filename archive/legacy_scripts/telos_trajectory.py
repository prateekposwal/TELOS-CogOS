"""
TELOS v14: Mission Simulation Engine & Evolutionary Trajectory Engine

Instead of evaluating single actions, TELOS evaluates entire multi-step
trajectories through counterfactual worlds. The simulation is guided by
mission constraints, historical evidence, and structural invariants.

Trajectory Generation:
  F_i = Φ(S, G, t)  — mission-guided trajectory generation

Evolutionary Cycle:
  Generate → Mutate → Merge → Prune → Repeat

Core equation:
  J(F_i) = Σ γ^k H(S_k) - λ Σ D_M(k) - κ Σ C(k)
  where H = system health, D_M = mission drift, C = corruption
"""

import time
import hashlib
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
from telos_v15_semantics import (
    SemanticExpansionEngine, LatentRole, EntityManifold, RelationalAffordanceGraph,
)


# ═══════════════════════════════════════════════════════════
# 1. TRAJECTORY DATA STRUCTURES
# ═══════════════════════════════════════════════════════════

@dataclass
class TrajectoryStep:
    """A single step in a trajectory."""
    state: np.ndarray
    action: np.ndarray
    reward: float
    health: float
    mission_drift: float
    corruption: float
    step_index: int


@dataclass
class Trajectory:
    """
    A complete trajectory through state space.

    F_i = (s_0, a_0, s_1, a_1, ..., s_T, a_T)

    Each trajectory carries:
      - The sequence of states and actions
      - Per-step health, drift, and corruption scores
      - Aggregate utility J(F_i)
      - Evolutionary metadata (generation, parentage)
    """
    trajectory_id: str
    steps: List[TrajectoryStep] = field(default_factory=list)
    mission_vector: Optional[np.ndarray] = None
    cumulative_health: float = 0.0
    cumulative_drift: float = 0.0
    cumulative_corruption: float = 0.0
    aggregate_utility: float = 0.0
    is_viable: bool = True
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    active_role_ids: List[str] = field(default_factory=list)
    propagation_cost: float = 0.0

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def final_state(self) -> Optional[np.ndarray]:
        return self.steps[-1].state if self.steps else None

    @property
    def final_health(self) -> float:
        return self.steps[-1].health if self.steps else 0.0

    def get_state_sequence(self) -> List[np.ndarray]:
        return [s.state for s in self.steps]

    def get_action_sequence(self) -> List[np.ndarray]:
        return [s.action for s in self.steps]

    def get_health_trajectory(self) -> List[float]:
        return [s.health for s in self.steps]


@dataclass
class CounterfactualWorld:
    """
    A counterfactual world built from a trajectory.

    Represents one possible future that the system could explore.
    Each world carries risk profiles and survival estimates.
    """
    world_id: str
    trajectory: Trajectory
    mission_alignment: float = 1.0
    corruption_level: float = 0.0
    survival_probability: float = 1.0
    risk_profile: Dict[str, float] = field(default_factory=dict)
    description: str = ""


# ═══════════════════════════════════════════════════════════
# 2. TRAJECTORY EVALUATION
# ═══════════════════════════════════════════════════════════

class TrajectoryEvaluator:
    """
    Evaluates trajectories using the aggregate utility function:

    J(F_i) = Σ γ^k H(S_k) - λ Σ D_M(k) - κ Σ C(k)

    where:
      γ = discount factor
      H(S_k) = health at step k
      D_M(k) = mission drift at step k
      C(k) = corruption at step k
      λ = drift penalty weight
      κ = corruption penalty weight
    """

    def __init__(self, gamma: float = 0.95,
                 drift_penalty: float = 1.0,
                 corruption_penalty: float = 2.0):
        self.gamma = gamma
        self.drift_penalty = drift_penalty
        self.corruption_penalty = corruption_penalty
        self._evaluation_count = 0

    def evaluate(self, trajectory: Trajectory) -> float:
        if not trajectory.steps:
            return 0.0

        utility = 0.0
        cumulative_health = 0.0
        cumulative_drift = 0.0
        cumulative_corruption = 0.0

        for k, step in enumerate(trajectory.steps):
            discount = self.gamma ** k
            utility += discount * step.health
            utility -= self.drift_penalty * step.mission_drift
            utility -= self.corruption_penalty * step.corruption
            cumulative_health += step.health
            cumulative_drift += step.mission_drift
            cumulative_corruption += step.corruption
        
        utility -= trajectory.propagation_cost

        trajectory.cumulative_health = cumulative_health
        trajectory.cumulative_drift = cumulative_drift
        trajectory.cumulative_corruption = cumulative_corruption
        trajectory.aggregate_utility = utility
        self._evaluation_count += 1

        return utility

    def batch_evaluate(self, trajectories: List[Trajectory]) -> List[float]:
        return [self.evaluate(t) for t in trajectories]

    def rank(self, trajectories: List[Trajectory]) -> List[Trajectory]:
        evaluated = [(self.evaluate(t), t) for t in trajectories]
        evaluated.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in evaluated]

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_evaluations': self._evaluation_count,
            'gamma': self.gamma,
            'drift_penalty': self.drift_penalty,
            'corruption_penalty': self.corruption_penalty,
        }


# ═══════════════════════════════════════════════════════════
# 3. MISSION SIMULATION ENGINE
# ═══════════════════════════════════════════════════════════

class SimulationStrategy(Enum):
    RANDOM_WALK = "random_walk"
    MISSION_GUIDED = "mission_guided"
    ADVERSARIAL = "adversarial"
    HYBRID = "hybrid"


class MissionSimulationEngine:
    """
    Generates counterfactual trajectories F_i = Φ(S, G, t).
    """

    def __init__(self, mission_vector: np.ndarray,
                 state_dim: int = 6,
                 action_dim: Optional[int] = None,
                 strategy: SimulationStrategy = SimulationStrategy.MISSION_GUIDED,
                 mutation_noise: float = 0.1,
                 n_worlds: int = 50,
                 horizon: int = 10,
                 debug: bool = False,
                 nonlinear_dynamics: bool = False,
                 multi_agent: bool = False,
                 semantic_engine: Optional[SemanticExpansionEngine] = None,
                 adapter: Optional['BaseAdapter'] = None):
        from telos.adapters.base_adapter import BaseAdapter
        mn = np.linalg.norm(mission_vector)
        if mn < 1e-9:
            raise ValueError("Mission vector must be non-zero")
        self.mission_dir = mission_vector / mn
        self.state_dim = state_dim
        self.action_dim = action_dim or state_dim
        self.adapter = adapter
        self.strategy = strategy
        self.mutation_noise = mutation_noise
        self.n_worlds = n_worlds
        self.horizon = horizon
        self.debug = debug
        self.nonlinear_dynamics = nonlinear_dynamics
        self.multi_agent = multi_agent
        self.semantic_engine = semantic_engine or SemanticExpansionEngine(k_roles=3)
        self.potential_entities: Dict[str, List[LatentRole]] = {}
        self._register_default_v15_entities()

        self._world_counter = 0
        self._total_generated = 0
        self._generation_history: deque = deque(maxlen=200)
        self._adversarial_blocked = 0
        self._current_trajectory_role_ids = []

        if self.strategy == SimulationStrategy.ADVERSARIAL and not self.debug:
            import warnings
            warnings.warn(
                "Adversarial strategy requires debug=True. "
                "Falling back to MISSION_GUIDED.",
                UserWarning, stacklevel=2,
            )
            self.strategy = SimulationStrategy.MISSION_GUIDED

    def _register_default_v15_entities(self) -> None:
        """Register initial set of default entities and their potential roles."""
        # Emergency beacon (highly aligned to mission)
        beacon_roles = [
            LatentRole(
                role_id="signal_transmitter",
                label="Emergency Beacon",
                embedding=self.mission_dir.copy(),
                material_properties={"conductive": True},
                safety_rating=0.95
            ),
            LatentRole(
                role_id="projectile",
                label="Weighted Throwing Object",
                embedding=np.roll(self.mission_dir, 1),
                material_properties={"heavy": True},
                safety_rating=0.8
            )
        ]
        
        # Stick / Plank
        stick_roles = [
            LatentRole(
                role_id="lever",
                label="Long Stick",
                embedding=np.roll(self.mission_dir, 2),
                material_properties={"flexible": True},
                safety_rating=0.85
            ),
            LatentRole(
                role_id="barrier",
                label="Wooden Plank",
                embedding=np.roll(self.mission_dir, 3),
                material_properties={"load_bearing": True},
                safety_rating=0.9
            )
        ]
        
        # Glass cup
        cup_roles = [
            LatentRole(
                role_id="liquid_container",
                label="Water Holder",
                embedding=np.roll(self.mission_dir, 4),
                material_properties={"water_tight": True},
                safety_rating=0.9
            ),
            LatentRole(
                role_id="load_bearing_support",
                label="Glass Pillar",
                embedding=np.roll(self.mission_dir, 5),
                material_properties={"load_bearing": True, "fragile": True},
                safety_rating=0.1  # Pruned due to safety < 0.2
            )
        ]
        
        self.potential_entities["improvised_beacon"] = beacon_roles
        self.potential_entities["structural_support"] = stick_roles
        self.potential_entities["glass_cup"] = cup_roles

    def generate_worlds(self, current_state: np.ndarray,
                        n_worlds: Optional[int] = None,
                        horizon: Optional[int] = None,
                        evidence: Optional[List[Dict]] = None,
                        ) -> List[CounterfactualWorld]:
        n = n_worlds or self.n_worlds
        h = horizon or self.horizon
        worlds = []

        for _ in range(n):
            trajectory = self._generate_trajectory(current_state, h, evidence)
            world = self._build_world(trajectory)
            worlds.append(world)

        self._total_generated += len(worlds)
        self._generation_history.append({
            'n_worlds': len(worlds),
            'horizon': h,
            'strategy': self.strategy.value,
            'timestamp': time.time(),
        })

        return worlds

    def _generate_trajectory(self, start_state: np.ndarray,
                             horizon: int,
                             evidence: Optional[List[Dict]] = None) -> Trajectory:
        self._world_counter += 1
        traj_id = f"traj-{self._world_counter}"
        self._current_trajectory_role_ids = []
        steps = []
        state = start_state.copy()

        for k in range(horizon):
            action = self._select_action(state, k, evidence)
            next_state = self._simulate_dynamics(state, action, k)
            health = self._compute_health(next_state)
            drift = self._compute_drift(next_state)
            corruption = self._compute_corruption(next_state, k)

            step = TrajectoryStep(
                state=state.copy(),
                action=action,
                reward=0.0,
                health=health,
                mission_drift=drift,
                corruption=corruption,
                step_index=k,
            )
            steps.append(step)
            state = next_state

        return Trajectory(
            trajectory_id=traj_id,
            steps=steps,
            mission_vector=self.mission_dir.copy(),
            active_role_ids=self._current_trajectory_role_ids
        )

    def _select_action(self, state: np.ndarray, step: int,
                       evidence: Optional[List[Dict]] = None) -> np.ndarray:
        if self.adapter is not None:
            return self.adapter.sample_action(state, self.mission_dir)

        if self.semantic_engine:
            # Dynamic semantic expansion with progressive depth
            tier = "deep" if (self.debug or self.strategy == SimulationStrategy.HYBRID) else "medium"
            constraints = {"disallowed_properties": ["fragile"]}
            
            # 1. Expand manifolds
            rag = RelationalAffordanceGraph()
            expanded_manifolds = {}
            for ent_id, roles in self.potential_entities.items():
                manifold = self.semantic_engine.expand(
                    ent_id, roles, self.mission_dir, state, progressive_tier=tier, constraints=constraints
                )
                expanded_manifolds[ent_id] = manifold
                rag.register_entity(manifold)
                
            # 2. Test cross-entity combinations
            emergent_role = rag.combine(
                ["improvised_beacon", "structural_support"], 
                self.mission_dir, state, 
                feasibility_filter=self.semantic_engine.feasibility_filter,
                constraints=constraints
            )
            
            # 3. Pull action toward the best active role or emergent combination
            best_embedding = self.mission_dir.copy()
            if emergent_role:
                best_embedding = emergent_role.embedding
                self._current_trajectory_role_ids.append(emergent_role.role_id)
            else:
                best_score = -float('inf')
                best_role = None
                for manifold in expanded_manifolds.values():
                    for role in manifold.active_roles:
                        sc = role.score(self.mission_dir, state)
                        if sc > best_score:
                            best_score = sc
                            best_embedding = role.embedding
                            best_role = role
                if best_role:
                    self._current_trajectory_role_ids.append(best_role.role_id)
            
            noise = np.random.randn(self.action_dim) * self.mutation_noise
            pull = best_embedding * 0.4
            return noise + pull

        if self.strategy == SimulationStrategy.RANDOM_WALK:
            return np.random.randn(self.action_dim) * self.mutation_noise

        elif self.strategy == SimulationStrategy.MISSION_GUIDED:
            noise = np.random.randn(self.action_dim) * self.mutation_noise
            mission_pull = self.mission_dir * 0.3
            return noise + mission_pull

        elif self.strategy == SimulationStrategy.ADVERSARIAL:
            anti_mission = -self.mission_dir
            noise = np.random.randn(self.action_dim) * self.mutation_noise
            return anti_mission * 0.5 + noise

        else:
            noise = np.random.randn(self.action_dim) * self.mutation_noise
            mission_pull = self.mission_dir * 0.2
            return noise + mission_pull

    def _simulate_dynamics(self, state: np.ndarray,
                           action: np.ndarray, step: int) -> np.ndarray:
        noise = np.random.randn(self.state_dim) * 0.05

        if self.nonlinear_dynamics:
            logistic = state * (1.0 - state) * 4.0
            sinusoidal = np.sin(step * 0.5 + state) * 0.1
            decay = 0.99
            next_state = state * decay + action * 0.1 + logistic * 0.05 + sinusoidal + noise
        else:
            decay = 0.99
            next_state = state * decay + action * 0.1 + noise

        if self.multi_agent and step > 0 and step % 5 == 0:
            perturbation = np.random.randn(self.state_dim) * 0.08
            next_state = next_state + perturbation

        if step > 0 and step % 15 == 0:
            shock = np.random.randn(self.state_dim) * 0.15
            next_state = next_state + shock

        return np.clip(next_state, 0.0, 1.0)

    def _compute_health(self, state: np.ndarray) -> float:
        return float(np.clip(np.mean(state), 0.0, 1.0))

    def _compute_drift(self, state: np.ndarray) -> float:
        if self.mission_dir is None or len(state) < len(self.mission_dir):
            return 0.0
        state_dir = state[:len(self.mission_dir)]
        sn = np.linalg.norm(state_dir)
        if sn < 1e-9:
            return 1.0
        alignment = float(np.dot(state_dir / sn, self.mission_dir))
        return max(0.0, 1.0 - alignment)

    def _compute_corruption(self, state: np.ndarray, step: int) -> float:
        normalized = state / (np.sum(state) + 1e-9)
        entropy = -np.sum(normalized * np.log(normalized + 1e-9))
        max_entropy = np.log(len(state))
        if max_entropy > 0:
            return float(np.clip(entropy / max_entropy, 0.0, 1.0))
        return 0.0

    def _build_world(self, trajectory: Trajectory) -> CounterfactualWorld:
        self._world_counter += 1
        world_id = f"world-{self._world_counter}"

        alignment = 1.0 - trajectory.steps[-1].mission_drift if trajectory.steps else 1.0
        corruption = trajectory.steps[-1].corruption if trajectory.steps else 0.0
        survival = self._estimate_survival(trajectory)

        risk_profile = {
            'drift_risk': trajectory.cumulative_drift / max(trajectory.length, 1),
            'corruption_risk': trajectory.cumulative_corruption / max(trajectory.length, 1),
            'collapse_risk': max(0.0, 1.0 - survival),
        }

        return CounterfactualWorld(
            world_id=world_id,
            trajectory=trajectory,
            mission_alignment=alignment,
            corruption_level=corruption,
            survival_probability=survival,
            risk_profile=risk_profile,
        )

    def _estimate_survival(self, trajectory: Trajectory) -> float:
        if not trajectory.steps:
            return 1.0
        survival = 1.0
        for step in trajectory.steps:
            if step.health < 0.3:
                survival *= 0.7
            elif step.health < 0.5:
                survival *= 0.9
            if step.mission_drift > 0.5:
                survival *= 0.8
        return max(0.0, min(1.0, survival))

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_generated': self._total_generated,
            'strategy': self.strategy.value,
            'n_worlds': self.n_worlds,
            'horizon': self.horizon,
            'generation_history_length': len(self._generation_history),
        }


# ═══════════════════════════════════════════════════════════
# 4. EVOLUTIONARY ENGINE
# ═══════════════════════════════════════════════════════════

class EvolutionaryEngine:
    """
    Evolutionary cycle for trajectory optimization:

      Generate → Mutate → Merge → Prune → Repeat

    Inspired by natural selection:
      - Fitness = aggregate utility J(F_i)
      - Selection = top-K survival
      - Mutation = action perturbation
      - Merge = trajectory crossover
      - Pruning = Neti-Neti negative filtering
    """

    def __init__(self, evaluator: Optional[TrajectoryEvaluator] = None,
                 mutation_rate: float = 0.1,
                 crossover_rate: float = 0.3,
                 survival_rate: float = 0.5,
                 max_generations: int = 20,
                 population_size: int = 50):
        self.evaluator = evaluator or TrajectoryEvaluator()
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.survival_rate = survival_rate
        self.max_generations = max_generations
        self.population_size = population_size
        self._generation = 0
        self._total_mutations = 0
        self._total_crossovers = 0
        self._evolution_history: deque = deque(maxlen=200)

    def evolve(self, population: List[Trajectory],
               mission_dir: Optional[np.ndarray] = None,
               n_generations: Optional[int] = None) -> List[Trajectory]:
        n_gen = n_generations or self.max_generations
        current = list(population)

        self.evaluator.batch_evaluate(current)

        for gen in range(n_gen):
            self._generation += 1

            selected = self._selection(current)

            mutated = []
            for traj in selected:
                if np.random.random() < self.mutation_rate:
                    m = self._mutate(traj, mission_dir)
                    mutated.append(m)
                    self._total_mutations += 1
            selected.extend(mutated)

            merged = []
            for i in range(0, len(selected) - 1, 2):
                if np.random.random() < self.crossover_rate:
                    child = self._crossover(selected[i], selected[i + 1])
                    merged.append(child)
                    self._total_crossovers += 1
            selected.extend(merged)

            pruned = self._prune_viable(selected)
            current = pruned[:self.population_size]

            self.evaluator.batch_evaluate(current)

            fitness_values = [t.aggregate_utility for t in current]
            self._evolution_history.append({
                'generation': self._generation,
                'population_size': len(current),
                'avg_fitness': round(float(np.mean(fitness_values)), 4) if fitness_values else 0.0,
                'max_fitness': round(float(max(fitness_values)), 4) if fitness_values else 0.0,
                'mutations': self._total_mutations,
                'crossovers': self._total_crossovers,
            })

        return current

    def _selection(self, population: List[Trajectory]) -> List[Trajectory]:
        if not population:
            return []
        scored = [(t.aggregate_utility, t) for t in population]
        scored.sort(key=lambda x: x[0], reverse=True)
        n_survive = max(2, int(len(scored) * self.survival_rate))
        return [t for _, t in scored[:n_survive]]

    def _mutate(self, trajectory: Trajectory,
                mission_dir: Optional[np.ndarray] = None) -> Trajectory:
        new_steps = []
        for step in trajectory.steps:
            noise = np.random.randn(len(step.action)) * self.mutation_rate
            if mission_dir is not None and len(noise) >= len(mission_dir):
                noise[:len(mission_dir)] += mission_dir * 0.05
            new_action = np.clip(step.action + noise, -1.0, 1.0)
            new_steps.append(TrajectoryStep(
                state=step.state.copy(),
                action=new_action,
                reward=step.reward,
                health=step.health,
                mission_drift=step.mission_drift,
                corruption=step.corruption,
                step_index=step.step_index,
            ))

        child = Trajectory(
            trajectory_id=f"{trajectory.trajectory_id}-m{self._total_mutations}",
            steps=new_steps,
            mission_vector=trajectory.mission_vector.copy() if trajectory.mission_vector is not None else None,
            generation=trajectory.generation + 1,
            parent_ids=[trajectory.trajectory_id],
        )
        return child

    def _crossover(self, parent_a: Trajectory,
                   parent_b: Trajectory) -> Trajectory:
        if not parent_a.steps or not parent_b.steps:
            return parent_a

        cut_point = np.random.randint(1, min(len(parent_a.steps), len(parent_b.steps)))
        child_steps = []

        for i in range(max(len(parent_a.steps), len(parent_b.steps))):
            if i < cut_point and i < len(parent_a.steps):
                child_steps.append(parent_a.steps[i])
            elif i >= cut_point and i < len(parent_b.steps):
                child_steps.append(parent_b.steps[i])
            elif i < len(parent_a.steps):
                child_steps.append(parent_a.steps[i])
            else:
                child_steps.append(parent_b.steps[i])

        mv = parent_a.mission_vector if parent_a.mission_vector is not None else parent_b.mission_vector
        return Trajectory(
            trajectory_id=f"cross-{parent_a.trajectory_id}-{parent_b.trajectory_id}",
            steps=child_steps,
            mission_vector=mv.copy() if mv is not None else None,
            generation=max(parent_a.generation, parent_b.generation) + 1,
            parent_ids=[parent_a.trajectory_id, parent_b.trajectory_id],
        )

    def _prune_viable(self, population: List[Trajectory]) -> List[Trajectory]:
        viable = []
        for t in population:
            if not t.steps:
                continue
            final_health = t.steps[-1].health
            total_drift = sum(s.mission_drift for s in t.steps)
            avg_drift = total_drift / len(t.steps)

            if final_health >= 0.2 and avg_drift < 0.8:
                t.is_viable = True
                viable.append(t)
            else:
                t.is_viable = False
        return viable

    def get_statistics(self) -> Dict[str, Any]:
        recent = list(self._evolution_history)[-10:]
        avg_fit = (
            np.mean([h['avg_fitness'] for h in recent])
            if recent else 0.0
        )
        return {
            'total_generations': self._generation,
            'total_mutations': self._total_mutations,
            'total_crossovers': self._total_crossovers,
            'avg_fitness_recent': round(float(avg_fit), 4),
            'evolution_history_length': len(self._evolution_history),
        }
