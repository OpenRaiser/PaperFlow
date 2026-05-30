import importlib
from datetime import datetime, timedelta


profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
daily_push = importlib.import_module("deployments.feishu.daily-push-agent.main")


def _paper(title, embedding, keywords, selected_at):
    return {
        "title": title,
        "abstract": " ".join(keywords),
        "embedding": embedding,
        "keywords": keywords,
        "categories": keywords,
        "topics": keywords,
        "authors": ["Alice"],
        "selected_at": selected_at,
    }


def test_update_profile_with_feedback_initializes_hidden_anchor_and_locks_after_consistent_signal():
    now = datetime(2026, 4, 15, 12, 0, 0)
    profile = {
        "version": "0.1",
        "core_directions": {"gui-agent": 0.8},
        "topic_weights": {"gui-agent": 0.8},
        "interest_vector": [1.0, 0.0, 0.0, 0.0],
        "drift_plan": {
            "shift_topics": ["multimodal-reasoning"],
            "downweight_topics": ["gui-agent"],
        },
    }

    selected = [
        _paper(
            f"New {idx} multimodal reasoning",
            [0.0, 1.0, 0.0, 0.0],
            ["multimodal-reasoning"],
            now.isoformat(),
        )
        for idx in range(3)
    ]

    day1 = profile_updater.update_profile_with_feedback(profile, selected, [], historical_selected_papers=[], current_time=now)
    day2 = profile_updater.update_profile_with_feedback(day1, selected, [], historical_selected_papers=selected, current_time=now + timedelta(days=1))
    day3 = profile_updater.update_profile_with_feedback(day2, selected, [], historical_selected_papers=selected * 2, current_time=now + timedelta(days=2))

    assert day1["drift_state"]["hidden_anchor"] == "multimodal-reasoning"
    assert day2["drift_state"]["status"] in {"observing", "stable", "shifting"}
    assert day3["drift_state"]["anchor_topic"] == "multimodal-reasoning"
    assert day3["drift_state"]["commitment_days_remaining"] >= 0
    assert "multimodal reasoning" not in (day3.get("must_read", {}).get("keywords", []) or [])
    assert "multimodal-reasoning" not in (day3.get("must_read", {}).get("keywords", []) or [])


def test_daily_push_relevance_signal_uses_anchor_topic_bonus():
    profile = {
        "interest_vector": [0.0, 0.0, 0.0],
        "topic_weights": {"gui-agent": 0.8},
        "drift_state": {
            "status": "stable",
            "hidden_anchor": "multimodal-reasoning",
            "anchor_topic": "multimodal-reasoning",
            "anchor_progress": 0.5,
            "commitment_days_remaining": 2,
        },
    }
    paper = {
        "embedding": [],
        "topics": ["multimodal-reasoning"],
        "authors": [],
        "institution": "",
    }

    signal = daily_push.compute_relevance_signal(paper, profile)
    bonus, topics = daily_push.compute_drift_bonus(paper, profile, {})

    assert signal > 0.0
    assert bonus > 0.0
    assert topics == ["multimodal-reasoning"]


def test_manual_suppressed_topics_override_anchor_and_reduce_recommendation():
    profile = {
        "interest_vector": [0.0, 0.0, 0.0],
        "topic_weights": {"gui-agent": 0.8},
        "drift_state": {
            "status": "stable",
            "manual_suppressed_topics": ["gui-agent"],
        },
    }
    paper = {
        "embedding": [],
        "topics": ["gui-agent"],
        "keywords": ["gui-agent"],
        "title": "GUI agent benchmark",
        "abstract": "gui agent evaluation",
        "authors": [],
        "institution": "",
        "quality_score": 0.5,
    }

    score = profile_updater.calculate_paper_score(paper, profile)
    signal = daily_push.compute_relevance_signal(paper, profile)

    assert score < 0.5
    assert signal < 0.8


def test_real_user_inactivity_decay_starts_after_seven_days():
    now = datetime(2026, 4, 22, 12, 0, 0)
    profile = {
        "version": "0.1",
        "core_directions": {"gui-agent": 0.8},
        "topic_weights": {"gui-agent": 0.8},
        "reading_history": [
            {
                "selected_at": (now - timedelta(days=8)).isoformat(),
                "action": "selected",
                "topics": ["gui-agent"],
            }
        ],
    }

    updated = profile_updater.update_profile_with_feedback(
        profile,
        selected_papers=[],
        skipped_papers=[],
        historical_selected_papers=[],
        current_time=now,
        apply_anchor_drift=False,
    )

    assert updated["core_directions"]["gui-agent"] < 0.8
    assert updated["topic_weights"]["gui-agent"] < 0.8


def test_real_user_inactivity_decay_is_stronger_after_fifteen_days():
    now = datetime(2026, 4, 22, 12, 0, 0)
    profile = {
        "version": "0.1",
        "core_directions": {"gui-agent": 0.8},
        "topic_weights": {"gui-agent": 0.8},
        "must_read": {"authors": [], "institutions": [], "keywords": ["gui-agent"]},
        "reading_history": [
            {
                "selected_at": (now - timedelta(days=16)).isoformat(),
                "action": "selected",
                "topics": ["gui-agent"],
            }
        ],
    }

    updated = profile_updater.update_profile_with_feedback(
        profile,
        selected_papers=[],
        skipped_papers=[],
        historical_selected_papers=[],
        current_time=now,
        apply_anchor_drift=False,
    )

    assert updated["core_directions"]["gui-agent"] <= 0.6
    assert updated["topic_weights"]["gui-agent"] <= 0.6
    assert "gui-agent" not in updated["must_read"]["keywords"]
