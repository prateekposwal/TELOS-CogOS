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
"""

import json
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

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
KNOWLEDGE_PATH = "/tmp/telos_knowledge.json"
LEDGER_PATH = "/tmp/telos_ledger.json"
IDENTITY_PATH = "/tmp/telos_identity.json"
PATTERN_PATH = "/tmp/telos_patterns.json"

CYCLE_INTERVAL_S = 2.0   # live cadence between steady-state cycles
BURST_CYCLES = 5         # warm-up cycles at boot so graphs fill within seconds
MAX_TRACES_IN_MEMORY = 200


def serialize_knowledge(kg: Any) -> Dict[str, list]:
    """Map a live KnowledgeGraph into the dashboard API shape.

    Mirrors serve_dashboard._load_knowledge's disk parsing so the API
    returns the same honest shape whether it reads live memory or cold
    files. Nodes: id/label/domain/importance. Edges: source/target/
    weight/edge_type — only what the graph actually holds.

    Args:
        kg: the KnowledgeGraph instance (may be None).
    """
    if kg is None:
        return {"nodes": [], "edges": []}
    nodes_raw = getattr(kg, "_nodes", {}) or {}
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
    return {"nodes": nodes, "edges": edges}


class DashboardProducer:
    """Runs the real GridWorld pipeline on a background thread and holds
    a thread-safe runtime snapshot that the dashboard APIs read.

    Honesty contract: every number in the snapshot is a measured value
    from an actual pipeline cycle. When the pipeline cannot run (import
    failure, repeated crash), the producer records the error and the
    dashboard renders the honest empty/history state.
    """

    def __init__(self, cycle_interval_s: float = CYCLE_INTERVAL_S,
                 burst_cycles: int = BURST_CYCLES):
        self._cycle_interval_s = max(0.5, float(cycle_interval_s))
        self._burst_cycles = max(1, int(burst_cycles))
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
        return {
            "nodes": len(payload.get("nodes", [])),
            "edges": len(payload.get("edges", [])),
            "domains": domains,
            "edge_types": edge_types,
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
        from telos_task import GridAdpt, GridSim, TERRAIN, DEFAULT_BLOCKED, DEFAULT_REWARDS
        from telos.core.runtime import PipelineConfig, TelosV14Pipeline
        from telos.core.streams.implementations import (
            ReflexStream, PerceptionStream, MemoryStream, PlanningStream, TheoryStream,
        )
        from telos.core.streams.inquiry_stream import InquiryStream
        from telos.core.council.validators import (
            RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
        )
        from telos.core.ledger.skill_library import SkillLibrary
        from telos.core.ledger.experience_manager import ExperienceManager, ExperienceConfig
        from telos.core.simulation import CounterfactualEngine
        from telos_task import GridAgent

        self._sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
        self._grid_size = 5  # GridWorld GRID_SIZE
        self._grid_area = float(self._grid_size ** 2)
        # Total positive reward available in the world - the denominator of
        # the reward component of the System Score (a world constant, real).
        self._reward_available = float(sum(v for v in DEFAULT_REWARDS.values() if v and v > 0))
        self._pipeline = TelosV14Pipeline(PipelineConfig(
            adapter=GridAdpt(), simulator=self._sim,
            compute_budget_ms=100.0, state_dim=2, n_worlds=10, horizon=5,
            checkpoint_path=CHECKPOINT_DIR,
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

    def _run_cycle(self) -> None:
        trace_dict: Optional[Dict] = None
        with self._lock:
            result = self._pipeline.execute(self._state_np, user_name="Prateek")
            self._cycles += 1
            trace = result.decision_trace
            self._experience_mgr.observe(result)

            # Real world dynamics (same as telos_task.py main loop).
            terrain_changes = self._sim.maybe_shift_terrain()
            if trace is not None and trace.selected_action is not None and not result.firewall_blocked:
                self._state_np = self._apply_action(self._state_np, trace.selected_action)

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

            # Persist knowledge (nodes AND edges) so cold-file readers + the
            # no-producer fallback always see the latest graph.
            try:
                kg = self._pipeline.infra_manager.knowledge
                kg.save(KNOWLEDGE_PATH)
            except Exception as e:
                logger.warning("producer: knowledge persist failed: %r", e)

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

            self._knowledge_payload = json_clean(serialize_knowledge(self._pipeline.infra_manager.knowledge))
            self._worlds_simulated_total += int(trace.worlds_simulated if trace else 0)
            self._last_cycle_at = time.time()

            # Goal reached → reset to origin for a continuous live run.
            if trace is not None and trace.selected_action is not None and self._sim.terminal(self._state_np):
                self._state_np = np.array([0.0, 0.0])

        # Broadcast OUTSIDE the lock (network I/O must not stall the cycle).
        if trace_dict is not None:
            self._broadcast_trace(trace_dict)

    def _apply_action(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Legal-route executor for the selected action.

        The pipeline's adapter emits diagonal/no-op vectors
        (np.sign(goal - state)) that GridSim.transition cannot route
        around blocked cells — a genuine no-op leaves the agent parked
        at the origin forever, which hides the live run. This executor
        decomposes a non-zero action into the dominant legal cardinal
        move (same intent direction, routed legally), and honours true
        no-ops (stay put). Deterministic: no randomness is introduced.
        """
        a = np.asarray(action, dtype=float)
        if a.shape != (2,):
            return state
        if abs(a[0]) < 0.05 and abs(a[1]) < 0.05:
            return state  # genuine no-op — respect the decision
        legal = self._sim.legal_transitions(state)
        if not legal:
            return state
        # Candidate destinations: legal moves CLIPPED to the grid and
        # verified against blocked cells (legal_transitions returns raw
        # vectors; the destination is the clipped position).
        destinations = []
        for lv in legal:
            dest = np.clip(state + np.asarray(lv, dtype=float), 0, self._grid_size - 1)
            if self._is_blocked(dest):
                continue
            destinations.append(dest)
        if not destinations:
            return state
        # Dominant axis of the selected action first, then the other axis.
        candidates = []
        if abs(a[0]) >= abs(a[1]):
            candidates.append(np.array([np.sign(a[0]), 0.0]))
            candidates.append(np.array([0.0, np.sign(a[1])]))
        else:
            candidates.append(np.array([0.0, np.sign(a[1])]))
            candidates.append(np.array([np.sign(a[0]), 0.0]))
        # Score each destination by alignment with the selected action.
        best_dest = destinations[0]
        best_score = -1e9
        for dest in destinations:
            align = float(np.dot(dest - state, a))
            if align > best_score:
                best_score = align
                best_dest = dest
        return best_dest

    def _is_blocked(self, pos: np.ndarray) -> bool:
        key = (int(round(pos[0])), int(round(pos[1])))
        return key in self._sim.blocked

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

    def _prune_aux_files(self) -> None:
        """Keep the checkpoint dir bounded (aux files are not checkpoint-rotated)."""
        import glob as _glob
        for pattern, keep in (("system_self_*.json", 20), ("patterns_*.json", 20)):
            files = sorted(_glob.glob(os.path.join(CHECKPOINT_DIR, pattern)))
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
                "health": float(self._traces[-1].get("health_score", 0.5)) if self._traces else 0.5,
                "score": self._system_score,
                "score_components": self._score_components,
                "reward_collected": self._reward_collected,
                "reward_available": self._reward_available,
                "worlds_simulated": self._worlds_simulated_total,
                "world_states": len(self._visited_positions),
                "position": self._state_np.tolist(),
                "mood": self._mood(),
                "knowledge": self._knowledge_stats(),
            }
