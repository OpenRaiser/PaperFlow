# Provider Backends

PaperFlow's `paperflow.providers` package wraps every LLM and embedding call
behind two protocols. This page documents the supported backends and shows how
to swap between them.

## Why a provider abstraction

- **Reproducibility.** Tests and offline experiments must run without API
  credentials. The deterministic `mock` LLM and `hash` embedding fall back
  automatically when keys are missing or look like placeholders.
- **Cost control.** Switch between OpenAI, Anthropic, and local Ollama
  models without touching any agent code.
- **Latency control.** Use sentence-transformers locally for embeddings while
  keeping a remote LLM for generation.

## Configuration

All provider selection happens through environment variables. Two top-level
knobs:

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
```

Each backend reads its own credentials. See
[configuration.md](configuration.md) for the full table.

Quick check:

```bash
paperflow doctor          # prints the resolved provider config
paperflow demo            # exercises both providers with deterministic input
```

## LLM backends

### OpenAI (`PAPERFLOW_LLM_PROVIDER=openai`)

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini       # default
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                      # any OpenAI-compatible gateway
OPENAI_API_TIMEOUT=60
```

Works with OpenAI proper, Azure OpenAI, DashScope, vLLM gateways, and any
service that speaks the OpenAI Chat Completions API.

### Anthropic (`PAPERFLOW_LLM_PROVIDER=anthropic`)

```env
PAPERFLOW_LLM_PROVIDER=anthropic
PAPERFLOW_LLM_MODEL=claude-haiku-4-5-20251001    # default
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=                   # leave empty for default
ANTHROPIC_API_TIMEOUT=60
```

The Anthropic backend uses the Messages API and concatenates text content
blocks into a single string response.

### Ollama (`PAPERFLOW_LLM_PROVIDER=ollama`)

```env
PAPERFLOW_LLM_PROVIDER=ollama
PAPERFLOW_LLM_MODEL=qwen2.5:7b-instruct           # default
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_TIMEOUT=120
```

Calls `POST /api/generate` with `stream=false`. Make sure the model has been
pulled (`ollama pull qwen2.5:7b-instruct`) before running PaperFlow.

### Mock (`PAPERFLOW_LLM_PROVIDER=mock`)

Used automatically when an API-based provider is configured but credentials are
missing. Returns a deterministic SHA256-derived snippet:

```text
[mock-llm:8019ef425562] <first 120 chars of prompt>
```

Useful for CI, regression tests, and dry-runs where we only care that the
pipeline executes end-to-end.

## Embedding backends

### sentence-transformers (`PAPERFLOW_EMBED_PROVIDER=sentence_transformers`)

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3                 # default
PAPERFLOW_EMBED_DIMENSIONS=1024
```

Default for new installs. Multilingual, runs locally, no API key needed.
Models from the Qwen and BAAI families are loaded with
`trust_remote_code=True` so custom model classes work.

### OpenAI (`PAPERFLOW_EMBED_PROVIDER=openai`)

```env
PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small      # default
PAPERFLOW_EMBED_DIMENSIONS=1536
OPENAI_API_KEY=sk-...
```

When the model name starts with `text-embedding-3`, PaperFlow passes the
`dimensions` parameter so OpenAI's truncation matches your configured size.

### Ollama (`PAPERFLOW_EMBED_PROVIDER=ollama`)

```env
PAPERFLOW_EMBED_PROVIDER=ollama
PAPERFLOW_EMBED_MODEL=nomic-embed-text            # default
PAPERFLOW_EMBED_DIMENSIONS=768
OLLAMA_BASE_URL=http://localhost:11434
```

### Hash (`PAPERFLOW_EMBED_PROVIDER=hash`)

Deterministic SHA256-derived bit-pattern, unit-normalized to the configured
dimension. Used for tests and offline reproduction. Not semantically
meaningful — vectors are stable across runs but encode no real similarity.

## Vector resizing

If a backend returns a vector whose length differs from
`PAPERFLOW_EMBED_DIMENSIONS`, PaperFlow resizes it:

- **Smaller** → zero-pad on the right.
- **Larger** → bucket-average and unit-normalize.

This lets you swap embedding models without invalidating downstream code that
expects a fixed dimension. Note: **the embedding cache keys on content hash
plus model name**, so changing the embedding model effectively invalidates
the cache.

## Programmatic use

```python
from paperflow.providers import (
    load_provider_config,
    build_llm_provider,
    build_embedding_provider,
)

config = load_provider_config()
print(config.describe())
# llm=openai:gpt-4o-mini embed=sentence_transformers:BAAI/bge-m3(1024)

llm = build_llm_provider(config)
embed = build_embedding_provider(config)

response = llm.generate(
    "Summarize this paper:",
    system="You are a concise research assistant.",
    temperature=0.0,
    max_tokens=512,
)
print(response.text, response.prompt_tokens, response.completion_tokens)

vectors = embed.embed_batch(["paper title 1", "paper title 2"])
```

## Adding a new backend

1. Implement the protocol in `paperflow/providers/llm.py` or
   `paperflow/providers/embedding.py`. Keep the heavy SDK import local to the
   class constructor.
2. Add normalization in `paperflow/providers/config.py` so the backend name
   is recognized.
3. Register a default model and dimension if it's an embedding backend.
4. Wire it into `build_llm_provider` / `build_embedding_provider`.

The protocol-based design keeps the surface tiny — typically a 30–60 line
class plus one entry in each of the three places above.
