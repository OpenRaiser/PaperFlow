import importlib


drift_engine = importlib.import_module("scripts.drift_engine")
sim = importlib.import_module("experiments.simulation.simulate_historical_episodes")


def _matching_checkfile():
    return {
        "name": "topic_shift",
        "drift_method": "topic_weight_decay",
        "params": {"emerging_topics_pool": ["multimodal-reasoning"]},
        "trigger": {"type": "selected_paper_topic_match", "min_count": 2},
        "_source_file": "01_topic_shift.json",
    }


def test_update_drift_state_enters_shifting_on_positive_delta():
    profile = {"drift_state": {"status": "stable", "score": 0.1}}
    updated = drift_engine._update_drift_state(profile, "2026-03-01", score_delta=0.25)

    assert updated["status"] == "shifting"
    assert updated["score"] == 0.35


def test_update_drift_state_enters_recovered_before_returning_stable():
    shifting_profile = {"drift_state": {"status": "shifting", "score": 0.50}}
    recovered = drift_engine._update_drift_state(shifting_profile, "2026-03-02", score_delta=-0.18)
    still_recovered = drift_engine._update_drift_state({"drift_state": recovered}, "2026-03-03", score_delta=-0.12)
    stable = drift_engine._update_drift_state({"drift_state": still_recovered}, "2026-03-04", score_delta=-0.21)

    assert recovered["status"] == "recovered"
    assert still_recovered["status"] == "recovered"
    assert stable["status"] == "stable"
    assert stable["score"] == 0.0


def test_apply_drift_skips_when_trigger_not_satisfied():
    checkfile = {
        "name": "keyword_shift",
        "drift_method": "keyword_emergence",
        "params": {"new_keywords_pool": ["graph neural network"], "add_count": 1},
        "trigger": {"type": "keyword_frequency", "min_count": 2},
    }
    profile = {"must_read": {"keywords": []}, "drift_state": {"status": "stable", "score": 0.0}}
    selected_papers = [{"title": "Unrelated paper", "abstract": "No matching terms here", "categories": [], "authors": []}]

    updated_profile, drift_event = drift_engine.DriftEngine([checkfile]).apply_drift(
        profile=profile,
        checkfile=checkfile,
        selected_papers=selected_papers,
        date="2026-03-01",
    )

    assert drift_event is None
    assert updated_profile == profile


def test_check_recovery_moves_shifting_to_recovered_without_resetting_daily_score():
    user = {
        "user_id": "user_role1",
        "profile": {
            "core_directions": {"multimodal-reasoning": 0.8, "gui-agent": 0.6},
            "topic_weights": {"multimodal-reasoning": 0.8, "gui-agent": 0.6},
            "drift_state": {
                "status": "shifting",
                "score": 0.50,
                "anchor_topic": "multimodal-reasoning",
                "baseline_core_directions": {"gui-agent": 0.7},
            },
        },
    }
    selected_for_reading = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "GUI agent benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "GUI automation", "abstract": "", "categories": [], "authors": []},
    ]

    recovery_event = sim._check_recovery(user, selected_for_reading, "2026-03-02")

    assert recovery_event is not None
    assert recovery_event["event_type"] == "recovery"
    assert user["profile"]["drift_state"]["status"] == "recovered"
    assert user["profile"]["drift_state"]["recovery_mode"] == "rebalance"
    assert user["profile"]["drift_state"]["score"] < 0.50


def test_check_recovery_keeps_recovered_until_score_falls_near_zero():
    user = {
        "user_id": "user_role1",
        "profile": {
            "core_directions": {"multimodal-reasoning": 0.8, "gui-agent": 0.6},
            "topic_weights": {"multimodal-reasoning": 0.8, "gui-agent": 0.6},
            "drift_state": {
                "status": "shifting",
                "score": 0.30,
                "anchor_topic": "multimodal-reasoning",
                "baseline_core_directions": {"gui-agent": 0.7},
            },
        },
    }
    selected_for_reading = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "GUI agent benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "GUI automation", "abstract": "", "categories": [], "authors": []},
    ]

    recovery_event = sim._check_recovery(user, selected_for_reading, "2026-03-02")

    assert recovery_event is not None
    assert recovery_event["event_type"] == "recovery"
    assert user["profile"]["drift_state"]["status"] == "recovered"
    assert user["profile"]["drift_state"]["score"] > 0.0


def test_create_drift_event_marks_recovery_transitions():
    event = drift_engine.create_drift_event(
        user_id="user_role1",
        date="2026-03-03",
        drift_event={"event_type": "recovery", "method": "recovery_feedback"},
        profile_before={"drift_state": {"status": "recovered", "score": 0.1}},
        profile_after={"drift_state": {"status": "stable", "score": 0.0}},
    )

    assert event["event_type"] == "recovery"
    assert event["transition"] == "recovered → stable"
    assert event["display_transition"] == "recovered → stable"
    assert event["display_status"] == "stable"
    assert event["display_score"] == 0.0
    assert event["internal_transition"] == "recovered → stable"
    assert event["internal_status"] == "stable"
    assert event["score_delta"] == -0.1

def test_create_drift_event_preserves_recovered_display_state():
    event = drift_engine.create_drift_event(
        user_id="user_role1",
        date="2026-03-03",
        drift_event={"event_type": "recovery", "method": "anchor_recovery"},
        profile_before={"drift_state": {"status": "shifting", "score": 0.30}},
        profile_after={"drift_state": {"status": "recovered", "score": 0.1}},
    )

    assert event["event_type"] == "recovery"
    assert event["transition"] == "shifting → recovered"
    assert event["display_transition"] == "shifting → recovered"
    assert event["display_status"] == "recovered"
    assert event["display_score"] == 0.1
    assert event["internal_transition"] == "shifting → recovered"
    assert event["internal_status"] == "recovered"

def test_anchor_drift_requires_consistent_multi_day_signal_before_lock(monkeypatch):
    monkeypatch.setattr(drift_engine.random, "random", lambda: 0.0)

    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72, "web-agent": 0.56},
        "topic_weights": {"gui-agent": 0.72, "web-agent": 0.56},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {
            "shift_topics": ["multimodal-reasoning"],
            "downweight_topics": ["web-agent"],
        },
        "drift_state": {"status": "stable", "score": 0.0, "last_drift_date": None},
    }
    selected = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "Robust multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "General GUI control", "abstract": "", "categories": [], "authors": []},
    ]

    day1_profile, day1_event = engine.advance_profile_drift(profile, selected_papers=selected, date="2026-03-01", drift_probability=0.5)
    day2_profile, day2_event = engine.advance_profile_drift(day1_profile, selected_papers=selected, date="2026-03-02", drift_probability=0.5)

    assert day1_event is not None
    assert day1_event["method"] == "checkfile_trigger"
    assert day2_event is not None
    assert day2_event["method"] == "anchor_lock"
    assert day2_profile["drift_state"]["anchor_topic"] == "multimodal-reasoning"
    assert day2_profile["drift_state"]["status"] == "shifting"
    assert day2_profile["drift_state"]["score"] >= 0.30
    assert day2_profile["drift_state"]["anchor_progress"] > 0.0
    assert day2_profile["must_read"]["keywords"] == ["gui agent"]


def test_anchor_drift_progresses_deterministically_after_lock(monkeypatch):
    monkeypatch.setattr(drift_engine.random, "random", lambda: 0.0)

    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72, "web-agent": 0.56},
        "topic_weights": {"gui-agent": 0.72, "web-agent": 0.56},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {
            "shift_topics": ["multimodal-reasoning"],
            "downweight_topics": ["web-agent"],
        },
        "drift_state": {
            "status": "shifting",
            "score": 0.4,
            "last_drift_date": "2026-03-03",
            "anchor_topic": "multimodal-reasoning",
            "anchor_topics": ["multimodal-reasoning"],
            "anchor_progress": 0.25,
            "commitment_days_remaining": 3,
        },
    }

    updated_profile, event = engine.advance_profile_drift(profile, selected_papers=[], date="2026-03-04", drift_probability=0.5)

    assert event is None
    assert updated_profile["drift_state"]["anchor_progress"] == 0.65
    assert updated_profile["drift_state"]["commitment_days_remaining"] == 2
    assert updated_profile["core_directions"]["multimodal-reasoning"] > 0.35
    assert updated_profile["core_directions"]["web-agent"] < 0.56
    assert updated_profile["must_read"]["keywords"] == ["gui agent"]


def test_recovery_is_blocked_during_anchor_commitment():
    user = {
        "user_id": "user_role1",
        "profile": {
            "drift_state": {
                "status": "shifting",
                "score": 0.6,
                "anchor_topic": "multimodal-reasoning",
                "anchor_progress": 0.5,
                "commitment_days_remaining": 2,
            }
        },
    }
    selected_for_reading = [
        {"relevance_level": "must_read"},
        {"relevance_level": "high_relevant"},
        {"relevance_level": "high_relevant"},
        {"relevance_level": "edge_relevant"},
    ]

    recovery_event = sim._check_recovery(user, selected_for_reading, "2026-03-05")

    assert recovery_event is None
    assert user["profile"]["drift_state"]["status"] == "shifting"
    assert user["profile"]["drift_state"]["score"] == 0.6


def test_anchor_recovery_can_stabilize_after_new_direction_consolidates():
    profile = {
        "core_directions": {"multimodal-reasoning": 0.9},
        "topic_weights": {"multimodal-reasoning": 0.9},
        "drift_state": {
            "status": "recovered",
            "score": 0.10,
            "anchor_topic": "multimodal-reasoning",
            "baseline_core_directions": {"gui-agent": 0.7},
        },
    }
    updated_profile, event = drift_engine.advance_anchor_recovery(
        profile,
        selected_papers=[
            {"title": "Multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
            {"title": "Multimodal reasoning for agents", "abstract": "", "categories": [], "authors": []},
        ],
        date="2026-03-06",
        strategy_mode=drift_engine.STRATEGY_SIMULATION,
    )

    assert event is not None
    assert event["recovery_mode"] == "consolidate_new"
    assert updated_profile["drift_state"]["status"] == "stable"


def test_anchor_lock_caps_long_shift_episode_start_for_shorter_runs(monkeypatch):
    monkeypatch.setattr(drift_engine.random, "random", lambda: 0.0)

    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72, "web-agent": 0.56},
        "topic_weights": {"gui-agent": 0.72, "web-agent": 0.56},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {
            "shift_topics": ["multimodal-reasoning"],
            "downweight_topics": ["web-agent"],
            "shift_episode_start": 5,
        },
        "drift_state": {"status": "stable", "score": 0.0, "last_drift_date": None},
    }
    selected = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "Robust multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "General GUI control", "abstract": "", "categories": [], "authors": []},
    ]

    day1_profile, day1_event = engine.advance_profile_drift(
        profile,
        selected_papers=selected,
        date="2026-03-01",
        drift_probability=0.5,
    )
    day2_profile, day2_event = engine.advance_profile_drift(
        day1_profile,
        selected_papers=selected,
        date="2026-03-02",
        drift_probability=0.5,
    )

    assert day1_event is not None
    assert day2_event is not None
    assert day2_profile["drift_state"]["anchor_topic"] == "multimodal-reasoning"


def test_hidden_anchor_is_sampled_once_and_observation_tracks_that_topic(monkeypatch):
    monkeypatch.setattr(drift_engine.random, "random", lambda: 0.0)

    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72, "web-agent": 0.56},
        "topic_weights": {"gui-agent": 0.72, "web-agent": 0.56},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {
            "shift_topics": ["multimodal-reasoning", "computer-using-agent"],
            "downweight_topics": ["web-agent"],
        },
        "drift_state": {"status": "stable", "score": 0.0, "last_drift_date": None},
    }
    selected = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "Robust multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
        {"title": "Computer using agent control", "abstract": "", "categories": [], "authors": []},
    ]

    day1_profile, day1_event = engine.advance_profile_drift(profile, selected_papers=selected, date="2026-03-01", drift_probability=0.5)
    day2_profile, day2_event = engine.advance_profile_drift(day1_profile, selected_papers=selected, date="2026-03-02", drift_probability=0.5)

    assert day1_event is not None
    assert day2_event is not None
    assert day2_profile["drift_state"]["hidden_anchor"] == "multimodal-reasoning"
    assert day2_profile["drift_state"]["anchor_topic"] == "multimodal-reasoning"
    assert day2_profile["drift_state"]["intent_score"] >= 0.15


def test_observing_can_timeout_after_two_days_without_anchor_hits():
    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72},
        "topic_weights": {"gui-agent": 0.72},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {"shift_topics": ["multimodal-reasoning"]},
        "drift_state": {"status": "stable", "score": 0.0},
    }
    selected = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "Robust multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
    ]

    day1_profile, day1_event = engine.advance_profile_drift(
        profile,
        selected_papers=selected,
        date="2026-03-01",
        drift_probability=0.5,
    )
    no_anchor_selected = [
        {"title": "General GUI control", "abstract": "", "categories": [], "authors": []},
        {"title": "Web control benchmark", "abstract": "", "categories": [], "authors": []},
    ]
    day2_profile, day2_event = engine.advance_profile_drift(
        day1_profile,
        selected_papers=no_anchor_selected,
        date="2026-03-02",
        drift_probability=0.5,
    )
    day3_profile, day3_event = engine.advance_profile_drift(
        day2_profile,
        selected_papers=no_anchor_selected,
        date="2026-03-03",
        drift_probability=0.5,
    )

    assert day1_event is not None
    assert day1_event["method"] == "checkfile_trigger"
    assert day2_event is None
    assert day2_profile["drift_state"]["status"] == "observing"
    assert day3_event is not None
    assert day3_event["method"] == "observing_timeout"
    assert day3_profile["drift_state"]["status"] == "stable"
    assert day3_profile["drift_state"]["hidden_anchor"] is None


def test_observing_enters_shifting_when_anchor_is_selected_within_window():
    engine = drift_engine.DriftEngine([_matching_checkfile()])
    profile = {
        "core_directions": {"gui-agent": 0.72},
        "topic_weights": {"gui-agent": 0.72},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {"shift_topics": ["multimodal-reasoning"]},
        "drift_state": {"status": "stable", "score": 0.0},
    }

    trigger_selected = [
        {"title": "Multimodal reasoning for interface agents", "abstract": "", "categories": [], "authors": []},
        {"title": "Robust multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
    ]
    supportive_selected = [
        {"title": "Multimodal reasoning for agents", "abstract": "", "categories": [], "authors": []},
    ]

    day1_profile, day1_event = engine.advance_profile_drift(
        profile,
        selected_papers=trigger_selected,
        date="2026-03-01",
        drift_probability=0.5,
    )
    day2_profile, day2_event = engine.advance_profile_drift(
        day1_profile,
        selected_papers=supportive_selected,
        date="2026-03-02",
        drift_probability=0.5,
    )

    assert day1_event is not None
    assert day1_event["method"] == "checkfile_trigger"
    assert day2_event is not None
    assert day2_event["method"] == "anchor_lock"
    assert day2_profile["drift_state"]["status"] == "shifting"


def test_without_matching_checkfile_simulation_stays_stable():

    engine = drift_engine.DriftEngine([])
    profile = {
        "core_directions": {"gui-agent": 0.72},
        "topic_weights": {"gui-agent": 0.72},
        "must_read": {"keywords": ["gui agent"]},
        "drift_plan": {"shift_topics": ["multimodal-reasoning"]},
        "drift_state": {"status": "stable", "score": 0.0, "last_drift_date": None},
    }

    updated_profile, event = engine.advance_profile_drift(profile, selected_papers=[], date="2026-03-01", drift_probability=0.5)

    assert event is None
    assert updated_profile["drift_state"]["drift_enabled"] is None
    assert updated_profile["drift_state"]["hidden_anchor"] is None


def test_simulation_max_drift_cycles_blocks_additional_cycles(monkeypatch):
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
            "completed_drift_cycles": 3,
            "max_drift_cycles": 3,
        },
    }

    updated_profile, event = engine.advance_profile_drift(
        profile,
        selected_papers=[
            {"title": "Multimodal reasoning benchmark", "abstract": "", "categories": [], "authors": []},
            {"title": "Multimodal reasoning for agents", "abstract": "", "categories": [], "authors": []},
        ],
        date="2026-03-01",
        drift_probability=0.5,
    )

    assert event is None
    assert updated_profile["drift_state"]["hidden_anchor"] is None
    assert updated_profile["drift_state"]["drift_enabled"] is False
