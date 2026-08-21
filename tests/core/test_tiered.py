"""Contract tests for TieredContext — the three-tier context window
(hot raw → warm compressed → cold summarized) that bounds the prompt."""
import pytest

from telos.core.context.tiered import TieredContext


def _msg(user="user", content="hello"):
    return {"role": user, "content": content}


def test_add_message_lands_in_hot():
    tc = TieredContext()
    tc.add_message(_msg())
    assert len(tc.hot) == 1
    assert tc.get_context()[-1]["content"] == "hello"


def test_hot_low_signal_is_preserved():
    tc = TieredContext()
    tc.add_message(_msg(content="high"), trace_signal=1.0)
    tc.add_message(_msg(content="low"), trace_signal=0.0)
    assert "_trace_signal" in tc.hot[0]


def test_token_estimate_is_positive_int():
    tc = TieredContext()
    tc.add_message(_msg(content="a" * 40))
    assert tc.get_token_estimate() > 0


def test_pressure_rises_with_messages():
    tc = TieredContext(hot_limit=2)
    tc.add_message(_msg())
    p1 = tc.get_pressure()
    tc.add_message(_msg())
    p2 = tc.get_pressure()
    assert p2 >= p1


def test_compression_demotes_hot_to_warm():
    tc = TieredContext(hot_limit=2, cold_compress_count=20, token_budget=1_000_000)
    for i in range(4):
        tc.add_message(_msg(content=f"msg-{i}"))
    assert len(tc.hot) <= tc.hot_limit
    assert len(tc.warm) >= 1, "over-hot messages must be compressed into warm"


def test_to_dict_shape():
    tc = TieredContext()
    tc.add_message(_msg())
    d = tc.to_dict()
    assert "hot" in d and "warm" in d and "cold" in d