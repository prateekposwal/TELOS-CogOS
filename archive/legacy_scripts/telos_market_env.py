"""
TELOS Market Simulator: Benchmark environment simulating adversarial market conditions.
Tests: Systemic drift, epistemic volatility, and long-term capital preservation.
"""
import numpy as np
from typing import Dict, Any, Tuple
from telos_controller import TelosController
from telos.core.runtime import PipelineConfig

class MarketBenchmarkEnv:
    def __init__(self, volatility: float = 0.5):
        self.volatility = volatility
        self.price = 100.0
        self.market_state = np.zeros(6) # Maps to TELOS state_dim
        self.steps_taken = 0

    def reset(self) -> np.ndarray:
        self.price = 100.0
        self.market_state = np.random.randn(6) * 0.1
        self.steps_taken = 0
        return self.market_state

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, Dict]:
        # Market dynamics: action influences price, volatility adds shock
        impact = np.dot(action, np.array([1.0, -1.0, 0.5, -0.5, 0.2, -0.2]))
        shock = np.random.randn() * self.volatility
        self.price += impact + shock
        
        # Update market state
        self.market_state = np.roll(self.market_state, 1)
        self.market_state[0] = np.clip(self.price / 200.0, 0.0, 1.0)
        
        # Reward: Capital preservation/growth
        reward = impact
        self.steps_taken += 1
        return self.market_state, reward, self.steps_taken >= 100, {}
