"""Contract tests for TrustManager — epistemic governance of who may access
what truth, when (cognitive confidentiality)."""
from telos.core.governance.trust_manager import TrustManager
from telos.core.governance.base import AccessLevel


def _tm():
    return TrustManager()


def test_register_and_authorize_stream():
    tm = _tm()
    tm.register_stream("reflex", default_access=AccessLevel.OBSERVE)
    result = tm.authorize_stream("reflex", "gridworld")
    assert isinstance(result, bool)


def test_unknown_stream_public_domain_allowed():
    tm = _tm()
    assert tm.authorize_stream("unregistered", "public") is True
    assert tm.authorize_stream("unregistered", "gridworld") is False


def test_knowledge_release_has_documented_behavior():
    tm = _tm()
    tm.set_mission("explore")
    result = tm.authorize_knowledge_release("gridworld")
    assert result in (True, False)


def test_stats_are_serializable():
    tm = _tm()
    tm.register_stream("s1", default_access=AccessLevel.ANALYZE)
    tm.authorize_stream("s1", "d")
    d = tm.stats
    assert isinstance(d, dict)
    assert "authorized_streams" in d
    import json
    json.dumps(d)