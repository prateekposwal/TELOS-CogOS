from abc import ABC, abstractmethod
import numpy as np
from telos.world.world import World
from telos.intent_ir import IntentIR
from telos.core.ledger.skill_library import SkillLibrary

class CognitiveStream(ABC):
    """
    Abstract interface for all cognitive processing streams.
    """
    
    def __init__(self, skill_library: SkillLibrary):
        self.skill_library = skill_library

    @abstractmethod
    def process(self, world: World) -> IntentIR:
        """Process the World and suggest an Intent."""
        ...

    @property
    @abstractmethod
    def priority(self) -> float:
        """The intrinsic priority for attention allocation."""
        ...

    @property
    def estimated_cost_ms(self) -> float:
        """Expected budget cost per process() call, used by StreamPhase for budget checks."""
        return 5.0
