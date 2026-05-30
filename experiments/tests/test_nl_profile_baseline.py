import json
from pathlib import Path

import pytest

from experiments.benchmark import export_clean_baseline_benchmark as clean_export
from experiments.baselines.nl_profile import runner


def _write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row(date, paper_id, title, abstract, *, selected=False, oracle_label="irrelevant", **extra):
    row = {
        "date": date,
        "episode_id": f"user_role1::{date}",
        "user_id": "user_role1",
        "role_name": "role1",
        "paper_id": paper_id,
        "title": title,
        "abstract": abstract,
        "authors": [],
        "source": "arxiv",
        "url": f"https://example.test/{paper_id}",
        "shown": False,
        "selected": selected,
        "pool_rank": None,
        "system_rank": None,
        "system_score": 0.0,
        "system_label": "edge_relevant",
        "oracle_score": 0.0,
        "oracle_label": oracle_label,
        "select_probability": 0.0,
    }
    row.update(extra)
    return row


def _write_clean_user(input_dir: Path, description="alpha agent benchmark methods"):
    (input_dir / "users.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user_id": "user_role1",
                        "role_name": "role1",
                        "description": description,
                        "seed_directions": {"alpha-agent": 0.8, "benchmark-method": 0.6},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _clean_candidate(row):
    return {
        "date": row["date"],
        "episode_id": row["episode_id"],
        "user_id": row["user_id"],
        "role_name": row["role_name"],
        "paper_id": row["paper_id"],
        "paper_identity": runner.paper_identity(row),
        "title": row["title"],
        "abstract": row["abstract"],
        "authors": row["authors"],
        "source": row["source"],
        "url": row["url"],
    }


def _label(row, *, selected=False, oracle_label="irrelevant", oracle_score=0.0):
    return {
        "date": row["date"],
        "episode_id": row["episode_id"],
        "user_id": row["user_id"],
        "paper_id": row["paper_id"],
        "paper_identity": runner.paper_identity(row),
        "selected": selected,
        "oracle_label": oracle_label,
        "oracle_score": oracle_score,
    }


def test_nl_profile_refuses_full_episode_papers_directly(tmp_path):
    input_dir = tmp_path / "benchmark"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    _write_jsonl(input_dir / "episode_papers.jsonl", [_row("2026-03-01", "p1", "Alpha", "Alpha.")])
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {}}), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="refuses to read Full PaperFlow episode_papers"):
        runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)


def test_nl_profile_ranks_by_fixed_natural_language_profile(tmp_path):
    input_dir = tmp_path / "clean"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_clean_user(input_dir)
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    candidates = [
        _row(
            "2026-03-01",
            "p_alpha",
            "Alpha Agent Benchmark Methods",
            "A benchmark method for alpha agents and paper recommendation evaluation.",
        ),
        _row(
            "2026-03-01",
            "p_beta",
            "Beta Control Forecasting",
            "A beta control forecasting system for unrelated markets.",
        ),
    ]
    _write_jsonl(input_dir / "candidate_pools.jsonl", [_clean_candidate(row) for row in candidates])
    _write_jsonl(input_dir / "labels_for_eval.jsonl", [_label(row) for row in candidates])
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    shown = [row for row in output_rows if row["shown"]]
    alpha = next(row for row in output_rows if row["paper_id"] == "p_alpha")
    beta = next(row for row in output_rows if row["paper_id"] == "p_beta")
    assert shown[0]["paper_id"] == "p_alpha"
    assert alpha["profile_similarity_score"] > beta["profile_similarity_score"]
    assert alpha["uses_feedback_update"] is False
    assert (output_dir / "main_experiment_table_top20.md").exists()


def test_nl_profile_does_not_rank_by_oracle_or_selected_labels(tmp_path):
    input_dir = tmp_path / "clean"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_clean_user(input_dir)
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    candidates = [
        _row(
            "2026-03-01",
            "p_alpha",
            "Alpha Agent Benchmark",
            "Alpha agent benchmark methods for scientific recommendation.",
        ),
        _row(
            "2026-03-01",
            "p_beta",
            "Beta Control",
            "Beta control for unrelated systems.",
        ),
    ]
    _write_jsonl(input_dir / "candidate_pools.jsonl", [_clean_candidate(row) for row in candidates])
    _write_jsonl(
        input_dir / "labels_for_eval.jsonl",
        [
            _label(candidates[0], selected=False, oracle_label="irrelevant", oracle_score=0.0),
            _label(candidates[1], selected=True, oracle_label="strong_relevant", oracle_score=0.99),
        ],
    )
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    shown = [row for row in runner.load_jsonl(output_dir / "episode_papers.jsonl") if row["shown"]]
    assert shown[0]["paper_id"] == "p_alpha"
    assert shown[0]["oracle_label"] == "irrelevant"


def test_nl_profile_does_not_update_from_previous_selected_papers(tmp_path):
    input_dir = tmp_path / "full"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_clean_user(input_dir)
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [
            {"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"},
            {"date": "2026-03-02", "episode_id": "user_role1::2026-03-02", "user_id": "user_role1"},
        ],
    )
    paper_rows = [
        _row(
            "2026-03-01",
            "seed_beta",
            "Beta Control Selected Paper",
            "Beta control and unrelated market forecasting.",
            selected=True,
            oracle_label="strong_relevant",
        ),
        _row(
            "2026-03-02",
            "follow_alpha",
            "Alpha Agent Benchmark",
            "Alpha agent benchmark methods for paper recommendation.",
        ),
        _row(
            "2026-03-02",
            "follow_beta",
            "Beta Control Followup",
            "Beta control and market forecasting follow-up paper.",
        ),
    ]
    _write_jsonl(input_dir / "episode_papers.jsonl", paper_rows)
    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    result = runner.run_baseline(input_dir=clean_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    day2_shown = [
        row for row in output_rows
        if row["episode_id"] == "user_role1::2026-03-02" and row["shown"]
    ]
    assert day2_shown[0]["paper_id"] == "follow_alpha"
    assert {row["uses_feedback_update"] for row in output_rows} == {False}
    assert result["method_stats"]["uses_dynamic_feedback"] is False


def test_nl_profile_does_not_require_reading_report_or_dynamic_profile_fields(tmp_path):
    input_dir = tmp_path / "full"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "users.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user_id": "user_role1",
                        "role_name": "role1",
                        "description": "alpha agent benchmark methods",
                        "seed_directions": {"alpha-agent": 0.8},
                        "profile": {"core_directions": {"future-drift": 1.0}},
                        "updated_profile": {"core_directions": {"future-drift": 1.0}},
                        "drift_state": {"status": "shifting"},
                        "report_preferences": {"preferred_report_length": "detailed"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    full_row = _row(
        "2026-03-01",
        "p1",
        "Alpha Agent Benchmark",
        "Alpha benchmark method.",
        reading_report="Full PaperFlow report that clean export must not expose.",
        report_quality_score=1.0,
    )
    _write_jsonl(input_dir / "episode_papers.jsonl", [full_row])
    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)
    [candidate] = runner.load_jsonl(clean_dir / "candidate_pools.jsonl")
    clean_user = json.loads((clean_dir / "users.json").read_text(encoding="utf-8"))["users"][0]
    assert "reading_report" not in candidate
    assert "report_quality_score" not in candidate
    assert "profile" not in clean_user
    assert "updated_profile" not in clean_user
    assert "drift_state" not in clean_user
    assert "report_preferences" not in clean_user

    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {}}), encoding="utf-8")
    runner.run_baseline(input_dir=clean_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    [output_row] = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    assert output_row["baseline_method"] == runner.METHOD_NAME
    assert output_row["uses_feedback_update"] is False
