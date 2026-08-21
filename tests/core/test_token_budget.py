"""Contract tests for telos/core/attention/token_budget.py."""

import pytest

from telos.core.attention.token_budget import (
    TokenBudgetManager, estimate_tokens, estimate_message_tokens,
    DEFAULT_TOKEN_BUDGET, DEFAULT_KEEP_LAST_N,
)


def test_estimate_tokens():
    assert estimate_tokens('hello world') == 3  # 11 chars / 4 + 0.5
    assert estimate_tokens('') == 0


def test_estimate_message_tokens_overhead():
    assert estimate_message_tokens({'role': 'user', 'content': 'hello world'}) \
        == estimate_tokens('hello world') + 12
    assert estimate_message_tokens({}) == 12


def test_score_user_base():
    m = TokenBudgetManager()
    assert m.score_message({'role': 'user', 'content': 'plain'}) == 0.8


def test_score_escalation_bonus():
    m = TokenBudgetManager()
    score = m.score_message({'role': 'assistant',
                             'content': 'emergency override requested'})
    assert score > 0.3


def test_score_block_keywords():
    m = TokenBudgetManager()
    score = m.score_message({'role': 'system',
                             'content': 'council block vetoed dissent'})
    assert score > 0.5


def test_score_trace_signals():
    m = TokenBudgetManager()
    trace = TokenBudgetManager.make_trace(di=0.2, md=0.8,
                                          blocked=True, escalated=True)
    score = m.score_message({'role': 'assistant', 'content': 'x'}, trace)
    assert score == pytest.approx(2.0)


def test_score_bounded_to_2():
    m = TokenBudgetManager()
    trace = TokenBudgetManager.make_trace(di=0.2, md=0.8,
                                          blocked=True, escalated=True)
    score = m.score_message({'role': 'user',
                             'content': 'emergency override blocked'}, trace)
    assert score <= 2.0


def test_score_length_penalty():
    m = TokenBudgetManager()
    long_score = m.score_message({'role': 'assistant', 'content': 'x' * 3000})
    short_score = m.score_message({'role': 'assistant', 'content': 'hi'})
    assert long_score < short_score


def test_make_trace():
    assert TokenBudgetManager.make_trace(di=0.5, md=0.1, blocked=True,
                                         escalated=False) == {
        'di': 0.5, 'md': 0.1, 'blocked': True, 'escalated': False,
    }


def test_optimize_empty():
    m = TokenBudgetManager()
    assert m.optimize([]) == []


def test_optimize_keeps_protected_last_turns():
    m = TokenBudgetManager(token_budget=2048, keep_last_n=2)
    hist = [
        {'role': 'user', 'content': 'plain ask'},
        {'role': 'assistant', 'content': 'plain answer'},
        {'role': 'user', 'content': 'emergency override escalate'},
        {'role': 'assistant', 'content': 'blocked by firewall'},
    ]
    out = m.optimize(hist)
    assert out[-1]['role'] == 'assistant'
    assert out[-2]['role'] == 'user'


def test_optimize_fits_all_when_budget_large():
    m = TokenBudgetManager(token_budget=2048, keep_last_n=2)
    hist = [{'role': 'user', 'content': 'short i'} for _ in range(8)]
    out = m.optimize(hist)
    assert len(out) == 8


def test_optimize_truncates_when_budget_exceeded():
    m = TokenBudgetManager(token_budget=700, keep_last_n=1)
    msgs = [{'role': 'assistant', 'content': 'ab cd ' * 200} for _ in range(6)]
    out = m.optimize(msgs)
    assert any('truncated' in msg.get('content', '') for msg in out)


def test_constants():
    assert DEFAULT_TOKEN_BUDGET == 2048
    assert DEFAULT_KEEP_LAST_N == 2
