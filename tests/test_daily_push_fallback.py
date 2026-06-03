from __future__ import annotations

import importlib


def test_fallback_filters_user_handled_papers(test_db_path, sample_paper):
    agent = importlib.import_module("deployments.feishu.daily-push-agent.main")
    db_ops = agent.db_ops
    db_ops.DB_PATH = test_db_path

    selected = dict(sample_paper)
    selected["arxiv_id"] = "2606.00001v1"
    selected["title"] = "Selected Literature Mining Paper"
    skipped = dict(sample_paper)
    skipped["arxiv_id"] = "2606.00002"
    skipped["title"] = "Skipped Scientific Knowledge Graph Paper"
    reported = dict(sample_paper)
    reported["arxiv_id"] = "2606.00003"
    reported["title"] = "Reported Hypothesis Generation Paper"

    selected_id = db_ops.add_paper(selected)
    skipped_id = db_ops.add_paper(skipped)
    reported_id = db_ops.add_paper(reported)

    db_ops.log_behavior("user_test", "push_1", selected_id, "selected", "selected", "selected")
    db_ops.log_behavior("user_test", "push_1", skipped_id, "skipped", "skipped", "skipped")
    db_ops.log_behavior("user_test", "read_1", reported_id, "created_report", "reading", "report")

    candidates = [
        {"arxiv_id": "2606.00001v2", "title": "Selected Literature Mining Paper"},
        {"arxiv_id": "2606.00002", "title": "Skipped Scientific Knowledge Graph Paper"},
        {"arxiv_id": "2606.00003", "title": "Reported Hypothesis Generation Paper"},
        {"arxiv_id": "2606.00004", "title": "Fresh Citation Graph Discovery Paper"},
    ]

    filtered, dropped = agent.filter_user_handled_papers("user_test", candidates)

    assert dropped == 3
    assert [paper["arxiv_id"] for paper in filtered] == ["2606.00004"]


def test_relaxed_fallback_returns_weak_matches(monkeypatch):
    agent = importlib.import_module("deployments.feishu.daily-push-agent.main")

    monkeypatch.setattr(agent, "calculate_paper_score", lambda paper, profile, weights: paper["score"])
    monkeypatch.setattr(agent, "compute_relevance_signal", lambda paper, profile: paper["relevance"])
    monkeypatch.setattr(agent, "compute_drift_bonus", lambda paper, profile, weights: (0.0, []))
    monkeypatch.setattr(agent, "compute_reading_signal_bonus", lambda paper, profile, weights: (0.0, []))
    monkeypatch.setattr(agent, "is_must_read", lambda paper, profile: False)

    scored = agent.build_relaxed_fallback_scores(
        [
            {"title": "A", "score": 0.10, "relevance": 0.01},
            {"title": "B", "score": 0.20, "relevance": 0.02},
        ],
        profile={},
        weights={},
        top_k=1,
    )

    assert len(scored) == 1
    assert scored[0].paper["title"] == "B"
    assert scored[0].category == "edge_relevant"
