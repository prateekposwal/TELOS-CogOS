"""
TELOS Chaos Engine: Stress testing for pipeline resilience.
"""
import logging
import numpy as np
from telos_controller import TelosController
from telos.core.runtime import PipelineConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('telos_chaos')

class TelosChaosEngine:
    def __init__(self):
        self.controller = TelosController()

    def test_zero_budget(self):
        logger.info("Running: Zero Budget Stress Test...")
        config = PipelineConfig(compute_budget_ms=0.0001)
        self.controller.pipeline.config = config
        
        state = np.zeros(6)
        try:
            result = self.controller.think(state)
            logger.info("Successfully handled zero budget (fallback utilized).")
        except Exception as e:
            logger.error("FAILED zero budget test: %s", e)

    def test_corrupted_state(self):
        logger.info("Running: Corrupted State Stress Test...")
        state = np.array([np.nan, np.inf, -1.0, 0.5, 0.5, 0.5])
        try:
            result = self.controller.think(state)
            logger.info("Successfully handled corrupted state.")
        except Exception as e:
            logger.error("FAILED corrupted state test: %s", e)

if __name__ == "__main__":
    engine = TelosChaosEngine()
    engine.test_zero_budget()
    engine.test_corrupted_state()
