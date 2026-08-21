"""Five-idea trust/attention/infra portfolio — TELOS state-space encoding.

PERCEIVE structural map for the DECENTRALIZED TRUST / AI-INFRA layer:
each component is a structural pressure (0..1) a veteran sees, not surface pain.
"""
import numpy as np
from typing import List, Optional
from telos.core.contracts.domain_model import DomainSimulator, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.ideation.concepts import weighted_score

# structural pressures active in the trust/attention/AI-infra layer
STATE_INDEX = {
    "attention_scarcity": 0,   # attention is economically scarce + unledgered
    "ai_trust_gap": 1,         # LLM/agent outputs are chaotic + unverifiable
    "data_commons_need": 2,    # datasets fragmented, no neutral governance
    "reputation_roots": 3,     # identity/reputation walled per-platform
    "dispute_arbitration": 4,  # no neutral escrow/arbitration rail
}
STATE_LABELS = [k for k in STATE_INDEX]

IDEAS = [
    {
        "key": "A",
        "name": "Proof-of-Attention (Degcentralized Attention Ledger)",
        "pattern": "Bitcoin",
        "axioms": ["4.7", "2.4"],
        "axes": {"market_size": 0.78, "feasibility": 0.42, "differentiation": 0.90,
                 "data_access": 0.60, "user_love": 0.62, "monetization": 0.70,
                 "moat": 0.88, "resilience": 0.55},
    },
    {
        "key": "B",
        "name": "Provenance Trust Layer for AI Outputs",
        "pattern": "PayPal",
        "axioms": ["1.3", "5.1"],
        "axes": {"market_size": 0.85, "feasibility": 0.62, "differentiation": 0.88,
                 "data_access": 0.72, "user_love": 0.70, "monetization": 0.78,
                 "moat": 0.82, "resilience": 0.66},
    },
    {
        "key": "C",
        "name": "Data Commons DAOs",
        "pattern": "Reddit",
        "axioms": ["4.6", "4.11"],
        "axes": {"market_size": 0.70, "feasibility": 0.55, "differentiation": 0.80,
                 "data_access": 0.78, "user_love": 0.68, "monetization": 0.58,
                 "moat": 0.78, "resilience": 0.62},
    },
    {
        "key": "D",
        "name": "Portable Reputation Primitives",
        "pattern": "Hybrid",
        "axioms": ["4.1", "6.4"],
        "axes": {"market_size": 0.76, "feasibility": 0.58, "differentiation": 0.86,
                 "data_access": 0.68, "user_love": 0.80, "monetization": 0.66,
                 "moat": 0.84, "resilience": 0.60},
    },
    {
        "key": "E",
        "name": "Protocol Escrow & Arbitration",
        "pattern": "PayPal-cross",
        "axioms": ["2.3", "4.4"],
        "axes": {"market_size": 0.72, "feasibility": 0.65, "differentiation": 0.82,
                 "data_access": 0.70, "user_love": 0.66, "monetization": 0.80,
                 "moat": 0.80, "resilience": 0.74},
    },
]

class PortfolioSimulator(DomainSimulator):
    def __init__(self, idea_subset: Optional[List[int]] = None):
        self.context = np.array([
            0.82,  # attention_scarcity
            0.88,  # ai_trust_gap
            0.74,  # data_commons_need
            0.78,  # reputation_roots
            0.72,  # dispute_arbitration
        ], dtype=float)
        self._subset = idea_subset or list(range(len(IDEAS)))
        self._positions: List[int] = []

    def initialize(self): self._positions = []
    def cleanup(self): pass
    def legal_transitions(self, state): return [np.zeros_like(state)]
    def transition(self, state, action): return state.copy()
    def terminal(self, state): return False

    def get_facts(self, state):
        metrics = {k: float(self.context[i]) for k, i in STATE_INDEX.items()}
        return DomainFacts(
            state=state.copy(),
            resources={"structural_pressure": float(np.mean(self.context)),
                       "n_insights": float(len(self.context))},
            constraints=[],
            events=["trust_infra_portfolio_task"],
            metrics=metrics,
            metadata={
                "task": "five_idea_trust_attention_infra_portfolio",
                "frame": "industry_structure_not_surface_pain",
                "state_labels": STATE_LABELS,
            },
        )

    def simulate(self, state, horizon):
        worlds = []
        for idx in self._subset:
            idea = IDEAS[idx]
            vec = np.concatenate([self.context, np.array([idx / 10.0, 0.0])])
            meta = {
                "idea_index": idx, "idea_key": idea["key"], "idea_name": idea["name"],
                "pattern": idea["pattern"], "axioms": idea["axioms"],
                "axes": idea["axes"], "weighted_score": weighted_score(idea["axes"]),
                "is_concept": True, "horizon": horizon,
            }
            for _ in range(max(1, min(3, horizon))):
                worlds.append(World(state=vec.copy(), metadata=meta))
        self._positions = list(self._subset)
        return worlds

    def evaluate(self, state):
        axes = None
        if isinstance(state, np.ndarray) and len(state) >= len(self.context) + 2:
            concept = state[len(self.context)] * 10.0
            idx = int(round(concept))
            if 0 <= idx < len(IDEAS):
                axes = IDEAS[idx]["axes"]
        if axes is None:
            return EvaluationReport(objectives={"concept_value": 0.01}, risks=0.0)
        w = weighted_score(axes)
        return EvaluationReport(
            objectives={"market": axes["market_size"], "feasibility": axes["feasibility"],
                        "differentiation": axes["differentiation"], "data_access": axes["data_access"],
                        "user_love": axes["user_love"], "monetization": axes["monetization"],
                        "moat_resilience": w},
            risks=1.0 - axes["resilience"],
        )

    @property
    def name(self): return "trust_portfolio"
    @property
    def state_dim(self): return len(self.context) + 2
    def world_spec(self):
        from telos.core.contracts.domain_model import WorldSpec
        return WorldSpec(name=self.name, state_dim=self.state_dim, action_dim=1,
                         objectives=["concept_value", "market", "feasibility"],
                         constraints=[], observability="high",
                         capabilities=["ideation_branch", "simulate"])
