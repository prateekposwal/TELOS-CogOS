"""Contract tests for telos/core/context/summarizer.py."""

import pytest

from telos.core.context.summarizer import (
    ContextSummarizer, SessionEssence, SUMMARIZER_PROMPT,
    DEFAULT_SUMMARY_INTERVAL, DEFAULT_MAX_HISTORY_BEFORE_SUMMARY,
)


def test_session_essence_defaults():
    e = SessionEssence()
    assert e.key_decisions == []
    assert e.user_preferences == []
    assert e.blockers_resolved == []
    assert e.recurring_intents == []
    assert e.mood_trajectory == 'neutral'


def test_session_essence_to_dict():
    e = SessionEssence(key_decisions=['a'], mood_trajectory='calm')
    d = e.to_dict()
    assert d['key_decisions'] == ['a']
    assert d['mood_trajectory'] == 'calm'
    for k in ['user_preferences', 'blockers_resolved',
              'recurring_intents']:
        assert k in d


def test_session_essence_roundtrip_json():
    e = SessionEssence(key_decisions=['a'], mood_trajectory='calm')
    import json
    restored = SessionEssence.from_dict(json.loads(e.to_json()))
    assert restored.to_dict() == e.to_dict()


def test_session_essence_from_dict_defaults():
    e = SessionEssence.from_dict({'key_decisions': ['b']})
    assert e.key_decisions == ['b']
    assert e.mood_trajectory == 'neutral'


def test_session_essence_merge_deduplicates():
    a = SessionEssence(key_decisions=['x'], mood_trajectory='calm')
    b = SessionEssence(key_decisions=['x', 'y'], mood_trajectory='happy')
    m = a.merge(b)
    assert m.key_decisions == ['x', 'y']
    assert m.mood_trajectory == 'happy'


def test_session_essence_repr():
    e = SessionEssence(key_decisions=['a'], mood_trajectory='calm')
    assert 'decisions=1' in repr(e)


def test_defaults():
    assert DEFAULT_SUMMARY_INTERVAL == 5
    assert DEFAULT_MAX_HISTORY_BEFORE_SUMMARY == 20


def test_parse_essence_direct_json():
    e = ContextSummarizer._parse_essence(
        '{"key_decisions": ["d1"], "mood_trajectory": "x"}')
    assert e.key_decisions == ['d1']
    assert e.mood_trajectory == 'x'


def test_parse_essence_fenced_json():
    e = ContextSummarizer._parse_essence(
        '```json\n{"mood_trajectory": "f"}\n```')
    assert e.mood_trajectory == 'f'


def test_parse_essence_embedded_json():
    e = ContextSummarizer._parse_essence(
        'Here is result: {"mood_trajectory": "embed"} done')
    assert e.mood_trajectory == 'embed'


def test_parse_essence_garbage_returns_none():
    assert ContextSummarizer._parse_essence('not json at all') is None


def test_maybe_summarize_not_due_returns_none():
    cs = ContextSummarizer(ollama_chat_fn=lambda m: '{}', summary_interval=5)
    assert cs.maybe_summarize(1, []) is None


def test_maybe_summarize_insufficient_history():
    cs = ContextSummarizer(ollama_chat_fn=lambda m: '{}', summary_interval=1)
    assert cs.maybe_summarize(1, [{'role': 'user', 'content': 'a'}]) is None


def test_maybe_summarize_generates_essence():
    calls = []

    def ollama(messages):
        calls.append(messages)
        return '{"key_decisions": ["k1"], "mood_trajectory": "good"}'

    cs = ContextSummarizer(ollama_chat_fn=ollama, summary_interval=5)
    hist = [{'role': 'user', 'content': 'hi x' + str(i)} for i in range(10)]
    ess = cs.maybe_summarize(5, hist)
    assert ess is not None
    assert ess.key_decisions == ['k1']
    assert len(cs.summaries) == 1
    assert cs.running_essence.key_decisions == ['k1']
    # not due again immediately
    assert cs.maybe_summarize(6, hist) is None


def test_maybe_summarize_accumulates_running_essence():
    def ollama(messages):
        return '{"key_decisions": ["k1"]}'

    cs = ContextSummarizer(ollama_chat_fn=ollama, summary_interval=1)
    hist = [{'role': 'user', 'content': 'hi x' + str(i)} for i in range(8)]
    cs.maybe_summarize(1, hist)
    cs.maybe_summarize(2, hist)
    assert cs.running_essence.key_decisions == ['k1']
    assert len(cs.summaries) == 2


def test_ollama_error_returns_none_and_not_recorded():
    def bad(messages):
        raise RuntimeError('boom')

    cs = ContextSummarizer(ollama_chat_fn=bad, summary_interval=1)
    hist = [{'role': 'user', 'content': c} for c in 'abcd']
    assert cs.maybe_summarize(1, hist) is None
    assert cs.summaries == []


def test_get_context_block():
    def ollama(messages):
        return '{"key_decisions": ["k1"]}'

    cs = ContextSummarizer(ollama_chat_fn=ollama, summary_interval=1)
    hist = [{'role': 'user', 'content': 'hi x' + str(i)} for i in range(8)]
    cs.maybe_summarize(1, hist)
    block = cs.get_context_block()
    assert block['summary_count'] == 1
    assert block['session_essence']['key_decisions'] == ['k1']
