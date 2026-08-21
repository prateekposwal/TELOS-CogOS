"""Contract tests for PSDT — partially signed decision trace integrity.

Each stream signs its contribution; the council signs the full assembly.
verify_full() is True only when every partial signature verifies AND the
council signature exists. Tampering with any field breaks verification.
"""
import pytest

from telos.core.trace.psdt import PartialDecision, PSDT


def _partial(stream="reflex", priority=1.0, intent="move", conf=0.8, eh="abc"):
    return PartialDecision(
        stream_name=stream, stream_priority=priority, intent_type=intent,
        confidence=conf, evidence_hash=eh,
    )


def test_signature_roundtrip_verifies():
    p = _partial()
    p.sign()
    assert p.signature
    assert p.verify() is True


def test_tampered_confidence_fails_verification():
    p = _partial(conf=0.8)
    p.sign()
    p.confidence = 0.99  # tamper after signing
    assert p.verify() is False


def test_empty_psdt_never_verifies_full():
    t = PSDT()
    assert t.verify_full() is False


def test_full_trace_verifies_when_signed():
    t = PSDT()
    t.add_partial(_partial(stream="reflex"))
    t.add_partial(_partial(stream="planning", intent="plan", eh="def"))
    t.finalize("approve")
    assert t.verify_full() is True


def test_tampered_partial_breaks_full_verification():
    t = PSDT()
    p = _partial(stream="reflex")
    t.add_partial(p)
    t.finalize("approve")
    p.confidence = 0.1  # tamper
    assert t.verify_full() is False


def test_from_ctx_extracts_or_creates():
    t = PSDT()
    t.add_partial(_partial(stream="reflex"))
    ctx = type("Ctx", (), {"psdt": t})()
    assert PSDT.from_ctx(ctx) is t
    assert PSDT.from_ctx(type("Ctx", (), {"psdt": None})()).partials == {}