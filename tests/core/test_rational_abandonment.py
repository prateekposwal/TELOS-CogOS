"""Contract tests for AbandonmentGate — distinguishing persistence from
obsession across method / project / mission levels."""

from telos.core.project.rational_abandonment import (
    AbandonmentGate, AbandonmentConfig, AbandonmentDecision, AbandonmentVerdict,
    Trend,
)


class TestEnums:
    def test_decision_values(self):
        assert AbandonmentDecision.CONTINUE.value == "continue"
        assert AbandonmentDecision.PAUSE.value == "pause"
        assert AbandonmentDecision.ARCHIVE.value == "archive"
        assert AbandonmentDecision.TERMINATE.value == "terminate"

    def test_trend_values(self):
        assert Trend.RISING.value == "rising"
        assert Trend.DECLINING.value == "declining"
        assert Trend.STABLE.value == "stable"
        assert Trend.INSUFFICIENT_DATA.value == "insufficient_data"


class TestEarlyAndMission:
    def test_too_early_always_continue(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=2, level="method")
        assert verdict.decision == AbandonmentDecision.CONTINUE
        assert verdict.confidence == 1.0
        assert "too early" in verdict.reason

    def test_method_min_cycles_default_five(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=4, level="method")
        assert verdict.decision == AbandonmentDecision.CONTINUE
        # 5 cycles has crossed the method threshold
        gate.evaluate(Trend.RISING, Trend.DECLINING,
                      alternative_value=1.0, project_ev=0.0,
                      time_invested=5, level="method")

    def test_mission_never_terminates(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.STABLE,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=600, level="mission")
        assert verdict.decision == AbandonmentDecision.CONTINUE
        assert verdict.reason == "missions almost never terminate"
        assert verdict.confidence == 0.95


class TestObsessionPattern:
    def test_obsession_on_method_archives(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=20, level="method")
        assert verdict.decision == AbandonmentDecision.ARCHIVE
        assert verdict.reason == ("obsession pattern: commitment rising, "
                                  "evidence declining, alternatives better")
        assert verdict.confidence == 0.7

    def test_obsession_on_project_pauses(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=60, level="project")
        assert verdict.decision == AbandonmentDecision.PAUSE


class TestDecliningEvidence:
    def test_evidence_decline_with_better_alternative_method_archives(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.STABLE, Trend.DECLINING,
                                alternative_value=0.9, project_ev=0.5,
                                time_invested=10, level="method")
        assert verdict.decision == AbandonmentDecision.ARCHIVE
        assert verdict.confidence == 0.6

    def test_evidence_decline_with_better_alternative_project_pauses(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.STABLE, Trend.DECLINING,
                                alternative_value=0.9, project_ev=0.5,
                                time_invested=60, level="project")
        assert verdict.decision == AbandonmentDecision.PAUSE

    def test_alternative_not_better_enough_no_abandonment_signal(self):
        gate = AbandonmentGate()
        # alternative_value must exceed project_ev + gap (0.2)
        verdict = gate.evaluate(Trend.STABLE, Trend.DECLINING,
                                alternative_value=0.6, project_ev=0.5,
                                time_invested=20, level="method")
        assert verdict.decision == AbandonmentDecision.CONTINUE


class TestCommitmentRising:
    def test_commitment_rising_with_declining_evidence_pauses(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=0.0, project_ev=0.5,
                                time_invested=20, level="method")
        assert verdict.decision == AbandonmentDecision.PAUSE
        assert verdict.confidence == 0.5

    def test_nominal_situation_continues(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.STABLE, Trend.STABLE,
                                alternative_value=0.1, project_ev=0.5,
                                time_invested=20, level="method")
        assert verdict.decision == AbandonmentDecision.CONTINUE
        assert verdict.reason == "no abandonment signal"
        assert verdict.confidence == 0.8


class TestConfig:
    def test_custom_min_cycles_respected(self):
        config = AbandonmentConfig(min_cycles_method=20)
        gate = AbandonmentGate(config)
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=10, level="method")
        assert verdict.decision == AbandonmentDecision.CONTINUE

    def test_custom_alternative_gap(self):
        config = AbandonmentConfig(alternative_value_gap=0.5)
        gate = AbandonmentGate(config)
        verdict = gate.evaluate(Trend.STABLE, Trend.DECLINING,
                                alternative_value=0.8, project_ev=0.5,
                                time_invested=20, level="method")
        assert verdict.decision == AbandonmentDecision.CONTINUE

    def test_unknown_level_defaults_to_ten(self):
        gate = AbandonmentGate()
        verdict = gate.evaluate(Trend.RISING, Trend.DECLINING,
                                alternative_value=1.0, project_ev=0.0,
                                time_invested=9, level="bogus")
        assert verdict.decision == AbandonmentDecision.CONTINUE

    def test_verdict_is_dataclass(self):
        verdict = AbandonmentVerdict(decision=AbandonmentDecision.PAUSE,
                                     reason="x", confidence=0.5)
        assert verdict.reason == "x"