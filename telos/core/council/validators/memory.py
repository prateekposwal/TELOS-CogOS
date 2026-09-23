"""
Concrete Council Validators — Truth-Anchored Advisors

Each validator is a specialized cognitive process that performs one
kind of truth-check. They are NOT agents — they have no goals, no
autonomy, and no ability to act. They only output ValidationSignals.

If any validator returns passed=False, the Council blocks the
Decision Integrator from acting. This is how TELOS ensures
Epistemic Integrity: the system refuses to pursue a mission
when reality contradicts it.
"""

from __future__ import annotations

import os
import numpy as np
import logging
from enum import Enum
from collections import Counter
from typing import Optional, Any, List, TYPE_CHECKING

from telos.core.council.base import Validator, ValidationSignal

if TYPE_CHECKING:
    from telos.core.infra_manager.failure_ledger import FailureLedger
from telos.world.world import World
from telos.world.facts import DomainFacts
from telos.intent_ir import IntentIR
from telos.core.ledger.skill_library import SkillLibrary

from typing import Callable, List as ListType

# GOVERNANCE_SUPPRESSION_REASONS is retained as the canonical re-export every
# consumer (and test_recovery_types.py) imports; the approach-failure filter
# below uses the superset NOT_EVIDENCE_APPROACH_FAILURE_REASONS.
from telos.core.governance.recovery_types import (  # noqa: F401
    GOVERNANCE_SUPPRESSION_REASONS,
    NOT_EVIDENCE_APPROACH_FAILURE_REASONS,
)

# Stale validation is not current falsification (Λ6.5): a KnowledgeGraph
# approach-failure older than this many cycles no longer vetoes. A node with no
# cycle stamp keeps the legacy behavior (veto) so nothing silently weakens
# until it is re-recorded with a stamp. Env-overridable.
KG_VETO_STALE_CYCLES = int(os.environ.get("TELOS_KG_VETO_STALE_CYCLES", "1000"))

# Type alias for constraint check functions
CheckFn = Callable[[Any, Any, Any], tuple]

logger = logging.getLogger('telos_council_validators')

# ═══════════════════════════════════════════════════════════════════════════
# Bitcoin-inspired Limited Constraint Language for Validators
# ═══════════════════════════════════════════════════════════════════════════
#
# Instead of arbitrary Python code, validators can be defined as a list of
# composable constraint opcodes. Each opcode performs a single check.
#
# Opcodes:
#   CHECK_NAN      - Check for NaN/Inf values in state
#   CHECK_BOUNDS   - Check state/action bounds
#   CHECK_SAFETY   - Check safety thresholds
#   CHECK_DRIFT    - Check mission drift
#   CHECK_HISTORY  - Check historical precedents
#   CHECK_MISSION  - Check mission alignment
# ═══════════════════════════════════════════════════════════════════════════

class MemoryAdvisor(Validator):
    """Checks that the planned action does not contradict historical fact.

    Queries the SkillLibrary for prior outcomes of similar situations,
    the FailureLedger for past structural failures (Kintsugi),
    and the KnowledgeGraph for proven/failed approaches.
    """

    def __init__(self, skill_library: SkillLibrary,
                 failure_ledger: Optional['FailureLedger'] = None,
                 knowledge_graph: Optional[Any] = None):
        self.skill_library = skill_library
        self.failure_ledger = failure_ledger
        self.knowledge_graph = knowledge_graph

    def connect(self, failure_ledger=None, knowledge_graph=None):
        self.failure_ledger = failure_ledger or self.failure_ledger
        self.knowledge_graph = knowledge_graph or self.knowledge_graph
        return self

    @property
    def name(self) -> str:
        return "MemoryAdvisor"

    def validate(self, world: World, intent: Optional[IntentIR],
                 domain_facts: Optional[Any] = None,
                 omega_vector: Optional[dict] = None,
                 context: Optional[Dict[str, Any]] = None) -> ValidationSignal:
        # If omega_vector has high Ω_O (other-uncertainty), lower evidence threshold
        # to be more tolerant during uncertainty investigation
        evidence_tolerance = 1.0
        if omega_vector and omega_vector.get('other', 0) > 0.3:
            evidence_tolerance = 1.0 - 0.3 * omega_vector.get('other', 0.5)
        if intent is None:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.0,
                reason="no intent to validate", evidence_weight=0.0,
            )

        relevant = self.skill_library.find_relevant_skills(world.state, threshold=0.3)

        # ── Kintsugi check: query FailureLedger for matching root causes ──
        kintsugi_signals = []
        action_str = None
        if intent is not None and intent.params:
            action_str = str(intent.params.get("action_vector", ""))
        # Pre-compute entity ID set from world metadata semantic_depths (Kintsugi fix a)
        semantic_entity_ids = set()
        for depth in world.metadata.get("semantic_depths", []):
            eid = getattr(depth, 'entity_id', None)
            if eid:
                semantic_entity_ids.add(str(eid))

        if self.failure_ledger is not None:
            recent = self.failure_ledger.get_recent_failures(n=20)
            for i, f in enumerate(recent):
                if f.root_cause in NOT_EVIDENCE_APPROACH_FAILURE_REASONS:
                    continue
                blocked_tokens = set(
                    token.strip().lower()
                    for token in f.blocked_by.replace(",", " ").split()
                ) if f.blocked_by else set()
                if intent.intent_type in blocked_tokens:
                    recency = (i + 1) / max(len(recent), 1)
                    kintsugi_signals.append((f, recency))
                if f.affected_entities and semantic_entity_ids:
                    ae_ids = set()
                    for ae in f.affected_entities:
                        if isinstance(ae, str):
                            ae_ids.add(ae)
                        elif isinstance(ae, dict):
                            ae_id = ae.get("entity_id")
                            if ae_id:
                                ae_ids.add(str(ae_id))
                    if ae_ids & semantic_entity_ids:
                        recency = (i + 1) / max(len(recent), 1)
                        kintsugi_signals.append((f, recency))
                # Check pattern_exploit failures against current move
                if f.failure_type == "pattern_exploit" and action_str is not None:
                    blocked_move = f.blocked_by or ""
                    if blocked_move.lower() in action_str.lower():
                        recency = (i + 1) / max(len(recent), 1)
                        kintsugi_signals.append((f, recency))

        if kintsugi_signals:
            # ── Kintsugi fix b: Trend clustering ──
            root_cause_counter = Counter(f.root_cause for f, _ in kintsugi_signals)
            most_common_rc = root_cause_counter.most_common(1)
            kintsugi_trend = most_common_rc[0][0] if most_common_rc else "none"
            kintsugi_cluster_size = most_common_rc[0][1] if most_common_rc else 0

            worst_failure, recency = max(kintsugi_signals, key=lambda x: x[0].severity)
            confidence = -0.2 - 0.8 * recency
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=confidence,
                reason=f"Kintsugi: past failure #{worst_failure.failure_id[:8]} "
                       f"(type={worst_failure.failure_type}, severity={worst_failure.severity:.2f}) "
                       f"matches current context — structural barrier prevents action",
                evidence_weight=min(0.9, (worst_failure.severity + 0.2) * evidence_tolerance),
                metadata={
                    "kintsugi_match_count": len(kintsugi_signals),
                    "kintsugi_trend": kintsugi_trend,
                    "kintsugi_cluster_size": kintsugi_cluster_size,
                    "worst_failure_id": worst_failure.failure_id,
                    "worst_failure_type": worst_failure.failure_type,
                    "recency": round(recency, 3),
                    "kintsugi_confidence": round(confidence, 3),
                    # ── Kintsugi fix c: Repair history ──
                    "worst_failure_repair": worst_failure.repair_outcome,
                    "repair_was_effective": worst_failure.repair_effective,
                },
            )

        # ── Knowledge Graph check: does a proven solution exist? ──
        if self.knowledge_graph is not None:
            domain = getattr(world, 'domain', 'unknown')
            proven = self.knowledge_graph.search(domain, top_k=3, min_outcome=0.51)
            failed = self.knowledge_graph.search_failures(domain, top_k=3)
            _now_cycle = (context or {}).get("cycle_count") if isinstance(context, dict) else None
            if intent is not None and intent.params:
                current_approach = intent.intent_type or "unknown"
                for fnode in failed:
                    if fnode.approach == current_approach:
                        if (fnode.failure_reason or "") in NOT_EVIDENCE_APPROACH_FAILURE_REASONS:
                            # Suppression / resource-exhaustion is not approach
                            # failure (mirrors the failure-ledger filter above):
                            # a vetoed or starved attempt was never tested, so it
                            # cannot falsify the approach.
                            continue
                        # Recency (Λ6.5): a stale approach-failure is not current
                        # falsification. Only enforced when both the node's cycle
                        # and the current cycle are known; an unstamped node
                        # keeps legacy behavior (veto).
                        _node_cycle = None
                        try:
                            _node_cycle = (fnode.params or {}).get("cycle")
                            if _node_cycle is None:
                                _node_cycle = (fnode.provenance or {}).get("cycle")
                        except Exception:
                            _node_cycle = None
                        if (_now_cycle is not None and _node_cycle is not None
                                and (int(_now_cycle) - int(_node_cycle)) > KG_VETO_STALE_CYCLES):
                            continue
                        return ValidationSignal(
                            validator_name=self.name,
                            passed=False,
                            confidence=-0.6,
                            reason=f"KnowledgeGraph: approach '{current_approach}' failed "
                                   f"previously in domain '{domain}' (outcome={fnode.outcome:.2f}) "
                                   f"— {fnode.failure_reason or 'no reason recorded'}",
                            evidence_weight=0.7,
                            metadata={
                                "failed_node": fnode.node_id,
                                "failed_domain": domain,
                                "failed_outcome": fnode.outcome,
                                "failed_reason": fnode.failure_reason,
                                "proven_alternatives": [n.approach for n in proven],
                            },
                        )
            if proven and intent is not None:
                best = proven[0]
                self.knowledge_graph.activate(best.node_id)
                if best.outcome > 0.85:
                    return ValidationSignal(
                        validator_name=self.name,
                        passed=True,
                        confidence=0.8,
                        reason=f"KnowledgeGraph: proven solution '{best.approach}' "
                               f"scored {best.outcome:.2f} in domain '{domain}'",
                        evidence_weight=0.3,
                        metadata={"proven_approach": best.approach, "proven_outcome": best.outcome},
                    )

        if not relevant:
            return ValidationSignal(
                validator_name=self.name, passed=True, confidence=0.5,
                reason="no contradictory historical evidence",
                evidence_weight=0.1 * evidence_tolerance,
            )

        worst = min(relevant, key=lambda s: s.utility_score)
        if worst.utility_score < 0.3:
            evidence_weight = min(0.8, (0.3 + 0.2 * (1.0 - worst.utility_score)) * evidence_tolerance)
            return ValidationSignal(
                validator_name=self.name,
                passed=False,
                confidence=-0.7,
                reason=f"historical skill {worst.skill_id} had utility {worst.utility_score:.2f} "
                       f"— similar situation previously failed",
                evidence_weight=evidence_weight,
                metadata={
                    "worst_skill_id": worst.skill_id,
                    "worst_utility": worst.utility_score,
                    "match_count": len(relevant),
                },
            )

        return ValidationSignal(
            validator_name=self.name, passed=True, confidence=0.6,
            reason=f"historical precedents are positive (best utility={worst.utility_score:.2f})",
            evidence_weight=0.1,
        )
