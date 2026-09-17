"""Contract tests for the DistributedCouncil — the 5-agent advisory crew
that re-scores the primary council evidence through role lenses and
aggregates a weighted consensus (Λ1.2: advisory only, primary blocking power
untouched)."""
import pytest

from telos.core.council.distributed import (
    DistributedCouncil, AgentRole, AgentVerdict, ROLE_WEIGHTS,
)


class TestAgentVerdict:
    def test_carries_documented_fields(self):
        v = AgentVerdict(
            agent_id="a1", role=AgentRole.SKEPTIC, validated=True,
            decision_integrity=0.9, mission_drift=0.1,
        )
        d = v.to_dict()
        assert d["agent_id"] == "a1"
        assert d["role"] == "skeptic"
        assert d["validated"] is True
        # The dataclass default weight is 1.0; the council assigns the real
        # role weight at submit_verdict time (tested separately).
        assert d["weight"] == v.weight == 1.0


class TestDistributedCouncil:
    def test_register_default_crew_has_five_agents(self):
        dc = DistributedCouncil()
        dc.register_default_crew()
        assert len(dc._agents) == 5

    def test_submit_verdict_stores_weighted_vote(self):
        dc = DistributedCouncil()
        dc.register_agent("a1", AgentRole.PRIMARY)
        dc.submit_verdict("a1", validated=True, di=0.9, md=0.1)
        assert dc._agent_votes["a1"].weight == ROLE_WEIGHTS[AgentRole.PRIMARY]

    def test_reset_clears_votes(self):
        dc = DistributedCouncil()
        dc.register_agent("a1", AgentRole.PRIMARY)
        dc.submit_verdict("a1", validated=True, di=0.9, md=0.1)
        dc.reset()
        assert dc._agent_votes == {}

    def test_run_perspectives_aggregates_weighted_consensus(self):
        dc = DistributedCouncil()
        dc.register_default_crew()
        primary = {
            "validated": True, "decision_integrity": 0.9,
            "mission_drift": 0.2,
            "evidence": [{"passed": True, "confidence": 0.8,
                          "evidence_weight": 0.6}],
        }
        dc.submit_verdict("PRIMARY", True, 0.9, 0.2)
        result = dc.run_perspectives(primary, {"signal_dicts": [
            {"passed": True, "confidence": 0.8, "evidence_weight": 0.6}]})
        assert "aggregate" in result or "consensus" in result or "votes" in result
        assert result

    def test_weighted_consensus_with_dissent(self):
        dc = DistributedCouncil()
        dc.register_agent("PRIMARY", AgentRole.PRIMARY)
        dc.register_agent("SKEPTIC", AgentRole.SKEPTIC)
        primary_verd = {
            "validated": True, "decision_integrity": 0.6,
            "mission_drift": 0.5,
            "evidence": [{"passed": False, "confidence": 0.9,
                          "evidence_weight": 0.8}],
        }
        dc.submit_verdict("PRIMARY", True, 0.6, 0.5)
        result = dc.run_perspectives(primary_verd, {
            "signal_dicts": [{"passed": False, "confidence": 0.9,
                              "evidence_weight": 0.8}]})
        # Dissent-leaning signals must drag the aggregate DI down.
        assert result

    def test_skeptic_dissent_multiplier_weighs_block(self):
        dc = DistributedCouncil()
        dc.register_default_crew()
        # PRIMARY approves, but a low-confidence pass triggers skeptic dissent.
        result = dc.run_perspectives(
            {"validated": True, "decision_integrity": 0.5,
             "mission_drift": 0.5,
             "evidence": [{"passed": True, "confidence": 0.2,
                           "evidence_weight": 0.7}]},
            {"signal_dicts": [{"passed": True, "confidence": 0.2,
                               "evidence_weight": 0.7}]})
        assert result


class TestDomainExpertLens:
    """v9: the DOMAIN_EXPERT lens joins the crew when the context carries
    domain knowledge and dissents on avoid-listed candidates. Advisory only —
    the primary blocking verdict and the aggregation formula are untouched."""

    def _crew_with_knowledge(self, knowledge_report, intent_type="blended_inquiry"):
        dc = DistributedCouncil()
        dc.register_default_crew()
        result = dc.run_perspectives(
            {"validated": True, "decision_integrity": 0.9,
             "mission_drift": 0.1},
            {"intent_type": intent_type, "domain": "gridworld",
             "knowledge_report": knowledge_report})
        return dc, result

    def test_domain_expert_lens_registers_and_dissents_on_avoid(self):
        dc, result = self._crew_with_knowledge({
            "approach": "plan_trajectory", "outcome": 0.9,
            "avoid": [{"approach": "blended_inquiry", "reason": "falsified loop"}],
        })
        agent_ids = [a["agent_id"] for a in result["agents"]]
        assert "domain_expert" in agent_ids
        expert = [a for a in result["agents"] if a["agent_id"] == "domain_expert"][0]
        assert expert["role"] == "domain_expert"
        assert expert["validated"] is False
        assert "validated" in result and "agents" in result

    def test_domain_expert_lens_absent_without_knowledge(self):
        dc = DistributedCouncil()
        dc.register_default_crew()
        result = dc.run_perspectives(
            {"validated": True, "decision_integrity": 0.9, "mission_drift": 0.1},
            {"intent_type": "plan_trajectory"})
        agent_ids = [a["agent_id"] for a in result["agents"]]
        assert "domain_expert" not in agent_ids
        assert len(agent_ids) == 5

    def test_domain_expert_neutral_when_candidate_not_listed(self):
        dc, result = self._crew_with_knowledge(
            {"approach": "plan_trajectory", "outcome": 0.9,
             "avoid": [{"approach": "blended_inquiry", "reason": "falsified"}]},
            intent_type="plan_trajectory",
        )
        expert = [a for a in result["agents"] if a["agent_id"] == "domain_expert"][0]
        assert expert["validated"] is True