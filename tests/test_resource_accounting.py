from telos.core.accounting.resource_accounting import (
    ResourceAccountingLayer,
    ResourceCost,
    DictLedgerBackend,
)


class TestResourceAccounting:
    def test_instantiate(self):
        ral = ResourceAccountingLayer()
        assert ral.total_cost.compute_ms == 0.0
        assert ral.total_cost.memory_traces == 0

    def test_record_action(self):
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_action("reflex_check", ResourceCost(compute_ms=2.0, memory_traces=1))
        ral.record_action("planning", ResourceCost(compute_ms=12.0, memory_traces=3))
        assert ral.total_cost.compute_ms == 14.0
        assert ral.total_cost.memory_traces == 4

    def test_stream_activation(self):
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_stream_activation("reflex", compute_ms=2.0)
        ral.record_stream_activation("planning", compute_ms=12.0, memory_traces=3)
        assert ral.total_cost.compute_ms == 14.0

    def test_budget_enforcement_within(self):
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_action("light", ResourceCost(compute_ms=10.0, memory_traces=5))
        result = ral.check_budget(max_compute_ms=100.0, max_memory_traces=50)
        assert result["within_budget"] is True
        assert len(result["exceeded_dimensions"]) == 0

    def test_budget_enforcement_exceeded(self):
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_action("heavy", ResourceCost(compute_ms=500.0, memory_traces=200))
        result = ral.check_budget(max_compute_ms=100.0, max_memory_traces=50)
        assert result["within_budget"] is False
        assert len(result["exceeded_dimensions"]) >= 1

    def test_cycle_summary(self):
        ral = ResourceAccountingLayer()
        ral.set_cycle(7)
        ral.record_action("a1", ResourceCost(compute_ms=3.0))
        ral.record_action("a2", ResourceCost(compute_ms=4.0))
        summary = ral.cycle_summary()
        assert summary["cycle"] == 7
        assert summary["total_compute_ms"] == 7.0
        assert summary["action_count"] == 2

    def test_ledger_backend_commit_and_query(self):
        backend = DictLedgerBackend()
        ral = ResourceAccountingLayer(backend=backend)
        ral.set_cycle(1)
        ral.record_action("test_action", ResourceCost(compute_ms=5.0))
        ral.set_cycle(2)
        retrieved = ral.get_action_cost("test_action")
        assert retrieved is not None
        assert retrieved["cost"]["compute_ms"] == 5.0

    def test_ledger_cycle_costs(self):
        backend = DictLedgerBackend()
        ral = ResourceAccountingLayer(backend=backend)
        ral.set_cycle(5)
        ral.record_action("a", ResourceCost(compute_ms=1.0))
        ral.set_cycle(6)
        ral.record_action("b", ResourceCost(compute_ms=2.0))
        ral.set_cycle(7)
        cycle5 = ral.get_cycle_costs(5)
        assert len(cycle5) == 1
        cycle6 = ral.get_cycle_costs(6)
        assert len(cycle6) == 1
        cycle7 = ral.get_cycle_costs(7)
        assert len(cycle7) == 0

    def test_cost_addition(self):
        a = ResourceCost(compute_ms=1.0, memory_traces=2, bandwidth_bytes=100, storage_entries=1)
        b = ResourceCost(compute_ms=3.0, memory_traces=1, bandwidth_bytes=50, storage_entries=0)
        c = a + b
        assert c.compute_ms == 4.0
        assert c.memory_traces == 3
        assert c.bandwidth_bytes == 150.0
        assert c.storage_entries == 1

    def test_to_dict(self):
        ral = ResourceAccountingLayer()
        ral.set_cycle(1)
        ral.record_action("x", ResourceCost(compute_ms=2.0))
        d = ral.to_dict()
        assert d["current_cycle"] == 1
        assert d["pending_actions"] == 1

    def test_attach_backend(self):
        ral = ResourceAccountingLayer()
        new_backend = DictLedgerBackend()
        ral.attach_backend(new_backend)
        ral.set_cycle(1)
        ral.record_action("test", ResourceCost(compute_ms=3.0))
        ral.set_cycle(2)
        assert ral.get_action_cost("test") is not None
