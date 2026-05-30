"""Smoke tests for the paperflow Typer CLI — fast, offline, no credentials."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paperflow import __version__
from paperflow.cli import app

runner = CliRunner()


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _force_mock_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every CLI test deterministic and offline."""
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "mock")
    monkeypatch.setenv("PAPERFLOW_EMBED_PROVIDER", "hash")
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.unit
def test_cli_version_flag_short() -> None:
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.unit
def test_cli_version_flag_long() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "paperflow" in result.stdout
    assert __version__ in result.stdout


@pytest.mark.unit
def test_cli_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "doctor", "daily", "read", "feedback", "demo", "eval"):
        assert command in result.stdout


@pytest.mark.unit
def test_cli_no_args_prints_help() -> None:
    result = runner.invoke(app, [])
    # Typer with no_args_is_help=True exits with code 2 after printing help.
    assert result.exit_code in (0, 2)
    assert "paperflow" in result.stdout.lower() or "paperflow" in result.output.lower()


@pytest.mark.unit
def test_cli_demo_runs_with_mock_providers() -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.stdout
    assert "PaperFlow demo" in result.stdout
    assert "llm=mock" in result.stdout
    assert "embed=hash" in result.stdout
    assert "[llm:mock:" in result.stdout
    assert "[embed:hash:" in result.stdout


@pytest.mark.unit
def test_cli_read_help_lists_arguments() -> None:
    result = runner.invoke(app, ["read", "--help"])
    assert result.exit_code == 0
    assert "PAPER_IDS" in result.stdout.upper()
    assert "--user-id" in result.stdout


@pytest.mark.unit
def test_cli_feedback_help_lists_options() -> None:
    result = runner.invoke(app, ["feedback", "--help"])
    assert result.exit_code == 0
    for opt in ("--user-id", "--push-id", "--reply"):
        assert opt in result.stdout


@pytest.mark.unit
def test_cli_daily_help_lists_options() -> None:
    result = runner.invoke(app, ["daily", "--help"])
    assert result.exit_code == 0
    for opt in ("--user-id", "--days", "--output", "--dry-run"):
        assert opt in result.stdout


@pytest.mark.unit
def test_cli_eval_help_lists_options() -> None:
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    for opt in ("--benchmark-dir", "--predictions", "--output"):
        assert opt in result.stdout


@pytest.mark.unit
def test_cli_module_invocation_returns_version() -> None:
    """`python -m paperflow.cli --version` should also work."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "paperflow.cli", "--version"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PAPERFLOW_LLM_PROVIDER": "mock", "PAPERFLOW_EMBED_PROVIDER": "hash"},
    )
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout
