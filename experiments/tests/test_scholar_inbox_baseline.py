import json
from pathlib import Path

import pytest

from experiments.benchmark import export_clean_baseline_benchmark as clean_export
from experiments.baselines.scholar_inbox import runner


def _write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row(date, paper_id, title, abstract, *, selected=False, shown=False, oracle_label="irrelevant"):
    return {
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
        "shown": shown,
        "selected": selected,
        "pool_rank": None,
        "system_rank": None,
        "system_score": 0.0,
        "system_label": "edge_relevant",
        "oracle_score": 0.0,
        "oracle_label": oracle_label,
        "select_probability": 0.0,
    }


def test_scholar_inbox_reranks_with_previous_feedback_only(tmp_path):
    input_dir = tmp_path / "benchmark"
    output_dir = tmp_path / "out"
    input_dir.mkdir()

    users = {
        "users": [
                    {
                        "user_id": "user_role1",
                        "role_name": "role1",
                        "description": "",
                        "seed_directions": {},
                    }
        ]
    }
    (input_dir / "users.json").write_text(json.dumps(users), encoding="utf-8")

    episode_rows = [
        {"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"},
        {"date": "2026-03-02", "episode_id": "user_role1::2026-03-02", "user_id": "user_role1"},
    ]
    _write_jsonl(input_dir / "episodes.jsonl", episode_rows)

    paper_rows = [
        _row(
            "2026-03-01",
            "d1a",
            "Alpha Graph Planning",
            "A paper about alpha graph planning for scientific agents.",
            selected=True,
            shown=True,
            oracle_label="strong_relevant",
        ),
        _row(
            "2026-03-01",
            "d1b",
            "Beta Control Systems",
            "A paper about beta control and unrelated optimization.",
            selected=False,
            shown=True,
        ),
        _row(
            "2026-03-02",
            "d2a",
            "Alpha Graph Retrieval",
            "Follow-up work on alpha graph planning and scientific agents.",
            oracle_label="strong_relevant",
        ),
        _row(
            "2026-03-02",
            "d2b",
            "Beta Control Forecasting",
            "Unrelated beta control forecasting for another domain.",
        ),
    ]
    _write_jsonl(input_dir / "episode_papers.jsonl", paper_rows)

    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)

    result = runner.run_baseline(
        input_dir=clean_dir,
        output_dir=output_dir,
        roles_file=roles_file,
        top_k=1,
        background_negatives_per_day=0,
    )

    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    day2_shown = [
        row for row in output_rows
        if row["episode_id"] == "user_role1::2026-03-02" and row["shown"]
    ]
    day1_rows = [
        row for row in output_rows
        if row["episode_id"] == "user_role1::2026-03-01"
    ]

    assert day2_shown[0]["paper_id"] == "d2a"
    assert day2_shown[0]["baseline_method"] == runner.METHOD_NAME
    assert day2_shown[0]["system_rank"] == 1
    assert day2_shown[0]["system_label"] != "must_read"
    assert {row["training_positive_count"] for row in day1_rows} == {0}
    assert day2_shown[0]["training_positive_count"] == 1
    assert result["method_stats"]["users"]["user_role1"]["positive_count"] == 1
    assert (output_dir / "evaluation_metrics.json").exists()
    assert (output_dir / "main_experiment_table_top20.md").exists()


def test_scholar_inbox_uses_logistic_classifier_after_enough_feedback(tmp_path):
    input_dir = tmp_path / "benchmark"
    output_dir = tmp_path / "out"
    input_dir.mkdir()

    users = {
        "users": [
            {
                "user_id": "user_role1",
                "role_name": "role1",
                "description": "",
                "seed_directions": {},
            }
        ]
    }
    (input_dir / "users.json").write_text(json.dumps(users), encoding="utf-8")

    _write_jsonl(
        input_dir / "episodes.jsonl",
        [
            {"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"},
            {"date": "2026-03-02", "episode_id": "user_role1::2026-03-02", "user_id": "user_role1"},
        ],
    )

    positive_rows = [
        _row(
            "2026-03-01",
            f"pos{i}",
            f"Alpha Graph Agent Planning {i}",
            "Alpha graph planning for scientific agents and literature discovery.",
            selected=True,
            oracle_label="strong_relevant",
        )
        for i in range(3)
    ]
    negative_rows = [
        _row(
            "2026-03-01",
            f"neg{i}",
            f"Beta Finance Control {i}",
            "Beta finance control forecasting with unrelated market signals.",
        )
        for i in range(8)
    ]
    day2_rows = [
        _row(
            "2026-03-02",
            "target_alpha",
            "Alpha Graph Agent Retrieval",
            "Alpha graph planning for scientific agents and paper retrieval.",
            oracle_label="strong_relevant",
        ),
        _row(
            "2026-03-02",
            "target_beta",
            "Beta Finance Forecasting",
            "Beta finance control forecasting with unrelated market signals.",
        ),
    ]
    _write_jsonl(input_dir / "episode_papers.jsonl", positive_rows + negative_rows + day2_rows)

    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")
    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)

    result = runner.run_baseline(
        input_dir=clean_dir,
        output_dir=output_dir,
        roles_file=roles_file,
        top_k=1,
        background_negatives_per_day=8,
    )

    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    day2_rows = [row for row in output_rows if row["episode_id"] == "user_role1::2026-03-02"]
    day2_shown = [row for row in day2_rows if row["shown"]]

    assert day2_shown[0]["paper_id"] == "target_alpha"
    assert {row["training_positive_count"] for row in day2_rows} == {3}
    assert {row["training_negative_count"] for row in day2_rows} == {8}
    assert {row["uses_feedback_classifier"] for row in day2_rows} == {True}
    assert result["method_stats"]["users"]["user_role1"]["uses_feedback_classifier"] is True


def test_scholar_inbox_preserves_oracle_fields_for_evaluation(tmp_path):
    full_dir = tmp_path / "benchmark"
    input_dir = tmp_path / "clean"
    output_dir = tmp_path / "out"
    full_dir.mkdir()
    (full_dir / "users.json").write_text(json.dumps({"users": []}), encoding="utf-8")
    _write_jsonl(
        full_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    _write_jsonl(
        full_dir / "episode_papers.jsonl",
        [
            _row(
                "2026-03-01",
                "p1",
                "Graph Agent Benchmark",
                "A graph agent benchmark.",
                oracle_label="relevant",
            )
        ],
    )
    clean_export.export_clean_benchmark(input_dir=full_dir, output_dir=input_dir)
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    [output_row] = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    assert output_row["oracle_label"] == "relevant"
    assert "oracle_score" in output_row
    assert output_row["ranking_source"] == "baselines.scholar_inbox.runner"


def test_scholar_inbox_refuses_full_episode_papers_directly(tmp_path):
    input_dir = tmp_path / "benchmark"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    _write_jsonl(
        input_dir / "episode_papers.jsonl",
        [_row("2026-03-01", "p1", "Graph Agent Benchmark", "A graph agent benchmark.")],
    )
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {}}), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="refuses to read Full PaperFlow episode_papers"):
        runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)


def test_clean_export_strips_full_pipeline_method_fields(tmp_path):
    input_dir = tmp_path / "full"
    output_dir = tmp_path / "clean"
    input_dir.mkdir()
    (input_dir / "users.json").write_text(json.dumps({"users": []}), encoding="utf-8")
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    full_row = _row("2026-03-01", "p1", "Alpha", "Alpha paper.", selected=True, shown=True)
    full_row.update(
        {
            "system_score": 999.0,
            "system_label": "must_read",
            "system_rank": 1,
            "drift_bonus": 99.0,
            "ranking_source": "full_paperflow",
            "oracle_label": "strong_relevant",
            "oracle_score": 0.95,
        }
    )
    _write_jsonl(input_dir / "episode_papers.jsonl", [full_row])

    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=output_dir)

    [candidate] = runner.load_jsonl(output_dir / "candidate_pools.jsonl")
    [label] = runner.load_jsonl(output_dir / "labels_for_eval.jsonl")
    [episode] = runner.load_jsonl(output_dir / "episodes.jsonl")

    for forbidden in clean_export.FORBIDDEN_METHOD_FIELDS:
        assert forbidden not in candidate
    assert "selected_papers" not in episode
    assert "selected_paper_ids" not in episode
    assert "selected_paper_titles" not in episode
    assert candidate["paper_id"] == "p1"
    assert label["selected"] is True
    assert label["oracle_label"] == "strong_relevant"
    assert label["oracle_score"] == 0.95


def test_clean_export_strips_dynamic_user_profile_fields(tmp_path):
    input_dir = tmp_path / "full"
    output_dir = tmp_path / "clean"
    input_dir.mkdir()
    (input_dir / "users.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user_id": "user_role1",
                        "role_name": "role1",
                        "description": "initial alpha interests",
                        "seed_directions": {"alpha": 0.7},
                        "initial_topics": ["alpha"],
                        "created_at": "2026-03-01",
                        "profile": {"core_directions": {"future-drift": 1.0}},
                        "updated_profile": {"core_directions": {"future-drift": 1.0}},
                        "core_directions": {"future-drift": 1.0},
                        "topic_weights": {"future-drift": 1.0},
                        "interest_vector": [0.1, 0.2],
                        "drift_state": {"status": "shifting", "top_shift_topics": ["future-drift"]},
                        "report_preferences": {"preferred_report_length": "detailed"},
                        "updated_at": "2026-04-19T23:59:59",
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
    _write_jsonl(input_dir / "episode_papers.jsonl", [_row("2026-03-01", "p1", "Alpha", "Alpha paper.")])

    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=output_dir)

    clean_users = json.loads((output_dir / "users.json").read_text(encoding="utf-8"))["users"]
    [clean_user] = clean_users
    for forbidden in clean_export.FORBIDDEN_USER_FIELDS:
        assert forbidden not in clean_user
    assert clean_user == {
        "user_id": "user_role1",
        "role_name": "role1",
        "description": "initial alpha interests",
        "seed_directions": {"alpha": 0.7},
        "initial_topics": ["alpha"],
        "created_at": "2026-03-01",
    }


def test_scholar_inbox_clean_input_does_not_rank_by_oracle_label(tmp_path):
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
                        "description": "alpha graph planning",
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
        _row("2026-03-01", "p_alpha", "Alpha Graph Planning", "Alpha graph planning for agents."),
        _row("2026-03-01", "p_beta", "Beta Control", "Beta control for unrelated systems."),
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
