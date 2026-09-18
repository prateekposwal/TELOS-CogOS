"""
ModelProvider — Multi-model orchestration abstraction.

Pipeline can speak through any provider: local (Ollama), cloud (OpenAI,
Anthropic), or routed by cost/complexity. The Pipeline itself stays
stateless — this is an external observer service.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger('telos_model')


class ModelProviderError(RuntimeError):
    """Raised when a provider request cannot be performed.

    A network request leaves the process ONLY through the governed
    :class:`~telos.core.actions.sandbox.NetworkSandbox` (host/port/route
    allowlist + bounded payloads). A sandbox refusal, a transport failure, or an
    unparseable response all surface here instead of a raw socket exception.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _sandbox_post(sandbox, url: str, payload: str,
                  headers: Optional[Dict[str, str]]):
    """Perform one POST through the governed egress sandbox.

    Args:
        sandbox: the NetworkSandbox that owns this provider's egress.
        url: the absolute request URL.
        payload: the JSON request body.
        headers: request headers (Authorization etc.).

    Returns:
        (parsed_json_dict, duration_ms).

    Raises:
        ModelProviderError: when the sandbox refuses/fails the request or the
            response body is not valid JSON.
    """
    result = sandbox.request("POST", url, body=payload, headers=headers)
    if not result.allowed:
        raise ModelProviderError(
            result.blocked_reason or "network request was blocked")
    try:
        return json.loads(result.body), result.duration_ms
    except (ValueError, TypeError) as e:
        raise ModelProviderError(f"invalid provider response: {e}")


@dataclass
class ModelResponse:
    content: str
    model: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    """Abstract interface for any LLM provider."""

    @abstractmethod
    def ask(self, messages: List[Dict[str, str]],
            temperature: float = 0.7, max_tokens: int = 256,
            **kwargs) -> ModelResponse:
        """Send a chat completion request and return the response.
            Args:
                messages: the messages argument for this call.
                temperature: the temperature argument for this call.
                max_tokens: the max_tokens argument for this call.
        """

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider+model identifier."""


class OllamaProvider(ModelProvider):
    """Local LLM via Ollama HTTP API."""

    def __init__(self, model: str = "qwen2:0.5b",
                 host: str = "localhost", port: int = 11434,
                 timeout: int = 30, sandbox=None):
        self._model = model
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sandbox = sandbox

    def _egress(self):
        """The governed egress channel (lazy; default allowlist)."""
        if self._sandbox is None:
            from telos.core.actions.sandbox import NetworkSandbox
            self._sandbox = NetworkSandbox(timeout=self._timeout)
        return self._sandbox

    def ask(self, messages: List[Dict[str, str]],
            temperature: float = 0.7, max_tokens: int = 256,
            **kwargs) -> ModelResponse:
        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature,
                        "num_predict": max_tokens},
        })
        data, latency = _sandbox_post(
            self._egress(),
            f"http://{self._host}:{self._port}/api/chat",
            payload,
            {"Content-Type": "application/json"},
        )
        content = data.get("message", {}).get("content", "")
        return ModelResponse(
            content=content,
            model=self._model,
            latency_ms=round(latency, 1),
        )

    def name(self) -> str:
        return f"ollama/{self._model}"


class OpenAIProvider(ModelProvider):
    """Cloud LLM via OpenAI-compatible API."""

    def __init__(self, model: str = "gpt-4o",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 timeout: int = 60, sandbox=None):
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._timeout = timeout
        self._sandbox = sandbox

    def _egress(self):
        """The governed egress channel (lazy; default allowlist)."""
        if self._sandbox is None:
            from telos.core.actions.sandbox import NetworkSandbox
            self._sandbox = NetworkSandbox(timeout=self._timeout)
        return self._sandbox

    def ask(self, messages: List[Dict[str, str]],
            temperature: float = 0.7, max_tokens: int = 256,
            **kwargs) -> ModelResponse:
        host = "api.openai.com"
        path = "/v1/chat/completions"
        scheme = "https"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })

        if self._base_url:
            parsed = urllib.parse.urlparse(self._base_url)
            if parsed.netloc:
                host = parsed.netloc
            if parsed.path:
                path = parsed.path.rstrip("/") + "/chat/completions"
            scheme = "https" if parsed.scheme in ("https", "") else "http"
        port = 443 if scheme == "https" else 80
        url = f"{scheme}://{host}:{port}{path}"

        data, latency = _sandbox_post(self._egress(), url, payload, headers)
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return ModelResponse(
            content=content,
            model=self._model,
            latency_ms=round(latency, 1),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )

    def name(self) -> str:
        return f"openai/{self._model}"


class AnthropicProvider(ModelProvider):
    """Cloud LLM via Anthropic API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 api_key: Optional[str] = None,
                 timeout: int = 60, sandbox=None):
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._timeout = timeout
        self._sandbox = sandbox

    def _egress(self):
        """The governed egress channel (lazy; default allowlist)."""
        if self._sandbox is None:
            from telos.core.actions.sandbox import NetworkSandbox
            self._sandbox = NetworkSandbox(timeout=self._timeout)
        return self._sandbox

    def ask(self, messages: List[Dict[str, str]],
            temperature: float = 0.7, max_tokens: int = 256,
            **kwargs) -> ModelResponse:
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                chat_messages.append({"role": m["role"],
                                      "content": m["content"]})

        payload = {
            "model": self._model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }
        data, latency = _sandbox_post(
            self._egress(),
            "https://api.anthropic.com:443/v1/messages",
            json.dumps(payload),
            headers,
        )
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        usage = data.get("usage", {})
        return ModelResponse(
            content=content,
            model=self._model,
            latency_ms=round(latency, 1),
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
        )

    def name(self) -> str:
        return f"anthropic/{self._model}"


class RouterProvider(ModelProvider):
    """Routes requests to sub-providers by complexity.

    Simple intents → cheap/fast model (Ollama)
    Complex reasoning → capable model (GPT-4o, Claude)
    """

    def __init__(self,
                 fast_provider: ModelProvider,
                 capable_provider: ModelProvider,
                 complexity_threshold: float = 0.5):
        self._fast = fast_provider
        self._capable = capable_provider
        self._threshold = complexity_threshold

    def estimate_complexity(self, messages: List[Dict[str, str]]) -> float:
        """Heuristic: longer user messages + system prompts = more complex."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return min(1.0, total_chars / 500)

    def ask(self, messages: List[Dict[str, str]],
            temperature: float = 0.7, max_tokens: int = 256,
            **kwargs) -> ModelResponse:
        complexity = self.estimate_complexity(messages)
        if complexity < self._threshold:
            logger.debug(f"Router: fast path (complexity={complexity:.2f})")
            return self._fast.ask(messages, temperature, max_tokens,
                                  **kwargs)
        logger.debug(f"Router: capable path (complexity={complexity:.2f})")
        return self._capable.ask(messages, temperature, max_tokens,
                                 **kwargs)

    def name(self) -> str:
        return f"router(fast={self._fast.name()},capable={self._capable.name()})"
