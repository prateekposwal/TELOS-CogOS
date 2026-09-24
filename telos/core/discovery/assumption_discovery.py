"""
Assumption Discovery — endogenous candidate assumptions from experience.

TELOS is domain-agnostic in architecture but (until now) assumption-dependent:
a human declares the premises. This module generates CANDIDATE assumptions from
raw experience alone — (state, action, next_state, reward, terminal) transitions
— with NO domain-specific rules.

It REUSES existing components rather than reimplementing them:
  * `telos.world.evidence.EvidenceInfo`     — provenance + validation status
  * `telos.world.epistemic.RealityGapTracker` — the predicted-vs-observed gap
  * `telos.core.knowledge.graph.KnowledgeGraph` — durable record of discoveries
  (TheoryBuilder / CounterfactualEngine are wired by the caller/runner.)

Hard rule: DECLARED assumptions are never silently promoted to ground truth, and
discovered assumptions are never re-labelled as declared. Provenance is explicit.

Critical capability: every candidate carries a FALSIFIABLE TEST — the concrete
observation that would prove it wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from telos.world.evidence import EvidenceInfo, EvidenceSource, ValidationStatus
from telos.world.epistemic import RealityGapTracker

# A raw experience: (state, action, next_state, reward, terminal).
Transition = Tuple[np.ndarray, np.ndarray, np.ndarray, float, bool]


@dataclass
class DiscoveredAssumption:
    """A candidate assumption, discovered or declared.

    Args:
        statement: human-readable claim.
        variables: the variables it relates.
        predicted_relationship: the directional relationship.
        confidence: belief in [0,1] (from evidence consistency).
        uncertainty: 1 - confidence (or effect variance), in [0,1].
        decision_relevance: |corr(variable, reward)| in [0,1].
        falsifiability: how cleanly a single test can refute it, in [0,1].
        provenance: "discovered" or "declared" (never silently merged).
        dependencies: assumptions this one rests on.
        test: the experiment that could falsify it.
        supporting_evidence / contradicting_evidence: evidence refs.
        evidence: the provenance/validation envelope.
        action_dim / state_dim / sign: the internal effect signature (for testing).
    """
    statement: str
    variables: List[str]
    predicted_relationship: str
    confidence: float = 0.5
    uncertainty: float = 0.5
    decision_relevance: float = 0.0
    falsifiability: float = 1.0
    provenance: str = "discovered"
    dependencies: List[str] = field(default_factory=list)
    test: str = ""
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    evidence: EvidenceInfo = field(default_factory=lambda: EvidenceInfo(
        source=EvidenceSource.DERIVED_INFERENCE,
        validation_status=ValidationStatus.ASSUMED))
    action_dim: int = -1
    state_dim: int = -1
    sign: int = 0

    def info_value(self, test_cost: float = 1.0) -> float:
        """Expected value of testing this assumption.

        value = decision_relevance × uncertainty × falsifiability ÷ test_cost

        Args:
            test_cost: relative cost of the experiment (>= a small epsilon).

        Returns:
            The information value (higher = test first).
        """
        return (self.decision_relevance * self.uncertainty * self.falsifiability
                / max(test_cost, 1e-6))

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict.

        Returns:
            The assumption as a JSON-serializable dict.
        """
        return {
            "statement": self.statement,
            "variables": self.variables,
            "predicted_relationship": self.predicted_relationship,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "confidence": round(self.confidence, 4),
            "uncertainty": round(self.uncertainty, 4),
            "decision_relevance": round(self.decision_relevance, 4),
            "falsifiability": round(self.falsifiability, 4),
            "provenance": self.provenance,
            "dependencies": self.dependencies,
            "test": self.test,
            "status": self.evidence.validation_status.value,
        }


class AssumptionDiscoverer:
    """Generates candidate assumptions from experience; tests them; updates.

    Args:
        declared: optional human-declared assumption texts (kept distinct).
        effect_threshold: minimum |slope| to propose a control relation.
        consistency_threshold: minimum |corr| to propose a relation.
    """

    def __init__(self, declared: Optional[Sequence[str]] = None,
                 effect_threshold: float = 0.15,
                 consistency_threshold: float = 0.5):
        self.effect_threshold = effect_threshold
        self.consistency_threshold = consistency_threshold
        self.discovered: List[DiscoveredAssumption] = []
        self._declared: List[DiscoveredAssumption] = [
            DiscoveredAssumption(
                statement=t, variables=[], predicted_relationship="(declared)",
                confidence=1.0, uncertainty=0.0, provenance="declared",
                evidence=EvidenceInfo(source=EvidenceSource.HUMAN_EXPERT,
                                      validation_status=ValidationStatus.ASSUMED),
                test="(declared — not discovered; never auto-promoted)")
            for t in (declared or [])]
        self.reality_gap = RealityGapTracker()

    # ── Discovery ────────────────────────────────────────────────────────────

    def discover(self, transitions: Sequence[Transition]) -> List[DiscoveredAssumption]:
        """Generate candidate assumptions from transitions (control structure).

        Domain-agnostic: it estimates, for every (action dim, state dim) pair, a
        linear effect and only proposes a relation when the effect is strong and
        consistent. No knowledge of what the dims mean.

        Args:
            transitions: raw experience.

        Returns:
            The discovered candidate assumptions (replaces prior discoveries).
        """
        if not transitions:
            return []
        S = np.array([t[0] for t in transitions], dtype=float)
        A = np.array([t[1] for t in transitions], dtype=float)
        Sn = np.array([t[2] for t in transitions], dtype=float)
        R = np.array([t[3] for t in transitions], dtype=float)
        D = Sn - S
        n_state, n_act = S.shape[1], A.shape[1]

        # reward-relevance of each state dim (decision relevance proxy).
        relevance = np.zeros(n_state)
        for i in range(n_state):
            if np.std(S[:, i]) > 1e-9 and np.std(R) > 1e-9:
                relevance[i] = abs(float(np.corrcoef(S[:, i], R)[0, 1]))

        found: List[DiscoveredAssumption] = []
        for j in range(n_act):
            for i in range(n_state):
                x = A[:, j]
                y = D[:, i]
                if np.std(x) < 1e-9 or np.std(y) < 1e-9:
                    continue
                slope = float(np.cov(x, y)[0, 1] / (np.var(x) + 1e-12))
                corr = float(np.corrcoef(x, y)[0, 1]) if np.std(y) > 1e-9 else 0.0
                if abs(slope) < self.effect_threshold or abs(corr) < self.consistency_threshold:
                    continue
                sign = 1 if slope > 0 else -1
                conf = min(1.0, abs(corr))
                found.append(DiscoveredAssumption(
                    statement=f"action dim a{j} {'' if sign > 0 else 'decreases'} "
                              f"state dim s{i} ({'increases' if sign > 0 else 'decreases'})",
                    variables=[f"a{j}", f"s{i}"],
                    predicted_relationship=f"a{j} {'+' if sign > 0 else '-'}→ s{i} "
                                           f"(slope≈{slope:.2f})",
                    confidence=conf, uncertainty=1.0 - conf,
                    decision_relevance=float(relevance[i]),
                    falsifiability=1.0,
                    provenance="discovered",
                    dependencies=[],
                    test=(f"from a neutral state, apply a{j}=+1 (others 0); "
                          f"expect s{i} to move {'+' if sign > 0 else '−'}; "
                          f"if it does not, the assumption is false."),
                    evidence=EvidenceInfo(source=EvidenceSource.SIMULATION,
                                          validation_status=ValidationStatus.OBSERVED,
                                          confidence=conf),
                    action_dim=j, state_dim=i, sign=sign,
                ))
        self.discovered = found
        return found

    # ── Experiment selection + execution ─────────────────────────────────────

    def select_test(self, test_costs: Optional[Dict[str, float]] = None
                    ) -> Optional[DiscoveredAssumption]:
        """Pick the highest-value unverified assumption to test.

        Args:
            test_costs: optional {statement: cost}.

        Returns:
            The selected assumption, or None when all are validated/falsified.
        """
        costs = test_costs or {}
        candidates = [a for a in self.discovered
                      if a.evidence.validation_status
                      not in (ValidationStatus.VALIDATED, ValidationStatus.FALSIFIED)]
        if not candidates:
            return None
        return max(candidates, key=lambda a: a.info_value(costs.get(a.statement, 1.0)))

    def run_test(self, assumption: DiscoveredAssumption,
                 step_fn: Callable[[np.ndarray, np.ndarray], Tuple[np.ndarray, float, bool]],
                 state: np.ndarray) -> Dict[str, Any]:
        """Execute the assumption's falsification test and update belief.

        Builds the intervention (a[action_dim]=+1), predicts the effect from the
        assumption, steps the environment, and compares predicted vs observed via
        the RealityGapTracker. Supporting evidence raises confidence (→ VALIDATED
        at a threshold); a contradiction FALSIFIES the assumption.

        Args:
            assumption: the assumption to test.
            step_fn: environment step (state, action) -> (next_state, reward, done).
            state: the state to act from.

        Returns:
            The outcome dict (predicted, observed, supported, gap).
        """
        action = np.zeros_like(state)
        action[assumption.action_dim] = 1.0
        predicted = np.array(state, dtype=float)
        predicted[assumption.state_dim] += assumption.sign * 1.0
        observed, _reward, _done = step_fn(np.array(state, dtype=float), action)

        delta = float(observed[assumption.state_dim] - state[assumption.state_dim])
        supported = (delta * assumption.sign) > 0
        gap = float(np.linalg.norm(predicted - observed))
        self.reality_gap.record("discovery", predicted, observed)

        if supported:
            assumption.supporting_evidence.append(f"test@cycle(gap={gap:.2f})")
            assumption.confidence = min(1.0, assumption.confidence + 0.25)
            assumption.uncertainty = 1.0 - assumption.confidence
            # Supportive test => MEASURED. Reaching VALIDATED is evidence-gated
            # (>= min_support observations) via promote() — never auto-granted.
            assumption.evidence.validation_status = ValidationStatus.MEASURED
        else:
            assumption.contradicting_evidence.append(f"test@cycle(gap={gap:.2f})")
            assumption.confidence = max(0.0, assumption.confidence - 0.5)
            assumption.uncertainty = 1.0 - assumption.confidence
            assumption.evidence.validation_status = ValidationStatus.FALSIFIED

        return {"assumption": assumption.statement, "predicted": predicted.tolist(),
                "observed": observed.tolist(), "supported": supported, "gap": gap,
                "status": assumption.evidence.validation_status.value}

    # ── Model + promotion ────────────────────────────────────────────────────

    def control_matrix(self) -> np.ndarray:
        """The discovered control map: M[i,j] = predicted effect of a_j on s_i.

        Returns:
            A (state_dim, action_dim) matrix from validated/measured assumptions.
        """
        dims_s, dims_a = 0, 0
        for a in self.discovered:
            dims_s = max(dims_s, a.state_dim + 1)
            dims_a = max(dims_a, a.action_dim + 1)
        M = np.zeros((dims_s, dims_a))
        for a in self.discovered:
            if a.evidence.validation_status in (ValidationStatus.VALIDATED,
                                                ValidationStatus.MEASURED,
                                                ValidationStatus.OBSERVED):
                M[a.state_dim, a.action_dim] = a.sign
        return M

    def declared_assumptions(self) -> List[DiscoveredAssumption]:
        """The human-declared assumptions (never auto-promoted)."""
        return list(self._declared)

    def discovered_assumptions(self) -> List[DiscoveredAssumption]:
        """The discovered assumptions."""
        return list(self.discovered)

    def promote(self, min_support: int = 2) -> List[DiscoveredAssumption]:
        """Promote DISCOVERED assumptions to VALIDATED only with evidence.

        Never touches declared assumptions; never promotes declared→discovered or
        vice versa. Promotion requires >= min_support supporting observations.

        Args:
            min_support: minimum supporting evidence count.

        Returns:
            The newly promoted assumptions.
        """
        promoted = []
        for a in self.discovered:
            if (len(a.supporting_evidence) >= min_support
                    and a.evidence.validation_status != ValidationStatus.VALIDATED):
                a.evidence.validation_status = ValidationStatus.VALIDATED
                promoted.append(a)
        return promoted
