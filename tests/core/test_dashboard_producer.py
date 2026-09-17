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
    monkeypatch.setattr(prod_mod, "DECISION_LOG_PATH", str(tmp_path / "decision_log.json"))
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


def test_producer_episode_worlds_accumulate_and_reset_on_goal(isolated_paths):
    """Audit C+D: the hero's rollout-states slot — _episode_worlds sums the
    real per-cycle worlds_simulated values (the exact accumulation _run_cycle
    performs) and RESETS when a goal is reached, mirroring the steps/moves
    episode clocks. The lifetime _worlds_simulated_total is untouched by the
    reset (monotone across episode boundaries); unmeasured episode averages
    stay None — the honest '—' state, never a fabricated 0.
    """
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        stats = p._episode_stats()
        assert stats["current_worlds"] == 0
        assert stats["last_worlds"] is None, "unmeasured until an episode completes"
        assert stats["avg_worlds_per_goal"] is None, "unmeasured until an episode completes"
        # Two real cycles: each adds its trace's worlds_simulated to BOTH
        # the episode counter and the lifetime total (line 836 pattern).
        p._worlds_simulated_total += int(5)
        p._episode_worlds += int(5)
        p._worlds_simulated_total += int(3)
        p._episode_worlds += int(3)
        stats = p._episode_stats()
        assert stats["current_worlds"] == 8
        # Goal reached: the episode's worlds are archived + reset.
        p._episode_steps = 10
        p._on_goal_reached()
        stats = p._episode_stats()
        assert stats["completed"] == 1
        assert stats["last_worlds"] == 8
        assert stats["avg_worlds_per_goal"] == 8.0
        assert stats["current_worlds"] == 0, "episode counter must reset at the goal"
        assert p._worlds_simulated_total == 8, "lifetime total never resets at an episode"
    finally:
        p.stop()


def test_producer_episode_worlds_follow_real_trace_field(isolated_paths):
    """Real cycles: _episode_worlds accumulates exactly the per-cycle
    worlds_simulated values the traces recorded — the hero slot reads the
    same real field the lifetime total sums, just windowed per episode.

    Goal-aware (flake-kill): the strict windowed equality holds only while
    the episode is OPEN (the window resets at each goal — the very behaviour
    under test, and this agent provably completes optimal 8/8 episodes). The
    final snapshot is branched on its own `completed`: open episode → exact
    trace-sum equality; a goal that landed meanwhile → structural invariants
    only (never a fabricated number on either path).
    """
    p = DashboardProducer(cycle_interval_s=0.05, burst_cycles=4)
    p.start()
    try:
        deadline = time.time() + 12
        while time.time() < deadline and p.snapshot()["decisions"] < 6:
            time.sleep(0.1)
        snap = p.snapshot()
        traces = snap["traces"]
        ep = snap["episodes"]
        assert traces, "real traces must exist"
        assert ep["current_worlds"] <= snap["worlds_simulated"], \
            "an episode window can never exceed the lifetime total"
        if ep["completed"] == 0:
            # No goal yet (isolated paths ⇒ no seeded history): the open
            # episode window spans every in-memory trace and the per-goal
            # averages are honestly unmeasured.
            assert ep["current_worlds"] == sum(
                int(t.get("worlds_simulated", 0) or 0) for t in traces
            ), "episode worlds must equal the real per-cycle trace sum"
            assert ep["avg_worlds_per_goal"] is None, \
                "no goal yet ⇒ average must be the honest unmeasured None"
        else:
            # A goal completed before the final snapshot: the window reset
            # at the goal (behaviour under test) — the episode archived its
            # totals and the current window started fresh.
            assert ep["last_worlds"] is not None, \
                "completed episode must archive its rollout total"
            assert ep["avg_worlds_per_goal"] is not None, \
                "completed episode makes the per-goal average measured"
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
                           "current_worlds", "last_worlds", "avg_worlds_per_goal",
                           "avg_steps_per_goal", "avg_moves_per_goal",
                           "efficiency_vs_optimal", "moves_efficiency_vs_optimal",
                           "optimal_steps", "optimal_moves"}
        assert ep["completed"] >= 0
        assert ep["current_steps"] >= 0
        # Audit C+D: the episode rollout counter is bounded by the lifetime
        # total (a window can never exceed the whole) and unmeasured episode
        # averages stay None — the honest '—' state.
        assert ep["current_worlds"] <= snap["worlds_simulated"]
        assert (ep["avg_worlds_per_goal"] is None) == (ep["completed"] == 0)
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

def test_legal_goal_step_optimal_legal_monotone_path():
    """The canonical legal-motion A* (telos_task.legal_goal_step — the
    function GridAdpt and GridSim both execute) plans the shortest legal
    path around the real blocked cells {(1,1),(2,2),(3,1)} toward (4,4);
    each step is cardinal, in-bounds, unblocked, and strictly reduces
    Manhattan distance (monotone). Ported from the producer's retired
    _astar_step duplicate (the verbatim executor no longer needs it)."""
    from telos_task import legal_goal_step
    blocked = {(1, 1), (2, 2), (3, 1)}
    goal = np.array([4.0, 4.0])
    fallback = np.array([0.0, 0.0])
    pos = np.array([0.0, 0.0])
    path = [(0, 0)]
    steps = 0
    while tuple(int(round(v)) for v in pos) != (4, 4):
        step = legal_goal_step(pos, blocked, goal, 5, fallback)
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


def test_legal_goal_step_deterministic_and_honest_noops():
    """Same state → same step (deterministic); at the goal or with no legal
    path the planner returns the fallback (honest no-op, never invented)."""
    from telos_task import legal_goal_step
    blocked = {(1, 1), (2, 2), (3, 1)}
    goal = np.array([4.0, 4.0])
    fallback = np.array([0.0, 0.0])
    pos = np.array([2.0, 0.0])
    s1 = legal_goal_step(pos, blocked, goal, 5, fallback)
    s2 = legal_goal_step(pos, blocked, goal, 5, fallback)
    assert (s1 == s2).all(), "A* must be deterministic"
    # Already at the goal → no-op.
    assert legal_goal_step(np.array([4.0, 4.0]), blocked, goal, 5, fallback) is fallback
    # Goal unreachable: all neighbours blocked.
    trapped = {(1, 0), (0, 1)}
    assert legal_goal_step(np.array([0.0, 0.0]), blocked | trapped, goal, 5, fallback) is fallback


def test_apply_action_executes_adapter_action_verbatim(isolated_paths):
    """_apply_action (live-loop plateau fix): the producer executes the
    pipeline's OWN adapter action verbatim through the same sim.transition
    the act phase uses for its predicted landing — the model and the world
    can never disagree about the executed step. Genuine no-ops stay put;
    a blocked landing stays put (transition returns s); a legal cardinal
    move lands exactly where the pipeline predicted."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=1)
    try:
        from telos_task import GridSim, DEFAULT_BLOCKED, DEFAULT_REWARDS, GOAL, GRID_SIZE
        p._sim = GridSim(blocked=set(DEFAULT_BLOCKED), rewards=dict(DEFAULT_REWARDS))
        p._grid_size = GRID_SIZE
        p._goal = GOAL
        state = np.array([0.0, 0.0])
        # Genuine no-op: unchanged (the decision is respected, never rewritten).
        out = p._apply_action(state, np.array([0.0, 0.0]))
        assert (out == state).all(), "no-op must stay put"
        # Legal cardinal move from the adapter: verbatim landing, in-bounds,
        # unblocked — exactly what the pipeline's predicted_state computes.
        out = p._apply_action(state, np.array([1.0, 0.0]))
        key = (int(round(out[0])), int(round(out[1])))
        assert tuple(key) == (1, 0), "verbatim cardinal move must land at (1,0)"
        assert key not in p._sim.blocked, "landed in a blocked cell"
        # A diagonal vector (the pre-fix adapter's shape, now impossible) is
        # routed by the sim: (0,0)+[1,1] -> (1,1) which IS blocked -> stays.
        # Honest: a vector that cannot be routed does not move the agent.
        out_d = p._apply_action(np.array([0.0, 0.0]), np.array([1.0, 1.0]))
        assert (out_d == np.array([0.0, 0.0])).all(), \
            "unroutable vector must stay put (blocked landing), never be rewritten"
        # A blocked landing: [1,0] from... (0,0) is fine; use [2,2] cell with
        # (-1,-1): (2,2)-(-1,-1)=(1,1) blocked -> stays put.
        out_b = p._apply_action(np.array([2.0, 2.0]), np.array([-1.0, -1.0]))
        assert (out_b == np.array([2.0, 2.0])).all(), "blocked landing must stay put"
        # Verbatim equality with the pipeline's predicted_state computation:
        # GridAdpt emits the action; the executor lands via sim.transition —
        # the exact same call the act phase makes for its honest prediction.
        from telos_task import GridAdpt
        adapter = GridAdpt()
        act = adapter.intent_to_action(
            type("I", (), {"intent_type": "bootstrap_navigate",
                           "params": {"action_vector": None},
                           "metadata": None})(), np.array([1.0, 0.0]), np.zeros(2))
        land = p._apply_action(np.array([1.0, 0.0]), act)
        assert (land == p._sim.transition(np.array([1.0, 0.0]), act)).all(), \
            "executor landing must equal the pipeline's predicted landing"
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


# ── Persistence throttling (pattern fix: no per-cycle 20MB churn) ─────

class TestPersistenceThrottle:
    def test_knowledge_payload_cached_not_reserialized_every_cycle(
            self, isolated_paths, monkeypatch):
        """The 56K-edge KG must NOT be re-serialized every 2s cycle: count
        serialize_knowledge calls and prove they are << cycles."""
        calls = {"n": 0}
        real = prod_mod.serialize_knowledge

        def counting(kg):
            calls["n"] += 1
            return real(kg)

        monkeypatch.setattr(prod_mod, "serialize_knowledge", counting)
        p = DashboardProducer(cycle_interval_s=0.25, burst_cycles=3,
                              checkpoint_every_n=100,
                              knowledge_serialize_interval=100)
        p.start()
        try:
            time.sleep(3.0)
            snap = p.snapshot()
            n_cycles = snap["decisions"]
            assert n_cycles >= 4, "producer must run real cycles"
            # cached: serialize once (first cycle) at most twice; never per-cycle
            assert calls["n"] <= 2, (
                f"serialize_knowledge called {calls['n']}x for {n_cycles} cycles"
            )
            assert snap["knowledge"]["edges"] >= 0
        finally:
            p.stop()

    def test_checkpoints_written_sparsely_not_per_cycle(self, isolated_paths):
        """Checkpoint writes follow checkpoint_every_n: cycle 1 seed + every N,
        never one 20MB file per 2s cycle."""
        p = DashboardProducer(cycle_interval_s=0.25, burst_cycles=3,
                              checkpoint_every_n=5,
                              knowledge_serialize_interval=100)
        p.start()
        try:
            time.sleep(4.5)
            snap = p.snapshot()
            n_cycles = snap["decisions"]
            cps = sorted(
                f for f in os.listdir(prod_mod.CHECKPOINT_DIR)
                if f.startswith("checkpoint_") and f.endswith(".json")
            )
            assert cps, "at least the cycle-1 seed checkpoint must exist"
            # sparse: expected = 1 seed + every 5 after
            expected = 1 + ((n_cycles - 1) // 5) if n_cycles > 1 else 1
            assert len(cps) <= expected, (
                f"{len(cps)} checkpoints for {n_cycles} cycles "
                f"(expected <= {expected}) — per-cycle writes are back"
            )
            # every checkpoint must be valid JSON with chain fields
            import json as _json
            for f in cps:
                raw = _json.load(open(os.path.join(prod_mod.CHECKPOINT_DIR, f)))
                assert "hmac" in raw
                assert "prev_checkpoint_hash" in raw
        finally:
            p.stop()

    def test_decision_log_wired_and_bounded(self, isolated_paths):
        """Producer feeds decision_log.json with real live traces (item 5:
        log=5 vs pipeline 28K+ gap closed) — bounded, lean, atomic."""
        p = DashboardProducer(cycle_interval_s=0.25, burst_cycles=3,
                              checkpoint_every_n=1,
                              knowledge_serialize_interval=1)
        p.start()
        try:
            time.sleep(3.0)
            assert os.path.exists(prod_mod.DECISION_LOG_PATH), (
                "decision log must be written by the producer"
            )
            with open(prod_mod.DECISION_LOG_PATH) as f:
                raw = json.load(f)
            assert raw["total_cycles"] > 0, "real entries recorded"
            assert len(raw["traces"]) == raw["total_cycles"]
            t = raw["traces"][0]
            # canonical schema contract (test_trace_schema aliases)
            assert "intent" in t or "selected_intent" in t
            assert "cycle_id" in t
            assert "decision_integrity" in t or "discrimination_index" in t
        finally:
            p.stop()


def test_stall_classifier_labels_stall_and_lockout(isolated_paths):
    """#3 stall-vs-lockout classifier: the SAME blocked loop reads "designed
    exploration stall (escape pending)" when a per-family escape counter is
    arming, but "LOCKED — escape counter not arming" when it is not (the
    [4,1] signature a human watching the dashboard must see: blocks continue
    but nothing arms). Driven at the classifier boundary against the REAL
    pipeline the producer builds — the counters it reads are the ones the
    escape machinery itself consults, never synthesized."""
    p = DashboardProducer(cycle_interval_s=0.4, burst_cycles=0)
    p._build()  # real pipeline internals (no cycles run — we control state)

    # ── LOCKED: blocked cycle, streak >= 2, ZERO arming counters ──
    trace = {"selected_action": None, "firewall_blocked": True,
             "decision_integrity": 0.3}
    p._pipeline._firewall._loop_blocks_by_type = {}
    p._pipeline._stagnant_no_action = {}
    p._pipeline._recovery_goal_seek_pending = False
    p._pipeline._recovery_stagnation_armed = False
    p._classify_stall(trace)   # streak -> 1 (transient, not yet LOCKED)
    second = p._classify_stall(trace)  # streak -> 2
    assert second["label"] == "locked", second
    assert second["status"] == "LOCKED — escape counter not arming"
    assert second["no_action_streak"] == 2
    assert second["escape_arming"]["firewall_max_loop_blocks"] == 0

    # ── STALL: the SAME blocked shape, but a family counter is arming
    #    (curiosity armed at 2 — blended's low_integrity block did NOT reset
    #    it, per-family #2) → the label flips to escape-pending ──
    p._pipeline._firewall._loop_blocks_by_type = {"curiosity_explore": 2}
    p._pipeline._stagnant_no_action = {"blended_inquiry": 3}
    stall = p._classify_stall(trace)
    assert stall["label"] == "stall", stall
    assert stall["status"] == "designed exploration stall (escape pending)"
    assert stall["escape_arming"]["firewall_max_loop_blocks"] == 2
    assert stall["families"]["firewall"] == {"curiosity_explore": 2}

    # ── ACTIVE: an emitted action resets the producer's no-action streak ──
    active = p._classify_stall({"selected_action": [1.0, 0.0],
                                "firewall_blocked": False})
    assert active["label"] == "active"
    assert active["no_action_streak"] == 0

    # ── the recovery-armed flag alone (no family streak yet) is still a
    #    STALL — the escape is pending, not locked ──
    p._pipeline._firewall._loop_blocks_by_type = {}
    p._pipeline._stagnant_no_action = {}
    p._pipeline._recovery_goal_seek_pending = True
    pending = p._classify_stall(trace)
    assert pending["label"] == "stall", pending
    assert pending["escape_arming"]["recovery_pending"] is True

    # ── the snapshot surfaces the classifier (measured, JSON-clean) ──
    snap = p.snapshot()
    assert snap["stall"]["label"] in ("active", "stall", "locked", "blocked", "unknown")
    p.stop()


def test_legal_goal_step_memoized_deterministic_and_invalidated():
    """v9: legal-motion A* is memoized per (start, goal, sorted-blocked,
    grid_size). Same inputs → cached identical result (determinism intact,
    cache never returns a step a fresh search would not); a CHANGED blocked
    set is a NEW key → a fresh, correct answer (never a stale cache)."""
    import telos_task

    fallback = np.zeros(2)
    s_a = telos_task.legal_goal_step(
        np.array([0.0, 0.0]), {(1, 1), (2, 2)}, np.array([4.0, 4.0]), 5, fallback)
    s_a2 = telos_task.legal_goal_step(
        np.array([0.0, 0.0]), {(1, 1), (2, 2)}, np.array([4.0, 4.0]), 5, fallback)
    assert np.array_equal(s_a, s_a2)
    assert telos_task._astar_first_step.cache_info().hits >= 1
    assert telos_task._astar_first_step.cache_info().maxsize <= 256
    s_b = telos_task.legal_goal_step(
        np.array([0.0, 0.0]), {(1, 0), (1, 1), (2, 2)}, np.array([4.0, 4.0]), 5, fallback)
    assert not np.array_equal(s_a, s_b)
    assert np.array_equal(s_b, np.array([0.0, 1.0]))
    assert telos_task._legal_cardinal_candidates.cache_info().maxsize <= 64
