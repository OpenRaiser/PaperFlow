import json
from pathlib import Path

from experiments.benchmark import evaluate_simulation_metrics as metrics


def test_evaluate_episode_computes_ranking_and_selection_metrics():
    rows = [
        {
            "episode_id": "u1::2026-03-01",
            "shown": True,
            "selected": True,
            "system_rank": 1,
            "system_label": "high_relevant",
            "oracle_label": "strong_relevant",
        },
        {
            "episode_id": "u1::2026-03-01",
            "shown": True,
            "selected": False,
            "system_rank": 2,
            "system_label": "maybe_interested",
            "oracle_label": "irrelevant",
        },
        {
            "episode_id": "u1::2026-03-01",
            "shown": True,
            "selected": True,
            "system_rank": 3,
            "system_label": "edge_relevant",
            "oracle_label": "relevant",
        },
        {
            "episode_id": "u1::2026-03-01",
            "shown": False,
            "selected": False,
            "system_rank": None,
            "system_label": "edge_relevant",
            "oracle_label": "relevant",
        },
    ]

    result = metrics.evaluate_episode(rows, [1, 3])

    assert result["metric_basis"] == "selected"
    assert result["selected_total"] == 2
    assert result["relevant_total"] == 2
    assert result["oracle_relevant_total"] == 3
    assert result["per_k"]["1"]["precision"] == 1.0
    assert result["per_k"]["1"]["recall"] == 1 / 2
    assert result["per_k"]["3"]["precision"] == 2 / 3
    assert result["per_k"]["3"]["recall"] == 1.0
    assert result["oracle_per_k"]["1"]["precision"] == 1.0
    assert result["oracle_per_k"]["1"]["recall"] == 1 / 3
    assert result["oracle_per_k"]["3"]["precision"] == 2 / 3
    assert result["case_per_k"]["3"]["useful_rate"] == 2 / 3
    assert result["case_per_k"]["3"]["strict_recall_positive"] == 2 / 3
    assert result["case_per_k"]["3"]["system_high_rate"] == 1 / 3
    assert result["selection_rate"]["high_relevant"]["rate"] == 1.0
    assert result["selection_rate"]["maybe_interested"]["rate"] == 0.0


def test_main_writes_evaluation_file(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "simulation_case"
    input_dir.mkdir()
    (input_dir / "episode_papers.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "date": "2026-03-01",
                        "episode_id": "u1::2026-03-01",
                        "shown": True,
                        "selected": True,
                        "system_rank": 1,
                        "system_label": "high_relevant",
                        "oracle_label": "strong_relevant",
                    }
                ),
                json.dumps(
                    {
                        "date": "2026-03-01",
                        "episode_id": "u1::2026-03-01",
                        "shown": False,
                        "selected": False,
                        "system_rank": None,
                        "system_label": "edge_relevant",
                        "oracle_label": "relevant",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_file = input_dir / "metrics.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_simulation_metrics.py",
            "--input-dir",
            str(input_dir),
            "--ks",
            "1",
            "5",
            "--output-file",
            str(output_file),
        ],
    )

    metrics.main()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["summary"]["episodes"] == 1
    assert payload["summary"]["metric_basis"] == "episode_macro"
    assert payload["dataset_summary"]["episodes"] == 1
    assert payload["dataset_summary"]["pool_oracle_label_counts"]["strong_relevant"] == 1
    assert "1" in payload["summary"]["macro"]["per_k"]
    assert "1" in payload["summary"]["macro"]["oracle_per_k"]
    assert "1" in payload["summary"]["macro"]["case_per_k"]
    assert (input_dir / "case_metrics_table_top20.md").exists()
    assert (input_dir / "dataset_summary.json").exists()
    assert (input_dir / "dataset_summary.md").exists()
    assert "System-High@20 up" not in (input_dir / "case_metrics_table_top20.md").read_text(encoding="utf-8")
    assert "LowRel@20 down" not in (input_dir / "case_metrics_table_top20.md").read_text(encoding="utf-8")


def test_precision_at_k_uses_fixed_k_denominator_when_shown_list_is_short():
    rows = [
        {
            "episode_id": "u1::2026-03-01",
            "shown": True,
            "selected": True,
            "system_rank": 1,
            "system_label": "high_relevant",
            "oracle_label": "strong_relevant",
        },
        {
            "episode_id": "u1::2026-03-01",
            "shown": True,
            "selected": False,
            "system_rank": 2,
            "system_label": "edge_relevant",
            "oracle_label": "irrelevant",
        },
    ]

    result = metrics.evaluate_episode(rows, [5])

    assert result["per_k"]["5"]["precision"] == 1 / 5
    assert result["oracle_per_k"]["5"]["precision"] == 1 / 5
    assert result["per_k"]["5"]["recall"] == 1.0
