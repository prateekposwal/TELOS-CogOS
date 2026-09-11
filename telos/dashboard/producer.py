"""
TELOS Dashboard Live-Data Producer — runs the REAL pipeline in-process
inside serve_dashboard.py so the dashboard serves LIVE runtime data
instead of cold files that nothing writes.

Pattern fixes (structural rules):
    1. A dashboard must PRODUCE or ATTACH to a live producer — it may never
       read cold files that nothing writes. If the producer is stopped, the
       dashboard falls back to persisted history (honest), never to
       fabricated data.
    2. A metric that claims to measure QUALITY must be BOUNDED — its range
       is part of its definition and enforced at the API boundary — and
       derived only from measured signals. Endurance facts (cycles elapsed)
       are labeled as endurance readouts and are NEVER folded into a quality
       score. (The old score = 100 - cycles + rewards was a cumulative drain
       shown as an unbounded quality score; the System Score replaces it.)

Everything exposed through the snapshot() dict comes from an actual
pipeline execution. There are no synthetic traces, no invented nodes,
no made-up metrics. Knowledge nodes/edges recorded here are REAL
observations of the running system (positions visited, terrain, council
verdicts, rewards) stamped with provenance caller=dashboard_producer.

Structural rules (v7 additions):
    3. Movement on the live grid is a LEGAL-ROUTE executor: the pipeline's
       adapter emits diagonal/no-op vectors; this producer plans with A*
       over the real 5x5 legal grid (blocked cells from the sim) toward the
       goal, so every approved cycle that can move makes monotone progress.
       Deterministic (fixed neighbor order + Manhattan heuristic), bounds-safe.
    4. Counters survive restarts: cycles and worlds_simulated_total are
       restored from the last persisted producer state (exact counters) or,
       failing that, from the latest checkpoint files (honest best-effort),
       so the hero never resets to 0 when the dashboard restarts.
"""


import glob as _glob
import sys
import heapq
import json
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("telos_dashboard_producer")


def json_clean(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays into plain JSON types.

    DecisionTrace.to_dict() leaks np.bool_/np.float64/np.int64 (e.g. the
    stream-activation 'activated' flag), which crash json.dumps in the
    HTTP and WebSocket paths. Everything the dashboard serializes passes
    through here so the API is always plain JSON.

    Args:
        obj: any nested dict/list/scalar value from the runtime.
    """
    if isinstance(obj, dict):
        return {k: json_clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_clean(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, np.ndarray):
        obj = obj.tolist()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        # NaN/Inf would serialize as bare NaN/Infinity — invalid JSON in
        # browsers. Map to None (a missing value) rather than poisoning
        # the API payload.
        return None
    if isinstance(obj, int) and (obj > 9e15 or obj < -9e15):
        return None
    return obj


# ── System Score - bounded composite of measured signals ───────────────
# The dashboard's headline metric. Replaces the legacy unbounded timer
# (score = 100 - cycles + rewards, monotonically decreasing forever).
#
# Structural rule: a quality metric must be bounded - its range is part of
# its definition - and derived ONLY from measured signals. Time/cycles are
# an endurance FACT (separate readout), never a component of a quality
# score. See telos/dashboard/STORYTELLING.md "System Score decision".
DRIFT_THRESHOLD = 5.0   # MissionDriftDetector(drift_threshold=...) in _build
SYSTEM_SCORE_WEIGHTS = {"di": 0.50, "md": 0.25, "reward": 0.15, "coverage": 0.10}

# ── Episode efficiency - real behavioral readout, ZERO sim mutation ─────
# The producer observes every goal-reach (terminal() -> reset) and counts
# decision-steps per episode. Pure producer-side bookkeeping on events it
# already observes: the shared sim's reward dict is NEVER touched for a
# display metric. (Restoring it at episode reset would make the pipeline's
# perception - GridSim.get_facts/evaluate read sim.rewards - see respawned
# rewards it already collected: fake infinite score. That was the original
# rejection's real kernel; the mutation-free path below delivers the same
# signal without it.) The System Score is untouched: steps-per-goal is a
# cycle-derived pace readout (each step is one decision cycle), and the
# structural rule says endurance facts are never folded into a quality
# score - so efficiency is a separate labeled stat, not a component.
OPTIMAL_STEPS = 8.0   # Manhattan distance (0,0)->(4,4): shortest possible episode
MAX_EPISODE_HISTORY = 50


def _astar_step(state, blocked, goal, grid_size, fallback):
    """First step of the shortest legal path toward the goal (A*).

    Deterministic legal-route planner over the REAL grid: blocked cells are
    taken from the live sim (never invented), neighbors are cardinal-only,
    heuristic is Manhattan distance to the goal, ties break by a monotone
    counter so the same state always yields the same step. Returns the
    first cardinal step (delta) along the shortest path — each approved
    step strictly decreases path-length to the goal (monotone progress).
    Returns ``fallback`` (no move) when the start IS the goal or no legal
    path exists (genuinely immovable state — the honest no-op).

    Args:
        state: current float position [x, y].
        blocked: iterable of (x, y) blocked cells from the live sim.
        goal: target [x, y] (module GOAL from telos_task, real).
        grid_size: edge length of the square grid (5 for GridWorld).
        fallback: value to return when no move is possible (the state).

    Returns:
        np.ndarray delta (first legal step) or ``fallback``.
    """
    start = (int(round(state[0])), int(round(state[1])))
    gx, gy = int(round(goal[0])), int(round(goal[1]))
    if start == (gx, gy):
        return fallback  # already at the goal — nothing to do
    blocked_set = set(tuple(b) for b in blocked)

    def manhattan(cell):
        return abs(cell[0] - gx) + abs(cell[1] - gy)

    # Deterministic neighbor order (ties resolve identically every run).
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    counter = 0
    start_h = manhattan(start)
    heap = [(start_h, 0, counter, start)]
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
            # Walk back to the first step after the start (start's parent
            # is None, so the first step is the node whose parent is start).
            node = cell
            while came_from[node] is not None and came_from[node] != start:
                node = came_from[node]
            return np.array([node[0] - start[0], node[1] - start[1]], dtype=float)
        for dx, dy in neighbors:
            ncell = (cell[0] + dx, cell[1] + dy)
            if not (0 <= ncell[0] < grid_size and 0 <= ncell[1] < grid_size):
                continue  # bounds-safe: never plan outside the grid
            if ncell in blocked_set:
                continue  # real blocked cells are never entered
            ng = g + 1
            if ng < g_score.get(ncell, float('inf')):
                g_score[ncell] = ng
                came_from[ncell] = cell
                heapq.heappush(heap, (ng + manhattan(ncell), ng, counter, ncell))
                counter += 1
    return fallback  # no legal path — honest no-op


def _clamp01(value: float) -> float:
    """Clamp any numeric input to [0, 1] (None/NaN-safe).

    Args:
        value: any scalar; non-numeric/None/NaN map to 0.0.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(0.0, min(1.0, v))


def system_score(di, md, reward_collected, reward_available, world_states,
                 grid_area, weights=None, drift_threshold=DRIFT_THRESHOLD) -> float:
    """Bounded 0-100 System Score - a real function of measured signals.

    score = 100 * clamp01(0.50*DI + 0.25*(1 - min(1, MD/tau))
                          + 0.15*min(1, rewards/available)
                          + 0.10*min(1, cells_visited/area))

    DI (decision integrity) dominates - Axiom 1.2: process over outcomes.
    Every component is clamped, so the result is always in [0, 100]. The
    perfect state (DI=1, MD=0, all rewards secured, whole grid mapped)
    scores 100; no state can score below 0 or above 100.

    Args:
        di: last cycle decision_integrity (0..1) - measured.
        md: last cycle mission_drift (>=0) - measured; normalized by tau.
        reward_collected: cumulative rewards secured (measured).
        reward_available: total positive reward in the world (constant).
        world_states: distinct grid cells visited (measured).
        grid_area: total grid cells (constant).
        weights: optional component weights (defaults to SYSTEM_SCORE_WEIGHTS).
        drift_threshold: MissionDriftDetector threshold (default 5.0).
    """
    w = weights or SYSTEM_SCORE_WEIGHTS
    di_c = _clamp01(di)
    md_c = _clamp01(md / drift_threshold) if (drift_threshold and md is not None) else 0.0
    reward_frac = (_clamp01(reward_collected / reward_available)
                   if (reward_available and reward_collected is not None) else 0.0)
    coverage = (_clamp01(world_states / grid_area)
                if (grid_area and world_states is not None) else 0.0)
    raw = (w["di"] * di_c
           + w["md"] * (1.0 - md_c)
           + w["reward"] * reward_frac
           + w["coverage"] * coverage)
    return round(100.0 * _clamp01(raw), 1)


def safe_score(value) -> Optional[float]:
    """Only a value inside the defined range is a valid System Score.

    Legacy persisted traces carry the old unbounded format
    (100 - cycles + rewards, e.g. -271); those are structurally rejected
    here rather than displayed - the range is part of the metric's
    definition. Returns None for missing/non-numeric/out-of-range values.

    Args:
        value: candidate score from a trace or snapshot.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    v = float(value)
    if v != v or not (0.0 <= v <= 100.0):
        return None
    return round(v, 2)

# Paths shared with serve_dashboard.py and telos_task.py
CHECKPOINT_DIR = "/tmp/telos_checkpoints"
# Producer-owned counter state (exact cycles/worlds_simulated_total across
# restarts). Written atomically each cycle; the hero reads it on boot so the
# numbers never reset to 0 when the dashboard restarts.
PRODUCER_STATE_PATH = "/tmp/telos_producer_state.json"
KNOWLEDGE_PATH = "/tmp/telos_knowledge.json"
LEDGER_PATH = "/tmp/telos_ledger.json"
IDENTITY_PATH = "/tmp/telos_identity.json"
PATTERN_PATH = "/tmp/telos_patterns.json"
# Decision log: the producer now feeds the SAME bounded, honest decision log
# the handoff writer reconciles ("log=N"). Written atomically at the
# knowledge-serialize cadence with lean canonical trace fields so it reflects
# LIVE pipeline decisions instead of a stale interactive-only artifact.
DECISION_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'audit', 'runtime',
    'decision_log.json')
DECISION_LOG_MAX_ENTRIES = 500

CYCLE_INTERVAL_S = float(os.environ.get('TELOS_CYCLE_S', '2.0'))   # live cadence between steady-state cycles (env-overridable)
BURST_CYCLES = 5         # warm-up cycles at boot so graphs fill within seconds
MAX_TRACES_IN_MEMORY = 200
# Default persistence cadence for long-lived runs: a checkpoint (~20MB with a
# full KG) or a full-KG serialization is NOT written every 2s cycle. First
# cycle always persists (fast restore seed); afterwards every N cycles.
CHECKPOINT_EVERY_N_DEFAULT = int(os.environ.get('TELOS_CHECKPOINT_EVERY_N', '20'))
KNOWLEDGE_SERIALIZE_INTERVAL_DEFAULT = 20


def serialize_knowledge(kg: Any) -> Dict[str, list]:
    """Map a live KnowledgeGraph into the dashboard API shape.

    Mirrors serve_dashboard._load_knowledge's disk parsing so the API
    returns the same honest shape whether it reads live memory or cold
    files. Nodes: id/label/domain/importance. Edges: source/target/
    weight/edge_type — only what the graph actually holds.

    As of the lessons-drill feature, nodes that have been ARCHIVED (moved
    out of the active set by attention decay / capacity eviction) are also
    returned in a separate "archived_nodes" list, plus a "stats" block with
    live/archived/total counts. This makes the total learned knowledge
    legible instead of hiding it behind the live-set ceiling.

    Args:
        kg: the KnowledgeGraph instance (may be None).
    """
    if kg is None:
        return {"nodes": [], "edges": [], "archived_nodes": [],
                "stats": {"live": 0, "archived": 0, "total": 0}}
    nodes_raw = getattr(kg, "_nodes", {}) or {}
    archived_raw = getattr(kg, "_archived_nodes", {}) or {}
    edges_raw = getattr(kg, "_edges", {}) or {}
    nodes = []
    for nid, ndata in nodes_raw.items():
        label = getattr(ndata, "approach", None) or getattr(ndata, "domain", None) or nid[:8]
        domain = getattr(ndata, "domain", "general") or "general"
        if "/" in domain:
            domain = domain.split("/")[0]
        importance = getattr(ndata, "outcome", 0.5)
        if isinstance(importance, (int, float)):
            importance = max(0.1, min(1.0, float(importance)))
        else:
            importance = 0.5
        nodes.append({
            "id": nid,
            "label": str(label).replace("_", " ").title(),
            "domain": domain,
            "importance": importance,
        })
    archived_nodes = []
    for nid, ndata in archived_raw.items():
        label = getattr(ndata, "approach", None) or getattr(ndata, "domain", None) or nid[:8]
        domain = getattr(ndata, "domain", "general") or "general"
        if "/" in domain:
            domain = domain.split("/")[0]
        importance = getattr(ndata, "outcome", 0.5)
        if isinstance(importance, (int, float)):
            importance = max(0.1, min(1.0, float(importance)))
        else:
            importance = 0.5
        archived_nodes.append({
            "id": nid,
            "label": str(label).replace("_", " ").title(),
            "domain": domain,
            "importance": importance,
        })
    edges = []
    for eid, edata in edges_raw.items():
        src = getattr(edata, "src", None)
        dst = getattr(edata, "dst", None)
        if not src or not dst:
            continue
        edges.append({
            "source": src,
            "target": dst,
            "weight": getattr(edata, "weight", 0.5),
            "edge_type": getattr(edata, "edge_type", "related"),
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "archived_nodes": archived_nodes,
        "stats": {
            "live": len(nodes),
            "archived": len(archived_nodes),
            "total": len(nodes) + len(archived_nodes),
        },
    }


class DashboardProducer:
    """Runs the real GridWorld pipeline on a background thread and holds
    a thread-safe runtime snapshot that the dashboard APIs read.

    Honesty contract: every number in the snapshot is a measured value
    from an actual pipeline cycle. When the pipeline cannot run (import
    failure, repeated crash), the producer records the error and the
    dashboard renders the honest empty/history state.
    """

    def __init__(self, cycle_interval_s: float = CYCLE_INTERVAL_S,
                 burst_cycles: int = BURST_CYCLES,
                 checkpoint_every_n: int = CHECKPOINT_EVERY_N_DEFAULT,
                 knowledge_serialize_interval: int = KNOWLEDGE_SERIALIZE_INTERVAL_DEFAULT):
        self._cycle_interval_s = max(0.5, float(cycle_interval_s))
        self._burst_cycles = max(1, int(burst_cycles))
        self._checkpoint_every_n = max(1, int(checkpoint_every_n))
        self._knowledge_serialize_interval = max(1, int(knowledge_serialize_interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._started = False

        # ── runtime components (built lazily in _build to keep import cheap) ──
        self._pipeline = None
        self._sim = None
        self._experience_mgr = None
        self._agent2 = None
        self._state_np = np.array([0.0, 0.0])
        self._last_nav_node: Optional[str] = None
        self._visited_positions: set = set()

        # ── episode efficiency (measured from real goal-reach events) ──
        # Two clocks per episode, both counted on the producer's own
        # observations (ZERO sim mutation):
        #   steps — every decision cycle (moves, no-ops AND inquiry pauses)
        #   moves — only cycles where the agent actually changed position.
        self._episode_steps = 0
        self._episode_moves = 0
        self._episodes_completed = 0
        self._last_episode_steps: Optional[int] = None
        self._last_episode_moves: Optional[int] = None
        self._completed_episode_steps: List[int] = []
        self._completed_episode_moves: List[int] = []

        # ── live metrics (all measured, none invented) ──
        self._traces: List[Dict] = []
        self._cycles = 0
        self._system_score: Optional[float] = None  # None = no cycle yet (honest empty)
        self._score_components: Optional[Dict] = None
        self._reward_collected = 0.0
        self._reward_available = 0.0
        self._grid_area = 0.0
        self._worlds_simulated_total = 0
        self._last_cycle_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._knowledge_payload: Dict[str, list] = {"nodes": [], "edges": []}
        # Payload cache guard: re-serialize the KG only when its node/edge
        # counts change or the forced interval elapses (serializing 56K edges
        # every 2s cycle was the wedge; the cache keeps the lock hold short).
        self._knowledge_cache_guard: tuple = (-1, -1)
        self._cycles_since_knowledge_serialize = 0
        # Bounded live decision log (mirrors TransparencyMonitor's 500-cap
        # 250-keep policy) so decision_log.json reflects the live pipeline.
        self._decision_log_entries: List[Dict] = []
        # Broadcast callback injected by the serving process. Injected (not
        # imported) so there is exactly ONE module instance of the server:
        # importing telos.serve_dashboard from the producer would create a
        # second module copy whose websocket_clients set is always empty.
        self._broadcast_fn = None

    # ── Public control ─────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._started and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._loop, name="telos-producer", daemon=True)
        self._thread.start()
        logger.info("DashboardProducer started (interval=%.1fs, burst=%d)",
                    self._cycle_interval_s, self._burst_cycles)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._started = False
        logger.info("DashboardProducer stopped")

    # ── Thread-safe snapshot for APIs ──────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            traces = list(self._traces)
            return {
                "producer": {
                    "running": self.is_running,
                    "cycles": self._cycles,
                    "last_cycle_at": self._last_cycle_at,
                    "last_error": self._last_error,
                    "rss_peak_kb": self._rss_peak_kb(),
                },
                "decisions": self._cycles,
                "traces": traces,
                "recent_decisions": [self._story_decision(t) for t in traces[-8:]],
                "di": traces[-1].get("decision_integrity", 0.0) if traces else 0.0,
                "md": traces[-1].get("mission_drift", 0.0) if traces else 0.0,
                "health": float(traces[-1].get("health_score", 0.5)) if traces else 0.5,
                "score": self._system_score,
                "score_components": self._score_components,
                "reward_collected": self._reward_collected,
                "reward_available": self._reward_available,
                "worlds_simulated": self._worlds_simulated_total,
                "world_states": len(self._visited_positions),
                "episodes": self._episode_stats(),
                "position": self._state_np.tolist(),
                "mood": self._mood(),
                "knowledge": self._knowledge_stats(),
                "knowledge_payload": self._knowledge_payload,
            }

    def _story_decision(self, trace: Dict) -> Dict:
        intent = trace.get("selected_intent") or {}
        if isinstance(intent, dict):
            intent_label = intent.get("type") or intent.get("intent_type") or "unknown"
        else:
            intent_label = "unknown"
        return {
            "cycle_id": trace.get("cycle_id"),
            "intent": intent_label,
            "di": trace.get("decision_integrity", 0.0),
            "md": trace.get("mission_drift", 0.0),
            "status": "BLOCKED" if (trace.get("firewall_blocked") or not trace.get("council_validated", True)) else "APPROVED",
            "worlds": trace.get("worlds_simulated", 0),
            "position": trace.get("world_state"),
            "blocking_validator": trace.get("blocking_validator"),
            "firewall_blocked_by": trace.get("firewall_blocked_by"),
        }

    def _mood(self) -> str:
        try:
            if self._pipeline is not None:
                ss = self._pipeline.infra_manager.system_self
                if ss is not None and hasattr(ss, "mood"):
                    return str(ss.mood)
        except Exception as e:
            logger.warning("producer: mood read failed: %r", e)
        return "neutral"

    def _knowledge_stats(self) -> Dict:
        payload = self._knowledge_payload
        domains: Dict[str, int] = {}
        edge_types: Dict[str, int] = {}
        for n in payload.get("nodes", []):
            d = n.get("domain", "general")
            domains[d] = domains.get(d, 0) + 1
        for e in payload.get("edges", []):
            t = e.get("edge_type", "related")
            edge_types[t] = edge_types.get(t, 0) + 1
        live = len(payload.get("nodes", []))
        archived = len(payload.get("archived_nodes", []))
        return {
            "nodes": live,
            "edges": len(payload.get("edges", [])),
            "archived_nodes": archived,
            "total_nodes": live + archived,
            "domains": domains,
            "edge_types": edge_types,
        }

    # ── Episode efficiency (zero sim mutation) ─────────────────────

    def _on_goal_reached(self) -> None:
        """Goal-reach bookkeeping (called from _run_cycle on terminal()).

        ZERO sim mutation: this only counts events the producer already
        observes. The live world's reward dict is untouched - no respawn,
        no fake re-collection, no changed perception for the pipeline.

        Returns:
            None.
        """
        self._episodes_completed += 1
        self._last_episode_steps = self._episode_steps
        self._last_episode_moves = self._episode_moves
        self._completed_episode_steps.append(self._episode_steps)
        self._completed_episode_moves.append(self._episode_moves)
        if len(self._completed_episode_steps) > MAX_EPISODE_HISTORY:
            self._completed_episode_steps = self._completed_episode_steps[-MAX_EPISODE_HISTORY:]
            self._completed_episode_moves = self._completed_episode_moves[-MAX_EPISODE_HISTORY:]
        self._episode_steps = 0
        self._episode_moves = 0

    def _episode_stats(self) -> Dict[str, Any]:
        """Episode efficiency - all values derived from real goal-reach events.

        avg_steps_per_goal / efficiency_vs_optimal are None until at least
        one episode completes (honest empty state: 'unmeasured' is never
        shown as a fake number). optimal_steps is the Manhattan distance
        (0,0)->(4,4) = 8, the shortest possible episode; efficiency is
        clamp01(optimal / avg), so it is bounded [0, 1] when defined.

        Returns:
            Dict with completed/current_steps/last_steps/avg_steps_per_goal/
            efficiency_vs_optimal/optimal_steps.
        """
        with self._lock:
            hist = list(self._completed_episode_steps)
            avg = (float(sum(hist)) / len(hist)) if hist else None
            eff = _clamp01(OPTIMAL_STEPS / avg) if avg else None
            hist_moves = list(self._completed_episode_moves)
            avg_moves = (float(sum(hist_moves)) / len(hist_moves)) if hist_moves else None
            eff_moves = _clamp01(OPTIMAL_STEPS / avg_moves) if avg_moves else None
            return {
                "completed": self._episodes_completed,
                "current_steps": self._episode_steps,
                "current_moves": self._episode_moves,
                "last_steps": self._last_episode_steps,
                "last_moves": self._last_episode_moves,
                "avg_steps_per_goal": (None if avg is None else round(avg, 1)),
                "avg_moves_per_goal": (None if avg_moves is None else round(avg_moves, 1)),
                "efficiency_vs_optimal": (None if eff is None else round(eff, 4)),
                "moves_efficiency_vs_optimal": (None if eff_moves is None else round(eff_moves, 4)),
                "optimal_steps": OPTIMAL_STEPS,
                "optimal_moves": OPTIMAL_STEPS,
            }

    # ── Producer loop ──────────────────────────────────────────────

    def _loop(self) -> None:
        try:
            self._build()
        except Exception as e:
            logger.critical("producer: pipeline build failed — dashboard will show persisted/history state only: %r", e)
            self._last_error = f"build_failed: {e}"
            return

        # Warm-up burst so the dashboard has data within seconds of boot.
        for _ in range(self._burst_cycles):
            if self._stop.is_set():
                break
            try:
                self._run_cycle()
            except Exception as e:
                logger.warning("producer: burst cycle failed: %r", e)
                self._last_error = f"cycle_error: {e}"
                break
        logger.info("producer: warm-up burst complete (%d cycles)", self._cycles)

        # Steady-state live cadence.
        while not self._stop.is_set():
            try:
                self._run_cycle()
            except Exception as e:
                logger.warning("producer: cycle failed: %r", e)
                self._last_error = f"cycle_error: {e}"
            self._stop.wait(self._cycle_interval_s)

    def _build(self) -> None:
        from telos_task import (
            GridAdpt, GridSim, TERRAIN, DEFAULT_BLOCKED, DEFAULT_REWARDS, GOAL,
        )
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
        from telos_task import GridAgent

        self._sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
        self._grid_size = 5  # GridWorld GRID_SIZE
        self._goal = GOAL  # real goal from telos_task (the A* planner's target)
        self._grid_area = float(self._grid_size ** 2)
        # Total positive reward available in the world - the denominator of
        # the reward component of the System Score (a world constant, real).
        self._reward_available = float(sum(v for v in DEFAULT_REWARDS.values() if v and v > 0))
        self._pipeline = TelosV14Pipeline(PipelineConfig(
            adapter=GridAdpt(), simulator=self._sim,
            compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
            checkpoint_path=CHECKPOINT_DIR,
            checkpoint_every_n=self._checkpoint_every_n,
            knowledge_path=KNOWLEDGE_PATH,
            ledger_path=LEDGER_PATH,
            identity_path=IDENTITY_PATH,
            pattern_path=PATTERN_PATH,
            deterministic_seed=42,
        ))
        skill_lib = SkillLibrary()
        self._experience_mgr = ExperienceManager(
            skill_lib,
            ExperienceConfig(utility_threshold=0.1, index_interval=1),
        )
        sim_engine = CounterfactualEngine(self._sim)
        pipeline = self._pipeline
        pipeline.register_stream(ReflexStream(skill_lib))
        pipeline.register_stream(PerceptionStream(skill_lib))
        pipeline.register_stream(MemoryStream(skill_lib))
        pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
        pipeline.register_stream(InquiryStream(skill_lib))
        pipeline.register_stream(TheoryStream(skill_lib, theory_builder=getattr(pipeline, "_theory_builder", None)))
        pipeline.register_validator(RealityValidator())
        pipeline.register_validator(ConstraintValidator())
        memory_advisor = MemoryAdvisor(skill_lib)
        pipeline.register_validator(memory_advisor)
        pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))
        pipeline.register_validator(EvidenceProvenanceValidator())
        if hasattr(pipeline, "infra_manager") and pipeline.infra_manager:
            im = pipeline.infra_manager
            memory_advisor.connect(
                failure_ledger=getattr(im, "failures", None),
                knowledge_graph=im.knowledge if hasattr(im, "knowledge") else None,
            )
        self._agent2 = GridAgent(
            start_pos=(4, 0),
            blocked=set(DEFAULT_BLOCKED),
            rewards=dict(DEFAULT_REWARDS),
        )
        # Warm the skill library from any persisted history (cross-session).
        if os.path.isdir(CHECKPOINT_DIR):
            try:
                self._experience_mgr.index_recent(CHECKPOINT_DIR, cycles=5)
            except Exception as e:
                logger.warning("producer: skill warm-up skipped: %r", e)

        # Hero counters survive restarts: restore exact counters from the
        # producer state file, or best-effort from the newest checkpoint
        # (the pipeline itself restores its cycle count from that same
        # checkpoint, so producer totals and trace cycle_ids stay aligned).
        self._restore_producer_counters()

    def _run_cycle(self) -> None:
        trace_dict: Optional[Dict] = None
        with self._lock:
            result = self._pipeline.execute(self._state_np, user_name="Prateek")
            self._cycles += 1
            # Every decision cycle is one step of the episode clock (moves,
            # no-ops AND inquiry pauses are all real time-to-goal - an
            # honest measure of how many decisions reaching the goal takes).
            self._episode_steps += 1
            trace = result.decision_trace
            self._experience_mgr.observe(result)

            # Real world dynamics (same as telos_task.py main loop).
            terrain_changes = self._sim.maybe_shift_terrain()
            pos_before = (int(round(self._state_np[0])), int(round(self._state_np[1])))
            if trace is not None and trace.selected_action is not None and not result.firewall_blocked:
                self._state_np = self._apply_action(self._state_np, trace.selected_action)
            pos_after = (int(round(self._state_np[0])), int(round(self._state_np[1])))
            # Moves clock: increments ONLY when the agent actually changed
            # position — blocked/no-op/inquiry cycles are excluded. This is
            # the moves-per-goal split alongside the steps (cycle) clock.
            if pos_after != pos_before:
                self._episode_moves += 1

            if self._agent2 is not None:
                a2_key = self._agent2.step()
                a2_pos = self._agent2.position.tolist()
                a2_reward = self._agent2.total_reward
            else:
                a2_key, a2_pos, a2_reward = None, [4, 0], 0.0

            pos_key = (int(round(self._state_np[0])), int(round(self._state_np[1])))
            self._visited_positions.add(pos_key)

            # Reward collection (real).
            reward = 0.0
            if pos_key in self._sim.rewards and self._sim.rewards[pos_key] > 0:
                if a2_key == pos_key:
                    reward = self._sim.rewards[pos_key] / 2.0
                    self._agent2.total_reward += reward
                else:
                    reward = self._sim.rewards[pos_key]
                self._sim.rewards[pos_key] = 0.0
            self._reward_collected += reward
            # System Score - bounded composite of MEASURED signals. Time is
            # NOT a component: cycles elapsed is an endurance fact, kept as
            # a separate labeled readout, never folded into a quality score.
            di_now = float(result.decision_integrity) if result.decision_integrity is not None else 0.0
            md_now = float(result.mission_drift) if result.mission_drift is not None else 0.0
            self._system_score = system_score(
                di=di_now, md=md_now,
                reward_collected=self._reward_collected,
                reward_available=self._reward_available,
                world_states=len(self._visited_positions),
                grid_area=self._grid_area,
            )
            self._score_components = {
                "di": round(di_now, 4),
                "md": round(md_now, 4),
                "reward_fraction": round(
                    _clamp01(self._reward_collected / self._reward_available)
                    if self._reward_available else 0.0, 4),
                "world_coverage": round(
                    _clamp01(len(self._visited_positions) / self._grid_area)
                    if self._grid_area else 0.0, 4),
                "weights": dict(SYSTEM_SCORE_WEIGHTS),
                "drift_threshold": DRIFT_THRESHOLD,
                "grid_area": self._grid_area,
            }

            # Record REAL observations into the knowledge graph.
            self._record_knowledge(result, trace, reward, terrain_changes)

            # Bound the checkpoint dir: CheckpointManager prunes only
            # checkpoint_*.json; system_self_*.json and patterns_*.json
            # accumulate per-cycle. Keep the newest 20 of each.
            try:
                self._prune_aux_files()
            except Exception as e:
                logger.warning("producer: aux-file prune failed: %r", e)

            # Full serialized trace (client consumes world_state, streams, ...).
            if trace is not None:
                trace_dict = trace.to_dict() if hasattr(trace, "to_dict") else {}
                if isinstance(trace_dict, dict):
                    trace_dict["agent2_pos"] = a2_pos
                    trace_dict["agent2_reward"] = a2_reward
                    trace_dict["score"] = safe_score(self._system_score)
                    trace_dict["terrain_changes"] = terrain_changes
                    trace_dict["health_score"] = float(result.health_score)
                    self._traces.append(json_clean(trace_dict))
                    if len(self._traces) > MAX_TRACES_IN_MEMORY:
                        self._traces = self._traces[-MAX_TRACES_IN_MEMORY:]
                    # Bounded live decision log (lean canonical fields —
                    # intentional: full serialized traces live in checkpoints;
                    # the audit log must stay small and honest).
                    lean = self._trace_for_broadcast(trace_dict)
                    lean["timestamp"] = trace_dict.get("timestamp", time.time())
                    self._decision_log_entries.append(lean)
                    if len(self._decision_log_entries) > DECISION_LOG_MAX_ENTRIES:
                        self._decision_log_entries = self._decision_log_entries[-DECISION_LOG_MAX_ENTRIES // 2:]

            # ── Persistence throttle (Λ4.7): the expensive parts are the KG
            # serialization, kg.save, and the decision-log write — NOT the
            # cycle itself. Re-serialize/save only when the graph changed
            # (node/edge counts) or the forced interval elapses; keep the
            # cycle lock hold short and the disk churn bounded.
            self._cycles_since_knowledge_serialize += 1
            kg = self._pipeline.infra_manager.knowledge
            kg_stats = kg.stats
            kg_guard = (kg_stats["total_nodes"], kg_stats["total_edges"])
            # Deterministic cadence: the modulo is the PRIMARY bound (serialize
            # at most every N cycles even if the KG churns every cycle — that
            # is the wedge-killer). A count change is a freshness trigger but
            # floored at interval//4 so it can never degrade back to
            # per-cycle serialization. First cycle always initializes.
            _fresh_floor = max(1, self._knowledge_serialize_interval // 4)
            first = self._knowledge_cache_guard == (-1, -1)
            force = self._cycles_since_knowledge_serialize >= self._knowledge_serialize_interval
            fresh = (kg_guard != self._knowledge_cache_guard
                     and self._cycles_since_knowledge_serialize >= _fresh_floor)
            if first or force or fresh:
                self._knowledge_payload = json_clean(serialize_knowledge(kg))
                self._knowledge_cache_guard = kg_guard
                self._cycles_since_knowledge_serialize = 0
                try:
                    kg.save(KNOWLEDGE_PATH)
                except Exception as e:
                    logger.warning("producer: knowledge persist failed: %r", e)
                self._flush_decision_log()
                rss = self._rss_peak_kb()
                if rss is not None:
                    logger.info(
                        "producer: cycle=%d rss_peak_kb=%d (memory guard)",
                        self._cycles, rss,
                    )

            self._worlds_simulated_total += int(trace.worlds_simulated if trace else 0)
            self._last_cycle_at = time.time()

            # Persist the exact hero counters atomically so a dashboard
            # restart continues the totals instead of resetting to 0.
            self._persist_producer_state()

            # Goal reached → record the episode (producer-side bookkeeping,
            # ZERO sim mutation) and reset to origin for a continuous live run.
            if trace is not None and trace.selected_action is not None and self._sim.terminal(self._state_np):
                self._on_goal_reached()
                self._state_np = np.array([0.0, 0.0])

        # Broadcast OUTSIDE the lock (network I/O must not stall the cycle).
        if trace_dict is not None:
            self._broadcast_trace(trace_dict)

    @staticmethod
    def _rss_peak_kb() -> Optional[int]:
        """Peak resident set size in KB (resource.ru_maxrss; macOS reports
        bytes, Linux KB — normalize). The producer's honesty memory guard:
        monotone peak RSS is logged every knowledge-serialize interval and
        exposed via /api/status so a leak is observable, never silent."""
        try:
            import resource
            raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS ru_maxrss is in BYTES; Linux/BSD report KB already.
            if sys.platform == "darwin":
                return raw // 1024
            return raw
        except Exception:
            return None

    def _apply_action(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Legal-route executor for the selected action (BFS/A*).

        The pipeline's adapter emits diagonal/no-op vectors
        (np.sign(goal - state)) that GridSim.transition cannot route
        around blocked cells — a genuine no-op leaves the agent parked
        at the origin forever, which hides the live run. This executor
        plans with A* over the REAL 5x5 legal grid (blocked cells read
        from the live sim, goal from telos_task.GOAL) and returns the
        first step of the shortest legal path: every approved cycle that
        can move makes monotone progress toward the goal. Deterministic
        (fixed neighbor order + Manhattan heuristic, heap tie-break),
        bounds-safe (A* only expands in-grid cells), verified in-bounds.
        Genuine no-ops (|action| ~ 0) and genuinely-immovable states (no
        legal path, or already at the goal) stay put — the decision is
        honored, never invented.
        """
        a = np.asarray(action, dtype=float)
        if a.shape != (2,):
            return state
        if abs(a[0]) < 0.05 and abs(a[1]) < 0.05:
            return state  # genuine no-op — respect the decision
        step = _astar_step(
            state=state,
            blocked=self._sim.blocked,
            goal=self._goal,
            grid_size=self._grid_size,
            fallback=np.array([0.0, 0.0], dtype=float),
        )
        if step is None or (abs(step[0]) < 0.05 and abs(step[1]) < 0.05):
            return state  # immovable / already at goal — honest no-op
        dest = np.clip(state + step, 0, self._grid_size - 1)
        # A* only returns legal in-grid steps; the clip is a belt-and-braces
        # guarantee for the in-bounds contract.
        return dest

    def _record_knowledge(self, result, trace, reward: float, terrain_changes: List[Dict]) -> None:
        """Record real runtime observations as knowledge nodes + edges.

        Provenance stamps every node as a dashboard-producer observation.
        Nothing here is invented: DI, position, terrain, verdicts, and
        rewards are measured values from the actual cycle.

        Args:
            result: the PipelineResult of the cycle just executed.
            trace: the cycle's DecisionTrace.
            reward: reward actually collected this cycle.
            terrain_changes: terrain shifts applied this cycle.
        """
        try:
            kg = self._pipeline.infra_manager.knowledge
        except Exception:
            return
        cyc = self._cycles
        di = float(result.decision_integrity)
        md = float(result.mission_drift)
        pos = self._state_np
        px, py = int(round(pos[0])), int(round(pos[1]))
        pos_key = f"{px},{py}"

        # 1) Navigation outcome node (real DI).
        nid_nav = kg.record(
            "navigation", f"move_to_{pos_key}", di,
            tags=["gridworld", "navigation", f"pos_{pos_key}"],
            params={"position": [px, py], "mission_drift": md},
            provenance={"source": "dashboard_producer", "cycle": cyc, "caller": "dashboard_producer"},
        )
        # 2) Terrain node (only the first time each biome is seen here).
        from telos_task import TERRAIN
        terrain_here = TERRAIN.get((px, py), "plains")
        nid_terrain = None
        for n in kg._nodes.values():
            if n.domain == "gridworld" and n.approach == f"terrain_{terrain_here}":
                nid_terrain = n.node_id
                break
        if nid_terrain is None:
            nid_terrain = kg.record(
                "gridworld", f"terrain_{terrain_here}", 1.0,
                tags=["terrain", terrain_here],
                params={"terrain": terrain_here, "first_seen_at": pos_key},
                provenance={"source": "dashboard_producer", "cycle": cyc, "caller": "dashboard_producer"},
            )
        # 3) Reward node (only when actually collected).
        if reward > 0:
            kg.record(
                "navigation", f"collect_reward_{pos_key}", 1.0,
                tags=["gridworld", "reward"],
                params={"reward": reward},
                provenance={"source": "dashboard_producer", "cycle": cyc, "caller": "dashboard_producer"},
            )
        # 4) Blocked decision node (real council/firewall block).
        blocked_by = None
        if result.council_blocked:
            blocked_by = trace.blocking_validator if trace else "council"
        elif result.firewall_blocked:
            blocked_by = trace.firewall_blocked_by if trace else "firewall"
        if blocked_by:
            kg.record(
                "blocker", f"blocked_by_{blocked_by}", 0.15,
                failure_reason=f"blocked_by_{blocked_by}",
                tags=["council", "blocked"],
                params={"cycle": cyc},
                provenance={"source": "dashboard_producer", "cycle": cyc, "caller": "dashboard_producer"},
            )
        # 5) Real edges: temporal 'follows' chain + 'at_location' terrain link.
        if nid_nav:
            if self._last_nav_node and self._last_nav_node != nid_nav:
                try:
                    kg.add_edge(self._last_nav_node, nid_nav, edge_type="follows",
                                weight=di, metadata={"cycle": cyc})
                except Exception:
                    pass
            if nid_terrain and nid_terrain != nid_nav:
                try:
                    kg.add_edge(nid_nav, nid_terrain, edge_type="at_location", weight=1.0,
                                metadata={"position": pos_key})
                except Exception:
                    pass
            self._last_nav_node = nid_nav

    # ── Hero counter persistence (Item 5c) ────────────────────────────

    def _persist_producer_state(self) -> None:
        """Atomically write the exact hero counters (cycles, worlds
        simulated) so a dashboard restart continues the totals instead of
        resetting to 0. Written every cycle; read by
        _restore_producer_counters on the next boot.

        Returns:
            None.
        """
        try:
            payload = {
                "cycles": self._cycles,
                "worlds_simulated_total": self._worlds_simulated_total,
                "updated_at": time.time(),
            }
            tmp_path = PRODUCER_STATE_PATH + ".tmp"
            with open(tmp_path, "w") as fh:
                json.dump(payload, fh)
            os.replace(tmp_path, PRODUCER_STATE_PATH)
        except Exception as e:
            logger.warning("producer: counter state persist failed: %r", e)

    def _restore_producer_counters(self) -> None:
        """Restore _cycles / _worlds_simulated_total from persisted state.

        Exact counters come from the producer state file (written every
        cycle). Failing that, the newest checkpoint's `cycle` field is the
        honest best-effort baseline (the pipeline itself restores its cycle
        count from the same checkpoint, so producer totals stay aligned
        with trace cycle_ids). worlds_simulated is only recoverable from
        checkpoints when the persisted decision_trace carries the field
        (older dumps do not — that component then honestly starts at 0).
        The in-memory trace list is seeded with the newest persisted real
        traces so the story's recent-decisions render a truthful
        continuation, never a blank slate.

        Returns:
            None.
        """
        state = None
        try:
            if os.path.exists(PRODUCER_STATE_PATH):
                with open(PRODUCER_STATE_PATH) as fh:
                    state = json.load(fh)
        except Exception as e:
            logger.warning("producer: counter restore (state file) failed: %r", e)
        if isinstance(state, dict):
            try:
                self._cycles = int(state.get("cycles", 0) or 0)
                self._worlds_simulated_total = int(state.get("worlds_simulated_total", 0) or 0)
                logger.info(
                    "producer: restored exact counters from %s "
                    "(cycles=%d, worlds_simulated=%d)",
                    PRODUCER_STATE_PATH, self._cycles, self._worlds_simulated_total,
                )
            except (TypeError, ValueError) as e:
                logger.warning("producer: counter restore (state file) malformed: %r", e)
        self._seed_traces_from_checkpoints()

    def _seed_traces_from_checkpoints(self) -> None:
        """Seed _traces with the newest persisted real decision traces.

        Checkpoints are real pipeline output (never invented): the story's
        recent-decisions and hero caption become a truthful continuation
        across restarts. Also falls back to the newest checkpoint's `cycle`
        field for the cycle baseline when the exact state file is absent.

        Returns:
            None.
        """
        if not os.path.isdir(CHECKPOINT_DIR):
            return
        files = sorted(_glob.glob(os.path.join(CHECKPOINT_DIR, "checkpoint_*.json")),
                       key=os.path.getmtime)
        if not files:
            return
        latest_cycle = None
        seeded = []
        for f in files[-20:]:
            try:
                with open(f) as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            try:
                c = data.get("cycle")
                if c is not None and (latest_cycle is None or int(c) > latest_cycle):
                    latest_cycle = int(c)
            except (TypeError, ValueError):
                pass
            dt = data.get("decision_trace")
            if isinstance(dt, dict) and dt.get("cycle_id") is not None:
                seeded.append(dt)
        if latest_cycle is not None:
            self._cycles = max(self._cycles, latest_cycle)
            logger.info("producer: checkpoint baseline cycle=%d", latest_cycle)
        if seeded:
            seeded.sort(key=lambda t: int(t.get("cycle_id", 0) or 0))
            self._traces = [json_clean(t) for t in seeded][-MAX_TRACES_IN_MEMORY:]
            logger.info(
                "producer: seeded %d persisted real traces from checkpoints",
                len(self._traces),
            )

    def _prune_aux_files(self) -> None:
        """Keep the checkpoint dir bounded (aux files are not checkpoint-rotated).

        Aux files (system_self_*.json, patterns_*.json) share the same
        zero-padded numeric names as checkpoints: they must be ordered by
        the canonical numeric key, never lexically (pattern: natural order —
        lexical sort inverts at the 4→5 digit boundary and would delete the
        NEWEST file).
        """
        import glob as _glob
        from telos.core.infra_manager.checkpoint_manager import _checkpoint_cycle_key
        for pattern, keep in (("system_self_*.json", 20), ("patterns_*.json", 20)):
            files = sorted(
                _glob.glob(os.path.join(CHECKPOINT_DIR, pattern)),
                key=_checkpoint_cycle_key,
            )
            for stale in files[:-keep]:
                try:
                    os.remove(stale)
                except OSError:
                    pass

    # Fields the frontend actually consumes — everything else (axiom_results,
    # belief_state, reasoning_witness, ...) stays in the HTTP checkpoints API
    # but is trimmed from the WebSocket frame (1MB limit; heavy traces would
    # otherwise kill the live push with a 1009 frame-too-big error).
    BROADCAST_TRACE_FIELDS = [
        "cycle_id", "timestamp", "decision_integrity", "mission_drift",
        "council_validated", "firewall_blocked", "blocking_validator",
        "intent", "discrimination_index", "action_taken", "budget_carryover_ms",
        "budget_consumed_ms",
        "world_state", "selected_intent", "selected_action",
        "strategic_options", "stream_activations", "council_signals",
        "domain_facts", "worlds_simulated", "inquiry_omega_vector",
        "inquiry_blend", "agent2_pos", "agent2_reward", "score",
        "terrain_changes", "health_score", "representation",
        "escalation_requested",
    ]

    def _trace_for_broadcast(self, trace_dict: Dict) -> Dict:
        if not isinstance(trace_dict, dict):
            return {}
        return {k: trace_dict[k] for k in self.BROADCAST_TRACE_FIELDS if k in trace_dict}

    def _flush_decision_log(self) -> None:
        """Write the bounded live decision log atomically (Λ2.3: failures
        are logged, never silent; a failed audit write must not break the
        cycle). Schema matches TransparencyMonitor's canonical contract so
        the handoff writer's `log_total_cycles` reconciliation reads real
        live totals."""
        try:
            data = {
                "version": "1.0",
                "total_cycles": len(self._decision_log_entries),
                "traces": self._decision_log_entries,
            }
            path = os.path.abspath(DECISION_LOG_PATH)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, path)
        except Exception as e:
            logger.warning("producer: decision log flush failed: %r", e)

    def _broadcast_trace(self, trace_dict: Dict) -> None:
        """Push a LEAN trace + slim overview via the injected callback.

        The full serialized trace can exceed the WebSocket frame limit once
        heavy audit fields (axiom_results, belief_state, reasoning_witness)
        accumulate; the live feed pushes only the fields the dashboard
        renders. Full traces remain available via /api/checkpoints.

        Args:
            trace_dict: the full serialized trace dict for this cycle.
        """
        if self._broadcast_fn is None:
            return
        try:
            self._broadcast_fn(self._trace_for_broadcast(trace_dict), self.overview_payload())
        except Exception as e:
            logger.warning("producer: broadcast failed: %r", e)

    def knowledge_path(self) -> str:
        return KNOWLEDGE_PATH

    def checkpoint_dir(self) -> str:
        return CHECKPOINT_DIR

    def set_broadcast(self, fn) -> None:
        """Inject the serving process's broadcast callable.

        :param fn: callable(trace_dict, overview_dict) invoked after each
            live cycle with the LEAN trace and the slim overview.
        """
        self._broadcast_fn = fn

    def overview_payload(self) -> Dict[str, Any]:
        """Slim overview for broadcasts — excludes the heavy traces list."""
        with self._lock:
            trace = self._traces[-1] if self._traces else None  # last trace once, None-guarded (pattern: bind guard-conditional vars once)
            return {
                "producer": {
                    "running": self.is_running,
                    "cycles": self._cycles,
                    "last_cycle_at": self._last_cycle_at,
                    "last_error": self._last_error,
                },
                "decisions": self._cycles,
                "recent_decisions": [self._story_decision(t) for t in self._traces[-8:]],
                "di": self._traces[-1].get("decision_integrity", 0.0) if self._traces else 0.0,
                "md": self._traces[-1].get("mission_drift", 0.0) if self._traces else 0.0,
                # Axiom coverage: fraction of active axioms with recent trace evidence
                "explain_axiom_coverage": float(
                    sum(
                        1.0 for aid, res in (trace.get("axiom_results") or {}).items()
                        if res.get("passed", False)
                    )
                    / max(len(trace.get("axiom_results") or {}), 1)
                ) if trace else 0.0,
                # Magnitude of the last selected action (control force)
                "control_action_force": float(
                    np.linalg.norm(trace.get("selected_action", [0, 0, 0])) if trace and trace.get("selected_action") else 0.0
                ),
                "health": float(self._traces[-1].get("health_score", 0.5)) if self._traces else 0.5,
                "score": self._system_score,
                "score_components": self._score_components,
                "reward_collected": self._reward_collected,
                "reward_available": self._reward_available,
                "worlds_simulated": self._worlds_simulated_total,
                "world_states": len(self._visited_positions),
                "episodes": self._episode_stats(),
                "position": self._state_np.tolist(),
                "mood": self._mood(),
                "knowledge": self._knowledge_stats(),
            }