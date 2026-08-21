"""Live-data producer tests: the dashboard PRODUCES the data it serves.

Pattern under test: a dashboard must produce or attach to a live producer —
never read cold files that nothing writes. And everything the producer
exposes must be REAL (measured) data, JSON-clean, and persisted with edges.
"""
import json
import os
import tempfile
import time

import numpy as np
import pytest

import telos.dashboard.producer as prod_mod
from telos.dashboard.producer import DashboardProducer, json_clean


@pytest.fixture()
def isolated_paths(tmp_path, monkeypatch):
    """Point the producer at temp paths so tests never touch /tmp/telos_*.

    Args:
        tmp_path: pytest temp dir.
        monkeypatch: pytest monkeypatch for producer module globals.
    """
    monkeypatch.setattr(prod_mod, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    monkeypatch.setattr(prod_mod, "PRODUCER_STATE_PATH", str(tmp_path / "producer_state.json"))
    monkeypatch.setattr(prod_mod, "KNOWLEDGE_PATH", str(tmp_path / "knowledge.json"))
    monkeypatch.setattr(prod_mod, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(prod_mod, "IDENTITY_PATH", str(tmp_path / "identity.json"))
    monkeypatch.setattr(prod_mod, "PATTERN_PATH", str(tmp_path / "patterns.json"))
    return tmp_path


def test_producer_runs_real_cycles_and_populates_everything(isolated_paths):
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=3)
    p.start()
    try:
        time.sleep(2.5)  # burst + a couple of steady cycles
        snap = p.snapshot()
        assert snap["decisions"] >= 3, "producer must run real cycles"
        assert snap["traces"], "real traces must be recorded"
        assert snap["di"] >= 0.0 and snap["md"] >= 0.0, "measured DI/MD"
        assert snap["mood"] in ("neutral", "confident", "curious", "cautious",
                                "reflective", "engaged", "testing_boundaries",
                                "determined") or isinstance(snap["mood"], str)
        # Knowledge graph: real nodes AND edges
        assert snap["knowledge"]["nodes"] > 0, "knowledge nodes from real runs"
        assert snap["knowledge"]["edges"] > 0, "edges from real runs"
        assert snap["knowledge"]["domains"], "per-domain stats"
        # Position stays inside the 5x5 grid
        pos = snap["position"]
        assert 0 <= pos[0] <= 4 and 0 <= pos[1] <= 4, "agent must stay in bounds"
        # Recent decisions carry real intents
        assert snap["recent_decisions"], "story decisions present"
        assert snap["recent_decisions"][-1]["cycle_id"] == snap["decisions"]
    finally:
        p.stop()
    assert not p.is_running


def test_producer_persists_knowledge_with_edges(isolated_paths):
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=3)
    p.start()
    try:
        time.sleep(2.5)
        assert os.path.exists(prod_mod.KNOWLEDGE_PATH), "knowledge persisted"
        with open(prod_mod.KNOWLEDGE_PATH) as f:
            raw = json.load(f)
        assert len(raw.get("nodes", {})) > 0, "persisted nodes"
        assert len(raw.get("edges", {})) > 0, "persisted edges — the edge layer"
        # Checkpoints written per cycle
        cps = os.listdir(prod_mod.CHECKPOINT_DIR)
        assert any(c.startswith("checkpoint_") for c in cps), "checkpoints written"
    finally:
        p.stop()


def test_producer_checkpoints_are_json_clean_and_serializable(isolated_paths):
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=2)
    p.start()
    try:
        time.sleep(2.0)
        snap = p.snapshot()
        for t in snap["traces"]:
            # json_clean output must round-trip through strict json.dumps
            json.dumps(json_clean(t), allow_nan=False)
        # The API-serialized knowledge payload must be strict-JSON clean too
        json.dumps(snap["knowledge_payload"], allow_nan=False)
    finally:
        p.stop()


def test_producer_no_fabrication_snapshot_counts_match_cycles(isolated_paths):
    """Honesty: snapshot numbers must equal measured cycle counts, never
    invented larger values. The trace-list equality holds in a clean
    session (this fixture isolates paths, so no restore happens); when the
    producer restores counters from persisted state (Item 5c) the in-memory
    trace list is a bounded window of the history, so the invariant is
    traces <= decisions — the hero number is never inflated by traces."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=2)
    p.start()
    try:
        time.sleep(2.0)
        snap = p.snapshot()
        assert snap["decisions"] == snap["producer"]["cycles"]
        assert len(snap["traces"]) <= snap["decisions"]
        assert len(snap["recent_decisions"]) <= len(snap["traces"])
    finally:
        p.stop()


def test_json_clean_converts_numpy_and_nan():
    assert json_clean(np.float64(1.5)) == 1.5
    assert json_clean(np.bool_(True)) is True
    assert json_clean(np.array([1.0, 2.0])) == [1.0, 2.0]
    assert json_clean(float("nan")) is None
    assert json_clean(float("inf")) is None
    d = json_clean({"a": np.float64(2.0), "b": float("nan"), "c": [np.int64(3)]})
    assert d == {"a": 2.0, "b": None, "c": [3]}


def test_serialize_knowledge_shapes_nodes_and_edges():
    from telos.core.knowledge.graph import KnowledgeGraph
    kg = KnowledgeGraph()
    n1 = kg.record("navigation", "move_to_1_0", 0.9, provenance={"source": "test", "cycle": 1, "caller": "test"})
    n2 = kg.record("gridworld", "terrain_forest", 1.0, provenance={"source": "test", "cycle": 1, "caller": "test"})
    kg.add_edge(n1, n2, edge_type="at_location", weight=0.8)
    payload = prod_mod.serialize_knowledge(kg)
    assert len(payload["nodes"]) == 2
    assert payload["nodes"][0]["id"] and payload["nodes"][0]["label"]
    assert payload["edges"][0]["source"] == n1
    assert payload["edges"][0]["edge_type"] == "at_location"


def test_producer_score_is_bounded_system_score(isolated_paths):
    """The headline metric is a bounded 0-100 composite of measured signals,
    never a timer: after real cycles the score is in range, the components
    are exposed, and the score equals the formula re-evaluated from the
    same components (integrity: no invented number)."""
    from telos.dashboard.producer import system_score

    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=3)
    p.start()
    try:
        time.sleep(2.5)
        snap = p.snapshot()
        assert snap["decisions"] >= 3
        assert snap["score"] is None or (0.0 <= snap["score"] <= 100.0), \
            f"score {snap['score']} outside the defined range"
        assert snap["score_components"] is not None, "components must be exposed"
        c = snap["score_components"]
        assert set(c["weights"]) == {"di", "md", "reward", "coverage"}
        # Re-evaluate the formula from the SAME components the producer used.
        recomputed = system_score(
            di=c["di"], md=c["md"],
            reward_collected=snap["reward_collected"],
            reward_available=snap["reward_available"],
            world_states=snap["world_states"],
            grid_area=c["grid_area"],
        )
        assert abs(snap["score"] - recomputed) < 0.01, \
            f"displayed score {snap['score']} != recomputed {recomputed}"
        # Every trace score is bounded too (old-format scores are rejected).
        for t in snap["traces"]:
            s = t.get("score")
            assert s is None or (0.0 <= s <= 100.0), f"trace score {s} out of range"
    finally:
        p.stop()


def test_producer_score_before_first_cycle_is_none(isolated_paths):
    """Honest empty state: before any cycle there is no score, not a fake
    100 or a fabricated neutral number."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    assert p.snapshot()["score"] is None
    assert p.snapshot()["score_components"] is None
    p.stop()


def test_producer_episode_bookkeeping_counts_and_resets(isolated_paths):
    """Goal-reach wiring: _on_goal_reached increments the episode counter,
    records the episode's step count, and resets the current-step counter.

    ZERO sim mutation: episode bookkeeping never touches the sim's reward
    dict — it only counts events the producer already observes (the same
    terminal() the reset path uses)."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        stats = p._episode_stats()
        assert stats["completed"] == 0
        assert stats["avg_steps_per_goal"] is None, "unmeasured until an episode completes"
        assert stats["efficiency_vs_optimal"] is None, "unmeasured until an episode completes"
        assert stats["optimal_steps"] == 8.0, "Manhattan distance (0,0)->(4,4)"
        p._episode_steps = 12
        p._on_goal_reached()
        stats = p._episode_stats()
        assert stats["completed"] == 1
        assert stats["last_steps"] == 12
        assert stats["avg_steps_per_goal"] == 12.0
        assert stats["efficiency_vs_optimal"] == pytest.approx(round(8.0 / 12.0, 4))
        assert stats["current_steps"] == 0, "step counter resets for the next episode"
    finally:
        p.stop()


def test_producer_episode_stats_real_run_shape_and_no_reward_mutation(isolated_paths):
    """Real cycles: the episodes payload is present, honest, and the sim's
    reward dict is never mutated by the metric — the live pool only ever
    decreases from the initial 20.0 as TELOS collects it (no respawn)."""
    p = DashboardProducer(cycle_interval_s=0.05, burst_cycles=4)
    p.start()
    try:
        deadline = time.time() + 12
        while time.time() < deadline and p.snapshot()["decisions"] < 8:
            time.sleep(0.1)
        snap = p.snapshot()
        ep = snap["episodes"]
        assert set(ep) == {"completed", "current_steps", "current_moves",
                           "last_steps", "last_moves",
                           "avg_steps_per_goal", "avg_moves_per_goal",
                           "efficiency_vs_optimal", "moves_efficiency_vs_optimal",
                           "optimal_steps", "optimal_moves"}
        assert ep["completed"] >= 0
        assert ep["current_steps"] >= 0
        if ep["completed"] > 0:
            # Can't beat the Manhattan optimum (>= 8 decision steps); the
            # efficiency ratio is bounded [0, 1] when defined.
            assert ep["avg_steps_per_goal"] >= 8.0
            assert 0.0 <= ep["efficiency_vs_optimal"] <= 1.0
        # Honesty: unmeasured stays None until the first episode completes.
        assert (ep["avg_steps_per_goal"] is None) == (ep["completed"] == 0)
        # ZERO sim mutation: the live reward pool never increases.
        total = sum(v for v in p._sim.rewards.values() if v and v > 0)
        assert total <= 20.0 + 1e-9, f"reward pool grew to {total} — sim mutated"
    finally:
        p.stop()


# ═══════════════════════════════════════════════════════════════════════
# Item 3 — BFS/A* legal-route executor (replaces the greedy diagonal
# decomposition): every approved cycle that can move makes monotone progress
# over the REAL 5x5 legal grid (blocked cells from the live sim). Deterministic,
# bounds-safe, honest no-op for immovable states.
# ═══════════════════════════════════════════════════════════════════════

def test_astar_step_finds_optimal_legal_monotone_path():
    """A* plans the shortest legal path around the real blocked cells
    {(1,1),(2,2),(3,1)} toward (4,4); each step is cardinal, in-bounds,
    unblocked, and strictly reduces Manhattan distance (monotone)."""
    from telos.dashboard.producer import _astar_step
    blocked = {(1, 1), (2, 2), (3, 1)}
    goal = np.array([4.0, 4.0])
    fallback = np.array([0.0, 0.0])
    pos = np.array([0.0, 0.0])
    path = [(0, 0)]
    steps = 0
    while tuple(int(round(v)) for v in pos) != (4, 4):
        step = _astar_step(pos, blocked, goal, 5, fallback)
        assert abs(step[0]) + abs(step[1]) == 1, f"non-cardinal step {step}"
        nxt = pos + step
        key = (int(round(nxt[0])), int(round(nxt[1])))
        assert 0 <= key[0] < 5 and 0 <= key[1] < 5, f"out of bounds {key}"
        assert key not in blocked, f"entered blocked cell {key}"
        # Monotone progress: Manhattan distance to the goal strictly drops.
        mh = abs(key[0] - 4) + abs(key[1] - 4)
        assert mh < abs(path[-1][0] - 4) + abs(path[-1][1] - 4), "no progress"
        path.append(key)
        pos = nxt
        steps += 1
        assert steps <= 10, "path is not optimal"
    assert path == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
                    (4, 1), (4, 2), (4, 3), (4, 4)], f"unexpected path {path}"
    assert steps == 8, "Manhattan optimum must be reachable legally"


def test_astar_step_deterministic_and_honest_noops():
    """Same state → same step (deterministic); at the goal or with no legal
    path the executor returns the fallback (honest no-op, never invented)."""
    from telos.dashboard.producer import _astar_step
    blocked = {(1, 1), (2, 2), (3, 1)}
    goal = np.array([4.0, 4.0])
    fallback = np.array([0.0, 0.0])
    pos = np.array([2.0, 0.0])
    s1 = _astar_step(pos, blocked, goal, 5, fallback)
    s2 = _astar_step(pos, blocked, goal, 5, fallback)
    assert (s1 == s2).all(), "A* must be deterministic"
    # Already at the goal → no-op.
    assert _astar_step(np.array([4.0, 4.0]), blocked, goal, 5, fallback) is fallback
    # Trapped state with no path (fully walled) → honest no-op.
    walled = {(x, y) for x in range(5) for y in range(5) if (x, y) != (0, 0) and (x, y) != (4, 4)}
    # Goal unreachable: all neighbours blocked.
    trapped = {(1, 0), (0, 1)}
    assert _astar_step(np.array([0.0, 0.0]), blocked | trapped, goal, 5, fallback) is fallback


def test_apply_action_preserves_genuine_noop_and_plans_legally(isolated_paths):
    """_apply_action: zero vectors stay put (respect the decision), non-zero
    vectors become the first legal A* step — in-bounds and unblocked."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        from telos_task import GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS
        p._sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
        p._grid_size = 5
        from telos_task import GOAL
        p._goal = GOAL
        state = np.array([0.0, 0.0])
        # Genuine no-op: unchanged.
        out = p._apply_action(state, np.array([0.0, 0.0]))
        assert (out == state).all(), "no-op must stay put"
        # Legal plan from the origin (blocked cells read from the live sim).
        out = p._apply_action(state, np.array([1.0, 1.0]))
        key = (int(round(out[0])), int(round(out[1])))
        assert 0 <= key[0] < 5 and 0 <= key[1] < 5, "out of bounds"
        assert key not in p._sim.blocked, "planned into a blocked cell"
        assert tuple(int(v) for v in out) == (1, 0), "A* first step from (0,0)"
    finally:
        p.stop()


# ═══════════════════════════════════════════════════════════════════════
# Item 2 — moves-per-goal split: the episode `moves` counter increments ONLY
# when the agent actually changed position (never on blocked/no-op/inquiry).
# ═══════════════════════════════════════════════════════════════════════

def test_producer_episode_moves_bookkeeping_counts_real_moves_only(isolated_paths):
    """_on_goal_reached records the moves split alongside steps, and the
    stats payload exposes avg_moves_per_goal bounded by avg_steps_per_goal
    (moves ⊆ cycles — a move can never exceed its episode's cycles)."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        stats = p._episode_stats()
        assert stats["avg_moves_per_goal"] is None, "unmeasured until an episode completes"
        p._episode_steps = 12
        p._episode_moves = 7   # 5 cycles were blocked/inquiry/no-op pauses
        p._on_goal_reached()
        stats = p._episode_stats()
        assert stats["completed"] == 1
        assert stats["last_steps"] == 12
        assert stats["last_moves"] == 7
        assert stats["avg_steps_per_goal"] == 12.0
        assert stats["avg_moves_per_goal"] == 7.0
        assert stats["optimal_moves"] == 8.0, "optimal episode = all cycles are moves"
        assert stats["current_steps"] == 0 and stats["current_moves"] == 0, \
            "both clocks reset for the next episode"
    finally:
        p.stop()


def test_producer_real_run_moves_never_exceed_cycles(isolated_paths):
    """Real cycles: moves-per-goal is present and bounded by steps-per-goal
    (a position change is a subset of decision cycles)."""
    p = DashboardProducer(cycle_interval_s=0.05, burst_cycles=4)
    p.start()
    try:
        deadline = time.time() + 12
        while time.time() < deadline and p.snapshot()["decisions"] < 8:
            time.sleep(0.1)
        snap = p.snapshot()
        ep = snap["episodes"]
        assert "avg_moves_per_goal" in ep
        if ep["completed"] > 0 and ep["avg_moves_per_goal"] is not None:
            assert ep["avg_moves_per_goal"] <= ep["avg_steps_per_goal"] + 1e-9
        assert ep["current_moves"] <= ep["current_steps"]
    finally:
        p.stop()


# ═══════════════════════════════════════════════════════════════════════
# Item 5c — hero counters survive restarts: exact state file first, then the
# newest checkpoint as an honest best-effort baseline + trace seeding.
# ═══════════════════════════════════════════════════════════════════════

def test_producer_restores_exact_counters_from_state_file(isolated_paths, monkeypatch):
    """The producer state file (written every cycle) restores the EXACT hero
    counters on boot — the totals never reset to 0 across a dashboard restart.

    Args:
        isolated_paths: pytest tmp_path fixture for isolated state files.
        monkeypatch: pytest fixture used to redirect PRODUCER_STATE_PATH."""
    import telos.dashboard.producer as prod_mod
    state_path = str(isolated_paths / "producer_state.json")
    monkeypatch.setattr(prod_mod, "PRODUCER_STATE_PATH", state_path)
    with open(state_path, "w") as fh:
        json.dump({"cycles": 41, "worlds_simulated_total": 3137, "updated_at": 1.0}, fh)
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        p._restore_producer_counters()
        assert p._cycles == 41, "cycles must restore from the exact state file"
        assert p._worlds_simulated_total == 3137, "worlds_simulated must restore exactly"
    finally:
        p.stop()


def test_producer_restores_counters_from_checkpoint_fallback(isolated_paths):
    """No state file → the newest checkpoint's cycle becomes the honest
    baseline and its real decision trace seeds the story (never invented)."""
    cp_dir = isolated_paths / "checkpoints"
    cp_dir.mkdir()
    for cyc, ws in ((9, 100), (10, 120)):
        with open(cp_dir / f"checkpoint_{cyc}.json", "w") as fh:
            json.dump({
                "cycle": cyc,
                "decision_trace": {"cycle_id": cyc, "decision_integrity": 0.9,
                                   "mission_drift": 0.1, "council_validated": True,
                                   "selected_intent": {"type": "navigate_to_goal", "confidence": 0.7}},
            }, fh)
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        p._restore_producer_counters()
        assert p._cycles == 10, "baseline must come from the newest checkpoint"
        assert p._traces, "real persisted traces must seed the story"
        assert p._traces[-1]["cycle_id"] == 10
        # worlds_simulated is NOT persisted in legacy checkpoint traces —
        # it honestly starts at 0 rather than inventing a value.
        assert p._worlds_simulated_total == 0
    finally:
        p.stop()


def test_producer_persists_counter_state_after_cycles(isolated_paths, monkeypatch):
    """Every cycle writes the exact counters to the state file — the same
    file _restore_producer_counters reads on the next boot.

    Args:
        isolated_paths: pytest tmp_path fixture for isolated state files.
        monkeypatch: pytest fixture used to redirect PRODUCER_STATE_PATH."""
    import telos.dashboard.producer as prod_mod
    state_path = str(isolated_paths / "producer_state.json")
    monkeypatch.setattr(prod_mod, "PRODUCER_STATE_PATH", state_path)
    p = DashboardProducer(cycle_interval_s=0.05, burst_cycles=3)
    p.start()
    try:
        deadline = time.time() + 8
        while time.time() < deadline and p.snapshot()["decisions"] < 4:
            time.sleep(0.1)
        assert os.path.exists(state_path), "state file must be written"
        with open(state_path) as fh:
            state = json.load(fh)
        assert state["cycles"] == p.snapshot()["decisions"]
        assert state["worlds_simulated_total"] == p.snapshot()["worlds_simulated"]
    finally:
        p.stop()


# ═══════════════════════════════════════════════════════════════════════
# LEFT ITEM 1 — faithful DI aggregation. The dashboard's health mood/DI must
# be a FAITHFUL read of the real recent decision trace — never a misleading
# aggregate (e.g. an average that only counts blocked cycles, or numpy-float
# pollution, or a stale/other-cycle value). This locks the "aggregation is
# honest" half of the DI investigation.
# ═══════════════════════════════════════════════════════════════════════

def test_producer_health_di_matches_last_real_trace(isolated_paths):
    """The headline DI surfaced by /api/health and /api/overview must equal
    the LAST real decision trace's `decision_integrity` — a direct, faithful
    read of the actually-executed cycle. It must NEVER be an average of
    blocked/no-op cycles, a stale cycle, or a numpy scalar that cannot
    serialize. If the last trace really was low-DI, the dashboard is
    HONESTLY showing real degradation — not an artifact to paper over."""
    p = DashboardProducer(cycle_interval_s=0.05, burst_cycles=4)
    p.start()
    try:
        deadline = time.time() + 12
        while time.time() < deadline and p.snapshot()["decisions"] < 5:
            time.sleep(0.1)
        snap = p.snapshot()
        assert snap["traces"], "producer must have real traces"
        last = snap["traces"][-1]
        # Health/overview DI is the last trace's DI, JSON-clean (plain float).
        assert snap["di"] == last["decision_integrity"],             "health DI must equal the last real trace DI (faithful)"
        assert isinstance(snap["di"], float), "DI must be a plain float, never numpy"
        ov = p.overview_payload()
        assert ov["di"] == last["decision_integrity"],             "overview DI must equal the last real trace DI (faithful)"
        # The trace sequence itself is the ground truth: the headlines aggregate
        # the actual recent DIs we expose, not a different/fabricated window.
        recent = snap["recent_decisions"]
        assert recent, "story recent-decisions must be present"
        assert recent[-1]["di"] == last["decision_integrity"]
    finally:
        p.stop()
