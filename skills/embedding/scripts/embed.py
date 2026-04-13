#!/usr/bin/env python3
"""
Embedding service used by ranking and profile updates.

Supported providers:
- openai: real API embeddings, optionally down-projected to the configured size
- dashscope: Alibaba Cloud Bailian (Qwen) embeddings via OpenAI-compatible API
- nscale_api: call Nscale's native /v1/embeddings endpoint
- local / sentence-transformers: free local model embeddings when installed
- hash: deterministic fallback with no external dependency
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

try:
    from huggingface_hub import InferenceClient, get_token

    HUGGINGFACE_HUB_AVAILABLE = True
except ImportError:
    HUGGINGFACE_HUB_AVAILABLE = False
    InferenceClient = None
    get_token = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "embeddings_cache"


def _is_truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_placeholder_openai_key(api_key: Optional[str]) -> bool:
    normalized = str(api_key or "").strip().lower()
    if not normalized:
        return True
    return (
        "your-api-key" in normalized
        or normalized.endswith("-here")
        or normalized == "sk-your-api-key-here"
    )


def _get_first_env_value(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _should_prefer_dashscope_credentials(provider_hint: Optional[str] = None) -> bool:
    hint = str(provider_hint or "").strip().lower()
    if hint in {"dashscope", "aliyun", "bailian"}:
        return True

    base_url = _get_first_env_value("OPENAI_BASE_URL", "DASHSCOPE_BASE_URL").lower()
    return "dashscope.aliyuncs.com" in base_url


def _get_openai_api_key(provider_hint: Optional[str] = None) -> str:
    if _should_prefer_dashscope_credentials(provider_hint):
        return _get_first_env_value("DASHSCOPE_API_KEY", "OPENAI_API_KEY")
    return _get_first_env_value("OPENAI_API_KEY", "DASHSCOPE_API_KEY")


def _get_openai_base_url(provider_hint: Optional[str] = None) -> Optional[str]:
    if _should_prefer_dashscope_credentials(provider_hint):
        base_url = _get_first_env_value("DASHSCOPE_BASE_URL", "OPENAI_BASE_URL")
    else:
        base_url = _get_first_env_value("OPENAI_BASE_URL", "DASHSCOPE_BASE_URL")
    return base_url or None


def _get_openai_timeout(provider_hint: Optional[str] = None) -> float:
    if _should_prefer_dashscope_credentials(provider_hint):
        raw_timeout = _get_first_env_value("DASHSCOPE_API_TIMEOUT", "OPENAI_API_TIMEOUT") or "60"
    else:
        raw_timeout = _get_first_env_value("OPENAI_API_TIMEOUT", "DASHSCOPE_API_TIMEOUT") or "60"
    try:
        return float(raw_timeout)
    except ValueError:
        return 60.0


def _get_openai_embedding_model(provider_hint: Optional[str] = None) -> str:
    if _should_prefer_dashscope_credentials(provider_hint):
        return _get_first_env_value("DASHSCOPE_EMBEDDING_MODEL", "EMBEDDING_MODEL") or "text-embedding-3-small"
    return _get_first_env_value("EMBEDDING_MODEL", "DASHSCOPE_EMBEDDING_MODEL") or "text-embedding-3-small"


def _is_placeholder_hf_token(api_key: Optional[str]) -> bool:
    normalized = str(api_key or "").strip().lower()
    if not normalized:
        return True
    return (
        "your_hf_token" in normalized
        or normalized.endswith("-here")
        or normalized == "hf_xxxxxxxxxxxxxxxxxxxx"
    )


def _is_placeholder_nscale_key(api_key: Optional[str]) -> bool:
    normalized = str(api_key or "").strip().lower()
    if not normalized:
        return True
    return (
        "your_nscale" in normalized
        or normalized.endswith("-here")
        or "service_token" in normalized
        or "api_key" in normalized
    )


def _looks_like_hf_user_token(api_key: Optional[str]) -> bool:
    return str(api_key or "").strip().lower().startswith("hf_")


def _looks_like_auth_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(
        token in message
        for token in (
            "401",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "invalid_request_error",
            "authentication",
            "forbidden",
        )
    )


def _resolve_hf_provider(primary_env_name: str, fallback_env_name: str = "HF_INFERENCE_PROVIDER") -> str:
    primary = (os.environ.get(primary_env_name) or "").strip()
    if primary:
        return primary
    fallback = (os.environ.get(fallback_env_name) or "").strip()
    return fallback or "auto"


def build_paper_text(paper: Dict[str, Any]) -> str:
    """Build the text payload used for paper embeddings."""
    title = str(paper.get("title") or "").strip()
    abstract = str(paper.get("abstract") or paper.get("cleaned_abstract") or "").strip()
    keywords = paper.get("keywords") or []

    blocks = []
    if title:
        blocks.append(title)
    if abstract:
        blocks.append(abstract)
    if keywords:
        blocks.append("Keywords: " + ", ".join(str(keyword).strip() for keyword in keywords if str(keyword).strip()))

    return "\n\n".join(block for block in blocks if block).strip()


def _requires_trust_remote_code(model_name: str) -> bool:
    normalized = str(model_name or "").strip().lower()
    return normalized.startswith("qwen/")


def _resolve_local_model_path() -> Optional[Path]:
    configured = os.environ.get("LOCAL_EMBEDDING_MODEL_PATH", "").strip()
    if not configured:
        return None

    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _flatten_embedding_payload(payload: Any) -> List[float]:
    if hasattr(payload, "tolist"):
        payload = payload.tolist()

    if not isinstance(payload, list):
        return list(payload)

    if not payload:
        return []

    if isinstance(payload[0], list):
        row_count = 0
        pooled = [0.0] * len(payload[0])
        for row in payload:
            if not isinstance(row, list) or not row:
                continue
            pooled = [left + float(right) for left, right in zip(pooled, row)]
            row_count += 1
        if row_count == 0:
            return []
        return [value / row_count for value in pooled]

    return [float(value) for value in payload]


class EmbeddingService:
    """Configurable embedding backend with caching and safe fallbacks."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        cache_dir: Optional[Path] = None,
    ):
        requested_provider = (provider or os.environ.get("EMBEDDING_PROVIDER") or "hash").strip().lower()
        self.dimensions = int(dimensions or os.environ.get("EMBEDDING_DIMENSIONS", "768"))
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.client = None
        self.local_model = None
        self.model_source = None

        if requested_provider in {"openai", "dashscope", "aliyun", "bailian"}:
            self.provider = "openai"
            provider_hint = requested_provider
            self.model = model or _get_openai_embedding_model(provider_hint)
            api_key = _get_openai_api_key(provider_hint)
            if OPENAI_AVAILABLE and not _is_placeholder_openai_key(api_key):
                self.client = OpenAI(
                    api_key=api_key,
                    base_url=_get_openai_base_url(provider_hint),
                    timeout=_get_openai_timeout(provider_hint),
                )
            else:
                self.provider = "hash"
                self.model = "hash"
        elif requested_provider in {"nscale_api", "nscale"}:
            self.provider = "nscale_api"
            self.model = model or os.environ.get("NSCALE_EMBEDDING_MODEL") or os.environ.get("HF_EMBEDDING_MODEL") or "Qwen3-Embedding-8B"
            api_key = (
                os.environ.get("NSCALE_API_KEY")
                or os.environ.get("NSCALE_SERVICE_TOKEN")
                or ""
            )
            if _is_placeholder_nscale_key(api_key):
                api_key = ""
            base_url = (
                os.environ.get("NSCALE_BASE_URL")
                or "https://aiproxy.infaas-amd-dev.glo1.nscale.com"
            ).strip().rstrip("/")
            timeout = float(os.environ.get("NSCALE_API_TIMEOUT", os.environ.get("HF_API_TIMEOUT", "60")))
            if api_key:
                self.client = {
                    "api_key": api_key,
                    "base_url": base_url,
                    "timeout": timeout,
                }
            else:
                self.provider = "hash"
                self.model = "hash"
        elif requested_provider in {"hf_api", "huggingface", "huggingface_api", "hf-inference"}:
            self.provider = "hf_api"
            self.model = model or os.environ.get("HF_EMBEDDING_MODEL") or "Qwen/Qwen3-Embedding-8B"
            api_key = os.environ.get("HF_TOKEN") or os.environ.get("HF_API_KEY") or ""
            if _is_placeholder_hf_token(api_key):
                api_key = ""
            if not api_key and HUGGINGFACE_HUB_AVAILABLE and get_token is not None:
                api_key = get_token() or ""
            provider_name = _resolve_hf_provider("HF_EMBEDDING_PROVIDER")
            timeout = float(os.environ.get("HF_API_TIMEOUT", "60"))
            if provider_name == "auto" and api_key and not _looks_like_hf_user_token(api_key):
                print(
                    "Embedding provider fallback: HF_EMBEDDING_PROVIDER/HF_INFERENCE_PROVIDER is auto, "
                    "but the configured key is not a Hugging Face hf_ token. "
                    "Set HF_EMBEDDING_PROVIDER explicitly or use a Hugging Face token."
                )
                self.provider = "hash"
                self.model = "hash"
            elif HUGGINGFACE_HUB_AVAILABLE and not _is_placeholder_hf_token(api_key):
                self.client = InferenceClient(
                    model=self.model,
                    provider=provider_name,
                    api_key=api_key,
                    timeout=timeout,
                )
            else:
                self.provider = "hash"
                self.model = "hash"
        elif requested_provider in {"local", "sentence-transformers", "sentence_transformers"}:
            self.provider = "local"
            local_model_path = _resolve_local_model_path()
            default_model = model or os.environ.get("LOCAL_EMBEDDING_MODEL") or "sentence-transformers/all-mpnet-base-v2"
            self.model_source = str(local_model_path) if local_model_path and local_model_path.exists() else default_model
            self.model = local_model_path.name if local_model_path and local_model_path.exists() else default_model
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                kwargs: Dict[str, Any] = {}
                if _is_truthy(os.environ.get("LOCAL_EMBEDDING_TRUST_REMOTE_CODE")) or _requires_trust_remote_code(self.model_source or self.model):
                    kwargs["trust_remote_code"] = True
                self.local_model = SentenceTransformer(self.model_source or self.model, **kwargs)
            else:
                self.provider = "hash"
                self.model = "hash"
                self.model_source = "hash"
        else:
            self.provider = "hash"
            self.model = "hash"
            self.model_source = "hash"

    @property
    def descriptor(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimensions}"

    def _normalize_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        return normalized[:8000]

    def _cache_key(self, text: str) -> str:
        payload = f"{self.descriptor}:{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _cache_path(self, text: str) -> Path:
        return self.cache_dir / f"{self._cache_key(text)}.json"

    def _load_cached(self, text: str) -> Optional[List[float]]:
        cache_path = self._cache_path(text)
        if not cache_path.exists():
            return None

        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            return None
        return embedding

    def _save_cached(self, text: str, embedding: List[float]) -> None:
        cache_path = self._cache_path(text)
        payload = {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "embedding": embedding,
        }
        cache_path.write_text(json.dumps(payload), encoding="utf-8")

    def _resize_vector(self, vector: List[float]) -> List[float]:
        if len(vector) == self.dimensions:
            return vector

        if len(vector) < self.dimensions:
            resized = vector + [0.0] * (self.dimensions - len(vector))
        else:
            bucket_size = len(vector) / self.dimensions
            resized = []
            for index in range(self.dimensions):
                start = int(index * bucket_size)
                end = int((index + 1) * bucket_size)
                if end <= start:
                    end = start + 1
                segment = vector[start:end]
                resized.append(sum(segment) / len(segment))

        norm = sum(value * value for value in resized) ** 0.5
        if norm > 0:
            resized = [value / norm for value in resized]
        return resized

    def _get_openai_embedding(self, text: str) -> List[float]:
        kwargs: Dict[str, Any] = {"model": self.model, "input": text}
        if self.model.startswith("text-embedding-3"):
            kwargs["dimensions"] = self.dimensions

        response = self.client.embeddings.create(**kwargs)
        return response.data[0].embedding

    def _get_hf_api_embedding(self, text: str) -> List[float]:
        response = self.client.feature_extraction(text, model=self.model)
        return _flatten_embedding_payload(response)

    def _get_nscale_api_embedding(self, text: str) -> List[float]:
        if not isinstance(self.client, dict):
            raise RuntimeError("Nscale client is not configured")

        response = requests.post(
            f"{self.client['base_url']}/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.client['api_key']}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "model": self.model,
                "input": text,
                "encoding_format": "float",
                "dimensions": None,
                "user": None,
            },
            timeout=float(self.client["timeout"]),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        if not data or not isinstance(data, list):
            raise RuntimeError(f"Unexpected Nscale embeddings payload: {payload}")
        embedding = data[0].get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError(f"Unexpected Nscale embedding item: {data[0]}")
        return [float(value) for value in embedding]

    def _get_local_embedding(self, text: str) -> List[float]:
        vector = self.local_model.encode(text, normalize_embeddings=True)
        return vector.tolist() if hasattr(vector, "tolist") else list(vector)

    def _get_hash_embedding(self, text: str) -> List[float]:
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        vector = []
        for index in range(self.dimensions):
            byte_index = index % 32
            sign = 1 if (hash_bytes[byte_index] & (1 << (index % 8))) else -1
            value = sign * ((hash_bytes[byte_index] >> (index % 8)) & 1)
            vector.append(float(value))

        norm = sum(value * value for value in vector) ** 0.5
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def embed_text(self, text: str) -> List[float]:
        normalized_text = self._normalize_text(text)
        if not normalized_text:
            return [0.0] * self.dimensions

        cached = self._load_cached(normalized_text)
        if cached is not None:
            return cached

        try:
            if self.provider == "openai" and self.client is not None:
                embedding = self._get_openai_embedding(normalized_text)
            elif self.provider == "nscale_api" and self.client is not None:
                embedding = self._get_nscale_api_embedding(normalized_text)
            elif self.provider == "hf_api" and self.client is not None:
                embedding = self._get_hf_api_embedding(normalized_text)
            elif self.provider == "local" and self.local_model is not None:
                embedding = self._get_local_embedding(normalized_text)
            else:
                embedding = self._get_hash_embedding(normalized_text)
        except Exception as exc:
            print(f"Embedding error ({self.provider}:{self.model}): {exc}")
            self.provider = "hash"
            self.model = "hash"
            embedding = self._get_hash_embedding(normalized_text)

        embedding = self._resize_vector(list(embedding))
        self._save_cached(normalized_text, embedding)
        return embedding

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        normalized_texts = [self._normalize_text(text) for text in texts]
        results: List[Optional[List[float]]] = [None] * len(normalized_texts)
        missing_indices = []

        for index, text in enumerate(normalized_texts):
            if not text:
                results[index] = [0.0] * self.dimensions
                continue
            cached = self._load_cached(text)
            if cached is not None:
                results[index] = cached
            else:
                missing_indices.append(index)

        if missing_indices and self.provider == "openai" and self.client is not None:
            try:
                for batch_start in range(0, len(missing_indices), batch_size):
                    batch_indices = missing_indices[batch_start:batch_start + batch_size]
                    batch_texts = [normalized_texts[index] for index in batch_indices]
                    kwargs: Dict[str, Any] = {"model": self.model, "input": batch_texts}
                    if self.model.startswith("text-embedding-3"):
                        kwargs["dimensions"] = self.dimensions
                    response = self.client.embeddings.create(**kwargs)
                    for index, item in zip(batch_indices, response.data):
                        embedding = self._resize_vector(list(item.embedding))
                        results[index] = embedding
                        self._save_cached(normalized_texts[index], embedding)
            except Exception as exc:
                print(f"Batch embedding error ({self.provider}:{self.model}): {exc}")
                if _looks_like_auth_error(exc):
                    print(
                        "Embedding auth failed. Check OPENAI_API_KEY / DASHSCOPE_API_KEY "
                        "and verify the key is valid for the configured DashScope endpoint."
                    )
                self.provider = "hash"
                self.model = "hash"
                for index in missing_indices:
                    results[index] = self._get_hash_embedding(normalized_texts[index])

        for index in missing_indices:
            if results[index] is None:
                results[index] = self.embed_text(normalized_texts[index])

        return [embedding if embedding is not None else [0.0] * self.dimensions for embedding in results]

    def cosine_similarity(self, vector1: List[float], vector2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vector1, vector2))
        norm1 = sum(a * a for a in vector1) ** 0.5
        norm2 = sum(b * b for b in vector2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


_default_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _default_service
    if _default_service is None:
        _default_service = EmbeddingService()
    return _default_service


def embed_text(text: str) -> List[float]:
    return get_embedding_service().embed_text(text)


def embed_batch(texts: List[str]) -> List[List[float]]:
    return get_embedding_service().embed_batch(texts)


def cosine_similarity(vector1: List[float], vector2: List[float]) -> float:
    return get_embedding_service().cosine_similarity(vector1, vector2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Embedding Service")
    parser.add_argument("--text", type=str, help="Text to embed")
    parser.add_argument("--provider", type=str, help="Embedding provider")
    parser.add_argument("--model", type=str, help="Embedding model")
    parser.add_argument("--dimensions", type=int, help="Target vector dimensions")

    args = parser.parse_args()
    service = EmbeddingService(
        provider=args.provider,
        model=args.model,
        dimensions=args.dimensions,
    )

    sample_text = args.text or "A data-driven framework for protein language models."
    embedding = service.embed_text(sample_text)
    print(f"provider={service.provider}")
    print(f"model={service.model}")
    print(f"dimensions={len(embedding)}")
    print(f"descriptor={service.descriptor}")
    print(f"first_10={embedding[:10]}")
