import numpy as np
from typing import List, Any
from telos.core.contracts.domain_model import DomainSimulator, DomainFacts, EvaluationReport
from telos.world.world import World
from telos.examples.chess.env import ChessEnv

class ChessDomainSimulator(DomainSimulator):
    """
    Plugin: Implements the DSI contract for Chess.
    Encapsulates all board logic. The TELOS Runtime sees only DSI methods.
    """
    def __init__(self, seed=None):
        self.env = ChessEnv()
        # Pattern: one RNG authority per engine — private RandomState,
        # never global np.random in the simulation hot path.
        self._rng = np.random.RandomState(seed)

    def initialize(self) -> None: pass
    def cleanup(self) -> None: pass

    def initial_state(self) -> np.ndarray:
        return self.env.reset()

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        legal_moves = self.env._legal_moves()
        actions = []
        for move in legal_moves:
            actions.append(np.array([move[0], move[1], 0, 0, 0, 0], dtype=float))
        return actions

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        obs, _, _, _ = self.env.step(action)
        return obs

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        futures = []
        curr = state
        for _ in range(horizon):
            moves = self.legal_transitions(curr)
            if not moves: break
            move = moves[self._rng.randint(len(moves))]
            curr = self.transition(curr, move)
            futures.append(World(state=curr))
        return futures

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        return DomainFacts(
            state=state,
            resources={"legal_move_count": len(self.env._legal_moves())},
            constraints=["chess_rules"],
            events=["check" if self.env._is_check(0) else "none"],
            metrics={"material_balance": 0.0}
        )

    def terminal(self, state: np.ndarray) -> bool:
        return bool(self.env._is_checkmate() or self.env._is_stalemate())

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        board = self.env.board
        white_material = board[board > 6].sum() - 6 * (board > 6).sum()
        black_material = board[(board > 0) & (board < 7)].sum()
        balance = white_material - black_material
        return EvaluationReport(
            objectives={"material": float(balance)},
            risks=float(1.0 if self.env._is_check(0) else 0.0),
        )
