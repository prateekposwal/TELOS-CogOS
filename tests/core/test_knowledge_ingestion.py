"""Contract tests for telos/core/context/knowledge_ingestion.py."""

from types import SimpleNamespace as NS

from telos.core.context.knowledge_ingestion import (
    ConversationKnowledgeIngestion, DOMAIN_CONVERSATION, DOMAIN_USER_PREFERENCE,
    DOMAIN_BLOCKER, DOMAIN_INTENT,
)


class _Intent:
    intent_type = 'navigate'


class _Trace:
    decision_integrity = 0.8
    mission_drift = 0.1
    selected_intent = _Intent()
    blocking_validator = 'wall_check'


class _Result:
    decision_trace = _Trace()
    council_blocked = True
    firewall_blocked = False


def _search_lib():
    def search(domain, top_k):
        if 'user_preference' in domain:
            return [NS(approach='prefer_X', params={'content': 'I like X'})]
        if 'conversation' in domain:
            return [NS(approach='navigate', params={})]
        if 'blocker' in domain:
            return [NS(approach='blocked_a', failure_reason='firewall',
                       params={})]
        return []
    return search


def test_domain_constants():
    assert DOMAIN_CONVERSATION == 'conversation'
    assert DOMAIN_USER_PREFERENCE == 'user_preference'
    assert DOMAIN_BLOCKER == 'blocker'
    assert DOMAIN_INTENT == 'intent_pattern'


def test_pre_cycle_populates_context():
    records = []
    ki = ConversationKnowledgeIngestion(
        search_fn=_search_lib(),
        consult_fn=lambda domain, cycle: {'ok': True},
        record_fn=lambda domain, **kw: records.append((domain, kw)) or 'id',
    )
    ctx = ki.pre_cycle('alice', 3)
    assert ctx['known_user'] is True
    assert ctx['known_preferences'] == ['prefer_X']
    assert ctx['past_approaches'] == ['navigate']
    assert ctx['past_failures'] == [{'approach': 'blocked_a',
                                     'reason': 'firewall'}]
    assert ctx['consultation'] == {'ok': True}


def test_pre_cycle_unknown_user():
    ki = ConversationKnowledgeIngestion(
        search_fn=lambda domain, top_k: [],
        consult_fn=lambda domain, cycle: {},
        record_fn=lambda domain, **kw: 'id',
    )
    ctx = ki.pre_cycle('bob', 1)
    assert ctx['known_user'] is False
    assert ctx['known_preferences'] == []


def test_post_cycle_records_conversation_and_blocker():
    records = []
    ki = ConversationKnowledgeIngestion(
        search_fn=lambda domain, top_k: [],
        consult_fn=lambda domain, cycle: {},
        record_fn=lambda domain, **kw: records.append((domain, kw)) or 'id',
    )
    ki.post_cycle('alice', 4, _Result(),
                  [{'role': 'user', 'content': 'I prefer fast'}])
    domains = [d for d, _ in records]
    assert f"{DOMAIN_CONVERSATION}/alice" in domains
    assert f"{DOMAIN_BLOCKER}/alice" in domains
    conv = [kw for d, kw in records if d == f"{DOMAIN_CONVERSATION}/alice"]
    assert conv[0]['approach'] == 'navigate'
    assert conv[0]['outcome'] == 0.8


def test_post_cycle_no_trace_returns_early():
    records = []
    ki = ConversationKnowledgeIngestion(
        search_fn=lambda domain, top_k: [],
        consult_fn=lambda domain, cycle: {},
        record_fn=lambda domain, **kw: records.append(kw) or 'id',
    )
    ki.post_cycle('alice', 5, NS(decision_trace=None), [])
    assert records == []


def test_post_cycle_extracts_user_preference():
    records = []
    ki = ConversationKnowledgeIngestion(
        search_fn=lambda domain, top_k: [],
        consult_fn=lambda domain, cycle: {},
        record_fn=lambda domain, **kw: records.append((domain, kw)) or 'id',
    )
    ki.post_cycle('alice', 4, _Result(),
                  [{'role': 'user',
                    'content': 'I prefer fast and please call me frank'}])
    pref_domains = [d for d, _ in records
                    if d == f"{DOMAIN_USER_PREFERENCE}/alice"]
    assert len(pref_domains) >= 1
    for d, kw in records:
        if d == f"{DOMAIN_USER_PREFERENCE}/alice":
            assert kw['outcome'] == 0.9
            assert 'preference' in kw['tags']


def test_post_cycle_high_drift_records_warning():
    class Trace2:
        decision_integrity = 0.4
        mission_drift = 0.9
        selected_intent = _Intent()

    class Result2:
        decision_trace = Trace2()
        council_blocked = False
        firewall_blocked = False

    records = []
    ki = ConversationKnowledgeIngestion(
        search_fn=lambda domain, top_k: [],
        consult_fn=lambda domain, cycle: {},
        record_fn=lambda domain, **kw: records.append((domain, kw)) or 'id',
    )
    ki.post_cycle('alice', 6, Result2(), [])
    approaches = [kw['approach'] for _, kw in records]
    assert f"high_drift_navigate" in approaches


def test_summarize_user_knowledge():
    prefs = [NS(approach='prefer_X', params={'content': 'contentX'},
                outcome=0.9)]
    convs = [NS(approach='navigate', params={}, outcome=0.8)]
    blockers = [NS(approach='blocked_a', failure_reason='fw', params={})]

    def search(domain, top_k):
        if 'user_preference' in domain:
            return prefs
        if 'conversation' in domain:
            return convs
        if 'blocker' in domain:
            return blockers
        return []

    ki = ConversationKnowledgeIngestion(
        search_fn=search,
        consult_fn=lambda domain, cycle: {},
        record_fn=lambda domain, **kw: 'id',
    )
    summ = ki.summarize_user_knowledge('alice')
    assert summ['user_name'] == 'alice'
    assert summ['known_preferences'] == [{'key': 'prefer_X',
                                          'content': 'contentX'}]
    assert summ['past_intents'] == [{'type': 'navigate', 'outcome': 0.8}]
    assert summ['past_blockers'] == [{'type': 'blocked_a', 'reason': 'fw'}]
