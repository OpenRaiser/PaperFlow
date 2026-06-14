"""LLM provider abstraction.

The :class:`LLMProvider` protocol exposes synchronous and streaming generation.
Concrete implementations target OpenAI-compatible APIs, Anthropic's API, a
local Ollama server, and a deterministic mock for offline tests.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Iterator, Optional, Protocol

import requests

from .config import ProviderConfig, load_provider_config


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(Protocol):
    """Minimal interface every LLM backend must satisfy."""

    name: str
    model: str

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...

    def stream_generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]: ...


def _chunk_text(text: str, size: int = 24) -> Iterator[str]:
    content = str(text or "")
    for index in range(0, len(content), max(1, int(size))):
        yield content[index : index + size]


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class OpenAILLM:
    name = "openai"

    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None, timeout: float = 60.0) -> None:
        from openai import OpenAI  # local import keeps dependency optional

        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=choice,
            model=self.model,
            provider=self.name,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    def stream_generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            choices = _field(chunk, "choices", []) or []
            if not choices:
                continue
            delta = _field(choices[0], "delta", None)
            text = _field(delta, "content", None) if delta is not None else None
            if text:
                yield str(text)


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None, timeout: float = 60.0) -> None:
        from anthropic import Anthropic  # local import keeps dependency optional

        self.model = model
        self._client = Anthropic(api_key=api_key, base_url=base_url, timeout=timeout)

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        text = "".join(
            block.text  # type: ignore[attr-defined]
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(response.usage, "output_tokens", 0) or 0,
        )

    def stream_generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                if text:
                    yield text


class OllamaLLM:
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        response = requests.post(
            f"{self._base_url}/api/generate",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            text=str(data.get("response") or ""),
            model=self.model,
            provider=self.name,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
        )

    def stream_generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        with requests.post(
            f"{self._base_url}/api/generate",
            json=payload,
            timeout=self._timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                data = json.loads(line)
                text = str(data.get("response") or "")
                if text:
                    yield text
                if data.get("done"):
                    break


class MockLLM:
    """Deterministic offline backend used when no credentials are available.

    Returns a stable hash-derived snippet so call sites can run end-to-end in
    tests without making network calls. The text is not meaningful — it is
    only intended to keep pipelines flowing.
    """

    name = "mock"

    def __init__(self, model: str = "mock-llm") -> None:
        self.model = model

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        digest = hashlib.sha256((system or "").encode("utf-8") + b"||" + prompt.encode("utf-8")).hexdigest()
        text = f"[mock-llm:{digest[:12]}] {prompt[:120]}"
        return LLMResponse(text=text, model=self.model, provider=self.name)

    def stream_generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        yield from _chunk_text(self.generate(prompt, system=system, temperature=temperature, max_tokens=max_tokens).text)


def _is_placeholder(value: Optional[str]) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return True
    return any(token in normalized for token in ("your-", "your_", "placeholder", "xxxxx", "replace_me"))


def build_llm_provider(config: Optional[ProviderConfig] = None) -> LLMProvider:
    """Construct the configured LLM provider, falling back to mock on missing credentials."""

    cfg = config or load_provider_config()

    if cfg.llm_provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if _is_placeholder(api_key):
            return MockLLM()
        base_url = os.environ.get("OPENAI_BASE_URL") or None
        timeout = float(os.environ.get("OPENAI_API_TIMEOUT", "60") or 60)
        return OpenAILLM(model=cfg.llm_model, api_key=api_key, base_url=base_url, timeout=timeout)

    if cfg.llm_provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if _is_placeholder(api_key):
            return MockLLM()
        base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
        timeout = float(os.environ.get("ANTHROPIC_API_TIMEOUT", "60") or 60)
        return AnthropicLLM(model=cfg.llm_model, api_key=api_key, base_url=base_url, timeout=timeout)

    if cfg.llm_provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        timeout = float(os.environ.get("OLLAMA_API_TIMEOUT", "120") or 120)
        return OllamaLLM(model=cfg.llm_model, base_url=base_url, timeout=timeout)

    return MockLLM(model=cfg.llm_model)


__all__ = [
    "AnthropicLLM",
    "LLMProvider",
    "LLMResponse",
    "MockLLM",
    "OllamaLLM",
    "OpenAILLM",
    "build_llm_provider",
]
