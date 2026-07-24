"""
TELOS RPS Server — Rock Paper Scissors with TELOS reasoning + identity memory.

TELOS uses its 7-phase Pipeline to reason about each move, showing
stream selection, simulation futures, council verdict, and DI/MD.

Run:  PYTHONPATH=. python3 telos_rps_server.py
Then:  http://localhost:8000
"""

import numpy as np
import logging
import json
import uuid
from typing import Dict, List, Optional

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn

from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.base import Validator, ValidationSignal
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR
from telos.core.coordination.coordinator import PipelineCoordinator, SubPipelineConfig

RPS_MOVES = {0: "rock", 1: "paper", 2: "scissors"}
RPS_VEC = {
    "rock": np.array([1, 0, 0]),
    "paper": np.array([0, 1, 0]),
    "scissors": np.array([0, 0, 1]),
}
MOVE_NAMES = ["rock", "paper", "scissors"]

BEATS = {0: 2, 1: 0, 2: 1}  # move X beats move Y (rock→scissors, paper→rock, scissors→paper)
COUNTER = {0: 1, 1: 2, 2: 0}  # opponent played X → I play COUNTER[X] to beat it (rock→paper, paper→scissors, scissors→rock)

def winner(telos_move: int, user_move: int) -> str:
    if telos_move == user_move:
        return "tie"
    if BEATS[telos_move] == user_move:
        return "telos"
    return "user"

class OpponentSwitchDetector(Validator):
    """Council validator that detects opponent pattern switches.

    Tracks recent opponent moves and blocks when a pattern shift is detected,
    forcing TELOS to re-evaluate rather than exploit a stale model (Λ4.5).
    When blocked, the play handler resets EMA to neutral for rapid adaptation.
    """

    def __init__(self, window: int = 3):
        self._recent: List[int] = []
        self._window = window
        self._switch_count = 0

    @property
    def name(self) -> str:
        return "OpponentSwitchDetector"

    def record_move(self, move_idx: int) -> None:
        self._recent.append(move_idx)
        if len(self._recent) > self._window * 3:
            self._recent = self._recent[-(self._window * 3):]

    @property
    def switch_detected(self) -> bool:
        if len(self._recent) < self._window:
            return False
        recent = self._recent[-self._window:]
        distinct = len(set(recent))
        if distinct >= 3:
            return True
        if distinct == 2 and recent[-1] != recent[-2]:
            return True
        return False

    def validate(self, world, intent, domain_facts):
        if len(self._recent) < self._window:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.8,
                reason=f"building pattern history ({len(self._recent)}/{self._window})",
                evidence_weight=0.05,
            )
        recent = self._recent[-self._window:]
        distinct = len(set(recent))

        # Λ4.3: Check if the Markov matrix has learned transitions.
        # If domain_facts reports a Markov prediction with confidence > 0.5,
        # the opponent is following a predictable sequence (even if cycling).
        # Only block on actual pattern transitions, not steady-state sequences.
        markov_conf = 0.0
        if domain_facts and domain_facts.metrics:
            markov_conf = domain_facts.metrics.get("markov_next_confidence", 0.0)

        if distinct >= 3:
            if markov_conf > 0.5:
                return ValidationSignal(
                    validator_name=self.name, passed=True, confidence=0.7,
                    reason=f"opponent cycling — Markov confidence={markov_conf:.2f}",
                    evidence_weight=0.15,
                )
            self._switch_count += 1
            return ValidationSignal(
                validator_name=self.name, passed=False, confidence=0.5,
                reason=f"opponent switching rapidly — recent moves: {[MOVE_NAMES[m] for m in recent]}",
                evidence_weight=0.35,
            )
        if distinct == 2 and recent[-1] != recent[-2]:
            if markov_conf > 0.5:
                return ValidationSignal(
                    validator_name=self.name, passed=True, confidence=0.7,
                    reason=f"opponent switching predictably — Markov confidence={markov_conf:.2f}",
                    evidence_weight=0.15,
                )
            self._switch_count += 1
            return ValidationSignal(
                validator_name=self.name, passed=False, confidence=0.6,
                reason=f"opponent pattern switch: {MOVE_NAMES[recent[-2]]} → {MOVE_NAMES[recent[-1]]}",
                evidence_weight=0.35,
            )
        stable_move = MOVE_NAMES[recent[-1]]
        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.9,
            reason=f"opponent pattern stable ({stable_move})",
            evidence_weight=0.1,
        )


class RPSSimulator(DomainSimulator):
    """TELOS reasons about RPS by counterfactual simulation.

    Models two opponent types (Λ4.3 Possibility Preservation):
    - Static Markov: samples from P(next | last) transition matrix
    - Adaptive: predicts TELOS's move and counters it (2-step lookahead)
    """

    def __init__(self):
        self._telos_history: List[int] = []

    def update_telos_history(self, telos_move_idx: int) -> None:
        self._telos_history.append(telos_move_idx)
        if len(self._telos_history) > 20:
            self._telos_history = self._telos_history[-20:]

    def initialize(self): pass
    def cleanup(self): pass

    def legal_transitions(self, state):
        return [np.array([0, 0, 1]), np.array([0, 1, 0]), np.array([1, 0, 0])]

    def transition(self, state, action):
        return state.copy()

    def _markov_next_probs(self, state: np.ndarray) -> np.ndarray:
        """Return P(next | last) from the bigram (Λ4.3) or Markov matrix.

        Tries bigram (prev_prev, prev) → next first, then unigram prev → next,
        then EMA frequency fallback.
        """
        last_opp = int(state[4]) if 0 <= int(state[4]) < 3 else None
        if last_opp is None or len(state) < 18:
            freq = np.array([state[6], state[7], state[8]], dtype=float)
            return freq / (freq.sum() + 1e-8)

        # Bigram: (prev_prev, prev) → next  (state[45] = prev_prev_opp)
        if len(state) >= 46:
            prev_prev = int(state[45]) if 0 <= int(state[45]) < 3 else None
            if prev_prev is not None:
                bigram = state[18:45].reshape(9, 3).copy()
                bk = prev_prev * 3 + last_opp
                bg_row_sum = bigram[bk].sum()
                if bg_row_sum >= 0.5:
                    return bigram[bk] / bg_row_sum

        # Unigram Markov fallback
        markov = state[9:18].reshape(3, 3).copy()
        row_sum = markov[last_opp].sum()
        if row_sum < 0.5:
            freq = np.array([state[6], state[7], state[8]], dtype=float)
            return freq / (freq.sum() + 1e-8)
        return markov[last_opp] / row_sum

    def _predict_opponent_counter(self, telos_move: int) -> int:
        """Predict an adaptive opponent's counter to TELOS's move."""
        if len(self._telos_history) < 3:
            return np.random.randint(0, 3)
        recent = self._telos_history[-5:]
        most_freq = max(set(recent), key=recent.count)
        return COUNTER[most_freq]

    def simulate(self, state, horizon):
        n_futures = 10
        futures = []
        last_opp = int(state[4]) if 0 <= int(state[4]) < 3 else None
        # Λ4.3: Use bigram/Markov conditional probs instead of raw frequency distribution
        for _ in range(n_futures):
            my_move = np.random.randint(0, 3)
            opp_probs = self._markov_next_probs(state)
            if np.random.random() < 0.4 and len(self._telos_history) >= 3:
                opp_move = self._predict_opponent_counter(my_move)
            else:
                opp_move = np.random.choice(3, p=opp_probs)
            w = winner(my_move, opp_move)
            # 2-step lookahead: simulate opponent's response to TELOS's move
            # Shift bigram: simulated_prev_prev = prev, simulated_prev = my_move
            if len(state) >= 46 and last_opp is not None:
                sim_state = np.concatenate([
                    state[:9], state[9:18], state[18:45],
                    [float(last_opp)],
                ])
            else:
                sim_state = state[:18]
            counter_probs = self._markov_next_probs(sim_state)
            counter_opp = np.random.choice(3, p=counter_probs)
            counter_my_move = COUNTER[counter_opp]
            counter_w = winner(counter_my_move, counter_opp)
            score_delta = (1 if w == "telos" else 0) + (1 if counter_w == "telos" else 0)
            # Propagate bigram: keep matrix, shift prev_prev_opp to prev
            if len(state) >= 46 and last_opp is not None:
                fut_state = np.concatenate([
                    [state[0] + score_delta,
                     state[1] + (1 if w == "user" else 0) + (1 if counter_w == "user" else 0),
                     state[2] + 2,
                     float(my_move), float(opp_move), float(opp_move),
                     state[6], state[7], state[8]],
                    state[9:18],
                    state[18:45],
                    [float(last_opp)],
                ]).astype(float)
            else:
                fut_state = np.array([
                    state[0] + score_delta,
                    state[1] + (1 if w == "user" else 0) + (1 if counter_w == "user" else 0),
                    state[2] + 2,
                    float(my_move), float(opp_move), float(opp_move),
                    state[6], state[7], state[8],
                    *state[9:18],
                ], dtype=float)
            futures.append(World(state=fut_state, metadata={
                "telos_move": MOVE_NAMES[my_move],
                "opponent_move": MOVE_NAMES[opp_move],
                "counter_telos_move": MOVE_NAMES[counter_my_move],
                "counter_result": counter_w,
                "result": w,
                "score": f"{fut_state[0]:.0f}-{fut_state[1]:.0f}",
                "model": "markov" if opp_probs.sum() >= 0.9 else "freq",
            }))
        return futures

    def get_facts(self, state):
        # Λ4.3: Compute bigram + Markov top predictions for Council visibility
        markov_next = None
        markov_confidence = 0.0
        bigram_next = None
        bigram_confidence = 0.0
        last_opp = int(state[4]) if 0 <= int(state[4]) < 3 else None
        if last_opp is not None:
            # Markov
            if len(state) >= 18:
                markov = state[9:18].reshape(3, 3)
                row_sum = markov[last_opp].sum()
                if row_sum >= 0.5:
                    markov_next = int(np.argmax(markov[last_opp]))
                    markov_confidence = float(markov[last_opp][markov_next] / row_sum)
            # Bigram
            if len(state) >= 46:
                prev_prev = int(state[45]) if 0 <= int(state[45]) < 3 else None
                if prev_prev is not None:
                    bigram = state[18:45].reshape(9, 3)
                    bk = prev_prev * 3 + last_opp
                    bg_row_sum = bigram[bk].sum()
                    if bg_row_sum >= 0.5:
                        bigram_next = int(np.argmax(bigram[bk]))
                        bigram_confidence = float(bigram[bk][bigram_next] / bg_row_sum)
        markov_prediction = MOVE_NAMES[markov_next] if markov_next is not None else "unknown"
        bigram_prediction = MOVE_NAMES[bigram_next] if bigram_next is not None else "unknown"

        # Use whichever model has higher confidence
        use_bigram = bigram_confidence >= markov_confidence and bigram_confidence > 0.0
        best_confidence = max(bigram_confidence, markov_confidence)

        return DomainFacts(
            state=state.copy(),
            resources={"telos_score": float(state[0]), "opponent_score": float(state[1])},
            constraints=[],
            events=[],
            metrics={
                "round": float(state[2]),
                "lead": float(state[0] - state[1]),
                "uncertainty": max(0.1, 1.0 - best_confidence),
                "opponent_rock_freq": float(state[6]) if len(state) > 6 else 0.33,
                "opponent_paper_freq": float(state[7]) if len(state) > 7 else 0.33,
                "opponent_scissors_freq": float(state[8]) if len(state) > 8 else 0.33,
                "markov_next_confidence": round(bigram_confidence if use_bigram else markov_confidence, 3),
            },
            metadata={
                "telos_move": MOVE_NAMES[int(state[3])] if len(state) > 3 and int(state[3]) in range(3) else "none",
                "opponent_move": MOVE_NAMES[int(state[4])] if len(state) > 4 and int(state[4]) in range(3) else "none",
                "opponent_bias": ["rock", "paper", "scissors"][int(np.argmax(state[6:9]))] if len(state) > 8 else "unknown",
                "markov_prediction": markov_prediction,
                "bigram_prediction": bigram_prediction,
            },
        )

    def terminal(self, state):
        return state[2] >= 50

    def evaluate(self, state):
        return EvaluationReport(
            objectives={"score_diff": state[0] - state[1]},
            risks=max(0, state[1] - state[0]),
        )


class RPSAdapter(DomainAdapter):
    def __init__(self):
        self.exploration_budget = 0.3

    def forward(self, x): return x
    def inverse(self, x): return x

    def intent_to_action(self, intent, state, md):
        # Pipeline streams produce GridWorld-shaped action_vectors — ignore them for RPS.
        # The Pipeline's value is in reasoning/validation (Council, DI, MD).
        # Each intent_type produces a different RPS play style (Λ4.6 Emergent Intelligence):
        #   reflex:         counter + high explore (immediate but noisy)
        #   perceive:       counter + standard explore (balanced)
        #   memory_*:       counter + high explore (uncertainty-driven)
        #   plan_trajectory: counter + minimal explore (strategic, most accurate)
        if len(state) < 9:
            return RPS_VEC["rock"]

        # Λ4.3: Prefer bigram prediction over Markov over frequency
        last_opp = int(state[4]) if 0 <= int(state[4]) < 3 else None
        bigram_next = None
        markov_next = None
        if last_opp is not None:
            if len(state) >= 46:
                prev_prev = int(state[45]) if 0 <= int(state[45]) < 3 else None
                if prev_prev is not None:
                    bigram = state[18:45].reshape(9, 3)
                    bk = prev_prev * 3 + last_opp
                    bg_row_sum = bigram[bk].sum()
                    if bg_row_sum >= 0.5:
                        bigram_next = int(np.argmax(bigram[bk]))
            if bigram_next is None and len(state) >= 18:
                markov = state[9:18].reshape(3, 3)
                row_sum = markov[last_opp].sum()
                if row_sum >= 0.5:
                    markov_next = int(np.argmax(markov[last_opp]))

        if bigram_next is not None:
            most_likely = bigram_next
        elif markov_next is not None:
            most_likely = markov_next
        else:
            opp_freq = state[6:9]
            most_likely = int(np.argmax(opp_freq))
        counter = COUNTER[most_likely]

        intent_type = intent.intent_type if intent else "unknown"
        explore = self.exploration_budget

        # Λ4.3: Reduce exploration proportionally to prediction confidence.
        # Check bigram first, then Markov.
        markov_certainty = 0.0
        if last_opp is not None and len(state) >= 46:
            prev_prev = int(state[45]) if 0 <= int(state[45]) < 3 else None
            if prev_prev is not None:
                m = state[18:45].reshape(9, 3)
                bk = prev_prev * 3 + last_opp
                row = m[bk]
                row_sum = row.sum()
                if row_sum >= 0.5:
                    top = row.max()
                    markov_certainty = top / row_sum if row_sum > 0 else 0.0
        if markov_certainty == 0.0 and last_opp is not None and len(state) >= 18:
            m = state[9:18].reshape(3, 3)
            row = m[last_opp]
            row_sum = row.sum()
            if row_sum >= 0.5:
                top = row.max()
                markov_certainty = top / row_sum if row_sum > 0 else 0.0

        # Scale explore down when confident
        explore_mult = max(0.2, 1.0 - markov_certainty * 0.8)

        if intent_type == "reflex":
            # Reflex: fast — explore scales with Markov uncertainty
            if np.random.random() < explore * 1.2 * explore_mult:
                return RPS_VEC[MOVE_NAMES[np.random.randint(0, 3)]]
            return RPS_VEC[MOVE_NAMES[counter]]

        elif intent_type == "plan_trajectory":
            # Strategic: most decisive — minimal explore even when uncertain
            if np.random.random() < explore * 0.2 * explore_mult:
                return RPS_VEC[MOVE_NAMES[np.random.randint(0, 3)]]
            return RPS_VEC[MOVE_NAMES[counter]]

        elif intent_type in ("memory_miss", "memory_recall"):
            # Memory-driven: explores when uncertain
            if np.random.random() < min(1.0, explore * 1.5 * explore_mult):
                return RPS_VEC[MOVE_NAMES[np.random.randint(0, 3)]]
            return RPS_VEC[MOVE_NAMES[counter]]

        else:  # perceive, unknown
            # Standard: counter with exploration
            if np.random.random() < explore * explore_mult:
                return RPS_VEC[MOVE_NAMES[np.random.randint(0, 3)]]
            return RPS_VEC[MOVE_NAMES[counter]]

    @property
    def name(self): return "rps"


app = FastAPI(title="TELOS RPS")

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <title>TELOS — Rock Paper Scissors</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, 'SF Mono', monospace; background: #0d1117; color: #c9d1d9; min-height: 100vh; display: flex; justify-content: center; padding: 20px; }
    .container { max-width: 700px; width: 100%; }
    h1 { font-size: 1.5rem; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin: 20px 0; color: #58a6ff; }
    h1 span { color: #8b949e; font-size: 0.9rem; font-weight: normal; }
    .status-bar { display: flex; gap: 20px; margin: 16px 0; padding: 12px 16px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; }
    .status-item { flex: 1; text-align: center; }
    .status-item .label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
    .status-item .value { font-size: 1.3rem; font-weight: bold; margin-top: 4px; }
    .identity { font-size: 0.8rem; color: #8b949e; text-align: center; margin-bottom: 12px; }
    .moves { display: flex; gap: 16px; justify-content: center; margin: 24px 0; perspective: 800px; }
    .move-btn { width: 140px; height: 140px; font-size: 4rem; border: 2px solid #30363d; border-radius: 20px; background: #161b22; color: #c9d1d9; cursor: pointer; transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1); position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; }
    .move-btn .label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; transition: color 0.2s; }
    .move-btn:hover { border-color: #58a6ff; background: #1c2333; transform: scale(1.08) translateY(-4px) rotateX(4deg); box-shadow: 0 8px 32px rgba(88,166,255,0.2); }
    .move-btn:hover .label { color: #58a6ff; }
    .move-btn:active { transform: scale(0.95) translateY(0); box-shadow: none; }
    .move-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none !important; box-shadow: none !important; }
    .move-btn.telos-pick { border-color: #f85149; background: #2d0b0b; box-shadow: 0 0 24px rgba(248,81,73,0.4), inset 0 0 20px rgba(248,81,73,0.1); animation: pulse-glow 1.5s ease-in-out infinite; }
    .move-btn.telos-pick::after { content: "TELOS"; position: absolute; top: -10px; right: -10px; background: #f85149; color: #fff; font-size: 0.6rem; font-weight: bold; padding: 3px 8px; border-radius: 10px; letter-spacing: 0.5px; box-shadow: 0 2px 8px rgba(248,81,73,0.5); }
    .move-btn.user-pick { border-color: #58a6ff; background: #0b1e33; box-shadow: 0 0 24px rgba(88,166,255,0.3), inset 0 0 20px rgba(88,166,255,0.1); }
    .move-btn.user-pick::after { content: "YOU"; position: absolute; top: -10px; left: -10px; background: #58a6ff; color: #fff; font-size: 0.6rem; font-weight: bold; padding: 3px 8px; border-radius: 10px; letter-spacing: 0.5px; box-shadow: 0 2px 8px rgba(88,166,255,0.5); }

    @keyframes pulse-glow { 0%, 100% { box-shadow: 0 0 24px rgba(248,81,73,0.4), inset 0 0 20px rgba(248,81,73,0.1); } 50% { box-shadow: 0 0 40px rgba(248,81,73,0.6), inset 0 0 30px rgba(248,81,73,0.15); } }

    .result-box { margin: 16px 0; padding: 20px; border-radius: 16px; text-align: center; border: 1px solid #30363d; animation: fade-slide 0.3s ease-out; }
    @keyframes fade-slide { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .result-win { border-color: #3fb950; background: #0b2d16; }
    .result-lose { border-color: #f85149; background: #2d0b0b; }
    .result-tie { border-color: #d29922; background: #2d220b; }
    .result-hands { display: flex; justify-content: center; align-items: center; gap: 30px; margin: 16px 0; }
    .result-hand { font-size: 4.5rem; line-height: 1; animation: hand-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
    .result-hand.opponent { transform: scaleX(-1); }
    .result-vs { font-size: 1rem; color: #8b949e; font-weight: bold; letter-spacing: 2px; }
    @keyframes hand-pop { 0% { transform: scale(0); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
    .result-hand.opponent { animation-delay: 0.15s; }
    .result-label { font-size: 1rem; font-weight: bold; margin-top: 4px; }
    .reasoning { margin: 12px 0; padding: 12px; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; font-size: 0.8rem; }
    .reasoning summary { cursor: pointer; color: #58a6ff; }
    .reasoning pre { margin-top: 8px; white-space: pre-wrap; font-size: 0.75rem; color: #8b949e; line-height: 1.5; }
    .history { margin: 16px 0; }
    .history-item { display: flex; justify-content: space-between; padding: 6px 12px; border-bottom: 1px solid #21262d; font-size: 0.8rem; }
    .dot-win { color: #3fb950; } .dot-lose { color: #f85149; } .dot-tie { color: #d29922; }
    .error { color: #f85149; text-align: center; padding: 12px; }
    .btn-row { display: flex; gap: 8px; justify-content: center; margin: 16px 0; flex-wrap: wrap; }
    .btn-row button { padding: 8px 20px; background: #21262d; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; cursor: pointer; font-size: 0.85rem; }
    .btn-row button:hover { background: #30363d; }
    .btn-row button.danger { border-color: #f85149; color: #f85149; }
    .btn-row button.danger:hover { background: #2d0b0b; }
    .btn-row button.active { border-color: #58a6ff; color: #58a6ff; background: #0b1e33; }
    .history.collapsed .history-list { display: none; }
    .history-toggle { cursor: pointer; user-select: none; }
    .perf-panel { margin: 12px 0; padding: 16px; background: #161b22; border: 1px solid #30363d; border-radius: 12px; display: none; }
    .perf-panel.open { display: block; animation: fade-slide 0.3s ease-out; }
    .perf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 12px 0; }
    .perf-card { padding: 12px; background: #0d1117; border-radius: 8px; text-align: center; }
    .perf-card .stat { font-size: 1.6rem; font-weight: bold; }
    .perf-card .stat.win { color: #3fb950; } .perf-card .stat.lose { color: #f85149; } .perf-card .stat.tie { color: #d29922; }
    .perf-card .stat.total { color: #58a6ff; }
    .perf-card .label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
    .perf-bar-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 0.8rem; }
    .perf-bar { height: 16px; border-radius: 8px; transition: width 0.5s ease-out; }
    .perf-bar.bar-win { background: #3fb950; } .perf-bar.bar-lose { background: #f85149; } .perf-bar.bar-tie { background: #d29922; }
    .perf-section-title { font-size: 0.8rem; color: #c9d1d9; font-weight: bold; margin: 12px 0 6px; border-bottom: 1px solid #21262d; padding-bottom: 4px; }
    .perf-move-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.8rem; border-bottom: 1px solid #0d1117; }
    .perf-move-row span { color: #8b949e; } .perf-move-row .count { color: #c9d1d9; font-weight: bold; }
    @media (max-width: 500px) { .move-btn { padding: 16px 20px; font-size: 1rem; } }
  </style>
</head>
<body>
  <div class="container">
    <h1>TELOS <span>Cognitive Operating System</span></h1>
    <div class="identity" id="identity">[new user]</div>
    <div class="status-bar">
      <div class="status-item"><div class="label">You</div><div class="value" id="user-score" style="color:#58a6ff">0</div></div>
      <div class="status-item"><div class="label">Round</div><div class="value" id="round">0</div></div>
      <div class="status-item"><div class="label">TELOS <span id="telos-badge" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#8b949e;vertical-align:middle;margin-left:4px;"></span></div><div class="value" id="telos-score" style="color:#f85149">0</div><div id="telos-identity" style="font-size:0.65rem;color:#8b949e;margin-top:2px;"></div></div>
    </div>
    <div class="moves" id="moves">
      <button class="move-btn" onclick="play('rock')">✊<span class="label">rock</span></button>
      <button class="move-btn" onclick="play('paper')">✋<span class="label">paper</span></button>
      <button class="move-btn" onclick="play('scissors')">✌️<span class="label">scissors</span></button>
    </div>
    <div id="result"></div>
    <div id="reasoning"></div>
    <div class="btn-row">
      <button onclick="resetGame()">🔄 New Game</button>
      <button onclick="toggleHistory()">📋 History</button>
      <button id="perf-btn" onclick="togglePerformance()">📊 Performance</button>
      <button class="danger" onclick="clearHistory()">🗑 Clear</button>
    </div>
    <div class="perf-panel" id="perf-panel">
      <div class="perf-grid" id="perf-stats"></div>
      <div class="perf-section-title">Move Distribution</div>
      <div id="perf-moves"></div>
      <div class="perf-section-title">Win Rate</div>
      <div id="perf-bars"></div>
    </div>
    <div class="history collapsed" id="history">
      <div class="history-toggle" onclick="toggleHistory()">▼ History (<span id="history-count">0</span> rounds)</div>
      <div class="history-list" id="history-list"></div>
    </div>
  </div>
  <script>
    let username = prompt("Your name:", "Player") || "Player";
    document.getElementById('identity').textContent = `Playing as ${username}`;

    function toggleHistory() {
      document.getElementById('history').classList.toggle('collapsed');
    }

    async function play(move) {
      document.querySelectorAll('.move-btn').forEach(b => { b.disabled = true; b.classList.remove('telos-pick', 'user-pick'); });
      document.getElementById('result').innerHTML = '<div class="result-box">TELOS is reasoning...</div>';
      document.getElementById('reasoning').innerHTML = '';

      try {
        const resp = await fetch('/play', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({move, username}),
        });
        const data = await resp.json();
        renderResult(data);
      } catch(e) {
        document.getElementById('result').innerHTML = '<div class="error">Error: ' + e.message + '</div>';
      }
      document.querySelectorAll('.move-btn').forEach(b => b.disabled = false);
    }

    const HAND_EMOJI = { rock: '✊', paper: '✋', scissors: '✌️' };
    let gameLog = [];

    function togglePerformance() {
      const panel = document.getElementById('perf-panel');
      const btn = document.getElementById('perf-btn');
      const open = !panel.classList.contains('open');
      panel.classList.toggle('open', open);
      btn.classList.toggle('active', open);
      if (open) renderPerformance();
    }

    function renderResult(data) {
      const result = data.result;

      let cls = '';
      let label = '';
      if (result === 'win') { cls = 'result-win'; label = 'YOU WIN'; }
      else if (result === 'lose') { cls = 'result-lose'; label = 'TELOS WINS'; }
      else { cls = 'result-tie'; label = 'TIE'; }

      document.getElementById('round').textContent = data.round;
      document.getElementById('user-score').textContent = data.scores.user;
      document.getElementById('telos-score').textContent = data.scores.telos;

      // Highlight both moves on buttons
      document.querySelectorAll('.move-btn').forEach(b => {
        b.classList.remove('telos-pick', 'user-pick');
        const txt = b.querySelector('.label')?.textContent || b.textContent.toLowerCase();
        if (txt.includes(data.telos_move)) b.classList.add('telos-pick');
        if (txt.includes(data.user_move)) b.classList.add('user-pick');
      });

      // Update TELOS badge + identity info
      const badge = document.getElementById('telos-badge');
      const idEl = document.getElementById('telos-identity');
      if (data.identity) {
        const colors = { 'new_user': '#8b949e', 'emerging_familiarity': '#d29922', 'established_relationship': '#3fb950', 'deep_relationship': '#58a6ff' };
        badge.style.background = colors[data.identity.relationship] || '#8b949e';
        idEl.textContent = `${data.identity.relationship} · trust ${data.identity.trust.toFixed(2)}`;
      }

      const identity = document.getElementById('identity');
      if (data.identity) {
        identity.textContent = `Playing as ${data.identity.name} — ${data.identity.relationship} (trust: ${data.identity.trust.toFixed(2)})`;
      }

      const uHand = HAND_EMOJI[data.user_move] || '?';
      const tHand = HAND_EMOJI[data.telos_move] || '?';
      document.getElementById('result').innerHTML =
        `<div class="result-box ${cls}">
          <div class="result-hands">
            <div class="result-hand">${uHand}</div>
            <div class="result-vs">VS</div>
            <div class="result-hand opponent">${tHand}</div>
          </div>
          <div class="result-label">${label}</div>
          <div style="font-size:0.8rem;color:#8b949e;margin-top:4px;">${data.user_move} vs ${data.telos_move}</div>
        </div>`;

      if (data.reasoning) {
        const trace = JSON.stringify(data.reasoning, null, 2);
        document.getElementById('reasoning').innerHTML =
          `<details class="reasoning"><summary>🔄 View TELOS reasoning trace</summary><pre>${trace}</pre></details>`;
      }

      // Store for performance
      gameLog.push({ user: data.user_move, telos: data.telos_move, result: data.result });
      if (gameLog.length > 100) gameLog = gameLog.slice(-100);

      if (data.history && data.history.length > 0) {
        const h = data.history.map(r =>
          `<div class="history-item"><span>R${r.round}: You ${r.user_move} vs TELOS ${r.telos_move}</span><span class="dot-${r.result}">${r.result === 'win' ? '✅' : r.result === 'lose' ? '❌' : '➖'} ${r.result.toUpperCase()}</span></div>`
        ).join('');
        document.getElementById('history-list').innerHTML = h;
        document.getElementById('history-count').textContent = data.history.length;
        document.getElementById('history').classList.remove('collapsed');
      }
    }

    async function resetGame() {
      document.querySelectorAll('.move-btn').forEach(b => b.disabled = true);
      await fetch('/reset', {method: 'POST'});
      document.getElementById('round').textContent = '0';
      document.getElementById('user-score').textContent = '0';
      document.getElementById('telos-score').textContent = '0';
      document.getElementById('result').innerHTML = '';
      document.getElementById('reasoning').innerHTML = '';
      document.getElementById('history-list').innerHTML = '';
      document.getElementById('history-count').textContent = '0';
      document.getElementById('history').classList.add('collapsed');
      document.querySelectorAll('.move-btn').forEach(b => b.disabled = false);
    }

    function clearHistory() {
      document.getElementById('history-list').innerHTML = '';
      document.getElementById('history-count').textContent = '0';
      document.getElementById('history').classList.add('collapsed');
    }

    function renderPerformance() {
      const total = gameLog.length;
      if (total === 0) {
        document.getElementById('perf-stats').innerHTML = '<div class="perf-card" style="grid-column:span 2"><div style="color:#8b949e;font-size:0.9rem;padding:12px;">No games played yet</div></div>';
        document.getElementById('perf-moves').innerHTML = '';
        document.getElementById('perf-bars').innerHTML = '';
        return;
      }

      const wins = gameLog.filter(r => r.result === 'win').length;
      const losses = gameLog.filter(r => r.result === 'lose').length;
      const ties = gameLog.filter(r => r.result === 'tie').length;

      // Stats cards
      document.getElementById('perf-stats').innerHTML = `
        <div class="perf-card"><div class="stat total">${total}</div><div class="label">Total Rounds</div></div>
        <div class="perf-card"><div class="stat win">${wins}</div><div class="label">Your Wins</div></div>
        <div class="perf-card"><div class="stat lose">${losses}</div><div class="label">TELOS Wins</div></div>
        <div class="perf-card"><div class="stat tie">${ties}</div><div class="label">Ties</div></div>
      `;

      // Win rate bars
      const wp = total > 0 ? (wins / total * 100).toFixed(1) : 0;
      const lp = total > 0 ? (losses / total * 100).toFixed(1) : 0;
      const tp = total > 0 ? (ties / total * 100).toFixed(1) : 0;
      document.getElementById('perf-bars').innerHTML = `
        <div class="perf-bar-row"><span style="color:#3fb950;width:60px;">You</span><div style="flex:1;background:#0d1117;border-radius:8px;overflow:hidden;"><div class="perf-bar bar-win" style="width:${wp}%"></div></div><span>${wp}%</span></div>
        <div class="perf-bar-row"><span style="color:#f85149;width:60px;">TELOS</span><div style="flex:1;background:#0d1117;border-radius:8px;overflow:hidden;"><div class="perf-bar bar-lose" style="width:${lp}%"></div></div><span>${lp}%</span></div>
        <div class="perf-bar-row"><span style="color:#d29922;width:60px;">Ties</span><div style="flex:1;background:#0d1117;border-radius:8px;overflow:hidden;"><div class="perf-bar bar-tie" style="width:${tp}%"></div></div><span>${tp}%</span></div>
      `;

      // Move distribution
      const moves = ['rock', 'paper', 'scissors'];
      const userFreq = {}, telosFreq = {};
      moves.forEach(m => { userFreq[m] = 0; telosFreq[m] = 0; });
      gameLog.forEach(r => { userFreq[r.user] = (userFreq[r.user] || 0) + 1; telosFreq[r.telos] = (telosFreq[r.telos] || 0) + 1; });
      document.getElementById('perf-moves').innerHTML = moves.map(m =>
        `<div class="perf-move-row">
          <span>${HAND_EMOJI[m]} ${m}</span>
          <span class="count">You: ${userFreq[m]}x</span>
          <span class="count">TELOS: ${telosFreq[m]}x</span>
        </div>`
      ).join('');
    }
  </script>
</body>
</html>
"""


def build_pipeline():
    from telos.core.council.validators import PredictionDriftValidator
    from telos.core.infra_manager.failure_ledger import FailureLedger
    from telos.core.infra_manager.infrastructure_manager import InfrastructureManager
    sim = RPSSimulator()
    infra = InfrastructureManager()
    adapter = RPSAdapter()
    config = PipelineConfig(
        adapter=adapter, simulator=sim,
        compute_budget_ms=50.0, state_dim=46, n_worlds=30, horizon=3,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    failure_ledger = FailureLedger()
    sim_engine = CounterfactualEngine(sim)
    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))
    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib, failure_ledger=failure_ledger))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))
    pipeline.register_validator(PredictionDriftValidator(drift_window=3))
    switch_detector = OpponentSwitchDetector(window=3)
    pipeline.register_validator(switch_detector)
    pipeline._failure_ledger = failure_ledger
    pipeline._prediction_validator = pipeline.council._validators[-2]
    pipeline._switch_detector = pipeline.council._validators[-1]
    pipeline._infra = infra
    pipeline._adapter = adapter
    pipeline._config_extra = {"exploration_budget": 0.3}
    # Seed a calibration entry so PlanningStream starts with influence_weight=1.0
    # (without seeding, no calibrations exist and get_influence_weight returns 1.0 anyway)
    # The Λ3.5 boost ensures non-selected streams grow influence each cycle.
    pipeline._active_session = None  # set each cycle by the play handler

    # Λ2.2 — Register council block callback: reset EMA, boost PlanningStream
    def _on_council_block(block_info):
        sess = pipeline._active_session
        if sess is None:
            return
        blocking = block_info.get("blocking_validator", "")
        if blocking == "OpponentSwitchDetector":
            sess["ema_freq"] = [0.33, 0.33, 0.33]
            sess["switch_cooldown"] = 3
            cal = infra.calibrator._calibrations.get("PlanningStream")
            if cal:
                cal.influence_weight = 2.0
            logger.info(f"Councill block by {blocking} — EMA reset, planning boosted")

    infra.on_council_block(_on_council_block)
    return pipeline


pipeline = build_pipeline()

# Multi-agent coordinator (Sprint 3)
sim = RPSSimulator()
adapter = RPSAdapter()
coordinator = PipelineCoordinator(
    supervisor=pipeline,
    default_simulator=sim,
    default_adapter=adapter,
)

# Per-session game state
sessions: Dict[str, dict] = {}


def get_or_create_session(session_id: str) -> dict:
    if session_id not in sessions:
        # Markov transition matrix: T[i][j] = times opponent played j after i (Λ4.3)
        markov = np.zeros((3, 3), dtype=float)
        bigram = np.zeros((9, 3), dtype=float)  # 9 bigram keys × 3 next moves
        state_arr = np.concatenate([
            np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.33, 0.33, 0.33]),
            markov.flatten(),
            bigram.flatten(),
            np.array([-1.0]),  # state[45]: prev_prev_opp (-1 = none)
        ])
        sessions[session_id] = {
            "state": state_arr,
            "history": [],
            "cycle_count": 0,
            "loss_streak": 0,
            "loss_move": None,
            "ema_freq": [0.33, 0.33, 0.33],
            "switch_cooldown": 0,
        }
    return sessions[session_id]


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE


@app.get("/metrics")
async def metrics():
    """Pipeline telemetry dashboard data."""
    return pipeline.telemetry.to_dict()


@app.post("/coordinate")
async def coordinate(data: dict):
    """Multi-agent coordination demo: fan-out across sub-pipelines."""
    session_id = data.get("session_id", "default")
    move = data.get("move", "rock")
    username = data.get("username", "Player")

    sess = get_or_create_session(session_id)
    state = np.array([
        float(sess["state"][0]), float(sess["state"][1]),
        float(sess["cycle_count"]), 0.0, 0.0,
        float(MOVE_NAMES.index(move)),
    ])

    result = coordinator.orchestrate(
        state=state,
        subtasks=[
            SubPipelineConfig(name="game_analyst", budget_ms=15.0,
                              streams=["reflex", "perception"],
                              user_name=username),
            SubPipelineConfig(name="move_planner", budget_ms=25.0,
                              streams=["memory", "planning"],
                              user_name=username),
        ],
        user_name=username,
    )

    return {
        "session_id": session_id,
        "user_move": move,
        "sub_pipelines": len(result.sub_results),
        "success": result.success,
        "aggregate_di": result.aggregate_di,
        "aggregate_md": result.aggregate_md,
        "all_council_validated": result.all_council_validated,
        "sub_results": [
            {
                "name": r.name,
                "success": r.success,
                "intent": r.intent,
                "di": r.di,
                "md": r.md,
                "council_validated": r.council_validated,
                "duration_ms": r.duration_ms,
                "error": r.error,
            }
            for r in result.sub_results
        ],
        "total_duration_ms": result.total_duration_ms,
        "coordinator_stats": coordinator.stats,
    }


@app.post("/play")
async def play(data: dict):
    session_id = data.get("session_id", "default")
    move = data.get("move", "rock")
    username = data.get("username", "Player")

    sess = get_or_create_session(session_id)
    user_move_idx = MOVE_NAMES.index(move)

    # ── 1. EMA opponent frequency (recency-weighted, alpha=0.5) ──
    hist = sess["history"]
    alpha = 0.5
    ema_freq = sess.get("ema_freq", [0.33, 0.33, 0.33])
    if len(hist) >= 1:
        last_move_idx = MOVE_NAMES.index(hist[-1]["user_move"])
        one_hot = [0.0, 0.0, 0.0]
        one_hot[last_move_idx] = 1.0
        ema_freq = [alpha * o + (1 - alpha) * e for o, e in zip(one_hot, ema_freq)]
        total_ema = max(sum(ema_freq), 1e-8)
        ema_freq = [f / total_ema for f in ema_freq]
    sess["ema_freq"] = ema_freq

    # Λ2.5 — Adaptive horizon: when opponent is predictable (low entropy),
    # increase simulation depth. When switching (high entropy), stay shallow.
    freq_entropy = -sum(f * np.log(f + 1e-8) for f in ema_freq) / np.log(3)
    if freq_entropy < 0.3:
        pipeline._infra.adaptive_horizon = 8
    elif freq_entropy > 0.8:
        pipeline._infra.adaptive_horizon = 2
    else:
        pipeline._infra.adaptive_horizon = 4

    # ── 2. Build state (Λ4.3: Markov transition matrix in state[9:18]) ──
    state = sess["state"].copy()
    state[2] = float(sess["cycle_count"])
    state[5] = float(user_move_idx)
    state[6:9] = ema_freq
    markov = sess.get("markov", np.zeros((3, 3)))
    state[9:18] = markov.flatten()

    # Inject exploration budget from MissionPolicy into adapter (Λ4.2)
    explore = pipeline._infra.policy.current.exploration_budget if hasattr(pipeline, '_infra') else 0.3
    if hasattr(pipeline, '_adapter'):
        pipeline._adapter.exploration_budget = explore

    # Record opponent move on switch detector before pipeline runs
    if hasattr(pipeline, '_switch_detector'):
        pipeline._switch_detector.record_move(user_move_idx)

    # Link active session so the on_council_block callback can update it (Λ2.2)
    pipeline._active_session = sess

    # ── 3. Run TELOS pipeline ──
    result = pipeline.execute(state, user_name=username)
    trace = result.decision_trace

    # ── 4. Trust pipeline output or fallback ──
    if trace is not None and trace.selected_action is not None and not result.council_blocked and not result.firewall_blocked:
        telos_move_idx = int(np.argmax(trace.selected_action))
    else:
        if len(hist) >= 2:
            most_likely = int(np.argmax(ema_freq))
            telos_move_idx = COUNTER[most_likely]
        else:
            telos_move_idx = np.random.randint(0, 3)

    # Update simulator with TELOS's move history (for adaptive opponent modeling)
    sim.update_telos_history(telos_move_idx)

    # ── 5. Determine result ──
    w = winner(telos_move_idx, user_move_idx)
    if w == "telos":
        result_str = "lose"
        sess["state"][0] += 1
    elif w == "user":
        result_str = "win"
        sess["state"][1] += 1
    else:
        result_str = "tie"

    # ── 6. Update prediction drift validator (Λ4.3: bigram → Markov → freq) ──
    predicted_opponent = None
    if len(sess["state"]) >= 46:
        prev_prev = int(sess["state"][45]) if 0 <= int(sess["state"][45]) < 3 else None
        last_opp = int(sess["state"][4]) if 0 <= int(sess["state"][4]) < 3 else None
        if prev_prev is not None and last_opp is not None:
            bg = sess["state"][18:45].reshape(9, 3)
            bk = prev_prev * 3 + last_opp
            if bg[bk].sum() >= 0.5:
                predicted_opponent = int(np.argmax(bg[bk]))
    if predicted_opponent is None:
        markov = sess.get("markov", np.zeros((3, 3)))
        last_opp = int(sess["state"][4]) if 0 <= int(sess["state"][4]) < 3 else None
        if last_opp is not None and markov[last_opp].sum() >= 0.5:
            predicted_opponent = int(np.argmax(markov[last_opp]))
        else:
            predicted_opponent = int(np.argmax(ema_freq))
    if hasattr(pipeline, '_prediction_validator'):
        pipeline._prediction_validator.record_prediction(
            predicted=MOVE_NAMES[predicted_opponent],
            actual=move
        )

    # ── 7. Kintsugi: record pattern exploit on 3+ consecutive losses with same move ──
    if w == "user":  # TELOS lost this round
        sess.setdefault("loss_streak", 0)
        sess["loss_streak"] += 1
        sess.setdefault("loss_move", MOVE_NAMES[telos_move_idx])
        if sess["loss_streak"] >= 3:
            if hasattr(pipeline, '_failure_ledger'):
                pipeline._failure_ledger.record_pattern_exploit(
                    cycle=sess["cycle_count"],
                    move=MOVE_NAMES[telos_move_idx],
                    streak=sess["loss_streak"],
                )
    else:
        sess["loss_streak"] = 0
        sess["loss_move"] = None

    # ── 8. Update session ──
    # Update Markov transition matrix (Λ4.3): T[last_move][current_move] += 1
    # Apply exponential decay (0.97/round) so old transitions fade and the model
    # adapts to non-stationary opponents (changing patterns). After 30 rounds,
    # any single transition's weight is 0.97^30 ≈ 0.40 of its original value,
    # letting recent patterns dominate without abrupt resets.
    MARKOV_DECAY = 0.97
    if len(hist) >= 1:
        prev_move = MOVE_NAMES.index(hist[-1]["user_move"])
        markov = sess.get("markov", np.zeros((3, 3)))
        markov *= MARKOV_DECAY
        markov[prev_move, user_move_idx] += 1.0
        sess["markov"] = markov
        sess["state"][9:18] = markov.flatten()

        # Λ4.3: Bigram update — predict from (prev_prev, prev) instead of just prev
        prev_prev_opp = int(sess["state"][45]) if int(sess["state"][45]) in (0, 1, 2) else None
        if prev_prev_opp is not None:
            bigram = sess["state"][18:45].reshape(9, 3).copy()
            bigram *= MARKOV_DECAY
            bk = prev_prev_opp * 3 + prev_move  # bigram key = prev_prev*3 + prev
            bigram[bk, user_move_idx] += 1.0
            sess["state"][18:45] = bigram.flatten()
    sess["cycle_count"] += 1
    sess["state"][3] = float(telos_move_idx)
    sess["state"][4] = float(user_move_idx)
    # Store the previous previous opponent move (one slot shift)
    if len(hist) >= 1:
        prev_move = MOVE_NAMES.index(hist[-1]["user_move"])
        sess["state"][45] = float(prev_move)
    sess["state"][2] = float(sess["cycle_count"])

    sess["history"].append({
        "round": sess["cycle_count"],
        "user_move": move,
        "telos_move": MOVE_NAMES[telos_move_idx],
        "result": result_str,
    })

    # Identity profile
    profile = pipeline.ledger.get_user_profile(username)
    identity_info = None
    if profile:
        identity_info = {
            "name": profile.name,
            "relationship": profile.relationship_summary,
            "trust": round(profile.trust_level, 3),
            "interactions": profile.total_interactions,
        }

    # Reasoning trace
    reasoning = None
    if trace:
        reasoning = {
            "cycle": trace.cycle_id,
            "selected_intent": trace.selected_intent.intent_type if trace.selected_intent else None,
            "streams": [
                {
                    "name": s.stream_name,
                    "priority": s.priority,
                    "activated": s.activated,
                    "intent": s.intent.intent_type if s.intent else None,
                }
                for s in trace.stream_activations
            ],
            "simulated_worlds": trace.worlds_simulated,
            "top_futures": [
                {"score": o.get("score", 0), "horizon": o.get("horizon", 0)}
                for o in trace.strategic_options[:5]
            ],
            "council": {
                "validated": trace.council_validated,
                "signals": trace.council_signals,
                "di": round(trace.decision_integrity, 3),
                "md": round(trace.mission_drift, 3),
            },
            "firewall": {
                "blocked": trace.firewall_blocked,
                "by": trace.firewall_blocked_by,
            },
            "duration_ms": round(trace.cycle_duration_ms, 1),
            "intent": trace.selected_intent.intent_type if trace.selected_intent else None,
            "telos_move": MOVE_NAMES[telos_move_idx],
        }

    return {
        "session_id": session_id,
        "round": sess["cycle_count"],
        "user_move": move,
        "telos_move": MOVE_NAMES[telos_move_idx],
        "result": result_str,
        "scores": {"user": int(sess["state"][1]), "telos": int(sess["state"][0])},
        "identity": identity_info,
        "reasoning": reasoning,
        "history": sess["history"][-10:],
    }


@app.post("/reset")
async def reset():
    global pipeline
    pipeline = build_pipeline()
    sessions.clear()
    return {"status": "ok"}


if __name__ == "__main__":
    print("TELOS RPS — http://localhost:8000")
    print("TELOS uses its 7-phase Pipeline to reason about each move.\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
