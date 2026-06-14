<div align="center">

# PaperFlow

**Dynamic personalized scientific-paper recommendation, reading, and reporting.**

PaperFlow turns daily paper discovery into a closed-loop research workflow:
build a profile, rank today's papers, read the useful ones, collect feedback,
and adapt tomorrow's recommendations.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/downloads/)
[![Package](https://img.shields.io/badge/package-paperflow-2E7D32.svg)](pyproject.toml)
[![HF Dataset](https://img.shields.io/badge/HF%20Dataset-OpenRaiser%2FPaperFlow-FFD21E.svg)](https://huggingface.co/datasets/OpenRaiser/PaperFlow)
[![License: MIT](https://img.shields.io/badge/License-MIT-111111.svg)](LICENSE)

![Personalized Recommendation](https://img.shields.io/badge/personalized-recommendation-2E7D32.svg)
![Scientific Reading](https://img.shields.io/badge/scientific-reading-1565C0.svg)
![Daily Digest](https://img.shields.io/badge/daily-paper%20digest-F9A825.svg)
![Feedback Learning](https://img.shields.io/badge/feedback-learning-6A5ACD.svg)
![Interest Drift](https://img.shields.io/badge/interest-drift-00897B.svg)
![Feishu/Lark](https://img.shields.io/badge/Feishu%2FLark-bot-00A1E9.svg)

[Quick Start](#quick-start) | [Desktop Preview](#desktop-preview) | [Local GUI](#local-gui) |
[GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[CLI Usage](#cli-usage) |
[Feedback Loop](docs/feedback-loop.md) |
[Feishu/Lark Bot](#feishu--lark-bot) |
[PaperFlow-Bench](#paperflow-bench) | [Reproduce](experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="PaperFlow personalized scientific reading banner" width="100%">

</div>

---

## Current Release

This first public release is a **CLI + local browser GUI + optional
Feishu/Lark bot** version. You can run PaperFlow entirely from the terminal,
open a local GUI for interactive paper selection, or keep the Feishu/Lark
webhook server alive for scheduled chat pushes.

<table>
  <tr>
    <td><b>Input</b></td>
    <td>Research profiles, papers, PDFs, homepages, Google Scholar pages</td>
  </tr>
  <tr>
    <td><b>Output</b></td>
    <td>Daily paper digests, reading reports, weekly profile reports</td>
  </tr>
  <tr>
    <td><b>Runtime</b></td>
    <td>Local Python CLI, local browser GUI, SQLite, optional Feishu/Lark webhook + ngrok</td>
  </tr>
  <tr>
    <td><b>Benchmark</b></td>
    <td>PaperFlow-Bench on HuggingFace, with public evaluation scripts</td>
  </tr>
</table>

## Desktop Preview

PaperFlow now ships with an offline-first desktop browser GUI. It uses the same
local SQLite state and backend workflows as the CLI, so the UI is not a static
mock: paper pulls, feedback, reading reports, Wiki graph updates, and settings
all route through the local backend.

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="PaperFlow offline desktop workflow demo" width="92%">
</div>

<br>

<details>
<summary>View desktop screenshots</summary>

<table>
  <tr>
    <td width="50%">
      <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="PaperFlow daily paper recommendation stream">
      <br><b>Daily paper stream</b><br>
      Date-aware pulls, source filters, candidate metrics, paper actions, and backend task state.
    </td>
    <td width="50%">
      <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="PaperFlow knowledge Wiki graph">
      <br><b>Knowledge Wiki graph</b><br>
      Backend-derived paper, topic, method, profile, and citation relationships.
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="PaperFlow cited local Wiki question answering">
      <br><b>Cited Wiki Q&A</b><br>
      Streamed answers with clickable reference markers and source cards.
    </td>
    <td width="50%">
      <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="PaperFlow local settings and source configuration">
      <br><b>Local settings</b><br>
      Provider keys, storage paths, paper-source modes, conference access, and export controls.
    </td>
  </tr>
</table>

</details>

### Product Framework

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="PaperFlow product framework diagram" width="100%">

The desktop loop is intentionally local: profile state, paper pushes, feedback,
reading reports, and Wiki nodes stay on disk unless you explicitly enable
external providers or Feishu/Lark export.

## Why PaperFlow

Scientific-paper recommendation is not a one-shot ranking problem. Real
researchers ask a moving question: **what should I read today, and how should
the system adapt tomorrow?**

| Traditional paper alerts | PaperFlow |
| --- | --- |
| Static keyword or profile matching | Structured profile with feedback updates |
| Same feed every day | Date-specific candidate pools and daily digest budget |
| Recommendation only | Recommendation + reading report + feedback loop |
| No explicit drift handling | Short-term and long-term interest drift modeling |
| Hard to reproduce longitudinally | Public PaperFlow-Bench episodes and evaluator |

## Core Capabilities

| Capability | What it does |
| --- | --- |
| Profile bootstrapping | Builds scholarly profiles from text, PDFs, homepages, or Google Scholar pages |
| Daily recommendation | Fetches arXiv, OpenReview, and journal papers, then ranks a personalized daily digest |
| Reading reports | Generates personalized paper reports from metadata and PDF content |
| Feedback learning | Updates the same profile from CLI, GUI, Feishu/Lark, selected, skipped, read, and natural-language feedback |
| Local research Wiki | Ingests paper pushes, reports, citations, feedback, and profile signals into a queryable local graph |
| Cited Wiki Q&A | Answers with local evidence when retrieval is needed, supports clickable citations and explicit `@`-style references |
| Offline desktop GUI | Provides a local UI for daily pulls, feedback, report reading, Wiki graph inspection, Q&A, and settings |
| Drift adaptation | Tracks short-window vs long-window interest movement across days |
| Feishu/Lark bot | Sends daily pushes and weekly reports; routes chat feedback and PDF requests |
| Benchmark tooling | Packages, downloads, predicts, and evaluates PaperFlow-Bench submissions |

## Quick Start

PaperFlow's daily flow has five steps. Steps 1-3 only run once; steps 4-5
become your daily routine.

```bash
# 1. Install
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # full install (or `pip install -e .` for the minimal CLI)

# 2. Configure providers (start with no-download settings; see below)
cp .env.example .env
# edit .env to set PAPERFLOW_LLM_PROVIDER and, for production, an embedding backend

# 3. Initialize runtime + create your user profile (REQUIRED)
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. Daily push (run every morning, or as often as you like)
paperflow daily --user-id user_alice

# 5. Read selected papers (paper IDs come from the latest daily push)
paperflow read 1 3 7 --user-id user_alice

# Optional: use the local browser GUI for steps 4-5
paperflow gui
```

> **Step 3 is mandatory.** `paperflow daily / read / feedback` all read the
> profile created by `paperflow profile`. Skipping it means there's no
> personalization signal to score against, so `paperflow read` has no push
> to read from. See [Initialize a User Profile](#initialize-a-user-profile)
> below for the four bootstrap methods (text / PDF / Google Scholar / homepage).

### Offline smoke test (no API keys)

```bash
paperflow demo
```

The demo uses deterministic mock/hash providers, so it does not need API keys
or network access. Use it to confirm the install before configuring real
providers.

## Configure Providers

Copy the environment template:

```bash
cp .env.example .env
```

Use the `PAPERFLOW_*` variables as the canonical configuration surface. A
fresh install defaults to no-download embeddings so `paperflow demo` and setup
checks are quick, but real recommendation quality needs a semantic embedding
backend.

### Option A: recommended production setup

Use one OpenAI-compatible gateway for both generation and embeddings:

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

OpenAI-compatible gateways are supported through `OPENAI_BASE_URL`, including
OpenAI, DashScope, Azure OpenAI, vLLM, and similar services. If credentials are
missing or still look like placeholders, PaperFlow falls back to mock/hash
providers where possible so local workflows remain testable.

### Option B: no-download smoke test

Use this for install checks, GUI demos, or classrooms where downloading model
weights is not acceptable:

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

This mode is deterministic and fast, but the hash vectors do not encode real
semantic similarity. It is not the recommended setting for evaluating
recommendation quality.

### Option C: high-quality local embeddings

Use this only when the machine is allowed to download and cache local model
weights:

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

This local mode needs no embedding API key, but the first run downloads the
model weights. `BAAI/bge-m3` is about 2.3GB, so do not use it for quick
classroom demos or first-run installation checks.

After changing providers, run:

```bash
paperflow doctor
```

`paperflow doctor` prints the resolved provider configuration. Runtime data is
stored under `data/` and is ignored by Git.

## Initialize a User Profile

PaperFlow keeps **one profile per `user_id`**, and every other command
(`daily`, `read`, `feedback`) reads from that profile. **You must create at
least one profile before the first daily run** — otherwise `paperflow daily`
has nothing to score against and `paperflow read` has no push to read from.

You can bootstrap a profile from any of these four sources, or combine them:

```bash
# (a) Self-description in natural language (fastest)
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) One or more papers you have written or care about
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) A Google Scholar profile (PaperFlow scrapes the public page)
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) A personal lab or homepage
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

Repeated `paperflow profile` calls **merge** new signals into the existing
profile by default. Use `--reset-existing` only when you want to rebuild it
from scratch.

Inspect the resulting profile any time with:

```bash
python scripts/show_profile.py user_alice
```

## Local GUI

Start the local browser GUI with:

```bash
paperflow gui
```

To preview the interface without installing PaperFlow, open the GitHub Pages
mock-data preview:
[PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1).

The GUI uses the same local SQLite database as the CLI. It is designed for the
real daily workflow, not a standalone mock:

- select a user profile and inspect the profile-derived direction summary
- pull papers for today's date, or intentionally fetch a previous date window
- keep long-running daily pulls in backend task state while the UI polls status
- mark papers as precision-read, not interested, or later
- submit feedback and update the local profile/Wiki signal path
- generate or reopen reading reports from paper cards
- inspect the backend-derived Wiki graph and search local knowledge nodes
- ask questions over the local Wiki with clickable references
- configure providers, source modes, storage paths, and export behavior

The desktop GUI does not run background schedules. Scheduled Feishu/Lark
delivery still uses `deployments/feishu/`.

Useful options:

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

Detailed GUI notes are in
[deployments/desktop/README.md](deployments/desktop/README.md).

## CLI Usage

```bash
paperflow --help
```

| Command | Purpose |
| --- | --- |
| `paperflow init` | Create local runtime directories and SQLite tables |
| `paperflow doctor` | Check dependencies, credentials, and runtime paths |
| `paperflow demo` | Run an offline provider demo |
| `paperflow profile` | Create or update a user profile from text, PDFs, Scholar, or homepage data |
| `paperflow daily` | Generate a daily personalized paper push |
| `paperflow read` | Generate a personalized reading report |
| `paperflow wiki` | List, search, and inspect the local reading wiki |
| `paperflow feedback` | Record feedback for a previous push |
| `paperflow gui` | Start the local browser GUI |
| `paperflow eval` | Evaluate PaperFlow-Bench predictions |

Generate a daily recommendation card without sending it:

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run
```

Generate reading reports from paper IDs shown in a previous push:

```bash
paperflow read 1 3 7 --user-id user_role1 --no-feishu
```

By default, `paperflow read` uses that user's latest push in
`data/paperflow.db`. To read from a specific previous push:

```bash
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

Daily pushes, reading reports, feedback signals, and profile-drift snapshots
are also ingested into the local PaperFlow Wiki. Inspect it:

```bash
paperflow wiki backfill --user-id user_role1
paperflow wiki topics --user-id user_role1
paperflow wiki stats --user-id user_role1
paperflow wiki search "graph rag" --user-id user_role1
paperflow wiki ask "What have I read about graph RAG?" --user-id user_role1
```

PDFs, reading-report Markdown, monthly reports, and Topic Index files can be
saved directly into an Obsidian vault. Point all four export variables at the
same upper-level folder:

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
`user_role1`, then `--user-id user_role1` writes these folders:
`role1/pdf/arXiv - May 2026/`, `role1/reading_reports/arXiv - May 2026/`,
`role1/monthly_reports/`, and `role1/topic_index/`. Monthly report and Topic
Index filenames also include the target month, for example
`PaperFlow Monthly Report - role1 - 2026-05.md`.
Set `PAPERFLOW_STORAGE_ROLE_SUBDIR=false` or
`PAPERFLOW_STORAGE_CATEGORY_SUBDIR=false` only if you want a flatter legacy
layout.

Export a monthly reading summary and Topic Index for Obsidian:

```bash
paperflow wiki monthly --user-id user_role1
```

Without `--month`, PaperFlow exports the current calendar month. Use
`--month 2026-05` only when you intentionally want to regenerate an older
month.

Feishu/Lark document export is optional and separate from the GUI and CLI core.
Configuration is in [docs/feishu-doc-export.md](docs/feishu-doc-export.md).
After configuring Feishu, CLI usage is:

```bash
paperflow read 1 --user-id user_role1
paperflow read 1 --user-id user_role1 --folder-id <feishu_folder_token>
```

In the GUI, tick "同时尝试写入飞书文档" when generating a reading report.

Record feedback:

```bash
paperflow feedback \
  --user-id user_role1 \
  --push-id push_20260401_090000 \
  --reply "1, 3"
```

Feedback from CLI, GUI, and Feishu/Lark bot replies is stored in the same
SQLite database and updates the same profile for that `user_id`. See
[docs/feedback-loop.md](docs/feedback-loop.md) for the full learning path.

## Feishu / Lark Bot

The Feishu/Lark integration is optional. Use it when you want PaperFlow to run
as a chat bot with scheduled pushes and weekly reports.

If you only want reading reports exported as Feishu/Lark docs, use
[docs/feishu-doc-export.md](docs/feishu-doc-export.md) instead; that path does
not require ngrok or webhook callbacks.

Add the Feishu/Lark and ngrok values to `.env`:

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_USER_ID=

NGROK_AUTHTOKEN=
NGROK_DOMAIN=
```

Bind role chat IDs in `data/roles.json`, then start the local webhook server:

```bash
python deployments/feishu/webhook-server/start-with-ngrok.py
```

The script prints the public Request URL. Paste it into the Feishu/Lark event
subscription page and enable `im.message.receive_v1`.

Keep the process running if you want scheduled jobs:

| Job | Default schedule |
| --- | --- |
| Daily paper push | 09:00, Asia/Shanghai |
| Weekly report | Monday 10:00, Asia/Shanghai |

Watch live logs:

```powershell
Get-Content data/webhook_stderr.log -Wait
```

Common chat commands:

```text
profile
daily push
weekly report
1 3
read 1
```

Detailed setup:
[docs/feishu-webhook-setup.md](docs/feishu-webhook-setup.md).

## PaperFlow-Bench

PaperFlow-Bench is published on HuggingFace:
[OpenRaiser/PaperFlow](https://huggingface.co/datasets/OpenRaiser/PaperFlow).

Download:

```bash
python experiments/benchmark/fetch_benchmark.py \
  --output-dir data/PaperFlow-Bench
```

Create a simple valid prediction file from pool order:

```bash
python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output data/PaperFlow-Bench/example_predictions.jsonl
```

Evaluate:

```bash
paperflow eval \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions data/PaperFlow-Bench/example_predictions.jsonl \
  --output data/PaperFlow-Bench/example_metrics.json
```

More benchmark details:

- [docs/benchmark.md](docs/benchmark.md)
- [experiments/REPRODUCE.md](experiments/REPRODUCE.md)

## Workflow

```text
research profile
      |
      v
daily candidate pool  ->  scoring + drift adjustment  ->  paper digest
      |                                                       |
      v                                                       v
arXiv / OpenReview / journals                         reading reports
                                                              |
                                                              v
                                                     feedback + profile update
                                                              |
                                                              v
                                                     tomorrow's recommendation
```

## Repository Layout

```text
PaperFlow/
  paperflow/                 CLI and provider abstraction
  agents/                    Core workflow agents
  skills/                    Fetching, parsing, profile, and storage helpers
  deployments/desktop/       Optional local browser GUI
  deployments/feishu/        Optional Feishu/Lark bot deployment
  experiments/               Benchmark and paper reproduction scripts
  scripts/                   Operational utilities
  config/                    Source, scoring, and direction configuration
  docs/                      Setup and benchmark documentation
  tests/                     Unit and integration tests
```

## Development Checks

```bash
pytest tests -q
pytest experiments/tests -q
```

The GitHub Actions workflow runs the main test suite. Experiment tests are kept
in `experiments/tests/` for benchmark and reproduction validation.

## Documentation

For a complete guide map, see [docs/README.md](docs/README.md). The most common
follow-ups are:

- [docs/quickstart.md](docs/quickstart.md) for the first local run
- [docs/configuration.md](docs/configuration.md) for environment variables and paths
- [docs/feedback-loop.md](docs/feedback-loop.md) for CLI / GUI / Feishu profile learning
- [deployments/desktop/README.md](deployments/desktop/README.md) for local GUI behavior
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) for a no-install UI preview
- [docs/feishu-doc-export.md](docs/feishu-doc-export.md) for Feishu document export
- [docs/feishu-webhook-setup.md](docs/feishu-webhook-setup.md) for webhook + ngrok bot deployment

## Citation

If you use PaperFlow or PaperFlow-Bench in academic work, please cite:

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

The formal citation will be updated after the paper is published.

## License

PaperFlow is released under the MIT License. See [LICENSE](LICENSE).
