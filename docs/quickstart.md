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

The minimum useful configuration:

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_EMBED_PROVIDER=sentence_transformers

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

Any OpenAI-compatible gateway works (DashScope, Azure OpenAI, vLLM, etc.) by
setting `OPENAI_BASE_URL`. See [configuration.md](configuration.md) for the
full reference.

If a credential is missing, providers transparently fall back to mock/hash so
the pipeline still runs end-to-end.

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

- **Customize a profile** — see [configuration.md](configuration.md).
- **Reproduce the paper** — see [reproduce.md](reproduce.md) and the
  [experiments/](../experiments/) directory.
- **Inspect the architecture** — see the architecture section of the top-level
  [README](../README.md).
