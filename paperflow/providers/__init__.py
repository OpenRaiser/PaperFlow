"""Provider abstractions for LLM and embedding backends.

PaperFlow keeps generation (``LLMProvider``) and embedding
(``EmbeddingProvider``) behind a single seam so the CLI, agents, and
experiments can switch between hosted APIs (OpenAI, Anthropic) and local
models (Ollama, sentence-transformers) without touching call sites.
"""

from __future__ import annotations

from .config import ProviderConfig, load_provider_config
from .embedding import EmbeddingProvider, HashEmbedding, build_embedding_provider
from .llm import LLMProvider, LLMResponse, MockLLM, build_llm_provider

__all__ = [
    "EmbeddingProvider",
    "HashEmbedding",
    "LLMProvider",
    "LLMResponse",
    "MockLLM",
    "ProviderConfig",
    "build_embedding_provider",
    "build_llm_provider",
    "load_provider_config",
]
