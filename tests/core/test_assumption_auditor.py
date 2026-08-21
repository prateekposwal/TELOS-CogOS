"""Contract tests for telos/core/curiosity/assumption_auditor.py.

AssumptionAuditor registers and audits the system's held assumptions:
question, reinforce on survival, revise on failure, and trigger audits on
curiosity / periodic / staleness signals.
"""
import time

from telos.core.curiosity.assumption_auditor import (
    Assumption,
    AssumptionAuditor,
    AssumptionType,
    AuditReport,
)


class TestAssumption:
    def test_survival_rate_empty_is_one(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.5, last_questioned=0.0)
        assert a.survival_rate == 1.0

    def test_survival_rate_half(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.5, last_questioned=0.0)
        a.times_survived = 1
        a.times_failed = 1
        assert a.survival_rate == 0.5

    def test_question_updates_timestamp(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.5, last_questioned=0.0)
        a.question()
        assert a.times_questioned == 1

    def test_survive_reinforces_confidence_and_records_evidence(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.5, last_questioned=0.0)
        a.survive("saw it work")
        assert a.times_survived == 1
        assert a.confidence == 0.55
        assert a.evidence_for == ["saw it work"]

    def test_survive_caps_confidence_at_one(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.99, last_questioned=0.0)
        a.survive("e")
        assert a.confidence == 1.0

    def test_fail_revises_confidence_and_records_evidence(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.5, last_questioned=0.0)
        a.fail("it broke")
        assert a.times_failed == 1
        assert a.confidence == 0.35
        assert a.evidence_against == ["it broke"]

    def test_fail_floors_confidence_at_zero(self):
        a = Assumption(id="a", description="d", type=AssumptionType.DOMAIN,
                       confidence=0.1, last_questioned=0.0)
        a.fail("x")
        assert a.confidence == 0.0


class TestAssumptionAuditor:
    def test_registers_core_assumptions(self):
        a = AssumptionAuditor()
        ids = {x.id for x in a.active_assumptions}
        assert {"world_stable", "action_effective", "council_reliable",
                "simulation_accurate", "identity_coherent", "curiosity_useful"} <= ids
        assert len(a.active_assumptions) == 6

    def test_register_assumption_deterministic_id(self):
        a = AssumptionAuditor()
        first = a.register_assumption("alpha hypothesis", AssumptionType.STRATEGIC, 0.6)
        second = a.register_assumption("alpha hypothesis", AssumptionType.STRATEGIC, 0.6)
        assert first == second
        assert first.startswith("asm_")
        assert len(a.active_assumptions) == 7

    def test_should_audit_curiosity_trigger(self):
        a = AssumptionAuditor()
        assert a.should_audit(1, 0.2) is False
        assert a.should_audit(1, 0.6) is True

    def test_should_audit_periodic_trigger(self):
        a = AssumptionAuditor()
        assert a.should_audit(10, 0.0) is True

    def test_should_audit_staleness_trigger(self):
        a = AssumptionAuditor()
        a._assumptions["world_stable"].last_questioned = time.time() - 4000
        assert a.should_audit(1, 0.0) is True

    def test_select_assumption_returns_active(self):
        a = AssumptionAuditor()
        selected = a.select_assumption_to_audit(1)
        assert selected is not None
        assert selected.id == "world_stable"

    def test_audit_unknown_id_returns_none(self):
        a = AssumptionAuditor()
        assert a.audit(1, "does_not_exist", "e", True) is None

    def test_audit_survived_updates_confidence_and_report(self):
        a = AssumptionAuditor()
        before = a._assumptions["world_stable"].confidence
        report = a.audit(1, "world_stable", "still holds", survived=True)
        assert isinstance(report, AuditReport)
        assert report.assumption_audited == "world_stable"
        assert report.survived is True
        assert report.confidence_before == before
        assert report.confidence_after == before + 0.05
        assert report.new_confidence == report.confidence_after
        assert report.evidence == "still holds"
        assert report.triggered_by_curiosity is False
        assert a._assumptions["world_stable"].times_questioned == 1
        assert a.total_audits == 1
        assert a._last_audit_cycle == 1

    def test_audit_failed_penalises_confidence(self):
        a = AssumptionAuditor()
        before = a._assumptions["world_stable"].confidence
        report = a.audit(2, "world_stable", "contradicted", survived=False)
        assert report.survived is False
        assert report.confidence_after == before - 0.15
        assert a._assumptions["world_stable"].times_failed == 1

    def test_audit_questioning_is_idempotent_on_state(self):
        a = AssumptionAuditor()
        a.audit(1, "world_stable", "e1", True)
        a.audit(2, "world_stable", "e2", True)
        assert a._assumptions["world_stable"].times_questioned == 2
        assert a.total_audits == 2

    def test_auto_audit_skips_when_not_due(self):
        a = AssumptionAuditor()
        assert a.auto_audit(1, 0.2) is None
        assert a.total_audits == 0

    def test_auto_audit_runs_on_high_curiosity(self):
        a = AssumptionAuditor()
        report = a.auto_audit(1, 0.9)
        assert isinstance(report, AuditReport)
        assert report.survived is True
        assert report.triggered_by_curiosity is True
        assert a.total_audits == 1

    def test_auto_audit_periodic_even_quiet(self):
        a = AssumptionAuditor()
        report = a.auto_audit(10, 0.0)
        assert isinstance(report, AuditReport)
        assert report.triggered_by_curiosity is False

    def test_audit_history_bounded(self):
        a = AssumptionAuditor()
        for i in range(50):
            a.audit(i, "world_stable", f"e{i}", True)
        assert len(a._audit_history) == 50

    def test_to_dict_shape(self):
        a = AssumptionAuditor()
        a.audit(1, "world_stable", "e", True)
        d = a.to_dict()
        assert d["total_audits"] == 1
        assert d["active_assumptions"] == 6
        world_entry = d["assumptions"]["world_stable"]
        assert world_entry["type"] == "domain"
        assert "confidence" in world_entry
        assert "survival_rate" in world_entry
        assert "staleness_seconds" in world_entry
        assert world_entry["active"] is True