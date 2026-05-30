import json
from pathlib import Path

import pytest

from experiments.benchmark import export_clean_baseline_benchmark as clean_export
from experiments.baselines.discourse_aware import runner


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


def test_discourse_aware_refuses_full_episode_papers_directly(tmp_path):
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


def test_discourse_aware_extracts_facets_and_prefers_structured_contribution(tmp_path):
    input_dir = tmp_path / "clean"
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
                        "seed_directions": {},
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
    candidates = [
        _row(
            "2026-03-01",
            "structured",
            "Alpha Agent Benchmark",
            (
                "Existing agent benchmarks remain difficult to use. "
                "We propose a new framework for alpha agent benchmark methods. "
                "Experiments demonstrate improved planning performance. "
                "We release a benchmark dataset and code."
            ),
        ),
        _row(
            "2026-03-01",
            "generic",
            "Alpha Agent Benchmark Overview",
            "Alpha agent benchmark papers are important and widely studied in recent years.",
        ),
    ]
    _write_jsonl(input_dir / "candidate_pools.jsonl", [
        {
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
        for row in candidates
    ])
    _write_jsonl(input_dir / "labels_for_eval.jsonl", [
        {
            "date": row["date"],
            "episode_id": row["episode_id"],
            "user_id": row["user_id"],
            "paper_id": row["paper_id"],
            "paper_identity": runner.paper_identity(row),
            "selected": False,
            "oracle_label": "irrelevant",
            "oracle_score": 0.0,
        }
        for row in candidates
    ])
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    structured = next(row for row in output_rows if row["paper_id"] == "structured")
    generic = next(row for row in output_rows if row["paper_id"] == "generic")
    shown = [row for row in output_rows if row["shown"]]

    assert shown[0]["paper_id"] == "structured"
    assert structured["discourse_coverage_score"] > generic["discourse_coverage_score"]
    assert structured["contribution_signal_score"] > generic["contribution_signal_score"]
    assert {"problem", "method", "result", "resource"}.issubset(set(structured["discourse_facets"]))


def test_discourse_aware_uses_previous_selected_feedback_only_after_ranking(tmp_path):
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
                        "description": "",
                        "seed_directions": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
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
            "seed",
            "Alpha Agent Planning",
            "We propose an alpha agent planning framework and demonstrate improved results.",
            selected=True,
            oracle_label="strong_relevant",
        ),
        _row(
            "2026-03-02",
            "followup",
            "Alpha Agent Planning Benchmark",
            "We propose an alpha agent planning benchmark and demonstrate improved performance.",
        ),
        _row(
            "2026-03-02",
            "distractor",
            "Beta Control Survey",
            "Existing beta control systems are widely studied.",
            oracle_label="strong_relevant",
        ),
    ]
    _write_jsonl(input_dir / "episode_papers.jsonl", paper_rows)
    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=clean_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    day1_rows = [row for row in output_rows if row["episode_id"] == "user_role1::2026-03-01"]
    day2_shown = [
        row for row in output_rows
        if row["episode_id"] == "user_role1::2026-03-02" and row["shown"]
    ]

    assert {row["training_selected_count"] for row in day1_rows} == {0}
    assert day2_shown[0]["paper_id"] == "followup"
    assert day2_shown[0]["training_selected_count"] == 1
    assert day2_shown[0]["oracle_label"] == "irrelevant"


def test_discourse_aware_clean_input_does_not_rank_by_oracle_label(tmp_path):
    input_dir = tmp_path / "clean"
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
                        "seed_directions": {},
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
    candidates = [
        _row(
            "2026-03-01",
            "p_alpha",
            "Alpha Agent Benchmark",
            "We propose an alpha agent benchmark method and demonstrate results.",
        ),
        _row(
            "2026-03-01",
            "p_beta",
            "Beta Control",
            "Beta control for unrelated systems.",
        ),
    ]
    labels = [
        {
            "date": row["date"],
            "episode_id": row["episode_id"],
            "user_id": row["user_id"],
            "paper_id": row["paper_id"],
            "paper_identity": runner.paper_identity(row),
            "selected": row["paper_id"] == "p_beta",
            "oracle_label": "strong_relevant" if row["paper_id"] == "p_beta" else "irrelevant",
            "oracle_score": 0.99 if row["paper_id"] == "p_beta" else 0.0,
        }
        for row in candidates
    ]
    clean_candidates = [
        {
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
        for row in candidates
    ]
    _write_jsonl(input_dir / "candidate_pools.jsonl", clean_candidates)
    _write_jsonl(input_dir / "labels_for_eval.jsonl", labels)
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    shown = [row for row in runner.load_jsonl(output_dir / "episode_papers.jsonl") if row["shown"]]
    assert shown[0]["paper_id"] == "p_alpha"
    assert shown[0]["oracle_label"] == "irrelevant"


def test_discourse_aware_does_not_require_reading_report_fields(tmp_path):
    input_dir = tmp_path / "full"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "users.json").write_text(json.dumps({"users": []}), encoding="utf-8")
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    full_row = _row(
        "2026-03-01",
        "p1",
        "Alpha Agent Benchmark",
        "We propose an alpha benchmark and demonstrate results.",
        selected=True,
        reading_report="Full PaperFlow report that clean export must not expose.",
        report_quality_score=1.0,
    )
    _write_jsonl(input_dir / "episode_papers.jsonl", [full_row])
    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)
    [candidate] = runner.load_jsonl(clean_dir / "candidate_pools.jsonl")
    assert "reading_report" not in candidate
    assert "report_quality_score" not in candidate

    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {}}), encoding="utf-8")
    runner.run_baseline(input_dir=clean_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    [output_row] = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    assert output_row["baseline_method"] == runner.METHOD_NAME
    assert output_row["training_selected_count"] == 0
