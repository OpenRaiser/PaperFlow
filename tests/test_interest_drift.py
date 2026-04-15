"""
Unit tests for drift-aware interest migration.
"""

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")


def _paper(title, embedding, keywords, selected_at):
    return {
        "title": title,
        "embedding": embedding,
        "keywords": keywords,
        "authors": ["Alice"],
        "selected_at": selected_at,
    }


def test_drift_update_enters_shifting_when_short_window_deviates():
    now = datetime(2026, 4, 15, 12, 0, 0)
    history = [
        _paper(
            f"Legacy {idx}",
            [1.0, 0.0, 0.0, 0.0],
            ["legacy-topic"],
            (now - timedelta(days=30 - idx)).isoformat(),
        )
        for idx in range(6)
    ]
    selected = [
        _paper(
            f"New {idx}",
            [0.0, 1.0, 0.0, 0.0],
            ["new-topic"],
            now.isoformat(),
        )
        for idx in range(3)
    ]

    updated = profile_updater.update_profile_with_feedback(
        profile={
            "version": "0.1",
            "core_directions": {"legacy-topic": 0.8},
            "topic_weights": {"legacy-topic": 0.8},
            "interest_vector": [1.0, 0.0, 0.0, 0.0],
        },
        selected_papers=selected,
        skipped_papers=[],
        historical_selected_papers=history,
        current_time=now,
    )

    assert updated["drift_state"]["status"] == "shifting"
    assert updated["drift_state"]["score"] >= 0.35
    assert updated["drift_state"]["adaptive_alpha"] > 0.08
    assert "new-topic" in updated["drift_state"]["top_shift_topics"]


def test_drift_update_stays_stable_when_windows_are_too_small():
    now = datetime(2026, 4, 15, 12, 0, 0)
    history = [
        _paper(
            "Legacy",
            [1.0, 0.0, 0.0, 0.0],
            ["legacy-topic"],
            (now - timedelta(days=2)).isoformat(),
        )
    ]

    updated = profile_updater.update_profile_with_feedback(
        profile={
            "version": "0.1",
            "core_directions": {"legacy-topic": 0.8},
            "topic_weights": {"legacy-topic": 0.8},
            "interest_vector": [1.0, 0.0, 0.0, 0.0],
        },
        selected_papers=history,
        skipped_papers=[],
        historical_selected_papers=history,
        current_time=now,
    )

    assert updated["drift_state"]["status"] == "stable"
    assert updated["drift_state"]["score"] == 0.0


def test_drift_update_enters_recovered_when_score_falls_below_recover_threshold():
    now = datetime(2026, 4, 15, 12, 0, 0)
    history = [
        _paper(
            f"Legacy {idx}",
            [1.0, 0.0, 0.0, 0.0],
            ["legacy-topic"],
            (now - timedelta(days=10 - idx)).isoformat(),
        )
        for idx in range(6)
    ]
    selected = [
        _paper(
            f"Legacy New {idx}",
            [1.0, 0.0, 0.0, 0.0],
            ["legacy-topic"],
            now.isoformat(),
        )
        for idx in range(3)
    ]

    updated = profile_updater.update_profile_with_feedback(
        profile={
            "version": "0.1",
            "core_directions": {"legacy-topic": 0.8},
            "topic_weights": {"legacy-topic": 0.8},
            "interest_vector": [0.6, 0.4, 0.0, 0.0],
            "drift_state": {
                "status": "shifting",
                "score": 0.8,
                "detected_at": (now - timedelta(days=1)).isoformat(),
            },
        },
        selected_papers=selected,
        skipped_papers=[],
        historical_selected_papers=history,
        current_time=now,
    )

    assert updated["drift_state"]["status"] == "recovered"
    assert updated["drift_state"]["score"] <= 0.20


def test_shifting_state_preserves_explicit_prior_floor():
    weights = profile_updater.get_drift_blend_weights("shifting")

    assert weights["explicit"] >= 0.35
    assert weights["explicit"] + weights["long"] + weights["short"] == 1.0
