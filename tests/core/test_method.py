"""Honest contract tests for telos/core/project/method.py (Method, MethodRegistry)."""

from telos.core.project.method import Method, MethodLifecycle, MethodRegistry


def test_method_default_lifecycle_is_proposed():
    m = Method(id="m1", name="alpha", project_id="p1")
    assert m.lifecycle == MethodLifecycle.PROPOSED
    assert m.attempts == 0
    assert m.successes == 0
    assert m.success_rate == 0.0


def test_success_rate_uses_max_attempts_guard():
    m = Method(id="m1", name="alpha", project_id="p1")
    assert m.success_rate == 0.0
    m.record_attempt(1, succeeded=True)
    assert m.success_rate == 1.0


def test_three_successes_promote_to_successful():
    m = Method(id="m1", name="alpha", project_id="p1")
    for cycle in range(1, 4):
        m.record_attempt(cycle, succeeded=True)
    assert m.lifecycle == MethodLifecycle.SUCCESSFUL
    assert m.attempts == 3
    assert m.successes == 3
    assert m.last_used_cycle == 3


def test_five_low_successes_mark_failed():
    m = Method(id="m2", name="beta", project_id="p1")
    for cycle in range(5):
        m.record_attempt(cycle, succeeded=False)
    assert m.lifecycle == MethodLifecycle.FAILED
    assert m.success_rate == 0.0


def test_record_attempt_updates_last_used_cycle():
    m = Method(id="m3", name="gamma", project_id="p1")
    m.record_attempt(7, succeeded=False)
    assert m.last_used_cycle == 7
    assert m.attempts == 1


def test_to_dict_contains_lifecycle_value():
    m = Method(id="m4", name="delta", project_id="p1")
    m.record_attempt(1, succeeded=True)
    d = m.to_dict()
    assert d["id"] == "m4"
    assert d["name"] == "delta"
    assert d["project_id"] == "p1"
    assert d["lifecycle"] == "proposed"
    assert "success_rate" in d
    assert "attempts" in d


def test_registry_register_creates_active_method():
    r = MethodRegistry()
    m = r.register("alpha", "proj1", cycle=0)
    assert m.lifecycle == MethodLifecycle.ACTIVE
    assert m.project_id == "proj1"
    assert m.birth_cycle == 0
    assert m.id in r._methods


def test_registry_get_returns_none_for_missing():
    r = MethodRegistry()
    assert r.get("method_missing") is None


def test_registry_active_and_failed_methods():
    r = MethodRegistry()
    active = r.register("alpha", "p1", cycle=0)
    failed = r.register("beta", "p1", cycle=0)
    failed.lifecycle = MethodLifecycle.FAILED
    assert r.active_methods() == [active]
    assert r.failed_methods() == [failed]


def test_parsimony_score_defaults_zero_five_when_no_active():
    r = MethodRegistry()
    assert r.parsimony_score() == 0.5


def test_parsimony_score_computes_from_active_names():
    r = MethodRegistry()
    r.register("alpha", "p1", cycle=0)
    score = r.parsimony_score()
    active = r.active_methods()
    expected = sum(1.0 / (1.0 + len(m.name)) for m in active) / len(active)
    assert score == expected
    assert 0.0 <= score <= 1.0


def test_registry_to_dict_counts():
    r = MethodRegistry()
    m = r.register("alpha", "p1", cycle=0)
    m.record_attempt(1, succeeded=True)
    m.record_attempt(2, succeeded=False)
    m.record_attempt(3, succeeded=False)
    m.record_attempt(4, succeeded=False)
    m.record_attempt(5, succeeded=False)
    d = r.to_dict()
    assert d["total"] == 1
    assert d["active"] == 0
    assert d["failed"] == 1
