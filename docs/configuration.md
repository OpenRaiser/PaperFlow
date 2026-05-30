# Configuration

PaperFlow reads configuration from `.env`, YAML/JSON files under `config/`, and
runtime role state under `data/`. This page is the full reference; for a
guided walkthrough, see [quickstart.md](quickstart.md).

## Provider selection

The two knobs most users will touch:

| Variable                    | Default                  | Allowed values                                              |
|-----------------------------|--------------------------|-------------------------------------------------------------|
| `PAPERFLOW_LLM_PROVIDER`    | `openai`                 | `openai` \| `anthropic` \| `ollama` \| `mock`               |
| `PAPERFLOW_LLM_MODEL`       | per-provider default     | any model accepted by the chosen backend                    |
| `PAPERFLOW_EMBED_PROVIDER`  | `sentence_transformers`  | `openai` \| `sentence_transformers` \| `ollama` \| `hash`   |
| `PAPERFLOW_EMBED_MODEL`     | per-provider default     | any model accepted by the chosen backend                    |
| `PAPERFLOW_EMBED_DIMENSIONS`| per-provider default     | integer; controls vector size after resize                  |

Per-provider defaults:

| Provider                | Default LLM model                  | Default embedding model      | Default dim |
|-------------------------|------------------------------------|------------------------------|-------------|
| `openai`                | `gpt-4o-mini`                      | `text-embedding-3-small`     | 1536        |
| `anthropic`             | `claude-haiku-4-5-20251001`        | —                            | —           |
| `ollama`                | `qwen2.5:7b-instruct`              | `nomic-embed-text`           | 768         |
| `sentence_transformers` | —                                  | `BAAI/bge-m3`                | 1024        |
| `mock` / `hash`         | `mock-llm` / `hash`                | `hash`                       | 768         |

If credentials for the configured provider are missing or look like
placeholders (`your-...`, `xxxxx`, etc.), PaperFlow falls back to the
deterministic mock/hash backend so the pipeline still runs end-to-end.

## OpenAI-compatible API

Used when `PAPERFLOW_LLM_PROVIDER=openai` or `PAPERFLOW_EMBED_PROVIDER=openai`.
Any OpenAI-compatible gateway works (OpenAI, DashScope, Azure, vLLM, etc.) by
setting `OPENAI_BASE_URL`.

| Variable               | Purpose                                                |
|------------------------|--------------------------------------------------------|
| `OPENAI_API_KEY`       | API key for the gateway                                |
| `OPENAI_BASE_URL`      | Base URL (leave empty for OpenAI proper)               |
| `OPENAI_API_TIMEOUT`   | Request timeout in seconds (default 60)                |

## Anthropic API

Used when `PAPERFLOW_LLM_PROVIDER=anthropic`.

| Variable                  | Purpose                                              |
|---------------------------|------------------------------------------------------|
| `ANTHROPIC_API_KEY`       | Anthropic API key                                    |
| `ANTHROPIC_BASE_URL`      | Optional custom base URL                             |
| `ANTHROPIC_API_TIMEOUT`   | Request timeout in seconds (default 60)              |

## Ollama (local)

Used when `PAPERFLOW_LLM_PROVIDER=ollama` or `PAPERFLOW_EMBED_PROVIDER=ollama`.

| Variable               | Purpose                                                |
|------------------------|--------------------------------------------------------|
| `OLLAMA_BASE_URL`      | Default `http://localhost:11434`                       |
| `OLLAMA_API_TIMEOUT`   | Request timeout in seconds (default 120)               |

## Optional upstream data sources

| Variable                 | Purpose                                              |
|--------------------------|------------------------------------------------------|
| `IEEE_API_KEY`           | IEEE Xplore API key for journal metadata             |
| `OPENREVIEW_USERNAME`    | OpenReview username (for venue fetching)             |
| `OPENREVIEW_PASSWORD`    | OpenReview password                                  |
| `OPENREVIEW_TOKEN`       | Optional OpenReview API token                        |

## Runtime storage and logging

| Variable                                   | Default                  | Purpose                                  |
|--------------------------------------------|--------------------------|------------------------------------------|
| `DATABASE_PATH`                            | `./data/paperflow.db`    | SQLite database location                 |
| `LOG_LEVEL`                                | `INFO`                   | Python logging level                     |
| `PAPERFLOW_SUPPRESS_HTTP_RETRY_WARNINGS`   | `true`                   | Hide noisy retry warnings                |
| `PAPERFLOW_ALLOW_MOCK_PAPERS`              | `false`                  | Allow mock papers in real pipelines      |

## Interest-drift defaults

These rarely need touching. They control the drift detector that compares
short-window vs long-window interest centroids.

| Variable                                | Default | Purpose                              |
|-----------------------------------------|---------|--------------------------------------|
| `PAPERFLOW_DRIFT_LONG_WINDOW_SIZE`      | 30      | Long-window event count              |
| `PAPERFLOW_DRIFT_LONG_WINDOW_DAYS`      | 60      | Long-window day cap                  |
| `PAPERFLOW_DRIFT_SHORT_WINDOW_SIZE`     | 8       | Short-window event count             |
| `PAPERFLOW_DRIFT_SHORT_WINDOW_DAYS`     | 14      | Short-window day cap                 |
| `PAPERFLOW_DRIFT_THRESHOLD`             | 0.35    | Drift-detection cosine threshold     |
| `PAPERFLOW_DRIFT_RECOVER_THRESHOLD`     | 0.20    | Drift-recovery threshold             |
| `PAPERFLOW_DRIFT_ALPHA_BASE`            | 0.08    | Base learning rate                   |
| `PAPERFLOW_DRIFT_ALPHA_MAX`             | 0.35    | Max learning rate during drift       |
| `PAPERFLOW_TOPIC_DECAY`                 | 0.01    | Per-day topic-weight decay           |
| `PAPERFLOW_AUTHOR_DECAY`                | 0.005   | Per-day author-weight decay          |
| `PAPERFLOW_INSTITUTION_DECAY`           | 0.005   | Per-day institution-weight decay     |

## Feishu / Lark deployment

Only needed if you deploy under `deployments/feishu/`. Plain CLI users can
leave the whole block empty.

| Variable                       | Purpose                                          |
|--------------------------------|--------------------------------------------------|
| `FEISHU_APP_ID`                | Feishu/Lark app id                               |
| `FEISHU_APP_SECRET`            | Feishu/Lark app secret                           |
| `FEISHU_BOT_NAME`              | Display name in generated messages               |
| `FEISHU_USER_ID`               | Default Feishu user_id for push targeting        |
| `FEISHU_CLI_CMD`               | Optional path to `lark-cli` / `lark-cli.cmd`     |
| `FEISHU_VERIFICATION_TOKEN`    | Webhook verification token                       |
| `NGROK_AUTHTOKEN`              | ngrok auth token (for local webhook exposure)    |
| `NGROK_PATH`                   | Optional path to the ngrok binary                |

For full Feishu setup, see [feishu-webhook-setup.md](feishu-webhook-setup.md).

## Role configuration

`config/roles.example.json` is copied to `data/roles.json` on first startup.
Edit `data/roles.json` to add real Feishu chat ids or custom role descriptions:

```json
{
  "roles": {
    "alice": {
      "user_id": "alice",
      "description": "direction: gui agent, web automation, computer vision grounding",
      "feishu_chat_id": ""
    }
  },
  "current_role": "alice"
}
```

## Source configuration

| File                                | Purpose                                       |
|-------------------------------------|-----------------------------------------------|
| `config/conferences.yaml`           | OpenReview venues to track                    |
| `config/journals.yaml`              | Journal feeds (RSS/API) to track              |
| `config/scoring_weights.yaml`       | Per-component scoring weights                 |
| `config/direction_lexicon.py`       | Direction aliases and keyword expansions      |

Change these files when adding new venues, journals, or direction aliases.
