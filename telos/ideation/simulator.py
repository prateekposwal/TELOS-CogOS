"""
IdeationSimulator — encodes the product-ideation task as a TELOS state space.

Design:
  - state: a fixed context vector whose components are the STRUCTURAL-INSIGHT
    scores active in the market (platform-take, churn, cheating, esports-moat,
    asset-provenance, dead-game, 25+dad, server-infra). This is the PERCEIVE
    layer's map, made numeric so the pipeline can reason over it.
  - simulate(state, horizon): branches into distinct candidate-future worlds,
    one per out-of-the-box concept. Each returned World carries its concept's
    full 8-axis score vector + name + the structural insight it exploits.
  - evaluate(): weighted veteran-lens composite (moat + resilience at 1.5x).
"""
import numpy as np
from typing import List, Dict, Any, Optional

from telos.core.contracts.domain_model import DomainSimulator, EvaluationReport
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.ideation.concepts import CONCEPTS, weighted_score, STRUCTURAL_INSIGHTS

# State layout: index -> structural insight activation (0..1), PERCEIVE map
STATE_INDEX = {
    "platform_take": 0,
    "churn_lifecycle": 1,
    "cheating_economy": 2,
    "esports_money_flow": 3,
    "asset_provenance": 4,
    "dead_game_afterlife": 5,
    "casual_dad_25plus": 6,
    "server_community_infra": 7,
}

STATE_LABELS = [k for k in STATE_INDEX]

# Competitor layer (added in the re-run; the PRIOR run excluded these).
# `discord_bots` was in the prior PERCEIVE "excluded" list — the exact blind
# spot this re-run removes.
BOT_ECOSYSTEM_INDEX = {
    "bot_ecosystem": 8,   # incumbent Discord-bot saturation (was excluded)
}



class IdeationSimulator(DomainSimulator):
    def __init__(self, concept_subset: Optional[List[int]] = None,
                 with_bot_ecosystem: bool = False,
                 extra_concepts: Optional[List[dict]] = None):
        # The veteran's PERCEIVE map: how structurally charged each pressure is.
        self.context = np.array([
            0.90,  # platform_take: storefronts own the wallet → renters
            0.95,  # churn_lifecycle: LTV cliff, nobody owns cross-game retention
            0.85,  # cheating_economy: monetized cheating → trust infra viable
            0.85,  # esports_money_flow: money stuck at the top
            0.80,  # asset_provenance: accounts are the real financial instrument
            0.65,  # dead_game_afterlife: culture vaporizes on server death
            0.70,  # casual_dad_25plus: money + no time, mislabeled "casual"
            0.80,  # server_community_infra: fragmented volunteer-run fabric
        ], dtype=float)
        # Competitor layer: 0.95 saturation = the bot set is mature, crowded,
        # often free, and has a curated directory. LOADED in the re-run.
        if with_bot_ecosystem:
            self.context = np.append(self.context, 0.95)
        self._with_bot = with_bot_ecosystem
        self._extra_concepts = extra_concepts or []
        # Extend the concept space with the new cross-server concepts when active.
        self._all_concepts = list(CONCEPTS) + self._extra_concepts
        self._subset = concept_subset or list(range(len(self._all_concepts)))
        self._positions: List[int] = []

    # ── DomainSimulator contract ────────────────────────────────────────
    def initialize(self): self._positions = []

    def cleanup(self): pass

    def legal_transitions(self, state: np.ndarray) -> List[np.ndarray]:
        # Ideation is single-step: each concept is one branch. Identity/no-op.
        return [np.zeros_like(state)]

    def transition(self, state: np.ndarray, action: np.ndarray) -> np.ndarray:
        return state.copy()

    def get_facts(self, state: np.ndarray) -> DomainFacts:
        metrics = {}
        idxmap = {**STATE_INDEX, **BOT_ECOSYSTEM_INDEX}
        for k, i in idxmap.items():
            if i < len(self.context):
                metrics[k] = float(self.context[i])
        return DomainFacts(
            state=state.copy(),
            resources={"structural_pressure": float(np.mean(self.context)),
                       "n_insights": float(len(self.context))},
            constraints=[],
            events=["ideation_task"],
            metrics=metrics,
            metadata={
                "task": "out_of_the_box_gaming_product_ideation",
                "frame": "industry_structure_not_surface_pain",
                "excluded": (["clips", "stats_platforms", "content_tools"]
                             if not self._with_bot else
                             ["clips", "stats_platforms", "content_tools"]),
                "competitor_layer_loaded": self._with_bot,
                "structural_map": {k: STRUCTURAL_INSIGHTS[k] for k in STATE_INDEX},
                "state_labels": STATE_LABELS,
            },
        )

    def simulate(self, state: np.ndarray, horizon: int) -> List[World]:
        worlds = []
        for idx in self._subset:
            concept = self._all_concepts[idx]
            # Encode this concept branch: context + concept index + axes.
            vec = np.concatenate([self.context, np.array([idx / 10.0, 0.0])])
            metadata = {
                "concept_index": idx,
                "concept_name": concept["name"],
                "insight_key": concept["insight_key"],
                "axes": concept["axes"],
                "weighted_score": weighted_score(concept["axes"]),
                "is_concept": True,
                "horizon": horizon,
            }
            for _ in range(max(1, min(3, horizon))):
                worlds.append(World(state=vec.copy(), metadata=metadata))
        self._positions = list(self._subset)
        return worlds

    def terminal(self, state: np.ndarray) -> bool:
        return False

    def evaluate(self, state: np.ndarray) -> EvaluationReport:
        meta = getattr(state, 'metadata', None) if not isinstance(state, np.ndarray) else None
        # When evaluate() receives a World (CounterfactualEngine passes world.state),
        # we won't have metadata here — so we store axis scores on the state tail.
        axes = None
        # The state tail encodes [concept_index/10, weighted/10]; but axes are in
        # metadata which isn't attached to world.state. Use the state tail to carry
        # the composite via metadata attached to the World instead.
        if isinstance(state, np.ndarray) and len(state) >= len(self.context) + 2:
            # concept index lives at position len(context); weighted at +1
            concept = state[len(self.context)] * 10.0
            idx = int(round(concept))
            if 0 <= idx < len(self._all_concepts):
                axes = self._all_concepts[idx]["axes"]
        if axes is None:
            return EvaluationReport(objectives={"concept_value": 0.01}, risks=0.0)
        w = weighted_score(axes)
        return EvaluationReport(
            objectives={
                "market": axes["market_size"],
                "feasibility": axes["feasibility"],
                "differentiation": axes["differentiation"],
                "data_access": axes["data_access"],
                "user_love": axes["user_love"],
                "monetization": axes["monetization"],
                "moat_resilience": w,  # veteran composite
            },
            risks=1.0 - axes["resilience"],  # fragility term (lower resilience = more risk)
        )
