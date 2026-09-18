"""Real multi-agent coordination: delegation, independent verification, bounded
deterministic conflict resolution — plus the measured-artifact score linkage.

These tests lock the load-bearing behaviors (a second agent can REJECT a first
with a recorded reason; disagreements resolve deterministically; collaboration
is bounded) and the writer/reader schema link that the scorecard depends on.
"""

import json

from telos.core.coordination.delegation import (
    CoordinationProtocol, HARD_VETO_ROLES,
)
from telos.core.verifier.capability_scorecard import (
    MULTI_AGENT_CRITERIA, _score_multi_agent,
)
from telos.tools.multi_agent_eval import evaluate as evaluate_multi_agent


def _protocol(max_rounds=3, max_handoffs=4):
    """Build a registered four-agent protocol.

    Args:
        max_rounds: the round ceiling.
        max_handoffs: the accepted-handoff ceiling.

    Returns:
        A configured CoordinationProtocol.
    """
    p = CoordinationProtocol(max_rounds=max_rounds, max_handoffs=max_handoffs)
    p.register_agent("primary", "primary", 1.0)
    p.register_agent("skeptic", "skeptic", 0.8)
    p.register_agent("analyst", "analyst", 0.5)
    return p


class TestDelegation:
    def test_accepted_handoff_is_recorded_with_parties_and_response(self):
        p = _protocol()
        h = p.delegate("audit risk", "primary", "skeptic",
                       response={"risk": "high"})
        assert h.accepted is True
        assert h.from_agent == "primary" and h.to_agent == "skeptic"
        assert h.response == {"risk": "high"}
        assert h.handoff_id.startswith("handoff-")

    def test_self_delegation_is_refused_with_reason(self):
        p = _protocol()
        h = p.delegate("loop", "primary", "primary")
        assert h.accepted is False
        assert "self-delegation" in h.reason

    def test_unknown_recipient_is_refused_with_reason(self):
        p = _protocol()
        h = p.delegate("x", "primary", "ghost")
        assert h.accepted is False
        assert "unknown recipient" in h.reason

    def test_handoff_budget_is_enforced(self):
        p = _protocol(max_handoffs=2)
        assert p.delegate("a", "primary", "skeptic").accepted is True
        assert p.delegate("b", "primary", "analyst").accepted is True
        over = p.delegate("c", "primary", "analyst")
        assert over.accepted is False
        assert over.reason == "handoff_budget_exhausted"
        assert p.audit()["bounded"] is True


class TestVerification:
    def test_invalid_proposal_is_rejected_with_reason(self):
        p = _protocol()
        v = p.verify({
            "proposal_id": "p1", "author": "primary",
            "evidence": ["sig"], "violates": ["reality_contradiction"],
            "confidence": 0.9,
        }, "skeptic")
        assert v.accepted is False
        assert v.reason and "violates" in v.reason

    def test_missing_evidence_is_rejected_with_reason(self):
        p = _protocol()
        v = p.verify({"proposal_id": "p2", "author": "primary",
                      "evidence": [], "confidence": 0.9}, "skeptic")
        assert v.accepted is False
        assert v.reason == "no supporting evidence provided"

    def test_low_confidence_is_rejected_with_reason(self):
        p = _protocol()
        v = p.verify({"proposal_id": "p3", "author": "primary",
                      "evidence": ["sig"], "confidence": 0.1}, "skeptic")
        assert v.accepted is False
        assert "below" in v.reason

    def test_valid_proposal_is_accepted(self):
        p = _protocol()
        v = p.verify({"proposal_id": "p4", "author": "primary",
                      "evidence": ["sig"], "violates": [],
                      "confidence": 0.9}, "skeptic")
        assert v.accepted is True
        assert v.reason

    def test_verifier_cannot_audit_its_own_proposal(self):
        p = _protocol()
        v = p.verify({"proposal_id": "p5", "author": "skeptic",
                      "evidence": ["sig"], "confidence": 0.9}, "skeptic")
        assert v.accepted is False
        assert "independence" in v.reason


class TestConflictResolution:
    def _positions(self):
        return [
            {"agent_id": "primary", "role": "primary", "validated": True, "weight": 1.0},
            {"agent_id": "skeptic", "role": "skeptic", "validated": False, "weight": 0.8},
            {"agent_id": "analyst", "role": "analyst", "validated": True, "weight": 0.5},
        ]

    def test_conflict_is_detected_and_hard_veto_decides(self):
        p = _protocol()
        r = p.resolve(self._positions())
        assert r.conflict is True
        assert r.method == "hard_veto"
        assert r.validated is False
        assert "skeptic" in r.reason

    def test_weighted_majority_decides_without_a_veto(self):
        p = _protocol()
        r = p.resolve([
            {"agent_id": "analyst", "role": "analyst", "validated": True, "weight": 1.0},
            {"agent_id": "explorer", "role": "explorer", "validated": False, "weight": 0.5},
        ])
        assert r.method == "weighted_majority"
        assert r.validated is True

    def test_exact_tie_breaks_by_authority_then_id(self):
        p = _protocol()
        positions = [
            {"agent_id": "auditor_a", "role": "analyst", "validated": True, "weight": 1.0},
            {"agent_id": "auditor_b", "role": "explorer", "validated": False, "weight": 1.0},
        ]
        r = p.resolve(positions)
        assert r.method == "authority_tiebreak"
        assert r.weight_for == r.weight_against
        # Both weight 1.0 → lexicographically smallest id ("auditor_a") wins.
        assert r.validated is True

    def test_resolution_is_deterministic_across_runs(self):
        first = _protocol().resolve(self._positions()).to_dict()
        second = _protocol().resolve(self._positions()).to_dict()
        assert first == second


class TestBoundsAndAudit:
    def test_round_ceiling_is_enforced(self):
        p = _protocol(max_rounds=2)
        assert p.advance_round() is True
        assert p.advance_round() is True
        assert p.advance_round() is False
        assert p.audit()["rounds_used"] == 2
        assert p.audit()["bounded"] is True

    def test_audit_counts_and_reasons(self):
        p = _protocol()
        p.delegate("a", "primary", "skeptic")
        p.delegate("b", "primary", "primary")
        p.verify({"proposal_id": "p", "author": "primary", "evidence": ["e"],
                  "violates": ["x"], "confidence": 0.9}, "skeptic")
        p.resolve([
            {"agent_id": "primary", "role": "primary", "validated": True, "weight": 1.0},
            {"agent_id": "skeptic", "role": "skeptic", "validated": False, "weight": 0.8},
        ])
        audit = p.audit()
        assert audit["delegations"] == 2
        assert audit["rejections_with_reason"] >= 1
        assert audit["conflicts_resolved"] == 1
        assert audit["bounded"] is True


class TestAuditSchemaLinkage:
    def test_writer_emits_exactly_the_keys_the_reader_reads(self):
        result = evaluate_multi_agent()
        assert set(result["criteria"]) == set(MULTI_AGENT_CRITERIA)

    def test_all_measured_criteria_pass(self):
        result = evaluate_multi_agent()
        assert result["beats_baseline"] is True
        assert all(result["criteria"].values())
        assert result["bounded"] is True
        assert result["rejections_with_reason"] >= 1
        assert result["conflicts_resolved"] >= 1


def _build_scored_repo(root, criteria):
    """Create the minimal repo structure a multi-agent score reads.

    Args:
        root: the temporary repo root (a pathlib.Path).
        criteria: the criteria mapping to write, or None for no artifact.

    Returns:
        The repo root as a string.
    """
    (root / "telos" / "core" / "council").mkdir(parents=True)
    (root / "telos" / "core" / "coordination").mkdir(parents=True)
    (root / "telos" / "audit").mkdir(parents=True)
    (root / "telos" / "core" / "council" / "distributed.py").write_text("")
    (root / "telos" / "core" / "coordination" / "delegation.py").write_text("")
    if criteria is not None:
        (root / "telos" / "audit" / "multi_agent_eval.json").write_text(
            json.dumps({"criteria": criteria}), encoding="utf-8")
    return str(root)


class TestScorecardReadsMeasurement:
    def test_awards_measured_points_when_criteria_pass(self, tmp_path):
        root = _build_scored_repo(tmp_path, {k: True for k in MULTI_AGENT_CRITERIA})
        result = _score_multi_agent(root)
        assert result.score == 4.5
        assert result.target == 4.5
        assert any("measured:" in e for e in result.evidence)

    def test_no_credit_without_the_artifact(self, tmp_path):
        root = _build_scored_repo(tmp_path, None)
        result = _score_multi_agent(root)
        assert result.score == 2.0
        assert any("no measured" in e for e in result.evidence)

    def test_no_measured_credit_when_criteria_fail(self, tmp_path):
        failing = {k: True for k in MULTI_AGENT_CRITERIA}
        failing["rejection_with_reason"] = False
        root = _build_scored_repo(tmp_path, failing)
        result = _score_multi_agent(root)
        expected = 2.0 + 2.5 * (len(MULTI_AGENT_CRITERIA) - 1) / len(
            MULTI_AGENT_CRITERIA)
        assert abs(result.score - expected) < 1e-9
        assert result.score < 4.5
        assert any("criteria pass" in e for e in result.evidence)

    def test_score_never_reaches_five(self, tmp_path):
        root = _build_scored_repo(tmp_path, {k: True for k in MULTI_AGENT_CRITERIA})
        assert _score_multi_agent(root).score < 5.0


class TestCouncilIntegration:
    def test_run_perspectives_returns_recorded_coordination(self):
        from telos.core.council.distributed import DistributedCouncil
        from telos.core.council.base import CouncilVerdict, ValidationSignal
        dc = DistributedCouncil()
        dc.register_default_crew()
        signals = [
            ValidationSignal("Reality", passed=False, confidence=0.8,
                             reason="contradiction", evidence_weight=0.5),
            ValidationSignal("MissionDrift", passed=True, confidence=0.6,
                             reason="ok", evidence_weight=0.4),
        ]
        verdict = CouncilVerdict(validated=False, signals=signals,
                                 decision_integrity=0.2, mission_drift=0.4)
        result = dc.run_perspectives(
            verdict,
            context={"alternatives": ["a", "b"], "curiosity_bonus": 1.5},
        )
        coord = result["coordination"]
        assert coord["handoff"]["from_agent"] == "primary"
        assert coord["handoff"]["to_agent"] == "skeptic"
        # The skeptic must reject the blocked primary, with a recorded reason.
        assert coord["verification"]["accepted"] is False
        assert coord["verification"]["reason"]
        assert coord["resolution"]["method"] == "hard_veto"
        assert coord["resolution"]["validated"] is False
        assert coord["audit"]["bounded"] is True
        assert HARD_VETO_ROLES == ("skeptic",)
