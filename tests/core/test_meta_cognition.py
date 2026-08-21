"""
MetaCognitionModule — self-doubt, recovery and epistemic-repair triggers.

Honest contract coverage (telos/core/meta/meta_cognition.py):
  - MetaPolicy.select_mode: WAIT on resource depletion, EXPLORE from
    InquiryStream (inquiry_active + Ω > 0.5), EXPLORE/DELEGATE/PLAN from
    tripartite dominance, REACT under low uncertainty + time pressure,
    mode_history/current_mode tracking.
  - MetaCognitionModule.observe: DI < 0.5 → EPISTEMIC_REPAIR (with dwell until
    2 consecutive good cycles), >3 consecutive council blocks → RECOVERING
    (dwell 2 cycles), inquiry_active → EXPLORING; consecutive-block counter
    resets on an unblocked cycle; state transitions carry a trigger_reason.
  - get_stats / to_dict report state + counters.
"""
from telos.core.meta.meta_cognition import (
    MetaCognitionModule,
    MetaPolicy,
    MetaState,
    MetaCognitionReport,
)

BLOCKED = [{"passed": False}]
PASSED = [{"passed": True}]
LOW_U = {"U_W": 0.1, "U_I": 0.1, "U_O": 0.1}


class TestMetaPolicy:
    def test_default_mode_is_plan(self):
        p = MetaPolicy()
        assert p.current_mode == "PLAN"

    def test_high_environmental_uncertainty_explores(self):
        assert MetaPolicy().select_mode({"U_W": 0.9, "U_I": 0.1, "U_O": 0.1}) == "EXPLORE"

    def test_high_identity_uncertainty_delegates(self):
        assert MetaPolicy().select_mode({"U_W": 0.1, "U_I": 0.9, "U_O": 0.1}) == "DELEGATE"

    def test_high_other_uncertainty_plans(self):
        assert MetaPolicy().select_mode({"U_W": 0.1, "U_I": 0.1, "U_O": 0.9}) == "PLAN"

    def test_low_uncertainty_with_pressure_reacts(self):
        assert MetaPolicy().select_mode(LOW_U, time_pressure=0.9) == "REACT"

    def test_low_uncertainty_without_pressure_plans(self):
        assert MetaPolicy().select_mode(LOW_U) == "PLAN"

    def test_resource_depletion_waits(self):
        p = MetaPolicy()
        assert p.select_mode(None, resource_depletion=0.9) == "WAIT"

    def test_inquiry_omega_overrides_threshold(self):
        p = MetaPolicy()
        assert p.select_mode(LOW_U, inquiry_active=True, inquiry_omega_value=0.9) == "EXPLORE"

    def test_inquiry_omega_below_threshold_ignored(self):
        p = MetaPolicy()
        assert p.select_mode(LOW_U, inquiry_active=True, inquiry_omega_value=0.4) == "PLAN"

    def test_none_tripartite_returns_last_mode(self):
        p = MetaPolicy()
        p.select_mode({"U_W": 0.9, "U_I": 0.1, "U_O": 0.1})
        assert p.select_mode(None) == "EXPLORE"

    def test_mode_history_tracks_modes(self):
        p = MetaPolicy()
        p.select_mode({"U_W": 0.9, "U_I": 0.1, "U_O": 0.1})
        p.select_mode(LOW_U, time_pressure=0.9)
        assert p.mode_history == ["EXPLORE", "REACT"]
        assert p.current_mode == "REACT"

    def test_to_dict(self):
        p = MetaPolicy()
        p.select_mode({"U_W": 0.9, "U_I": 0.1, "U_O": 0.1})
        d = p.to_dict()
        assert set(d) == {"current_mode", "mode_history"}
        assert d["current_mode"] == "EXPLORE"


class TestMetaCognitionModule:
    def test_initial_state_nominal(self):
        m = MetaCognitionModule()
        assert m.state == MetaState.NOMINAL
        assert m.consecutive_blocks == 0
        assert m.state_history == []

    def test_observe_returns_report(self):
        m = MetaCognitionModule()
        report = m.observe({}, PASSED, 1.0, 1, tripartite_u=LOW_U)
        assert isinstance(report, MetaCognitionReport)
        assert report.current_state == MetaState.NOMINAL
        assert report.current_di == 1.0
        assert report.consecutive_council_blocks == 0
        assert report.exploration_mode_active is False
        assert report.recovery_mode_active is False
        assert report.epistemic_repair_active is False

    def test_nominal_cycles_recorded(self):
        m = MetaCognitionModule()
        m.observe({}, PASSED, 1.0, 1, tripartite_u=LOW_U)
        m.observe({}, PASSED, 0.9, 2, tripartite_u=LOW_U)
        assert len(m.state_history) == 2
        assert [s["state"] for s in m.state_history] == ["nominal", "nominal"]
        stats = m.get_stats()
        assert stats["total_observations"] == 2
        assert stats["current_state"] == "nominal"

    def test_di_below_threshold_triggers_epistemic_repair(self):
        m = MetaCognitionModule()
        report = m.observe({}, PASSED, 0.4, 1, tripartite_u=LOW_U)
        assert report.current_state == MetaState.EPISTEMIC_REPAIR
        assert report.epistemic_repair_active is True
        assert "DI dropped to" in report.trigger_reason

    def test_epistemic_repair_dwells_until_two_good_cycles(self):
        m = MetaCognitionModule()
        m.observe({}, PASSED, 0.4, 1, tripartite_u=LOW_U)
        report = m.observe({}, PASSED, 0.9, 2, tripartite_u=LOW_U)
        assert report.current_state == MetaState.EPISTEMIC_REPAIR
        report = m.observe({}, PASSED, 0.95, 3, tripartite_u=LOW_U)
        assert report.current_state == MetaState.NOMINAL

    def test_consecutive_council_blocks_trigger_recovery(self):
        m = MetaCognitionModule()
        for cycle in range(1, 5):
            report = m.observe({}, BLOCKED, 1.0, cycle, tripartite_u=LOW_U)
        assert report.current_state == MetaState.RECOVERING
        assert report.recovery_mode_active is True
        assert "Council blocked 4x" in report.trigger_reason
        assert m.consecutive_blocks == 4

    def test_recovery_dwells_two_cycles_after_block_clears(self):
        m = MetaCognitionModule()
        for cycle in range(1, 5):
            m.observe({}, BLOCKED, 1.0, cycle, tripartite_u=LOW_U)
        report = m.observe({}, PASSED, 1.0, 5, tripartite_u=LOW_U)
        assert report.current_state == MetaState.RECOVERING
        assert report.consecutive_council_blocks == 0
        report = m.observe({}, PASSED, 1.0, 6, tripartite_u=LOW_U)
        assert report.current_state == MetaState.NOMINAL

    def test_block_counter_resets_on_unblocked_cycle(self):
        m = MetaCognitionModule()
        m.observe({}, BLOCKED, 1.0, 1, tripartite_u=LOW_U)
        m.observe({}, BLOCKED, 1.0, 2, tripartite_u=LOW_U)
        report = m.observe({}, PASSED, 1.0, 3, tripartite_u=LOW_U)
        assert report.consecutive_council_blocks == 0

    def test_inquiry_active_triggers_exploring(self):
        m = MetaCognitionModule()
        report = m.observe({}, PASSED, 1.0, 1,
                           inquiry_active=True, inquiry_omega_value=0.9,
                           tripartite_u=LOW_U)
        assert report.current_state == MetaState.EXPLORING
        assert report.exploration_mode_active is True
        assert "InquiryStream" in report.trigger_reason

    def test_exploring_stays_while_inquiry_active(self):
        m = MetaCognitionModule()
        m.observe({}, PASSED, 1.0, 1,
                  inquiry_active=True, inquiry_omega_value=0.9, tripartite_u=LOW_U)
        report = m.observe({}, PASSED, 1.0, 2,
                           inquiry_active=True, inquiry_omega_value=0.9,
                           tripartite_u=LOW_U)
        assert report.current_state == MetaState.EXPLORING

    def test_exploring_exits_when_inquiry_stops(self):
        m = MetaCognitionModule()
        m.observe({}, PASSED, 1.0, 1,
                  inquiry_active=True, inquiry_omega_value=0.9, tripartite_u=LOW_U)
        report = m.observe({}, PASSED, 1.0, 2,
                           inquiry_active=False, inquiry_omega_value=0.0,
                           tripartite_u=LOW_U)
        assert report.current_state == MetaState.NOMINAL

    def test_repair_has_priority_over_inquiry(self):
        m = MetaCognitionModule()
        report = m.observe({}, PASSED, 0.3, 1,
                           inquiry_active=True, inquiry_omega_value=0.9,
                           tripartite_u=LOW_U)
        assert report.current_state == MetaState.EPISTEMIC_REPAIR

    def test_state_counts_and_to_dict(self):
        m = MetaCognitionModule()
        m.observe({}, BLOCKED, 1.0, 1, tripartite_u=LOW_U)
        m.observe({}, BLOCKED, 1.0, 2, tripartite_u=LOW_U)
        m.observe({}, BLOCKED, 1.0, 3, tripartite_u=LOW_U)
        m.observe({}, BLOCKED, 1.0, 4, tripartite_u=LOW_U)
        m.observe({}, BLOCKED, 1.0, 5, tripartite_u=LOW_U)
        stats = m.get_stats()
        assert stats["total_blocks"] == 5
        assert stats["recovery_cycles"] >= 2
        assert stats["consecutive_blocks"] == 5
        assert stats["recent_states"][-1]["state"] == "recovering"
        assert m.to_dict() == stats
