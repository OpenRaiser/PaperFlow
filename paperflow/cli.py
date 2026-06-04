"""PaperFlow command-line interface.

Wraps the user-facing entry points described in the README:

    paperflow init       Initialize local runtime + database
    paperflow profile    Create or update a user profile
    paperflow daily      Run a single daily push pipeline pass
    paperflow read       Generate a reading report for a paper
    paperflow feedback   Record feedback on a recommendation
    paperflow wiki       Inspect the local PaperFlow Wiki
    paperflow gui        Start the local browser GUI
    paperflow doctor     Verify the local install + provider settings
    paperflow demo       End-to-end demo with the bundled mock providers
    paperflow eval       Run the public PaperFlow-Bench evaluator

The implementation is intentionally thin: each command resolves its
arguments, prints a short banner, and delegates to the underlying script or
provider. Adding a new command means adding one ``@app.command`` here, not
threading through a router.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .providers import build_embedding_provider, build_llm_provider, load_provider_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = typer.Typer(
    name="paperflow",
    help="Personalized scientific-paper recommendation, reading, and reporting.",
    add_completion=False,
    no_args_is_help=True,
    invoke_without_command=True,
)
wiki_app = typer.Typer(help="Inspect and search the local PaperFlow Wiki.", add_completion=False)
app.add_typer(wiki_app, name="wiki")


def _run_python(script: Path, *args: str) -> int:
    """Run a project-internal Python script and stream its output."""
    cmd = [sys.executable, str(script), *args]
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    paths = [str(PROJECT_ROOT)]
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    typer.echo(f"$ {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return completed.returncode


def _run_wiki(*args: str) -> int:
    script = PROJECT_ROOT / "agents" / "wiki-agent" / "main.py"
    if not script.exists():
        typer.echo(f"[error] wiki agent not found: {script}", err=True)
        return 1
    return _run_python(script, *args)


@app.callback()
def _main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(f"paperflow {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def init() -> None:
    """Create local data directories and initialize the SQLite database."""
    script = PROJECT_ROOT / "scripts" / "init_db.py"
    if not script.exists():
        typer.echo(f"[error] init script not found: {script}", err=True)
        raise typer.Exit(code=1)
    raise typer.Exit(code=_run_python(script))


@app.command()
def doctor() -> None:
    """Check Python deps, provider credentials, and database state."""
    config = load_provider_config()
    typer.echo(f"PaperFlow {__version__}")
    typer.echo(f"Configured providers: {config.describe()}")

    script = PROJECT_ROOT / "scripts" / "doctor.py"
    if script.exists():
        raise typer.Exit(code=_run_python(script))
    typer.echo("[warn] scripts/doctor.py not found; provider configuration shown above only.")


@app.command()
def profile(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Create or update this PaperFlow user ID."),
    natural_language: Optional[str] = typer.Option(
        None,
        "--natural-language",
        "-d",
        help="Free-form research-interest description.",
    ),
    pdf: Optional[list[Path]] = typer.Option(
        None,
        "--pdf",
        help="PDF used to bootstrap the profile. Repeat this option for multiple PDFs.",
    ),
    scholar_url: Optional[str] = typer.Option(None, "--scholar-url", help="Google Scholar profile URL."),
    homepage_url: Optional[str] = typer.Option(None, "--homepage-url", help="Research homepage URL."),
    reset_existing: bool = typer.Option(False, "--reset-existing", help="Rebuild instead of merging into an existing profile."),
    send_feishu: bool = typer.Option(False, "--send-feishu", help="Send the profile summary through Feishu/Lark."),
    feishu_user_id: Optional[str] = typer.Option(None, "--feishu-user-id", help="Optional Feishu/Lark user open_id."),
    chat_id: Optional[str] = typer.Option(None, "--chat-id", help="Optional Feishu/Lark chat ID."),
) -> None:
    """Create or update a user profile from text, PDFs, Scholar, or homepage data."""
    script = PROJECT_ROOT / "agents" / "coldstart-agent" / "main.py"
    if not script.exists():
        typer.echo(f"[error] cold-start agent not found: {script}", err=True)
        raise typer.Exit(code=1)
    args: list[str] = ["--user-id", user_id]
    if natural_language:
        args.extend(["--natural-language", natural_language])
    if pdf:
        args.append("--pdf")
        args.extend(str(path) for path in pdf)
    if scholar_url:
        args.extend(["--scholar-url", scholar_url])
    if homepage_url:
        args.extend(["--homepage-url", homepage_url])
    if reset_existing:
        args.append("--reset-existing")
    if send_feishu:
        args.append("--send-feishu")
    if feishu_user_id:
        args.extend(["--feishu-user-id", feishu_user_id])
    if chat_id:
        args.extend(["--chat-id", chat_id])
    raise typer.Exit(code=_run_python(script, *args))


@app.command()
def daily(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Run the daily pipeline for this user."),
    days: int = typer.Option(1, "--days", help="Fetch papers from the last N days."),
    limit_per_source: int = typer.Option(100, "--limit-per-source", help="Max papers to fetch per source."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write the push card to a text file."),
    send_feishu: bool = typer.Option(False, "--send-feishu", help="Send the push through Feishu/Lark."),
    chat_id: Optional[str] = typer.Option(None, "--chat-id", help="Optional Feishu/Lark chat ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute recommendations without sending a push."),
) -> None:
    """Run a single daily-push pipeline pass for one user."""
    script = PROJECT_ROOT / "deployments" / "feishu" / "daily-push-agent" / "main.py"
    if not script.exists():
        script = PROJECT_ROOT / "agents" / "daily-push-agent" / "main.py"
    if not script.exists():
        typer.echo(f"[error] daily-push agent not found under deployments/feishu/ or agents/", err=True)
        raise typer.Exit(code=1)
    args: list[str] = ["--user-id", user_id, "--days", str(days), "--limit-per-source", str(limit_per_source)]
    if output:
        args.extend(["--output", str(output)])
    if chat_id:
        args.extend(["--chat-id", chat_id])
    if send_feishu and not dry_run:
        args.append("--send-feishu")
    raise typer.Exit(code=_run_python(script, *args))


@app.command()
def read(
    paper_ids: list[int] = typer.Argument(..., help="Paper IDs from a previous PaperFlow push."),
    user_id: Optional[str] = typer.Option(None, "--user-id", "-u", help="Personalize the report for this user."),
    push_id: Optional[str] = typer.Option(None, "--push-id", help="Read papers from a specific push ID."),
    folder_id: Optional[str] = typer.Option(None, "--folder-id", help="Optional Feishu/Lark folder ID."),
    no_feishu: bool = typer.Option(False, "--no-feishu", help="Do not send a Feishu/Lark notification."),
    feishu_user_id: Optional[str] = typer.Option(None, "--feishu-user-id", help="Optional Feishu/Lark user open_id."),
) -> None:
    """Generate a personalized reading report for a paper."""
    script = PROJECT_ROOT / "agents" / "reading-agent" / "main.py"
    if not script.exists():
        typer.echo(f"[error] reading agent not found: {script}", err=True)
        raise typer.Exit(code=1)
    args: list[str] = ["--paper-ids", *[str(paper_id) for paper_id in paper_ids]]
    if user_id:
        args.extend(["--user-id", user_id])
    if push_id:
        args.extend(["--push-id", push_id])
    if folder_id:
        args.extend(["--folder-id", folder_id])
    if no_feishu:
        args.append("--no-feishu")
    if feishu_user_id:
        args.extend(["--feishu-user-id", feishu_user_id])
    raise typer.Exit(code=_run_python(script, *args))


@app.command()
def feedback(
    user_id: str = typer.Option(..., "--user-id", "-u"),
    push_id: str = typer.Option(..., "--push-id", "-p", help="Push ID returned by the daily command."),
    reply: str = typer.Option(..., "--reply", "-r", help="Natural-language feedback or selected paper numbers."),
    send_feishu: bool = typer.Option(False, "--send-feishu", help="Send follow-up messages through Feishu/Lark."),
    feishu_user_id: Optional[str] = typer.Option(None, "--feishu-user-id", help="Optional Feishu/Lark user open_id."),
) -> None:
    """Record explicit feedback on a recommended paper."""
    script = PROJECT_ROOT / "agents" / "feedback-agent" / "main.py"
    if not script.exists():
        typer.echo(f"[error] feedback agent not found: {script}", err=True)
        raise typer.Exit(code=1)
    args = ["--user-id", user_id, "--push-id", push_id, "--reply", reply]
    if send_feishu:
        args.append("--send-feishu")
    if feishu_user_id:
        args.extend(["--feishu-user-id", feishu_user_id])
    raise typer.Exit(code=_run_python(script, *args))


@app.command()
def gui(
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface for the local GUI server."),
    port: int = typer.Option(8765, "--port", "-p", help="Port for the local GUI server."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the browser automatically."),
) -> None:
    """Start the local browser GUI."""
    script = PROJECT_ROOT / "deployments" / "desktop" / "server.py"
    if not script.exists():
        typer.echo(f"[error] desktop GUI server not found: {script}", err=True)
        raise typer.Exit(code=1)
    args = ["--host", host, "--port", str(port)]
    if no_browser:
        args.append("--no-browser")
    raise typer.Exit(code=_run_python(script, *args))


@wiki_app.command("init")
def wiki_init() -> None:
    """Initialize the local wiki tables and folders."""
    raise typer.Exit(code=_run_wiki("init"))


@wiki_app.command("list")
def wiki_list(
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    node_type: Optional[str] = typer.Option(None, "--type", help="Filter by paper, section, trajectory, or topic."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of nodes to print."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of a text table."),
) -> None:
    """List recent wiki nodes for a user."""
    args = ["list", "--user-id", user_id, "--limit", str(limit)]
    if node_type:
        args.extend(["--type", node_type])
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("search")
def wiki_search(
    query: str = typer.Argument(..., help="Search query."),
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    node_type: Optional[str] = typer.Option(None, "--type", help="Filter by paper, section, trajectory, or topic."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of nodes to print."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of a text table."),
) -> None:
    """Search wiki nodes for a user."""
    args = ["search", query, "--user-id", user_id, "--limit", str(limit)]
    if node_type:
        args.extend(["--type", node_type])
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("stats")
def wiki_stats(
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of text."),
) -> None:
    """Show local wiki node, edge, and citation counts."""
    args = ["stats", "--user-id", user_id]
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("embed")
def wiki_embed(
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    force: bool = typer.Option(False, "--force", help="Recompute existing embeddings."),
    limit: int = typer.Option(500, "--limit", help="Maximum number of nodes to embed."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of text."),
) -> None:
    """Embed wiki nodes for vector search."""
    args = ["embed", "--user-id", user_id, "--limit", str(limit)]
    if force:
        args.append("--force")
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("topics")
def wiki_topics(
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    min_count: int = typer.Option(2, "--min-count", help="Minimum keyword frequency."),
    limit: int = typer.Option(50, "--limit", help="Maximum number of topics to create."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of text."),
) -> None:
    """Build keyword topic nodes from paper nodes."""
    args = ["topics", "--user-id", user_id, "--min-count", str(min_count), "--limit", str(limit)]
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("ask")
def wiki_ask(
    question: str = typer.Argument(..., help="Question to ask over the local wiki."),
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    limit: int = typer.Option(8, "--limit", help="Maximum number of snippets to cite."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of text."),
) -> None:
    """Ask a RAG question over the local wiki."""
    args = ["ask", question, "--user-id", user_id, "--limit", str(limit)]
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("backfill")
def wiki_backfill(
    user_id: Optional[str] = typer.Option(None, "--user-id", "-u", help="PaperFlow user ID."),
    all_users: bool = typer.Option(False, "--all", help="Backfill every user found in the database."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count work without writing wiki data."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of text."),
) -> None:
    """Backfill existing behavior logs into the local wiki."""
    args = ["backfill"]
    if user_id:
        args.extend(["--user-id", user_id])
    if all_users:
        args.append("--all")
    if dry_run:
        args.append("--dry-run")
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@wiki_app.command("monthly")
def wiki_monthly(
    user_id: str = typer.Option(..., "--user-id", "-u", help="PaperFlow user ID."),
    month: Optional[str] = typer.Option(None, "--month", help="Month to export in YYYY-MM format."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Monthly report output directory."),
    topic_index_dir: Optional[Path] = typer.Option(None, "--topic-index-dir", help="Topic Index output directory."),
    no_topic_index: bool = typer.Option(False, "--no-topic-index", help="Only write the monthly report."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of text."),
) -> None:
    """Export an Obsidian-friendly monthly report and topic index."""
    args = ["monthly", "--user-id", user_id]
    if month:
        args.extend(["--month", month])
    if output_dir:
        args.extend(["--output-dir", str(output_dir)])
    if topic_index_dir:
        args.extend(["--topic-index-dir", str(topic_index_dir)])
    if no_topic_index:
        args.append("--no-topic-index")
    if json_output:
        args.append("--json")
    raise typer.Exit(code=_run_wiki(*args))


@app.command()
def demo() -> None:
    """End-to-end demo using the bundled mock providers (no credentials needed)."""
    os.environ.setdefault("PAPERFLOW_LLM_PROVIDER", "mock")
    os.environ.setdefault("PAPERFLOW_EMBED_PROVIDER", "hash")

    config = load_provider_config()
    typer.echo("PaperFlow demo (deterministic, offline)")
    typer.echo(f"Providers: {config.describe()}")

    llm = build_llm_provider(config)
    embed = build_embedding_provider(config)

    response = llm.generate(
        "Summarize PaperFlow in one sentence.",
        system="You are a concise research assistant.",
    )
    typer.echo(f"\n[llm:{llm.name}:{llm.model}] {response.text}")

    sample_texts = [
        "Personalized paper recommendation with interest drift.",
        "Multi-modal foundation models for scientific discovery.",
        "Reinforcement learning from human feedback.",
    ]
    vectors = embed.embed_batch(sample_texts)
    typer.echo(f"\n[embed:{embed.name}:{embed.model}] dim={embed.dimensions} batch={len(vectors)}")
    for text, vector in zip(sample_texts, vectors):
        preview = ", ".join(f"{value:+.3f}" for value in vector[:5])
        typer.echo(f"  - {text[:60]:<60} -> [{preview}, ...]")


@app.command()
def eval(
    benchmark_dir: Path = typer.Option(
        Path("data/PaperFlow-Bench"),
        "--benchmark-dir",
        "-b",
        help="Benchmark root containing data/, reference_outputs/, evaluation/.",
    ),
    predictions: Path = typer.Option(
        ...,
        "--predictions",
        "-p",
        help="Top-20 predictions JSONL file (one row per episode).",
    ),
    output: Path = typer.Option(
        Path("paperflow_eval.json"),
        "--output",
        "-o",
        help="Where to write the metrics JSON.",
    ),
) -> None:
    """Run the public PaperFlow-Bench evaluator on a predictions file."""
    script = PROJECT_ROOT / "experiments" / "benchmark" / "evaluate_benchmark_predictions.py"
    if not script.exists():
        typer.echo(f"[error] evaluator not found: {script}", err=True)
        raise typer.Exit(code=1)
    raise typer.Exit(
        code=_run_python(
            script,
            "--benchmark-dir",
            str(benchmark_dir),
            "--predictions",
            str(predictions),
            "--output",
            str(output),
        )
    )


def main() -> None:  # pragma: no cover - thin wrapper
    app()


if __name__ == "__main__":
    main()
