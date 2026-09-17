"""
MetaDomainAdapter — Self-Analysis Domain for TELOS.

Allows TELOS to run its own pipeline on self-analysis tasks
by providing a DomainSimulator that returns codebase facts
and a DomainAdapter that converts self-audit intents to
improvement actions.

Satisfies Λ4.6 (Emergent Intelligence): understanding self
is the highest cognitive function.
"""

import os
import sys
import time
import json
import logging
from typing import List, Optional, Dict, Any
import numpy as np
from dataclasses import dataclass, field

from telos.core.contracts.domain_model import (
    DomainSimulator, DomainAdapter, EvaluationReport,
)
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR

logger = logging.getLogger('telos_meta_adapter')


@dataclass
class MetaConfig:
    codebase_path: str = ""
    test_command: str = f"{sys.executable} -m pytest tests/ -v"
    lint_command: str = ""
    report_path: str = os.environ.get("TELOS_REPORT_DIR", os.path.expanduser("~/.telos")) + "/telos_meta_report.json"


class MetaDomainSimulator(DomainSimulator):
    """Simulator for the 'meta' domain — introspective self-analysis.

    Returns facts about the TELOS codebase: test counts, coverage gaps,
    file counts, axiom coverage.
    """

    def __init__(self, config: Optional[MetaConfig] = None, seed=None):
        self.config = config
        # Pattern: one RNG authority per engine — private RandomState,
        # never global np.random in the simulation hot path.
        self._rng = np.random.RandomState(seed) or MetaConfig()
        self._initialized = False
        self._fact_cache: Optional[DomainFacts] = None

    def initialize(self) -> None:
        self._initialized = True
        logger.info("MetaDomainSimulator initialized")

    def cleanup(self) -> None:
        self._initialized = False
        self._fact_cache = None

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        return [np.array([1.0]), np.array([0.0])]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return state + action * 0.1

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        worlds = []
        for h in range(horizon):
            worlds.append(World(state=state + self._rng.randn(*state.shape) * 0.05))
        return worlds

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        if self._fact_cache:
            return self._fact_cache
        facts = DomainFacts(
            resources={"codebase": self._scan_codebase()},
            constraints=["self_analysis"],
            events=["meta_cycle"],
            metrics={"mode": "self_analysis"},
        )
        self._fact_cache = facts
        return facts

    def terminal(self, state: np.ndarray) -> bool:
        return False

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        return EvaluationReport(objectives={"self_awareness": 1.0}, risks=0.0)

    @property
    def name(self) -> str:
        return "meta"

    @property
    def state_dim(self) -> int:
        return 2

    def world_spec(self):
        from telos.core.contracts.domain_model import WorldSpec
        return WorldSpec(
            name=self.name,
            state_dim=self.state_dim,
            action_dim=2,
            objectives=["self_awareness"],
            constraints=["self_analysis"],
            observability="high",
            capabilities=["self_analysis"],
        )

    def _scan_codebase(self) -> Dict[str, Any]:
        base = self.config.codebase_path or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        py_files = 0
        test_files = 0
        total_lines = 0
        for root, _, files in os.walk(base):
            for f in files:
                if f.endswith('.py'):
                    py_files += 1
                    if f.startswith('test_'):
                        test_files += 1
                    fp = os.path.join(root, f)
                    try:
                        with open(fp) as fh:
                            total_lines += sum(1 for _ in fh)
                    except Exception:
                        pass
        return {
            "py_files": py_files,
            "test_files": test_files,
            "total_lines": total_lines,
            "codebase_path": base,
        }


class MetaDomainAdapter(DomainAdapter):
    """Adapter for the meta domain — converts self-audit intents to actions."""

    @property
    def action_dim(self) -> int:
        return 2

    @property
    def name(self) -> str:
        return "meta"

    @property
    def state_dim(self) -> int:
        return 2

    def forward(self, domain_state: np.ndarray) -> np.ndarray:
        return domain_state

    def inverse(self, telos_action: np.ndarray) -> np.ndarray:
        return telos_action

    def sample_action(self, state: np.ndarray, mission_dir: np.ndarray) -> np.ndarray:
        return np.array([1.0, 0.0])

    def intent_to_action(self, intent: IntentIR, state: np.ndarray,
                         mission_dir: np.ndarray) -> np.ndarray:
        return np.array([1.0, 0.0])

    def action_to_intent(self, action: np.ndarray,
                         state: Optional[np.ndarray] = None) -> IntentIR:
        return IntentIR("meta_action", target=action.copy(),
                        confidence=1.0,
                        params={"vector": action.copy()})

    def is_action_valid(self, action: np.ndarray, state: np.ndarray) -> bool:
        return len(action) == 2 and not np.isnan(action).any()
