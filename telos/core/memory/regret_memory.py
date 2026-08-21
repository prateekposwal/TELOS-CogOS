"""
RegretMemory — Counterfactual "What If" Archival.

Prateek's insight #6: "Regret Memory — counterfactual history:
'would alternative B have been better?' Archival of what-ifs."

The current system generates counterfactual options (StrategicOption)
but discards them after each cycle. RegretMemory preserves these
alternatives and evaluates them retroactively when the outcome is known.

Architecture:
  - Each cycle, store the top-K counterfactual options alongside the chosen action
  - After outcome is known, evaluate: "would option B have been better?"
  - Regret = utility(chosen) - utility(best_alternative)
  - Regret is tracked per decision type, per stream, per context
  - High regret on a decision type → adjust future selection preference

This is NOT the same as learning (ExperienceManager) which indexes
successful skills. This is about preserving forgotten alternatives
and learning from what was NOT chosen.
"""

from __future__ import annotations

import logging
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger('telos_regret_memory')


@dataclass
class CounterfactualEntry:
    """A counterfactual trajectory that was NOT selected."""
    option_id: str
    intent_type: str
    simulated_score: float  # predicted utility at decision time
    actual_score: float     # retroactively evaluated (if possible)
    would_have_been_better: Optional[bool]  # set after outcome evaluation
    regret: Optional[float]  # set after outcome evaluation
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegretRecord:
    """A full record of one decision and its counterfactuals."""
    cycle: int
    timestamp: float
    chosen_intent: str
    chosen_score: float
    chosen_outcome: float  # actual outcome after execution
    counterfactuals: List[CounterfactualEntry]
    regret: float  # max regret across all counterfactuals
    decision_type: str  # exploration vs exploitation
    context_hash: str  # hash of state context for similarity matching


class RegretMemory:
    """Archival of counterfactual what-ifs with retroactive evaluation.

    The regret memory stores:
      - What was chosen and how it turned out
      - What was NOT chosen (counterfactuals) and how they would have done

    Regret is computed per decision type and used to:
      - Adjust future selection preferences
      - Identify systematic blind spots
      - Generate "lessons learned" for the TheoryBuilder
    """

    def __init__(self, max_records: int = 500):
        self._records: List[RegretRecord] = []
        self._max_records = max_records
        self._total_regret: float = 0.0
        self._regret_by_type: Dict[str, List[float]] = defaultdict(list)
        self._total_counterfactuals: int = 0

    def record_decision(self, cycle: int,
                         chosen_intent: str,
                         chosen_score: float,
                         chosen_outcome: float,
                         counterfactual_options: List[Dict],
                         decision_type: str = "unknown",
                         context_hash: str = "") -> RegretRecord:
        """Record a decision and its counterfactuals.

        Args:
            cycle: Pipeline cycle
            chosen_intent: The intent that was selected
            chosen_score: The utility score of the chosen intent
            chosen_outcome: The actual outcome after execution (0-1)
            counterfactual_options: List of dicts with 'intent_type', 'score', 'metadata'
            decision_type: Category of decision (explore, exploit, etc.)
            context_hash: Hash of the decision context for similarity matching

        Returns:
            RegretRecord with computed regrets
        """
        # Create counterfactual entries
        counterfactuals: List[CounterfactualEntry] = []
        for i, opt in enumerate(counterfactual_options):
            entry = CounterfactualEntry(
                option_id=f"cf_{cycle}_{i}",
                intent_type=opt.get('intent_type', 'unknown'),
                simulated_score=opt.get('score', 0.0),
                actual_score=opt.get('score', 0.0),  # same as sim score initially
                would_have_been_better=None,  # set later if evaluated
                regret=None,  # set later
                metadata=opt.get('metadata', {}),
            )
            counterfactuals.append(entry)

        # Compute regrets
        best_alternative = max(
            [cf.simulated_score for cf in counterfactuals],
            default=chosen_score
        )
        regret = max(0.0, best_alternative - chosen_outcome)

        # Set would_have_been_better for each counterfactual
        for cf in counterfactuals:
            cf.would_have_been_better = cf.simulated_score > chosen_outcome
            cf.regret = max(0.0, cf.simulated_score - chosen_outcome)

        record = RegretRecord(
            cycle=cycle,
            timestamp=time.time(),
            chosen_intent=chosen_intent,
            chosen_score=chosen_score,
            chosen_outcome=chosen_outcome,
            counterfactuals=counterfactuals,
            regret=regret,
            decision_type=decision_type,
            context_hash=context_hash,
        )

        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records.pop(0)

        self._total_regret += regret
        self._regret_by_type[decision_type].append(regret)
        self._total_counterfactuals += len(counterfactuals)

        if regret > 0.1:
            logger.info(
                f"RegretMemory: regret={regret:.3f} (chose {chosen_intent} "
                f"over best alternative {best_alternative:.3f})"
            )

        return record

    def query_similar_contexts(self, context_hash: str,
                                top_k: int = 5) -> List[RegretRecord]:
        """Find similar past decisions by context hash.

        Currently uses exact hash match; could be upgraded to
        embedding-based similarity.
        Args:
            context_hash: the context_hash argument for this call.
            top_k: the top_k argument for this call.
        """
        matches = [
            r for r in self._records
            if r.context_hash == context_hash
        ]
        return matches[-top_k:] if matches else []

    def get_regret_by_type(self, decision_type: str) -> Tuple[float, int]:
        """Get average regret and count for a decision type.
            Args:
                decision_type: the decision_type argument for this call.
        """
        regrets = self._regret_by_type.get(decision_type, [])
        if not regrets:
            return (0.0, 0)
        return (sum(regrets) / len(regrets), len(regrets))

    def get_highest_regret_decisions(self, top_n: int = 5) -> List[RegretRecord]:
        """Get the decisions with highest regret.
            Args:
                top_n: the top_n argument for this call.
        """
        sorted_records = sorted(self._records, key=lambda r: r.regret, reverse=True)
        return sorted_records[:top_n]

    def get_decision_types_with_most_regret(self) -> List[Tuple[str, float]]:
        """Get decision types sorted by average regret."""
        avg_regrets = []
        for dtype, regrets in self._regret_by_type.items():
            avg = sum(regrets) / len(regrets) if regrets else 0.0
            avg_regrets.append((dtype, avg))
        avg_regrets.sort(key=lambda x: x[1], reverse=True)
        return avg_regrets

    def get_blind_spots(self) -> List[Dict]:
        """Identify systematic blind spots from high-regret patterns.

        A blind spot is a decision type where:
          - The system consistently picks suboptimal options
          - Counterfactuals would have been significantly better
        """
        blind_spots = []
        for dtype, regrets in self._regret_by_type.items():
            avg_regret = sum(regrets) / len(regrets) if regrets else 0.0
            if avg_regret > 0.2 and len(regrets) > 3:
                blind_spots.append({
                    "decision_type": dtype,
                    "avg_regret": round(avg_regret, 3),
                    "count": len(regrets),
                    "severity": "high" if avg_regret > 0.5 else "medium",
                })
        return blind_spots

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def average_regret(self) -> float:
        if not self._records:
            return 0.0
        return self._total_regret / len(self._records)

    def to_dict(self) -> Dict:
        return {
            "total_records": self.record_count,
            "total_counterfactuals": self._total_counterfactuals,
            "average_regret": round(self.average_regret, 4),
            "regret_by_type": {
                dtype: {
                    "avg": round(sum(r) / len(r), 4) if r else 0.0,
                    "count": len(r),
                }
                for dtype, r in self._regret_by_type.items()
            },
            "blind_spots": self.get_blind_spots(),
            "highest_regret": [
                {
                    "cycle": r.cycle,
                    "chosen": r.chosen_intent,
                    "regret": round(r.regret, 3),
                }
                for r in self.get_highest_regret_decisions(3)
            ],
        }
