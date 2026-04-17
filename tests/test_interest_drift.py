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


def test_single_reading_signal_stays_conservative_and_does_not_trigger_drift():
    now = datetime(2026, 4, 17, 13, 0, 0)

    updated = profile_updater.update_profile_with_reading_signal(
        profile={
            "version": "0.1",
            "core_directions": {"language": 0.7},
            "topic_weights": {"language": 0.7},
            "drift_state": {"status": "stable", "score": 0.0},
        },
        paper={
            "title": "Protein Language Models for Discovery",
            "abstract": "We study protein language models for scientific discovery.",
        },
        parsed_pdf={
            "inferred_topics": ["protein language model"],
            "inferred_directions": [{"name": "Protein Language Model", "confidence": 0.66}],
        },
        signal_strength="weak",
        current_time=now,
        source_type="feishu_file_key",
        source_key="file_v3_signal_1",
    )

    assert updated["drift_state"]["status"] == "stable"
    assert "protein-language-model" in updated["topic_weights"]
    assert "protein-language-model" not in updated["reading_signal_state"]["short_term_topics"]
    assert updated["reading_signal_state"]["last_signal"]["strength"] == "weak"


def test_repeated_reading_signals_activate_upload_short_term_interest():
    now = datetime(2026, 4, 17, 13, 0, 0)
    profile = {
        "version": "0.1",
        "core_directions": {"language": 0.7},
        "topic_weights": {"language": 0.7},
    }

    first = profile_updater.update_profile_with_reading_signal(
        profile=profile,
        signal_topics=["GUI Agent"],
        signal_strength="weak",
        current_time=now,
        source_type="feishu_file_key",
        source_key="file_v3_signal_2",
    )
    second = profile_updater.update_profile_with_reading_signal(
        profile=first,
        signal_topics=["GUI Agent"],
        signal_strength="weak",
        current_time=now + timedelta(minutes=5),
        source_type="feishu_file_key",
        source_key="file_v3_signal_3",
    )

    assert second["reading_signal_state"]["recent_topics"]["gui-agent"]["count"] == 2
    assert "gui-agent" in second["reading_signal_state"]["short_term_topics"]
    assert second["reading_signal_state"]["last_signal"]["activated_topics"] == ["gui-agent"]


def test_explicit_reading_signal_immediately_activates_short_term_topic_and_seeds_core_direction():
    now = datetime(2026, 4, 17, 13, 30, 0)

    updated = profile_updater.update_profile_with_reading_signal(
        profile={"version": "0.1", "core_directions": {}, "topic_weights": {}},
        signal_topics=["Scientific Reasoning"],
        signal_strength="strong",
        explicit_text="这类我最近想多看",
        current_time=now,
        source_type="feishu_file_key",
        source_key="file_v3_signal_4",
    )

    assert updated["core_directions"]["scientific-reasoning"] >= 0.45
    assert "scientific-reasoning" in updated["reading_signal_state"]["short_term_topics"]
    assert updated["reading_signal_state"]["last_signal"]["strength"] == "strong"
    assert updated["reading_signal_state"]["last_signal"]["explicit_note"] == "这类我最近想多看"
