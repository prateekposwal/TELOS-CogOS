"""
DecisionTraceBuilder (core/trace_builder.py) — honest contract coverage.
"""
import numpy as np

from telos.core.trace_builder import build_trace


class FakeBudget:
    consumed_ms = 5.0
    total_budget_ms = 10.0
    budget_carryover_ms = 2.0


class FakeCtx:
    def __init__(self):
        self.verdict = None
        self.world = None
        self.domain_facts = None
        self.stream_activations = []
        self.selected_intent = None
        self.selected_action = None
        self.representation = "rep"
        self.worlds_generated = 0
        self.semantic_depths = []
        self.firewall_verdict = None
        self.firewall_blocked = False
        self.strategic_options_data = []
        self.tool_audit = None
        self.curiosity_bonus = 1.0
        self.curiosity_state = None
        self.psdt = None
        self.selected_question = None
        self.perceive = None
        self.reflection = None
        self.attention_metrics = None
        self.local_optima_escape = None


class FakeInfra:
    system_self = None


class TestBuildTrace:
    def test_builds_with_minimal_ctx(self):
        ctx = FakeCtx()
        trace = build_trace(
            ctx=ctx, state=np.zeros(2), cycle_count=3,
            budget_manager=FakeBudget(), cycle_duration=1.5,
            infra_manager=FakeInfra(), last_quality_report=None,
        )
        assert trace.cycle_id == 3
        assert trace.budget_carryover_ms == 2.0
        assert trace.tool_audit is None
        d = trace.to_dict()
        assert d["budget_carryover_ms"] == 2.0
        assert d["intent"] is None

    def test_verdict_defaults_when_missing(self):
        ctx = FakeCtx()
        trace = build_trace(ctx=ctx, state=np.zeros(1), cycle_count=1,
                            budget_manager=FakeBudget(), cycle_duration=0.5,
                            infra_manager=FakeInfra(), last_quality_report=None)
        assert trace.decision_integrity == 1.0
