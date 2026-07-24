
"""
Tripartite Uncertainty U = (U_W, U_I, U_O) — three orthogonal uncertainty dimensions.

P0: Formal Mathematical Formalization Gap 1.

U_W: Environmental uncertainty — from observation noise and prediction error.
U_I: Identity uncertainty — from identity entropy trajectory.
U_O: Other-agent uncertainty — from council signal disagreement.

This replaces the single  scalar with a structured
tripartite representation of uncertainty, each with its own semantics.

The module also tracks answered questions and decays uncertainty accordingly,
supporting the InquiryStream's question-answer cycle.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger('telos_uncertainty')


class TripartiteUncertainty:
    """U = (U_W, U_I, U_O) — three orthogonal uncertainty dimensions.
    
    Each dimension captures a distinct source of uncertainty:
      - U_W (Environmental): How noisy/unpredictable is the world?
      - U_I (Identity): How uncertain is the system's own identity?
      - U_O (Other): How much disagreement exists among council/advisors?
    
    New in v14.5: Tracks answered_questions counter and provides decay
    mechanics so that answering questions reduces uncertainty over time.
    """

    def __init__(self):
        self.U_W: float = 0.0  # Environmental uncertainty
        self.U_I: float = 0.0  # Identity uncertainty
        self.U_O: float = 0.0  # Other-agent uncertainty
        self.answered_questions: int = 0  # Counter of questions answered
        self._history: List[Dict[str, float]] = []
        self._max_history: int = 50

    @classmethod
    def compute_from_available(cls, prediction_error=0.0, identity_entropy=0.0, council_signals=None, relational_coherence=1.0):
        """Compute tripartite uncertainty from data available during SELECT phase.
        
        This fixes the timing issue where tripartite U was computed in ACT phase
        but consumed in SELECT phase. By computing from data that is already
        available in SELECT phase, we avoid stale values.
        
        Args:
            prediction_error: Trajectory prediction error (0-1), from attention engine
            identity_entropy: Identity entropy signal (0-1), from identity entropy tracker
            council_signals: List of council ValidationSignal objects from current cycle
            relational_coherence: Coherence of relational reasoning (0-1), default 1.0
            
        Returns:
            TripartiteUncertainty instance with computed values
        """
        instance = cls()
        
        # U_W from prediction error
        instance.U_W = min(1.0, max(0.0, prediction_error * 0.5))
        
        # U_I from identity entropy
        instance.U_I = min(1.0, max(0.0, identity_entropy * 0.3))
        
        # U_O = (1 - relational_coherence) * 0.7 + council_disagreement * 0.3
        if council_signals:
            passed = sum(1 for s in council_signals if getattr(s, 'passed', True))
            total = len(council_signals)
            council_disagreement = 1.0 - (passed / max(total, 1)) if total > 0 else 0.0
        else:
            council_disagreement = 0.0
        instance.U_O = min(1.0, (1.0 - relational_coherence) * 0.7 + council_disagreement * 0.3)
        
        # Record initial snapshot
        instance._history.append({
            "U_W": instance.U_W,
            "U_I": instance.U_I,
            "U_O": instance.U_O,
        })
        
        logger.debug(
            f"Tripartite U computed from available data: U_W={instance.U_W:.3f} "
            f"(pe={prediction_error:.3f}), U_I={instance.U_I:.3f} "
            f"(entropy={identity_entropy:.3f}), U_O={instance.U_O:.3f}"
        )
        
        return instance

    def update(self,
               observation_noise: float = 0.0,
               prediction_error: float = 0.0,
               identity_entropy: float = 0.0,
               council_disagreement: float = 0.0,
               relational_coherence: float = 1.0) -> None:
        """Update all three uncertainty dimensions from observed signals.
        
        Args:
            observation_noise: Measured noise in perception/observation (0-1)
            prediction_error: Trajectory prediction error (0-1)
            identity_entropy: Identity entropy trajectory signal (0-1)
            council_disagreement: Disagreement among council validators (0-1)
            relational_coherence: Coherence of relational reasoning (0-1), default 1.0
        """
        # U_W = observation_noise + prediction_error_clipped
        self.U_W = min(1.0, observation_noise + prediction_error * 0.5)
        
        # U_I = identity_entropy_trajectory (smoothed)
        self.U_I = min(1.0, identity_entropy)
        
        # U_O = (1 - relational_coherence) * 0.7 + council_disagreement * 0.3
        self.U_O = min(1.0, (1.0 - relational_coherence) * 0.7 + council_disagreement * 0.3)

        snapshot = {
            "U_W": self.U_W,
            "U_I": self.U_I,
            "U_O": self.U_O,
        }
        self._history.append(snapshot)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        logger.debug(
            f"Tripartite U updated: U_W={self.U_W:.3f} "
            f"(noise={observation_noise:.3f}, pe={prediction_error:.3f}), "
            f"U_I={self.U_I:.3f} (entropy={identity_entropy:.3f}), "
            f"U_O={self.U_O:.3f} (disagreement={council_disagreement:.3f}, rc={relational_coherence:.3f})"
        )

    def record_answer(self, question_type: str) -> None:
        """Record that a question has been answered and decay uncertainty.
        
        When the InquiryStream generates a question and the system acts on it,
        this method decays the relevant uncertainty dimension(s):
        
        - U_W decays by exp(-answered_questions * 0.3) — each answered question
          provides compounding environmental insight
        - U_I decays by exp(-answered_questions * 0.2) — identity uncertainty
          reduces more slowly (identity is stickier)
        - U_O resets to a low residual — council disagreement is resolved by
          acting on the inquiry
        
        Args:
            question_type: The type of question answered ('explore', 
                          'recalibrate', 'investigate', 'proceed')
        """
        self.answered_questions += 1
        n = self.answered_questions
        
        # Decay U_W: environmental uncertainty reduces with each question
        decay_w = math.exp(-n * 0.3)
        self.U_W = self.U_W * decay_w
        
        # Decay U_I: identity uncertainty reduces more slowly
        decay_i = math.exp(-n * 0.2)
        self.U_I = self.U_I * decay_i
        
        # Reset U_O: council disagreement resolved after acting on inquiry
        self.U_O = self.U_O * 0.1  # 90% reduction
        
        logger.info(
            f"Question answered (type={question_type}, count={n}): "
            f"U_W→{self.U_W:.3f}, U_I→{self.U_I:.3f}, U_O→{self.U_O:.3f} "
            f"(decay: W={decay_w:.3f}, I={decay_i:.3f})"
        )

    def get_dominant(self) -> str:
        """Returns 'environmental', 'identity', or 'other' — the highest U dimension.
        
        If all are below 0.3, returns 'none' (low uncertainty).
        If there's a tie, the dominant dimension is the first highest.
        """
        if self.U_W < 0.3 and self.U_I < 0.3 and self.U_O < 0.3:
            return 'none'
        
        max_val = max(self.U_W, self.U_I, self.U_O)
        if max_val == self.U_W:
            return 'environmental'
        elif max_val == self.U_I:
            return 'identity'
        else:
            return 'other'

    def to_dict(self) -> Dict[str, float]:
        """Return current uncertainty values as a dict."""
        return {
            "U_W": self.U_W,
            "U_I": self.U_I,
            "U_O": self.U_O,
            "answered_questions": self.answered_questions,
            "dominant": self.get_dominant(),
        }

    @property
    def vector(self) -> Tuple[float, float, float]:
        """Return the three uncertainty values as a tuple."""
        return (self.U_W, self.U_I, self.U_O)

    @property
    def composite(self) -> float:
        """Composite uncertainty: L2 norm of the three dimensions, normalized to [0,1]."""
        raw = (self.U_W ** 2 + self.U_I ** 2 + self.U_O ** 2) ** 0.5
        return min(1.0, raw / (3.0 ** 0.5))

    @property
    def history(self) -> List[Dict[str, float]]:
        return list(self._history)

    @property
    def trend(self) -> str:
        """Overall trend: 'rising', 'falling', or 'stable' based on composite history."""
        if len(self._history) < 3:
            return 'stable'
        recent = [h["U_W"] + h["U_I"] + h["U_O"] for h in self._history[-3:]]
        if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)):
            return 'rising'
        if all(recent[i] >= recent[i + 1] for i in range(len(recent) - 1)):
            return 'falling'
        return 'stable'

    def reset(self) -> None:
        """Reset all uncertainty values to zero."""
        self.U_W = 0.0
        self.U_I = 0.0
        self.U_O = 0.0
        self.answered_questions = 0
        self._history.clear()
