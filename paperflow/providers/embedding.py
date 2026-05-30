"""Embedding provider abstraction.

The :class:`EmbeddingProvider` protocol exposes ``embed`` for a single text
and ``embed_batch`` for many. Concrete implementations target OpenAI's
embeddings API, a local ``sentence-transformers`` model, an Ollama embedding
endpoint, and a deterministic hash fallback.
"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable, List, Optional, Protocol

import requests

from .config import ProviderConfig, load_provider_config


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    def embed(self, text: str) -> List[float]: ...

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]: ...


def _resize(vector: List[float], target_dim: int) -> List[float]:
    if not vector:
        return [0.0] * target_dim
    if len(vector) == target_dim:
        return vector
    if len(vector) < target_dim:
        return vector + [0.0] * (target_dim - len(vector))

    bucket = len(vector) / target_dim
    out: List[float] = []
    for index in range(target_dim):
        start = int(index * bucket)
        end = int((index + 1) * bucket) or start + 1
        segment = vector[start:end]
        out.append(sum(segment) / len(segment))
    norm = sum(value * value for value in out) ** 0.5
    if norm > 0:
        out = [value / norm for value in out]
    return out


class OpenAIEmbedding:
    name = "openai"

    def __init__(
        self,
        model: str,
        dimensions: int,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        from openai import OpenAI  # local import keeps dependency optional

        self.model = model
        self.dimensions = dimensions
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]:
        inputs = [text or " " for text in texts]
        kwargs: dict[str, object] = {"model": self.model, "input": inputs}
        if self.model.startswith("text-embedding-3"):
            kwargs["dimensions"] = self.dimensions
        response = self._client.embeddings.create(**kwargs)
        return [_resize(list(item.embedding), self.dimensions) for item in response.data]


class SentenceTransformersEmbedding:
    name = "sentence_transformers"

    def __init__(self, model: str, dimensions: int) -> None:
        from sentence_transformers import SentenceTransformer  # local import

        self.model = model
        self.dimensions = dimensions
        kwargs: dict[str, object] = {}
        if model.lower().startswith(("qwen/", "baai/")):
            kwargs["trust_remote_code"] = True
        self._model = SentenceTransformer(model, **kwargs)

    def embed(self, text: str) -> List[float]:
        vector = self._model.encode(text or " ", normalize_embeddings=True)
        return _resize(list(vector.tolist() if hasattr(vector, "tolist") else vector), self.dimensions)

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]:
        items = [text or " " for text in texts]
        vectors = self._model.encode(items, normalize_embeddings=True, convert_to_numpy=True)
        return [_resize(list(row.tolist()), self.dimensions) for row in vectors]


class OllamaEmbedding:
    name = "ollama"

    def __init__(self, model: str, dimensions: int, base_url: str = "http://localhost:11434", timeout: float = 60.0) -> None:
        self.model = model
        self.dimensions = dimensions
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def embed(self, text: str) -> List[float]:
        response = requests.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self.model, "prompt": text or " "},
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        vector = list(data.get("embedding") or [])
        return _resize(vector, self.dimensions)

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]


class HashEmbedding:
    """Deterministic offline backend.

    Used for tests and when no real provider is configured. Embeddings are
    not semantically meaningful, but they are stable and unit-norm.
    """

    name = "hash"

    def __init__(self, dimensions: int = 768, model: str = "hash") -> None:
        self.model = model
        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        vector: List[float] = []
        for index in range(self.dimensions):
            byte_index = index % len(digest)
            bit = (digest[byte_index] >> (index % 8)) & 1
            vector.append(1.0 if bit else -1.0)
        norm = sum(value * value for value in vector) ** 0.5
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]


def _is_placeholder(value: Optional[str]) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return True
    return any(token in normalized for token in ("your-", "your_", "placeholder", "xxxxx", "replace_me"))


def build_embedding_provider(config: Optional[ProviderConfig] = None) -> EmbeddingProvider:
    """Construct the configured embedding provider, falling back to hash on missing deps."""

    cfg = config or load_provider_config()

    if cfg.embed_provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if _is_placeholder(api_key):
            return HashEmbedding(dimensions=cfg.embed_dimensions)
        base_url = os.environ.get("OPENAI_BASE_URL") or None
        timeout = float(os.environ.get("OPENAI_API_TIMEOUT", "60") or 60)
        return OpenAIEmbedding(
            model=cfg.embed_model,
            dimensions=cfg.embed_dimensions,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    if cfg.embed_provider == "sentence_transformers":
        try:
            return SentenceTransformersEmbedding(model=cfg.embed_model, dimensions=cfg.embed_dimensions)
        except ImportError:
            return HashEmbedding(dimensions=cfg.embed_dimensions)

    if cfg.embed_provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        timeout = float(os.environ.get("OLLAMA_API_TIMEOUT", "60") or 60)
        return OllamaEmbedding(
            model=cfg.embed_model,
            dimensions=cfg.embed_dimensions,
            base_url=base_url,
            timeout=timeout,
        )

    return HashEmbedding(dimensions=cfg.embed_dimensions)


__all__ = [
    "EmbeddingProvider",
    "HashEmbedding",
    "OllamaEmbedding",
    "OpenAIEmbedding",
    "SentenceTransformersEmbedding",
    "build_embedding_provider",
]
