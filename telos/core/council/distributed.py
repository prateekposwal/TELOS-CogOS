"""Distributed Council — multi-agent validation with secondary agents.

The DistributedCouncil is the "crew" layer (one plans, several look, one
checks the others for lies/gaps): multiple perspective-agents each evaluate
the selected intent independently, then aggregate into a weighted verdict.

Architecture honesty note: agents are IN-PROCESS secondary perspectives,
not forked processes or sub-pipelines. Each role re-scores the SAME primary
council evidence (the validator signals) through a role-specific weighting
profile — a skeptic weights dissent heavier, a conservative enforces a DI
floor and MD cap, an explorer rewards novelty/alternatives (Λ4.3). The
aggregate is ADVISORY: it never weakens the primary council's blocking power
(Λ1.2 Process over Outcomes — the primary verdict stays binding).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger('telos_distributed_council')


class AgentRole(str, Enum):
    PRIMARY = "primary"
    SKEPTIC = "skeptic"
    EXPLORER = "explorer"
    CONSERVATIVE = "conservative"
    ANALYST = "analyst"
    DOMAIN_EXPERT = "domain_expert"
    # Deprecated alias: typo fixed 2026-08-14 (PRIMARAY -> PRIMARY).
    # Kept for compatibility with any serialized telemetry/checkpoints.
    PRIMARAY = "primary"


@dataclass
class AgentVerdict:
    agent_id: str
    role: AgentRole
    validated: bool
    decision_integrity: float
    mission_drift: float
    signals: List[Dict] = field(default_factory=list)
    weight: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "validated": self.validated,
            "decision_integrity": round(self.decision_integrity, 4),
            "mission_drift": round(self.mission_drift, 4),
            "signals": self.signals,
            "weight": self.weight,
        }


# Default agent weight per role (consensus authority: PRIMARY > SKEPTIC >
# CONSERVATIVE > EXPLORER > ANALYST).
ROLE_WEIGHTS: Dict[AgentRole, float] = {
    AgentRole.PRIMARY: 1.0,
    AgentRole.SKEPTIC: 0.8,
    AgentRole.EXPLORER: 0.6,
    AgentRole.CONSERVATIVE: 0.7,
    AgentRole.ANALYST: 0.5,
    AgentRole.DOMAIN_EXPERT: 0.6,
}


# Per-role evidence re-weighting profiles. Each perspective re-scores the
# primary council's signals with a role-specific lens — the same evidence,
# different emphasis (this is the "several look" part of the crew model).
ROLE_PROFILES: Dict[AgentRole, Dict[str, Any]] = {
    AgentRole.PRIMARY: {
        "dissent_multiplier": 1.0, "pass_multiplier": 1.0,
        "di_floor": 0.0, "md_cap": float("inf"), "novelty": False,
    },
    AgentRole.SKEPTIC: {
        "dissent_multiplier": 1.6, "pass_multiplier": 0.7,
        "di_floor": 0.35, "md_cap": float("inf"), "novelty": False,
    },
    AgentRole.CONSERVATIVE: {
        "dissent_multiplier": 1.3, "pass_multiplier": 0.9,
        "di_floor": 0.5, "md_cap": 1.5, "novelty": False,
    },
    AgentRole.EXPLORER: {
        "dissent_multiplier": 0.6, "pass_multiplier": 1.2,
        "di_floor": 0.0, "md_cap": float("inf"), "novelty": True,
    },
    AgentRole.ANALYST: {
        "dissent_multiplier": 1.0, "pass_multiplier": 1.0,
        "di_floor": 0.0, "md_cap": float("inf"), "novelty": False,
    },
    AgentRole.DOMAIN_EXPERT: {
        "dissent_multiplier": 1.4, "pass_multiplier": 1.1,
        "di_floor": 0.35, "md_cap": float("inf"), "novelty": False,
    },
}


class DistributedCouncil:
    """Multi-agent council that aggregates verdicts from secondary agents.

    Deterministic and cheap: run_perspectives() computes every role's
    verdict from the primary council's signals with role-modulated weights —
    no sub-pipelines, no forked processes, no randomness.
    """

    DISSENT_FLOOR = 0.3  # mirrors Council._compute_decision_integrity

    def __init__(self):
        self._agents: Dict[str, AgentRole] = {}
        self._agent_votes: Dict[str, AgentVerdict] = {}
        self._min_agents = 1

    def register_agent(self, agent_id: str, role: AgentRole = AgentRole.ANALYST) -> None:
        self._agents[agent_id] = role
        logger.info(f"DistributedCouncil: registered agent '{agent_id}' as {role.value}")

    def register_default_crew(self) -> None:
        """Register the standard five-agent crew (one plans, several look,
        one checks for lies/gaps): PRIMARY + four secondary perspectives."""
        self.register_agent("primary", AgentRole.PRIMARY)
        self.register_agent("skeptic", AgentRole.SKEPTIC)
        self.register_agent("explorer", AgentRole.EXPLORER)
        self.register_agent("conservative", AgentRole.CONSERVATIVE)
        self.register_agent("analyst", AgentRole.ANALYST)

    def submit_verdict(self, agent_id: str, validated: bool, di: float, md: float,
                       signals: Optional[List[Dict]] = None) -> None:
        role = self._agents.get(agent_id, AgentRole.ANALYST)
        weight = ROLE_WEIGHTS.get(role, 0.5)
        self._agent_votes[agent_id] = AgentVerdict(
            agent_id=agent_id, role=role, validated=validated,
            decision_integrity=di, mission_drift=md,
            signals=signals or [], weight=weight,
        )

    def reset(self) -> None:
        """Clear votes between cycles (cadence support)."""
        self._agent_votes.clear()

    # ── Role perspectives: re-score the primary evidence through role lenses ──

    @staticmethod
    def _score_signals(signals: List[Dict], profile: Dict[str, Any]) -> float:
        """DI = 1 - sum(ignored * belief_confidence) / total_evidence,
        exactly mirroring Council._compute_decision_integrity, but with
        role-modulated evidence weights (dissent weighted differently from
        passes per perspective).

        Args:
            signals: primary council ValidationSignal dicts
            profile: role re-weighting profile (dissent/pass multipliers)

        Returns:
            Role-modulated decision integrity in [0, 1].
        """
        total = 0.0
        ignored = 0.0
        has_block = False
        for s in signals:
            passed = s.get("passed", True)
            conf = abs(float(s.get("confidence", 0.5)))
            ew = float(s.get("evidence_weight", 0.5))
            if passed:
                ew *= profile["pass_multiplier"]
            else:
                ew *= profile["dissent_multiplier"]
                has_block = True
            total += ew
            if not passed:
                ignored += ew * conf
        total = total or 1e-9
        di = float(max(0.0, min(1.0, 1.0 - ignored / total)))
        if has_block:
            di = min(di, DistributedCouncil.DISSENT_FLOOR)
        return di

    @staticmethod
    def _role_validated(role: AgentRole, primary_validated: bool, di: float,
                        md: float, profile: Dict[str, Any], context: Dict[str, Any]) -> bool:
        if role == AgentRole.SKEPTIC:
            # Skeptic: any unexplained low-confidence pass is a red flag.
            return primary_validated and di >= profile["di_floor"]
        if role == AgentRole.CONSERVATIVE:
            # Conservative: DI floor + mission-drift cap on top of primary.
            return primary_validated and di >= profile["di_floor"] and md <= profile["md_cap"]
        if role == AgentRole.EXPLORER:
            # Explorer: novelty/alternative-awareness (Λ4.3 Possibility
            # Preservation) — validates when alternatives exist or curiosity
            # is high, even if the primary was cautious. DI is still honest.
            if primary_validated:
                return True
            alternatives = context.get("alternatives") or []
            curiosity = float(context.get("curiosity_bonus", 1.0))
            return (len(alternatives) >= 2) or (curiosity > 1.2)
        if role == AgentRole.DOMAIN_EXPERT:
            # Domain lens (v9): the perceive-phase consult_knowledge report
            # lists proven approaches and known failures (avoid). A candidate
            # on the avoid list dissents regardless of the primary — the
            # domain evidence contradicts it. Otherwise mirrors the primary.
            # Advisory only, like every crew role (Λ1.2); the aggregation
            # formula is unchanged — this is one more weighted vote.
            krep = context.get("knowledge_report") or {}
            avoid = krep.get("avoid") or []
            candidate = context.get("intent_type", "")
            listed = any(
                (a.get("approach") if isinstance(a, dict) else a) == candidate
                for a in avoid
            )
            return (not listed) and primary_validated
        if role == AgentRole.ANALYST:
            return primary_validated
        return primary_validated

    def run_perspectives(self, primary_verdict: Any, context: Optional[Dict[str, Any]] = None) -> Dict:
        """Evaluate the selected intent from every registered role's
        perspective, then aggregate into a weighted consensus.

        Args:
            primary_verdict: the binding CouncilVerdict from the primary council
            context: dict with intent_type, confidence, alternatives,
                uncertainty, curiosity_bonus, criticality, n_sim_options.

        Returns:
            Aggregated verdict dict: validated, decision_integrity,
            mission_drift, signals, per-agent details, consensus.
        """
        context = context or {}
        # v9 DOMAIN_EXPERT lens: when the context carries domain knowledge (a
        # proven approach or known failures) the domain_expert agent joins the
        # crew, idempotently, for this and future cycles (crew memory). The
        # default five-agent crew is untouched on knowledge-less cycles
        # (locked by test_register_default_crew_has_five_agents) and the
        # aggregation formula is unchanged. On later cycles without knowledge
        # the lens votes a neutral mirror of the primary (nothing listed).
        krep = context.get("knowledge_report") or {}
        if isinstance(krep, dict) and (krep.get("approach") or krep.get("avoid")):
            self.register_agent("domain_expert", AgentRole.DOMAIN_EXPERT)
        if primary_verdict is None:
            return {"validated": True, "decision_integrity": 1.0,
                    "mission_drift": 0.0, "signals": [], "agents": [],
                    "consensus": 1.0}

        primary_signals = [
            {
                "validator_name": getattr(s, "validator_name", "unknown"),
                "passed": getattr(s, "passed", True),
                "confidence": getattr(s, "confidence", 0.5),
                "reason": getattr(s, "reason", ""),
                "evidence_weight": getattr(s, "evidence_weight", 0.5),
            }
            for s in getattr(primary_verdict, "signals", []) or []
        ]
        primary_validated = getattr(primary_verdict, "validated", True)
        primary_di = float(getattr(primary_verdict, "decision_integrity", 1.0))
        primary_md = float(getattr(primary_verdict, "mission_drift", 0.0))

        if not self._agents:
            self.register_default_crew()

        self.reset()
        for agent_id, role in self._agents.items():
            profile = ROLE_PROFILES.get(role, ROLE_PROFILES[AgentRole.ANALYST])
            di = self._score_signals(primary_signals, profile) if primary_signals else primary_di
            # Primary's md is a measurement, not an opinion — every role sees it.
            md = primary_md
            if role == AgentRole.PRIMARY:
                di = primary_di  # PRIMARY mirrors the binding verdict exactly
            validated = self._role_validated(role, primary_validated, di, md, profile, context)
            role_signals = [{
                "validator_name": f"distributed::{role.value}",
                "passed": validated,
                "confidence": round(di, 4),
                "reason": (f"role lens {role.value}: di={di:.3f} md={md:.3f} "
                           f"primary_validated={primary_validated}"),
                "evidence_weight": ROLE_WEIGHTS.get(role, 0.5),
            }]
            self.submit_verdict(agent_id, validated, di, md, role_signals)

        aggregate = self.aggregate()
        votes = list(self._agent_votes.values())
        validated_count = sum(1 for v in votes if v.validated)
        return {
            "validated": aggregate.validated,
            "decision_integrity": aggregate.decision_integrity,
            "mission_drift": aggregate.mission_drift,
            "signals": aggregate.signals,
            "agents": [v.to_dict() for v in votes],
            "consensus": round(validated_count / max(len(votes), 1), 3),
            "n_agents": len(votes),
        }

    def aggregate(self) -> AgentVerdict:
        votes = list(self._agent_votes.values())
        if not votes:
            return AgentVerdict("none", AgentRole.PRIMARY, True, 1.0, 0.0)

        total_weight = sum(v.weight for v in votes)
        if total_weight == 0:
            total_weight = 1.0

        avg_di = sum(v.decision_integrity * v.weight for v in votes) / total_weight
        avg_md = sum(v.mission_drift * v.weight for v in votes) / total_weight
        # Weighted majority: consensus authority follows weights, not raw count.
        validated_weight = sum(v.weight for v in votes if v.validated)
        validated = validated_weight > total_weight / 2

        all_signals = []
        for v in votes:
            all_signals.extend(v.signals)

        return AgentVerdict(
            agent_id="aggregated", role=AgentRole.PRIMARY,
            validated=validated, decision_integrity=avg_di,
            mission_drift=avg_md, signals=all_signals,
            weight=1.0,
        )

    def to_dict(self) -> Dict:
        return {
            "registered_agents": len(self._agents),
            "voting_agents": len(self._agent_votes),
            "agents": {aid: r.value for aid, r in self._agents.items()},
        }
