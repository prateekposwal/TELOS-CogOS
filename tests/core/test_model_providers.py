"""
Tests for ModelProvider abstraction + HumanGateway.
"""

from telos.core.contracts.model_provider import (
    OllamaProvider, RouterProvider, ModelResponse,
)
from telos.core.governance.human_gateway import HumanGateway, HumanVerdict


class FakeProvider:
    """Minimal provider for testing that doesn't hit any API."""

    def __init__(self, name="fake/model", content="fake response"):
        self._name = name
        self._content = content

    def ask(self, messages, temperature=0.7, max_tokens=256, **kwargs):
        return ModelResponse(
            content=self._content,
            model=self._name,
            latency_ms=5.0,
            tokens_in=10,
            tokens_out=5,
        )

    def name(self):
        return self._name


def test_fake_provider():
    p = FakeProvider()
    resp = p.ask([{"role": "user", "content": "hi"}])
    assert resp.content == "fake response"
    assert resp.model == "fake/model"
    assert resp.latency_ms == 5.0


def test_router_routes_to_fast_when_simple():
    fast = FakeProvider("fast/model", "fast reply")
    capable = FakeProvider("capable/model", "capable reply")
    router = RouterProvider(fast, capable, complexity_threshold=0.5)

    resp = router.ask([{"role": "user", "content": "hi"}])
    assert resp.content == "fast reply"
    assert "fast" in resp.model


def test_router_routes_to_capable_when_complex():
    fast = FakeProvider("fast/model", "fast reply")
    capable = FakeProvider("capable/model", "capable reply")
    router = RouterProvider(fast, capable, complexity_threshold=0.5)

    long_msg = " ".join(["word"] * 300)
    resp = router.ask([{"role": "system", "content": "long context"},
                       {"role": "user", "content": long_msg}])
    assert resp.content == "capable reply"
    assert "capable" in resp.model


def test_router_name():
    fast = FakeProvider("ollama/llama3")
    capable = FakeProvider("openai/gpt-4o")
    router = RouterProvider(fast, capable)
    name = router.name()
    assert "ollama/llama3" in name
    assert "openai/gpt-4o" in name


def test_human_gateway_auto_approves():
    gw = HumanGateway(mode="auto")
    verdict = gw.review("test_intent", council_signals=[], decision_integrity=0.9)
    assert verdict.approved is True
    assert verdict.reviewer == "auto"


def test_human_gateway_should_review_false_on_auto():
    gw = HumanGateway(mode="auto")
    assert gw.should_review(True, 0.9) is False
    assert gw.should_review(False, 0.1) is False


def test_human_gateway_should_review_true_on_block():
    gw = HumanGateway(mode="webhook", webhook_url="https://example.com/review")
    assert gw.should_review(False, 0.9) is True


def test_human_gateway_should_review_on_low_di():
    gw = HumanGateway(mode="webhook", webhook_url="https://example.com/review",
                      auto_approve_threshold=0.5)
    assert gw.should_review(True, 0.3) is True
    assert gw.should_review(True, 0.8) is False


def test_human_gateway_stats():
    gw = HumanGateway(mode="auto")
    assert gw.stats["total_reviews"] == 0
    gw.review("test", council_signals=[], decision_integrity=0.9)
    assert gw.stats["total_reviews"] == 1
    assert gw.stats["approved"] == 1


def test_human_gateway_callback():
    gw = HumanGateway(mode="auto")
    results = []
    gw.on_review(lambda v, d: results.append(v.approved))
    gw.review("test", council_signals=[], decision_integrity=0.9)
    assert len(results) == 1
    assert results[0] is True


def test_ollama_provider_imports():
    """Verify OllamaProvider can be instantiated (no API call)."""
    p = OllamaProvider(model="test-model")
    assert p.name() == "ollama/test-model"
