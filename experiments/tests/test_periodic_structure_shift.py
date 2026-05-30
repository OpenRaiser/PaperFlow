import importlib


drift_engine = importlib.import_module("scripts.drift_engine")


def _matching_checkfile():
    return {
        "name": "topic_shift",
        "drift_method": "topic_weight_decay",
        "params": {"emerging_topics_pool": ["multimodal-reasoning"]},
        "trigger": {"type": "selected_paper_topic_match", "min_count": 2},
        "_source_file": "01_topic_shift.json",
    }


def test_simulation_observing_failure_only_has_one_day_cooldown(monkeypatch):
    monkeypatch.setattr(drift_engine.random, "random", lambda: 0.0)

    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72},
        "topic_weights": {"gui-agent": 0.72},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {"shift_topics": ["multimodal-reasoning"]},
        "drift_state": {"status": "stable", "score": 0.0},
    }
    selected = [
        {"title": "Multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "Multimodal reasoning for agents", "abstract": "", "categories": [], "authors": []},
    ]

    day1, event1 = engine.advance_profile_drift(
        profile,
        selected_papers=selected,
        date="2026-03-01",
        drift_probability=0.5,
        strategy_mode=drift_engine.STRATEGY_SIMULATION,
    )
    reset_profile = drift_engine._reset_to_stable_after_observing(day1, "2026-03-02")
    reset_profile["drift_state"]["episode_index"] = 2
    day3, event3 = engine.advance_profile_drift(
        reset_profile,
        selected_papers=selected,
        date="2026-03-03",
        drift_probability=0.5,
        strategy_mode=drift_engine.STRATEGY_SIMULATION,
    )

    assert event1 is not None
    assert event1["method"] == "checkfile_trigger"
    assert event3 is not None
    assert event3["method"] == "checkfile_trigger"


def test_simulation_opportunity_cap_is_five(monkeypatch):
    monkeypatch.setattr(drift_engine.random, "random", lambda: 0.0)

    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72},
        "topic_weights": {"gui-agent": 0.72},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {"shift_topics": ["multimodal-reasoning"]},
        "drift_state": {
            "status": "stable",
            "score": 0.0,
            "drift_opportunity_count": 5,
            "max_drift_opportunities": 5,
        },
    }
    selected = [
        {"title": "Multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "Multimodal reasoning for agents", "abstract": "", "categories": [], "authors": []},
    ]

    updated, event = engine.advance_profile_drift(
        profile,
        selected_papers=selected,
        date="2026-03-09",
        drift_probability=0.5,
        strategy_mode=drift_engine.STRATEGY_SIMULATION,
    )

    assert event is None
    assert updated["drift_state"]["hidden_anchor"] is None
    assert updated["drift_state"]["drift_opportunity_count"] == 5
