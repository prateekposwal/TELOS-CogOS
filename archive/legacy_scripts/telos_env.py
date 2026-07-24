"""
TELOS Survival Environment: Grid-based Resource Extraction
Tests latent role affordances, health management, and safety constraints.
"""
import numpy as np
from typing import Dict, List, Any, Tuple

class TelosEnv:
    def __init__(self, size: int = 10):
        self.size = size
        self.agent_pos = np.array([0, 0])
        self.resources = [(np.random.randint(size), np.random.randint(size)) for _ in range(5)]
        self.tools = {
            "stick": (np.random.randint(size), np.random.randint(size)),
            "rock": (np.random.randint(size), np.random.randint(size))
        }
        self.corruptors = [(np.random.randint(size), np.random.randint(size)) for _ in range(3)]
        self.energy = 1.0
        self.corruption = 0.0

    def reset(self) -> np.ndarray:
        self.agent_pos = np.array([0, 0])
        self.energy = 1.0
        self.corruption = 0.0
        self.resources = [(np.random.randint(self.size), np.random.randint(self.size)) for _ in range(5)]
        return self._get_obs()

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, Dict]:
        # Move agent
        move = np.clip(np.round(action[:2] * 2), -1, 1).astype(int)
        self.agent_pos = np.clip(self.agent_pos + move, 0, self.size - 1)
        
        # Energy decay and corruption
        self.energy -= 0.05
        if tuple(self.agent_pos) in self.corruptors:
            self.corruption += 0.2
        
        # Resource extraction
        reward = 0.0
        if tuple(self.agent_pos) in self.resources:
            reward = 1.0
            self.resources.remove(tuple(self.agent_pos))
            
        done = self.energy <= 0 or self.corruption >= 1.0
        return self._get_obs(), reward, done, {}

    def _get_obs(self) -> np.ndarray:
        # Returns simplified state vector for TELOS pipeline
        obs = np.zeros(6)
        obs[0] = self.agent_pos[0] / self.size
        obs[1] = self.agent_pos[1] / self.size
        obs[2] = self.energy
        obs[3] = self.corruption
        obs[4] = len(self.resources) / 5
        # Tool proximity: 1.0 if agent is within 3 steps of any tool
        in_range = any(
            np.linalg.norm(np.array(self.agent_pos) - np.array(tp)) < 3
            for tp in self.tools.values()
        )
        obs[5] = 1.0 if in_range else 0.0
        return obs
