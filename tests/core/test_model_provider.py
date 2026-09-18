"""Contract tests for telos/core/contracts/model_provider.py.

Exercises ModelResponse, the ModelProvider abstract interface, the concrete
Ollama/OpenAI/Anthropic provider constructors + name(), and the
RouterProvider's complexity-based dispatch (the only path exercised without a
live network).
"""
import json

import http.client
import pytest

from telos.core.actions.sandbox import EgressRule, NetworkSandbox
from telos.core.contracts.model_provider import (
    ModelProvider,
    ModelResponse,
    ModelProviderError,
    OllamaProvider,
    OpenAIProvider,
    AnthropicProvider,
    RouterProvider,
)


class TestModelResponse:
    def test_defaults(self):
        r = ModelResponse(content="c", model="m", latency_ms=1.0)
        assert r.tokens_in == 0
        assert r.tokens_out == 0
        assert r.metadata == {}

    def test_fields_roundtrip(self):
        r = ModelResponse(
            content="answer", model="m1", latency_ms=12.5,
            tokens_in=3, tokens_out=7, metadata={"k": "v"},
        )
        assert r.content == "answer"
        assert r.model == "m1"
        assert r.latency_ms == 12.5
        assert r.tokens_in == 3
        assert r.tokens_out == 7
        assert r.metadata == {"k": "v"}


class TestModelProviderAbstract:
    def test_abstract_methods(self):
        assert "ask" in ModelProvider.__abstractmethods__
        assert "name" in ModelProvider.__abstractmethods__

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ModelProvider()


class TestOllamaProvider:
    def test_defaults(self):
        p = OllamaProvider()
        assert p._model == "qwen2:0.5b"
        assert p._host == "localhost"
        assert p._port == 11434
        assert p._timeout == 30

    def test_name(self):
        p = OllamaProvider(model="llama3")
        assert p.name() == "ollama/llama3"

    def test_ask_parses_chat_response(self, monkeypatch):
        """Parity: the SAME request leaves through the governed sandbox.

        The provider no longer opens http.client directly; it routes through
        NetworkSandbox, which performs the exact same POST (method, path, body,
        headers) and parses the exact same response. A loopback rule authorizes
        the test endpoint; the socket itself is faked so nothing leaves the box.
        """
        captured = {}

        class FakeResponse:
            status = 200

            def read(self, *args):
                return json.dumps({"message": {"content": "hello world"}}).encode()

        class FakeConnection:
            def __init__(self, host, port, timeout):
                captured["host"] = host
                captured["port"] = port
                captured["timeout"] = timeout

            def request(self, method, path, body, headers):
                captured["method"] = method
                captured["path"] = path
                captured["body"] = json.loads(body)
                captured["headers"] = headers

            def getresponse(self):
                return FakeResponse()

            def close(self):
                captured["closed"] = True

        monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)
        sandbox = NetworkSandbox(rules=[EgressRule(
            host="127.0.0.1", ports=(4567,), routes=("/api/",),
            methods=("POST",))])
        p = OllamaProvider(model="ollama-test", host="127.0.0.1", port=4567,
                           timeout=2, sandbox=sandbox)
        resp = p.ask([{"role": "user", "content": "hi"}], temperature=0.4, max_tokens=16)

        assert resp.content == "hello world"
        assert resp.model == "ollama-test"
        assert resp.latency_ms >= 0.0
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 4567
        assert captured["method"] == "POST"
        assert captured["path"] == "/api/chat"
        assert captured["body"]["model"] == "ollama-test"
        assert captured["body"]["stream"] is False
        assert captured["body"]["options"] == {"temperature": 0.4, "num_predict": 16}
        assert captured["closed"] is True

    def test_unlisted_host_is_blocked_by_the_sandbox_before_any_socket(self):
        """A non-allowlisted provider host is refused (no connection opens)."""
        p = OllamaProvider(host="evil.example.com", port=11434)
        with pytest.raises(ModelProviderError) as exc:
            p.ask([{"role": "user", "content": "hi"}])
        assert "loopback" in str(exc.value) or "egress denied" in str(exc.value)


class TestOpenAIProvider:
    def test_defaults_and_name(self):
        p = OpenAIProvider()
        assert p._model == "gpt-4o"
        assert p.name() == "openai/gpt-4o"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = OpenAIProvider()
        assert p._api_key == "sk-test"

    def test_api_key_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        p = OpenAIProvider(api_key="sk-explicit")
        assert p._api_key == "sk-explicit"


class TestAnthropicProvider:
    def test_defaults_and_name(self):
        p = AnthropicProvider()
        assert p._model == "claude-sonnet-4-20250514"
        assert p.name() == "anthropic/claude-sonnet-4-20250514"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
        p = AnthropicProvider()
        assert p._api_key == "ant-test"


class TestRouterProvider:
    def test_estimate_complexity_short_message(self):
        r = RouterProvider(None, None)
        assert r.estimate_complexity([{"role": "user", "content": "hi"}]) == 0.004

    def test_estimate_complexity_caps_at_1(self):
        r = RouterProvider(None, None)
        # 300 chars -> 0.6; a massive message saturates at 1.0
        assert r.estimate_complexity([{"role": "user", "content": "x" * 300}]) == 0.6
        assert r.estimate_complexity([{"role": "user", "content": "x" * 5000}]) == 1.0

    def test_routes_simple_to_fast(self):
        class FakeProvider(ModelProvider):
            def __init__(self, label):
                self.label = label
                self.calls = 0

            def ask(self, messages, temperature=0.7, max_tokens=256, **kw):
                self.calls += 1
                return ModelResponse(content=self.label, model=self.label, latency_ms=1.0)

            def name(self):
                return self.label

        fast, capable = FakeProvider("fast"), FakeProvider("capable")
        r = RouterProvider(fast, capable, complexity_threshold=0.5)
        resp = r.ask([{"role": "user", "content": "hi"}])
        assert resp.content == "fast"
        assert fast.calls == 1
        assert capable.calls == 0

    def test_routes_complex_to_capable(self):
        class FakeProvider(ModelProvider):
            def __init__(self, label):
                self.label = label
                self.calls = 0

            def ask(self, messages, temperature=0.7, max_tokens=256, **kw):
                self.calls += 1
                return ModelResponse(content=self.label, model=self.label, latency_ms=1.0)

            def name(self):
                return self.label

        fast, capable = FakeProvider("fast"), FakeProvider("capable")
        r = RouterProvider(fast, capable, complexity_threshold=0.5)
        resp = r.ask([{"role": "user", "content": "x" * 300}])
        assert resp.content == "capable"
        assert capable.calls == 1
        assert fast.calls == 0

    def test_name_format(self):
        class FakeProvider(ModelProvider):
            def name(self):
                return "n"

            def ask(self, messages, temperature=0.7, max_tokens=256, **kw):
                return ModelResponse("", "", 0.0)

        r = RouterProvider(FakeProvider(), FakeProvider())
        assert r.name() == "router(fast=n,capable=n)"

class TestGovernedEgressParity:
    """Each cloud provider leaves through NetworkSandbox with identical shape."""

    def _patch(self, monkeypatch, captured, response_json):
        class FakeResponse:
            status = 200

            def read(self, *args):
                return json.dumps(response_json).encode()

        class FakeConnection:
            def __init__(self, host, port, timeout):
                captured["host"] = host
                captured["port"] = port

            def request(self, method, path, body, headers):
                captured["method"] = method
                captured["path"] = path
                captured["body"] = json.loads(body)
                captured["headers"] = headers

            def getresponse(self):
                return FakeResponse()

            def close(self):
                pass

        monkeypatch.setattr(http.client, "HTTPSConnection", FakeConnection)

    def test_anthropic_same_request_via_sandbox(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured,
                    {"content": [{"type": "text", "text": "hi"}],
                     "usage": {"input_tokens": 3, "output_tokens": 2}})
        p = AnthropicProvider(api_key="k")
        r = p.ask([{"role": "system", "content": "sys"},
                   {"role": "user", "content": "yo"}])
        assert r.content == "hi" and r.tokens_in == 3 and r.tokens_out == 2
        assert captured["host"] == "api.anthropic.com"
        assert captured["port"] == 443
        assert captured["path"] == "/v1/messages"
        assert captured["headers"]["x-api-key"] == "k"
        assert captured["body"]["system"] == "sys"

    def test_openai_same_request_via_sandbox(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured,
                    {"choices": [{"message": {"content": "ok"}}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 2}})
        p = OpenAIProvider(api_key="k")
        r = p.ask([{"role": "user", "content": "yo"}])
        assert r.content == "ok" and r.tokens_in == 1 and r.tokens_out == 2
        assert captured["host"] == "api.openai.com"
        assert captured["port"] == 443
        assert captured["path"] == "/v1/chat/completions"
        assert captured["headers"]["Authorization"] == "Bearer k"
