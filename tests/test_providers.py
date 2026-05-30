"""Smoke tests for paperflow.providers — fast, offline, no credentials."""

from __future__ import annotations

import os

import pytest

from paperflow.providers import (
    HashEmbedding,
    MockLLM,
    build_embedding_provider,
    build_llm_provider,
    load_provider_config,
)
from paperflow.providers.embedding import (
    OllamaEmbedding,
    OpenAIEmbedding,
    SentenceTransformersEmbedding,
    _resize,
)
from paperflow.providers.llm import (
    AnthropicLLM,
    LLMResponse,
    OllamaLLM,
    OpenAILLM,
)


@pytest.mark.unit
def test_load_provider_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "PAPERFLOW_LLM_PROVIDER",
        "PAPERFLOW_LLM_MODEL",
        "PAPERFLOW_EMBED_PROVIDER",
        "PAPERFLOW_EMBED_MODEL",
        "PAPERFLOW_EMBED_DIMENSIONS",
    ]:
        monkeypatch.delenv(var, raising=False)

    config = load_provider_config()
    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4o-mini"
    assert config.embed_provider == "sentence_transformers"
    assert config.embed_model == "BAAI/bge-m3"
    assert config.embed_dimensions == 1024


@pytest.mark.unit
def test_load_provider_config_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "MOCK")
    monkeypatch.setenv("PAPERFLOW_EMBED_PROVIDER", "sentence-transformers")
    config = load_provider_config()
    assert config.llm_provider == "mock"
    assert config.embed_provider == "sentence_transformers"


@pytest.mark.unit
def test_load_provider_config_unknown_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "completely-unknown")
    monkeypatch.setenv("PAPERFLOW_EMBED_PROVIDER", "made-up-backend")
    config = load_provider_config()
    assert config.llm_provider == "openai"
    assert config.embed_provider == "sentence_transformers"


@pytest.mark.unit
def test_describe_format() -> None:
    monkey_env = os.environ.copy()
    try:
        for var in [
            "PAPERFLOW_LLM_PROVIDER",
            "PAPERFLOW_EMBED_PROVIDER",
            "PAPERFLOW_LLM_MODEL",
            "PAPERFLOW_EMBED_MODEL",
            "PAPERFLOW_EMBED_DIMENSIONS",
        ]:
            os.environ.pop(var, None)
        os.environ["PAPERFLOW_LLM_PROVIDER"] = "mock"
        os.environ["PAPERFLOW_EMBED_PROVIDER"] = "hash"
        config = load_provider_config()
        text = config.describe()
        assert "llm=mock:" in text
        assert "embed=hash:" in text
    finally:
        os.environ.clear()
        os.environ.update(monkey_env)


@pytest.mark.unit
def test_mock_llm_is_deterministic() -> None:
    llm = MockLLM()
    a = llm.generate("hello", system="sys")
    b = llm.generate("hello", system="sys")
    c = llm.generate("hello", system="different-sys")
    assert isinstance(a, LLMResponse)
    assert a.text == b.text
    assert a.text != c.text
    assert a.provider == "mock"
    assert a.model == "mock-llm"


@pytest.mark.unit
def test_hash_embedding_is_deterministic_and_normalized() -> None:
    embed = HashEmbedding(dimensions=32)
    v1 = embed.embed("alpha")
    v2 = embed.embed("alpha")
    v3 = embed.embed("beta")
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 32
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.unit
def test_hash_embedding_batch_matches_single() -> None:
    embed = HashEmbedding(dimensions=16)
    batch = embed.embed_batch(["a", "b", "c"])
    assert len(batch) == 3
    assert batch[0] == embed.embed("a")
    assert batch[1] == embed.embed("b")
    assert batch[2] == embed.embed("c")


@pytest.mark.unit
def test_resize_zero_pad_when_smaller() -> None:
    out = _resize([1.0, 2.0], 5)
    assert out == [1.0, 2.0, 0.0, 0.0, 0.0]


@pytest.mark.unit
def test_resize_unit_norm_when_larger() -> None:
    out = _resize([1.0] * 32, 4)
    assert len(out) == 4
    norm = sum(x * x for x in out) ** 0.5
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.unit
def test_resize_passthrough_when_equal() -> None:
    inp = [0.5, 0.5, 0.5, 0.5]
    out = _resize(inp, 4)
    assert out == inp


@pytest.mark.unit
def test_resize_handles_empty() -> None:
    out = _resize([], 4)
    assert out == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.unit
def test_build_llm_falls_back_to_mock_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm = build_llm_provider()
    assert llm.name == "mock"


@pytest.mark.unit
def test_build_llm_falls_back_on_placeholder_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-key-here")
    llm = build_llm_provider()
    assert llm.name == "mock"


@pytest.mark.unit
def test_build_embedding_falls_back_to_hash_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERFLOW_EMBED_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    embed = build_embedding_provider()
    assert embed.name == "hash"


@pytest.mark.unit
def test_build_embedding_explicit_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERFLOW_EMBED_PROVIDER", "hash")
    monkeypatch.setenv("PAPERFLOW_EMBED_DIMENSIONS", "64")
    embed = build_embedding_provider()
    assert embed.name == "hash"
    assert embed.dimensions == 64
    assert len(embed.embed("test")) == 64


@pytest.mark.unit
def test_provider_classes_exposed() -> None:
    assert OpenAILLM.name == "openai"
    assert AnthropicLLM.name == "anthropic"
    assert OllamaLLM.name == "ollama"
    assert OpenAIEmbedding.name == "openai"
    assert SentenceTransformersEmbedding.name == "sentence_transformers"
    assert OllamaEmbedding.name == "ollama"
