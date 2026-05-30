import csv
import json

from experiments.human_eval import aggregate_drift_human_eval as drift_agg
from experiments.human_eval import aggregate_model_human_eval as model_agg
from experiments.human_eval import build_drift_human_eval_packet as drift_packet
from experiments.human_eval import build_model_human_eval_packet as model_packet


def write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_model_packet_hides_model_identity_and_keeps_internal_key(tmp_path):
    model_dir = tmp_path / "model_outputs"
    model_dir.mkdir()
    write_jsonl(
        model_dir / "reading_reports.jsonl",
        [
            {
                "episode_id": "episode_1",
                "paper_id": "paper_1",
                "user_id": "user_1",
                "title": "Paper title",
                "abstract": "Paper abstract",
                "authors": ["A. Author"],
                "report_payload": {
                    "one_sentence_summary": "Useful summary.",
                    "core_method": "A concrete method.",
                },
            }
        ],
    )
    write_jsonl(
        model_dir / "episode_papers.jsonl",
        [
            {
                "episode_id": "episode_1",
                "paper_id": "paper_1",
                "user_id": "user_1",
                "reason": "Matches the user's current work.",
                "system_rank": 3,
                "system_score": 0.72,
                "oracle_label": "relevant",
                "selected": True,
            }
        ],
    )

    blind, key = model_packet.build_rows(
        [("model_a", "Model A", model_dir)],
        {"user_1": {"description": "Works on scientific recommendation.", "seed_directions": {"recommender-systems": {}}}},
        reports_per_model=1,
        seed=7,
        abstract_chars=200,
        report_chars=1000,
    )

    assert len(blind) == 1
    assert len(key) == 1
    assert "model_key" not in blind[0]
    assert "system_rank" not in blind[0]
    assert blind[0]["reading_report"]
    assert key[0]["model_key"] == "model_a"
    assert key[0]["system_rank"] == 3


def test_model_human_aggregation_formula_and_auto_score_join(tmp_path):
    blind_rows = [
        {
            "sample_id": "HMODEL_00001",
            "HumanRelevance": "4",
            "HumanUsefulness": "5",
            "RecommendationDecisionHelpfulness": "3",
            "ReportFaithfulness": "5",
            "ReportSpecificity": "4",
            "ReportDecisionHelpfulness": "4",
            "comments": "ok",
        }
    ]
    key_rows = [{"sample_id": "HMODEL_00001", "model_key": "model_a", "model_name": "Model A"}]
    auto_csv = tmp_path / "auto.csv"
    write_csv(
        auto_csv,
        [
            {
                "model_key": "model_a",
                "RecommendationScore": "70",
                "ReportProxyScore": "80",
                "ReportSuccessRate": "1.0",
                "CostUSDProxy": "0.1234",
            }
        ],
    )

    scored = model_agg.build_scored_reports(blind_rows, key_rows)
    summary = model_agg.aggregate_model_scores(scored, model_agg.load_auto_summary(auto_csv))

    assert scored[0]["HumanRecommendationScore"] == "80.0000"
    assert scored[0]["ReportHumanScore"] == "86.6667"
    assert scored[0]["ModelHumanScore"] == "82.6667"
    assert summary[0]["ModelAutoScore"] == "74.5000"
    assert summary[0]["ReportAutoScore"] == "80.0000"
    assert summary[0]["ParsingSuccess"] == "100.0000"
    assert summary[0]["TokenCost"] == "0.1234"


def test_drift_packet_samples_post_drift_new_topic_rows(tmp_path):
    method_dir = tmp_path / "method"
    method_dir.mkdir()
    write_jsonl(
        method_dir / "episode_papers.jsonl",
        [
            {
                "shown": True,
                "user_id": "user_1",
                "date": "2026-03-03",
                "episode_id": "episode_1",
                "paper_id": "paper_1",
                "title": "New topic paper",
                "abstract": "This paper studies the new topic.",
                "topics": ["new-topic"],
                "authors": ["A. Author"],
                "system_rank": 1,
                "oracle_label": "relevant",
                "selected": True,
            }
        ],
    )
    events = [
        {
            "user_id": "user_1",
            "date": "2026-03-02",
            "anchor_topics": ["new-topic"],
            "suppressed_topics": ["old-topic"],
        }
    ]

    blind, key = drift_packet.build_rows(
        [("full_paperflow", "Full PaperFlow", method_dir)],
        events,
        {"user_1": {"description": "A user profile."}},
        papers_per_event=1,
        post_days=7,
        seed=3,
        abstract_chars=200,
    )

    assert len(blind) == 1
    assert "method_key" not in blind[0]
    assert blind[0]["new_interest_topics"] == "new-topic"
    assert key[0]["new_topic_match"] is True
    assert key[0]["old_topic_match"] is False


def test_drift_human_aggregation_formula_and_proxy_score():
    blind_rows = [
        {
            "sample_id": "HDRIFT_00001",
            "NewTopicFit": "5",
            "AdaptationAppropriateness": "4",
            "OldNewBalance": "3",
            "DriftDecisionHelpfulness": "4",
            "comments": "ok",
        }
    ]
    key_rows = [
        {
            "sample_id": "HDRIFT_00001",
            "method_key": "full_paperflow",
            "method_name": "Full PaperFlow",
            "event_user_id": "user_1",
            "event_date": "2026-03-02",
            "system_rank": "1",
            "selected": "True",
            "new_topic_match": "True",
            "old_topic_match": "False",
        }
    ]

    scored = drift_agg.build_scored_rows(blind_rows, key_rows)
    event_scores = drift_agg.aggregate_event_scores(scored)
    method_scores = drift_agg.aggregate_method_scores(event_scores)

    assert scored[0]["AdaptationHumanScore"] == "80.0000"
    assert scored[0]["DriftAutoScore"] == "100.0000"
    assert event_scores[0]["AdaptationHumanScore"] == "80.0000"
    assert method_scores[0]["AdaptationHumanScore"] == "80.0000"
