"""
Embedding backend — real learned embeddings for memory retrieval (Phase 2+).

PATTERN (a capability must not be a vocabulary list): the first semantic layer
was a curated synonym lexicon. It works for words someone remembered to add and
fails for everything else — "unseen vocabulary cannot match" is a ceiling no
amount of lexicon editing removes. This backend replaces that ceiling with real
learned embeddings from a local model, while keeping the lexical layer as a
deterministic OFFLINE fallback.

Design rules:
  - OPTIONAL and PLUGGABLE: a missing model / down server must degrade to the
    lexical path, never break retrieval (the pipeline may run headless).
  - DETERMINISTIC when it matters: embeddings are cached per text, so repeated
    retrieval over a fixed corpus is reproducible.
  - LOCAL ONLY: the endpoint is loopback; nothing is sent to a third party
    (TELOS's own egress sandbox treats non-loopback hosts as allowlisted-only).
  - HONEST FAILURE: availability is probed once and recorded; callers can see
    whether a result came from embeddings or the lexical fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Dict, List, Optional, Sequence

from telos.core.actions.sandbox import NetworkSandbox

DEFAULT_HOST = os.environ.get("TELOS_EMBED_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("TELOS_EMBED_PORT", "11434"))
DEFAULT_MODEL = os.environ.get("TELOS_EMBED_MODEL", "nomic-embed-text")
DEFAULT_TIMEOUT = float(os.environ.get("TELOS_EMBED_TIMEOUT", "20"))
EMBED_DIM = 768


class EmbeddingBackend:
    """A cached, loopback-only embedding client with an availability probe.

    The client never raises on a missing model: `available` reports the truth
    and `embed_many` returns None, so callers can fall back.
    """

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST,
                 port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT,
                 enabled: bool = True):
        """Construct the backend and probe availability once.

        Args:
            model: the embedding model name served by the local runtime.
            host: loopback host of the embedding server.
            port: server port.
            timeout: per-request timeout in seconds.
            enabled: when False, never probes or calls (pure offline mode).
        """
        self.model = model
        self.host = host
        self.port = port
        self.timeout = timeout
        self.enabled = bool(enabled)
        self._sandbox = NetworkSandbox(timeout=max(1.0, float(timeout)))
        self._cache: Dict[str, List[float]] = {}
        self._available: Optional[bool] = None

    @property
    def available(self) -> bool:
        """Whether embeddings can be served (probed lazily, cached).

        Returns:
            True when the local model answered a probe successfully.
        """
        if not self.enabled:
            return False
        if self._available is None:
            probe = self._request(["probe"])
            self._available = bool(probe and probe[0])
        return bool(self._available)

    def _request(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        """POST a batch of texts to the local embeddings endpoint.

        Egress goes through the ONE governed NetworkSandbox (loopback is on its
        allowlist), so the embedding client is not a second ungoverned channel:
        the same host/port/route/bounds discipline applies as everywhere else.

        Args:
            texts: the texts to embed.

        Returns:
            A list of vectors, or None on any failure (never raises).
        """
        url = f"http://{self.host}:{self.port}/api/embed"
        body = json.dumps({"model": self.model, "input": list(texts)})
        result = self._sandbox.request("POST", url, body=body)
        if not result.allowed:
            return None
        try:
            data = json.loads(result.body)
        except (ValueError, TypeError):
            return None
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            return None
        return vectors

    def embed_many(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        """Embed texts, using the per-text cache where possible.

        Args:
            texts: the texts to embed.

        Returns:
            A list of vectors aligned with `texts`, or None when embeddings are
            unavailable (caller falls back to lexical retrieval).
        """
        if not self.available:
            return None
        out: List[Optional[List[float]]] = []
        missing: List[str] = []
        for t in texts:
            key = self._key(t)
            if key in self._cache:
                out.append(self._cache[key])
            else:
                out.append(None)
                missing.append(t)
        if missing:
            vectors = self._request(missing)
            if vectors is None:
                return None
            for text, vec in zip(missing, vectors):
                self._cache[self._key(text)] = vec
            idx = 0
            for i, slot in enumerate(out):
                if slot is None and idx < len(missing):
                    # Fill in order: the missing list preserves text order.
                    out[i] = self._cache.get(self._key(missing[idx]))
                    idx += 1
        resolved = [v for v in out]
        if any(v is None for v in resolved):
            return None
        return [v for v in resolved if v is not None]

    def embed(self, text: str) -> Optional[List[float]]:
        """Embed a single text.

        Args:
            text: the text to embed.

        Returns:
            The vector, or None when unavailable.
        """
        many = self.embed_many([text])
        return many[0] if many else None

    @staticmethod
    def _key(text: str) -> str:
        """Cache key for a text (stable across runs).

        Args:
            text: the text.

        Returns:
            A hex digest key.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine_dense(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two dense vectors.

    Args:
        a: first vector.
        b: second vector.

    Returns:
        Cosine similarity in [-1, 1] (0.0 when either vector is degenerate).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# A shared default backend (one probe per process).
_SHARED: Optional[EmbeddingBackend] = None


def shared_backend() -> EmbeddingBackend:
    """Return the process-wide embedding backend.

    Returns:
        The shared EmbeddingBackend instance.
    """
    global _SHARED
    if _SHARED is None:
        _SHARED = EmbeddingBackend()
    return _SHARED


__all__ = [
    "EmbeddingBackend", "cosine_dense", "shared_backend",
    "DEFAULT_MODEL", "EMBED_DIM",
]
