import json
from pathlib import Path

import pytest

from experiments.benchmark import export_clean_baseline_benchmark as clean_export
from experiments.baselines.citation_enhanced import runner


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


def test_clean_export_preserves_citation_metadata_but_strips_method_fields(tmp_path):
    input_dir = tmp_path / "full"
    output_dir = tmp_path / "clean"
    input_dir.mkdir()
    (input_dir / "users.json").write_text(json.dumps({"users": []}), encoding="utf-8")
    _write_jsonl(
        input_dir / "episodes.jsonl",
        [{"date": "2026-03-01", "episode_id": "user_role1::2026-03-01", "user_id": "user_role1"}],
    )
    full_row = _row(
        "2026-03-01",
        "p1",
        "Citation Graph Paper",
        "A citation graph paper.",
        cited_by_count=42,
        reference_ids=["paper_id:seed"],
    )
    full_row.update({"system_score": 999.0, "drift_bonus": 99.0, "ranking_source": "full_paperflow"})
    _write_jsonl(input_dir / "episode_papers.jsonl", [full_row])

    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=output_dir)

    [candidate] = runner.load_jsonl(output_dir / "candidate_pools.jsonl")
    assert candidate["cited_by_count"] == 42
    assert candidate["reference_ids"] == ["paper_id:seed"]
    for forbidden in clean_export.FORBIDDEN_METHOD_FIELDS:
        assert forbidden not in candidate


def test_citation_enhanced_refuses_full_episode_papers_directly(tmp_path):
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


def test_citation_enhanced_uses_previous_citation_relation_only_after_ranking(tmp_path):
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
                        "description": "alpha planning",
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
            "Seed Alpha Planning",
            "Alpha planning paper selected yesterday.",
            selected=True,
            reference_ids=["paper_id:shared-ref"],
        ),
        _row(
            "2026-03-02",
            "linked",
            "Linked Control Paper",
            "A control paper with sparse content overlap.",
            reference_ids=["paper_id:seed", "paper_id:shared-ref"],
            cited_by_count=2,
        ),
        _row(
            "2026-03-02",
            "unlinked",
            "Unlinked Alpha Paper",
            "Alpha planning paper without citation relation.",
            reference_ids=["paper_id:other-ref"],
            cited_by_count=0,
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
    day2_shown = [
        row for row in output_rows
        if row["episode_id"] == "user_role1::2026-03-02" and row["shown"]
    ]
    day1_rows = [
        row for row in output_rows
        if row["episode_id"] == "user_role1::2026-03-01"
    ]

    assert {row["training_selected_count"] for row in day1_rows} == {0}
    assert day2_shown[0]["paper_id"] == "linked"
    assert day2_shown[0]["citation_direct_link"] is True
    assert day2_shown[0]["training_selected_count"] == 1
    assert day2_shown[0]["oracle_label"] == "irrelevant"


def test_citation_enhanced_parses_string_reference_fields(tmp_path):
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
                        "description": "alpha planning",
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
            "Seed Alpha Planning",
            "Alpha planning paper selected yesterday.",
            selected=True,
            reference_ids="paper_id:shared-ref;paper_id:old-ref",
        ),
        _row(
            "2026-03-02",
            "linked",
            "Linked Control Paper",
            "A control paper with sparse content overlap.",
            reference_ids="paper_id:seed,paper_id:shared-ref",
        ),
        _row(
            "2026-03-02",
            "unlinked",
            "Unlinked Alpha Paper",
            "Alpha planning paper without citation relation.",
            reference_ids="paper_id:other-ref",
        ),
    ]
    _write_jsonl(input_dir / "episode_papers.jsonl", paper_rows)

    clean_dir = tmp_path / "clean"
    clean_export.export_clean_benchmark(input_dir=input_dir, output_dir=clean_dir)
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=clean_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    day2_rows = [
        row for row in runner.load_jsonl(output_dir / "episode_papers.jsonl")
        if row["episode_id"] == "user_role1::2026-03-02"
    ]
    linked = next(row for row in day2_rows if row["paper_id"] == "linked")
    unlinked = next(row for row in day2_rows if row["paper_id"] == "unlinked")
    assert linked["citation_direct_link"] is True
    assert linked["citation_relation_score"] > unlinked["citation_relation_score"]


def test_citation_enhanced_clean_input_does_not_rank_by_oracle_label(tmp_path):
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
    _write_jsonl(input_dir / "candidate_pools.jsonl", clean_candidates)
    _write_jsonl(input_dir / "labels_for_eval.jsonl", labels)
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"roles": {"role1": {}}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)

    shown = [row for row in runner.load_jsonl(output_dir / "episode_papers.jsonl") if row["shown"]]
    assert shown[0]["paper_id"] == "p_alpha"
    assert shown[0]["oracle_label"] == "irrelevant"
