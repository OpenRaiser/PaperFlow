# Architecture

PaperFlow is built around three layers: a thin **CLI**, a **provider
abstraction** for LLMs and embeddings, and a set of **agents** and **skills**
that compose the daily-pipeline / reading-report / feedback / drift loop.

```text
                 +------------------------------------------+
                 |             paperflow CLI (typer)         |
                 |   init / doctor / daily / read / feedback |
                 |   demo / eval                             |
                 +------------------------------------------+
                                     |
                                     v
                 +------------------------------------------+
                 |          paperflow.providers              |
                 |   LLMProvider:    OpenAI / Anthropic /    |
                 |                   Ollama / Mock           |
                 |   EmbeddingProvider: OpenAI /             |
                 |                   sentence-transformers / |
                 |                   Ollama / Hash           |
                 +------------------------------------------+
                                     |
                                     v
+-------------+     +-------------+     +-----------------------+
|  agents/    |<--->|  skills/    |<--->|  data sources         |
|             |     |             |     |  arXiv / OpenReview / |
| coldstart   |     | fetch       |     |  journals             |
| reading     |     | parse       |     +-----------------------+
| feedback    |     | store       |
| must-read   |     | profile     |     +-----------------------+
| profile     |     | report      |     |  storage              |
| coordinator |     |             |     |  data/paperflow.db    |
+-------------+     +-------------+     |  data/embeddings_cache|
                                        +-----------------------+
                                                  ^
                                                  |
                                  +---------------+----------------+
                                  |  deployments/feishu/ (optional)|
                                  |  webhook + daily push          |
                                  +--------------------------------+
```

## CLI layer (`paperflow/cli.py`)

The CLI is intentionally thin. Each command resolves its arguments, validates
provider configuration, and either:

- delegates to a project-internal Python script via `subprocess.run`
  (`init`, `daily`, `read`, `feedback`, `eval`, the heavyweight `doctor`); or
- runs in-process to exercise the provider abstraction (`demo`).

Adding a new command means adding one `@app.command` in `paperflow/cli.py` —
no router, no plugin discovery.

## Provider abstraction (`paperflow/providers/`)

The provider layer defines two protocols:

```python
class LLMProvider(Protocol):
    name: str
    model: str
    def generate(self, prompt: str, *, system: Optional[str] = None,
                 temperature: float = 0.0, max_tokens: int = 1024) -> LLMResponse: ...

class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    def embed(self, text: str) -> List[float]: ...
    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]: ...
```

Concrete implementations live next to the protocols and are constructed by
two factory functions:

```python
from paperflow.providers import build_llm_provider, build_embedding_provider

llm = build_llm_provider()
embed = build_embedding_provider()
```

Both factories read `PAPERFLOW_LLM_PROVIDER` / `PAPERFLOW_EMBED_PROVIDER` from
the environment, fall back to per-provider defaults when models or dimensions
aren't set, and silently substitute the deterministic mock/hash backend when
credentials are missing or look like placeholders. This keeps tests and
offline reproductions stable.

See [providers.md](providers.md) for per-backend details.

## Agents (`agents/`)

Agents are coarse-grained units that compose the user-visible pipeline:

| Agent                 | Responsibility                                             |
|-----------------------|------------------------------------------------------------|
| `coldstart-agent`     | Bootstrap a structured profile from text/PDF/homepage      |
| `reading-agent`       | Generate per-paper personalized reading reports            |
| `feedback-agent`      | Translate user signals into profile + drift updates        |
| `must-read-manager`   | Maintain author/keyword anchor lists                       |
| `profile-report-agent`| Produce long-form profile reports                          |
| `master-coordinator`  | Cross-agent orchestration, intent parsing                  |

The Feishu daily-push agent moved out of `agents/` into
`deployments/feishu/daily-push-agent/` to make the deployment-specific
nature explicit.

## Skills (`skills/`)

Skills are the small reusable pieces — fetchers, parsers, and storage helpers
the agents call into:

| Skill                | Purpose                                              |
|----------------------|------------------------------------------------------|
| `arxiv-fetcher`      | Pull papers from arXiv by date/category              |
| `openreview-fetcher` | Pull papers from OpenReview by venue                 |
| `journal-fetcher`    | RSS / API journal fetchers                           |
| `profile-updater`    | Score papers against profile, drift bookkeeping      |
| `storage-helper`     | SQLite + embedding cache I/O                         |
| `feishu-reporter`    | Card rendering for the Feishu deployment             |

Skills are resolved with `importlib` because some directory names contain
hyphens. Each skill is dependency-light by design: heavy imports
(`openai`, `sentence_transformers`, `anthropic`) happen inside the provider
classes, not at module load time, so missing optional deps don't break
unrelated agents.

## Data flow: a daily pipeline run

1. **Fetch.** `daily-push-agent` walks `config/conferences.yaml`,
   `config/journals.yaml`, and the arXiv categories baked into the user
   profile. Skills fetch raw papers and write them to
   `data/paperflow.db`.
2. **Score.** Each paper is embedded (cached in `data/embeddings_cache/`),
   scored against the user's interest weights, given an anchor boost for
   author/keyword matches, and a freshness term for recency.
3. **Drift correction.** `skills/profile-updater` compares short-window vs
   long-window centroids and adjusts the learning rate before applying the
   day's score updates.
4. **Top-20 selection.** A diversity-aware ranker picks 20 papers under the
   display budget.
5. **Push (optional).** If running under `deployments/feishu/`, the cards
   are rendered and pushed via the Feishu webhook.

## Storage

PaperFlow uses a single SQLite database at `data/paperflow.db` and a flat
JSON store for user roles. Embeddings are cached as raw float arrays under
`data/embeddings_cache/` keyed by content hash, so swapping embedding
backends invalidates the cache automatically.

## Experiment surface (`experiments/`)

The paper experiments are runnable, reproducible scripts split by purpose:

```text
experiments/
├── benchmark/         Public PaperFlow-Bench evaluator + packagers
├── main_experiment/   6 baselines + the PaperFlow main system
├── ablation/          Component-removal runs
├── drift/             Interest-drift experiments
├── llm_comparison/    LLM-backbone comparison
├── token_cost/        Token-usage profiling
├── simulation/        Historical-episode simulator
├── reading_reports/   Reading-report quality runs
└── analysis/          Plot + summary scripts
```

Each runnable folder ships both `.sh` (Linux/macOS) and `.cmd`/`.ps1`
(Windows) entry points. See [reproduce.md](reproduce.md) and
[../experiments/REPRODUCE.md](../experiments/REPRODUCE.md).

## Optional Feishu deployment (`deployments/feishu/`)

The Feishu/Lark integration is fully optional and lives in its own deployment
directory:

```text
deployments/feishu/
├── daily-push-agent/    Daily pipeline behind a Feishu webhook
├── feishu-reporter/     Feishu card rendering
└── webhook-server/      Webhook + ngrok launcher
```

CLI users never need to look at this directory. See
[feishu-webhook-setup.md](feishu-webhook-setup.md) if you want the bot.
