"""Provider configuration loaded from environment variables.

Environment knobs the CLI and providers honor. Defaults keep the public
quickstart minimal: with only ``PAPERFLOW_LLM_PROVIDER`` and
``PAPERFLOW_EMBED_PROVIDER`` set, the rest fall back to per-provider
defaults. Each provider then reads its own credential / model keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - optional dependency
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved provider selection.

    Attributes track the *user-requested* provider, not the runtime fallback
    (the provider implementations decide whether to fall back to hash / mock
    when credentials are missing).
    """

    llm_provider: str
    llm_model: str
    embed_provider: str
    embed_model: str
    embed_dimensions: int

    def describe(self) -> str:
        return (
            f"llm={self.llm_provider}:{self.llm_model} "
            f"embed={self.embed_provider}:{self.embed_model}({self.embed_dimensions})"
        )


_DEFAULT_LLM_MODEL: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": "qwen2.5:7b-instruct",
    "mock": "mock-llm",
}

_DEFAULT_EMBED_MODEL: dict[str, str] = {
    "openai": "text-embedding-3-small",
    "ollama": "nomic-embed-text",
    "sentence_transformers": "BAAI/bge-m3",
    "hash": "hash",
}

_DEFAULT_EMBED_DIM: dict[str, int] = {
    "openai": 1536,
    "ollama": 768,
    "sentence_transformers": 1024,
    "hash": 768,
}


def _normalize_llm_provider(raw: Optional[str]) -> str:
    value = (raw or "").strip().lower()
    if value in {"", "auto"}:
        return "openai"
    if value in {"openai", "anthropic", "ollama", "mock"}:
        return value
    return "openai"


def _normalize_embed_provider(raw: Optional[str]) -> str:
    value = (raw or "").strip().lower()
    if value in {"", "auto"}:
        return "sentence_transformers"
    if value in {"openai", "ollama", "hash"}:
        return value
    if value in {"sentence_transformers", "sentence-transformers", "local", "st"}:
        return "sentence_transformers"
    return "sentence_transformers"


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def load_provider_config() -> ProviderConfig:
    """Read provider settings from the environment.

    The function is pure with respect to the current environment — it is
    fine to call repeatedly, and tests can monkeypatch ``os.environ``.
    """

    llm_provider = _normalize_llm_provider(
        _first_env("PAPERFLOW_LLM_PROVIDER", "LLM_PARSER_PROVIDER")
    )
    llm_model = (
        _first_env(
            "PAPERFLOW_LLM_MODEL",
            "LLM_PARSER_OPENAI_MODEL",
            "DASHSCOPE_LLM_MODEL",
            "HF_LLM_MODEL",
        )
        or _DEFAULT_LLM_MODEL[llm_provider]
    )

    embed_provider = _normalize_embed_provider(
        _first_env("PAPERFLOW_EMBED_PROVIDER", "EMBEDDING_PROVIDER")
    )
    embed_model = (
        _first_env("PAPERFLOW_EMBED_MODEL", "EMBEDDING_MODEL")
        or _DEFAULT_EMBED_MODEL[embed_provider]
    )

    raw_dim = os.environ.get("PAPERFLOW_EMBED_DIMENSIONS", "").strip()
    if raw_dim:
        try:
            embed_dimensions = int(raw_dim)
        except ValueError:
            embed_dimensions = _DEFAULT_EMBED_DIM[embed_provider]
    else:
        embed_dimensions = _DEFAULT_EMBED_DIM[embed_provider]

    return ProviderConfig(
        llm_provider=llm_provider,
        llm_model=llm_model,
        embed_provider=embed_provider,
        embed_model=embed_model,
        embed_dimensions=embed_dimensions,
    )
