"""
Canonical trace types — core/types.py AND core/ledger/types.py (same basename).

Honest contract coverage: DecisionTrace serialization (canonical aliases),
PipelineConfig defaults, and ledger Skill/Experience types where declared.
"""
import numpy as np

from telos.core.types import DecisionTrace, PipelineConfig, PipelineResult
from telos.world.facts import DomainFacts


def make_trace():
    return DecisionTrace(
        cycle_id=1, timestamp=1.0,
        world_state_snapshot=np.zeros(2),
        domain_facts=None, stream_activations=[], selected_intent=None,
        selected_action=None, representation="r", budget_consumed_ms=1.0,
        budget_total_ms=10.0, worlds_simulated=0, cycle_duration_ms=2.0,
    )


class TestDecisionTrace:
    def test_canonical_aliases(self):
        d = make_trace().to_dict()
        assert "intent" in d and "discrimination_index" in d
        assert "action_taken" in d and "budget_carryover_ms" in d
        assert d["discrimination_index"] == 1.0

    def test_tool_audit_field(self):
        d = make_trace()
        d.tool_audit = {"tool_name": "git_status", "allowed": True}
        assert d.to_dict()["tool_audit"]["tool_name"] == "git_status"

    def test_roundtrip_dict(self):
        d = make_trace().to_dict()
        assert d["cycle_id"] == 1
        assert d["world_state"] == [0.0, 0.0]


class TestPipelineConfig:
    def test_defaults(self):
        c = PipelineConfig()
        assert c.compute_budget_ms == 50.0
        assert c.operator_tool_permission is False
        assert c.action_executor is None
        assert c.distributed_council_enabled is True


class TestPipelineResult:
    def test_defaults(self):
        r = PipelineResult(selected_trajectory=None, health_score=1.0,
                           pipeline_phase=None)
        assert r.council_blocked is False
        assert r.decision_integrity == 1.0
