# Quick Start

This guide takes you from a fresh clone to a working PaperFlow install in under
five minutes. By the end, you will have run `paperflow demo` end-to-end with
deterministic offline providers.

## 1. Clone and install

```bash
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow

# Install the CLI + provider abstraction (no heavy ML deps)
pip install -e .
```

If you want everything (OpenAI, Anthropic, sentence-transformers, PDF parsing,
fetchers):

```bash
pip install -e ".[all]"
```

Python ≥ 3.10 is required.

## 2. Run the offline demo

```bash
paperflow demo
```

This forces the bundled mock LLM and hash embedding providers, then exercises
both. You should see deterministic output in a few seconds — no credentials
needed, no network calls. If this works, the install is good.

## 3. Configure providers

```bash
cp .env.example .env
```

Pick one configuration path.

### Production API path

Use an OpenAI-compatible gateway for both the LLM and embeddings:

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

Any OpenAI-compatible gateway works (DashScope, Azure OpenAI, vLLM, etc.) by
setting `OPENAI_BASE_URL`. See [configuration.md](configuration.md) for the
full reference.

### No-download smoke-test path

Use this for install checks and GUI previews:

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

This avoids credentials, API calls, and local model downloads. It is not a
semantic embedding setup, so do not use it to judge recommendation quality.

### Local embedding path

If you want local semantic embeddings and the machine can cache model weights:

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

`BAAI/bge-m3` downloads about 2.3GB on first use. Choose this deliberately; it
should not be the first-run classroom/demo configuration.

## 4. Verify the environment

```bash
paperflow doctor
```

This checks Python version, core imports, runtime directories, `.env` presence,
and provider configuration.

## 5. Initialize the runtime database

```bash
paperflow init
```

This creates:

```text
data/
data/paperflow.db
data/embeddings_cache/
data/exports/
data/wiki/
models/
```

All runtime artifacts under `data/` and `models/` are ignored by Git.

## 6. Create your first user profile (REQUIRED)

PaperFlow keeps **one profile per `user_id`**, and every other command
(`daily`, `read`, `feedback`) reads from it. **You must create a profile
before the first `paperflow daily` call** — otherwise there's no
personalization signal to score against, and `paperflow read` has no push to
read from.

A quick cold start can use a self-description:

```bash
paperflow profile \
  --user-id user_alice \
  --natural-language "I study LLM agents for scientific discovery, literature mining, and automated paper reading."
```

You can enrich the same user with local PDFs, a Google Scholar page, or a
research homepage:

```bash
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf
paperflow profile --user-id user_alice --scholar-url "https://scholar.google.com/citations?user=..."
paperflow profile --user-id user_alice --homepage-url "https://example.edu/~alice"
```

Use `--reset-existing` only when you want to rebuild the profile instead of
merging new signals into it.

Inspect what was bootstrapped:

```bash
python scripts/show_profile.py user_alice
```

## 7. First daily run

```bash
paperflow daily --user-id user_alice --days 1 --output daily_push.txt --dry-run
```

`--dry-run` computes recommendations without sending any push, so you can see
the Top-20 stream and verify scoring before wiring up a notification channel.

## 8. Read selected papers from that push

The daily push lists candidate paper IDs. Pass them straight to `paperflow
read` to get personalized reading reports:

```bash
paperflow read 1 3 7 --user-id user_alice --no-feishu
```

By default `paperflow read` pulls papers from the **latest push** for that
user. Use `--push-id <push_id>` to read from a specific historical push
instead.

If you prefer a local interface for selection and feedback, start:

```bash
paperflow gui
```

The GUI lets you create or select a profile, run/load a daily push, multi-select
papers for reading, mark explicit "not interested" feedback, generate local
Markdown reports, manage must-read anchors, read an arXiv ID or local PDF
directly, manage local research roles, filter feedback history, and search the
local Wiki.

Feedback has the same profile-learning effect across surfaces. A CLI command
such as `paperflow feedback --reply "1 3"`, a GUI selection, and a Feishu/Lark
reply with `1 3` all update the matching user's profile and drift state. See
[feedback-loop.md](feedback-loop.md).

Daily pushes, generated reading reports, explicit feedback, and profile-drift
snapshots are also written into the local PaperFlow Wiki:

```bash
paperflow wiki backfill --user-id user_alice
paperflow wiki topics --user-id user_alice
paperflow wiki stats --user-id user_alice
paperflow wiki search "literature mining" --user-id user_alice
paperflow wiki ask "What have I read about literature mining?" --user-id user_alice
```

To save PDFs, reading-report Markdown, monthly reports, and Topic Index files
directly into an Obsidian vault, point all four export variables at the same
upper-level folder:

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_MONTHLY_REPORT_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_TOPIC_INDEX_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_STORAGE_ROLE_SUBDIR=true
PAPERFLOW_STORAGE_CATEGORY_SUBDIR=true
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

Local exports are role-scoped by default. If `data/roles.json` maps `role1` to
`user_role1`, then `--user-id user_role1` writes under
`role1/pdf/arXiv - May 2026/`, `role1/reading_reports/arXiv - May 2026/`,
`role1/monthly_reports/`, and `role1/topic_index/`. Monthly report and Topic
Index filenames also include the target month, for example
`Topic Index - role1 - 2026-05.md`. If no role name exists, PaperFlow falls
back to the raw `user_id`.
Set `PAPERFLOW_STORAGE_ROLE_SUBDIR=false` or
`PAPERFLOW_STORAGE_CATEGORY_SUBDIR=false` only if you intentionally want a
flatter layout.

Generate the Obsidian monthly summary and Topic Index from local wiki data:

```bash
paperflow wiki monthly --user-id user_alice
```

Without `--month`, PaperFlow exports the current calendar month. Pass
`--month 2026-05` only to regenerate a historical month.

For the local GUI, keep `PAPERFLOW_WRITE_FEISHU=false` unless you explicitly
want reading reports to also create Feishu docs.

Feishu/Lark document export is optional and separate from the GUI and CLI core.
Configure it in [feishu-doc-export.md](feishu-doc-export.md). After that, run
`paperflow read` without `--no-feishu`, or tick "同时尝试写入飞书文档" in the GUI.
To create docs inside a folder, pass the folder token:

```bash
paperflow read 1 --user-id user_alice --folder-id <feishu_folder_token>
```

## 9. (Optional) Feishu/Lark deployment

If you want PaperFlow to push daily cards to a Feishu/Lark group, set up the
webhook server in [feishu-webhook-setup.md](feishu-webhook-setup.md). For most
users, the CLI is enough.

## 10. (Optional) Run the benchmark

```bash
python experiments/benchmark/fetch_benchmark.py \
  --output-dir data/PaperFlow-Bench

python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output data/PaperFlow-Bench/example_predictions.jsonl

paperflow eval \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions data/PaperFlow-Bench/example_predictions.jsonl \
  --output paperflow_eval.json
```

See [experiments/REPRODUCE.md](../experiments/REPRODUCE.md) for full
benchmark and ablation reproduction.

## What's next

- **Browse the full documentation map** — see [README.md](README.md).
- **Customize a profile** — see [configuration.md](configuration.md).
- **Understand feedback learning** — see [feedback-loop.md](feedback-loop.md).
- **Reproduce the paper** — see [reproduce.md](reproduce.md) and the
  [experiments/](../experiments/) directory.
- **Inspect the architecture** — see [architecture.md](architecture.md).
