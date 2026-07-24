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
from typing import Set, Dict, Tuple, Optional, List

logger = logging.getLogger('telos_task')

logging.basicConfig(level=logging.WARNING)

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.streams.inquiry_stream import InquiryStream
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
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

# ─── P0: Obstacles + Rewards + Terrain ──────────────────────────────────────────
DEFAULT_BLOCKED: Set[Tuple[int, int]] = {(1, 1), (2, 2), (3, 1)}
DEFAULT_REWARDS: Dict[Tuple[int, int], float] = {(0, 4): 10.0, (4, 0): 5.0}
GRID_SIZE = 5

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
    """
    max_retries = 3
    retry_delay = 2.0
    last_error = None

    for attempt in range(max_retries):
        try:
            conn = http.client.HTTPConnection("localhost", 11434, timeout=30)
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
                 rewards: Optional[Dict[Tuple[int, int], float]] = None):
        self.blocked = blocked or DEFAULT_BLOCKED
        self.rewards = rewards or DEFAULT_REWARDS
        self.position = np.array([0.0, 0.0])

    def initialize(self): pass
    def cleanup(self): pass

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
            diff = GOAL - pos
            step = np.sign(diff + np.random.randn(2) * 0.5).astype(float)
            key = (int(round(pos[0])), int(round(pos[1])))
            if key in self.blocked:
                step = np.array([0, 0])
            pos = np.clip(pos + step, 0, GRID_SIZE - 1)
            # Avoid landing on blocked cells
            if (int(round(pos[0])), int(round(pos[1]))) in self.blocked:
                pos = np.clip(pos - step * 0.5, 0, GRID_SIZE - 1)
            futures.append(World(state=pos.copy()))
        return futures

    def get_facts(self, s):
        dist = float(np.linalg.norm(GOAL - s))
        key = (int(round(s[0])), int(round(s[1])))
        reward = self.rewards.get(key, 0.0)
        near_reward = max(
            (v for k, v in self.rewards.items()
             if np.linalg.norm(np.array(k) - s) < 2.0),
            default=0.0,
        )
        terrain_here = TERRAIN.get(key, 'plains')
        cost = TERRAIN_COST.get(terrain_here, 1.0)
        return DomainFacts(
            state=s.copy(),
            resources={"distance": dist, "reward_near": near_reward, "terrain_cost": cost},
            constraints=["obstacle_near"] if any(
                np.linalg.norm(np.array(b) - s) < 1.5 for b in self.blocked
            ) else [],
            events=["on_reward"] if reward > 0 else [],
            metrics={"distance": dist, "uncertainty": 0.1, "reward": reward, "terrain_cost": cost},
            metadata={
                "position": s.tolist(), "goal": GOAL.tolist(),
                "blocked": [list(b) for b in self.blocked],
                "rewards": {str(k): v for k, v in self.rewards.items()},
                "terrain": {str(k): v for k, v in TERRAIN.items()},
                "current_terrain": terrain_here,
                "causal_edges": [
                    "position → distance",
                    "action → position",
                    "position → nearby_obstacles",
                    "position → terrain_type",
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


class GridAdpt(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x

    def intent_to_action(self, intent, state, md):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        diff = GOAL - state
        return np.sign(diff + np.random.randn(2) * 0.3).astype(float)

    @property
    def name(self): return "gridworld"


# ─── P1: ASCII Grid Rendering ───────────────────────────────────────────────

def render_grid(state: np.ndarray, blocked: Set[Tuple[int, int]],
                rewards: Dict[Tuple[int, int], float]) -> str:
    """Render a 5x5 grid with terrain, TELOS, goal, obstacles, and rewards."""
    lines = ["    0  1  2  3  4"]
    for y in range(GRID_SIZE):
        row = [f"  {y} "]
        for x in range(GRID_SIZE):
            pos = (x, y)
            terrain_emoji = TERRAIN_EMOJI.get(TERRAIN.get(pos, 'plains'), '·')
            if int(round(state[0])) == x and int(round(state[1])) == y:
                row.append("🔴T")
            elif (GOAL == np.array([x, y])).all():
                row.append("🟩G")
            elif pos in blocked:
                row.append("🧱 ")
            elif pos in rewards:
                row.append("⭐ ")
            else:
                row.append(terrain_emoji)
            row.append(" ")
        lines.append("".join(row))
    return "\n".join(lines)


# ─── P2: Benchmark Metrics ──────────────────────────────────────────────────

class BenchmarkMetrics:
    """Tracks and reports pipeline performance metrics across a session."""

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

    def record_step(self, result, trace):
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

    def mark_goal(self):
        self.goal_reached = True

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
        checkpoint_path=CHECKPOINT_DIR,
        knowledge_path=KNOWLEDGE_PATH,
        ledger_path="/tmp/telos_ledger.json",
        identity_path="/tmp/telos_identity.json",
        pattern_path="/tmp/telos_patterns.json",
    ))
    skill_lib = SkillLibrary()
    experience_mgr = ExperienceManager(
        skill_lib,
        ExperienceConfig(utility_threshold=0.1, index_interval=1),
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
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    memory_advisor = MemoryAdvisor(skill_lib)
    pipeline.register_validator(memory_advisor)
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

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
        grid = render_grid(state, sim.blocked, sim.rewards)
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
        metrics.record_step(result, trace)
        step_count += 1

        # Broadcast trace to live dashboard via WebSocket
        try:
            from telos.serve_dashboard import broadcast_trace_sync, websocket_clients
            if websocket_clients:
                trace_dict = trace.to_dict() if hasattr(trace, 'to_dict') else trace
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

        dist = np.linalg.norm(GOAL - state)
        if dist < 0.5:
            print(f"\n✅ GOAL REACHED in {step_count} steps!")
            print(render_grid(state, sim.blocked, sim.rewards))
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
