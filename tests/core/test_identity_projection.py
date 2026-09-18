"""Tests for IdentityProjectionGate — F(I) formal domain restrictor."""

from telos.core.identity.projection_gate import IdentityProjectionGate
from telos.core.identity.system_self import IdentityCore, IdentityNarrative


class TestIdentityProjectionGate:

    def test_admits_reflex(self):
        gate = IdentityProjectionGate()
        assert gate.is_admissible("reflex") is True
        assert gate.is_admissible("halt") is True
        assert gate.is_admissible("emergency_stop") is True

    def test_admits_curiosity_with_core(self):
        gate = IdentityProjectionGate()
        assert gate.is_admissible("curiosity_explore", mission_active=True) is True

    def test_to_dict(self):
        gate = IdentityProjectionGate()
        d = gate.to_dict()
        assert "core_values" in d
        assert "narrative_role" in d
        assert "narrative_markers" in d
        assert "curiosity" in d["core_values"]

    def test_project_intents(self):
        gate = IdentityProjectionGate()
        class MockIntent:
            def __init__(self, t):
                self.intent_type = t
        intents = [MockIntent("reflex"), MockIntent("curiosity_explore"), MockIntent("plan_trajectory")]
        result = gate.project_intents(intents, mission_active=True, mission_ids=["m1"])
        assert len(result) == 3

    def test_custom_narrative(self):
        narrative = IdentityNarrative(role="explorer", markers={"curious", "bold"})
        gate = IdentityProjectionGate(identity_narrative=narrative)
        assert gate.to_dict()["narrative_role"] == "explorer"
        assert "bold" in gate.to_dict()["narrative_markers"]


class TestStrictVsMissionlessBootstrap:
    """The mission-existence layer is strict by default; the documented
    mission-less bootstrap path skips ONLY that layer (Layers 1-2 still hold).
    (Λ4.1 × theorem T8)"""

    def test_strict_gate_blocks_mission_less_intent(self):
        gate = IdentityProjectionGate()
        # No active mission + strict (default) => mission-less intent blocked.
        assert gate.is_admissible("plan_trajectory", mission_active=False) is False

    def test_bootstrap_flag_admits_mission_less_intent(self):
        gate = IdentityProjectionGate()
        # Documented pre-mission path: mission-existence layer not applicable.
        assert gate.is_admissible(
            "plan_trajectory", mission_active=False,
            missionless_bootstrap=True,
        ) is True

    def test_bootstrap_still_enforces_core_values(self):
        # A core-value violator is projected out EVEN on the bootstrap path —
        # the exception skips only Layer 3, never Layers 1-2.
        gate = IdentityProjectionGate()
        assert gate.is_admissible(
            "steal_payload", mission_active=False,
            missionless_bootstrap=True,
        ) is False

    def test_project_intents_bootstrap_filters_only_inadmissible(self):
        from telos.intent_ir import IntentIR
        gate = IdentityProjectionGate()
        intents = [
            IntentIR(intent_type="plan_trajectory", confidence=0.8),
            IntentIR(intent_type="steal_payload", confidence=0.8),
            IntentIR(intent_type="reflex", confidence=0.8),
        ]
        kept = gate.project_intents(
            intents, mission_active=False, missionless_bootstrap=True)
        assert {i.intent_type for i in kept} == {"plan_trajectory", "reflex"}

    def test_project_intents_strict_default_unchanged(self):
        # T8's primitive: strict default still projects mission-less intents out.
        from telos.intent_ir import IntentIR
        gate = IdentityProjectionGate()
        intents = [
            IntentIR(intent_type="plan_trajectory", confidence=0.8),
            IntentIR(intent_type="reflex", confidence=0.8),
        ]
        kept = gate.project_intents(intents, mission_active=False)
        assert [i.intent_type for i in kept] == ["reflex"]


class _FakeMission:
    def __init__(self, mid):
        self.id = mid


class _FakePortfolio:
    def __init__(self, missions=()):
        self._missions = list(missions)

    def active_missions(self):
        return list(self._missions)


class _FakePipeline:
    def __init__(self, gate, portfolio, narrative=None):
        self._identity_projection_gate = gate
        self._mission_portfolio = portfolio
        self._identity_narrative = narrative


class TestSelectEnforcesIdentityProjection:
    """Root enforcement in SelectPhase: an identity-inadmissible trajectory is
    projected out, not merely logged (the old behaviour)."""

    def _ctx(self, intents, selected):
        from telos.core.phases.base import PhaseContext
        import numpy as np
        ctx = PhaseContext(cycle_count=7, state=np.zeros(2), user_name=None)
        ctx.intents = list(intents)
        ctx.selected_intent = selected
        return ctx

    def _pipe(self, missions):
        gate = IdentityProjectionGate()
        return _FakePipeline(gate, _FakePortfolio(missions))

    def test_inadmissible_selected_is_replaced_by_best_admissible(self):
        from telos.core.phases.select import SelectPhase
        from telos.intent_ir import IntentIR
        bad = IntentIR(intent_type="steal_payload", confidence=0.9)
        good = IntentIR(intent_type="plan_trajectory", confidence=0.5)
        weak = IntentIR(intent_type="memory_recall", confidence=0.2)
        ctx = self._ctx([(bad, 0.9), (good, 0.5), (weak, 0.2)], bad)
        SelectPhase()._enforce_identity_projection(self._pipe([_FakeMission("m1")]), ctx)
        # Inadmissible removed from the option space and from the selection.
        assert "steal_payload" not in {i.intent_type for i, _ in ctx.intents}
        assert ctx.selected_intent.intent_type == "plan_trajectory"
        assert ctx.identity_projection["projected_out"] == ["steal_payload"]
        assert ctx.identity_projection["rejected_selected"] == "steal_payload"
        assert ctx.identity_projection["replacement"] == "plan_trajectory"
        assert ctx.identity_projection["fallback"] is False

    def test_no_admissible_candidate_uses_safe_reflex_fallback(self):
        from telos.core.phases.select import SelectPhase
        from telos.intent_ir import IntentIR
        bad = IntentIR(intent_type="steal_payload", confidence=0.9)
        bad2 = IntentIR(intent_type="deceive_peer", confidence=0.8)
        ctx = self._ctx([(bad, 0.9), (bad2, 0.8)], bad)
        SelectPhase()._enforce_identity_projection(self._pipe([_FakeMission("m1")]), ctx)
        assert ctx.selected_intent is not None
        assert ctx.selected_intent.intent_type == "reflex"
        assert ctx.identity_projection["fallback"] is True
        assert ctx.identity_projection["projected_out"] == ["steal_payload", "deceive_peer"]

    def test_admissible_selection_is_untouched(self):
        from telos.core.phases.select import SelectPhase
        from telos.intent_ir import IntentIR
        good = IntentIR(intent_type="plan_trajectory", confidence=0.9)
        ctx = self._ctx([(good, 0.9)], good)
        SelectPhase()._enforce_identity_projection(self._pipe([_FakeMission("m1")]), ctx)
        assert ctx.selected_intent is good
        assert ctx.identity_projection["projected_out"] == []
        assert ctx.identity_projection["rejected_selected"] is None

    def test_missionless_bootstrap_admits_normal_intent(self):
        from telos.core.phases.select import SelectPhase
        from telos.intent_ir import IntentIR
        good = IntentIR(intent_type="plan_trajectory", confidence=0.9)
        ctx = self._ctx([(good, 0.9)], good)
        # Empty portfolio => documented bootstrap path, not a collapse.
        SelectPhase()._enforce_identity_projection(self._pipe([]), ctx)
        assert ctx.selected_intent is good
        assert ctx.identity_projection["missionless_bootstrap"] is True
        assert ctx.identity_projection["projected_out"] == []
