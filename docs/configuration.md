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
| `PAPERFLOW_PDF_DIR`                        | `./data/papers`          | Persistent PDF save directory            |
| `PAPERFLOW_READING_REPORTS_DIR`            | `./data/reading_reports` | Persistent reading-report Markdown directory |
| `PAPERFLOW_STORAGE_MONTHLY_SUBDIR`         | `false`                  | Append `arXiv - May 2026` style subfolders |
| `PAPERFLOW_WRITE_FEISHU`                   | `false`                  | Let local GUI reading reports also create Feishu docs |
| `PAPERFLOW_WIKI_INGEST`                    | `true`                   | Mirror runtime events into the local wiki |
| `PAPERFLOW_WIKI_DIR`                       | `./data/wiki`            | Markdown mirror directory for wiki nodes |
| `PAPERFLOW_MONTHLY_REPORT_DIR`             | `./data/wiki/monthly_reports` | Obsidian-friendly monthly report output directory |
| `PAPERFLOW_TOPIC_INDEX_DIR`                | empty                    | Optional separate Topic Index output directory |

## Obsidian-style local storage

Set the PDF and reading-report directories to any local folder. For example,
both can point to the same monthly Obsidian folder:

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026/arXiv - May 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026/arXiv - May 2026
```

If you prefer to configure only the year-level root and let PaperFlow create
month folders, enable:

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

With monthly subfolders enabled, PaperFlow writes files under names like
`arXiv - May 2026`, based on the paper publish date when available.

To export an Obsidian-friendly monthly reading summary and topic index into a
Daily Note folder, set:

```env
PAPERFLOW_MONTHLY_REPORT_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_TOPIC_INDEX_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026/topic index
```

Then run:

```bash
paperflow wiki monthly --user-id user_alice --month 2026-05
```

This writes `PaperFlow Monthly Report - 2026-05.md` and `Topic Index -
2026-05.md`. You can override the configured directories for one run:

```bash
paperflow wiki monthly \
  --user-id user_alice \
  --month 2026-05 \
  --output-dir "/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026" \
  --topic-index-dir "/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026/topic index"
```

The GUI uses the same variables. In the GUI, the arXiv/PDF fields are input
addresses; generated Markdown reports still go to
`PAPERFLOW_READING_REPORTS_DIR`. See
[../deployments/desktop/README.md](../deployments/desktop/README.md).

## Local PaperFlow Wiki

The wiki is a local memory layer over `data/paperflow.db`. It stores paper,
section, topic, and trajectory nodes, then mirrors them to Markdown files so
they can be inspected with normal editors or Obsidian.

```bash
paperflow wiki init
paperflow wiki backfill --user-id user_alice
paperflow wiki topics --user-id user_alice
paperflow wiki embed --user-id user_alice
paperflow wiki search "graph rag" --user-id user_alice
paperflow wiki ask "What have I read about graph RAG?" --user-id user_alice
```

Set `PAPERFLOW_WIKI_INGEST=false` to turn off automatic ingestion while
keeping the rest of the PaperFlow pipeline unchanged.

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

## Feishu / Lark

These values are only needed if you want PaperFlow to create Feishu/Lark docs
or run the Feishu webhook deployment. Plain local-only users can leave the
whole block empty.

| Variable                       | Purpose                                          |
|--------------------------------|--------------------------------------------------|
| `FEISHU_APP_ID`                | Feishu/Lark app id                               |
| `FEISHU_APP_SECRET`            | Feishu/Lark app secret                           |
| `FEISHU_BOT_NAME`              | Display name in generated messages               |
| `FEISHU_USER_ID`               | Default Feishu user_id for push targeting        |
| `FEISHU_CLI_CMD`               | Optional path to `lark-cli` / `lark-cli.cmd`     |
| `FEISHU_IM_IDENTITY`           | `bot` by default; use `user` only after user auth |
| `FEISHU_VERIFICATION_TOKEN`    | Webhook verification token                       |
| `NGROK_AUTHTOKEN`              | ngrok auth token (for local webhook exposure)    |
| `NGROK_PATH`                   | Optional path to the ngrok binary                |
| `NGROK_DOMAIN`                 | Optional static ngrok domain for stable callbacks |

Reading-report document export and webhook delivery are separate:

- Feishu document export needs Feishu app credentials and `lark-cli`; it does
  not need ngrok. See [feishu-doc-export.md](feishu-doc-export.md).
- Feishu bot webhook / scheduled delivery needs event callbacks and ngrok.
  See [feishu-webhook-setup.md](feishu-webhook-setup.md).
- Unified feedback/profile learning: see [feedback-loop.md](feedback-loop.md).

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
