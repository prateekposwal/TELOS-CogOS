"""Contract tests for telos/core/contracts/model_provider.py.

Exercises ModelResponse, the ModelProvider abstract interface, the concrete
Ollama/OpenAI/Anthropic provider constructors + name(), and the
RouterProvider's complexity-based dispatch (the only path exercised without a
live network).
"""
import json

import http.client
import pytest

from telos.core.contracts.model_provider import (
    ModelProvider,
    ModelResponse,
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
        captured = {}

        class FakeResponse:
            def read(self):
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
        p = OllamaProvider(model="ollama-test", host="h", port=4567, timeout=2)
        resp = p.ask([{"role": "user", "content": "hi"}], temperature=0.4, max_tokens=16)

        assert resp.content == "hello world"
        assert resp.model == "ollama-test"
        assert resp.latency_ms >= 0.0
        assert captured["host"] == "h"
        assert captured["port"] == 4567
        assert captured["method"] == "POST"
        assert captured["path"] == "/api/chat"
        assert captured["body"]["model"] == "ollama-test"
        assert captured["body"]["stream"] is False
        assert captured["body"]["options"] == {"temperature": 0.4, "num_predict": 16}
        assert captured["closed"] is True


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