"""
Pluggable domain adapters for TELOS.
"""

from abc import abstractmethod
from typing import Optional, List, Any
import numpy as np
from telos.intent_ir import IntentIR
from telos.representations.transform import (
    RepresentationTransform,
    RuntimeState,
)
from telos.core.contracts.domain_model import DomainAdapter

class BaseAdapter(RepresentationTransform, DomainAdapter):
    """Interface all domain adapters must satisfy.

    Pattern: one RNG authority per engine — every adapter owns a private
    RandomState and NEVER reads global np.random. Action sampling lives in
    the production ACT phase; a shared global stream makes sampled actions
    order-dependent across the suite (RNG-isolation flake pattern).
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = np.random.RandomState(seed)

    @property
    @abstractmethod
    def action_dim(self) -> int: ...
    @property
    @abstractmethod
    def state_dim(self) -> int: ...

    @abstractmethod
    def sample_action(self, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def intent_to_action(self, intent: IntentIR, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def action_to_intent(self, action: np.ndarray, state: Optional[np.ndarray] = None) -> IntentIR: ...
    @abstractmethod
    def is_action_valid(self, action: np.ndarray, state: np.ndarray) -> bool: ...

    def forward(self, input_data: Any) -> Any: return input_data
    def inverse(self, output_data: Any) -> Any: return output_data
    def applicable(self, state: RuntimeState) -> float: return 1.0

class MarketAdapter(BaseAdapter):
    """6-d continuous action space."""
    @property
    def action_dim(self) -> int: return 6
    @property
    def state_dim(self) -> int: return 6
    @property
    def name(self) -> str: return "market_adapter"

    def sample_action(self, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray:
        return self._rng.randn(self.action_dim) * 0.1 + mission_dir * 0.3

    def intent_to_action(self, intent: IntentIR, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray:
        return np.asarray(intent.params.get("vector", np.zeros(self.action_dim)))

    def action_to_intent(self, action: np.ndarray, state: Optional[np.ndarray] = None) -> IntentIR:
        return IntentIR("continuous_market_action", target=action.copy(), confidence=1.0, params={"vector": action.copy()})

    def is_action_valid(self, action: np.ndarray, state: np.ndarray) -> bool:
        return len(action) == self.action_dim and not np.isnan(action).any()

class ChessAdapter(BaseAdapter):
    """Discrete 2-d action space."""
    @property
    def action_dim(self) -> int: return 2
    @property
    def state_dim(self) -> int: return 64
    @property
    def name(self) -> str: return "chess_adapter"

    def sample_action(self, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray:
        return np.array([self._rng.randint(0, 64), self._rng.randint(0, 64)], dtype=float)

    def intent_to_action(self, intent: IntentIR, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray:
        return np.array([float(intent.source or 0), float(intent.target or 0)])

    def action_to_intent(self, action: np.ndarray, state: Optional[np.ndarray] = None) -> IntentIR:
        return IntentIR("chess_move", source=int(action[0]), target=int(action[1]), confidence=1.0)

    def is_action_valid(self, action: np.ndarray, state: np.ndarray) -> bool:
        src, tgt = int(action[0]), int(action[1])
        return 0 <= src < 64 and 0 <= tgt < 64 and src != tgt
