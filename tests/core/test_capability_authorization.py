"""
Honest contract tests for telos/core/governance/capability_authorization.py
(v6 capability gate). The gate is conjunctive: authorized() == all(mandatory
gates are PASS or LIMITED); a single FAIL vetoes regardless of the rest.
"""

import pytest

from telos.core.governance.capability_authorization import (
    CapabilityAuthorization,
    CapabilityDimension,
    CapabilityStatus,
    all_pass,
    from_dimensions,
)


DIMENSION_NAMES = [
    "observability",
    "model_fidelity",
    "action_validity",
    "risk_coverage",
    "causal_confidence",
    "recovery",
    "authority",
]


def test_default_authorization_is_fully_authorized():
    cap = CapabilityAuthorization()
    assert cap.authorized() is True
    assert cap.failed_gates() == []


def test_seven_mandatory_dimensions_present():
    cap = CapabilityAuthorization()
    assert [d.name for d in cap.dimensions] == DIMENSION_NAMES
    assert all(d.mandatory for d in cap.dimensions)


def test_single_fail_vetoes_even_when_all_others_pass():
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.PASS,
        model_fidelity=CapabilityStatus.FAIL,
        action_validity=CapabilityStatus.PASS,
        risk_coverage=CapabilityStatus.PASS,
        causal_confidence=CapabilityStatus.PASS,
        recovery=CapabilityStatus.PASS,
        authority=CapabilityStatus.PASS,
    )
    assert cap.authorized() is False
    assert cap.failed_gates() == ["model_fidelity"]


def test_each_dimension_fail_is_detected_by_name():
    for name in DIMENSION_NAMES:
        kwargs = {name: CapabilityStatus.FAIL}
        cap = CapabilityAuthorization(**kwargs)
        assert cap.authorized() is False
        assert cap.failed_gates() == [name]


def test_limited_gate_does_not_veto():
    cap = CapabilityAuthorization(model_fidelity=CapabilityStatus.LIMITED)
    assert cap.authorized() is True
    assert cap.failed_gates() == []


def test_unknown_blocks_authorization_but_is_not_a_fail():
    cap = CapabilityAuthorization(model_fidelity=CapabilityStatus.UNKNOWN)
    assert cap.authorized() is False
    assert cap.failed_gates() == []


@pytest.mark.parametrize("status,expected_ok", [
    (CapabilityStatus.PASS, True),
    (CapabilityStatus.LIMITED, True),
    (CapabilityStatus.FAIL, False),
    (CapabilityStatus.UNKNOWN, False),
])
def test_capability_status_is_ok_semantics(status, expected_ok):
    assert status.is_ok is expected_ok


def test_dimension_passed_follows_status_is_ok():
    dim = CapabilityDimension("x", CapabilityStatus.LIMITED)
    assert dim.passed is True
    dim2 = CapabilityDimension("y", CapabilityStatus.FAIL)
    assert dim2.passed is False


def test_gate_lookup_returns_dimension_or_none():
    cap = CapabilityAuthorization()
    dim = cap.gate("authority")
    assert dim is not None
    assert dim.name == "authority"
    assert cap.gate("no_such_gate") is None


def test_dimensions_returns_a_copy():
    cap = CapabilityAuthorization()
    dims = cap.dimensions
    dims.clear()
    assert len(cap.dimensions) == 7


def test_to_dict_contract():
    cap = CapabilityAuthorization(
        model_fidelity=CapabilityStatus.FAIL,
        details={"model_fidelity": "model rejected by validation"},
    )
    d = cap.to_dict()
    assert d["authorized"] is False
    assert d["failed_gates"] == ["model_fidelity"]
    assert d["profile"]["observability"] == "PASS"
    assert d["profile"]["model_fidelity"] == "FAIL"
    assert d["profile"]["authority"] == "PASS"
    assert d["details"] == {"model_fidelity": "model rejected by validation"}


def test_to_dict_omits_empty_details():
    cap = CapabilityAuthorization()
    d = cap.to_dict()
    assert d["details"] == {}
    assert d["authorized"] is True


def test_repr_contains_authorized_flag():
    cap = CapabilityAuthorization()
    assert "authorized=True" in repr(cap)
    cap2 = CapabilityAuthorization(authority=CapabilityStatus.FAIL)
    assert "authorized=False" in repr(cap2)


def test_all_pass_convenience_constructor():
    cap = all_pass()
    assert cap.authorized() is True
    assert cap.failed_gates() == []


def test_from_dimensions_partial_defaults_to_pass():
    cap = from_dimensions({"model_fidelity": CapabilityStatus.FAIL})
    assert cap.authorized() is False
    assert cap.failed_gates() == ["model_fidelity"]
    # Everything not supplied defaulted to PASS, so only model_fidelity failed.
    assert cap.gate("observability").status == CapabilityStatus.PASS


def test_from_dimensions_unknown_default_blocks_by_omission():
    cap = from_dimensions(
        {"model_fidelity": CapabilityStatus.PASS},
        default=CapabilityStatus.UNKNOWN,
    )
    assert cap.authorized() is False
    assert cap.failed_gates() == []
    assert cap.gate("model_fidelity").status == CapabilityStatus.PASS


def test_from_dimensions_attaches_details():
    cap = from_dimensions(
        {"observability": CapabilityStatus.LIMITED},
        details={"observability": "partially occluded"},
    )
    assert cap.gate("observability").detail == "partially occluded"
    assert cap.to_dict()["details"] == {"observability": "partially occluded"}


def test_high_scores_cannot_trade_away_a_failed_gate():
    # The whole point of the gate: a failed capability dimension is a veto
    # no matter how strong the rest of the profile looks.
    cap = CapabilityAuthorization(
        observability=CapabilityStatus.PASS,
        model_fidelity=CapabilityStatus.PASS,
        action_validity=CapabilityStatus.PASS,
        risk_coverage=CapabilityStatus.PASS,
        causal_confidence=CapabilityStatus.PASS,
        recovery=CapabilityStatus.PASS,
        authority=CapabilityStatus.FAIL,
    )
    assert cap.authorized() is False
    assert cap.failed_gates() == ["authority"]
