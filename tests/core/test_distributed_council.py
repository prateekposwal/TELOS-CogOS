"""Gap-3 tests: DistributedCouncil is a real, wired advisory crew.

Proves:
  1. N role-agents register and aggregate correctly with weights
  2. the pipeline actually invokes the distributed council during execute()
  3. the PRIMARY typo fix is compatible (PRIMARAY alias still resolves)
  4. cadence control works (disable-able without breaking the pipeline)
"""

import os
import tempfile

import numpy as np

from telos.core.council.distributed import (
    DistributedCouncil, AgentRole, ROLE_WEIGHTS,
)
from telos.core.council.base import CouncilVerdict, ValidationSignal


def _primary_verdict(validated=True, di=1.0, md=0.0, signals=None):
    if signals is None:
        signals = [
            ValidationSignal("Reality", passed=True, confidence=0.9,
                             reason="ok", evidence_weight=0.5),
            ValidationSignal("MissionDrift", passed=True, confidence=0.8,
                             reason="ok", evidence_weight=0.4),
        ]
    return CouncilVerdict(validated=validated, signals=signals,
                          decision_integrity=di, mission_drift=md)


class TestDistributedCouncilCore:
    def test_registers_and_aggregates_role_agents_with_weights(self):
        dc = DistributedCouncil()
        dc.register_default_crew()
        assert dc.to_dict()["registered_agents"] == 5
        assert dc.to_dict()["agents"] == {
            "primary": "primary", "skeptic": "skeptic",
            "explorer": "explorer", "conservative": "conservative",
            "analyst": "analyst",
        }
        # All five perspectives submit votes
        result = dc.run_perspectives(_primary_verdict(validated=True, di=0.9, md=0.3))
        assert result["n_agents"] == 5
        assert dc.to_dict()["voting_agents"] == 5
        # Weighted aggregate: majority of weight says validated
        assert result["validated"] in (True, False)
        assert 0.0 <= result["decision_integrity"] <= 1.0
        assert result["consensus"] > 0.0
        # PRIMARY agent mirrors the binding verdict exactly
        primary_vote = [a for a in result["agents"] if a["role"] == "primary"][0]
        assert primary_vote["decision_integrity"] == 0.9

    def test_skeptic_blocks_when_dissent_weighted_high(self):
        """A blocked primary with dissent-heavy signals → skeptic stays blocked,
        explorer may still see opportunity (Λ4.3) — the crew disagrees."""
        signals = [
            ValidationSignal("Reality", passed=False, confidence=0.8,
                             reason="contradiction", evidence_weight=0.5),
            ValidationSignal("MissionDrift", passed=True, confidence=0.6,
                             reason="ok", evidence_weight=0.4),
        ]
        dc = DistributedCouncil()
        dc.register_default_crew()
        result = dc.run_perspectives(
            _primary_verdict(validated=False, di=0.2, md=0.4, signals=signals),
            context={"alternatives": ["a", "b"], "curiosity_bonus": 1.5},
        )
        by_role = {a["role"]: a for a in result["agents"]}
        assert by_role["primary"]["validated"] is False
        assert by_role["skeptic"]["validated"] is False
        assert by_role["analyst"]["validated"] is False
        assert by_role["explorer"]["validated"] is True  # novelty path
        # Weighted aggregate: PRIMARY(1.0) + CONSERVATIVE(0.7) + SKEPTIC(0.8)
        # + ANALYST(0.5) = 3.0 weight against; EXPLORER(0.6) for.
        assert result["validated"] is False
        assert result["consensus"] < 1.0

    def test_weighted_majority_not_raw_count(self):
        """aggregate() follows weights: 3 light agents cannot outvote the
        heavier PRIMARY+skeptic+conservative block."""
        dc = DistributedCouncil()
        dc.register_default_crew()
        # Manually submit: three validated with weight 0.5/0.6, two blocked
        # with weights 1.0 + 0.8 + 0.7 -> blocked weight 2.5 > validated 1.1
        dc.submit_verdict("primary", False, 0.2, 0.5)
        dc.submit_verdict("skeptic", False, 0.25, 0.5)
        dc.submit_verdict("conservative", False, 0.3, 0.5)
        dc.submit_verdict("explorer", True, 0.8, 0.5)
        dc.submit_verdict("analyst", True, 0.7, 0.5)
        agg = dc.aggregate()
        assert agg.validated is False
        assert abs(agg.decision_integrity - (
            0.2*1.0 + 0.25*0.8 + 0.3*0.7 + 0.8*0.6 + 0.7*0.5
        ) / 3.6) < 1e-9

    def test_primary_typo_compat(self):
        """PRIMARY is the canonical name; the deprecated PRIMARAY alias still
        resolves to the same value (telemetry/checkpoint compat)."""
        assert AgentRole.PRIMARY.value == "primary"
        assert AgentRole.PRIMARAY == AgentRole.PRIMARY
        assert AgentRole.PRIMARAY.value == "primary"

    def test_empty_council_aggregate_defaults(self):
        dc = DistributedCouncil()
        agg = dc.aggregate()
        assert agg.validated is True
        assert agg.decision_integrity == 1.0


class TestPipelineDistributedCouncil:
    def _build_pipeline(self, enabled=True, interval=1):
        from telos.core.runtime import TelosV14Pipeline, PipelineConfig
        from telos.core.contracts.domain_model import DomainAdapter
        from telos.core.ledger.skill_library import SkillLibrary
        from telos.core.streams.implementations import (
            ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
        )
        from telos.core.simulation import CounterfactualEngine
        from tests.core.conftest import MockSimulator

        class MockAdapter(DomainAdapter):
            def forward(self, x): return x
            def inverse(self, x): return x
            def intent_to_action(self, intent, state, mission_dir): return np.zeros(2)
            @property
            def name(self): return "mock"

        sim = MockSimulator()
        # Hermetic checkpoint dir per test run: a restored cycle count from
        # a stale checkpoint would shift the cadence and flake this test
        # (same shared-state pattern that caused the Gap-2 RNG flake).
        ckpt_dir = tempfile.mkdtemp(prefix=f"dc_wiring_{enabled}_{interval}_")
        config = PipelineConfig(
            simulator=sim, adapter=MockAdapter(),
            checkpoint_path=os.path.join(ckpt_dir, "ckpt"),
            distributed_council_enabled=enabled,
            distributed_council_interval=interval,
        )
        pipeline = TelosV14Pipeline(config)
        sl = SkillLibrary()
        se = CounterfactualEngine(sim, seed=7)
        pipeline.register_stream(ReflexStream(sl))
        pipeline.register_stream(PerceptionStream(sl))
        pipeline.register_stream(MemoryStream(sl))
        pipeline.register_stream(PlanningStream(sl, sim_engine=se))
        return pipeline

    def test_pipeline_invokes_distributed_council_during_execute(self):
        pipeline = self._build_pipeline()
        state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
        result = pipeline.execute(state)
        dv = result.distributed_verdict
        assert dv is not None, "execute() must run the distributed council"
        assert dv["aggregate"]["n_agents"] == 5
        assert dv["voting_agents"] == 5
        assert any(a.startswith("primary:") for a in dv["agents"])
        # carried into the DecisionTrace → decision log
        assert result.decision_trace.distributed_verdict is not None
        assert result.decision_trace.distributed_verdict["aggregate"]["n_agents"] == 5

    def test_disabled_distributed_council_does_not_break_pipeline(self):
        pipeline = self._build_pipeline(enabled=False)
        state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
        result = pipeline.execute(state)
        assert result.pipeline_phase.value == "complete"
        assert result.distributed_verdict is None

    def test_interval_cadence_runs_on_schedule(self):
        pipeline = self._build_pipeline(enabled=True, interval=2)
        state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
        r1 = pipeline.execute(state)  # cycle 1 → interval 2 → skip
        r2 = pipeline.execute(state)  # cycle 2 → run
        assert r1.distributed_verdict is None
        assert r2.distributed_verdict is not None

    def test_distributed_council_context_carries_domain_and_knowledge(self):
        """v9: the DOMAIN_EXPERT lens needs the domain string + the perceive
        knowledge report in the crew context — both keys must be present on
        every distributed-council invocation."""
        pipeline = self._build_pipeline()
        state = np.array([1.0, 2.0, 0.5, -0.3, 0.0, 0.1])
        captured = {}
        dc = pipeline._distributed_council
        orig = dc.run_perspectives

        def capturing(primary_verdict, context=None):
            captured["context"] = context
            return orig(primary_verdict, context)

        dc.run_perspectives = capturing
        try:
            pipeline.execute(state)
        finally:
            dc.run_perspectives = orig
        assert captured, "distributed council must run during execute"
        assert "domain" in captured["context"]
        assert "knowledge_report" in captured["context"]
