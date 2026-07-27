"""Belief Capital — ideas accumulate evidence, trust, influence. Earn the right to affect decisions."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger('telos_belief_capital')


@dataclass
class BeliefCapitalAccount:
    idea_id: str
    idea_name: str
    evidence: float = 0.0
    trust: float = 0.0
    influence: float = 0.0
    predictions_correct: int = 0
    predictions_total: int = 0

    @property
    def accuracy(self) -> float:
        return self.predictions_correct / max(self.predictions_total, 1)

    @property
    def capital(self) -> float:
        return (self.evidence * 0.4 + self.trust * 0.3 +
                self.influence * 0.2 + self.accuracy * 0.1)

    def record_prediction(self, correct: bool) -> None:
        self.predictions_total += 1
        if correct:
            self.predictions_correct += 1
            self.evidence = min(1.0, self.evidence + 0.1)
            self.trust = min(1.0, self.trust + 0.05)
        else:
            self.trust = max(0.0, self.trust - 0.05)


class BeliefCapitalMarket:
    """Market where ideas earn capital through prediction, compression, bridging."""

    def __init__(self):
        self._accounts: Dict[str, BeliefCapitalAccount] = {}
        self._count: int = 0

    def register(self, idea_id: str, name: str) -> BeliefCapitalAccount:
        acct = BeliefCapitalAccount(idea_id=idea_id, idea_name=name)
        self._accounts[idea_id] = acct
        return acct

    def get(self, idea_id: str) -> Optional[BeliefCapitalAccount]:
        return self._accounts.get(idea_id)

    def record_prediction(self, idea_id: str, correct: bool) -> None:
        acct = self._accounts.get(idea_id)
        if acct:
            acct.record_prediction(correct)

    def top_ideas(self, n: int = 5) -> List[BeliefCapitalAccount]:
        return sorted(self._accounts.values(), key=lambda a: a.capital, reverse=True)[:n]

    def to_dict(self) -> dict:
        return {
            "total_ideas": len(self._accounts),
            "top_ideas": [
                {"name": a.idea_name, "capital": round(a.capital, 3)}
                for a in self.top_ideas(3)
            ],
        }
