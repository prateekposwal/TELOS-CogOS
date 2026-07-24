"""
TELOS Controller: High-level API wrapper.
"""
from typing import Dict, Any, Optional
import numpy as np
from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos_rte import TelosRTE


class TelosController:
    """High-level wrapper to simplify pipeline interaction."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.pipeline = TelosV14Pipeline(config)
        self.adapter = config.adapter if config else None
        self._config = config
        self.is_initialized = True

    def initialize(self) -> None:
        """Initialize the controller."""
        self.is_initialized = True

    def think(self, state: np.ndarray, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a pipeline step."""
        if not self.is_initialized:
            raise RuntimeError("Controller not initialized")
        
        result = self.pipeline.execute(state, context)
        
        action = (result.selected_trajectory.get_action_sequence()[0]
                  if result.selected_trajectory else None)
        
        intent = None
        if result.selected_intent:
            intent = {
                "intent_type": result.selected_intent.intent_type,
                "source": result.selected_intent.source,
                "target": result.selected_intent.target,
                "confidence": result.selected_intent.confidence,
                "params": result.selected_intent.params,
            }
        
        return {
            "action": action,
            "intent": intent,
            "health": result.health_score,
            "safety_passed": result.safety_passed,
            "safety_level": result.safety_level,
            "transform_chain": result.transform_chain,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Retrieve system metrics."""
        return self.pipeline.get_statistics()
