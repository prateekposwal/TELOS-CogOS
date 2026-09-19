"""
TELOS Task — TELOS performs a real task (GridWorld navigation with obstacles + rewards)
and explains its decisions in English. Includes ASCII grid rendering and benchmark metrics.

Integrated optimizations:
    1. TokenBudgetManager  — Signal-weighted chat history truncation (replaces [-4:])
    2. ContextSummarizer   — Periodic Session Essence compression (every 5 cycles)
    3. KnowledgeIngestion  — Extracts conversation facts into persistent KnowledgeGraph

Run:  PYTHONPATH=. python3 telos_task.py
"""

import numpy as np
import logging
import json
import http.client
import time
import os
import random
import functools
from typing import Set, Dict, Tuple, Optional, List

logger = logging.getLogger('telos_task')

logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
    EvidenceProvenanceValidator,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR

# ─── New optimization imports ──────────────────────────────────────────────
from telos.core.attention.token_budget import TokenBudgetManager
from telos.core.context.summarizer import ContextSummarizer, SessionEssence
from telos.core.context.knowledge_ingestion import ConversationKnowledgeIngestion
from telos.core.session.agents_writer import AgentsWriter


CHECKPOINT_DIR = "/tmp/telos_checkpoints"
KNOWLEDGE_PATH = "/tmp/telos_knowledge.json"

OLLAMA = "/Applications/Ollama.app/Contents/Resources/ollama"
OLLAMA_MODEL = "phi3:mini"

GOAL = np.array([4, 4])

# Canonical Layer-3 mission declaration for the GridWorld kernel. ONE source
# (Λ6.7): producer.py and cli.py import these; the pipeline seeds its
# MissionPortfolio from them so F(I) Layer 3 is genuinely evaluated.
MISSION_NAME = "navigate_to_goal"
MISSION_DESCRIPTION = "Navigate the GridWorld agent to the goal cell."

# ─── P0: Obstacles + Rewards + Terrain ──────────────────────────────────────────
DEFAULT_BLOCKED: Set[Tuple[int, int]] = {(1, 1), (2, 2), (3, 1)}
DEFAULT_REWARDS: Dict[Tuple[int, int], float] = {(0, 4): 10.0, (4, 0): 5.0, (2, 4): 3.0, (4, 2): 2.0}
GRID_SIZE = 5

# ─── Legal-motion planner (single canonical source) ───────────────────────────
# GridSim.transition can only route CARDINAL moves; diagonal/fractional vectors
# leave the agent stuck at the origin while simulated futures keep predicting
# movement — an inflated predicted-vs-observed gap (MD) the governor then reads
# as failure (BLOCK/DEFER -> action_taken=null forever). Every action the
# pipeline emits must be a legal cardinal step or an honest no-op. Both
# GridSim.simulate (futures) and GridAdpt.intent_to_action (execution) derive
# from these helpers so the model and the executor can never disagree about
# what is reachable (honesty axiom: no impossible trajectories).

# Memoization: the grid, blocked set and goal are STATIC per process
# (blocked is assigned once in __init__; terrain shifts mutate TERRAIN costs
# only and never blocked cells or the goal; GOAL/GRID_SIZE are module
# constants). A* is therefore a pure function of (start, goal, blocked,
# grid_size): the lru cache below is the identity function on those exact
# inputs, so determinism is UNCHANGED — the cache can never return a step a
# fresh search would not. A (future) blocked-set mutation invalidates by key,
# never by flush. The fallback vector stays out of the cache key (it only
# selects the return value on None).
_ASTAR_CACHE_MAXSIZE = 256


@functools.lru_cache(maxsize=_ASTAR_CACHE_MAXSIZE)
def _astar_first_step(start, goal, blocked, grid_size):
    """Cached A* first cardinal step; None when start IS the goal or no
    legal path exists. Pure: every input is hashable and the search body
    is the canonical one (same tie-break, same result). Callers map None
    to their honest no-op fallback.

    Args:
        start: (x, y) cardinal cell coordinate.
        goal: (x, y) target coordinate.
        blocked: tuple of blocked (x, y) coordinates (canonicalized).
        grid_size: square grid side length (bounds the search).

    Returns:
        (dx, dy) first-step delta tuple, or None when immovable.
    """
    import heapq
    gx, gy = goal
    blocked_set = set(blocked)
    if start == (gx, gy):
        return None

    def manhattan(cell):
        return abs(cell[0] - gx) + abs(cell[1] - gy)

    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))  # deterministic order
    counter = 0
    heap = [(manhattan(start), 0, counter, start)]
    counter += 1
    g_score = {start: 0}
    came_from = {start: None}
    closed = set()
    while heap:
        f, g, _, cell = heapq.heappop(heap)
        if cell in closed:
            continue
        closed.add(cell)
        if cell == (gx, gy):
            node = cell
            while came_from[node] is not None and came_from[node] != start:
                node = came_from[node]
            return (node[0] - start[0], node[1] - start[1])
        for dx, dy in neighbors:
            ncell = (cell[0] + dx, cell[1] + dy)
            if not (0 <= ncell[0] < grid_size and 0 <= ncell[1] < grid_size):
                continue
            if ncell in blocked_set:
                continue
            ng = g + 1
            if ng < g_score.get(ncell, float('inf')):
                g_score[ncell] = ng
                came_from[ncell] = cell
                heapq.heappush(heap, (ng + manhattan(ncell), ng, counter, ncell))
                counter += 1
    return None  # no legal path - honest no-op


def legal_goal_step(state, blocked, goal, grid_size, fallback):
    """First cardinal step of the shortest legal path toward `goal` (A*).

    Deterministic (and memoized per (start, goal, blocked, grid_size)):
    neighbors are cardinal-only, heuristic is Manhattan, ties break by
    push-order counter so the same state always returns the same step.
    Returns `fallback` (no move) when start IS the goal or no legal path
    exists (genuinely immovable - the honest no-op). The cache key is
    canonicalized (sorted blocked tuples) so a re-ordered blocked iterable
    still hits; a CHANGED blocked set is a new key -> fresh search.

    Args:
        state: current position (N-vector of floats).
        blocked: iterable of blocked cell coordinates.
        goal: the target coordinate.
        grid_size: square grid side length (bounds the search).
        fallback: the action vector returned when no legal path exists.
    """
    start = (int(round(state[0])), int(round(state[1])))
    gx, gy = int(round(goal[0])), int(round(goal[1]))
    if start == (gx, gy):
        return fallback
    blocked_frozen = tuple(sorted(tuple(b) for b in blocked))
    step = _astar_first_step(start, (gx, gy), blocked_frozen, grid_size)
    if step is None:
        return fallback
    return np.array([step[0], step[1]], dtype=float)


@functools.lru_cache(maxsize=64)
def _legal_cardinal_candidates(start, blocked, grid_size):
    """Legal cardinal neighbor deltas of `start`, deterministic push order.

    Args:
        start: (x, y) cardinal cell coordinate.
        blocked: tuple of blocked (x, y) coordinates (canonicalized).
        grid_size: square grid side length (bounds the search).

    Returns:
        Tuple of legal (dx, dy) neighbor deltas in deterministic order.
    """
    out = []
    blocked_set = set(blocked)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nc = (start[0] + dx, start[1] + dy)
        if not (0 <= nc[0] < grid_size and 0 <= nc[1] < grid_size):
            continue
        if nc in blocked_set:
            continue
        out.append((dx, dy))
    return tuple(out)


def legal_cardinal_action(state, blocked, goal, grid_size, fallback,
                          preferred=None):
    """Best LEGAL cardinal move toward `preferred` (or the goal).

    `preferred` may be any vector (diagonal/fractional, e.g. a blended
    inquiry vector). Returns the legal cardinal step whose direction best
    matches it (highest dot product, minimum 0.3 agreement), or the A*
    step toward the goal when no preferred vector is given. Falls back to
    `fallback` only when no legal move exists at all (honest no-op).

    Args:
        state: current position (N-vector of floats).
        blocked: iterable of blocked cell coordinates.
        goal: the target coordinate.
        grid_size: square grid side length (bounds the search).
        fallback: the action vector returned when no legal move exists.
        preferred: optional preferred (possibly diagonal) action vector.
    """
    start = (int(round(state[0])), int(round(state[1])))
    blocked_frozen = tuple(sorted(tuple(b) for b in blocked))
    candidate_steps = _legal_cardinal_candidates(start, blocked_frozen, grid_size)
    if not candidate_steps:
        return fallback
    if preferred is not None and float(np.linalg.norm(preferred)) > 0:
        pref = np.asarray(preferred, dtype=float)
        pref = pref / float(np.linalg.norm(pref))
        best = max(
            (np.array([dx, dy], dtype=float) for dx, dy in candidate_steps),
            key=lambda c: float(np.dot(c, pref)),
        )
        if float(np.dot(best, pref)) > 0.3:
            return best
    return legal_goal_step(state, blocked, goal, grid_size, fallback)


# Terrain types: each cell gets a terrain biome that affects movement cost
# 'plains' = normal, 'forest' = slow, 'water' = slowest, 'desert' = sandy, 'mountain' = blocked-like
TERRAIN: Dict[Tuple[int, int], str] = {
    (0, 0): 'plains', (1, 0): 'plains', (2, 0): 'forest', (3, 0): 'plains', (4, 0): 'desert',
    (0, 1): 'plains', (1, 1): 'blocked', (2, 1): 'plains', (3, 1): 'blocked', (4, 1): 'forest',
    (0, 2): 'water', (1, 2): 'plains', (2, 2): 'blocked', (3, 2): 'desert', (4, 2): 'plains',
    (0, 3): 'plains', (1, 3): 'forest', (2, 3): 'plains', (3, 3): 'plains', (4, 3): 'mountain',
    (0, 4): 'desert', (1, 4): 'plains', (2, 4): 'plains', (3, 4): 'forest', (4, 4): 'plains',
}

TERRAIN_COST = {'plains': 1.0, 'forest': 2.0, 'water': 3.0, 'desert': 1.5, 'mountain': 4.0, 'blocked': 99.0}

TERRAIN_EMOJI = {
    'plains': '🌿', 'forest': '🌲', 'water': '🌊',
    'desert': '🏜️', 'mountain': '⛰️', 'blocked': '🧱',
}


def ollama_chat(messages: list, cycle: int = 0) -> str:
    """Send a chat request to Ollama with retry logic.

    Retries up to 3 times with a 2-second delay between attempts.
    If Ollama is unavailable after all retries, returns a fallback response.

    Args:
        messages: the conversation messages to send to Ollama.
        cycle: the current cycle index (used in the fallback response).
    """
    max_retries = 3
    retry_delay = 2.0
    last_error = None

    for attempt in range(max_retries):
        try:
            conn = http.client.HTTPConnection("localhost", 11434, timeout=int(os.environ.get("TELOS_OLLAMA_TIMEOUT", "30")))
            payload = json.dumps({"model": OLLAMA_MODEL, "messages": messages, "stream": False})
            conn.request("POST", "/api/chat", body=payload, headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            return data.get("message", {}).get("content", "")
        except (ConnectionRefusedError, http.client.HTTPException, OSError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning("Ollama connection failed (attempt %d/%d): %s", attempt + 1, max_retries, e)
                time.sleep(retry_delay)
            else:
                logger.warning(
                    "Ollama unavailable after %d retries: %s. Using fallback response.",
                    max_retries, last_error,
                )

    # Fallback response when Ollama is unavailable
    fallback = "TELOS [cycle %d]: Processing complete. No LLM available for explanation." % cycle
    return fallback


def prime_skill_library(experience_mgr, pipeline, checkpoint_dir: str, cycles: int = 5) -> int:
    """Prime the skill library on startup by indexing recent decision traces.

    Loads the latest checkpoint, extracts recent decision traces,
    and runs them through experience_mgr.observe() to build initial skills.

    Args:
        experience_mgr: the ExperienceManager that indexes skills.
        pipeline: the running pipeline (for observation context).
        checkpoint_dir: directory holding decision checkpoints.
        cycles: how many recent checkpoints to index.

    Returns:
        Number of skills indexed.
    """
    indexed = 0
    
    # Step 1: Use index_recent to warm up from checkpoints
    if os.path.isdir(checkpoint_dir):
        indexed = experience_mgr.index_recent(checkpoint_dir, cycles=cycles)
        logger.info("prime_skill_library: indexed %d skills from checkpoints", indexed)
    else:
        logger.info("prime_skill_library: no checkpoint dir at %s, skipping", checkpoint_dir)
    
    # Step 2: Create synthetic initial skills from pipeline's first result if available
    # (The pipeline hasn't executed yet at startup, so this is a cold start)
    return indexed


class GridSim(DomainSimulator):
    def __init__(self, blocked: Optional[Set[Tuple[int, int]]] = None,
                 rewards: Optional[Dict[Tuple[int, int], float]] = None,
                 random_seed: Optional[int] = None):
        self.blocked = blocked or DEFAULT_BLOCKED
        self.rewards = rewards or DEFAULT_REWARDS
        self.position = np.array([0.0, 0.0])
        self._cycle: int = 0
        self.terrain_changes: List[Dict] = []
        # RNG isolation (audit Item 3): maybe_shift_terrain is a production
        # hot path — the dashboard producer calls it EVERY cycle — so it must
        # own a private random.Random, never the global `random` module (whose
        # state depends on whatever imported it first; locked by
        # tests/core/test_gridsim_rng_isolation.py). random_seed=None yields a
        # private OS-entropy instance (isolated, live-nondeterministic);
        # a fixed seed makes terrain shifts reproducible (the regression-test
        # and harness pattern for the other engines).
        self._rng = random.Random(random_seed)
        # World extent exposed to the act-phase catastrophe gate (Item 1):
        # the state space is [0, world_extent-1]², so the max legitimate
        # horizon mission-drift is its corner-to-corner diameter (≈5.66 for
        # GRID_SIZE=5) — the act ceiling is scaled from this instead of a
        # fixed absolute bar that sat below the grid's own maximum.
        self.world_extent: int = GRID_SIZE

    def initialize(self): pass
    def cleanup(self): pass

    @property
    def visible_cells(self) -> Set[Tuple[int, int]]:
        """Fog of War: cells within Manhattan distance <= 2 of TELOS."""
        pos = (int(round(self.position[0])), int(round(self.position[1])))
        return {(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)
                if abs(x - pos[0]) + abs(y - pos[1]) <= 2}

    def maybe_shift_terrain(self) -> List[Dict]:
        """Dynamic Terrain: every 3 cycles, shift 2 random cells."""
        self._cycle += 1
        self.terrain_changes = []
        if self._cycle % 3 != 0:
            return []
        cells = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]
        # Don't change blocked, goal, or cells with >= 4 cost
        candidates = [(x, y) for x, y in cells
                      if (x, y) not in self.blocked and (x, y) != (4, 4)]
        if len(candidates) < 2:
            return []
        chosen = self._rng.sample(candidates, 2)
        terrain_types = ['plains', 'forest', 'water', 'desert', 'mountain']
        changes = []
        for cx, cy in chosen:
            old = TERRAIN.get((cx, cy), 'plains')
            new = self._rng.choice([t for t in terrain_types if t != old])
            TERRAIN[(cx, cy)] = new
            changes.append({'x': cx, 'y': cy, 'old': old, 'new': new})
            logger.info(f"🌋 Cell ({cx},{cy}) changed: {old} → {new}")
        self.terrain_changes = changes
        return changes

    def legal_transitions(self, s):
        moves = [np.array([1, 0]), np.array([-1, 0]), np.array([0, 1]), np.array([0, -1])]
        legal = []
        for a in moves:
            n = np.clip(s + a, 0, GRID_SIZE - 1)
            key = (int(round(n[0])), int(round(n[1])))
            if key not in self.blocked:
                legal.append(a)
        return legal if legal else [np.array([0, 0])]  # no-op if trapped

    def transition(self, s, a):
        new_pos = np.clip(s + a, 0, GRID_SIZE - 1)
        key = (int(round(new_pos[0])), int(round(new_pos[1])))
        if key in self.blocked:
            return s  # blocked: stay in place
        return new_pos

    def simulate(self, s, h):
        futures = []
        pos = s.copy()
        for _ in range(h):
            # Only LEGAL cardinal steps are ever predicted: a future that the
            # real transition cannot route is a hallucination, and a model that
            # hallucinates future positions inflates mission drift until the
            # governor permanently blocks action (the no-action stagnation
            # trap). The model and the executor now agree on what is reachable.
            step = legal_cardinal_action(
                pos, self.blocked, GOAL, GRID_SIZE,
                fallback=np.array([0.0, 0.0]),
                preferred=GOAL - pos,
            )
            pos = np.clip(pos + step, 0, GRID_SIZE - 1)
            futures.append(World(state=pos.copy()))
        return futures

    def get_facts(self, s):
        dist = float(np.linalg.norm(GOAL - s))
        key = (int(round(s[0])), int(round(s[1])))
        self.position = s.copy()  # Track position for visible_cells
        visible = self.visible_cells
        # Fog of War: only return data for visible cells
        visible_terrain = {str(k): TERRAIN.get(k, 'unknown') for k in visible}
        visible_blocked = [list(b) for b in self.blocked if tuple(b) in visible]
        visible_rewards = {str(k): v for k, v in self.rewards.items() if k in visible}
        terrain_here = TERRAIN.get(key, 'unknown')
        cost = TERRAIN_COST.get(terrain_here, 1.0) if terrain_here != 'unknown' else 1.0
        reward = self.rewards.get(key, 0.0) if key in visible else 0.0
        near_reward = max(
            (v for k, v in self.rewards.items()
             if k in visible and np.linalg.norm(np.array(k) - s) < 2.0),
            default=0.0,
        )
        return DomainFacts(
            state=s.copy(),
            resources={"distance": dist, "reward_near": near_reward, "terrain_cost": cost},
            constraints=["obstacle_near"] if any(
                np.linalg.norm(np.array(b) - s) < 1.5 for b in self.blocked if tuple(b) in visible
            ) else [],
            events=["on_reward"] if reward > 0 else [],
            metrics={"distance": dist, "uncertainty": 0.1, "reward": reward, "terrain_cost": cost},
            metadata={
                "position": s.tolist(), "goal": GOAL.tolist(),
                "blocked": [list(b) for b in self.blocked],
                "rewards": {str(k): v for k, v in self.rewards.items()},
                "terrain": {str(k): v for k, v in TERRAIN.items()},
                "current_terrain": terrain_here,
                "visible_terrain": visible_terrain,
                "visible_blocked": visible_blocked,
                "visible_rewards": visible_rewards,
                "causal_edges": [
                    "position -> distance",
                    "action -> position",
                    "position -> nearby_obstacles",
                    "position -> terrain_type",
                ],
            },
        )

    def terminal(self, s):
        return bool(np.linalg.norm(GOAL - s) < 0.5)

    def evaluate(self, s):
        dist = np.linalg.norm(GOAL - s)
        key = (int(round(s[0])), int(round(s[1])))
        reward = self.rewards.get(key, 0.0)
        return EvaluationReport(
            objectives={"proximity": -float(dist), "reward": reward},
            risks=0.0,
        )

    name = "gridworld"
    state_dim = 2

    def world_spec(self):
        from telos.core.contracts.domain_model import WorldSpec
        return WorldSpec(
            name=self.name,
            state_dim=self.state_dim,
            action_dim=2,
            objectives=["proximity", "reward"],
            constraints=["obstacle_near", "blocked"],
            observability="partial",
            capabilities=["transition", "simulate", "terrain_shift"],
        )


class GridAdpt(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x

    def intent_to_action(self, intent, state, md):
        # The adapter is the executor: it must never emit a vector the real
        # transition cannot route. Diagonal/fractional intents (blended
        # inquiry, curiosity random-walks) are projected onto the best LEGAL
        # cardinal move; goal intents use the A* first step. An honest no-op
        # is returned only when the agent is genuinely immovable.
        preferred = intent.params.get("action_vector", None)
        if preferred is not None:
            preferred = np.asarray(preferred, dtype=float)
        blocked = getattr(getattr(intent, "metadata", None), "blocked", None)
        if blocked is None and isinstance(intent.params.get("blocked"), (set, list)):
            blocked = intent.params.get("blocked")
        return legal_cardinal_action(
            state, blocked if blocked is not None else DEFAULT_BLOCKED,
            GOAL, GRID_SIZE,
            fallback=np.array([0.0, 0.0]),
            preferred=preferred,
        )

    @property
    def name(self): return "gridworld"

    @property
    def state_dim(self): return 2



# ─── GridAgent: Second Agent (upgrade 5) ──────────────────────────────────────

class GridAgent:
    """Simple agent that moves toward nearest unvisited reward."""

    def __init__(self, start_pos=(4, 0), blocked=None, rewards=None):
        self.position = np.array(start_pos, dtype=float)
        self.blocked = blocked or DEFAULT_BLOCKED
        self.rewards = rewards or DEFAULT_REWARDS
        self.visited = set()
        self.visited.add(start_pos)
        self.total_reward = 0.0
        self.goal_reached = False

    def decide_action(self) -> np.ndarray:
        """Move toward nearest unvisited reward."""
        pos_key = (int(round(self.position[0])), int(round(self.position[1])))

        # Find nearest unvisited reward
        best_dist = float('inf')
        best_target = None
        for r_pos, r_val in self.rewards.items():
            if r_pos in self.visited:
                continue
            d = np.linalg.norm(np.array(r_pos) - self.position)
            if d < best_dist:
                best_dist = d
                best_target = r_pos

        if best_target is None:
            best_target = (4, 4)  # Move toward goal

        # Pick best cardinal direction toward target
        diff = np.array(best_target) - self.position
        if np.linalg.norm(diff) < 0.5:
            return np.array([0, 0])

        moves = [np.array([1, 0]), np.array([-1, 0]), np.array([0, 1]), np.array([0, -1])]
        best_move = None
        best_score = float('inf')

        for a in moves:
            n = np.clip(self.position + a, 0, GRID_SIZE - 1)
            key = (int(round(n[0])), int(round(n[1])))
            if key in self.blocked:
                continue
            new_dist = np.linalg.norm(np.array(best_target) - n)
            if new_dist < best_score:
                best_score = new_dist
                best_move = a

        return best_move if best_move is not None else np.array([0, 0])

    def step(self) -> Tuple[int, int]:
        """Execute one step: decide action and move."""
        action = self.decide_action()
        new_pos = np.clip(self.position + action, 0, GRID_SIZE - 1)
        key = (int(round(new_pos[0])), int(round(new_pos[1])))
        if key not in self.blocked:
            self.position = new_pos
        self.visited.add(key)
        if key == (4, 4):
            self.goal_reached = True
        return key


# ─── P1: ASCII Grid Rendering ───────────────────────────────────────────────

def render_grid(state: np.ndarray, blocked: Set[Tuple[int, int]],
                rewards: Dict[Tuple[int, int], float],
                agent2_pos: Optional[np.ndarray] = None) -> str:
    """Render a 5x5 grid with terrain, TELOS, goal, obstacles, rewards, and second agent.

    Args:
        state: current agent position.
        blocked: set of blocked cell coordinates.
        rewards: map of reward cell coordinates to reward values.
        agent2_pos: optional second-agent position to render.
    """
    lines = ["    0  1  2  3  4"]
    for y in range(GRID_SIZE):
        row = [f"  {y} "]
        for x in range(GRID_SIZE):
            pos = (x, y)
            terrain_emoji = TERRAIN_EMOJI.get(TERRAIN.get(pos, 'plains'), '·')
            if int(round(state[0])) == x and int(round(state[1])) == y:
                row.append("🔴T")
            elif agent2_pos is not None and int(round(agent2_pos[0])) == x and int(round(agent2_pos[1])) == y:
                row.append("🔵A")
            elif (GOAL == np.array([x, y])).all():
                row.append("🟩G")
            elif pos in blocked:
                row.append("🧱 ")
            elif pos in rewards and rewards[pos] > 0:
                row.append("⭐ ")
            else:
                row.append(terrain_emoji)
            row.append(" ")
        lines.append("".join(row))
    return "\n".join(lines)

# ─── P2: Benchmark Metrics ──────────────────────────────────────────────────

class BenchmarkMetrics:
    """Tracks and reports pipeline performance metrics across a session.
    
    Includes time pressure scoring (upgrade 4).
    """
    def __init__(self):
        self.steps: int = 0
        self.blocks: int = 0
        self.di_history: list = []
        self.alternatives_history: list = []
        self.worlds_history: list = []
        self.goal_reached: bool = False
        self.start_time: float = time.time()
        self.recovery_cycles: int = 0
        self.last_blocked: bool = False
        # Time pressure (upgrade 4)
        self.total_score: float = 100.0
        self.time_cost: float = 0.0
        self.reward_collected: float = 0.0
        self.goal_bonus: float = 0.0

    def record_step(self, result, trace, reward_collected=0.0):
        self.steps += 1
        if trace:
            self.di_history.append(trace.decision_integrity)
            self.alternatives_history.append(len(getattr(trace, 'strategic_options', [])))
            self.worlds_history.append(trace.worlds_simulated)
        if result.council_blocked or result.firewall_blocked:
            self.blocks += 1
            if not self.last_blocked:
                self.recovery_cycles += 1
            self.last_blocked = True
        else:
            self.last_blocked = False
        # Time pressure: each cycle costs 1 point
        self.time_cost += 1.0
        self.total_score -= 1.0
        # Add collected rewards
        if reward_collected > 0:
            self.reward_collected += reward_collected
            self.total_score += reward_collected

    def mark_goal(self):
        self.goal_reached = True
        self.goal_bonus = 50.0
        self.total_score += 50.0

    def report(self) -> str:
        elapsed = time.time() - self.start_time
        di_mean = np.mean(self.di_history) if self.di_history else 0.0
        di_std = np.std(self.di_history) if len(self.di_history) > 1 else 0.0
        alt_mean = np.mean(self.alternatives_history) if self.alternatives_history else 0.0
        block_rate = self.blocks / max(self.steps, 1) * 100

        lines = [
            "\n" + "=" * 50,
            "📊  BENCHMARK REPORT",
            "=" * 50,
            f"  Goal Reached:      {'✅ Yes' if self.goal_reached else '❌ No'}",
            f"  Total Steps:       {self.steps}",
            f"  Council Blocks:    {self.blocks} ({block_rate:.1f}%)",
            f"  Recovery Events:   {self.recovery_cycles}",
            f"  Mean DI:           {di_mean:.3f} ± {di_std:.3f}",
            f"  Mean Alternatives: {alt_mean:.1f} per cycle",
            f"  Total Worlds Sim:  {sum(self.worlds_history)}",
            f"  Elapsed:           {elapsed:.1f}s",
            f"  Final Score:       {self.total_score:.1f} (time cost: {self.time_cost:.0f}, rewards: {self.reward_collected:.1f}, goal bonus: +{self.goal_bonus:.0f})",
            "=" * 50,
        ]
        return "\n".join(lines)

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    sim = GridSim()
    print(f"🧱 Obstacles at: {sorted(DEFAULT_BLOCKED)}")
    print(f"⭐ Rewards at:    {dict((str(k), v) for k, v in DEFAULT_REWARDS.items())}")

    pipeline = TelosV14Pipeline(PipelineConfig(
        adapter=GridAdpt(), simulator=sim,
        compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
        mission_name=MISSION_NAME, mission_description=MISSION_DESCRIPTION,
        checkpoint_path=CHECKPOINT_DIR,
        knowledge_path=KNOWLEDGE_PATH,
        ledger_path="/tmp/telos_ledger.json",
        identity_path="/tmp/telos_identity.json",
        pattern_path="/tmp/telos_patterns.json",
        deterministic_seed=42,  # Ensures reproducible pipeline runs
        verified_learning=True,
        learning_curriculum=True,
    ))
    skill_lib = SkillLibrary()
    experience_mgr = ExperienceManager(
        skill_lib,
        ExperienceConfig(utility_threshold=0.1, index_interval=1,
                         verified_acquisition=True),
    )
    # Warm up the skill library from recent checkpoints
    if os.path.isdir(CHECKPOINT_DIR):
        indexed = experience_mgr.index_recent(CHECKPOINT_DIR, cycles=5)
        if indexed > 0:
            print(f"  🧠 Warmed up skill library: {indexed} skills from checkpoints")
    else:
        print(f"  📂 No checkpoint dir at {CHECKPOINT_DIR}, starting fresh")
    
    # Prime the learning loop on startup
    primed = prime_skill_library(experience_mgr, pipeline, CHECKPOINT_DIR, cycles=5)
    if primed > 0:
        print(f"  🧪 Primed skill library: {primed} skills indexed from traces")
    sim_engine = CounterfactualEngine(sim)
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_stream(InquiryStream(skill_lib))
    pipeline.register_stream(TheoryStream(
        skill_lib,
        theory_builder=getattr(pipeline, '_theory_builder', None),
        curriculum=getattr(pipeline, 'curriculum', None),
    ))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    memory_advisor = MemoryAdvisor(skill_lib)
    pipeline.register_validator(memory_advisor)
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))
    pipeline.register_validator(EvidenceProvenanceValidator())

    # Wire up MemoryAdvisor to infrastructure after pipeline init
    if hasattr(pipeline, 'infra_manager') and pipeline.infra_manager:
        im = pipeline.infra_manager
        memory_advisor.connect(
            failure_ledger=getattr(im, 'failures', None),
            knowledge_graph=im.knowledge if hasattr(im, 'knowledge') else None,
        )

    # ─── Initialize optimization components ──────────────────────────────────
    token_budget = TokenBudgetManager(token_budget=2048, keep_last_n=2)
    summarizer = ContextSummarizer(ollama_chat_fn=ollama_chat, summary_interval=5)
    agents_writer = AgentsWriter("AGENTS.md")

    kg_ingestion = ConversationKnowledgeIngestion(
        search_fn=lambda domain, top_k=5: pipeline.infra_manager.knowledge.search(
            domain=domain, top_k=top_k, min_outcome=0.51
        ),
        consult_fn=lambda domain, cycle: pipeline.infra_manager.knowledge_manager.consult_knowledge(
            domain=domain, cycle=cycle
        ),
        record_fn=pipeline.infra_manager.knowledge.record,
    )

    metrics = BenchmarkMetrics()

    # ─── Initialize second agent (upgrade 5) ───────────────────────────────
    agent2 = GridAgent(start_pos=(4, 0), blocked=sim.blocked, rewards=sim.rewards)
    print(f"🔵 Second Agent starts at (4,0) — moves toward nearest unvisited reward")


    print("\nTELOS is performing a task: Navigate from (0,0) to (4,4)")
    print("Avoid obstacles (█), collect rewards (⭐), reach the goal (G).")
    print("TELOS now remembers who you are across cycles.")
    print("Optimizations: TokenBudget ℹ️ | ContextSummarizer 📝 | KG Ingestion 🧠\n")

    USER_NAME = "Prateek"
    state = np.array([0., 0.])
    step_count = 0
    chat_history: List[Dict] = []
    trace_history: Dict[int, Dict] = {}  # msg_index → trace dict for token scoring

    while True:
        profile = pipeline.ledger.get_user_profile(USER_NAME)
        rel = profile.relationship_summary if profile else "unknown"
        trust = profile.trust_level if profile else 0.0
        known = f"[known: {rel}, trust: {trust:.2f}]" if profile and profile.total_interactions > 0 else "[new user]"

        # ─── Pre-cycle: Query KG for past context ────────────────────────────
        kg_context = kg_ingestion.pre_cycle(USER_NAME, step_count)

        # Render the grid
        grid = render_grid(state, sim.blocked, sim.rewards, agent2.position)
        print(grid)

        try:
            user = input(f"[Step {step_count}] {known} > ")
        except EOFError:
            break
        if user.lower() in ("quit", "exit"):
            break

        # ─── Execute pipeline cycle ──────────────────────────────────────────
        result = pipeline.execute(state, user_name=USER_NAME)
        experience_mgr.observe(result)
        trace = result.decision_trace
        # metrics.record_step now called after reward collection
        step_count += 1
        # Dynamic Terrain: shift 2 cells every 3 cycles (upgrade 1)
        terrain_changes = sim.maybe_shift_terrain()


        # Broadcast trace to live dashboard via WebSocket
        try:
            from telos.serve_dashboard import broadcast_trace_sync, websocket_clients
            if websocket_clients:
                trace_dict = trace.to_dict() if hasattr(trace, 'to_dict') else trace
                # Augment trace with dashboard extras (upgrades 1,4,5)
                if isinstance(trace_dict, dict):
                    trace_dict['agent2_pos'] = agent2.position.tolist()
                    trace_dict['agent2_reward'] = agent2.total_reward
                    trace_dict['score'] = metrics.total_score
                    trace_dict['terrain_changes'] = sim.terrain_changes
                broadcast_trace_sync(trace_dict)
        except (ImportError, Exception):
            pass

        intent = trace.selected_intent.intent_type if trace and trace.selected_intent else "none"
        status = "APPROVED" if not (result.firewall_blocked or result.council_blocked) else "BLOCKED"
        scores = [round(o.get("score", 0), 3) for o in trace.strategic_options[:3]] if trace else []
        dist = float(np.linalg.norm(GOAL - state))

        profile = pipeline.ledger.get_user_profile(USER_NAME)
        rel = profile.relationship_summary if profile else "unknown"

        reasoning = json.dumps({
            "position": state.tolist(), "goal": GOAL.tolist(),
            "distance_to_goal": round(dist, 2),
            "intent": intent, "council": status,
            "di": round(trace.decision_integrity, 3) if trace else 0,
            "worlds_simulated": trace.worlds_simulated if trace else 0,
            "top_futures": scores,
        })

        # ─── Build system prompt with KG context and session essence ──────────
        essence_block = summarizer.get_context_block()
        kg_summary = ""
        if kg_context.get("known_user"):
            prefs = kg_context.get("known_preferences", [])
            if prefs:
                kg_summary = f"Known preferences: {'; '.join(prefs[:3])}"

        system_prompt = (
            f"You are TELOS navigating from (0,0) to (4,4). "
            f"Obstacles at {sorted(DEFAULT_BLOCKED)}. "
            f"Rewards at {DEFAULT_REWARDS}. "
            f"Current state: {reasoning}. "
            f"Your relationship with the user is: {rel}. "
            f"{kg_summary} "
        )
        if essence_block.get("session_essence", {}).get("key_decisions"):
            essence = essence_block["session_essence"]
            system_prompt += (
                f"Session context: {len(essence.get('key_decisions', []))} past decisions, "
                f"mood trajectory: {essence.get('mood_trajectory', 'neutral')}. "
            )
        system_prompt += "Explain what you are doing in 1-2 sentences."

        # ─── Append user message ──────────────────────────────────────────────
        chat_history.append({"role": "user", "content": user})

        # Store trace data for token budget scoring
        trace_key = len(chat_history) - 1
        trace_history[trace_key] = TokenBudgetManager.make_trace(
            di=trace.decision_integrity if trace else 1.0,
            md=trace.mission_drift if trace else 0.0,
            blocked=result.council_blocked or result.firewall_blocked,
            escalated=trace.escalation_requested if trace else False,
        )

        # ─── Use TokenBudgetManager instead of naive [-4:] ───────────────────
        optimized = token_budget.optimize(chat_history, trace_history)
        msgs = [{"role": "system", "content": system_prompt}] + optimized
        reply = ollama_chat(msgs, cycle=step_count)
        chat_history.append({"role": "assistant", "content": reply})

        print(f"\nTELOS: {reply}")
        print(f"  [{status}] DI={trace.decision_integrity:.3f} | {rel} (trust={profile.trust_level:.2f})")

        # ─── Post-cycle: feed the conversation turn into theory formation ────
        # The pipeline's execute() never sees the message/reply, so the
        # conversation path is bridged explicitly (Λ6.5 Theory Formation).
        try:
            conv_outcome = 1.0 - float(trace.mission_drift or 0.0) if trace else 0.5
            pipeline.observe_conversation_outcome(user, reply, outcome=conv_outcome)
        except Exception as e:
            print(f"  ⚠ observe_conversation skipped: {e}")

        # ─── Post-cycle: Knowledge Ingestion ─────────────────────────────────
        kg_ingestion.post_cycle(USER_NAME, step_count, result, chat_history)

        # ─── Post-cycle: Context Summarizer ──────────────────────────────────
        essence = summarizer.maybe_summarize(step_count, chat_history)
        if essence is not None:
            print(f"  📝 Session essence updated: {essence}")

        # ─── Post-cycle: Context Pressure → Auto-AGENTS.md Handoff ────────────
        pressure = agents_writer.detect_context_pressure(pipeline, step_count, chat_history)
        if pressure > 0.8:
            essence_block = summarizer.get_context_block()
            agents_writer.write_summary(
                pipeline=pipeline,
                cycle_count=step_count,
                chat_history=chat_history,
                session_essence=essence_block.get("session_essence"),
            )
            print(f"  📋 Session handoff written to AGENTS.md (pressure: {pressure:.1%})")

        if trace and trace.selected_action is not None and not result.firewall_blocked:
            state = sim.transition(state, trace.selected_action)

        # ─── Move second agent (upgrade 5) ────────────────────────────────────
        agent2_key = agent2.step()
        print(f"  🔵 Agent2 moves to ({agent2.position[0]:.0f},{agent2.position[1]:.0f})")

        # ─── Reward collection (upgrade 3, 5) ────────────────────────────────
        telos_key = (int(round(state[0])), int(round(state[1])))
        reward_collected = 0.0
        if telos_key in sim.rewards and sim.rewards[telos_key] > 0:
            # Check if both agents on same cell → split reward
            if telos_key == agent2_key:
                split_reward = sim.rewards[telos_key] / 2.0
                reward_collected = split_reward
                agent2.total_reward += split_reward
                print(f"  🤝 Both agents on {telos_key}: reward split! TELOS gets {split_reward:.1f}, Agent2 gets {split_reward:.1f}")
            else:
                reward_collected = sim.rewards[telos_key]
                print(f"  ⭐ TELOS collected reward at {telos_key}: +{reward_collected:.1f}!")
            # Remove collected reward
            sim.rewards[telos_key] = 0.0

        # Also check if agent2 collected a reward alone
        if agent2_key in sim.rewards and sim.rewards[agent2_key] > 0 and agent2_key != telos_key:
            agent2_reward = sim.rewards[agent2_key]
            agent2.total_reward += agent2_reward
            print(f"  🔵 Agent2 collected reward at {agent2_key}: +{agent2_reward:.1f}!")
            sim.rewards[agent2_key] = 0.0

        # ─── Time pressure score update (upgrade 4) ──────────────────────────
        metrics.record_step(result, trace, reward_collected=reward_collected)

        dist = np.linalg.norm(GOAL - state)
        print(f"  📊 Score: {metrics.total_score:.1f} (time cost: {metrics.time_cost:.0f}, rewards: {metrics.reward_collected:.1f})")
        if dist < 0.5:
            print(f"\n✅ GOAL REACHED in {step_count} steps!")
            print(render_grid(state, sim.blocked, sim.rewards, agent2.position))
            metrics.mark_goal()
            break

    print(metrics.report())

    # ─── Final knowledge summary ─────────────────────────────────────────────
    kg_summary = kg_ingestion.summarize_user_knowledge(USER_NAME)
    print(f"\n📚 Knowledge Graph knows {USER_NAME}:")
    print(f"  Preferences:  {len(kg_summary['known_preferences'])}")
    print(f"  Past Intents: {len(kg_summary['past_intents'])}")
    print(f"  Past Blockers:{len(kg_summary['past_blockers'])}")
    print(f"  Essences:     {summarizer.summary_count if hasattr(summarizer, 'summary_count') else len(summarizer.summaries)}")

    print(f"\nUser memory: {pipeline.ledger.known_users} known user(s)")
    for s in pipeline.ledger.get_known_user_summaries():
        print(f"  - {s['name']}: {s['relationship']} (trust={s['trust']})")
    print(f"ExperienceManager: {experience_mgr.stats['skills_indexed']} skills indexed")

    # ─── Final session handoff ──────────────────────────────────────────────
    essence_block = summarizer.get_context_block()
    agents_writer.write_summary(
        pipeline=pipeline,
        cycle_count=step_count,
        chat_history=chat_history,
        session_essence=essence_block.get("session_essence"),
    )
    print(f"📋 Final session handoff written to AGENTS.md")

    pipeline.shutdown()
    print(f"State saved to {CHECKPOINT_DIR}/ and {KNOWLEDGE_PATH}")


if __name__ == "__main__":
    main()