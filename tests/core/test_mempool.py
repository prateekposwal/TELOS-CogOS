"""
Decision Mempool (core/mempool.py) — honest contract coverage.
"""
from telos.core.mempool import DecisionMempool, MempoolStatus


def _intent(name="explore", confidence=0.9):
    from telos.intent_ir import IntentIR
    return IntentIR(intent_type=name, confidence=confidence, params={})


class TestDecisionMempool:
    def test_submit_confirm_flow(self):
        m = DecisionMempool()
        iid = m.submit(_intent(), stream_name="s1")
        assert iid is not None
        assert m.pending_count == 1
        assert m.confirm(iid) is True
        assert m.pending_count == 0
        assert any(e.intent_id == iid for e in m.get_confirmed())

    def test_reject_flow(self):
        m = DecisionMempool()
        iid = m.submit(_intent(), stream_name="s2")
        assert m.reject(iid, reason="blocked") is True
        assert any(e.intent_id == iid for e in m.get_rejected())

    def test_confirm_unknown_returns_false(self):
        m = DecisionMempool()
        assert m.confirm("nope") is False
        assert m.reject("nope") is False

    def test_capacity(self):
        m = DecisionMempool(max_pending=2)
        m.submit(_intent("a")); m.submit(_intent("b"))
        assert m.mempool_full is True

    def test_clear_and_stats(self):
        m = DecisionMempool()
        m.submit(_intent())
        m.clear()
        assert m.pending_count == 0
        assert m.stats is not None
