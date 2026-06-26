"""Smoke tests for paperflow.providers — fast, offline, no credentials."""

from __future__ import annotations

import os
import sys

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
    _field,
)


@pytest.mark.unit
def test_load_provider_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "PAPERFLOW_LLM_PROVIDER",
        "PAPERFLOW_LLM_MODEL",
        "PAPERFLOW_EMBED_PROVIDER",
        "PAPERFLOW_EMBED_MODEL",
        "PAPERFLOW_EMBED_DIMENSIONS",
        "LLM_PARSER_PROVIDER",
        "LLM_PARSER_OPENAI_MODEL",
        "DASHSCOPE_LLM_MODEL",
        "HF_LLM_MODEL",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
    ]:
        monkeypatch.delenv(var, raising=False)

    config = load_provider_config()
    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4o-mini"
    assert config.embed_provider == "hash"
    assert config.embed_model == "hash"
    assert config.embed_dimensions == 768


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
    assert config.embed_provider == "hash"


@pytest.mark.unit
def test_load_provider_config_accepts_legacy_env_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "PAPERFLOW_LLM_PROVIDER",
        "PAPERFLOW_LLM_MODEL",
        "PAPERFLOW_EMBED_PROVIDER",
        "PAPERFLOW_EMBED_MODEL",
        "PAPERFLOW_EMBED_DIMENSIONS",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "openai")
    monkeypatch.setenv("LLM_PARSER_OPENAI_MODEL", "gemini-3-flash-preview")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")

    config = load_provider_config()

    assert config.llm_provider == "openai"
    assert config.llm_model == "gemini-3-flash-preview"
    assert config.embed_provider == "openai"
    assert config.embed_model == "Qwen/Qwen3-Embedding-8B"


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
def test_mock_llm_stream_matches_sync_text() -> None:
    llm = MockLLM()
    prompt = "hello " * 20
    sync = llm.generate(prompt, system="sys")
    chunks = list(llm.stream_generate(prompt, system="sys"))

    assert chunks
    assert "".join(chunks) == sync.text


@pytest.mark.unit
def test_openai_stream_field_helper_accepts_dict_and_objects() -> None:
    class Obj:
        content = "object-content"

    assert _field({"content": "dict-content"}, "content") == "dict-content"
    assert _field(Obj(), "content") == "object-content"
    assert _field({}, "missing", "fallback") == "fallback"


@pytest.mark.unit
def test_openai_llm_retries_high_after_max_reasoning_effort_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeUsage:
        prompt_tokens = 3
        completion_tokens = 5

    class FakeMessage:
        content = "ok"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = FakeUsage()

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            if kwargs.get("reasoning_effort") == "max":
                raise ValueError("unsupported parameter: reasoning_effort")
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    class FakeOpenAIModule:
        @staticmethod
        def OpenAI(**_kwargs):
            return FakeClient()

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule)
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)

    llm = OpenAILLM(model="gpt-test", api_key="sk-test")
    response = llm.generate("hello", system="sys")

    assert response.text == "ok"
    assert calls[0]["reasoning_effort"] == "max"
    assert calls[1]["reasoning_effort"] == "high"


@pytest.mark.unit
def test_openai_llm_retries_without_reasoning_effort_after_max_and_high_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeMessage:
        content = "ok"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = None

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            if "reasoning_effort" in kwargs:
                raise ValueError("unsupported parameter: reasoning_effort")
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    class FakeOpenAIModule:
        @staticmethod
        def OpenAI(**_kwargs):
            return FakeClient()

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule)
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)

    llm = OpenAILLM(model="gpt-test", api_key="sk-test")
    response = llm.generate("hello")

    assert response.text == "ok"
    assert calls[0]["reasoning_effort"] == "max"
    assert calls[1]["reasoning_effort"] == "high"
    assert "reasoning_effort" not in calls[2]


@pytest.mark.unit
def test_openai_llm_can_disable_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeMessage:
        content = "ok"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = None

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    class FakeOpenAIModule:
        @staticmethod
        def OpenAI(**_kwargs):
            return FakeClient()

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule)
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "default")

    llm = OpenAILLM(model="gpt-test", api_key="sk-test")
    llm.generate("hello")

    assert len(calls) == 1
    assert "reasoning_effort" not in calls[0]


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
