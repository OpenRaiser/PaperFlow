"""PaperFlow command-line interface.

Wraps the seven user-facing entry points described in the README:

    paperflow init       Initialize local runtime + database
    paperflow daily      Run a single daily push pipeline pass
    paperflow read       Generate a reading report for a paper
    paperflow feedback   Record feedback on a recommendation
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
def daily(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Run the daily pipeline for this user."),
    days: int = typer.Option(1, "--days", help="Fetch papers from the last N days."),
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
    args: list[str] = ["--user-id", user_id, "--days", str(days)]
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
