"""
KnowledgeManager — Knowledge consultation, recording, and perception feedback.

Extracted from InfrastructureManager to reduce god-object complexity.
Handles:
  - Knowledge Graph search and consultation (Lambda 4.7)
  - Outcome recording to KnowledgeGraph (success/failure)
  - UCB outcome recording for exploration bonus
  - SystemSelf identity updates
  - Perception quality feedback loop
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, List, Any

from telos.core.infra_manager.mission_policy import MissionPolicyManager
from telos.core.knowledge.inference import KGInferenceEngine
from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.recommender import KnowledgeRecommender
from telos.core.knowledge.recorder import OutcomeRecorder

logger = logging.getLogger('telos_infra')


class KnowledgeManager:
    """Manages knowledge consultation, recording, and feedback.

    Owned by InfrastructureManager. Provides consultation for the
    Pipeline's perceive phase and records outcomes after each cycle.
    """

    # Domain-specific adjustment scales for risk and exploration
    DOMAIN_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
        "gridworld": {"risk": 0.1, "exploration": 0.1},
        "devdomain": {"risk": 0.03, "exploration": 0.03},
        "default":   {"risk": 0.05, "exploration": 0.05},
    }

    def __init__(self, policy: MissionPolicyManager, system_self, domain: str = "gridworld"):
        self.policy = policy
        self.system_self = system_self
        self.domain = domain
        self.knowledge = KnowledgeGraph(max_hot_nodes=100)
        self.inference = KGInferenceEngine(self.knowledge)
        self.recommender = KnowledgeRecommender(self.knowledge)
        self.recorder = OutcomeRecorder(self.knowledge)
        self._last_consultation: Dict[str, int] = {}

    def _get_domain_scale(self, key: str) -> float:
        """Get the domain-specific adjustment scale factor.
        
        Returns the scale factor for the given adjustment key (risk or exploration)
        based on the current domain configuration. Falls back to 'default' if the
        domain is not found.
        """
        return self.DOMAIN_ADJUSTMENTS.get(self.domain, self.DOMAIN_ADJUSTMENTS["default"]).get(key, 0.05)

    def search_knowledge(self, domain: str, top_k: int = 5) -> List[Any]:
        """Search the knowledge graph for proven solutions in a domain."""
        return self.knowledge.search(domain, top_k=top_k, min_outcome=0.51)

    def consult_knowledge(self, domain: str, cycle: int = 0) -> Dict:
        """Consult KnowledgeGraph before the Pipeline executes.

        Returns a consultation report with:
          - approach: best proven approach or None
          - outcome: its proven outcome score
          - adjust_risk: suggested risk_tolerance adjustment
          - adjust_exploration: suggested exploration_budget adjustment
          - avoid: list of approaches that failed in this domain
          - summary: human-readable text

        P2.6: Tracks last consultation cycle per domain. Policy adjustments
        are only applied once per 3 cycles per domain to prevent
        over-adjustment from repeated consultations in the same domain.
        """
        last = self._last_consultation.get(domain, -999)
        if cycle - last < 3:
            return {
                "domain": domain,
                "approach": None,
                "outcome": None,
                "avoid": [],
                "adjust_risk": 0.0,
                "adjust_exploration": 0.0,
                "summary": f"Consultation throttled for '{domain}' (last cycle {last})",
                "quality_adjustment": 0.0,
                "throttled": True,
            }
        self._last_consultation[domain] = cycle

        proven = self.knowledge.search(domain, top_k=3, min_outcome=0.51)
        failed = self.knowledge.search_failures(domain, top_k=3)

        report: Dict[str, Any] = {
            "domain": domain,
            "approach": proven[0].approach if proven else None,
            "outcome": proven[0].outcome if proven else None,
            "avoid": [{"approach": n.approach, "reason": n.failure_reason} for n in failed],
            "summary": "",
        }

        if proven:
            best = proven[0]
            report["summary"] = f"Knowledge: {best.approach} scored {best.outcome:.2f}"
            if best.outcome > 0.85:
                report["adjust_risk"] = 0.1 * self._get_domain_scale("risk")
                report["adjust_exploration"] = -0.1 * self._get_domain_scale("exploration")
                report["summary"] += " — exploiting proven strategy"
            else:
                report["adjust_risk"] = 0.0
                report["adjust_exploration"] = 0.0
                report["summary"] += " — moderate confidence, maintaining policy"
            self.knowledge.activate(best.node_id)
        else:
            report["adjust_risk"] = -0.05 * self._get_domain_scale("risk")
            report["adjust_exploration"] = 0.05 * self._get_domain_scale("exploration")
            report["summary"] = f"No proven approach for '{domain}' — exploring"

        if failed:
            report["summary"] += f" | {len(failed)} known failures"
            report["adjust_risk"] = (report.get("adjust_risk", 0) or 0) - 0.05 * self._get_domain_scale("risk")
            report["adjust_exploration"] = (report.get("adjust_exploration", 0) or 0) + 0.05 * self._get_domain_scale("exploration")

        quality_adjustments = self.knowledge.search(tags=["quality_adjustment"], top_k=3)
        if quality_adjustments:
            total_adj = sum(
                p.params.get("suggested_adjustment", 0)
                for p in quality_adjustments
                if hasattr(p, 'params')
            )
            report["quality_adjustment"] = total_adj
            report["summary"] += f" | quality_adj={total_adj:+.3f}"
        else:
            report["quality_adjustment"] = 0.0

        if report.get("adjust_risk"):
            self.policy.adjust_risk_tolerance(report["adjust_risk"])
        if report.get("adjust_exploration"):
            self.policy.adjust_exploration_budget(report["adjust_exploration"])

        logger.info(f"[ConsultKnowledge] {report['summary']}")
        return report

    def observe(self, result, failure, trace):
        """Record outcomes, update UCB, identity, and perception quality.

        Args:
            result: PipelineResult from the current cycle.
            failure: FailureRecord or None from upstream detection.
            trace: DecisionTrace or None.

        Returns:
            The (possibly updated) failure for downstream consumers.
        """
        if not (hasattr(result, 'decision_trace') and result.decision_trace):
            self.knowledge.tick()
            return failure

        dt = result.decision_trace
        domain = getattr(result, 'domain', 'unknown')
        approach = getattr(dt, 'selected_intent', None)
        approach_name = approach.intent_type if approach else 'unknown'
        outcome = 1.0 - min(abs(getattr(dt, 'mission_drift', 1.0)), 1.0)
        di_score = getattr(dt, 'decision_integrity', 1.0)

        if outcome > 0.6:
            self.recorder.success(domain, approach_name, outcome, tags=[domain, "pipeline"])
        elif failure is not None:
            params = {}
            if hasattr(failure, 'blocked_by') and failure.blocked_by:
                params["blocking_validator"] = failure.blocked_by
            self.recorder.failure(domain, approach_name, failure.root_cause or "unknown", tags=[domain, failure.failure_type], params=params)

        if self.policy is not None:
            self.policy.record_outcome(domain, approach_name, di_score)

        if self.system_self is not None:
            self.system_self.observe(
                di=di_score,
                md=getattr(dt, 'mission_drift', 0.0),
                was_blocked=result.council_blocked or result.firewall_blocked,
            )
            risk_adj = self.system_self.get_risk_adjustment()
            if risk_adj != 0.0:
                self.policy.adjust_risk_tolerance(risk_adj)
            expl_adj = self.system_self.get_exploration_adjustment()
            if expl_adj != 0.0:
                self.policy.adjust_exploration_budget(expl_adj)

        percept = getattr(result, 'decision_trace', None)
        quality = getattr(percept, 'perception_quality', None) if percept else None
        gate = getattr(percept, 'gate_verdict', None) if percept else None
        if quality is not None and gate is not None:
            was_proxy = gate.get('proxy_activated', False)
            di = percept.decision_integrity if percept else 0.0
            council_ok = percept.council_validated if percept else True
            outcome_good = di > 0.7 and council_ok

            if was_proxy and outcome_good:
                self.knowledge.record(
                    domain, 'quality_threshold', 0.0,
                    failure_reason=f'proxy_overridden: quality={quality.get("quality_score", 0):.2f}, di={di:.2f}',
                    tags=['quality_adjustment', 'lower_threshold'],
                    params={'suggested_adjustment': -0.05},
                )
            elif not was_proxy and not outcome_good and failure is not None:
                self.knowledge.record(
                    domain, 'quality_threshold', 0.0,
                    failure_reason=f'direct_failed_not_proxied: quality={quality.get("quality_score", 0):.2f}, di={di:.2f}',
                    tags=['quality_adjustment', 'raise_threshold'],
                    params={'suggested_adjustment': 0.05},
                )

        self.knowledge.tick()
        return failure

    @property
    def stats(self) -> Dict:
        return {
            "knowledge_nodes": len(self.knowledge._nodes) if hasattr(self.knowledge, '_nodes') else 0,
            "last_consultations": len(self._last_consultation),
        }
