import json
from pathlib import Path

import pytest

from experiments.baselines.scinup_strict import runner


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
        "oracle_score": 0.0,
        "oracle_label": oracle_label,
    }
    row.update(extra)
    return row


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


def _write_clean_user(input_dir: Path, description="alpha agent benchmark methods"):
    (input_dir / "users.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user_id": "user_role1",
                        "role_name": "role1",
                        "description": description,
                        "seed_directions": {"alpha-agent": 0.8},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_scinup_strict_refuses_full_episode_papers_directly(tmp_path):
    input_dir = tmp_path / "benchmark"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_jsonl(input_dir / "episode_papers.jsonl", [_row("2026-03-01", "p1", "Alpha", "Alpha.")])

    with pytest.raises(FileNotFoundError, match="refuses to read Full PaperFlow episode_papers"):
        runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=tmp_path / "roles.json", top_k=1)


def test_scinup_strict_ranks_with_bm25_query_profile_only(tmp_path):
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
            "Quantum Chemistry Simulation",
            "A chemistry simulator with molecular orbitals.",
            selected=True,
            oracle_label="strong_relevant",
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
    roles_file.write_text(json.dumps({"roles": {}}), encoding="utf-8")

    runner.run_baseline(input_dir=input_dir, output_dir=output_dir, roles_file=roles_file, top_k=1)
    output_rows = runner.load_jsonl(output_dir / "episode_papers.jsonl")
    shown = [row for row in output_rows if row["shown"]]

    assert shown[0]["paper_id"] == "p_alpha"
    assert shown[0]["ranking_source"] == "baselines.nl_profile.runner"
    assert shown[0]["uses_paperflow_direction_expansion"] is False
    assert shown[0]["uses_feedback_update"] is False
    assert shown[0]["oracle_label"] == "irrelevant"


def test_scinup_strict_does_not_use_role_secondary_or_must_read_terms(tmp_path):
    role = {
        "description": "alpha agent methods",
        "seed_directions": [{"canonical_name": "alpha-agent", "bootstrap_phrase": "alpha agent"}],
        "secondary_topics": ["forbidden booster"],
        "must_read_keywords": ["forbidden booster"],
    }

    profile = runner.build_query_profile({"description": ""}, role)

    assert "alpha agent" in profile["query_text"]
    assert "forbidden booster" not in profile["query_text"]


def test_scinup_strict_dict_seed_directions_do_not_leak_python_repr():
    profile = runner.build_query_profile(
        {
            "description": "alpha agent methods",
            "seed_directions": {"alpha-agent": 0.8, "benchmark-method": 0.6},
        },
        {},
    )

    assert "dict_keys" not in profile["query_text"]
    assert "alpha-agent" in profile["query_text"]
    assert "benchmark-method" in profile["query_text"]
